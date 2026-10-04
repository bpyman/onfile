"""The recorded runtime and the live runtime, and the builders that choose between them."""

import json
import logging
import threading
from collections.abc import Callable
from functools import lru_cache
from pathlib import Path

from financial_analyst_agent.config import AppMode, Settings, get_settings
from financial_analyst_agent.contracts import Runtime, RuntimeKind
from financial_analyst_agent.domain.errors import ProviderError, ProviderRefusal
from financial_analyst_agent.essay import OpenAIEssayCompleter
from financial_analyst_agent.facts import RecordedSECDataSource
from financial_analyst_agent.news import (
    FIXTURE_NEWS_QUERY,
    FIXTURE_RESEARCH_QUERY,
    RecordedNewsSearch,
    TavilyNewsSearch,
    replay_key,
)
from financial_analyst_agent.planner import OpenAIStructuredCompleter
from financial_analyst_agent.providers.sec.cache import CachingSECDataSource
from financial_analyst_agent.providers.sec.client import SECClient
from financial_analyst_agent.ranking import SnapshotRanking
from financial_analyst_agent.rules_planner import (
    FIXTURE_UNIVERSE_SNAPSHOT_PATH as FIXTURE_UNIVERSE_SNAPSHOT_PATH,
)
from financial_analyst_agent.rules_planner import (
    RECORDED_FILING_NEWER as RECORDED_FILING_NEWER,
)
from financial_analyst_agent.rules_planner import (
    RECORDED_FILING_OLDER as RECORDED_FILING_OLDER,
)
from financial_analyst_agent.rules_planner import (
    DemoCompleter as DemoCompleter,
)
from financial_analyst_agent.rules_planner import issuer_index, recorded_issuer_index
from financial_analyst_agent.sec_facts import SecFactLookup
from financial_analyst_agent.session import SessionBudget

_LOGGER = logging.getLogger("financial_analyst_agent")

FIXTURE_EXPLAIN_ESSAY = (
    "AI can disrupt healthcare by automating imaging review, triage, and documentation. "
    "Common use cases include clinical decision support, administrative coding, "
    "and patient outreach."
)
FIXTURE_EXPLAIN_QUERY = "How can AI disrupt healthcare?"
# Written from the recorded Microsoft 10-Q pair's changes, one per reviewed
# section, and replayed only for that evidence. No numerals, so the numeral lock
# has nothing to check against the grounding.
RECORDED_DISCLOSURE_SUMMARIES = {
    (RECORDED_FILING_OLDER, RECORDED_FILING_NEWER, "mda"): (
        "Management's highlights now report faster Microsoft Cloud and Azure growth "
        "and add the commercial remaining performance obligation, while Windows OEM "
        "and Devices and Xbox content and services revenue now fell where a year "
        "earlier they grew. The MD&A adds the extended OpenAI partnership, and "
        "currency movements now raised reported revenue and expenses rather than "
        "lowering them."
    ),
    (RECORDED_FILING_OLDER, RECORDED_FILING_NEWER, "risk_factors"): (
        "Across the Risk Factors, competition and other risks now “could” rather "
        "than “may” affect results; the platform risk adds that scale is needed to "
        "meet consumer demand; the investment risks are reworded around AI-based "
        "products; OpenAI is now described as a long-term strategic partnership; "
        "the impairment risk says such charges have been recorded; and the security "
        "risk names cybercriminal groups."
    ),
}
RECORDED_SUMMARY_MISSING = (
    "No summary is shown: the recorded demo holds one only for the Microsoft 10-Qs "
    "it recorded. The live runtime can summarize any filing pair."
)


def _recorded_disclosure_summary(tool_json: str) -> str:
    """The recorded summary for exactly this evidence, one sentence per section."""
    try:
        payload = json.loads(tool_json)
    except json.JSONDecodeError as exc:
        raise ProviderError("Recorded disclosure changes were invalid") from exc
    if not isinstance(payload, list) or not payload:
        raise ProviderRefusal(RECORDED_SUMMARY_MISSING)
    keys: list[tuple[str, str, str]] = []
    for item in payload:
        if not isinstance(item, dict):
            raise ProviderRefusal(RECORDED_SUMMARY_MISSING)
        key = (
            str(item.get("older_accession") or ""),
            str(item.get("newer_accession") or ""),
            str(item.get("section") or ""),
        )
        if key not in RECORDED_DISCLOSURE_SUMMARIES:
            raise ProviderRefusal(RECORDED_SUMMARY_MISSING)
        if key not in keys:
            keys.append(key)
    return " ".join(RECORDED_DISCLOSURE_SUMMARIES[key] for key in keys)


