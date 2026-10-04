"""Deterministic company resolution from SEC ticker mapping."""

import re
import threading
from dataclasses import dataclass
from typing import Any

from financial_analyst_agent.domain.errors import (
    AmbiguousCompanyError,
    CompanyNotFoundError,
)
from financial_analyst_agent.domain.models import Company
from financial_analyst_agent.providers.sec.aliases import ALIASES
from financial_analyst_agent.providers.sec.tickers import extract_usable_ticker_entries, parse_cik

_LEGAL_SUFFIXES = re.compile(
    r"(?:,)?\s+(?:"
    r"incorporated|inc|corporation|corp|companies|company|co|"
    r"limited|ltd|holdings|holding|group|llc|l\.l\.c|"
    r"lp|l\.p|plc|s\.a|sa|n\.v|nv|a\.g|ag|"
    r"class\s+[a-z]|ordinary\s+shares?"
    r")\.?$",
    re.IGNORECASE,
)
_MIN_CORE_PREFIX_LEN = 4
# "MAIN" or "BRK.A": a ticker. One the mapping lacks names no company by prefix
# ("MAIN" is not MainStreet Bancshares, "CHEV" is not Chevron).
_TICKER_SHAPE = re.compile(r"[A-Z]{1,5}(?:[.\-/][A-Z])?")


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip()).casefold()


def _core_company_name(name: str) -> str:
    """Strip legal suffixes and punctuation so successor titles match operating names."""
    text = _normalize_text(name)
    while True:
        stripped = _LEGAL_SUFFIXES.sub("", text).strip(" ,.")
        if stripped == text:
            break
        text = stripped
    return re.sub(r"[^a-z0-9]+", "", text)


def _group_by_cik(entries: list[dict[str, str]]) -> dict[str, dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for entry in entries:
        cik = entry["cik"]
        bucket = grouped.setdefault(cik, {"title": entry["title"], "tickers": {}})
        # SEC lists a filer's main listing first (BRK-B before BRK-A); keep that order.
        bucket["tickers"].setdefault(entry["ticker"], None)
    return grouped


def _ordered_tickers(tickers: dict[str, None], primary_ticker: str | None = None) -> list[str]:
    listed = list(tickers)
    if primary_ticker is None:
        return listed
    primary = primary_ticker.upper()
    others = [ticker for ticker in listed if ticker != primary]
    return [primary, *others]


def _company_from_group(
    cik: str,
    group: dict[str, Any],
    primary_ticker: str | None = None,
) -> Company:
    tickers = _ordered_tickers(group["tickers"], primary_ticker)
    return Company(cik=cik, name=group["title"], tickers=tickers)


def _unique_cik(
    query: str,
    entries: list[dict[str, str]],
    ciks: set[str],
    message: str,
) -> str:
    if len(ciks) > 1:
        matches = [entry for entry in entries if entry["cik"] in ciks]
        raise AmbiguousCompanyError(
            message,
            details={"query": query, "matches": matches},
        )
    return next(iter(ciks))


@dataclass(frozen=True)
class _TickerIndex:
    """A ticker mapping read once: its rows, each filer's group, each title's readings."""

    entries: list[dict[str, str]]
    grouped: dict[str, dict[str, Any]]
    # (cik, normalised title, core name) for each row, in the mapping's order.
    titles: list[tuple[str, str, str]]


# The last few ticker payloads read, each held with its index. Holding the payload
# keeps its id from being reused; a turn asks of the same payload many times.
_INDEXES: dict[int, tuple[dict[str, Any], _TickerIndex]] = {}
_INDEXES_LOCK = threading.Lock()
_MAX_INDEXES = 4


def _ticker_index(payload: dict[str, Any]) -> _TickerIndex:
    with _INDEXES_LOCK:
        held = _INDEXES.get(id(payload))
    if held is not None and held[0] is payload:
        return held[1]
    entries = extract_usable_ticker_entries(payload)
    index = _TickerIndex(
        entries=entries,
        grouped=_group_by_cik(entries),
        titles=[
            (entry["cik"], _normalize_text(entry["title"]), _core_company_name(entry["title"]))
            for entry in entries
        ],
    )
    with _INDEXES_LOCK:
        while len(_INDEXES) >= _MAX_INDEXES:
            _INDEXES.pop(next(iter(_INDEXES)))
        _INDEXES[id(payload)] = (payload, index)
    return index


def _name_match_ciks(query: str, index: _TickerIndex, *, prefix: bool = True) -> set[str]:
    normalized_query = _normalize_text(query)
    exact = {cik for cik, title, _core in index.titles if title == normalized_query}
    if exact:
        return exact
    query_core = _core_company_name(query)
    if not query_core:
        return set()
    core_matches = {cik for cik, _title, core in index.titles if core == query_core}
    if core_matches:
        return core_matches
    if not prefix or len(query_core) < _MIN_CORE_PREFIX_LEN:
        return set()
    return {cik for cik, _title, core in index.titles if core and core.startswith(query_core)}


def resolve_company(query: str, tickers_payload: dict[str, Any]) -> Company:
    """
    Resolve a company query using deterministic precedence:

    1. Exact normalized ticker (issuer-level; multiple tickers per CIK consolidate)
    2. Direct CIK
    3. Explicit alias registry
    4. Legal name, then suffix-stripped core name, then unique core prefix
       (never for a ticker-shaped query: "MAIN" is not MainStreet Bancshares)
    5. Typed not-found or ambiguity error

    Ambiguity is raised only when valid matches span multiple distinct CIKs.
    Multiple ticker entries sharing one CIK represent one issuer.
    Core-name matching covers successor/holdings titles (ExxonMobil vs
    ExxonMobil Holdings Corp) without a per-issuer alias list.
    """
    normalized_query = _normalize_text(query)
    index = _ticker_index(tickers_payload)
    entries = index.entries
    if not entries:
        raise CompanyNotFoundError("SEC ticker mapping was empty")

    grouped = index.grouped

    ticker_query = normalized_query.upper()
    ticker_matches = [entry for entry in entries if entry["ticker"] == ticker_query]
    if ticker_matches:
        ticker_ciks = {entry["cik"] for entry in ticker_matches}
        cik = _unique_cik(
            query, ticker_matches, ticker_ciks, "Multiple CIKs matched ticker query"
        )
        return _company_from_group(cik, grouped[cik], primary_ticker=ticker_query)

    cik_query = parse_cik(query.strip())
    if cik_query is not None and cik_query in grouped:
        return _company_from_group(cik_query, grouped[cik_query])

    alias_target = ALIASES.get(normalized_query)
    if alias_target is not None:
        alias_ciks = _name_match_ciks(alias_target, index)
        if not alias_ciks:
            raise CompanyNotFoundError(
                f"Alias target '{alias_target}' not found in SEC ticker mapping",
                details={"query": query, "alias": alias_target},
            )
        cik = _unique_cik(
            query, entries, alias_ciks, "Multiple CIKs matched alias target"
        )
        return _company_from_group(cik, grouped[cik])

    name_ciks = _name_match_ciks(
        query, index, prefix=_TICKER_SHAPE.fullmatch(query.strip()) is None
    )
    if not name_ciks:
        raise CompanyNotFoundError(
            f"Company not found for query '{query}'",
            details={"query": query},
        )
    cik = _unique_cik(
        query, entries, name_ciks, "Multiple CIKs matched legal name query"
    )
    return _company_from_group(cik, grouped[cik])
