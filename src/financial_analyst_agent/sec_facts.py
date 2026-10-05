"""SEC fact lookup over an injectable live or recorded data source."""

import threading
from collections import Counter, OrderedDict
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any, Protocol

from financial_analyst_agent.config import Settings
from financial_analyst_agent.domain.enums import PERIODIC_FORMS, Metric
from financial_analyst_agent.domain.errors import (
    SOURCE_FAILURES,
    AmbiguousCompanyError,
    CompanyNotFoundError,
    DataIntegrityError,
    FilingNotFoundError,
    NoDividendThisQuarterError,
    PerShareNotDerivableError,
    ProviderError,
    SessionQuotaError,
    UnsupportedQuarterlyFactError,
)
from financial_analyst_agent.domain.models import Company, FactRecord, Filing, FinancialFact
from financial_analyst_agent.providers.sec.client import SECClient
from financial_analyst_agent.providers.sec.company_facts import (
    parse_company_facts,
    parse_company_facts_for_concepts,
)
from financial_analyst_agent.providers.sec.company_resolver import resolve_company
from financial_analyst_agent.providers.sec.submissions import (
    files_quarterly_reports,
    parse_submissions,
    trim_submissions,
)
from financial_analyst_agent.providers.sec.tickers import parse_cik
from financial_analyst_agent.providers.sec.urls import build_filing_source_url
from financial_analyst_agent.services.fact_selector import (
    FactOwner,
    derive_quarter,
    derive_trailing_year,
    select_instant_fact,
    select_quarterly_fact_with_filing_fallback,
)
from financial_analyst_agent.services.filing_selector import (
    FISCAL_WEEK_TOLERANCE,
    get_annual_filings,
    get_candidate_filings,
    latest_period_end,
    list_quarterly_report_dates,
)
from financial_analyst_agent.services.fiscal_periods import (
    BANK_REVENUE_LABEL,
    FiscalLabel,
    FiscalPeriod,
    fiscal_labels,
    gross_profit_from_components,
    periods_from_filings,
    revenue_from_components,
    sum_of_components,
)
from financial_analyst_agent.services.metric_catalog import (
    GROSS_PROFIT_EXCLUDING_CONCEPTS,
    INSTANT_METRICS,
    METRIC_CONCEPTS,
    PER_SHARE_METRICS,
    READ_CONCEPTS,
    REVENUE_CHECK_CONCEPTS,
    SHARE_COUNT_CONCEPT,
    TRAILING_YEAR_METRICS,
    metric_unit,
    parse_metric,
)
from financial_analyst_agent.universe import require_operating

# How many periods back "latest" may step when SEC has not yet added the
# newest filings' numbers to companyfacts. A year: Citigroup's companyfacts
# lagged two 10-Qs in September 2026.
_LATEST_FALLBACK = 4


class SECDataSource(Protocol):
    """Provider boundary shared by live EDGAR and offline recordings."""

    def get_company_tickers(self) -> dict[str, Any]: ...

    def get_submissions(self, cik: str, *, with_history: bool = True) -> dict[str, Any]: ...

    def get_company_facts(self, cik: str) -> dict[str, Any]: ...

    def close(self) -> None: ...


# History the submissions list must span before company facts is asked for more.
_FULL_HISTORY_DAYS = 3 * 365
# Every concept a metric reads. A company's facts file holds a thousand concepts
# and parses to about 40 MB for a bank; once its whole-file summaries are taken,
# only these stay in memory (about 2 MB), so a ten-company ranking fits.
_READ_CONCEPTS = READ_CONCEPTS
# Facts files parsed at once across the process: a spike of rankings would
# otherwise hold dozens of whole files in memory together. Only the parse holds
# a slot; the download happens before it, so a slow SEC holds none.
_FACTS_PARSE_SLOTS = threading.BoundedSemaphore(2)
# Fewer periodic reports than this marks a new registrant worth a predecessor check.
_THIN_HISTORY = 4


# Companies whose parsed facts stay in memory across turns. A company's trimmed
# facts and summaries take about 2.5 to 4 MB, so this holds about 130 MB at most.
_PARSED_FACTS_LIMIT = 32


@dataclass(frozen=True)
class _ParsedFacts:
    """A company's facts as a lookup reads them: the catalog's concepts and two summaries."""

    concepts: dict[str, Any]
    labels: dict[str, FiscalLabel]
    filings: tuple[Filing, ...]


class _ParsedFactsCache:
    """Parsed company facts shared by every turn, keyed by the stamp of the file they came from.

    Reading a company's facts file decodes megabytes of JSON and summarises it
    again on every turn. A turn that asks about a company whose cached file has
    not changed reuses the last parse; a refreshed file has a new stamp and is
    parsed again. Shared across threads and turns, so nothing that reads a
    parse may change it. The least recently used company goes first.
    """

    def __init__(self, limit: int) -> None:
        self._limit = limit
        self._parsed: OrderedDict[tuple[str, int, int], _ParsedFacts] = OrderedDict()
        self._lock = threading.Lock()

    def get(self, stamp: tuple[str, int, int]) -> _ParsedFacts | None:
        with self._lock:
            parsed = self._parsed.get(stamp)
            if parsed is not None:
                self._parsed.move_to_end(stamp)
            return parsed

    def put(self, stamp: tuple[str, int, int], parsed: _ParsedFacts) -> None:
        with self._lock:
            # An older copy of the same file is never asked for again.
            for older in [key for key in self._parsed if key[0] == stamp[0]]:
                del self._parsed[older]
            self._parsed[stamp] = parsed
            while len(self._parsed) > self._limit:
                self._parsed.popitem(last=False)

    def clear(self) -> None:
        with self._lock:
            self._parsed.clear()


