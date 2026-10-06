"""Google latest-quarter net income through run_turn."""

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from financial_analyst_agent.contracts import (
    ALLOWED_METRICS,
    Intent,
    RendererKind,
    Runtime,
    WorkflowPlan,
)
from financial_analyst_agent.domain.errors import AmbiguousFactError
from financial_analyst_agent.presentation import present_turn
from financial_analyst_agent.providers.sec.company_resolver import resolve_company
from financial_analyst_agent.ranking import SnapshotRanking
from financial_analyst_agent.runtime import (
    FIXTURE_UNIVERSE_SNAPSHOT_PATH,
    DemoCompleter,
    build_runtime,
    recorded_runtime,
)
from financial_analyst_agent.turn import run_turn
from helpers import FakeFacts

GOOGLE_LATEST_QUARTER_NET_INCOME_QUERY = (
    "What was Google's net income based on their latest quarterly report?"
)
UNKNOWN_METRIC_QUERY = "What was Google's ROA based on their latest quarterly report?"
UNKNOWN_COSTS_QUERY = "What was Google's costs based on their latest quarterly report?"
GOOGLE_GROSS_PROFIT_QUERY = "What was Google's gross profit based on their latest quarterly report?"
GOOGLE_OPERATING_MARGIN_QUERY = (
    "What was Google's operating margin based on their latest quarterly report?"
)
SHOPIFY_NET_MARGIN_QUERY = "Shopify net margin"
SHOPIFY_RD_TO_SALES_QUERY = "Shopify R&D to sales"
UNRELATED_QUERY = "What is the weather in Atlanta?"
EXXONMOBIL_NET_INCOME_QUERY = (
    "What was ExxonMobil's net income based on their latest quarterly report?"
)
XOM_NET_INCOME_QUERY = "What was XOM's net income based on their latest quarterly report?"
EXXON_NET_INCOME_QUERY = "What was Exxon's net income based on their latest quarterly report?"
APPL_NET_INCOME_QUERY = "What was Appl's net income based on their latest quarterly report?"
SUCCESSOR_TICKERS = {
    "0": {"cik_str": 2115436, "ticker": "XOM", "title": "ExxonMobil Holdings Corp"},
    "1": {"cik_str": 2014337, "ticker": "NPT", "title": "Texxon Holding Ltd"},
    "2": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."},
    "3": {"cik_str": 1418121, "ticker": "APLE", "title": "Apple Hospitality REIT, Inc."},
}

# Closed catalog from the PRD: reported facts plus allowed formulas.

# Expected figures on the recorded runtime (recorded Alphabet quarterly fact, not live SEC).
ALPHABET_CIK = "0001652044"
ALPHABET_NAME = "Alphabet Inc."
ALPHABET_TICKER = "GOOG"
NET_INCOME = Decimal("112193000000")
PERIOD_START = date(2026, 4, 1)
PERIOD_END = date(2026, 6, 30)
FORM = "10-Q"
ACCESSION = "0001652044-26-000071"
TAXONOMY = "us-gaap"
CONCEPT = "NetIncomeLoss"
SOURCE_URL = "https://www.sec.gov/Archives/edgar/data/1652044/000165204426000071/goog-20260630.htm"


class _FakeCompleter:
    def complete(self, query: str, current_spec: object = None) -> WorkflowPlan:
        if query != GOOGLE_LATEST_QUARTER_NET_INCOME_QUERY:
            raise AssertionError(f"unexpected query: {query!r}")
        return WorkflowPlan(intent=Intent.LOOKUP, company="Google", metric="net_income")


class _FixtureFacts(FakeFacts):
    def get_financials(
        self, company: str, metric: str, *, report_date: date | None = None
    ) -> SimpleNamespace:
        if company != "Google" or metric != "net_income":
            raise AssertionError(f"unexpected get_financials({company!r}, {metric!r})")
        return SimpleNamespace(
            company_name=ALPHABET_NAME,
            ticker=ALPHABET_TICKER,
            cik=ALPHABET_CIK,
            metric="net_income",
            value=NET_INCOME,
            currency="USD",
            start_date=PERIOD_START,
            end_date=PERIOD_END,
            filed_date=PERIOD_END,
            form=FORM,
            accession_number=ACCESSION,
            taxonomy=TAXONOMY,
            concept=CONCEPT,
            source_url=SOURCE_URL,
            source="sec_xbrl",
        )


