"""Per-share levels across a stock split, on the basis after it (ADR 0009).

A filing restates every per-share figure it presents on the basis after any
split before it was filed; one filed before a split is on the older basis. The
split's ratio is the one the company reports
(``StockholdersEquityNoteStockSplitConversionRatio1``), never inferred.
"""

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from fractions import Fraction

from financial_analyst_agent.domain.models import (
    DerivationPart,
    FactRecord,
    FinancialFact,
    SplitAdjustment,
)

# Reports of one ratio this close together are one split: NVIDIA tags its 2024
# split with periods ending 31 May and 30 June 2024.
_SAME_SPLIT = timedelta(days=90)
# An adjusted figure and the figure a later filing restates must agree to within
# rounding: half a cent.
_HALF_CENT = Decimal("0.005")
_QUARTER_DAYS = (70, 110)
# The most places an adjusted value is given to keep it from reading zero.
_MAX_PLACES = 6

_WORDS = [
    "zero",
    "one",
    "two",
    "three",
    "four",
    "five",
    "six",
    "seven",
    "eight",
    "nine",
    "ten",
    "eleven",
    "twelve",
    "thirteen",
    "fourteen",
    "fifteen",
    "sixteen",
    "seventeen",
    "eighteen",
    "nineteen",
    "twenty",
]


@dataclass(frozen=True)
class StockSplit:
    """One split: the ratio reported, and the dates the company reported it at.

    ``effective`` is the earliest date reported for it: a filing filed before it
    is on the older basis. ``named`` is the latest, which names the split's month
    ("June 2024" for NVIDIA's, whose reports end 31 May and 30 June).
    """

    ratio: Decimal
    effective: date
    named: date

    @property
    def description(self) -> str:
        """ "the ten-for-one split of June 2024"; "the one-for-ten reverse split of ..." """
        share = Fraction(self.ratio).limit_denominator(1000)
        kind = "split" if share > 1 else "reverse split"
        month = self.named.strftime("%B %Y")
        return f"the {_word(share.numerator)}-for-{_word(share.denominator)} {kind} of {month}"


def _word(number: int) -> str:
    return _WORDS[number] if 0 <= number < len(_WORDS) else str(number)


def reported_splits(ratio_records: list[FactRecord]) -> tuple[StockSplit, ...]:
    """The company's splits, oldest first, from the ratios it reports.

    Reports of the same ratio within about 90 days of each other are one split.
    A ratio of 1 or below zero is no split.
    """
    by_ratio: dict[Decimal, list[date]] = {}
    for record in ratio_records:
        ratio = Decimal(str(record.value))
        if ratio > 0 and ratio != 1:
            by_ratio.setdefault(ratio, []).append(record.end_date)
    splits: list[StockSplit] = []
    for ratio, ends in by_ratio.items():
        ordered = sorted(set(ends))
        first = last = ordered[0]
        for end in ordered[1:]:
            if end - last > _SAME_SPLIT:
                splits.append(StockSplit(ratio, first, last))
                first = end
            last = end
        splits.append(StockSplit(ratio, first, last))
    return tuple(sorted(splits, key=lambda split: split.effective))


def _after(splits: tuple[StockSplit, ...], filed: date) -> tuple[StockSplit, ...]:
    """The splits that took effect after a filing was filed."""
    return tuple(split for split in splits if filed < split.effective)


def _divisor(splits: tuple[StockSplit, ...]) -> Decimal:
    divisor = Decimal(1)
    for split in splits:
        divisor *= split.ratio
    return divisor


def _adjusted(value: Decimal, divisor: Decimal) -> Decimal:
    """The value over the divisor, to the places it was filed at, as a company restates it.

    $5.98 over 10 is $0.60, NVIDIA's own restated figure; a place more only where
    those places would read zero ($0.04 over 10 is $0.004).
    """
    places = max(-int(value.as_tuple().exponent), 0)
    adjusted = (value / divisor).quantize(Decimal(1).scaleb(-places))
    while value and not adjusted and places < _MAX_PLACES:
        places += 1
        adjusted = (value / divisor).quantize(Decimal(1).scaleb(-places))
    return adjusted


def series_agrees(splits: tuple[StockSplit, ...], records: list[FactRecord]) -> bool:
    """Whether every quarter, put on the latest basis, agrees with its later restatement.

    Each filing's figure for a quarter, divided by the splits after it was filed,
    must agree to within half a cent with the same quarter from a filing on
    another basis. This is the guard against a misread ratio or date.
    """
    by_period: dict[tuple[str, date | None, date], list[tuple[Decimal, Decimal]]] = {}
    for record in records:
        if record.start_date is None:
            continue
        days = (record.end_date - record.start_date).days
        if not _QUARTER_DAYS[0] <= days <= _QUARTER_DAYS[1]:
            continue
        divisor = _divisor(_after(splits, record.filed_date))
        key = (record.concept, record.start_date, record.end_date)
        by_period.setdefault(key, []).append((divisor, Decimal(str(record.value)) / divisor))
    for reports in by_period.values():
        for divisor, value in reports:
            for other_divisor, other in reports:
                if divisor != other_divisor and abs(value - other) > _HALF_CENT:
                    return False
    return True


def on_latest_basis(
    fact: FinancialFact, splits: tuple[StockSplit, ...], records: list[FactRecord]
) -> FinancialFact:
    """A per-share fact on the basis after every split since its filing.

    ``records`` are the concept's reported facts, for the cross-check; a series
    that disagrees with its restatement is left as first filed. Its comparative
    comes from the same filing, so it takes the same divisor; weighted diluted
    shares take the inverse, so a split no longer shows between two quarters.
    """
    later = _after(splits, fact.filed_date)
    if not later:
        return fact
    concept = [record for record in records if record.concept == fact.concept]
    if not series_agrees(splits, concept):
        return fact
    divisor = _divisor(later)
    named = " and ".join(split.description for split in later)
    update: dict[str, object] = {
        "value": _adjusted(Decimal(str(fact.value)), divisor),
        "split_adjustment": SplitAdjustment(first_filed=fact.value, divisor=divisor, splits=named),
    }
    if fact.year_earlier is not None:
        update["year_earlier"] = _part_on_latest_basis(fact.year_earlier, divisor, named)
    if fact.diluted_shares is not None:
        update["diluted_shares"] = Decimal(str(fact.diluted_shares)) * divisor
    return fact.model_copy(update=update)


def _part_on_latest_basis(part: DerivationPart, divisor: Decimal, named: str) -> DerivationPart:
    return part.model_copy(
        update={
            "value": _adjusted(Decimal(str(part.value)), divisor),
            "split_adjustment": SplitAdjustment(
                first_filed=part.value, divisor=divisor, splits=named
            ),
        }
    )
