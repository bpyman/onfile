"""Retail calendars and long quarters, annual filers, narrowing follow-ups,
whole-snapshot rankings, and 10-Q paragraphs that changed only a date."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

from financial_analyst_agent.answer_notes import (
    FISCAL_Q4_GAP_BANNER,
    annual_filer_note,
    fund_note,
    missing_component_notes,
    period_notes,
)
from financial_analyst_agent.contracts import TableRow
from financial_analyst_agent.filing_change import diff_paragraphs
from financial_analyst_agent.graph.analysis_spec import (
    AnalysisSpec,
    PeriodSelection,
    ResolvedCompany,
    SpecPatch,
)
from financial_analyst_agent.graph.spec_turn import compile_tasks, drop_annual_filers, drop_funds
from financial_analyst_agent.period_selection import Periods, read
from financial_analyst_agent.presentation import long_quarter_banner
from financial_analyst_agent.ranking import SnapshotRanking
from financial_analyst_agent.request_wording import refine_patch_from_message
from financial_analyst_agent.runtime import FIXTURE_UNIVERSE_SNAPSHOT_PATH
from helpers import ListedFilings

# Costco's quarters end on Sundays of 12- and 16-week periods; Walmart's at month ends.
_COSTCO = (date(2026, 5, 10), date(2026, 2, 15), date(2025, 11, 23), date(2025, 8, 31))
_WALMART = (date(2026, 7, 31), date(2026, 4, 30), date(2026, 1, 31), date(2025, 10, 31))


def _company(query: str, name: str | None = None) -> ResolvedCompany:
    return ResolvedCompany(cik=query, name=name or query, ticker=query.upper(), query=query)


class _Facts(ListedFilings):
    """Two retailers' quarters; Novo Nordisk files annual reports under its full name."""

    def __init__(self) -> None:
        super().__init__({"Costco": _COSTCO, "Walmart": _WALMART}, annual=("NVO",))

    def files_quarterly(self, company: str) -> tuple[bool, str]:
        quarterly, _ = super().files_quarterly(company)
        return quarterly, {"NVO": "Novo Nordisk A/S"}.get(company, company)


def _runtime() -> Any:
    return SimpleNamespace(facts=_Facts())


def _window(*companies: ResolvedCompany) -> AnalysisSpec:
    return AnalysisSpec(
        companies=companies,
        metrics=("revenue",),
        periods=PeriodSelection(kind="last_n_quarters", count=4),
    )


def test_a_retailer_ten_days_off_another_calendar_keeps_its_own_quarters() -> None:
    spec = Periods(_window(_company("Costco"), _company("Walmart"))).dated(_Facts()).spec

    asked = {(task.issuers, task.report_date) for task in compile_tasks(spec)}

    # Costco's May 10 and Walmart's April 30 sit in the same month of the quarter
    # grid; asking Walmart for May 10 found no filing, so every cell was missing.
    assert asked == {
        *((("Costco",), day) for day in _COSTCO),
        *((("Walmart",), day) for day in _WALMART),
    }


