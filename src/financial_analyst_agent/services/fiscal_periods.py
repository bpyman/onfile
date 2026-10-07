"""Fiscal labels for filings, named periods, and the gross-profit fallback.

A filing's XBRL declares the fiscal year and period it covers (``fy`` and
``fp`` on every fact it reports), so "Q3 2024" means what the company itself
calls its third quarter of fiscal 2024, as companies and the press name
quarters (ADR 0007).
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, replace
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from financial_analyst_agent.domain.enums import ANNUAL_FORMS, PERIODIC_FORMS, Metric
from financial_analyst_agent.domain.errors import UnsupportedQuarterlyFactError
from financial_analyst_agent.domain.models import (
    Derivation,
    DerivationPart,
    Filing,
    FinancialFact,
)
from financial_analyst_agent.services.filing_selector import FISCAL_WEEK_TOLERANCE

_QUARTER_OF_PERIOD = {"Q1": 1, "Q2": 2, "Q3": 3, "Q4": 4, "FY": 4}
GROSS_PROFIT_LABEL = "Revenue minus cost of revenue"


@dataclass(frozen=True)
class FiscalLabel:
    """The fiscal year and period a filing declares (``fy``, ``fp``)."""

    fiscal_year: int | None
    fiscal_period: str | None


@dataclass(frozen=True)
class FiscalPeriod:
    """One quarter end with the fiscal year and quarter its filing declares."""

    end: date
    fiscal_year: int | None
    quarter: int | None
    form: str


def fiscal_labels(payload: dict[str, Any]) -> dict[str, FiscalLabel]:
    """Accession → declared fiscal year and period, from any fact the filing reports."""
    labels: dict[str, FiscalLabel] = {}
    facts = payload.get("facts")
    if not isinstance(facts, dict):
        return labels
    for concepts in facts.values():
        if not isinstance(concepts, dict):
            continue
        for concept in concepts.values():
            units = concept.get("units") if isinstance(concept, dict) else None
            if not isinstance(units, dict):
                continue
            for entries in units.values():
                if not isinstance(entries, list):
                    continue
                for entry in entries:
                    if not isinstance(entry, dict):
                        continue
                    accession = entry.get("accn")
                    if not isinstance(accession, str) or accession in labels:
                        continue
                    year = entry.get("fy")
                    period = entry.get("fp")
                    labels[accession] = FiscalLabel(
                        year if isinstance(year, int) else None,
                        period if isinstance(period, str) else None,
                    )
    return labels


def periods_from_filings(
    filings: list[Filing], labels: dict[str, FiscalLabel]
) -> tuple[FiscalPeriod, ...]:
    """Newest-first quarter ends, each labelled by its original filing."""
    by_end: dict[date, FiscalPeriod] = {}
    # The original filing names the period; an amendment repeats it.
    for filing in sorted(filings, key=lambda item: item.filed_date):
        if filing.form not in PERIODIC_FORMS:
            continue
        if any(abs(end - filing.report_date) <= FISCAL_WEEK_TOLERANCE for end in by_end):
            continue
        label = labels.get(filing.accession_number, FiscalLabel(None, None))
        quarter = _QUARTER_OF_PERIOD.get(label.fiscal_period or "")
        if filing.form in ANNUAL_FORMS:
            quarter = 4
        by_end[filing.report_date] = FiscalPeriod(
            end=filing.report_date,
            fiscal_year=label.fiscal_year,
            quarter=quarter,
            form=filing.form,
        )
    newest_first = tuple(sorted(by_end.values(), key=lambda period: period.end, reverse=True))
    return _without_repeats(_sequenced(newest_first))


Label = tuple[int, int]
# A quarter is 13 weeks: how many lie between two period ends.
_QUARTER_DAYS = 91.3


def _label(period: FiscalPeriod) -> Label | None:
    if period.fiscal_year is None or period.quarter is None:
        return None
    return period.fiscal_year, period.quarter


def _without_repeats(periods: tuple[FiscalPeriod, ...]) -> tuple[FiscalPeriod, ...]:
    """Newest-first periods, where two that declare one quarter are told apart.

    One of two periods declaring the same fiscal quarter is mislabelled
    (Salesforce's 10-K for the year ended January 2026 declares fiscal 2025,
    as did the one before; Blackstone's second 10-Q of 2024 declares Q1).
    Each takes the label its position gives it: the quarters elapsed since
    the period before it, or until the one after, from that period's own label,
    when that label is not repeated. The one whose label its position confirms
    keeps it; a repair can expose the next (CrowdStrike's 10-Ks each declare
    the year before), so this runs until no label repeats or nothing changes.
    """
    ordered = list(reversed(periods))
    for _ in ordered:
        counts = Counter(label for period in ordered if (label := _label(period)) is not None)
        repeated = {label for label, count in counts.items() if count > 1}
        if not repeated:
            break
        fixes = {
            index: expected
            for index, period in enumerate(ordered)
            if _label(period) in repeated
            and (expected := _positional_label(ordered, index, repeated)) is not None
            and expected != _label(period)
        }
        if not fixes:
            break
        for index, (year, quarter) in fixes.items():
            ordered[index] = replace(ordered[index], fiscal_year=year, quarter=quarter)
    return tuple(reversed(ordered))


def _positional_label(
    ordered: list[FiscalPeriod], index: int, repeated: set[Label]
) -> Label | None:
    """The label a period's neighbours give it, when those that are trusted agree."""
    period = ordered[index]
    found: set[Label] = set()
    for step in (-1, 1):
        other = index + step
        if not 0 <= other < len(ordered):
            continue
        label = _label(ordered[other])
        if label is None or label in repeated:
            continue
        quarters = round(abs((period.end - ordered[other].end).days) / _QUARTER_DAYS)
        if quarters < 1:
            continue
        position = label[0] * 4 + label[1] - 1 - step * quarters
        year, quarter = divmod(position, 4)
        # A 10-K closes a fiscal year; a 10-Q never does.
        if (quarter + 1 == 4) == (period.form in ANNUAL_FORMS):
            found.add((year, quarter + 1))
    return found.pop() if len(found) == 1 else None


def _sequenced(periods: tuple[FiscalPeriod, ...]) -> tuple[FiscalPeriod, ...]:
    """Newest-first periods, with quarters that repeat the year just closed renumbered.

    A filing's own ``fy`` is sometimes wrong: Oracle's 10-Q for the quarter ended
    August 31, 2026 (Q1 of fiscal 2027) declares 2026, the year its 10-K just
    closed, and NetApp's first two quarters of fiscal 2026 declare 2025. A Q1
    that follows a Q4 of the same fiscal year belongs to the next year, with
    the quarters after it that keep that label. When the Q4's own label is not
    confirmed by the 10-K a year before it, a later report keeping the year
    means the Q4 is the wrong one, and nothing is renumbered; so too when the
    next 10-K closes that same year. Only filed labels
    are compared, so one bad label never shifts the rest.
    """
    ordered = list(reversed(periods))
    repaired = list(ordered)
    for index in range(1, len(ordered)):
        closed, period = ordered[index - 1], ordered[index]
        if not (
            closed.quarter == 4
            and period.quarter == 1
            and period.fiscal_year is not None
            and period.fiscal_year == closed.fiscal_year
        ):
            continue
        year = period.fiscal_year
        earlier = [item for item in ordered[: index - 1] if item.quarter == 4]
        confirmed = not earlier or earlier[-1].fiscal_year == year - 1
        run = index
        while (
            run < len(ordered)
            and ordered[run].quarter in (1, 2, 3)
            and ordered[run].fiscal_year == year
        ):
            run += 1
        if not confirmed and run < len(ordered) and ordered[run].fiscal_year == year:
            continue
        if not confirmed and run - index > 1:
            continue
        following = next((item for item in ordered[run:] if item.quarter == 4), None)
        if following is not None and following.fiscal_year == year:
            # The next 10-K closes this year: the Q4 before was the mislabelled one
            # (Domino's 53-week year ending January 1, 2023 declares 2023).
            continue
        for fixed in range(index, run):
            repaired[fixed] = replace(ordered[fixed], fiscal_year=year + 1)
    return tuple(reversed(_labelled_forward(repaired)))


# A quarter's end is 12 to 14 weeks after the one before it.
_NEXT_QUARTER_DAYS = (80, 100)


def _labelled_forward(ordered: list[FiscalPeriod]) -> list[FiscalPeriod]:
    """Oldest-first periods, the newest unlabelled ones numbered from the one before.

    SEC's company facts can lag a filing by weeks: Coca-Cola's 10-Q for the
    quarter ended June 27, 2026 is listed but carries no fiscal year yet, so
    "Q2 2026" found nothing. The quarter after Q1 of 2026 is Q2 of 2026.
    """
    labelled = list(ordered)
    low, high = _NEXT_QUARTER_DAYS
    for index in range(1, len(labelled)):
        before, period = labelled[index - 1], labelled[index]
        if period.fiscal_year is not None or before.fiscal_year is None:
            continue
        if before.quarter is None or not low <= (period.end - before.end).days <= high:
            continue
        quarter = before.quarter % 4 + 1
        if (period.quarter or quarter) != quarter:
            continue
        year = before.fiscal_year + (1 if before.quarter == 4 else 0)
        labelled[index] = replace(period, fiscal_year=year, quarter=quarter)
    return labelled


def calendar_quarter(end: date) -> tuple[int, int]:
    """(year, quarter) holding the middle of the quarter that ends on ``end``."""
    middle = end - timedelta(days=45)
    return middle.year, (middle.month - 1) // 3 + 1


def dates_for(
    periods: tuple[FiscalPeriod, ...], year: int, quarter: int | None, *, calendar: bool
) -> tuple[date, ...]:
    """Newest-first quarter ends a named year (or one of its quarters) covers."""
    matched: list[date] = []
    for period in periods:
        if calendar:
            period_year, period_quarter = calendar_quarter(period.end)
        else:
            if period.fiscal_year is None or period.quarter is None:
                continue
            period_year, period_quarter = period.fiscal_year, period.quarter
        if period_year == year and (quarter is None or period_quarter == quarter):
            matched.append(period.end)
    return tuple(matched)


def gross_profit_from_components(revenue: FinancialFact, cost: FinancialFact) -> FinancialFact:
    """Gross profit as revenue minus cost of revenue, for filers that tag no gross profit."""

    def part(fact: FinancialFact) -> DerivationPart:
        return DerivationPart(
            value=fact.value,
            start_date=fact.start_date,
            end_date=fact.end_date,
            form=fact.form,
            accession_number=fact.accession_number,
            taxonomy=fact.taxonomy,
            concept=fact.concept,
            filed_date=fact.filed_date,
            source_url=fact.source_url,
            derivation=fact.derivation,
            metric=fact.metric.value,
        )

    derivation = Derivation(
        method="revenue_minus_cost_of_revenue",
        label=GROSS_PROFIT_LABEL,
        parts=[part(revenue), part(cost)],
    )
    return revenue.model_copy(
        update={
            "metric": Metric.GROSS_PROFIT,
            "value": revenue.value - cost.value,
            "concept": f"{revenue.concept} − {cost.concept}",
            "directly_reported": False,
            "derivation": derivation,
            "year_earlier": combined_year_earlier([revenue, cost], derivation, signs=(1, -1)),
        }
    )


REVENUE_FROM_COMPONENTS_LABEL = (
    "Gross profit plus cost of revenue, because the filing's own revenue figure "
    "is smaller than either and so mis-scaled"
)


def revenue_from_components(
    filed: FinancialFact, gross: FinancialFact, cost: FinancialFact
) -> FinancialFact:
    """Revenue as gross profit plus cost of revenue, when the filed revenue is mis-scaled."""
    derivation = Derivation(
        method="sum",
        label=REVENUE_FROM_COMPONENTS_LABEL,
        parts=[
            _derivation_part(gross).model_copy(update={"metric": gross.metric.value}),
            _derivation_part(cost).model_copy(update={"metric": cost.metric.value}),
        ],
    )
    return filed.model_copy(
        update={
            "value": gross.value + cost.value,
            "concept": f"{gross.concept} + {cost.concept}",
            "accession_number": gross.accession_number,
            "form": gross.form,
            "source_url": gross.source_url,
            "directly_reported": False,
            "derivation": derivation,
            "year_earlier": combined_year_earlier([gross, cost], derivation),
        }
    )


DEPRECIATION_AMORTIZATION_LABEL = "Depreciation plus amortization of intangible assets"
BANK_REVENUE_LABEL = "Net interest income plus noninterest income"


def sum_of_components(
    metric: Metric,
    facts: list[FinancialFact],
    *,
    label: str = DEPRECIATION_AMORTIZATION_LABEL,
    name_parts: bool = False,
) -> FinancialFact:
    """One amount as the sum of reported parts that cover the same period.

    ``name_parts`` labels each part by its own metric (a bank's net interest
    income), where the parts are not halves of the same metric.
    """
    first = facts[0]
    period = (first.start_date, first.end_date)
    if any((fact.start_date, fact.end_date) != period for fact in facts):
        raise UnsupportedQuarterlyFactError(
            "The parts of the amount cover different periods",
            details={"metric": metric.value},
        )
    derivation = Derivation(
        method="sum",
        label=label,
        parts=[
            _derivation_part(fact).model_copy(
                update={"metric": fact.metric.value if name_parts else None}
            )
            for fact in facts
        ],
    )
    return first.model_copy(
        update={
            "metric": metric,
            "value": sum((fact.value for fact in facts), start=Decimal(0)),
            "concept": " + ".join(fact.concept for fact in facts),
            "directly_reported": False,
            "derivation": derivation,
            "year_earlier": combined_year_earlier(facts, derivation),
        }
    )


def combined_year_earlier(
    facts: list[FinancialFact], derivation: Derivation, *, signs: tuple[int, ...] = ()
) -> DerivationPart | None:
    """The year-earlier amount by the same sum or difference, when every part has one.

    Each part's comparative comes from that part's own filing, so a restated part
    stays restated. None when any part lacks a comparative or they cover
    different periods.
    """
    befores = [fact.year_earlier for fact in facts]
    if any(before is None for before in befores):
        return None
    parts = [before for before in befores if before is not None]
    if len({(part.start_date, part.end_date) for part in parts}) != 1:
        return None
    weights = signs or (1,) * len(parts)
    value = sum(
        (part.value * weight for part, weight in zip(parts, weights, strict=True)),
        start=Decimal(0),
    )
    named = [
        part.model_copy(update={"metric": inner.metric or part.metric})
        for part, inner in zip(parts, derivation.parts, strict=True)
    ]
    return parts[0].model_copy(
        update={
            "value": value,
            "concept": " ".join(
                [parts[0].concept]
                + [
                    f"{'+' if weight > 0 else '−'} {part.concept}"
                    for part, weight in zip(parts[1:], weights[1:], strict=True)
                ]
            ),
            "metric": None,
            "derivation": derivation.model_copy(update={"parts": named}),
        }
    )


def _derivation_part(fact: FinancialFact) -> DerivationPart:
    return DerivationPart(
        value=fact.value,
        start_date=fact.start_date,
        end_date=fact.end_date,
        form=fact.form,
        accession_number=fact.accession_number,
        taxonomy=fact.taxonomy,
        concept=fact.concept,
        filed_date=fact.filed_date,
        source_url=fact.source_url,
        derivation=fact.derivation,
    )


# One fiscal quarter is 13 weeks, or 14 in a 53-week year; calendar quarters run
# 90 to 92 days. Anything outside this band pairs non-adjacent quarters.
# Up to 17 weeks: some 52/53-week retailers (Costco) run a 16- or 17-week fourth quarter.
_ADJACENT_QUARTER_GAP = (timedelta(days=84), timedelta(days=126))


def quarters_since(year: int, dates: Iterable[date]) -> tuple[date, ...]:
    """The quarter ends on or after 1 January of ``year``, newest first.

    A "since 2024" window is every filed quarter that ended since that calendar
    year began, on each company's own calendar: Walmart's quarter to 31 January
    2024 is one of them.
    """
    first = date(year, 1, 1)
    return tuple(sorted((end for end in dates if end >= first), reverse=True))


def quarters_since_fiscal_year(year: int, periods: Iterable[FiscalPeriod]) -> tuple[date, ...]:
    """The quarter ends in or after fiscal ``year``, newest first.

    A "since fiscal 2025" window is every filed quarter of that company's fiscal
    2025 and after, on its own labels: Apple's opens with the quarter ended
    December 2024, Microsoft's with September 2024. A quarter whose filing
    declares no fiscal year counts when it ended after one that does.
    """
    ordered = sorted(periods, key=lambda period: period.end, reverse=True)
    first = min(
        (
            period.end
            for period in ordered
            if period.fiscal_year is not None and period.fiscal_year >= year
        ),
        default=None,
    )
    if first is None:
        return ()
    return tuple(period.end for period in ordered if period.end >= first)


def quarters_in_fiscal_span(year: int, periods: Iterable[FiscalPeriod]) -> int:
    """How many quarters lie from Q1 of fiscal ``year`` to the newest filed one, inclusive.

    Counted on the company's own labels, so it is what filings reaching back
    that far would show; zero when the year is ahead of the filings, or no
    filing declares its fiscal quarter.
    """
    ordered = sorted(periods, key=lambda period: period.end, reverse=True)
    for newer, period in enumerate(ordered):
        if period.fiscal_year is None or period.quarter is None:
            continue
        return max((period.fiscal_year - year) * 4 + period.quarter + newer, 0)
    return 0


def quarters_in_span(year: int, newest: date) -> int:
    """How many quarter ends lie from 1 January of ``year`` to ``newest``, inclusive.

    Counted on the grid of quarters ending at ``newest``, so it is what a company
    whose filings reach back that far would show; zero when ``newest`` is before
    the year began.
    """
    days = (newest - date(year, 1, 1)).days
    if days < 0:
        return 0
    return int(days // _QUARTER_DAYS) + 1


def adjacent_quarters(newer: date, older: date) -> bool:
    low, high = _ADJACENT_QUARTER_GAP
    return low <= newer - older <= high


def one_year_earlier(day: date) -> date:
    """The same day a year before; 29 February becomes 28 February."""
    try:
        return day.replace(year=day.year - 1)
    except ValueError:
        return day.replace(year=day.year - 1, day=28)