_PARSED_FACTS = _ParsedFactsCache(_PARSED_FACTS_LIMIT)


# A quarter whose filing SEC lists but whose facts its structured data lacks yet.
PENDING_IN_XBRL_MESSAGE = "SEC's structured data does not yet include this quarter's filing"
# Every entry SEC holds for the metric is malformed: not the same as not reported.
UNREADABLE_FACTS_MESSAGE = "SEC's structured data for this metric could not be read"


@dataclass(frozen=True)
class FilingSources:
    """Where a lookup's filings live, for their source links.

    ``folders`` names the registrant whose EDGAR folder holds a filing when it is
    not the company's own (a predecessor's reports, see ``SecFactLookup._filings``).
    ``primary_document`` finds a filing's main document when the filing at hand
    has none: one read from company facts (``SecFactLookup._with_facts_filings``).
    Without one the link is the filing's index page.
    """

    folders: Mapping[str, str] = field(default_factory=dict)
    primary_document: Callable[[str, str], str | None] | None = None

    def url(self, cik: str, filing: Filing) -> str:
        folder = self.folders.get(filing.accession_number, cik)
        if not filing.primary_document and self.primary_document is not None:
            document = self.primary_document(folder, filing.accession_number)
            if document:
                filing = filing.model_copy(update={"primary_document": document})
        return build_filing_source_url(folder, filing)


def _related_lookup_ciks(resolved_cik: str, predecessor: str | None) -> tuple[str, ...]:
    """The listed company's CIK, then its verified predecessor's (ExxonMobil's old CIK).

    An accession number's prefix alone is not enough: a subsidiary co-registrant
    (Georgia Power) files under its parent's prefix, and a filing agent
    (Workiva, Donnelley) under its own, so neither names the company asked for.
    """
    if predecessor is None or predecessor == resolved_cik:
        return (resolved_cik,)
    return (resolved_cik, predecessor)


def _select_or_derive(
    records: list[FactRecord],
    filings: list[Filing],
    metric: Metric,
    owner: FactOwner,
    *,
    report_date: date | None,
    sources: FilingSources | None = None,
) -> FinancialFact:
    fact = _select_or_derive_in_unit(
        records,
        filings,
        metric,
        owner,
        report_date=report_date,
        sources=sources,
    )
    # EPS is filtered by its "USD/shares" unit but is still an amount in dollars.
    return fact if fact.currency == "USD" else fact.model_copy(update={"currency": "USD"})


def _select_or_derive_in_unit(
    records: list[FactRecord],
    filings: list[Filing],
    metric: Metric,
    owner: FactOwner,
    *,
    report_date: date | None,
    sources: FilingSources | None = None,
) -> FinancialFact:
    """A reported quarter when a filing has one, else a derived quarter (ADR 0007).

    ``sources`` says where each filing lives, for its source link (``FilingSources``).
    """
    by_accession = {filing.accession_number: filing for filing in filings}
    where = sources or FilingSources()

    def source_url_for_filing(filing: Filing) -> str:
        return where.url(owner.cik, filing)

    def source_url_for_accession(accession: str) -> str:
        filing = by_accession.get(accession) or Filing(
            form="",
            accession_number=accession,
            filed_date=date.min,
            report_date=date.min,
        )
        return source_url_for_filing(filing)

    if report_date is None:
        raise FilingNotFoundError("No 10-Q or 10-K filing found")
    try:
        quarterly = get_candidate_filings(filings, report_date=report_date)
    except FilingNotFoundError:
        quarterly = []
    candidates = quarterly or get_annual_filings(filings, report_date=report_date)
    if not candidates:
        raise FilingNotFoundError(
            "No 10-Q or 10-K for reporting period",
            details={"report_date": report_date.isoformat()},
        )
    last: UnsupportedQuarterlyFactError | None = None
    if metric in INSTANT_METRICS or metric in TRAILING_YEAR_METRICS:
        for filing in candidates:
            try:
                if metric in INSTANT_METRICS:
                    return select_instant_fact(
                        records,
                        filing,
                        metric,
                        owner,
                        source_url_for_filing(filing),
                    )
                return derive_trailing_year(
                    records,
                    filing,
                    metric,
                    owner,
                    source_url_for_filing(filing),
                    source_url_for_accession,
                )
            except UnsupportedQuarterlyFactError as exc:
                last = last or exc
        assert last is not None
        raise last
    if quarterly:
        try:
            return select_quarterly_fact_with_filing_fallback(
                records,
                filings,
                metric,
                owner,
                source_url_for_filing,
                report_date=report_date,
            )[0]
        except UnsupportedQuarterlyFactError as exc:
            last = exc
    for filing in candidates:
        try:
            return derive_quarter(
                records,
                filing,
                metric,
                owner,
                source_url_for_filing(filing),
                source_url_for_accession,
            )
        except PerShareNotDerivableError:
            raise
        except UnsupportedQuarterlyFactError as exc:
            last = last or exc
    assert last is not None
    raise last


