"""Pure deterministic quarterly fact selection from normalized XBRL records."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from financial_analyst_agent.domain.enums import (
    ANNUAL_FORMS,
    QUARTERLY_FORMS,
    DataSourceKind,
    FormType,
    Metric,
)
from financial_analyst_agent.domain.errors import (
    AmbiguousFactError,
    PerShareNotDerivableError,
    UnsupportedQuarterlyFactError,
)
from financial_analyst_agent.domain.models import (
    Derivation,
    DerivationPart,
    FactRecord,
    Filing,
    FinancialFact,
)
from financial_analyst_agent.services.filing_selector import get_candidate_filings
from financial_analyst_agent.services.fiscal_periods import one_year_earlier
from financial_analyst_agent.services.metric_catalog import (
    PER_SHARE_METRICS,
    get_concept_candidates,
)


@dataclass(frozen=True)
class FactOwner:
    """The company a selected fact is reported by, and the unit it is read in."""

    company_name: str
    ticker: str
    cik: str
    currency: str = "USD"


_MIN_QUARTER_DAYS = 70
# Longer than this, a duration fact is not one quarter.
MAX_QUARTER_DAYS = 110


def _duration_days(start: date, end: date) -> int:
    return (end - start).days


def _is_quarterly_form(form: str, selected_form: str) -> bool:
    if form not in QUARTERLY_FORMS:
        return False
    return form == selected_form


def is_standalone_quarter(start_date: date | None, end_date: date) -> bool:
    """Whether a duration fact covers one quarter: 70 to 110 days, inclusive."""
    if start_date is None:
        return False
    days = _duration_days(start_date, end_date)
    return _MIN_QUARTER_DAYS <= days <= MAX_QUARTER_DAYS


def _filter_quarterly_candidates(
    facts: list[FactRecord],
    filing: Filing,
    taxonomy: str,
    concept: str,
    currency: str,
) -> list[FactRecord]:
    """Apply all mandatory filters; reject YTD, comparative, and instant facts."""
    candidates: list[FactRecord] = []
    for fact in facts:
        if fact.taxonomy != taxonomy or fact.concept != concept:
            continue
        if fact.accession_number != filing.accession_number:
            continue
        if fact.end_date != filing.report_date:
            continue
        if not _is_quarterly_form(fact.form, filing.form):
            continue
        if fact.unit.upper() != currency.upper():
            continue
        if not is_standalone_quarter(fact.start_date, fact.end_date):
            continue
        candidates.append(fact)
    return candidates


def _resolve_same_concept_candidates(candidates: list[FactRecord]) -> FactRecord:
    """Apply same-concept precedence; error if multiple remain at same filed_date."""
    if len(candidates) == 1:
        return candidates[0]

    by_filed = sorted(candidates, key=lambda fact: fact.filed_date, reverse=True)
    best_filed = by_filed[0].filed_date
    top = [fact for fact in by_filed if fact.filed_date == best_filed]
    if len(top) == 1:
        return top[0]
    if len({(fact.start_date, fact.end_date, fact.value) for fact in top}) == 1:
        # companyfacts lists one reported number again under another frame or
        # form; identical copies agree, so they are not ambiguous.
        return top[0]

    raise AmbiguousFactError(
        "Multiple directly reported quarterly facts remain after precedence rules",
        details={
            "candidates": [
                {
                    "accession_number": fact.accession_number,
                    "concept": fact.concept,
                    "start_date": fact.start_date.isoformat() if fact.start_date else None,
                    "end_date": fact.end_date.isoformat(),
                    "filed_date": fact.filed_date.isoformat(),
                    "value": str(fact.value),
                }
                for fact in top
            ],
        },
    )


def _fact(
    anchor: FactRecord,
    metric: Metric,
    owner: FactOwner,
    source_url: str,
    *,
    value: Decimal,
    start_date: date,
    directly_reported: bool,
    derivation: Derivation | None = None,
    year_earlier: DerivationPart | None = None,
) -> FinancialFact:
    """``owner``'s ``metric``, with ``anchor``'s filing, period end and concept as its provenance.

    A reported fact is its own anchor; a derived one is anchored on the record
    whose filing reports the longer period it was computed from.
    """
    return FinancialFact(
        company_name=owner.company_name,
        ticker=owner.ticker,
        cik=owner.cik,
        metric=metric,
        value=value,
        currency=owner.currency.upper(),
        start_date=start_date,
        end_date=anchor.end_date,
        form=anchor.form,
        filed_date=anchor.filed_date,
        accession_number=anchor.accession_number,
        taxonomy=anchor.taxonomy,
        concept=anchor.concept,
        source_url=source_url,
        directly_reported=directly_reported,
        derivation=derivation,
        source=DataSourceKind.SEC_XBRL,
        year_earlier=year_earlier,
    )


def _build_financial_fact(
    selected: FactRecord,
    metric: Metric,
    owner: FactOwner,
    source_url: str,
    *,
    year_earlier: DerivationPart | None = None,
) -> FinancialFact:
    if selected.start_date is None:
        raise UnsupportedQuarterlyFactError(
            "Selected fact missing start_date for quarterly duration",
            details={"concept": selected.concept},
        )
    return _fact(
        selected,
        metric,
        owner,
        source_url,
        value=selected.value,
        start_date=selected.start_date,
        directly_reported=True,
        year_earlier=year_earlier,
    )


def select_quarterly_fact(
    facts: list[FactRecord],
    filing: Filing,
    metric: Metric,
    owner: FactOwner,
    source_url: str,
) -> tuple[FinancialFact, ...]:
    """
    Select a directly reported standalone-quarter fact for a single filing.

    Tries catalog concepts in order and returns the first with a standalone
    quarter. Same-concept duplicates still raise AmbiguousFactError. A later
    concept is only a fallback when earlier ones have no quarterly candidate.
    Never derives values by subtraction.
    """
    concept_candidates = get_concept_candidates(metric)
    for taxonomy, concept in concept_candidates:
        concept_facts = [
            fact for fact in facts if fact.taxonomy == taxonomy and fact.concept == concept
        ]
        if not concept_facts:
            continue

        candidates = _filter_quarterly_candidates(
            concept_facts, filing, taxonomy, concept, owner.currency
        )
        if not candidates:
            continue

        selected = _resolve_same_concept_candidates(candidates)
        return (
            _build_financial_fact(
                selected,
                metric,
                owner,
                source_url,
                year_earlier=comparative(concept_facts, selected, source_url),
            ),
        )

    raise UnsupportedQuarterlyFactError(
        "No directly reported standalone-quarter fact exists for metric",
        details={
            "metric": metric.value,
            "filing_accession": filing.accession_number,
            "report_date": filing.report_date.isoformat(),
            "reason": "no_standalone_quarter",
        },
    )


def select_quarterly_fact_with_filing_fallback(
    facts: list[FactRecord],
    filings: list[Filing],
    metric: Metric,
    owner: FactOwner,
    source_url_for_filing: Callable[[Filing], str],
    *,
    report_date: date | None = None,
) -> tuple[FinancialFact, ...]:
    """
    Select quarterly facts using amendment-first filing fallback.

    Tries each candidate filing for the chosen report_date (newest when omitted)
    in order without mixing facts across accessions. UnsupportedQuarterlyFactError
    from a filing triggers fallback; AmbiguousFactError is never concealed by
    fallback. A missing named report_date is a typed filing failure, not the
    nearest available period.
    """
    candidate_filings = get_candidate_filings(filings, report_date=report_date)

    last_unsupported: UnsupportedQuarterlyFactError | None = None
    for filing in candidate_filings:
        try:
            return select_quarterly_fact(
                facts,
                filing,
                metric,
                owner,
                source_url_for_filing(filing),
            )
        except UnsupportedQuarterlyFactError as exc:
            last_unsupported = exc

    if last_unsupported is not None:
        raise last_unsupported

    raise UnsupportedQuarterlyFactError(
        "No directly reported standalone-quarter fact exists for metric",
        details={"metric": metric.value, "reason": "no_standalone_quarter"},
    )


# --- Derived quarters (ADR 0007) -------------------------------------------------

_ANNUAL_DAYS = (350, 380)
_NINE_MONTH_DAYS = (250, 290)
_CUMULATIVE_MIN_DAYS = MAX_QUARTER_DAYS + 1
# The shorter cumulative amount ends one quarter before the longer one.
_ONE_QUARTER_EARLIER_DAYS = (60, 120)
FOURTH_QUARTER_LABEL = "Fiscal year (10-K) minus nine months (10-Q)"
YEAR_TO_DATE_LABEL = "Year to date minus the previous quarter's year to date (10-Qs)"


def _days_between(fact: FactRecord) -> int | None:
    if fact.start_date is None:
        return None
    return _duration_days(fact.start_date, fact.end_date)


def _within(days: int | None, bounds: tuple[int, int]) -> bool:
    return days is not None and bounds[0] <= days <= bounds[1]


def _part(fact: FactRecord, source_url: str) -> DerivationPart:
    assert fact.start_date is not None
    return DerivationPart(
        value=fact.value,
        start_date=fact.start_date,
        end_date=fact.end_date,
        form=fact.form,
        accession_number=fact.accession_number,
        taxonomy=fact.taxonomy,
        concept=fact.concept,
        filed_date=fact.filed_date,
        source_url=source_url,
    )


def comparative(
    concept_facts: list[FactRecord], current: FactRecord, source_url: str
) -> DerivationPart | None:
    """The same amount a year before ``current``, as ``current``'s own filing reports it.

    A filing restates its comparatives on its own basis: NVIDIA's 10-Q for the
    quarter after its ten-for-one split reports the year-earlier diluted EPS as
    $0.60, not the $5.98 first filed, and Bank of America's restated revenue
    differs from the figure its older 10-Q gave. A change over the year reads both
    amounts from one filing; None when the filing reports no such comparative.
    """
    target = one_year_earlier(current.end_date)
    length = _days_between(current)
    matches = [
        fact
        for fact in concept_facts
        if fact.accession_number == current.accession_number
        and fact.taxonomy == current.taxonomy
        and fact.concept == current.concept
        and fact.unit.upper() == current.unit.upper()
        and _near(fact.end_date, target)
        and (fact.start_date is None) == (length is None)
        and (length is None or abs((_days_between(fact) or 0) - length) <= _ONE_YEAR_TOLERANCE_DAYS)
    ]
    if not matches:
        return None
    try:
        before = _resolve_same_concept_candidates(matches)
    except AmbiguousFactError:
        return None
    if before.start_date is None:
        before = before.model_copy(update={"start_date": before.end_date})
    return _part(before, source_url)


def _one_quarter_shorter(concept_facts: list[FactRecord], longer: FactRecord) -> FactRecord | None:
    """The same-start cumulative amount ending one quarter before ``longer``, as then reported.

    A 10-K that reports the nine months itself is read first: it may have
    revised them (Rapid7's 10-K cut nine months of net income from $27.0 million
    to $23.4 million), and its year is on that same basis. Otherwise only a
    copy filed no later than ``longer`` counts: a 10-Q filed afterwards may
    restate the nine months (a spin-off recast), and subtracting a restated
    part from an as-reported total mixes two bases (3M's fourth quarter of 2023
    read $14.07 billion against $8.01 billion reported). With no copy on file
    by then, the quarter is not derived.
    """
    low, high = _ONE_QUARTER_EARLIER_DAYS
    same_start = [
        fact
        for fact in concept_facts
        if fact.start_date == longer.start_date
        and fact.unit.upper() == longer.unit.upper()
        and low <= (longer.end_date - fact.end_date).days <= high
        and (_days_between(fact) or 0) >= _MIN_QUARTER_DAYS
    ]
    shorter = [
        fact for fact in same_start if fact.accession_number == longer.accession_number
    ] or [
        fact
        for fact in same_start
        if fact.form in QUARTERLY_FORMS and fact.filed_date <= longer.filed_date
    ]
    if not shorter:
        return None
    # Every copy of the shorter amount must share one end date, or the pair is unclear.
    newest_end = max(fact.end_date for fact in shorter)
    return _resolve_same_concept_candidates(
        [fact for fact in shorter if fact.end_date == newest_end]
    )


def _derived_fact(
    longer: FactRecord,
    shorter: FactRecord,
    concept_facts: list[FactRecord],
    *,
    method: str,
    label: str,
    metric: Metric,
    owner: FactOwner,
    source_url: str,
    source_url_for_accession: Callable[[str], str],
) -> FinancialFact:
    shorter_url = source_url_for_accession(shorter.accession_number)
    longer_before = comparative(concept_facts, longer, source_url)
    shorter_before = comparative(concept_facts, shorter, shorter_url)
    year_earlier = None
    if longer_before is not None and shorter_before is not None:
        # The year-earlier quarter by the same subtraction, each part as its own filing
        # restates it.
        year_earlier = longer_before.model_copy(
            update={
                "value": longer_before.value - shorter_before.value,
                "start_date": shorter_before.end_date + timedelta(days=1),
                "derivation": Derivation(
                    method=method, label=label, parts=[longer_before, shorter_before]
                ),
            }
        )
    return _fact(
        longer,
        metric,
        owner,
        source_url,
        value=longer.value - shorter.value,
        start_date=shorter.end_date + timedelta(days=1),
        directly_reported=False,
        derivation=Derivation(
            method=method,
            label=label,
            parts=[_part(longer, source_url), _part(shorter, shorter_url)],
        ),
        year_earlier=year_earlier,
    )


def derive_quarter(
    facts: list[FactRecord],
    filing: Filing,
    metric: Metric,
    owner: FactOwner,
    source_url: str,
    source_url_for_accession: Callable[[str], str],
) -> FinancialFact:
    """The quarter ending on ``filing``'s report date, when no filing reports it alone.

    A 10-K gives the fiscal fourth quarter as the fiscal year minus nine months;
    a 10-Q gives a cash-flow quarter as year to date minus the previous quarter's
    year to date. A standalone quarter the 10-K happens to report is used as is.
    Per-share figures are never derived.
    """
    annual = filing.form in (FormType.FORM_10_K, FormType.FORM_10_K_A)
    per_share = False
    for taxonomy, concept in get_concept_candidates(metric):
        concept_facts = [
            fact
            for fact in facts
            if fact.taxonomy == taxonomy
            and fact.concept == concept
            and fact.unit.upper() == owner.currency.upper()
        ]
        in_filing = [
            fact
            for fact in concept_facts
            if fact.accession_number == filing.accession_number
            and fact.end_date == filing.report_date
        ]
        if annual:
            standalone = [
                fact
                for fact in in_filing
                if is_standalone_quarter(fact.start_date, fact.end_date)
            ]
            if standalone:
                selected = _resolve_same_concept_candidates(standalone)
                return _build_financial_fact(
                    selected,
                    metric,
                    owner,
                    source_url,
                    year_earlier=comparative(concept_facts, selected, source_url),
                )
        bounds = _ANNUAL_DAYS if annual else (_CUMULATIVE_MIN_DAYS, _NINE_MONTH_DAYS[1])
        longer_candidates = [fact for fact in in_filing if _within(_days_between(fact), bounds)]
        if not longer_candidates:
            continue
        if metric in PER_SHARE_METRICS:
            per_share = True
            continue
        longer = _resolve_same_concept_candidates(longer_candidates)
        shorter = _one_quarter_shorter(concept_facts, longer)
        if shorter is None or (
            annual and not _within(_days_between(shorter), _NINE_MONTH_DAYS)
        ):
            continue
        return _derived_fact(
            longer,
            shorter,
            concept_facts,
            method="annual_minus_nine_months" if annual else "year_to_date_difference",
            label=FOURTH_QUARTER_LABEL if annual else YEAR_TO_DATE_LABEL,
            metric=metric,
            owner=owner,
            source_url=source_url,
            source_url_for_accession=source_url_for_accession,
        )
    if per_share:
        raise PerShareNotDerivableError(
            "Per-share figures for this quarter are reported only for a longer period",
            details={"metric": metric.value, "report_date": filing.report_date.isoformat()},
        )
    raise UnsupportedQuarterlyFactError(
        "No reported or derivable quarter exists for metric",
        details={
            "metric": metric.value,
            "filing_accession": filing.accession_number,
            "report_date": filing.report_date.isoformat(),
            "reason": "not_reported_or_derivable",
        },
    )


# --- Balance-sheet amounts and trailing years (ADR 0008) ----------------------------

_ONE_YEAR_TOLERANCE_DAYS = 7
_TRAILING_PARTS = {Metric.NET_INCOME_TTM: Metric.NET_INCOME}
TRAILING_YEAR_LABEL = (
    "Last fiscal year (10-K) plus this year to date minus the same months "
    "a year earlier (10-Q)"
)


def select_instant_fact(
    facts: list[FactRecord],
    filing: Filing,
    metric: Metric,
    owner: FactOwner,
    source_url: str,
) -> FinancialFact:
    """A balance-sheet amount at ``filing``'s report date, as that filing reports it.

    An instant has no start; the fact's period starts and ends on the report date.
    """
    for taxonomy, concept in get_concept_candidates(metric):
        candidates = [
            fact
            for fact in facts
            if fact.taxonomy == taxonomy
            and fact.concept == concept
            and fact.start_date is None
            and fact.accession_number == filing.accession_number
            and fact.end_date == filing.report_date
            and fact.unit.upper() == owner.currency.upper()
        ]
        if not candidates:
            continue
        selected = _resolve_same_concept_candidates(candidates)
        return _build_financial_fact(
            selected.model_copy(update={"start_date": selected.end_date}),
            metric,
            owner,
            source_url,
            year_earlier=comparative(
                [fact for fact in facts if fact.concept == concept], selected, source_url
            ),
        )
    raise UnsupportedQuarterlyFactError(
        "No balance-sheet amount is reported at the filing's report date",
        details={
            "metric": metric.value,
            "filing_accession": filing.accession_number,
            "report_date": filing.report_date.isoformat(),
        },
    )


def _newest_filed(facts: list[FactRecord]) -> list[FactRecord]:
    """The copies of an amount from its newest filing; later 10-Ks repeat it."""
    newest = max(fact.filed_date for fact in facts)
    return [fact for fact in facts if fact.filed_date == newest]


def _near(day: date, target: date) -> bool:
    return abs((day - target).days) <= _ONE_YEAR_TOLERANCE_DAYS


def derive_trailing_year(
    facts: list[FactRecord],
    filing: Filing,
    metric: Metric,
    owner: FactOwner,
    source_url: str,
    source_url_for_accession: Callable[[str], str],
) -> FinancialFact:
    """The four quarters ending on ``filing``'s report date, as one amount.

    A 10-K reports the fiscal year itself. After a 10-Q, the year is the last
    fiscal year plus this year to date minus the same months a year earlier;
    the 10-Q reports both year-to-date amounts and the 10-K the fiscal year.
    """
    annual_form = filing.form in ANNUAL_FORMS
    for taxonomy, concept in get_concept_candidates(metric):
        concept_facts = [
            fact
            for fact in facts
            if fact.taxonomy == taxonomy
            and fact.concept == concept
            and fact.unit.upper() == owner.currency.upper()
            and fact.start_date is not None
        ]
        in_filing = [
            fact
            for fact in concept_facts
            if fact.accession_number == filing.accession_number
            and fact.end_date == filing.report_date
        ]
        years = [fact for fact in in_filing if _within(_days_between(fact), _ANNUAL_DAYS)]
        if annual_form:
            if not years:
                continue
            return _build_financial_fact(
                _resolve_same_concept_candidates(years),
                metric,
                owner,
                source_url,
            )
        to_date = [
            fact
            for fact in in_filing
            if _within(_days_between(fact), (_MIN_QUARTER_DAYS, _NINE_MONTH_DAYS[1]))
        ]
        if not to_date:
            continue
        # The longest same-end amount is the year to date (the quarter itself in Q1).
        longest = max(_days_between(fact) or 0 for fact in to_date)
        current = _resolve_same_concept_candidates(
            [fact for fact in to_date if _days_between(fact) == longest]
        )
        assert current.start_date is not None
        earlier_end = one_year_earlier(current.end_date)
        earlier = [
            fact
            for fact in concept_facts
            if fact.form in QUARTERLY_FORMS
            and _near(fact.end_date, earlier_end)
            and abs((_days_between(fact) or 0) - longest) <= _ONE_YEAR_TOLERANCE_DAYS
        ]
        # Only a 10-K's fiscal year: proxy statements tag net income too.
        last_year = [
            fact
            for fact in concept_facts
            if fact.form in ANNUAL_FORMS
            and _within(_days_between(fact), _ANNUAL_DAYS)
            and _near(fact.end_date, current.start_date - timedelta(days=1))
        ]
        if not earlier or not last_year:
            continue
        # Prefer the comparative this 10-Q reports, then the newest filing.
        same_filing = [
            fact for fact in earlier if fact.accession_number == filing.accession_number
        ]
        prior = _resolve_same_concept_candidates(same_filing or _newest_filed(earlier))
        year = _resolve_same_concept_candidates(_newest_filed(last_year))
        return _fact(
            current,
            metric,
            owner,
            source_url,
            value=year.value + current.value - prior.value,
            start_date=prior.end_date + timedelta(days=1),
            directly_reported=False,
            derivation=Derivation(
                method="trailing_twelve_months",
                label=TRAILING_YEAR_LABEL,
                # Each part is net income for its own months, not a trailing year.
                parts=[
                    part.model_copy(update={"metric": _TRAILING_PARTS.get(metric, metric).value})
                    for part in (
                        _part(year, source_url_for_accession(year.accession_number)),
                        _part(current, source_url),
                        _part(prior, source_url_for_accession(prior.accession_number)),
                    )
                ],
            ),
        )
    raise UnsupportedQuarterlyFactError(
        "No fiscal year and year-to-date amounts give the trailing year",
        details={
            "metric": metric.value,
            "filing_accession": filing.accession_number,
            "report_date": filing.report_date.isoformat(),
        },
    )
