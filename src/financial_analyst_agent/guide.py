"""Guide replies and suggested next questions.

Some messages are not analysis requests: a greeting, "what can you do?", "is
Apple a good buy?", or "why?". They get a short, friendly answer that points at
what the window can do, instead of a refusal. Every answer also offers a few
next questions, phrased in words the planner reads, so the analyst can keep
exploring with one tap.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from datetime import date
from typing import Any

from financial_analyst_agent.contracts import (
    FORMULA_METRICS,
    Intent,
    RendererKind,
    TurnResult,
)
from financial_analyst_agent.graph.analysis_spec import AnalysisSpec
from financial_analyst_agent.issuer_index import CompanyNames, expand_groups
from financial_analyst_agent.services.metric_catalog import METRIC_DISPLAY

STARTER_QUESTIONS: tuple[str, ...] = (
    "How is Nvidia doing?",
    "Compare Apple and Microsoft revenue year over year",
    "Top 5 semiconductor companies by revenue",
    "What changed in Microsoft's latest 10-Q?",
)
HELP_MESSAGE = (
    "I answer from companies' SEC filings. Ask for a quarterly figure (revenue, "
    "net income, margins, EPS, free cash flow, EBITDA, cash, dividends, return on "
    "equity, P/E, share price), name a period (“Q3 2024”, "
    "“fiscal 2025”), compare companies, rank an industry, track a metric over "
    "several quarters, or see what changed in a 10-Q. Every number links to the "
    "filing it came from."
)
GREETING_MESSAGE = "Hi! " + HELP_MESSAGE
THANKS_MESSAGE = "Glad that helped. Here are a few places to go next."
ADVICE_MESSAGE = (
    "I don't give investment advice or price predictions. I can show what "
    "{subject} filings report, so you can judge for yourself."
)
NOT_RECORDED_MESSAGE = (
    "{name} isn't in the recorded demo. It replays SEC filings for a fixed set of "
    "companies, such as Apple, Microsoft, NVIDIA and JPMorgan Chase. With live "
    "data, any US-listed operating company works."
)
WHY_MESSAGE = (
    "Filings report what happened, not why. Management explains the quarter in "
    "the MD&A section of the 10-Q, and I can show what changed there."
)

_GREETING = re.compile(
    r"^(?:hi|hello|hey|hiya|yo|howdy|good (?:morning|afternoon|evening))(?: there)?$"
)
_HELP = re.compile(
    r"^(?:help|\?|menu|examples?|show me examples|capabilities|what is this|who are you"
    r"|what are you)$"
    r"|\bwhat (?:can|do) you (?:do|answer|know)\b|\bwhat can i ask\b"
    r"|\bhow (?:does this|do i use this|do i use you)\b"
)
_THANKS = re.compile(r"^(?:thanks|thank you|thx|ty|cheers|great|awesome|nice|cool|perfect)\b")
_ADVICE = re.compile(
    r"\b(?:should i (?:buy|sell|invest|hold|short)|(?:good|bad) (?:buy|investment|stock)"
    r"|worth (?:buying|investing)|invest in|price target|stock (?:go up|go down|rise|fall)"
    r"|buy or sell|undervalued|overvalued|buy the dip)\b"
    r"|\b(?:is|are)\b.{1,40}?\ba (?:good |bad |strong |safe )?(?:buy|sell|hold)\b"
    # "Best stock to buy?", "what stocks should I buy", "stock tips".
    r"|\b(?:best|top|hottest|safest) (?:stocks?|shares?|investments?|picks?)"
    r"(?: to (?:buy|own|invest in|hold))?\b"
    r"|\b(?:which|what) (?:stocks?|shares?|companies) (?:to|should i|do i|would you) "
    r"(?:buy|invest|own|pick)\b"
    r"|\bstock (?:tips?|picks?|recommendations?)\b|\bwhere (?:should|do) i invest\b"
)
STOCK_PICKS_MESSAGE = (
    "I don't give investment advice or pick stocks. I can show what companies' filings "
    "report, so you can compare them yourself, for example “Top 5 semiconductor companies "
    "by revenue” or “Compare Apple and Microsoft net margin”."
)
ENGLISH_MESSAGE = (
    "I read questions in English for now. Try, for example, “What was Apple's revenue "
    "last quarter?”"
)
# Words of other languages a finance question uses; with no catalog metric in
# the question, they mean it was not asked in English.
_FOREIGN_WORDS = frozenset(
    """
    cuál cuáles cual fueron los las ingresos ganancias beneficio último trimestre empresa
    qué cuánto wie hoch war der die das umsatz gewinn von quartal welche ist quel quelle
    est le les chiffre d'affaires bénéfice trimestre dernier quanto receita lucro
    """.split()  # noqa: SIM905
)
_NON_LATIN = re.compile(r"[Ѐ-ӿ֐-ۿऀ-ॿ぀-ヿ㐀-鿿가-힯]")
NOT_OPERATING_MESSAGE = (
    "SPACs, business development companies, funds and ETFs aren't operating companies, "
    "so the snapshot leaves them out and they can't be ranked or looked up. Rankings "
    "cover operating companies, for example “Top 5 banks by revenue”."
)
_NOT_OPERATING_GROUP = re.compile(
    r"\b(?:spacs?|blank[- ]check|bdcs?|business development compan(?:y|ies)|etfs?"
    r"|(?:mutual |index |hedge )?funds?|closed[- ]end)\b"
)
_RANKING_WORDS = re.compile(r"\b(?:top|biggest|largest|leading|rank(?:ed|ing)?|best)\b")
ETF_MESSAGE = (
    "{ticker} is an exchange-traded fund, not an operating company, so it files no 10-Q "
    "figures to look up. Ask about a company it holds, for example “Apple revenue”."
)
# Funds people name by ticker that SEC's company list does not hold.
_ETF_TICKERS = frozenset(
    """
    QQQ VOO VTI IVV IWM DIA GLD SLV ARKK XLK XLF XLE XLV VGT SCHD TLT HYG LQD EEM EFA
    VEA VWO BND AGG SMH SOXX TQQQ SQQQ VNQ JEPI VIG VYM IEMG IEFA RSP
    """.split()  # noqa: SIM905
)
_ETF_MENTION = re.compile(r"(?<![\w$])\$?([A-Z]{3,5})\b")
NEVER_MIND_MESSAGE = "Okay, set that aside. Ask about any company, industry or period."
_NEVER_MIND = re.compile(r"^(?:never ?mind|nevermind|cancel|forget it|nvm|skip it)$")
START_OVER_MESSAGE = "Started over. Ask about any company, industry or period."
UNDO_MESSAGE = (
    "I can't undo a step yet. Say what to change instead (“remove Apple”, “just "
    "revenue”, “last 4 quarters”), or start over."
)
_START_OVER = re.compile(r"^(?:start (?:over|again|fresh)|reset|clear|new (?:question|analysis))$")
_UNDO = re.compile(r"^(?:undo|go back|back|revert|undo that)$")
_WHY = re.compile(r"^why\b")
_CHART = re.compile(
    r"^(?:can you |please )?(?:chart|plot|graph|visuali[sz]e|draw)(?: it| that| this| them)?$"
)
CHART_MESSAGE = (
    "Charts appear on their own when an answer has several quarters or several "
    "companies. Ask for a window or add a company, and the chart follows."
)
SMALLEST_MESSAGE = (
    "Rankings start from the largest companies by market cap, so I can't list the "
    "smallest yet."
)
_SMALLEST = re.compile(r"\b(?:smallest|tiniest|bottom\s+\d+)\b")
_SMALLEST_GROUP = re.compile(
    r"\b(?:smallest|tiniest|bottom)\s+(?:\d+\s+)?(?P<group>[a-z&][a-z& -]*?)\s+"
    r"(?:companies|company|stocks|firms)\b"
)
UNSUPPORTED_MESSAGE = (
    "I can't look up {names} yet. I answer from reported 10-Q figures such as "
    "revenue, net income, margins, EPS, cash flow, cash, dividends and P/E."
)
_WHY_MAX_WORDS = 6
_THANKS_MAX_WORDS = 4


def _normalized(message: str) -> str:
    text = message.strip().casefold().replace("’", "'")
    return " ".join(re.sub(r"[!.,]+", " ", text).split()).rstrip(" ?") or text.strip()


def _guide(message: str, suggestions: list[str]) -> TurnResult:
    return TurnResult(
        intent=Intent.LOOKUP,
        tool_traces=[],
        renderer=RendererKind.REFUSE,
        message=message,
        suggestions=suggestions,
        guide=True,
    )


def _spec_company(spec: AnalysisSpec | None) -> tuple[str, str] | None:
    """(display name, planner query) of the current analysis's first company."""
    if spec is None:
        return None
    if spec.companies:
        company = spec.companies[0]
        return short_name(company.name) or company.query, company.query
    return None