def test_a_sixteen_week_fourth_quarter_is_not_a_skipped_quarter() -> None:
    spec = Periods(_window(_company("Costco"))).dated(_Facts()).spec

    message = "Costco revenue"
    assert FISCAL_Q4_GAP_BANNER not in period_notes(
        message, spec, window=read(message).reading
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


def test_a_fund_beside_a_company_is_left_out_with_a_reason() -> None:
    # README: a fund beside a company is left out with a note. SPY is on the
    # ineligible list (ADR 0001); the recorded runtime knows it by ticker only.
    spy = ResolvedCompany(cik="", name="SPY", ticker="", query="SPY")
    spec = _window(spy, _company("AAPL", "Apple Inc."))

    kept, dropped = drop_funds(spec)

    assert [company.query for company in kept.companies] == ["AAPL"]
    assert dropped == [("SPY", "SPDR S&P 500 ETF TRUST")]
    assert fund_note(dropped) == (
        "SPY (SPDR S&P 500 ETF Trust) is a fund, not an operating company, so it is left out."
    )


def test_a_fund_sec_identified_is_left_out_by_its_cik() -> None:
    spy = ResolvedCompany(
        cik="0000884394", name="SPDR S&P 500 ETF TRUST", ticker="SPY", query="SPY"
    )
    kept, dropped = drop_funds(_window(_company("AAPL", "Apple Inc."), spy))

    assert [company.query for company in kept.companies] == ["AAPL"]
    assert dropped == [("SPY", "SPDR S&P 500 ETF TRUST")]


def test_a_fund_asked_alone_is_kept_for_the_refusal() -> None:
    spec = _window(ResolvedCompany(cik="", name="SPY", ticker="", query="SPY"))

    assert drop_funds(spec) == (spec, [])


def test_two_funds_are_left_out_together() -> None:
    assert fund_note([("SPY", "SPDR S&P 500 ETF TRUST"), ("ARCC", "ARES CAPITAL CORP")]) == (
        "SPY (SPDR S&P 500 ETF Trust) and ARCC (Ares Capital Corp) are funds, not operating "
        "companies, so they are left out."
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


_CIKS = {"AMD": "0000002488", "INTC": "0000050863", "MRK": "0000310158", "AAPL": "0000320193"}


def _missing_row(
    company: str, ticker: str, end: date, missing: list[str], metric: str = "ebitda"
) -> TableRow:
    return TableRow(
        company_name=company,
        ticker=ticker,
        cik=_CIKS[ticker],
        metric=metric,
        reason="missing_fact",
        end_date=end,
        missing_components=missing,
    )


def test_a_formula_missing_a_component_says_which_in_a_note() -> None:
    # probe-round-3-gaps ticket 11: AMD's filings report depreciation only for the
    # fiscal year, so no quarter has EBITDA and no change; the answer says why.
    rows = [
        _missing_row("Advanced Micro Devices, Inc.", "AMD", end, ["depreciation_amortization"])
        for end in (date(2026, 6, 27), date(2026, 3, 28), date(2025, 12, 27), date(2025, 9, 27))
    ]

    assert missing_component_notes(rows) == [
        "Advanced Micro Devices' EBITDA is missing: no standalone quarterly depreciation "
        "and amortization was found in its filings, which EBITDA needs."
    ]


def test_a_formula_missing_two_components_names_both() -> None:
    rows = [
        _missing_row(
            "Merck & Co., Inc.",
            "MRK",
            date(2026, 6, 30),
            ["operating_income", "depreciation_amortization"],
        )
    ]

    assert missing_component_notes(rows) == [
        "Merck's EBITDA is missing: no standalone quarterly operating income or "
        "depreciation and amortization was found in its filings, which EBITDA needs."
    ]


def test_a_formula_missing_in_some_quarters_names_them() -> None:
    shown = TableRow(
        company_name="Advanced Micro Devices, Inc.",
        ticker="AMD",
        cik=_CIKS["AMD"],
        metric="ebitda",
        value="1000",
        end_date=date(2026, 6, 27),
    )
    rows = [
        shown,
        _missing_row(
            "Advanced Micro Devices, Inc.", "AMD", date(2026, 3, 28), ["depreciation_amortization"]
        ),
        _missing_row(
            "Advanced Micro Devices, Inc.", "AMD", date(2025, 12, 27), ["depreciation_amortization"]
        ),
    ]

    assert missing_component_notes(rows) == [
        "Advanced Micro Devices' EBITDA is missing for Mar 28, 2026 and Dec 27, 2025: no "
        "standalone quarterly depreciation and amortization was found for those quarters, "
        "which EBITDA needs."
    ]


def test_a_plain_missing_fact_gets_no_component_note() -> None:
    row = _missing_row("Apple Inc.", "AAPL", date(2026, 6, 27), [], "revenue")

    assert missing_component_notes([row]) == []


def test_companies_missing_the_same_component_share_one_note() -> None:
    rows = [
        _missing_row(
            "Advanced Micro Devices, Inc.", "AMD", date(2026, 6, 27), ["depreciation_amortization"]
        ),
        _missing_row("Intel Corporation", "INTC", date(2026, 6, 27), ["depreciation_amortization"]),
    ]

    assert missing_component_notes(rows) == [
        "EBITDA is missing for Advanced Micro Devices and Intel: no standalone quarterly "
        "depreciation and amortization was found in their filings, which EBITDA needs."
    ]


def test_a_newest_quarter_sec_lacks_is_explained_once() -> None:
    # SEC's structured data lacks Abbott's newest 10-Q; the newer-filing banner
    # already says so, and a note about the formula's parts would contradict it.
    shown = TableRow(
        company_name="Abbott Laboratories",
        ticker="ABT",
        cik="0000001800",
        metric="gross_margin",
        value="0.56",
        end_date=date(2026, 3, 31),
        newer_filing_end=date(2026, 6, 30),
    )
    pending = TableRow(
        company_name="Abbott Laboratories",
        ticker="ABT",
        cik="0000001800",
        metric="gross_margin",
        reason="missing_fact",
        end_date=date(2026, 6, 30),
        missing_components=["gross_profit", "revenue"],
    )

    assert missing_component_notes([pending, shown]) == []