class SecFactLookup:
    """SEC XBRL lookup behind the application's get_financials port."""

    def __init__(
        self,
        settings: Settings | None = None,
        client: SECDataSource | None = None,
        display_names: Mapping[str, str] | None = None,
        listed_tickers: Mapping[str, str] | None = None,
        member_ticker: Callable[[str], str] | None = None,
    ) -> None:
        # The snapshot's reading of a company name ("Goldman Sachs" is GS), so a
        # fact is fetched for the company the analysis resolved, not re-guessed
        # from SEC titles ("Coca-Cola" is KO, not one of three bottlers).
        self._member_ticker = member_ticker
        # SEC's ticker file titles companies "AMAZON COM INC"; the snapshot
        # knows them as "Amazon.com, Inc.". Keyed by 10-digit CIK.
        self._display_names: Mapping[str, str] = display_names or {}
        # The snapshot's listing for a company with several (GOOG of GOOGL and
        # GOOG), so a table row and the ranking name it alike. Keyed by CIK.
        self._listed_tickers: Mapping[str, str] = listed_tickers or {}
        self._tickers: dict[str, Any] | None = None
        # A document that failed once this turn fails again without asking SEC:
        # a ranking's metrics and periods would otherwise ask six times each.
        self._failures: dict[str, BaseException] = {}
        self._resolved_by_query: dict[str, Company] = {}
        self._submissions_by_cik: dict[str, dict[str, Any]] = {}
        self._documents_by_cik: dict[str, dict[str, str]] = {}
        self._company_facts_by_cik: dict[str, dict[str, Any] | None] = {}
        # A window asks for each quarter of the same metric: its records are read
        # from the facts once a turn, not once a quarter.
        self._records_by_metric: dict[
            tuple[str, Metric, str], tuple[list[FactRecord], list[dict[str, Any]]]
        ] = {}
        self._facts_filings_by_cik: dict[str, Sequence[Filing]] = {}
        self._fiscal_labels_by_cik: dict[str, dict[str, FiscalLabel]] = {}
        self._predecessor_ciks: dict[str, str | None] = {}
        if client is not None:
            self._client: SECDataSource = client
            self._owns_client = False
            return
        if settings is None:
            raise TypeError("settings are required when no SEC data source is provided")
        self._client = SECClient(settings)
        self._owns_client = True

    def display_name(self, cik: str, fallback: str) -> str:
        """The snapshot's name for a company, or ``fallback`` (SEC's title)."""
        return self._display_names.get(cik, fallback)

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def _remembering_failure[T](self, key: str, fetch: Callable[[], T]) -> T:
        failed = self._failures.get(key)
        if failed is not None:
            raise failed
        try:
            return fetch()
        except SOURCE_FAILURES as exc:
            self._failures[key] = exc
            raise

    def _cached_company_tickers(self) -> dict[str, Any]:
        if self._tickers is None:
            self._tickers = self._remembering_failure("tickers", self._client.get_company_tickers)
        return self._tickers

    def _resolve(self, company: str) -> Company:
        # Resolution scans the whole ticker map; a turn repeats the same query per
        # metric, period, and formula component.
        resolved = self._resolved_by_query.get(company)
        if resolved is None:
            asked = self._snapshot_ticker(company) or company
            resolved = resolve_company(asked, self._cached_company_tickers())
            self._resolved_by_query[company] = resolved
        return resolved

    def _snapshot_ticker(self, company: str) -> str | None:
        if self._member_ticker is None:
            return None
        try:
            return self._member_ticker(company)
        except (CompanyNotFoundError, AmbiguousCompanyError):
            # Not a snapshot member (a filer it leaves out): SEC's titles decide.
            return None

    def _cached_submissions(self, cik: str) -> dict[str, Any]:
        payload = self._submissions_by_cik.get(cik)
        if payload is None:
            payload = trim_submissions(
                self._remembering_failure(
                    # The first page only: older 10-Qs and 10-Ks come from company
                    # facts (``_with_facts_filings``), which a lookup reads anyway.
                    # A bank's older pages hold years of prospectuses and cost a
                    # request each.
                    f"submissions:{cik}",
                    lambda: self._client.get_submissions(cik, with_history=False),
                )
            )
            self._submissions_by_cik[cik] = payload
        return payload

    def _primary_document(self, cik: str, accession: str) -> str | None:
        """A filing's main document, from the filer's older submissions pages.

        Read only when a source link needs a filing the first page leaves out
        (``_cached_submissions``), once a turn per filer. A page that fails ends
        the reading, and the link is the filing's index page.
        """
        documents = self._documents_by_cik.get(cik)
        if documents is None:
            try:
                history = parse_submissions(trim_submissions(self._client.get_submissions(cik)))
            except (ProviderError, SessionQuotaError):
                history = []
            documents = {
                filing.accession_number: filing.primary_document
                for filing in history
                if filing.primary_document
            }
            self._documents_by_cik[cik] = documents
        return documents.get(accession)

    def _filings(self, cik: str) -> list[Filing]:
        """The issuer's filings, with its predecessor's when it is a new registrant.

        A holding-company reorganisation (ExxonMobil in 2026) gives the listed
        company a new CIK whose history starts at the reorganisation. Its first
        reports are filed jointly with the old registrant, so the old CIK is found
        from them, and its filings supply the quarters before.
        """
        filings = self._with_facts_filings(cik, parse_submissions(self._cached_submissions(cik)))
        if cik not in self._predecessor_ciks:
            self._predecessor_ciks[cik] = self._find_predecessor(cik, filings)
        predecessor = self._predecessor_ciks[cik]
        if predecessor is None:
            return filings
        known = {filing.accession_number for filing in filings}
        older = [
            filing
            for filing in parse_submissions(self._cached_submissions(predecessor))
            if filing.accession_number not in known
        ]
        return sorted([*filings, *older], key=lambda filing: filing.filed_date, reverse=True)

    def _with_facts_filings(self, cik: str, filings: list[Filing]) -> list[Filing]:
        """``filings`` plus the 10-Qs and 10-Ks company facts names, for a short history.

        SEC's submissions list the last year or 1,000 filings; a bank filing
        thousands of prospectuses a year shows a year of reports there. Company
        facts carries every periodic report's accession, form, filing date and
        period, so the quarters before are found without paging through years
        of prospectuses.
        """
        if _periodic_history_days(filings) >= _FULL_HISTORY_DAYS:
            return filings
        try:
            self._cached_company_facts(cik)
        except ProviderError:
            return filings
        known = {filing.accession_number for filing in filings}
        extra = [
            filing
            for filing in self._facts_filings_by_cik.get(cik, [])
            if filing.accession_number not in known
        ]
        if not extra:
            return filings
        return sorted([*filings, *extra], key=lambda filing: filing.filed_date, reverse=True)

    def _with_predecessor_facts(
        self, records: list[FactRecord], predecessor: str, metric: Metric, unit: str
    ) -> tuple[list[FactRecord], dict[str, str]]:
        """``records`` plus the predecessor's, so a quarter can span the reorganisation."""
        try:
            payload = self._cached_company_facts(predecessor)
        except ProviderError as exc:
            if exc.details.get("status_code") != 404:
                raise
            return records, {}
        older, _rejections = self._metric_records(predecessor, payload, metric, unit)
        seen = {(record.accession_number, record.start_date, record.end_date) for record in records}
        extra = [
            record
            for record in older
            if (record.accession_number, record.start_date, record.end_date) not in seen
        ]
        own = {record.accession_number for record in records}
        folders = {
            record.accession_number: predecessor
            for record in extra
            if record.accession_number not in own
        }
        return [*records, *extra], folders

    def _find_predecessor(self, cik: str, filings: list[Filing]) -> str | None:
        periodic = [filing for filing in filings if filing.form in PERIODIC_FORMS]
        if len(periodic) >= _THIN_HISTORY:
            return None
        for filing in periodic:
            other = parse_cik(filing.accession_number.split("-", 1)[0])
            if other is None or other == cik:
                continue
            try:
                theirs = parse_submissions(self._cached_submissions(other))
            except ProviderError:
                continue
            # A filing agent's own submissions do not list its client's report;
            # a joint registrant's do.
            if any(item.accession_number == filing.accession_number for item in theirs):
                return other
        return None

    def _metric_records(
        self, cik: str, payload: dict[str, Any], metric: Metric, unit: str
    ) -> tuple[list[FactRecord], list[dict[str, Any]]]:
        """``parse_company_facts`` for the company's facts, once a turn per metric."""
        key = (cik, metric, unit)
        parsed = self._records_by_metric.get(key)
        if parsed is None:
            parsed = parse_company_facts(payload, metric, unit)
            self._records_by_metric[key] = parsed
        # Callers extend the lists; the cached ones stay as parsed.
        return list(parsed[0]), list(parsed[1])

    def _cached_company_facts(self, cik: str) -> dict[str, Any]:
        if cik in self._company_facts_by_cik:
            payload = self._company_facts_by_cik[cik]
            if payload is None:
                raise ProviderError(
                    "No SEC companyfacts response exists for the issuer",
                    details={"cik": cik, "status_code": 404},
                )
            return payload
        try:
            payload = self._remembering_failure(f"facts:{cik}", lambda: self._parsed_facts(cik))
        except ProviderError as exc:
            if exc.details.get("status_code") == 404:
                self._company_facts_by_cik[cik] = None
            raise
        self._company_facts_by_cik[cik] = payload
        return payload

    def _parsed_facts(self, cik: str) -> dict[str, Any]:
        prefetch = getattr(self._client, "prefetch_company_facts", None)
        if callable(prefetch):
            prefetch(cik)
        # A cached file's stamp, where the source keeps one: an unchanged file is not
        # parsed again (_PARSED_FACTS). The recording has none, so it parses each turn.
        stamp_of = getattr(self._client, "company_facts_stamp", None)
        stamp = stamp_of(cik) if callable(stamp_of) else None
        parsed = _PARSED_FACTS.get(stamp) if stamp is not None else None
        if parsed is None:
            with _FACTS_PARSE_SLOTS:
                payload = self._client.get_company_facts(cik)
                # The summaries read every concept; the rest of the turn reads only the catalog's.
                parsed = _ParsedFacts(
                    concepts=_read_concepts_only(payload),
                    labels=fiscal_labels(payload),
                    filings=tuple(filings_from_company_facts(payload)),
                )
            if stamp is not None:
                _PARSED_FACTS.put(stamp, parsed)
        self._fiscal_labels_by_cik.setdefault(cik, parsed.labels)
        self._facts_filings_by_cik[cik] = parsed.filings
        return parsed.concepts

    def get_financials(
        self,
        company: str,
        metric: str,
        *,
        report_date: date | None = None,
    ) -> FinancialFact:
        parsed_metric = parse_metric(metric)
        unit = metric_unit(parsed_metric)
        resolved = self._resolve(company)
        # Lookup applies the ranking's membership rule (ADR 0002).
        require_operating(resolved.cik, resolved.name, self._listed_tickers)
        listed = self._listed_tickers.get(resolved.cik)
        ticker = (
            listed
            if listed in resolved.tickers
            else resolved.tickers[0]
            if resolved.tickers
            else company.upper()
        )
        filings = self._filings(resolved.cik)
        # "Latest" is the newest period any 10-Q or 10-K covers (ADR 0007).
        target = report_date if report_date is not None else latest_period_end(filings)
        last_unsupported: UnsupportedQuarterlyFactError | FilingNotFoundError | None = None
        last_missing: ProviderError | None = None
        unreadable = False
        related = _related_lookup_ciks(resolved.cik, self._predecessor_ciks.get(resolved.cik))
        for cik in related:
            try:
                company_facts_payload = self._cached_company_facts(cik)
            except ProviderError as exc:
                if exc.details.get("status_code") != 404:
                    raise
                last_missing = exc
                continue
            records, rejections = self._metric_records(
                cik, company_facts_payload, parsed_metric, unit
            )
            unreadable = unreadable or (not records and bool(rejections))
            folders: dict[str, str] = {}
            predecessor = self._predecessor_ciks.get(resolved.cik)
            if cik == resolved.cik and predecessor is not None:
                records, folders = self._with_predecessor_facts(
                    records, predecessor, parsed_metric, unit
                )
            sources = FilingSources(folders, self._primary_document)
            name = self._display_names.get(resolved.cik, resolved.name)
            targets: list[date | None] = [target]
            if report_date is None:
                targets = list(list_quarterly_report_dates(filings, limit=_LATEST_FALLBACK))
            for period in targets:
                try:
                    fact = self._select_with_fallbacks(
                        company_facts_payload,
                        records,
                        filings,
                        parsed_metric,
                        FactOwner(company_name=name, ticker=ticker, cik=cik, currency=unit),
                        report_date=period,
                        sources=sources,
                    )
                except (UnsupportedQuarterlyFactError, FilingNotFoundError) as exc:
                    last_unsupported = exc
                    if (
                        report_date is not None
                        and period is not None
                        and not self._period_in_xbrl(cik, filings, period)
                        and any(
                            abs(filing.report_date - period) <= FISCAL_WEEK_TOLERANCE
                            for filing in filings
                        )
                    ):
                        # Filed, but SEC's company facts have not caught up with it.
                        last_unsupported = UnsupportedQuarterlyFactError(
                            PENDING_IN_XBRL_MESSAGE,
                            details={
                                "metric": parsed_metric.value,
                                "reason": "pending_structured_data",
                            },
                        )
                    if period is None or report_date is not None:
                        break
                    if self._period_in_xbrl(cik, filings, period):
                        break
                    # SEC has not yet added the newest filing to companyfacts;
                    # "latest" is then the newest quarter it has.
                    continue
                if period is not None and period != targets[0]:
                    fact = fact.model_copy(update={"newer_filing_end": targets[0]})
                return fact
        if unreadable:
            raise DataIntegrityError(
                UNREADABLE_FACTS_MESSAGE, details={"metric": parsed_metric.value}
            ) from last_unsupported
        if isinstance(last_unsupported, FilingNotFoundError):
            raise UnsupportedQuarterlyFactError(
                str(last_unsupported),
                details=last_unsupported.details,
            ) from last_unsupported
        if last_unsupported is not None:
            raise last_unsupported
        if last_missing is not None:
            raise UnsupportedQuarterlyFactError(
                "No SEC companyfacts response exists for the issuer",
                details={"metric": parsed_metric.value},
            ) from last_missing
        raise UnsupportedQuarterlyFactError(
            "No directly reported standalone-quarter fact exists for metric",
            details={
                "metric": parsed_metric.value,
                "reason": "no_standalone_quarter",
            },
        )

    def _select_with_fallbacks(
        self,
        payload: dict[str, Any],
        records: list[FactRecord],
        filings: list[Filing],
        metric: Metric,
        owner: FactOwner,
        *,
        report_date: date | None,
        sources: FilingSources | None = None,
    ) -> FinancialFact:

        def select(kept: list[FactRecord], chosen: Metric) -> FinancialFact:
            return _select_or_derive(
                kept,
                filings,
                chosen,
                owner,
                report_date=report_date,
                sources=sources,
            )

        if metric is Metric.REVENUE:
            fact = _total_revenue(records, payload, owner.currency, select)
            fact = _bank_revenue(fact, payload, owner.currency, select)
            return self._plausible_revenue(fact, payload, filings, owner, sources=sources)
        try:
            fact = select(records, metric)
            if metric is Metric.DIVIDENDS_PER_SHARE:
                _refuse_dividend_declared_earlier(fact, records)
            return _with_diluted_shares(fact, payload) if metric in PER_SHARE_METRICS else fact
        except UnsupportedQuarterlyFactError:
            if metric is Metric.DEPRECIATION_AMORTIZATION:
                return self._depreciation_plus_amortization(
                    payload,
                    filings,
                    owner,
                    report_date=report_date,
                    sources=sources,
                )
            if metric is not Metric.GROSS_PROFIT:
                raise
            # Retailers (Costco, Walmart) tag no gross profit line; revenue
            # minus cost of revenue is the same amount (ADR 0007).
            revenue_records, _ = parse_company_facts(payload, Metric.REVENUE, owner.currency)
            revenue = _sales_revenue(
                _total_revenue(revenue_records, payload, owner.currency, select),
                revenue_records,
                select,
            )
            cost_records, _ = parse_company_facts(payload, Metric.COST_OF_REVENUE, owner.currency)
            cost = select(cost_records, Metric.COST_OF_REVENUE)
            if (revenue.start_date, revenue.end_date) != (cost.start_date, cost.end_date):
                raise
            if _reports_excluding_costs(payload, revenue.end_date):
                raise
            return gross_profit_from_components(revenue, cost)

    def _plausible_revenue(
        self,
        revenue: FinancialFact,
        payload: dict[str, Any],
        filings: list[Filing],
        owner: FactOwner,
        *,
        sources: FilingSources | None,
    ) -> FinancialFact:
        """Revenue, unless the filing's own gross profit or cost of revenue exceeds it.

        Plexus tagged a quarter's revenue as $1,304,778, its thousands without
        their scale, beside $131 million of gross profit. Revenue is then gross
        profit plus cost of revenue, both as filed, when the two cover the
        quarter; otherwise the mis-scaled figure is refused, never shown.
        """
        parts: list[FinancialFact] = []
        for component in (Metric.GROSS_PROFIT, Metric.COST_OF_REVENUE):
            component_records, _ = parse_company_facts(payload, component, owner.currency)
            try:
                parts.append(
                    _select_or_derive(
                        component_records,
                        filings,
                        component,
                        owner,
                        report_date=revenue.end_date,
                        sources=sources,
                    )
                )
            except (UnsupportedQuarterlyFactError, FilingNotFoundError):
                continue
        period = (revenue.start_date, revenue.end_date)
        same = {part.metric: part for part in parts if (part.start_date, part.end_date) == period}
        gross, cost = same.get(Metric.GROSS_PROFIT), same.get(Metric.COST_OF_REVENUE)
        if gross is not None and cost is not None:
            total = gross.value + cost.value
            # Cost above revenue is a negative gross margin, not an error, when
            # the three agree; only a revenue the parts do not add up to is.
            agrees = abs(total - revenue.value) <= abs(total) / 100
            if agrees or revenue.value >= max(gross.value, cost.value):
                return revenue
            return revenue_from_components(revenue, gross, cost)
        if gross is None or not gross.value > revenue.value > 0:
            return revenue
        raise UnsupportedQuarterlyFactError(
            "The filing's revenue is smaller than its own gross profit or cost of "
            "revenue, so the filed figure is mis-scaled",
            details={"metric": Metric.REVENUE.value, "concept": revenue.concept},
        )

    def _depreciation_plus_amortization(
        self,
        payload: dict[str, Any],
        filings: list[Filing],
        owner: FactOwner,
        *,
        report_date: date | None,
        sources: FilingSources | None,
    ) -> FinancialFact:
        """D&A as depreciation plus amortization of intangibles (Microsoft, Alphabet).

        Both must cover the same period; depreciation alone would understate it.
        """
        parts = []
        for component in (Metric.DEPRECIATION, Metric.AMORTIZATION_OF_INTANGIBLES):
            component_records, _ = parse_company_facts(payload, component, owner.currency)
            parts.append(
                _select_or_derive(
                    component_records,
                    filings,
                    component,
                    owner,
                    report_date=report_date,
                    sources=sources,
                )
            )
        return sum_of_components(Metric.DEPRECIATION_AMORTIZATION, parts)

    def _fiscal_labels(self, cik: str) -> dict[str, FiscalLabel]:
        if cik not in self._fiscal_labels_by_cik:
            # Reading the facts records their labels before trimming them.
            self._cached_company_facts(cik)
        return self._fiscal_labels_by_cik.get(cik, {})

    def _period_in_xbrl(self, cik: str, filings: list[Filing], period: date) -> bool:
        labels = self._fiscal_labels(cik)
        return any(
            filing.accession_number in labels
            for filing in filings
            if abs(filing.report_date - period) <= FISCAL_WEEK_TOLERANCE
        )

    def fiscal_periods(self, company: str) -> tuple[FiscalPeriod, ...]:
        """Every 10-Q and 10-K period end with the fiscal year and quarter it declares.

        Newest first. A 10-K's period is the fiscal fourth quarter.
        """
        resolved = self._resolve(company)
        filings = self._filings(resolved.cik)
        labels: dict[str, FiscalLabel] = {}
        predecessor = self._predecessor_ciks.get(resolved.cik)
        for cik in (predecessor, resolved.cik):
            if cik is None:
                continue
            try:
                labels.update(self._fiscal_labels(cik))
            except ProviderError as exc:
                if exc.details.get("status_code") != 404:
                    raise
        return periods_from_filings(filings, labels)

    def files_quarterly(self, company: str) -> tuple[bool, str]:
        """(Whether the company files 10-Qs, its name). False for 20-F/40-F filers."""
        resolved = self._resolve(company)
        name = self._display_names.get(resolved.cik, resolved.name)
        return files_quarterly_reports(self._cached_submissions(resolved.cik)), name

    def list_quarterly_report_dates(self, company: str, *, limit: int) -> tuple[date, ...]:
        """Newest-first distinct quarterly report dates for a company."""
        resolved = self._resolve(company)
        return tuple(list_quarterly_report_dates(self._filings(resolved.cik), limit=limit))