class _UnknownMetricCompleter:
    def complete(self, query: str, current_spec: object = None) -> WorkflowPlan:
        if query != UNKNOWN_METRIC_QUERY:
            raise AssertionError(f"unexpected query: {query!r}")
        return WorkflowPlan(intent=Intent.LOOKUP, company="Google", metric="roa")


class _ShopifyNetMarginCompleter:
    def complete(self, query: str, current_spec: object = None) -> WorkflowPlan:
        if query != SHOPIFY_NET_MARGIN_QUERY:
            raise AssertionError(f"unexpected query: {query!r}")
        return WorkflowPlan(intent=Intent.LOOKUP, company="Shopify", metric="net_margin")


class _ShopifyRdToSalesCompleter:
    def complete(self, query: str, current_spec: object = None) -> WorkflowPlan:
        if query != SHOPIFY_RD_TO_SALES_QUERY:
            raise AssertionError(f"unexpected query: {query!r}")
        return WorkflowPlan(intent=Intent.LOOKUP, company="Shopify", metric="rd_to_sales")


class _ComponentFacts(FakeFacts):
    def __init__(self, company: str, values: dict[str, Decimal]) -> None:
        self._company = company
        self._values = values

    def get_financials(

        self, company: str, metric: str, *, report_date: date | None = None

    ) -> SimpleNamespace:
        if company != self._company or metric not in self._values:
            raise AssertionError(f"unexpected get_financials({company!r}, {metric!r})")
        return SimpleNamespace(
            company_name=company,
            ticker="SHOP",
            cik="0001594805",
            metric=metric,
            value=self._values[metric],
            currency="USD",
            start_date=PERIOD_START,
            end_date=PERIOD_END,
            filed_date=PERIOD_END,
            form=FORM,
            accession_number="0001594805-26-000012",
            taxonomy=TAXONOMY,
            concept=metric,
            source_url="https://www.sec.gov/Archives/edgar/data/1594805/shop.htm",
            source="sec_xbrl",
        )


class _ExplodingFacts(FakeFacts):
    def get_financials(
        self, company: str, metric: str, *, report_date: date | None = None
    ) -> SimpleNamespace:
        raise AssertionError("get_financials must not invent a number for an unknown metric")


class _SuccessorFacts(FakeFacts):
    def get_financials(
        self, company: str, metric: str, *, report_date: date | None = None
    ) -> SimpleNamespace:
        resolved = resolve_company(company, SUCCESSOR_TICKERS)
        return SimpleNamespace(
            company_name=resolved.name,
            ticker=resolved.tickers[0],
            cik=resolved.cik,
            metric=metric,
            value=Decimal("14525000000"),
            currency="USD",
            start_date=PERIOD_START,
            end_date=PERIOD_END,
            filed_date=PERIOD_END,
            form=FORM,
            accession_number="0000034088-26-000093",
            taxonomy=TAXONOMY,
            concept=CONCEPT,
            source_url=(
                "https://www.sec.gov/Archives/edgar/data/2115436/"
                "000003408826000093/xom-20260630.htm"
            ),
        )


def test_run_turn_returns_lookup_table_for_google_latest_quarter_net_income() -> None:
    result = run_turn(
        GOOGLE_LATEST_QUARTER_NET_INCOME_QUERY,
        Runtime(completer=_FakeCompleter(), facts=_FixtureFacts()),
    )

    assert result.intent is Intent.LOOKUP
    assert result.renderer is RendererKind.TABLE
    assert result.banners == []
    assert result.numeral_lock_extras == []

    assert len(result.tool_traces) == 1
    trace = result.tool_traces[0]
    assert trace.tool == "get_financials"
    assert trace.args == {"company": "Google", "metric": "net_income"}
    assert trace.provenance["accession_number"] == ACCESSION
    assert trace.provenance["concept"] == CONCEPT
    assert trace.provenance["form"] == FORM
    assert trace.provenance["taxonomy"] == TAXONOMY
    assert trace.provenance["source"] == "sec_xbrl"
    assert trace.provenance["source_url"] == SOURCE_URL
    assert trace.provenance["start_date"] == PERIOD_START.isoformat()
    assert trace.provenance["end_date"] == PERIOD_END.isoformat()

    assert len(result.table_rows) == 1
    row = result.table_rows[0]
    assert row.company_name == ALPHABET_NAME
    assert row.ticker == ALPHABET_TICKER
    assert row.cik == ALPHABET_CIK
    assert row.metric == "net_income"
    assert row.value == NET_INCOME
    assert row.start_date == PERIOD_START
    assert row.end_date == PERIOD_END
    assert row.form == FORM
    assert row.accession_number == ACCESSION
    assert row.taxonomy == TAXONOMY
    assert row.concept == CONCEPT
    assert row.source_url == SOURCE_URL