class RecordedEssayCompleter:
    """Recorded essay so explain and news_and_explain turns stay offline.

    The live runtime uses it too when it has no OpenAI key (``live=True``);
    its refusals then say that, rather than pointing at the live runtime.
    """

    def __init__(self, *, live: bool = False) -> None:
        self._live = live

    def _refusal(self, captured: str) -> ProviderRefusal:
        if self._live:
            return ProviderRefusal(
                "Written answers need an OpenAI key, which this server does not have. "
                f"It can replay the one it captured, for {captured}."
            )
        return ProviderRefusal(
            f"The recorded demo replays written answers only for {captured}. "
            "Switch to Live for other questions."
        )

    def complete_essay(self, query: str, tool_json: str = "") -> str:
        asked = replay_key(query)
        if asked == replay_key(FIXTURE_EXPLAIN_QUERY):
            # Asked after a lookup, the question arrives with that lookup's facts.
            return FIXTURE_EXPLAIN_ESSAY
        if not tool_json:
            raise self._refusal(f"“{FIXTURE_EXPLAIN_QUERY}”")
        if asked not in {
            replay_key(FIXTURE_NEWS_QUERY),
            replay_key(FIXTURE_RESEARCH_QUERY),
        } and "disclosure changes" not in asked:
            raise self._refusal(
                f"“{FIXTURE_EXPLAIN_QUERY}” and “{FIXTURE_NEWS_QUERY}”"
            )
        if "disclosure changes" in query.casefold():
            return _recorded_disclosure_summary(tool_json)
        try:
            payload = json.loads(tool_json)
        except json.JSONDecodeError as exc:
            raise ProviderError("Recorded fixture news input was invalid") from exc
        if not isinstance(payload, list):
            raise ProviderError("Recorded fixture news input was not a list")
        sentences: list[str] = []
        for item in payload:
            if not isinstance(item, dict):
                continue
            title = str(item.get("title") or "").strip()
            snippet = str(item.get("snippet") or "").strip()
            published = str(item.get("published") or "").strip()
            if not title:
                continue
            sentence = f"{title}: {snippet}" if snippet else title
            if published:
                sentence = f"{sentence} ({published})"
            sentences.append(sentence)
        if not sentences:
            raise ProviderError("Recorded fixture news input contained no usable hits")
        return " ".join(sentences)


@lru_cache(maxsize=4)
def _cached_ranking(path: Path | None, _mtime_ns: int) -> SnapshotRanking:
    # The planner's index: a company resolves the way the planner read it.
    return SnapshotRanking.from_path(path, issuer_index(path))


def _display_names(path: Path | None) -> dict[str, str]:
    """Snapshot company names by CIK, for tables that read like the landing page."""
    return {
        company.cik: company.name for company in _snapshot_ranking(path).snapshot_companies()
    }


def _listed_tickers(path: Path | None) -> dict[str, str]:
    """The snapshot's ticker for each CIK: the listing rankings show."""
    return {
        company.cik: company.ticker for company in _snapshot_ranking(path).snapshot_companies()
    }


def _member_ticker(path: Path | None) -> Callable[[str], str]:
    """The snapshot ticker a company name resolves to, for the facts lookup."""
    ranking = _snapshot_ranking(path)
    return lambda company: ranking.lookup_member(company).ticker


def _snapshot_ranking(path: Path | None) -> SnapshotRanking:
    """The snapshot is immutable per file version; parse it once, not on every turn."""
    from financial_analyst_agent.universe import DEFAULT_SNAPSHOT_PATH

    resolved = path or DEFAULT_SNAPSHOT_PATH
    return _cached_ranking(path, resolved.stat().st_mtime_ns)


_SEC_CLIENTS: dict[tuple[object, ...], SECClient] = {}
_SEC_CLIENTS_LOCK = threading.Lock()


def _shared_sec_client(settings: Settings) -> SECClient:
    """One SEC client (and connection pool) per configuration for the process.

    A client per turn left an unclosed httpx pool behind on every live turn.
    """
    key = (
        settings.sec_user_agent,
        settings.sec_base_url,
        settings.sec_max_requests_per_second,
        settings.sec_timeout_seconds,
        settings.sec_request_deadline_seconds,
        settings.sec_max_response_bytes,
        settings.sec_block_pause_seconds,
    )
    with _SEC_CLIENTS_LOCK:
        client = _SEC_CLIENTS.get(key)
        if client is None:
            client = SECClient(settings)
            _SEC_CLIENTS[key] = client
        return client


def recorded_runtime() -> Runtime:
    """Replay captured SEC, news, and model responses; never touches the network."""
    source = RecordedSECDataSource()
    return Runtime(
        completer=DemoCompleter(recorded_issuer_index(), recorded=True),
        filings=source,
        facts=SecFactLookup(
            client=source,
            display_names=_display_names(FIXTURE_UNIVERSE_SNAPSHOT_PATH),
            listed_tickers=_listed_tickers(FIXTURE_UNIVERSE_SNAPSHOT_PATH),
            member_ticker=_member_ticker(FIXTURE_UNIVERSE_SNAPSHOT_PATH),
        ),
        ranking=_snapshot_ranking(FIXTURE_UNIVERSE_SNAPSHOT_PATH),
        news=RecordedNewsSearch(),
        essay=RecordedEssayCompleter(),
        kind=RuntimeKind.RECORDED,
    )