def _read_concepts_only(payload: dict[str, Any]) -> dict[str, Any]:
    """Company facts with only the concepts a metric reads; other keys kept as they are."""
    facts = payload.get("facts")
    if not isinstance(facts, dict):
        return payload
    kept = {
        taxonomy: {
            name: body for name, body in concepts.items() if (taxonomy, name) in _READ_CONCEPTS
        }
        if isinstance(concepts, dict)
        else concepts
        for taxonomy, concepts in facts.items()
    }
    return {**payload, "facts": kept}


def _reports_excluding_costs(payload: dict[str, Any], end: date) -> bool:
    """Whether the company reports costs that "cost of revenue" leaves out, for ``end``."""
    facts = payload.get("facts", {})
    for taxonomy, concept in GROSS_PROFIT_EXCLUDING_CONCEPTS:
        body = facts.get(taxonomy, {}).get(concept)
        if body is None:
            continue
        for records in body.get("units", {}).values():
            if any(record.get("end") == end.isoformat() for record in records):
                return True
    return False


_CONTRACT_REVENUE = "RevenueFromContractWithCustomerExcludingAssessedTax"
# The most of total revenue that membership and other income may be (Walmart's is 1%).
_OTHER_INCOME_SHARE = Decimal("0.05")
_COST_CONCEPTS = tuple(concept for _, concept in METRIC_CONCEPTS[Metric.COST_OF_REVENUE])
# Cost of revenue this many times revenue means the revenue line is a part of it.
_COST_MULTIPLE = 5