def guide_reply(
    message: str, spec: AnalysisSpec | None, index: CompanyNames | None = None
) -> TurnResult | None:
    """A guide answer when the message is not an analysis request, else None."""
    text = _normalized(message)
    if not text:
        return None
    if _GREETING.match(text):
        return _guide(GREETING_MESSAGE, list(STARTER_QUESTIONS))
    if _HELP.search(text) or text == "?":
        return _guide(HELP_MESSAGE, list(STARTER_QUESTIONS))
    if _THANKS.match(text) and len(text.split()) <= _THANKS_MAX_WORDS:
        return _guide(THANKS_MESSAGE, list(STARTER_QUESTIONS[:3]))
    if _NEVER_MIND.match(text):
        return _guide(NEVER_MIND_MESSAGE, list(STARTER_QUESTIONS[:3]))
    if _ADVICE.search(text):
        named = _named_company(message, index) or _spec_company(spec)
        if named is None:
            return _guide(STOCK_PICKS_MESSAGE, list(STARTER_QUESTIONS[:3]))
        name, _query = named
        return _guide(
            ADVICE_MESSAGE.format(subject=possessive(name)),
            [
                f"How is {name} doing?",
                f"Show {name}'s revenue year over year",
                f"What changed in {name}'s latest 10-Q?",
            ],
        )
    if _not_english(text):
        return _guide(ENGLISH_MESSAGE, list(STARTER_QUESTIONS[:3]))
    if _NOT_OPERATING_GROUP.search(text) and _RANKING_WORDS.search(text):
        return _guide(NOT_OPERATING_MESSAGE, ["Top 5 banks by revenue", STARTER_QUESTIONS[2]])
    etf = _etf_ticker(message, index)
    if etf is not None:
        return _guide(ETF_MESSAGE.format(ticker=etf), list(STARTER_QUESTIONS[:3]))
    if _START_OVER.match(text):
        return _guide(START_OVER_MESSAGE, list(STARTER_QUESTIONS))
    if _UNDO.match(text):
        return _guide(UNDO_MESSAGE, ["start over"] if spec is not None else [])
    if _SMALLEST.search(text):
        group = _SMALLEST_GROUP.search(text)
        suggestion = (
            f"Top 5 {group.group('group')} companies by revenue"
            if group is not None
            else STARTER_QUESTIONS[2]
        )
        return _guide(SMALLEST_MESSAGE, [suggestion])
    unsupported = _unsupported_metrics(text)
    if unsupported:
        named = _named_company(message, index) or _spec_company(spec)
        suggestions = (
            [f"How is {named[0]} doing?", f"{named[0]} free cash flow last 4 quarters"]
            if named is not None
            else list(STARTER_QUESTIONS[:3])
        )
        return _guide(UNSUPPORTED_MESSAGE.format(names=joined(unsupported, "or")), suggestions)
    if _CHART.match(text):
        return _guide(CHART_MESSAGE, ["last 4 quarters", "show year-over-year"])
    if _WHY.match(text) and len(text.split()) <= _WHY_MAX_WORDS and not _names_figure(
        message, index
    ):
        # "why?" alone gets the guide; "why did revenue drop?" is a change to show.
        named = _spec_company(spec)
        if named is None:
            return _guide(WHY_MESSAGE, list(STARTER_QUESTIONS[3:]))
        name, _query = named
        return _guide(WHY_MESSAGE, [f"What changed in {name}'s latest 10-Q?"])
    return None