def openai_enabled(settings: Settings) -> bool:
    """Whether the live runtime plans and writes with OpenAI (a key, and allowed here)."""
    return bool(settings.openai_api_key.strip()) and (
        not settings.public_demo or settings.allow_public_openai
    )


def tavily_enabled(settings: Settings) -> bool:
    """Whether the live runtime searches news with Tavily (a key, and allowed here)."""
    return bool(settings.tavily_api_key.strip()) and (
        not settings.public_demo or settings.allow_public_tavily
    )


def live_runtime(
    settings: Settings | None = None,
    *,
    budget: SessionBudget | None = None,
) -> Runtime:
    resolved = settings or get_settings()
    # Without an OpenAI key (or with public OpenAI turned off) the rules planner plans.
    use_openai = openai_enabled(resolved)
    use_tavily = tavily_enabled(resolved)
    completer = (
        OpenAIStructuredCompleter.from_settings(resolved)
        if use_openai
        else DemoCompleter(issuer_index())
    )
    essay = (
        OpenAIEssayCompleter.from_settings(resolved)
        if use_openai
        else RecordedEssayCompleter(live=True)
    )
    news = TavilyNewsSearch(resolved) if use_tavily else RecordedNewsSearch()
    cache_dir = resolved.sec_cache_dir or Path(".cache") / "sec"
    client = CachingSECDataSource(
        _shared_sec_client(resolved),
        Path(cache_dir),
        budget=budget,
        # Waiting on another turn's fetch longer than one request may take is pointless.
        fill_wait_seconds=resolved.sec_request_deadline_seconds,
        max_bytes=resolved.sec_cache_max_bytes,
    )
    return Runtime(
        completer=completer,
        filings=client,
        facts=SecFactLookup(
            client=client,
            display_names=_display_names(None),
            listed_tickers=_listed_tickers(None),
            member_ticker=_member_ticker(None),
        ),
        ranking=_snapshot_ranking(None),
        news=news,
        essay=essay,
        kind=RuntimeKind.LIVE,
        live_news=use_tavily,
        live_essays=use_openai,
    )


def live_sec_configured(settings: Settings) -> bool:
    """Whether live SEC requests can be made: SEC asks for a User-Agent naming a contact."""
    return bool(settings.sec_user_agent.strip())


def runtime_locked(settings: Settings | None = None) -> bool:
    """Whether this deployment serves only the recorded runtime.

    A public demo (``PUBLIC_DEMO`` on) with ``DEMO_LIVE_SEC`` off is locked, and
    so is any deployment without ``SEC_USER_AGENT``: its live turns could only fail.
    """
    resolved = settings or get_settings()
    demo_off = bool(resolved.public_demo) and not resolved.demo_live_sec
    return demo_off or not live_sec_configured(resolved)


def resolve_runtime_kind(kind: RuntimeKind, settings: Settings | None = None) -> RuntimeKind:
    """The runtime this deployment serves when ``kind`` is asked for.

    A locked deployment (see ``runtime_locked``) serves recorded for every request.
    """
    if runtime_locked(settings):
        return RuntimeKind.RECORDED
    return kind


def default_runtime_kind(settings: Settings | None = None) -> RuntimeKind:
    """The runtime ``APP_MODE`` selects, after the public-demo lock."""
    resolved = settings or get_settings()
    kind = RuntimeKind.RECORDED if resolved.app_mode is AppMode.RECORDED else RuntimeKind.LIVE
    return resolve_runtime_kind(kind, resolved)


def runtime_for(
    kind: RuntimeKind,
    *,
    settings: Settings | None = None,
    budget: SessionBudget | None = None,
) -> Runtime:
    """Build the runtime asked for.

    A locked public demo builds the recorded runtime even when the live one is asked
    for (see ``resolve_runtime_kind``); read ``Runtime.kind`` for the answer.
    """
    resolved = settings or get_settings()
    if resolve_runtime_kind(kind, resolved) is RuntimeKind.RECORDED:
        return recorded_runtime()
    return live_runtime(resolved, budget=budget)


def build_runtime(settings: Settings | None = None) -> Runtime:
    """Build the runtime ``APP_MODE`` selects.

    ``APP_MODE=live`` without ``SEC_USER_AGENT`` answers from the recording, as
    the API does (``runtime_locked``); outside the API nothing else says so, so
    it is logged here, and the MCP tools name the runtime in every answer.
    """
    resolved = settings or get_settings()
    if resolved.app_mode is AppMode.LIVE and not live_sec_configured(resolved):
        _LOGGER.warning(
            "APP_MODE=live but SEC_USER_AGENT is unset: answering from the recorded runtime"
        )
    return runtime_for(default_runtime_kind(resolved), settings=resolved)