def _anchor(fact: FinancialFact) -> tuple[str, date | None, date]:
    """The filing and period a quarter was read from: a derived one's longer amount."""
    if fact.derivation is not None and fact.derivation.parts:
        part = fact.derivation.parts[0]
        if part.accession_number == fact.accession_number:
            return part.accession_number, part.start_date, part.end_date
    return fact.accession_number, fact.start_date, fact.end_date


def _reported(
    records: list[FactRecord], anchor: tuple[str, date | None, date]
) -> dict[str, Decimal]:
    """Each concept's value in the anchor's filing and period."""
    accession, start, end = anchor
    return {
        record.concept: record.value
        for record in records
        if record.accession_number == accession
        and record.start_date == start
        and record.end_date == end
    }


def _revenue_checks(
    payload: dict[str, Any], unit: str, anchor: tuple[str, date | None, date]
) -> tuple[list[Decimal], dict[str, Decimal]]:
    """Totals the filing's other lines add up to, and those lines, for the anchor period.

    Costs and expenses plus operating income is revenue; so is operating
    expenses plus operating income, with or without cost of revenue (Kopin's
    operating expenses hold its cost of sales), and gross profit plus cost of revenue.
    """
    concepts = [
        *REVENUE_CHECK_CONCEPTS,
        *METRIC_CONCEPTS[Metric.OPERATING_EXPENSES],
        *METRIC_CONCEPTS[Metric.OPERATING_INCOME],
        *METRIC_CONCEPTS[Metric.COST_OF_REVENUE],
        *METRIC_CONCEPTS[Metric.GROSS_PROFIT],
    ]
    records, _ = parse_company_facts_for_concepts(payload, concepts, unit)
    lines = _reported(records, anchor)
    income = lines.get("OperatingIncomeLoss")
    costs = [lines[name] for name in _COST_CONCEPTS if name in lines]
    totals: list[Decimal] = []
    if income is not None:
        for name in ("CostsAndExpenses", "OperatingExpenses"):
            if name in lines:
                totals.append(lines[name] + income)
        if "OperatingExpenses" in lines:
            totals.extend(lines["OperatingExpenses"] + cost + income for cost in costs)
    if "GrossProfit" in lines:
        totals.extend(lines["GrossProfit"] + cost for cost in costs)
    return totals, lines