def test_run_turn_resolves_google_and_selects_standalone_quarter() -> None:
    result = run_turn(GOOGLE_LATEST_QUARTER_NET_INCOME_QUERY, recorded_runtime())

    assert result.intent is Intent.LOOKUP
    assert result.renderer is RendererKind.TABLE
    row = result.table_rows[0]
    assert row.company_name == ALPHABET_NAME
    assert row.cik == ALPHABET_CIK
    assert row.ticker == ALPHABET_TICKER
    assert row.value == NET_INCOME
    assert row.start_date == PERIOD_START
    assert row.end_date == PERIOD_END
    assert row.accession_number == ACCESSION
    assert row.concept == CONCEPT
    assert row.source_url == SOURCE_URL


def test_build_runtime_fixture_mode_uses_recorded_facts() -> None:
    result = run_turn(GOOGLE_LATEST_QUARTER_NET_INCOME_QUERY, build_runtime())
    assert result.intent is Intent.LOOKUP
    assert result.table_rows[0].company_name == ALPHABET_NAME
    assert result.table_rows[0].value == NET_INCOME
    assert result.table_rows[0].accession_number == ACCESSION


def test_run_turn_refuses_unknown_metric_with_allowed_list() -> None:
    result = run_turn(
        UNKNOWN_METRIC_QUERY,
        Runtime(completer=_UnknownMetricCompleter(), facts=_ExplodingFacts()),
    )

    assert result.intent is Intent.LOOKUP
    assert result.renderer is RendererKind.REFUSE
    assert result.table_rows == []
    assert result.tool_traces == []
    assert result.numeral_lock_extras == []
    assert result.message is not None
    assert result.message.startswith("I can't look up return on assets yet.")


def test_recorded_runtime_refuses_unknown_costs_without_inventing_net_income() -> None:
    result = run_turn(UNKNOWN_COSTS_QUERY, recorded_runtime())
    assert result.renderer is RendererKind.REFUSE
    assert result.table_rows == []
    assert result.message is not None
    assert "costs" in result.message.casefold()
    for metric in ALLOWED_METRICS:
        assert metric in result.message


def test_run_turn_lookup_computes_shopify_net_margin() -> None:
    net_income = Decimal("100000000")
    revenue = Decimal("1000000000")
    result = run_turn(
        SHOPIFY_NET_MARGIN_QUERY,
        Runtime(
            completer=_ShopifyNetMarginCompleter(),
            facts=_ComponentFacts("Shopify", {"net_income": net_income, "revenue": revenue}),
        ),
    )

    assert result.intent is Intent.LOOKUP
    assert result.renderer is RendererKind.TABLE
    assert result.message is None
    assert len(result.table_rows) == 1
    row = result.table_rows[0]
    assert row.company_name == "Shopify"
    assert row.metric == "net_margin"
    assert row.value == net_income / revenue
    assert row.start_date == PERIOD_START
    assert row.end_date == PERIOD_END
    components = {component.metric: component for component in row.components}
    assert set(components) == {"net_income", "revenue"}
    assert components["net_income"].value == net_income
    assert components["revenue"].value == revenue
    assert len(result.tool_traces) == 1
    trace = result.tool_traces[0]
    assert trace.tool == "compare_metrics"
    assert trace.args == {"issuers": ["Shopify"], "metric": "net_margin"}
    provenance_components = {item["metric"]: item for item in trace.provenance["components"]}
    assert provenance_components["net_income"]["value"] == str(net_income)
    assert provenance_components["revenue"]["value"] == str(revenue)
    assert provenance_components["net_income"]["form"] == FORM
    assert provenance_components["net_income"]["taxonomy"] == TAXONOMY
    assert provenance_components["net_income"]["source"] == "sec_xbrl"