def _names_figure(message: str, index: CompanyNames | None) -> bool:
    """Whether a message names a catalog metric or a company: an analysis, not a chat."""
    from financial_analyst_agent.services.metric_catalog import resolve_metric_phrase

    return (
        resolve_metric_phrase(message).kind != "unknown"
        or _named_company(message, index) is not None
    )


def _not_english(text: str) -> bool:
    """A question in another language: other scripts, or its finance words, and no metric."""
    from financial_analyst_agent.services.metric_catalog import resolve_metric_phrase

    words = set(re.findall(r"[\w'’]+", text))
    foreign = _NON_LATIN.search(text) is not None or len(words & _FOREIGN_WORDS) >= 2
    return foreign and resolve_metric_phrase(text).kind == "unknown"


def _etf_ticker(message: str, index: CompanyNames | None) -> str | None:
    """A fund's ticker named on its own ("QQQ revenue"), which no company list holds."""
    found = [match.group(1) for match in _ETF_MENTION.finditer(message)]
    etf = next((ticker for ticker in found if ticker in _ETF_TICKERS), None)
    if etf is None:
        return None
    return etf if index is None or not index.find(message) else None


def resets_analysis(message: str) -> bool:
    """Whether a message asks to drop the current analysis ("start over")."""
    return _START_OVER.match(_normalized(message)) is not None