def _agrees(value: Decimal, totals: list[Decimal]) -> bool:
    return any(abs(total - value) <= abs(total) / 100 for total in totals)


def _implausible(value: Decimal, lines: dict[str, Decimal]) -> bool:
    """Operating income above revenue, or cost of revenue many times it."""
    if value <= 0:
        return False
    income = lines.get("OperatingIncomeLoss")
    costs = [lines[name] for name in _COST_CONCEPTS if name in lines]
    return (income is not None and income > value) or any(
        cost >= value * _COST_MULTIPLE for cost in costs
    )


def _total_revenue(
    records: list[FactRecord],
    payload: dict[str, Any],
    unit: str,
    select: Callable[[list[FactRecord], Metric], FinancialFact],
) -> FinancialFact:
    """Revenue from the concept that is the filing's total, not one of its lines.

    The catalog prefers ``Revenues``, but Verra Mobility tags one segment's
    $25.8 million with it beside $263.6 million of contract revenue. When the
    filing's revenue concepts disagree, the one its costs plus operating income
    add up to is the total; without those lines, a revenue below operating
    income or far below cost of revenue is a part. California Resources'
    smaller ``Revenues`` nets a derivative loss and does add up, so it stays.
    """
    fact = select(records, Metric.REVENUE)
    anchor = _anchor(fact)
    reported = _reported(
        [record for record in records if record.taxonomy == fact.taxonomy], anchor
    )
    others = {
        concept: value
        for concept, value in reported.items()
        if concept != fact.concept and value != fact.value
    }
    if not others:
        return fact
    totals, lines = _revenue_checks(payload, unit, anchor)
    if _agrees(fact.value, totals):
        return fact
    agreeing = {concept for concept, value in reported.items() if _agrees(value, totals)}
    if agreeing:
        wrong = set(reported) - agreeing
    elif _implausible(fact.value, lines):
        wrong = {concept for concept, value in reported.items() if _implausible(value, lines)}
    else:
        return fact
    if not set(others) - wrong:
        return fact
    try:
        total = select(
            [record for record in records if record.concept not in wrong], Metric.REVENUE
        )
    except (UnsupportedQuarterlyFactError, FilingNotFoundError):
        return fact
    return total if total.end_date == fact.end_date else fact


