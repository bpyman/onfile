"""Shared test helpers."""

from collections.abc import Collection, Mapping, Sequence
from datetime import date
from decimal import Decimal

from financial_analyst_agent.domain.errors import CompanyNotFoundError
from financial_analyst_agent.domain.models import FactRecord, Filing
from financial_analyst_agent.services.fiscal_periods import FiscalPeriod


def make_filing(
    *,
    form: str = "10-Q",
    accession_number: str = "0000320193-24-000081",
    filed_date: date = date(2024, 11, 1),
    report_date: date = date(2024, 9, 28),
    primary_document: str | None = "aapl-20240928.htm",
) -> Filing:
    return Filing(
        form=form,
        accession_number=accession_number,
        filed_date=filed_date,
        report_date=report_date,
        primary_document=primary_document,
        fiscal_year=2024,
        fiscal_period="Q3",
    )


def make_fact(
    *,
    accession_number: str = "0000320193-24-000081",
    end_date: date = date(2024, 9, 28),
    start_date: date | None = date(2024, 6, 30),
    form: str = "10-Q",
    unit: str = "USD",
    value: Decimal = Decimal("23636000000"),
    concept: str = "NetIncomeLoss",
    taxonomy: str = "us-gaap",
    filed_date: date = date(2024, 11, 1),
) -> FactRecord:
    return FactRecord(
        accession_number=accession_number,
        end_date=end_date,
        start_date=start_date,
        form=form,
        unit=unit,
        value=value,
        concept=concept,
        taxonomy=taxonomy,
        filed_date=filed_date,
    )


def named_by_cik(*names: str):  # type: ignore[no-untyped-def]
    """Map the CIK a turn asks a test fake for back to the name the fake knows.

    A resolved company is asked for by CIK (CONTEXT.md, Analysis spec); fakes keep
    their readable names. A name the fixture snapshot does not hold maps to itself.
    """
    from financial_analyst_agent.domain.errors import CompanyNotFoundError
    from financial_analyst_agent.ranking import SnapshotRanking
    from financial_analyst_agent.runtime import FIXTURE_UNIVERSE_SNAPSHOT_PATH

    ranking = SnapshotRanking.from_path(FIXTURE_UNIVERSE_SNAPSHOT_PATH)
    by_cik: dict[str, str] = {}
    for name in names:
        try:
            by_cik[ranking.lookup_member(name).cik] = name
        except CompanyNotFoundError:
            continue

    def named(company: str) -> str:
        return by_cik.get(company, company)

    return named


class FakeFacts:
    """A facts port's optional methods, for fakes that only answer ``get_financials``.

    No quarters are listed, no fiscal periods are known, every company files
    10-Qs, and a company keeps the name it was asked by.
    """

    def list_quarterly_report_dates(self, company: str, *, limit: int) -> tuple[date, ...]:
        return ()

    def fiscal_periods(self, company: str) -> tuple[object, ...]:
        return ()

    def files_quarterly(self, company: str) -> tuple[bool, str]:
        return True, company

    def display_name(self, cik: str, fallback: str) -> str:
        return fallback


class ListedFilings(FakeFacts):
    """Quarter ends and fiscal periods per company, keyed by the name a test asks by.

    ``quarters`` are each company's quarter ends, newest first; a company given only
    these is a calendar-year filer, so its fiscal periods carry the calendar year and
    quarter of each end. ``fiscal`` are each company's declared fiscal periods; a
    company given only these lists their ends as its quarter ends. A company in
    ``failing`` cannot be found; one in ``annual`` files no 10-Qs. A company given
    neither quarters nor fiscal periods was not set up: listing it is a ``KeyError``.

    ``listed`` records every listing as ``(company, limit)`` in call order, with no
    limit for a listing of fiscal periods, so a test can assert which company was
    listed, with what limit, and in what order.
    """

    def __init__(
        self,
        quarters: Mapping[str, Sequence[date]] = {},
        fiscal: Mapping[str, Sequence[FiscalPeriod]] = {},
        *,
        failing: Collection[str] = (),
        annual: Collection[str] = (),
    ) -> None:
        self.quarters = {company: tuple(dates) for company, dates in quarters.items()}
        self.fiscal = {company: tuple(periods) for company, periods in fiscal.items()}
        self.failing = frozenset(failing)
        self.annual = frozenset(annual)
        self.listed: list[tuple[str, int | None]] = []

    def list_quarterly_report_dates(self, company: str, *, limit: int) -> tuple[date, ...]:
        self.listed.append((company, limit))
        self._known(company)
        if company in self.quarters:
            return self.quarters[company][:limit]
        return tuple(period.end for period in self.fiscal[company])[:limit]

    def fiscal_periods(self, company: str) -> tuple[FiscalPeriod, ...]:
        self.listed.append((company, None))
        self._known(company)
        if company in self.fiscal:
            return self.fiscal[company]
        return tuple(
            FiscalPeriod(
                end=end, fiscal_year=end.year, quarter=(end.month - 1) // 3 + 1, form="10-Q"
            )
            for end in self.quarters[company]
        )

    def files_quarterly(self, company: str) -> tuple[bool, str]:
        return company not in self.annual, company

    def _known(self, company: str) -> None:
        if company in self.failing:
            raise CompanyNotFoundError(f"no such company: {company}")