def _unsupported_metrics(text: str) -> list[str]:
    """Names of the uncatalogued measures a question asks for, when it asks for no other.

    The catalog lists the measures it lacks by name ("debt-to-equity", "return on
    assets"). A catalog metric beside one is answered instead, so "Apple revenue
    and dividend yield" still answers revenue.
    """
    from financial_analyst_agent.services.metric_catalog import (
        resolve_metric_phrase,
        resolve_metric_phrases,
    )

    if resolve_metric_phrase(text).kind != "unknown":
        return []
    named = [phrase.term for phrase in resolve_metric_phrases(text) if phrase.term is not None]
    return list(dict.fromkeys(named))


def not_recorded_reply(
    message: str, index: CompanyNames | None, outside: CompanyNames | None
) -> TurnResult | None:
    """A reply for a figures question naming only companies the recording left out.

    ``outside`` is the live snapshot's index on the recorded runtime. A company it
    finds that ``index`` does not was not recorded, and saying so beats answering
    about the companies already on screen. When the question also names recorded
    companies, those are answered and ``not_recorded_banner`` names the rest.
    """
    missing = unrecorded_companies(message, index, outside)
    if not missing:
        return None
    if index is not None and index.find(expand_groups(message)):
        return None
    return _guide(NOT_RECORDED_MESSAGE.format(name=missing[0]), list(STARTER_QUESTIONS[:3]))


def not_recorded_banner(missing: list[str]) -> str:
    """ "Amazon.com and Meta Platforms aren't in the recorded demo, so …"."""
    if len(missing) == 1:
        return (
            f"{missing[0]} isn't in the recorded demo, so it is left out. With live "
            "data, any US-listed operating company works."
        )
    names = joined(missing)
    return (
        f"{names} aren't in the recorded demo, so they are left out. With live data, "
        "any US-listed operating company works."
    )


def unrecorded_companies(
    message: str, index: CompanyNames | None, outside: CompanyNames | None
) -> list[str]:
    """Display names of companies ``outside`` finds in the message but ``index`` lacks."""
    if index is None or outside is None:
        return []
    missing: list[str] = []
    for mention in outside.find(expand_groups(message)):
        if index.find(mention.typed):
            continue
        display = outside.display_name(mention.query)
        name = short_name(display) or mention.typed
        if name not in missing:
            missing.append(name)
    return missing


def _named_company(message: str, index: CompanyNames | None) -> tuple[str, str] | None:
    if index is None:
        return None
    mentions = index.find(message)
    if not mentions:
        return None
    query = mentions[0].query
    display = index.display_name(query)
    return short_name(display) or query, query


_SUFFIX = re.compile(
    r"(?:,?\s+(?:inc|incorporated|corp|corporation|co|company|ltd|plc|holdings|group"
    r"|& co|& company|and company|a/s|ag|s\.?a|n\.?v|se)\.?)+$",
    re.IGNORECASE,
)


