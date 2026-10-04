"""Fixes from the showcase run: retail calendars, long quarters, annual filers,
narrowing follow-ups, whole-snapshot rankings, and date-only 10-Q changes."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

from financial_analyst_agent.answer_notes import (
    FISCAL_Q4_GAP_BANNER,
    annual_filer_note,
    period_notes,
)
from financial_analyst_agent.contracts import TableRow
from financial_analyst_agent.filing_change import diff_paragraphs
from financial_analyst_agent.graph.analysis_spec import (
    AnalysisSpec,
    PeriodSelection,
    ResolvedCompany,
    SpecPatch,
    compile_tasks,
)
from financial_analyst_agent.graph.spec_turn import drop_annual_filers, materialize_period_dates
from financial_analyst_agent.presentation import long_quarter_banner
from financial_analyst_agent.ranking import SnapshotRanking
from financial_analyst_agent.request_wording import read_window, refine_patch_from_message
from financial_analyst_agent.runtime import FIXTURE_UNIVERSE_SNAPSHOT_PATH
from helpers import FakeFacts

# Costco's quarters end on Sundays of 12- and 16-week periods; Walmart's at month ends.
_COSTCO = (date(2026, 5, 10), date(2026, 2, 15), date(2025, 11, 23), date(2025, 8, 31))
_WALMART = (date(2026, 7, 31), date(2026, 4, 30), date(2026, 1, 31), date(2025, 10, 31))


def _company(query: str, name: str | None = None) -> ResolvedCompany:
    return ResolvedCompany(cik=query, name=name or query, ticker=query.upper(), query=query)


class _Facts(FakeFacts):
    def list_quarterly_report_dates(self, company: str, *, limit: int) -> tuple[date, ...]:
        return {"Costco": _COSTCO, "Walmart": _WALMART}[company][:limit]

    def files_quarterly(self, company: str) -> tuple[bool, str]:
        return company != "NVO", {"NVO": "Novo Nordisk A/S"}.get(company, company)


def _runtime() -> Any:
    return SimpleNamespace(facts=_Facts())


def _window(*companies: ResolvedCompany) -> AnalysisSpec:
    return AnalysisSpec(
        companies=companies,
        metrics=("revenue",),
        periods=PeriodSelection(kind="last_n_quarters", count=4),
    )


def test_a_retailer_ten_days_off_another_calendar_keeps_its_own_quarters() -> None:
    spec = materialize_period_dates(
        _window(_company("Costco"), _company("Walmart")), _runtime()
    )

    asked = {(task.issuers, task.report_date) for task in compile_tasks(spec)}

    # Costco's May 10 and Walmart's April 30 sit in the same month of the quarter
    # grid; asking Walmart for May 10 found no filing, so every cell was missing.
    assert asked == {
        *((("Costco",), day) for day in _COSTCO),
        *((("Walmart",), day) for day in _WALMART),
    }


def test_a_sixteen_week_fourth_quarter_is_not_a_skipped_quarter() -> None:
    spec = materialize_period_dates(_window(_company("Costco")), _runtime())

    message = "Costco revenue"
    assert FISCAL_Q4_GAP_BANNER not in period_notes(
        message, spec, window=read_window(message)
    )


def _row(end: date, weeks: int) -> TableRow:
    return TableRow(
        company_name="Costco Wholesale Corporation",
        ticker="COST",
        cik="0000909832",
        metric="revenue",
        value=Decimal("86156000000"),
        start_date=end - timedelta(days=weeks * 7 - 1),
        end_date=end,
        form="10-K",
        accession_number=f"COST-{end}",
        concept="Revenues",
        source_url="https://www.sec.gov/",
    )


def test_long_quarters_are_named_with_their_length() -> None:
    rows = [_row(date(2026, 5, 10), 12), _row(date(2025, 8, 31), 16), _row(date(2024, 9, 1), 16)]

    assert long_quarter_banner(rows) == (
        "Costco Wholesale's quarters ended Aug 31, 2025 and Sep 1, 2024 ran 16 weeks, "
        "longer than the usual 13 weeks, which lifts those amounts."
    )
    assert long_quarter_banner(rows[:1]) == ""


def test_annual_filers_are_left_out_with_a_reason() -> None:
    spec = _window(_company("LLY", "Eli Lilly and Company"), _company("NVO", "Novo Nordisk A/S"))

    kept, dropped = drop_annual_filers(spec, _runtime())

    assert [company.query for company in kept.companies] == ["LLY"]
    assert dropped == ["Novo Nordisk"]
    assert annual_filer_note(dropped) == (
        "Novo Nordisk files annual reports with the SEC (Form 20-F or 40-F) rather than "
        "quarterly 10-Qs, so there are no quarterly figures to show."
    )


def test_a_facts_port_without_the_check_keeps_every_company() -> None:
    spec = _window(_company("NVO"))

    assert drop_annual_filers(spec, SimpleNamespace(facts=object())) == (spec, [])


def test_naming_one_of_the_companies_on_screen_is_a_new_question() -> None:
    current = AnalysisSpec(
        companies=(
            _company("COST", "Costco Wholesale Corporation"),
            _company("WMT", "Walmart Inc."),
        ),
        metrics=("revenue",),
    )
    patch = SpecPatch(mode="replace", add_companies=("WMT",), add_metrics=("revenue",))

    refined = refine_patch_from_message(
        patch, "Walmart revenue over the last four quarters", current
    )

    assert refined.mode == "replace"
    assert refined.add_companies == ("WMT",)
    # A period on its own still edits the analysis on screen.
    edit = refine_patch_from_message(
        SpecPatch(mode="replace", add_companies=("COST", "WMT")), "last eight quarters", current
    )
    assert edit.mode == "extend"


def test_top_companies_with_no_industry_ranks_the_whole_snapshot() -> None:
    ranking = SnapshotRanking.from_path(FIXTURE_UNIVERSE_SNAPSHOT_PATH)

    table = ranking.rank_companies("companies", 5)

    assert table.sector == "All companies"
    assert len(table.companies) == 5
    caps = [company.market_cap for company in table.companies]
    assert caps == sorted(caps, reverse=True)
    assert len({company.sector for company in ranking.rank_companies("stocks", 20).companies}) > 1


def test_a_paragraph_that_only_moved_a_year_is_not_a_change() -> None:
    older = (
        "Highlights from the third quarter of fiscal year 2025 compared with fiscal year 2024.\n\n"
        "Microsoft Cloud revenue increased 20% to $42.4 billion."
    )
    newer = (
        "Highlights from the third quarter of fiscal year 2026 compared with fiscal year 2025.\n\n"
        "Microsoft Cloud revenue increased 29% to $54.5 billion."
    )

    changes = diff_paragraphs(
        older,
        newer,
        section="mda",
        older_accession="old",
        newer_accession="new",
        older_url="https://www.sec.gov/old.htm",
        newer_url="https://www.sec.gov/new.htm",
    )

    assert [(change.before_text, change.after_text) for change in changes] == [
        (
            "Microsoft Cloud revenue increased 20% to $42.4 billion.",
            "Microsoft Cloud revenue increased 29% to $54.5 billion.",
        )
    ]
