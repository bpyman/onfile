"""Domain models."""

from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field

from financial_analyst_agent.domain.enums import DataSourceKind, Metric
from financial_analyst_agent.domain.serialization import DecimalStr


class Company(BaseModel):
    """Resolved SEC-reporting company."""

    cik: str = Field(min_length=10, max_length=10, pattern=r"^\d{10}$")
    name: str
    tickers: list[str] = Field(default_factory=list)


class Filing(BaseModel):
    """SEC filing metadata for a reporting period."""

    form: str
    accession_number: str
    filed_date: date
    report_date: date
    primary_document: str | None = None
    fiscal_year: int | None = None
    fiscal_period: str | None = None


class FactRecord(BaseModel):
    """Normalized XBRL fact used as input to the deterministic selector."""

    accession_number: str
    end_date: date
    start_date: date | None = None
    form: str
    unit: str
    value: DecimalStr
    concept: str
    taxonomy: str
    filed_date: date


class SplitAdjustment(BaseModel):
    """A per-share figure filed before a stock split, put on the basis after it (ADR 0009).

    The shown value is ``first_filed / divisor``; ``splits`` names the splits
    the divisor compounds ("the ten-for-one split of June 2024").
    """

    first_filed: DecimalStr
    divisor: DecimalStr
    splits: str

    @property
    def operation(self) -> str:
        """ "÷ 10"; a reverse split multiplies ("× 10")."""
        divisor = Decimal(str(self.divisor))
        if divisor >= 1:
            return f"÷ {_plain(divisor)}"
        return f"× {_plain(1 / divisor)}"

    @property
    def how(self) -> str:
        """ "÷ 10 for the ten-for-one split of June 2024"."""
        return f"{self.operation} for {self.splits}"

    @property
    def label(self) -> str:
        """The figure as first filed and how it was adjusted, for the evidence.

        "$5.98 as first filed, ÷ 10 for the ten-for-one split of June 2024".
        """
        value = Decimal(str(self.first_filed))
        sign = "-" if value < 0 else ""
        amount = abs(value)
        if amount.as_tuple().exponent > -2:  # type: ignore[operator]
            amount = amount.quantize(Decimal("0.01"))
        return f"{sign}${amount:f} as first filed, {self.how}"


def _plain(number: Decimal) -> str:
    """40, or 1.5: a ratio without trailing zeros or an exponent."""
    rounded = number.quantize(Decimal("0.0001")).normalize()
    return f"{rounded:f}"


class DerivationPart(BaseModel):
    """One directly reported fact a derived quarter was computed from."""

    value: DecimalStr
    start_date: date
    end_date: date
    form: str
    accession_number: str
    taxonomy: str
    concept: str
    filed_date: date
    source_url: str
    # Set when this part is itself derived (a fiscal Q4's revenue inside a gross
    # profit), so the evidence keeps the filings it came from.
    derivation: "Derivation | None" = None
    # The part's own metric when it differs from the derived one: a gross
    # profit's parts are revenue and cost of revenue. None: the same metric.
    metric: str | None = None
    # A per-share comparative filed before a split, on the basis after it.
    split_adjustment: SplitAdjustment | None = None


class Derivation(BaseModel):
    """How a derived amount was computed (ADR 0007, 0008).

    A derived quarter is ``parts[0]`` minus ``parts[1]``; a trailing year
    (``method == "trailing_twelve_months"``) is ``parts[0] + parts[1] - parts[2]``.
    """

    method: str
    label: str
    parts: list[DerivationPart]


DerivationPart.model_rebuild()


class FinancialFact(BaseModel):
    """A quarterly financial fact with typed provenance."""

    company_name: str
    ticker: str
    cik: str = Field(min_length=10, max_length=10, pattern=r"^\d{10}$")
    metric: Metric
    value: DecimalStr
    currency: str
    start_date: date
    end_date: date
    filed_date: date
    form: str
    accession_number: str
    taxonomy: str
    concept: str
    source_url: str
    directly_reported: bool = True
    derivation: Derivation | None = None
    source: DataSourceKind = DataSourceKind.SEC_XBRL
    # "Latest" stepped back: the end of a newer filed quarter SEC's companyfacts lacks.
    newer_filing_end: date | None = None
    # The same amount a year earlier as this fact's own filing reports it (its
    # comparative), on the same basis after a restatement or share split.
    year_earlier: DerivationPart | None = None
    # Weighted diluted shares the filing reports beside a per-share figure.
    diluted_shares: DecimalStr | None = None
    # A per-share figure filed before a stock split, shown on the basis after it.
    split_adjustment: SplitAdjustment | None = None