def _bank_revenue(
    revenue: FinancialFact,
    payload: dict[str, Any],
    unit: str,
    select: Callable[[list[FactRecord], Metric], FinancialFact],
) -> FinancialFact:
    """A bank's revenue as net interest income plus noninterest income.

    M&T and Huntington tag no total revenue; their contract revenue is fee
    income alone, a part of noninterest income, so net margins read over 100%.
    """
    if revenue.concept != _CONTRACT_REVENUE:
        return revenue
    parts: list[FinancialFact] = []
    for component in (Metric.NET_INTEREST_INCOME, Metric.NONINTEREST_INCOME):
        component_records, _ = parse_company_facts(payload, component, unit)
        try:
            parts.append(select(component_records, component))
        except (UnsupportedQuarterlyFactError, FilingNotFoundError):
            return revenue
    interest, noninterest = parts
    period = (revenue.start_date, revenue.end_date)
    if any((part.start_date, part.end_date) != period for part in parts):
        return revenue
    # Fees are a part of noninterest income; a company's net interest expense is not a bank's.
    if interest.value <= 0 or noninterest.value < revenue.value:
        return revenue
    return sum_of_components(Metric.REVENUE, parts, label=BANK_REVENUE_LABEL, name_parts=True)


def _sales_revenue(
    revenue: FinancialFact,
    records: list[FactRecord],
    select: Callable[[list[FactRecord], Metric], FinancialFact],
) -> FinancialFact:
    """Sales for a gross profit: contract revenue, when the total adds other income.

    Walmart's ``Revenues`` adds membership and other income to net sales, and
    cost of sales is the cost of net sales alone. Such income is a sliver of
    the total; a wider gap is rent or interest (Welltower, WEX) whose costs
    may sit in cost of revenue, so the total stays.
    """
    if revenue.concept != "Revenues":
        return revenue
    anchor = _anchor(revenue)
    reported = _reported(records, anchor)
    sales, total = reported.get(_CONTRACT_REVENUE), reported.get("Revenues")
    if sales is None or total is None or not 0 < total - sales <= total * _OTHER_INCOME_SHARE:
        return revenue
    try:
        fact = select(
            [record for record in records if record.concept == _CONTRACT_REVENUE], Metric.REVENUE
        )
    except (UnsupportedQuarterlyFactError, FilingNotFoundError):
        return revenue
    same = (fact.start_date, fact.end_date) == (revenue.start_date, revenue.end_date)
    return fact if same else revenue