def test_run_turn_lookup_computes_shopify_rd_to_sales() -> None:
    research = Decimal("120000000")
    revenue = Decimal("1000000000")
    result = run_turn(
        SHOPIFY_RD_TO_SALES_QUERY,
        Runtime(
            completer=_ShopifyRdToSalesCompleter(),
            facts=_ComponentFacts(
                "Shopify",
                {"research_and_development": research, "revenue": revenue},
            ),
        ),
    )

    assert result.intent is Intent.LOOKUP
    assert result.renderer is RendererKind.TABLE
    row = result.table_rows[0]
    assert row.metric == "rd_to_sales"
    assert row.value == research / revenue
    components = {component.metric: component for component in row.components}
    assert set(components) == {"research_and_development", "revenue"}
    assert result.tool_traces[0].args == {"issuers": ["Shopify"], "metric": "rd_to_sales"}


def test_recorded_runtime_does_not_invent_net_income_for_unrelated_query() -> None:
    result = run_turn(UNRELATED_QUERY, recorded_runtime())
    assert result.renderer is RendererKind.REFUSE
    assert result.table_rows == []
    assert all(row.value != NET_INCOME for row in result.table_rows)


def test_recorded_runtime_derives_gross_profit_when_no_line_is_tagged() -> None:
    # Alphabet tags revenue and cost of revenue but no gross profit line.
    result = run_turn(GOOGLE_GROSS_PROFIT_QUERY, recorded_runtime())
    assert result.renderer is RendererKind.TABLE
    row = result.table_rows[0]
    assert row.metric == "gross_profit"
    assert row.derivation == "Revenue minus cost of revenue"
    revenue, cost = row.derived_from
    assert row.value == revenue.value - cost.value


def test_recorded_runtime_lookup_computes_operating_margin() -> None:
    result = run_turn(GOOGLE_OPERATING_MARGIN_QUERY, recorded_runtime())
    assert result.intent is Intent.LOOKUP
    assert result.renderer is RendererKind.TABLE
    assert result.message is None
    row = result.table_rows[0]
    assert row.metric == "operating_margin"
    assert row.value is not None
    assert row.components


def _assert_successor_lookup(query: str) -> None:
    result = run_turn(
        query,
        Runtime(completer=DemoCompleter(), facts=_SuccessorFacts()),
    )
    assert result.intent is Intent.LOOKUP
    assert result.renderer is RendererKind.TABLE
    row = result.table_rows[0]
    assert row.cik == "0002115436"
    assert row.ticker == "XOM"
    assert row.company_name == "ExxonMobil Holdings Corp"
    assert row.value == Decimal("14525000000")
    assert result.tool_traces[0].args["metric"] == "net_income"


def test_run_turn_lookup_resolves_exxonmobil_successor_name() -> None:
    _assert_successor_lookup(EXXONMOBIL_NET_INCOME_QUERY)


def test_run_turn_lookup_resolves_xom_ticker() -> None:
    _assert_successor_lookup(XOM_NET_INCOME_QUERY)


def test_run_turn_lookup_resolves_exxon_prefix() -> None:
    _assert_successor_lookup(EXXON_NET_INCOME_QUERY)


def test_run_turn_refuses_conflicting_catalog_concepts() -> None:
    class _AmbiguousFacts(FakeFacts):
        def get_financials(
            self, company: str, metric: str, *, report_date: date | None = None
        ) -> SimpleNamespace:
            raise AmbiguousFactError(
                "Supported concepts produced conflicting quarterly values",
                details={"metric": metric, "concepts": ["NetIncomeLoss", "ProfitLoss"]},
            )

    result = run_turn(
        XOM_NET_INCOME_QUERY,
        Runtime(completer=DemoCompleter(), facts=_AmbiguousFacts()),
    )

    assert result.intent is Intent.LOOKUP
    assert result.renderer is RendererKind.REFUSE
    assert result.table_rows == []
    # The refusal still shows the lookup it tried and why it stopped.
    [trace] = result.tool_traces
    assert trace.tool == "get_financials"
    assert trace.provenance["error"]["code"] == "ambiguous_fact"
    assert result.message is not None
    assert "conflicting" in result.message.casefold()


def test_run_turn_refuses_ambiguous_company_prefix() -> None:
    result = run_turn(
        APPL_NET_INCOME_QUERY,
        Runtime(completer=DemoCompleter(), facts=_SuccessorFacts()),
    )

    assert result.intent is Intent.LOOKUP
    assert result.renderer is RendererKind.REFUSE
    assert result.table_rows == []
    # The refusal still shows the lookup it tried and why it stopped.
    [trace] = result.tool_traces
    assert trace.tool == "get_financials"
    assert trace.provenance["error"]["code"] == "ambiguous_company"
    assert result.message is not None
    assert "appl" in result.message.casefold() or "multiple" in result.message.casefold()


