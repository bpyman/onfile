"""Conversation seam: multi-period windows and across-period comparison (ticket 11).

Asserts period windows and sequential/YoY change at the public conversation entry.
Does not assert graph internals. Uses a real temporary store.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

from financial_analyst_agent.domain.errors import UnsupportedQuarterlyFactError
from financial_analyst_agent.runtime import FIXTURE_UNIVERSE_SNAPSHOT_PATH
from financial_analyst_agent.services.fiscal_periods import FiscalPeriod
from helpers import ListedFilings, named_by_cik

# Resolved companies are asked for by CIK; these fakes answer by name.
_NAMED = named_by_cik('Microsoft', 'Google')

Q1 = date(2025, 3, 31)
Q2 = date(2025, 6, 30)
Q3 = date(2025, 9, 30)
Q4 = date(2025, 12, 31)
Q1_PRIOR = date(2024, 3, 31)

FOUR_QUARTERS = (Q4, Q3, Q2, Q1)  # newest first
FIVE_QUARTERS = (Q4, Q3, Q2, Q1, Q1_PRIOR)


class _PeriodFacts(ListedFilings):
    """Per-(company, metric, report_date) facts; one cell can be missing.

    Microsoft and Google file four calendar quarters unless ``dates_by_company``
    says otherwise.
    """

    def __init__(
        self,
        values: dict[tuple[str, str, date], Decimal],
        *,
        missing: set[tuple[str, str, date]] | None = None,
        dates_by_company: dict[str, tuple[date, ...]] | None = None,
    ) -> None:
        super().__init__(
            {"Microsoft": FOUR_QUARTERS, "Google": FOUR_QUARTERS, **(dates_by_company or {})}
        )
        self.values = values
        self.missing = missing or set()
        self.calls: list[tuple[str, str, date | None]] = []

    def list_quarterly_report_dates(self, company: str, *, limit: int) -> tuple[date, ...]:
        return super().list_quarterly_report_dates(_NAMED(company), limit=limit)

    def fiscal_periods(self, company: str) -> tuple[FiscalPeriod, ...]:
        return super().fiscal_periods(_NAMED(company))

    def get_financials(
        self, company: str, metric: str, *, report_date: date | None = None
    ) -> SimpleNamespace:
        company = _NAMED(company)
        self.calls.append((company, metric, report_date))
        if report_date is None:
            report_date = self.quarters[company][0]
        if (company, metric, report_date) in self.missing:
            raise UnsupportedQuarterlyFactError(
                f"no standalone quarter for {company} {metric} {report_date.isoformat()}"
            )
        value = self.values[(company, metric, report_date)]
        start = (
            date(report_date.year, report_date.month - 2, 1)
            if report_date.month > 2
            else date(report_date.year - 1, 10, 1)
        )
        return SimpleNamespace(
            company_name=company,
            ticker="MSFT" if company == "Microsoft" else "GOOG",
            cik="0000789019" if company == "Microsoft" else "0001652044",
            metric=metric,
            value=value,
            currency="USD",
            start_date=start,
            end_date=report_date,
            filed_date=report_date,
            form="10-Q",
            accession_number=f"acc-{report_date.isoformat()}",
            taxonomy="us-gaap",
            concept=metric,
            source_url="https://www.sec.gov/example.htm",
            source="sec_xbrl",
        )


def _msft_revenue_four() -> dict[tuple[str, str, date], Decimal]:
    return {
        ("Microsoft", "revenue", Q4): Decimal("400"),
        ("Microsoft", "revenue", Q3): Decimal("300"),
        ("Microsoft", "revenue", Q2): Decimal("200"),
        ("Microsoft", "revenue", Q1): Decimal("100"),
        ("Microsoft", "operating_income", Q4): Decimal("80"),
        ("Microsoft", "operating_income", Q3): Decimal("60"),
        ("Microsoft", "operating_income", Q2): Decimal("40"),
        ("Microsoft", "operating_income", Q1): Decimal("20"),
    }


def _msft_revenue_five() -> dict[tuple[str, str, date], Decimal]:
    values = _msft_revenue_four()
    values[("Microsoft", "revenue", Q1_PRIOR)] = Decimal("90")
    return values


def _runtime(*, completer: object, facts: object):
    from financial_analyst_agent.contracts import Runtime
    from financial_analyst_agent.ranking import SnapshotRanking

    return Runtime(
        completer=completer,  # type: ignore[arg-type]
        facts=facts,  # type: ignore[arg-type]
        ranking=SnapshotRanking.from_path(FIXTURE_UNIVERSE_SNAPSHOT_PATH),
    )


def test_period_window_reruns_metrics_across_quarters(tmp_path: Path) -> None:
    from financial_analyst_agent.contracts import Intent, RendererKind
    from financial_analyst_agent.conversation import run_conversation_turn
    from financial_analyst_agent.graph.analysis_spec import PeriodSelection, SpecPatch
    from financial_analyst_agent.thread_store import LocalThreadStore

    class _FourQuarterLookup:
        def complete(self, query: str, current_spec: object = None) -> SpecPatch:
            return SpecPatch(
                mode="replace",
                add_companies=("Microsoft",),
                add_metrics=("revenue",),
                set_periods=PeriodSelection(
                    kind="last_n_quarters",
                    count=4,
                    report_dates=FOUR_QUARTERS,
                ),
            )

    facts = _PeriodFacts(_msft_revenue_four())
    store = LocalThreadStore(tmp_path)
    turn = run_conversation_turn(
        "t1",
        "Microsoft revenue for the last four quarters",
        _runtime(completer=_FourQuarterLookup(), facts=facts),
        store=store,
    )

    assert turn.result.intent is Intent.LOOKUP
    assert turn.result.renderer is RendererKind.TABLE
    assert turn.analysis_spec is not None
    assert turn.analysis_spec.periods.kind == "last_n_quarters"
    assert turn.analysis_spec.periods.count == 4
    assert turn.analysis_spec.metrics == ("revenue",)

    by_end = {row.end_date: row for row in turn.result.table_rows}
    assert set(by_end) == set(FOUR_QUARTERS)
    assert by_end[Q4].value == Decimal("400")
    assert by_end[Q3].value == Decimal("300")
    assert by_end[Q2].value == Decimal("200")
    assert by_end[Q1].value == Decimal("100")
    assert by_end[Q4].accession_number == "acc-2025-12-31"
    assert all(row.reason is None for row in turn.result.table_rows)


def test_period_materialization_refusal_keeps_provider_error_details(tmp_path: Path) -> None:
    from financial_analyst_agent.contracts import RendererKind
    from financial_analyst_agent.conversation import run_conversation_turn
    from financial_analyst_agent.domain.errors import ProviderError
    from financial_analyst_agent.graph.analysis_spec import PeriodSelection, SpecPatch
    from financial_analyst_agent.thread_store import LocalThreadStore

    class _Window:
        def complete(self, query: str, current_spec: object = None) -> SpecPatch:
            return SpecPatch(
                mode="replace",
                add_companies=("Microsoft",),
                add_metrics=("revenue",),
                set_periods=PeriodSelection(kind="last_n_quarters", count=4),
            )

    class _Unavailable(_PeriodFacts):
        def list_quarterly_report_dates(
            self, company: str, *, limit: int
        ) -> tuple[date, ...]:
            raise ProviderError("SEC timed out", details={"status_code": 503})

    turn = run_conversation_turn(
        "t1",
        "Microsoft revenue for the last four quarters",
        _runtime(completer=_Window(), facts=_Unavailable({})),
        store=LocalThreadStore(tmp_path),
    )

    assert turn.result.renderer is RendererKind.REFUSE
    assert turn.result.refusal is not None
    assert turn.result.refusal.model_dump() == {
        "code": "provider_error",
        "details": {"status_code": 503},
    }


def test_change_window_keeps_companies_metrics_operations(tmp_path: Path) -> None:
    from financial_analyst_agent.conversation import run_conversation_turn
    from financial_analyst_agent.graph.analysis_spec import PeriodSelection, SpecPatch
    from financial_analyst_agent.thread_store import LocalThreadStore

    class _Initial:
        def complete(self, query: str, current_spec: object = None) -> SpecPatch:
            return SpecPatch(
                mode="replace",
                add_companies=("Microsoft",),
                add_metrics=("revenue",),
                set_periods=PeriodSelection(
                    kind="last_n_quarters",
                    count=2,
                    report_dates=(Q4, Q3),
                ),
            )

    class _Widen:
        def complete(self, query: str, current_spec: object = None) -> SpecPatch:
            return SpecPatch(
                mode="extend",
                set_periods=PeriodSelection(
                    kind="last_n_quarters",
                    count=4,
                    report_dates=FOUR_QUARTERS,
                ),
            )

    facts = _PeriodFacts(_msft_revenue_four())
    store = LocalThreadStore(tmp_path)
    run_conversation_turn(
        "t1",
        "Microsoft revenue last two quarters",
        _runtime(completer=_Initial(), facts=facts),
        store=store,
    )
    turn = run_conversation_turn(
        "t1",
        "make that the last four quarters",
        _runtime(completer=_Widen(), facts=facts),
        store=store,
    )

    assert turn.analysis_spec is not None
    assert [c.query for c in turn.analysis_spec.companies] == ["Microsoft"]
    assert turn.analysis_spec.metrics == ("revenue",)
    assert turn.analysis_spec.periods.count == 4
    assert {row.end_date for row in turn.result.table_rows} == set(FOUR_QUARTERS)


def test_across_periods_sequential_and_yoy(tmp_path: Path) -> None:
    from financial_analyst_agent.contracts import RendererKind
    from financial_analyst_agent.conversation import run_conversation_turn
    from financial_analyst_agent.graph.analysis_spec import PeriodSelection, SpecPatch
    from financial_analyst_agent.thread_store import LocalThreadStore

    class _Across:
        def complete(self, query: str, current_spec: object = None) -> SpecPatch:
            return SpecPatch(
                mode="replace",
                add_companies=("Microsoft",),
                add_metrics=("revenue",),
                set_periods=PeriodSelection(
                    kind="last_n_quarters",
                    count=5,
                    report_dates=FIVE_QUARTERS,
                ),
                add_operations=("across_periods",),
            )

    facts = _PeriodFacts(_msft_revenue_five(), dates_by_company={"Microsoft": FIVE_QUARTERS})
    store = LocalThreadStore(tmp_path)
    turn = run_conversation_turn(
        "t1",
        "Microsoft revenue last five quarters with sequential and year over year change",
        _runtime(completer=_Across(), facts=facts),
        store=store,
    )

    assert turn.result.renderer is RendererKind.TABLE
    levels = [r for r in turn.result.table_rows if r.comparison is None]
    sequential = [r for r in turn.result.table_rows if r.comparison == "sequential"]
    yoy = [r for r in turn.result.table_rows if r.comparison == "year_over_year"]

    assert len(levels) == 5
    assert {r.end_date for r in levels} == set(FIVE_QUARTERS)

    # Newest-first: Q4 vs Q3 sequential = 400 - 300
    seq_q4 = next(r for r in sequential if r.end_date == Q4)
    assert seq_q4.value == Decimal("100")
    assert seq_q4.metric == "revenue"
    assert len(seq_q4.components) == 2

    # YoY: Q4 2025 vs Q1_PRIOR is wrong; Q4 vs same quarter prior year.
    # With FIVE_QUARTERS newest-first, index 0 (Q4) vs index 4 (Q1_PRIOR) is not YoY.
    # YoY partner of Q4 is absent; partner of Q1 (index 3) is Q1_PRIOR (index 4).
    yoy_q1 = next(r for r in yoy if r.end_date == Q1)
    assert yoy_q1.value == Decimal("100") - Decimal("90")
    assert yoy_q1.metric == "revenue"


def test_across_companies_for_named_period_still_works(tmp_path: Path) -> None:
    from financial_analyst_agent.contracts import Intent, RendererKind
    from financial_analyst_agent.conversation import run_conversation_turn
    from financial_analyst_agent.graph.analysis_spec import PeriodSelection, SpecPatch
    from financial_analyst_agent.thread_store import LocalThreadStore

    values = {
        ("Microsoft", "revenue", Q2): Decimal("200"),
        ("Google", "revenue", Q2): Decimal("150"),
    }

    class _CompareOnePeriod:
        def complete(self, query: str, current_spec: object = None) -> SpecPatch:
            return SpecPatch(
                mode="replace",
                add_companies=("Microsoft", "Google"),
                add_metrics=("revenue",),
                set_periods=PeriodSelection(
                    kind="last_n_quarters",
                    count=1,
                    report_dates=(Q2,),
                ),
                add_operations=("across_companies",),
            )

    facts = _PeriodFacts(values, dates_by_company={"Microsoft": (Q2,), "Google": (Q2,)})
    store = LocalThreadStore(tmp_path)
    turn = run_conversation_turn(
        "t1",
        "compare Microsoft and Google revenue for Q2 2025",
        _runtime(completer=_CompareOnePeriod(), facts=facts),
        store=store,
    )

    assert turn.result.intent is Intent.COMPARE
    assert turn.result.renderer is RendererKind.TABLE
    by_ticker = {row.ticker: row for row in turn.result.table_rows}
    assert by_ticker["MSFT"].value == Decimal("200")
    assert by_ticker["GOOG"].value == Decimal("150")
    assert by_ticker["MSFT"].end_date == Q2
    assert by_ticker["GOOG"].end_date == Q2


def test_mismatched_periods_and_zero_denominator_do_not_compute(tmp_path: Path) -> None:
    from financial_analyst_agent.contracts import PERIOD_MISMATCH, ZERO_DENOMINATOR, RendererKind
    from financial_analyst_agent.conversation import run_conversation_turn
    from financial_analyst_agent.graph.analysis_spec import PeriodSelection, SpecPatch
    from financial_analyst_agent.thread_store import LocalThreadStore

    values = {
        ("Microsoft", "operating_income", Q2): Decimal("40"),
        ("Microsoft", "revenue", Q2): Decimal("0"),
        ("Google", "operating_income", Q2): Decimal("50"),
        ("Google", "revenue", Q1): Decimal("200"),  # different period → mismatch path
    }

    class _Facts(ListedFilings):
        def __init__(self) -> None:
            super().__init__({"Microsoft": (Q2,), "Google": (Q2,)})

        def list_quarterly_report_dates(self, company: str, *, limit: int) -> tuple[date, ...]:
            return super().list_quarterly_report_dates(_NAMED(company), limit=limit)

        def get_financials(
            self, company: str, metric: str, *, report_date: date | None = None
        ) -> SimpleNamespace:
            company = _NAMED(company)
            target = report_date or Q2
            if company == "Google" and metric == "revenue":
                # Force component period mismatch for Google formula
                end = Q1
                start = date(2024, 12, 31)
            else:
                end = target
                start = date(2025, 4, 1)
            if company == "Google" and metric == "operating_income":
                end = Q2
                start = date(2025, 4, 1)
            if company == "Microsoft":
                value = values[(company, metric, Q2)]
            elif metric == "operating_income":
                value = values[("Google", "operating_income", Q2)]
            else:
                value = values[("Google", "revenue", Q1)]
            return SimpleNamespace(
                company_name=company,
                ticker="MSFT" if company == "Microsoft" else "GOOG",
                cik="0000789019" if company == "Microsoft" else "0001652044",
                metric=metric,
                value=value,
                currency="USD",
                start_date=start,
                end_date=end,
                filed_date=end,
                form="10-Q",
                accession_number="acc",
                taxonomy="us-gaap",
                concept=metric,
                source_url="https://www.sec.gov/example.htm",
                source="sec_xbrl",
            )

    class _CompareMargin:
        def complete(self, query: str, current_spec: object = None) -> SpecPatch:
            return SpecPatch(
                mode="replace",
                add_companies=("Microsoft", "Google"),
                add_metrics=("operating_margin",),
                set_periods=PeriodSelection(
                    kind="last_n_quarters",
                    count=1,
                    report_dates=(Q2,),
                ),
                add_operations=("across_companies",),
            )

    store = LocalThreadStore(tmp_path)
    turn = run_conversation_turn(
        "t1",
        "compare Microsoft and Google operating margin for Q2",
        _runtime(completer=_CompareMargin(), facts=_Facts()),
        store=store,
    )

    assert turn.result.renderer is RendererKind.TABLE
    by_ticker = {row.ticker: row for row in turn.result.table_rows}
    assert by_ticker["MSFT"].value is None
    assert by_ticker["MSFT"].reason == ZERO_DENOMINATOR
    assert by_ticker["GOOG"].value is None
    assert by_ticker["GOOG"].reason == PERIOD_MISMATCH


def test_window_with_missing_quarter_keeps_typed_gap(tmp_path: Path) -> None:
    from financial_analyst_agent.contracts import MISSING_FACT, RendererKind
    from financial_analyst_agent.conversation import run_conversation_turn
    from financial_analyst_agent.graph.analysis_spec import PeriodSelection, SpecPatch
    from financial_analyst_agent.thread_store import LocalThreadStore

    class _FourWithGap:
        def complete(self, query: str, current_spec: object = None) -> SpecPatch:
            return SpecPatch(
                mode="replace",
                add_companies=("Microsoft",),
                add_metrics=("revenue",),
                set_periods=PeriodSelection(
                    kind="last_n_quarters",
                    count=4,
                    report_dates=FOUR_QUARTERS,
                ),
            )

    facts = _PeriodFacts(
        _msft_revenue_four(),
        missing={("Microsoft", "revenue", Q2)},
    )
    store = LocalThreadStore(tmp_path)
    turn = run_conversation_turn(
        "t1",
        "Microsoft revenue last four quarters",
        _runtime(completer=_FourWithGap(), facts=facts),
        store=store,
    )

    assert turn.result.renderer is RendererKind.TABLE
    by_end = {row.end_date: row for row in turn.result.table_rows}
    assert by_end[Q4].value == Decimal("400")
    assert by_end[Q3].value == Decimal("300")
    assert by_end[Q1].value == Decimal("100")
    assert by_end[Q2].value is None
    assert by_end[Q2].reason == MISSING_FACT
    assert by_end[Q2].metric == "revenue"
