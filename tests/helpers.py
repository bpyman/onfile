"""Shared test helpers."""

from datetime import date
from decimal import Decimal

from financial_analyst_agent.domain.models import FactRecord, Filing


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