_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def format_date(value: date) -> str:
    """ "Mar 31, 2026", the same whatever the locale."""
    return f"{_MONTHS[value.month - 1]} {value.day}, {value.year}"


def joined(words: Sequence[str], conjunction: str = "and") -> str:
    """Words in prose: "A", "A and B", "A, B and C"."""
    if len(words) <= 1:
        return "".join(words)
    return f"{', '.join(words[:-1])} {conjunction} {words[-1]}"


def in_sentence(label: str) -> str:
    """ "Net margin" → "net margin" mid-sentence; "EBITDA" and "P/E ratio" keep their case."""
    if len(label) > 1 and (label[1].isupper() or not label[1].isalpha()):
        return label
    return label[:1].lower() + label[1:]


def possessive(name: str) -> str:
    """ "Apple's", "Abbott Laboratories'", and "Lowe's" left as it is."""
    if name.endswith(("'s", "’s")):
        return name
    return f"{name}'" if name.endswith("s") else f"{name}'s"


def short_name(name: str) -> str:
    """ "NVIDIA Corporation" → "NVIDIA"; "Eli Lilly and Company" → "Eli Lilly"."""
    short = _SUFFIX.sub("", name.strip()).strip(" ,.")
    # "The Goldman Sachs Group, Inc." reads as "Goldman Sachs".
    return re.sub(r"^the\s+(?=\S)", "", short, flags=re.IGNORECASE)


_METRIC_IDEAS: tuple[str, ...] = ("net_margin", "operating_margin", "revenue", "gross_margin")
_LABELS = {
    metric: in_sentence(METRIC_DISPLAY[metric].label)
    for metric in ("net_margin", "operating_margin", "gross_margin", "revenue", "net_income")
}
_MAX_SUGGESTIONS = 3
_MAX_COMPANIES_FOR_PEERS = 4


def suggest_follow_ups(result: TurnResult, spec: AnalysisSpec | None, ranking: Any) -> list[str]:
    """Next questions for a finished answer, in words the planner reads."""
    if result.suggestions or result.renderer is RendererKind.CLARIFY:
        return list(result.suggestions)
    if result.renderer is RendererKind.REFUSE:
        return list(STARTER_QUESTIONS[:3]) if spec is None else []
    if spec is None or result.intent not in (
        Intent.LOOKUP,
        Intent.COMPARE,
        Intent.RANK,
        Intent.RANK_AND_LOOKUP,
    ):
        return []
    ideas: list[str] = []
    metrics = set(spec.metrics)
    if spec.constituents is not None:
        for metric in ("revenue", "net_margin", "operating_margin"):
            if metric not in metrics:
                ideas.append(f"show their {_LABELS[metric]}")
                break
        if spec.constituents.limit > 5:
            ideas.append("only the top 5")
        return ideas[:_MAX_SUGGESTIONS]
    if not spec.companies:
        return []
    if "across_periods" not in spec.operations:
        ideas.append("show year-over-year")
    if len(spec.companies) < _MAX_COMPANIES_FOR_PEERS:
        peer = _peer_name(spec, ranking)
        if peer:
            ideas.append(f"add {peer}")
    for metric in _METRIC_IDEAS:
        if metric not in metrics and (metric not in FORMULA_METRICS or len(metrics) < 5):
            ideas.append(f"add {_LABELS[metric]}")
            break
    return ideas[:_MAX_SUGGESTIONS]


_FOREIGN_FORM = re.compile(
    r"\b(?:limited|plc|ag|n\.?v\.?|s\.?a\.?|se|s\.?p\.?a\.?|a/s|asa|ab)\.?$", re.IGNORECASE
)


def _peer_name(spec: AnalysisSpec, ranking: Any) -> str | None:
    peers = getattr(ranking, "peers", None)
    if not callable(peers):
        return None
    ciks = frozenset(company.cik for company in spec.companies if company.cik)
    for company in spec.companies:
        if not company.cik:
            continue
        for peer in peers(company.cik, exclude=ciks, limit=5):
            if _FOREIGN_FORM.search(peer.name):
                # Foreign filers report on 20-F, not 10-Q: a peer with no data.
                continue
            return short_name(peer.name) or peer.ticker
    return None