DIVIDEND_DECLARED_EARLIER_MESSAGE = (
    "No dividend was declared in this quarter; one was declared earlier in the fiscal year"
)


def _refuse_dividend_declared_earlier(fact: FinancialFact, records: list[FactRecord]) -> None:
    """Refuse a declared dividend of zero when the year to date declared one.

    Walmart declares the year's dividend in its first quarter; the next 10-Q
    reports $0.00 declared for its quarter beside $0.99 for the six months. A
    company that suspends its dividend reports the same, so the refusal says
    only what the filing does: none this quarter, one earlier in the year.
    """
    if fact.value != 0 or fact.concept != "CommonStockDividendsPerShareDeclared":
        return
    if any(
        record.accession_number == fact.accession_number
        and record.concept == fact.concept
        and record.start_date is not None
        and record.start_date < fact.start_date
        and record.end_date == fact.end_date
        and record.value > 0
        for record in records
    ):
        raise NoDividendThisQuarterError(
            DIVIDEND_DECLARED_EARLIER_MESSAGE,
            details={"metric": fact.metric.value, "report_date": fact.end_date.isoformat()},
        )


def _with_diluted_shares(fact: FinancialFact, payload: dict[str, Any]) -> FinancialFact:
    """A per-share figure with the weighted diluted shares its filing reports beside it."""
    records, _ = parse_company_facts_for_concepts(payload, [SHARE_COUNT_CONCEPT], "shares")
    shares = _reported(records, (fact.accession_number, fact.start_date, fact.end_date))
    count = shares.get(SHARE_COUNT_CONCEPT[1])
    return fact if count is None else fact.model_copy(update={"diluted_shares": count})


def _periodic_history_days(filings: list[Filing]) -> int:
    ends = [filing.report_date for filing in filings if filing.form in PERIODIC_FORMS]
    return (max(ends) - min(ends)).days if ends else 0


def filings_from_company_facts(payload: dict[str, Any]) -> list[Filing]:
    """The 10-Qs and 10-Ks company facts cites: accession, form, filing date and period.

    A report's period is the latest end date that many of its financial facts
    share: a 10-K can carry as many prior-year comparatives as current facts,
    and a few subsequent-event facts are dated after the period. Cover-page
    (dei) facts such as shares outstanding are dated later and are left out.
    Its primary document is not in company facts, so its source link is the
    filing's index page.
    """
    seen: dict[str, tuple[str, date, Counter[date]]] = {}
    facts = payload.get("facts")
    if not isinstance(facts, dict):
        return []
    for taxonomy, concepts in facts.items():
        if taxonomy == "dei" or not isinstance(concepts, dict):
            continue
        for concept in concepts.values():
            units = concept.get("units") if isinstance(concept, dict) else None
            if not isinstance(units, dict):
                continue
            for entries in units.values():
                for entry in entries if isinstance(entries, list) else []:
                    _note_filing(seen, entry)
    return [
        Filing(
            form=form,
            accession_number=accession,
            filed_date=filed,
            report_date=_report_period(ends),
        )
        for accession, (form, filed, ends) in seen.items()
    ]


def _report_period(ends: Counter[date]) -> date:
    """The latest end date with at least half as many facts as the commonest one."""
    most = max(ends.values())
    return max(end for end, count in ends.items() if count * 2 >= most)


def _note_filing(seen: dict[str, tuple[str, date, Counter[date]]], entry: Any) -> None:
    if not isinstance(entry, dict) or entry.get("form") not in ("10-Q", "10-K"):
        return
    accession, filed, end = entry.get("accn"), entry.get("filed"), entry.get("end")
    if not (isinstance(accession, str) and isinstance(filed, str) and isinstance(end, str)):
        return
    try:
        filed_date, end_date = date.fromisoformat(filed), date.fromisoformat(end)
    except ValueError:
        return
    if accession not in seen:
        seen[accession] = (str(entry["form"]), filed_date, Counter())
    seen[accession][2][end_date] += 1