GOOGLE_MARKET_CAP_QUERY = "What was Google's market cap?"
SHOPIFY_MARKET_CAP_QUERY = "What was Shopify's market cap?"


def test_snapshot_banner_keeps_a_corrected_company_note_before_it() -> None:
    answer = present_turn(run_turn("Aple market cap", recorded_runtime()))

    assert answer.banners[0].startswith("Showing Apple for")
    assert answer.banners[1].startswith("Universe snapshot as of")
ALPHABET_SNAPSHOT_MARKET_CAP = Decimal("4139313608328")
SNAPSHOT_AS_OF = "2026-09-27T22:43:45.015184+00:00"


class _ShopifyMarketCapCompleter:
    def complete(self, query: str, current_spec: object = None) -> WorkflowPlan:
        if query != SHOPIFY_MARKET_CAP_QUERY:
            raise AssertionError(f"unexpected query: {query!r}")
        return WorkflowPlan(intent=Intent.LOOKUP, company="Shopify", metric="market_cap")


class _NoFacts(FakeFacts):
    def get_financials(
        self, company: str, metric: str, *, report_date: date | None = None
    ) -> SimpleNamespace:
        raise AssertionError("snapshot metrics must not call get_financials")


def test_run_turn_lookup_google_market_cap_from_snapshot() -> None:
    result = run_turn(GOOGLE_MARKET_CAP_QUERY, recorded_runtime())

    assert result.intent is Intent.LOOKUP
    assert result.renderer is RendererKind.TABLE
    assert result.snapshot_as_of == SNAPSHOT_AS_OF
    assert len(result.table_rows) == 1
    row = result.table_rows[0]
    assert row.company_name == ALPHABET_NAME
    assert row.ticker == ALPHABET_TICKER
    assert row.cik == ALPHABET_CIK
    assert row.metric == "market_cap"
    assert row.value == ALPHABET_SNAPSHOT_MARKET_CAP
    assert row.currency == "USD"
    assert row.start_date is None
    assert row.form is None
    assert result.tool_traces[0].tool == "compare_metrics"
    assert result.tool_traces[0].args == {"issuers": [ALPHABET_CIK], "metric": "market_cap"}
    assert result.tool_traces[0].provenance["snapshot_as_of"] == SNAPSHOT_AS_OF


def test_run_turn_lookup_market_cap_refuses_when_not_in_snapshot() -> None:
    result = run_turn(
        SHOPIFY_MARKET_CAP_QUERY,
        Runtime(
            completer=_ShopifyMarketCapCompleter(),
            facts=_NoFacts(),
            ranking=SnapshotRanking.from_path(FIXTURE_UNIVERSE_SNAPSHOT_PATH),
        ),
    )

    assert result.intent is Intent.LOOKUP
    assert result.renderer is RendererKind.REFUSE
    assert result.table_rows == []
    assert result.tool_traces == []
    assert result.message is not None
    assert "shopify" in result.message.casefold()


CISCO_EPS_QUERY = "What are Cisco's earnings per share?"


def test_recorded_runtime_shows_the_latest_quarter_with_its_own_eps() -> None:
    # Cisco's latest report is its 10-K, whose fourth quarter reports EPS only for
    # the year, and per-share figures are never derived (ADR 0007). With no period
    # named, the answer is the latest quarter with its own, and a note says so.
    result = run_turn(CISCO_EPS_QUERY, recorded_runtime())

    assert result.renderer is RendererKind.TABLE
    (row,) = result.table_rows
    assert row.ticker == "CSCO"
    assert row.value == Decimal("0.85")
    assert row.end_date == date(2026, 4, 25)
    assert row.year_only_quarter_end == date(2026, 7, 25)
    presented = present_turn(result)
    assert presented.fact_card is not None
    assert presented.fact_card.amount == "$0.85"
    assert (
        "Cisco Systems' quarter ended Jul 25, 2026 reports diluted EPS only for the year, "
        "so Cisco Systems is shown for the quarter ended Apr 25, 2026, the latest with "
        "its own."
    ) in presented.banners


def test_recorded_runtime_eps_for_a_latest_quarter_with_its_own_has_no_note() -> None:
    result = run_turn("Apple EPS", recorded_runtime())

    (row,) = result.table_rows
    assert row.year_only_quarter_end is None
    assert not any("the latest with its own" in banner for banner in present_turn(result).banners)
