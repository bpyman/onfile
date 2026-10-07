"""Top 10 healthcare from the checked-in universe snapshot through run_turn."""

import json
from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from financial_analyst_agent.config import Settings
from financial_analyst_agent.contracts import Intent, RendererKind, Runtime, WorkflowPlan
from financial_analyst_agent.domain.errors import ProviderError
from financial_analyst_agent.facts import RecordedSECDataSource
from financial_analyst_agent.ranking import SnapshotRanking
from financial_analyst_agent.runtime import FIXTURE_UNIVERSE_SNAPSHOT_PATH, DemoCompleter
from financial_analyst_agent.sec_facts import SecFactLookup
from financial_analyst_agent.snapshot_builder import (
    companies_from_vendor_payloads,
    fetch_fmp_rows,
    main,
)
from financial_analyst_agent.turn import run_turn
from financial_analyst_agent.universe import (
    INELIGIBLE_ISSUER_CIKS,
    UniverseCompany,
    build_universe_snapshot,
    load_universe_snapshot,
)
from helpers import FakeFacts

HEALTHCARE_TOP_10_QUERY = "What are the top 10 companies in healthcare?"
FIXTURE_SNAPSHOT_PATH = FIXTURE_UNIVERSE_SNAPSHOT_PATH
SNAPSHOT_AS_OF = "2026-09-27T22:43:45.015184+00:00"


def _snapshot_rank_runtime() -> Runtime:
    return Runtime(
        completer=DemoCompleter(),
        facts=SecFactLookup(client=RecordedSECDataSource()),
        ranking=SnapshotRanking.from_path(FIXTURE_SNAPSHOT_PATH),
    )


def test_packaged_snapshot_is_vendor_universe_freeze() -> None:
    snapshot = load_universe_snapshot()
    healthcare = [company for company in snapshot.companies if company.sector == "Healthcare"]
    tickers = {company.ticker for company in snapshot.companies}
    names = [company.name.casefold() for company in snapshot.companies]
    assert snapshot.source == "fmp_universe_snapshot"
    assert len(snapshot.companies) > 19
    assert len(healthcare) > 11
    assert "EP-PC" not in tickers
    assert "SOMN" not in tickers
    assert "OXLCG" not in tickers
    assert "DMII" not in tickers
    assert "MU" in tickers
    assert "PNW" in tickers
    assert "BLK" in tickers
    freeze_ciks = {company.cik for company in snapshot.companies}
    assert not INELIGIBLE_ISSUER_CIKS & freeze_ciks
    industries = {company.industry.casefold() for company in snapshot.companies if company.industry}
    assert "shell companies" not in industries
    assert "financial - conglomerates" not in industries
    assert all("pfd cv tr secs" not in name for name in names)
    assert all("collateral tr" not in name for name in names)
    assert all("notes due" not in name for name in names)
    assert all("senior notes" not in name for name in names)
    southern = next(company for company in snapshot.companies if company.cik == "0000092122")
    assert southern.ticker == "SO"
    xom = next(company for company in snapshot.companies if company.ticker == "XOM")
    assert xom.cik == "0002115436"


# Expected figures on the recorded runtime (injected snapshot, not the live vendor freeze).
HEALTHCARE_TOP_10 = (
    ("Eli Lilly and Company", "LLY", "0000059478", Decimal("1114757656520")),
    ("Johnson & Johnson", "JNJ", "0000200406", Decimal("653612648388")),
    ("AbbVie Inc.", "ABBV", "0001551152", Decimal("467140021872")),
    ("Merck & Co., Inc.", "MRK", "0000310158", Decimal("367361026800")),
    ("UnitedHealth Group Incorporated", "UNH", "0000731766", Decimal("341998101102")),
    ("Thermo Fisher Scientific Inc.", "TMO", "0000097745", Decimal("249579418050")),
    ("Amgen Inc.", "AMGN", "0000318154", Decimal("223768333880")),
    ("Gilead Sciences, Inc.", "GILD", "0000882095", Decimal("187146431544")),
    ("Abbott Laboratories", "ABT", "0000001800", Decimal("175287835584")),
    ("Pfizer Inc.", "PFE", "0000078003", Decimal("163402944800")),
)


def test_run_turn_returns_rank_table_for_top_10_healthcare() -> None:
    result = run_turn(HEALTHCARE_TOP_10_QUERY, _snapshot_rank_runtime())

    assert result.intent is Intent.RANK
    assert result.renderer is RendererKind.TABLE
    assert result.model_dump()["snapshot_as_of"] == SNAPSHOT_AS_OF
    assert result.numeral_lock_extras == []
    assert result.message is None

    assert len(result.tool_traces) == 1
    trace = result.tool_traces[0]
    assert trace.tool == "rank_companies"
    assert trace.args == {"industry": "healthcare", "limit": 10}
    assert trace.provenance["snapshot_as_of"] == SNAPSHOT_AS_OF
    assert trace.provenance["source"] == "universe_snapshot"

    assert len(result.table_rows) == 10
    tickers = [row.ticker for row in result.table_rows]
    assert "DHR" not in tickers
    assert "XLV" not in tickers
    assert tickers.count("UNH") == 1
    for index, (name, ticker, cik, market_cap) in enumerate(HEALTHCARE_TOP_10, start=1):
        row = result.table_rows[index - 1]
        assert row.rank == index
        assert row.company_name == name
        assert row.ticker == ticker
        assert row.cik == cik
        assert row.metric == "market_cap"
        assert row.value == market_cap
        assert row.currency == "USD"
        assert row.reason is None


def test_run_turn_returns_rank_table_for_bare_top_10_healthcare() -> None:
    result = run_turn("top 10 healthcare", _snapshot_rank_runtime())

    assert result.intent is Intent.RANK
    assert result.renderer is RendererKind.TABLE
    assert result.tool_traces[0].args == {"industry": "healthcare", "limit": 10}
    assert [row.ticker for row in result.table_rows] == [
        ticker for _, ticker, _, _ in HEALTHCARE_TOP_10
    ]


UNKNOWN_INDUSTRY_QUERY = "What are the top 10 companies in AI?"
ALLOWED_INDUSTRIES = ("finance", "healthcare", "technology")


class _MissingIndustryCompleter:
    def __init__(self, intent: Intent) -> None:
        self._intent = intent

    def complete(self, query: str, current_spec: object = None) -> WorkflowPlan:
        return WorkflowPlan(
            intent=self._intent,
            industry=None,
            metric="net_income",
            limit=10,
        )


@pytest.mark.parametrize("intent", [Intent.RANK, Intent.RANK_AND_LOOKUP])
def test_run_turn_ranks_every_company_when_the_planner_names_no_industry(
    intent: Intent,
) -> None:
    # README, a ranking with no group: every company in the snapshot,
    # whichever planner left the group out.
    runtime = replace(_snapshot_rank_runtime(), completer=_MissingIndustryCompleter(intent))
    query = (
        "rank companies by net income"
        if intent is Intent.RANK_AND_LOOKUP
        else "rank companies"
    )

    result = run_turn(query, runtime)

    assert result.intent is intent
    assert result.renderer is not RendererKind.REFUSE
    assert result.tool_traces[0].args == {"industry": "companies", "limit": 10}


def test_run_turn_refuses_unknown_ai_industry_with_allowed_names() -> None:
    result = run_turn(UNKNOWN_INDUSTRY_QUERY, _snapshot_rank_runtime())

    assert result.intent is Intent.RANK
    assert result.renderer is RendererKind.REFUSE
    assert result.table_rows == []
    assert result.tool_traces == []
    assert result.numeral_lock_extras == []
    assert result.message is not None
    assert result.model_dump()["refusal"] == {
        "code": "unknown_industry",
        "details": {
            "industry": "ai",
            "allowed": [
                "Communication Services",
                "Financial Services",
                "Healthcare",
                "Technology",
                "finance",
            ],
        },
    }
    assert "ai" in result.message.casefold()
    for industry in ALLOWED_INDUSTRIES:
        assert industry in result.message.casefold()


def test_run_turn_refuses_biotechnology_and_fintech_instead_of_technology() -> None:
    runtime = _snapshot_rank_runtime()
    for query, label in (
        ("What are the top 10 biotechnology companies?", "biotechnology"),
        ("What are the top 10 companies in fintech?", "fintech"),
    ):
        result = run_turn(query, runtime)
        assert result.intent is Intent.RANK
        assert result.renderer is RendererKind.REFUSE
        assert result.table_rows == []
        assert result.tool_traces == []
        assert result.message is not None
        assert label in result.message.casefold()
        for industry in ALLOWED_INDUSTRIES:
            assert industry in result.message.casefold()


FINANCE_TOP_10_QUERY = "What are the top 10 companies in finance?"
FINANCE_TOP_4 = (
    ("JPMorgan Chase & Co.", "JPM", "0000019617", Decimal("919232700600")),
    ("Bank of America Corporation", "BAC", "0000070858", Decimal("402376653000")),
    ("The Goldman Sachs Group, Inc.", "GS", "0000886982", Decimal("275964298150")),
    ("Wells Fargo & Company", "WFC", "0000072971", Decimal("250901280000")),
)


def test_run_turn_ranks_finance_alias_and_does_not_pad_short_sectors() -> None:
    result = run_turn(FINANCE_TOP_10_QUERY, _snapshot_rank_runtime())

    assert result.intent is Intent.RANK
    assert result.renderer is RendererKind.TABLE
    assert len(result.table_rows) == 4
    assert len(result.table_rows) < 10
    for index, (name, ticker, cik, market_cap) in enumerate(FINANCE_TOP_4, start=1):
        row = result.table_rows[index - 1]
        assert row.rank == index
        assert row.company_name == name
        assert row.ticker == ticker
        assert row.cik == cik
        assert row.value == market_cap
        assert row.reason is None


TECHNOLOGY_TOP_10_QUERY = "What are the top 10 companies in technology?"
TECHNOLOGY_TOP_10 = (
    # The live snapshot's top ten: Alphabet is Communication Services there.
    ("NVIDIA Corporation", "NVDA", "0001045810", Decimal("5451420470000")),
    ("Apple Inc.", "AAPL", "0000320193", Decimal("5009416510920")),
    ("Microsoft Corporation", "MSFT", "0000789019", Decimal("3832846143500")),
    ("Broadcom Inc.", "AVGO", "0001730168", Decimal("1678521799800")),
    ("Micron Technology, Inc.", "MU", "0000723125", Decimal("1222316209200")),
    ("Advanced Micro Devices, Inc.", "AMD", "0000002488", Decimal("1028305278000")),
    ("Intel Corp.", "INTC", "0000050863", Decimal("620411968881")),
    ("Palantir Technologies Inc.", "PLTR", "0001321655", Decimal("435495596900")),
    ("Cisco Systems, Inc.", "CSCO", "0000858877", Decimal("420551078756")),
    ("Oracle Corporation", "ORCL", "0001341439", Decimal("394854827600")),
)


def test_run_turn_ranks_technology_as_the_live_snapshot_does() -> None:
    result = run_turn(TECHNOLOGY_TOP_10_QUERY, _snapshot_rank_runtime())

    assert result.intent is Intent.RANK
    assert result.renderer is RendererKind.TABLE
    assert len(result.table_rows) == 10
    for index, (name, ticker, cik, market_cap) in enumerate(TECHNOLOGY_TOP_10, start=1):
        row = result.table_rows[index - 1]
        assert row.rank == index
        assert row.company_name == name
        assert row.ticker == ticker
        assert row.cik == cik
        assert row.value == market_cap


def test_run_turn_consolidates_share_classes() -> None:
    result = run_turn(
        "What are the top 10 companies in communication services?", _snapshot_rank_runtime()
    )

    assert [(row.ticker, row.cik) for row in result.table_rows] == [("GOOG", "0001652044")]


class _ExplodingFacts(FakeFacts):
    def get_financials(
        self, company: str, metric: str, *, report_date: date | None = None
    ) -> SimpleNamespace:
        raise AssertionError("rank must not call fact lookup")


def _company(
    *,
    cik: str,
    name: str,
    ticker: str,
    market_cap: str,
    sector: str = "Healthcare",
    exchange: str = "NYSE",
    is_etf: bool = False,
    is_fund: bool = False,
    industry: str = "",
) -> UniverseCompany:
    return UniverseCompany(
        cik=cik,
        name=name,
        ticker=ticker,
        sector=sector,
        exchange=exchange,
        market_cap=Decimal(market_cap),
        is_etf=is_etf,
        is_fund=is_fund,
        industry=industry,
    )


def test_run_turn_ranks_builder_snapshot_without_etfs_funds_or_duplicate_ciks() -> None:
    snapshot = build_universe_snapshot(
        (
            _company(
                cik="0000731766",
                name="UnitedHealth Group Incorporated",
                ticker="UNH",
                market_cap="500000000000",
            ),
            _company(
                cik="0000731766",
                name="UnitedHealth Group Incorporated",
                ticker="UNHC",
                market_cap="499000000000",
            ),
            _company(
                cik="0000059478",
                name="Eli Lilly and Company",
                ticker="LLY",
                market_cap="800000000000",
            ),
            _company(
                cik="0000884394",
                name="Health Care Select Sector SPDR Fund",
                ticker="XLV",
                market_cap="900000000000",
                is_etf=True,
            ),
            _company(
                cik="0000102909",
                name="Vanguard Health Care Fund",
                ticker="VGHCX",
                market_cap="850000000000",
                is_fund=True,
            ),
            _company(
                cik="0000999999",
                name="Pink Sheet Health Co.",
                ticker="OTCH",
                market_cap="700000000000",
                exchange="OTC",
            ),
        ),
        as_of=datetime(2026, 8, 17, 16, 0, tzinfo=UTC),
    )
    result = run_turn(
        HEALTHCARE_TOP_10_QUERY,
        Runtime(
            completer=DemoCompleter(),
            facts=_ExplodingFacts(),
            ranking=SnapshotRanking(snapshot),
        ),
    )

    assert result.intent is Intent.RANK
    assert result.renderer is RendererKind.TABLE
    tickers = [row.ticker for row in result.table_rows]
    assert tickers == ["LLY", "UNH"]
    assert "XLV" not in tickers
    assert "VGHCX" not in tickers
    assert "UNHC" not in tickers
    assert "OTCH" not in tickers
    assert [row.cik for row in result.table_rows].count("0000731766") == 1


def test_snapshot_builder_drops_compact_nasdaq_unit_right_and_warrant_symbols() -> None:
    snapshot = build_universe_snapshot(
        (
            _company(
                cik="0002090000",
                name="JPMorgan Chase & Co.",
                ticker="JPM",
                sector="Financial Services",
                exchange="NASDAQ",
                market_cap="800000000000",
            ),
            _company(
                cik="0002090001",
                name="Alpha Acquisition Corp.",
                ticker="ABCDU",
                sector="Financial Services",
                exchange="NASDAQ",
                market_cap="300000000",
            ),
            _company(
                cik="0002090002",
                name="Beta Acquisition Corp.",
                ticker="EFGHR",
                sector="Financial Services",
                exchange="NASDAQ",
                market_cap="200000000",
            ),
            _company(
                cik="0002090003",
                name="Gamma Acquisition Corp.",
                ticker="IJKLW",
                sector="Financial Services",
                exchange="NASDAQ",
                market_cap="100000000",
            ),
            _company(
                cik="0002090004",
                name="Arrow Operating Company",
                ticker="ARROW",
                sector="Financial Services",
                exchange="NYSE",
                market_cap="500000000",
            ),
        ),
        as_of=datetime(2026, 8, 17, 16, 0, tzinfo=UTC),
    )

    assert [company.ticker for company in snapshot.companies] == ["JPM", "ARROW"]


def test_run_turn_ranks_operating_finance_issuers_not_shells_or_conglomerate_vehicles() -> None:
    snapshot = build_universe_snapshot(
        (
            _company(
                cik="0000019617",
                name="JPMorgan Chase & Co.",
                ticker="JPM",
                sector="Financial Services",
                market_cap="600000000000",
                industry="Banks - Diversified",
            ),
            _company(
                cik="0002047258",
                name="Drugs Made In America Acquisition II Corp. Ordinary Shares",
                ticker="DMII",
                sector="Financial Services",
                market_cap="645918000",
                industry="Shell Companies",
            ),
            _company(
                cik="0002040002",
                name="Long Table Growth Corp.",
                ticker="LTGR",
                sector="Financial Services",
                market_cap="171000000",
                industry="Financial - Conglomerates",
            ),
            _company(
                cik="0002012383",
                name="BlackRock, Inc.",
                ticker="BLK",
                sector="Financial Services",
                market_cap="170000000000",
                industry="Asset Management",
            ),
            _company(
                cik="0001287750",
                name="Ares Capital Corporation",
                ticker="ARCC",
                sector="Financial Services",
                market_cap="14000000000",
                industry="Asset Management",
            ),
        ),
        as_of=datetime(2026, 8, 17, 16, 0, tzinfo=UTC),
    )
    result = run_turn(
        FINANCE_TOP_10_QUERY,
        Runtime(
            completer=DemoCompleter(),
            facts=_ExplodingFacts(),
            ranking=SnapshotRanking(snapshot),
        ),
    )

    assert result.intent is Intent.RANK
    assert result.renderer is RendererKind.TABLE
    assert [row.ticker for row in result.table_rows] == ["JPM", "BLK"]
    assert "DMII" not in [row.ticker for row in result.table_rows]
    assert "LTGR" not in [row.ticker for row in result.table_rows]
    assert "ARCC" not in [row.ticker for row in result.table_rows]


def test_run_turn_keeps_common_shares_whose_ticker_shares_a_letter_suffix() -> None:
    snapshot = build_universe_snapshot(
        (
            _company(
                cik="0000723125",
                name="Micron Technology, Inc.",
                ticker="MU",
                sector="Technology",
                market_cap="150000000000",
                industry="Semiconductors",
            ),
            _company(
                cik="0000794367",
                name="Macy's, Inc.",
                ticker="M",
                sector="Consumer Cyclical",
                market_cap="5000000000",
                industry="Department Stores",
            ),
        ),
        as_of=datetime(2026, 8, 17, 16, 0, tzinfo=UTC),
    )
    result = run_turn(
        "What are the top 10 companies in technology?",
        Runtime(
            completer=DemoCompleter(),
            facts=_ExplodingFacts(),
            ranking=SnapshotRanking(snapshot),
        ),
    )

    assert [row.ticker for row in result.table_rows] == ["MU"]


def test_run_turn_excludes_shell_company_industry_even_without_acquisition_in_name() -> None:
    snapshot = build_universe_snapshot(
        (
            _company(
                cik="0000019617",
                name="JPMorgan Chase & Co.",
                ticker="JPM",
                sector="Financial Services",
                market_cap="600000000000",
                industry="Banks - Diversified",
            ),
            _company(
                cik="0002040001",
                name="Talon Capital Corp.",
                ticker="TLNC",
                sector="Financial Services",
                market_cap="400000000",
                industry="Shell Companies",
            ),
        ),
        as_of=datetime(2026, 8, 17, 16, 0, tzinfo=UTC),
    )
    result = run_turn(
        FINANCE_TOP_10_QUERY,
        Runtime(
            completer=DemoCompleter(),
            facts=_ExplodingFacts(),
            ranking=SnapshotRanking(snapshot),
        ),
    )

    assert result.intent is Intent.RANK
    assert result.renderer is RendererKind.TABLE
    assert [row.ticker for row in result.table_rows] == ["JPM"]


def test_run_turn_ranks_common_operating_companies_not_preferreds_or_trusts() -> None:
    snapshot = build_universe_snapshot(
        (
            _company(
                cik="0000034088",
                name="Exxon Mobil Corporation",
                ticker="XOM",
                sector="Energy",
                market_cap="500000000000",
            ),
            _company(
                cik="0001506307",
                name="El Paso Energy Capital Trust I PFD CV TR SECS",
                ticker="EP-PC",
                sector="Energy",
                market_cap="112533190000",
            ),
            _company(
                cik="0000753308",
                name="NextEra Energy, Inc.",
                ticker="NEE",
                sector="Utilities",
                market_cap="150000000000",
            ),
            _company(
                cik="0000764622",
                name="Pinnacle West Capital Corporation",
                ticker="PNW",
                sector="Utilities",
                market_cap="80000000000",
            ),
            _company(
                cik="0001348952",
                name="Entergy Louisiana, LLC COLLATERAL TR MT",
                ticker="ELC",
                sector="Utilities",
                market_cap="49766091729",
            ),
            _company(
                cik="0001067983",
                name="Berkshire Hathaway Inc.",
                ticker="BRK-A",
                sector="Financial Services",
                market_cap="1000000000000",
            ),
        ),
        as_of=datetime(2026, 8, 17, 16, 0, tzinfo=UTC),
    )
    energy = run_turn(
        "What are the top 10 companies in energy?",
        Runtime(
            completer=DemoCompleter(),
            facts=_ExplodingFacts(),
            ranking=SnapshotRanking(snapshot),
        ),
    )
    utilities = run_turn(
        "What are the top 10 companies in utilities?",
        Runtime(
            completer=DemoCompleter(),
            facts=_ExplodingFacts(),
            ranking=SnapshotRanking(snapshot),
        ),
    )
    finance = run_turn(
        FINANCE_TOP_10_QUERY,
        Runtime(
            completer=DemoCompleter(),
            facts=_ExplodingFacts(),
            ranking=SnapshotRanking(snapshot),
        ),
    )

    assert [row.ticker for row in energy.table_rows] == ["XOM"]
    assert [row.ticker for row in utilities.table_rows] == ["NEE", "PNW"]
    assert [row.ticker for row in finance.table_rows] == ["BRK-A"]


def test_run_turn_ranks_operating_companies_not_listed_debt() -> None:
    snapshot = build_universe_snapshot(
        (
            _company(
                cik="0000019617",
                name="JPMorgan Chase & Co.",
                ticker="JPM",
                sector="Financial Services",
                market_cap="800000000000",
            ),
            _company(
                cik="0001495222",
                name="Oxford Lane Capital Corp. 7.95% Notes due 2032",
                ticker="OXLCG",
                sector="Financial Services",
                market_cap="8492458000",
                exchange="NASDAQ",
            ),
            _company(
                cik="0001467623",
                name="TPG Mortgage Investment Trust Inc  9.500% Senior Notes due 2029",
                ticker="TPGN",
                sector="Financial Services",
                market_cap="7000000000",
                exchange="NYSE",
            ),
        ),
        as_of=datetime(2026, 8, 17, 16, 0, tzinfo=UTC),
    )
    result = run_turn(
        "What are the top 200 companies in financial services?",
        Runtime(
            completer=DemoCompleter(),
            facts=_ExplodingFacts(),
            ranking=SnapshotRanking(snapshot),
        ),
    )

    tickers = [row.ticker for row in result.table_rows]
    assert tickers == ["JPM"]
    assert "OXLCG" not in tickers
    assert all("notes due" not in row.company_name.casefold() for row in result.table_rows)


def test_run_turn_keeps_sec_common_share_not_note_ticker() -> None:
    rows = companies_from_vendor_payloads(
        (
            {
                "symbol": "SOMN",
                "cik": "0000092122",
                "companyName": "The Southern Company",
                "marketCap": 107637913197,
                "sector": "Utilities",
                "exchangeShortName": "NYSE",
                "isEtf": False,
                "isFund": False,
            },
            {
                "symbol": "SO",
                "cik": "0000092122",
                "companyName": "The Southern Company",
                "marketCap": 90000000000,
                "sector": "Utilities",
                "exchangeShortName": "NYSE",
                "isEtf": False,
                "isFund": False,
            },
        ),
        tickers_payload={
            "0": {"cik_str": 92122, "ticker": "SO", "title": "SOUTHERN CO"},
            "1": {"cik_str": 92122, "ticker": "SOMN", "title": "SOUTHERN CO"},
        },
    )
    snapshot = build_universe_snapshot(
        rows,
        as_of=datetime(2026, 8, 17, 16, 0, tzinfo=UTC),
        source="fmp_universe_snapshot",
    )
    result = run_turn(
        "What are the top 10 companies in utilities?",
        Runtime(
            completer=DemoCompleter(),
            facts=_ExplodingFacts(),
            ranking=SnapshotRanking(snapshot),
        ),
    )

    assert [(row.ticker, row.cik) for row in result.table_rows] == [
        ("SO", "0000092122"),
    ]


def test_run_turn_uses_sec_cik_when_vendor_cik_disagrees() -> None:
    rows = companies_from_vendor_payloads(
        (
            {
                "symbol": "XOM",
                "cik": "0002115436",
                "companyName": "Exxon Mobil Corporation",
                "marketCap": 669413179200,
                "sector": "Energy",
                "exchangeShortName": "NYSE",
                "isEtf": False,
                "isFund": False,
            },
        ),
        tickers_payload={
            "0": {"cik_str": 34088, "ticker": "XOM", "title": "EXXON MOBIL CORP"},
        },
    )
    snapshot = build_universe_snapshot(
        rows,
        as_of=datetime(2026, 8, 17, 16, 0, tzinfo=UTC),
        source="fmp_universe_snapshot",
    )
    result = run_turn(
        "What are the top 10 companies in energy?",
        Runtime(
            completer=DemoCompleter(),
            facts=_ExplodingFacts(),
            ranking=SnapshotRanking(snapshot),
        ),
    )

    assert [(row.ticker, row.cik) for row in result.table_rows] == [
        ("XOM", "0000034088"),
    ]


def test_run_turn_ranks_fmp_screener_rows_after_cik_and_exchange_normalization() -> None:
    """Live FMP screener rows omit cik and use descriptive exchange names."""
    rows = companies_from_vendor_payloads(
        (
            {
                "symbol": "MSFT",
                "companyName": "Microsoft Corporation",
                "marketCap": 3100000000000,
                "sector": "Technology",
                "exchange": "NASDAQ Global Select",
                "exchangeShortName": "NASDAQ",
                "isEtf": False,
                "isFund": False,
            },
            {
                "symbol": "GOOG",
                "companyName": "Alphabet Inc.",
                "marketCap": 2200000000000,
                "sector": "Technology",
                "exchange": "NASDAQ Global Select",
                "exchangeShortName": "NASDAQ",
                "isEtf": False,
                "isFund": False,
            },
        ),
        tickers_payload={
            "0": {"cik_str": 789019, "ticker": "MSFT", "title": "MICROSOFT CORP"},
            "1": {"cik_str": 1652044, "ticker": "GOOG", "title": "Alphabet Inc."},
        },
    )
    snapshot = build_universe_snapshot(
        rows,
        as_of=datetime(2026, 8, 17, 16, 0, tzinfo=UTC),
        source="fmp_universe_snapshot",
    )
    result = run_turn(
        TECHNOLOGY_TOP_10_QUERY,
        Runtime(
            completer=DemoCompleter(),
            facts=_ExplodingFacts(),
            ranking=SnapshotRanking(snapshot),
        ),
    )

    assert result.intent is Intent.RANK
    assert result.renderer is RendererKind.TABLE
    assert [(row.ticker, row.cik) for row in result.table_rows] == [
        ("MSFT", "0000789019"),
        ("GOOG", "0001652044"),
    ]


def test_fetch_fmp_rows_uses_stable_screener_on_configured_base_url() -> None:
    requested: list[httpx.URL] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(request.url)
        if request.url.path == "/stable/company-screener":
            return httpx.Response(
                200,
                json=[
                    {
                        "symbol": "MSFT",
                        "companyName": "Microsoft Corporation",
                        "marketCap": 3100000000000,
                        "sector": "Technology",
                        "exchange": "NASDAQ Global Select",
                        "exchangeShortName": "NASDAQ",
                        "isEtf": False,
                        "isFund": False,
                    }
                ],
            )
        return httpx.Response(404, json={"error": "unexpected url"})

    rows = fetch_fmp_rows(
        "test-key",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        tickers_payload={
            "0": {"cik_str": 789019, "ticker": "MSFT", "title": "MICROSOFT CORP"},
        },
        settings=Settings(
            fmp_api_key="test-key",
            fmp_base_url="https://fmp.example",
            sec_user_agent="FinancialAnalystAgent (dev@example.com)",
        ),
    )

    screener_urls = [url for url in requested if "company-screener" in url.path]
    assert screener_urls
    assert all(url.host == "fmp.example" for url in screener_urls)
    assert all(url.path == "/stable/company-screener" for url in screener_urls)
    assert all("/api/v3/" not in str(url) for url in requested)
    assert {row.ticker for row in rows} == {"MSFT"}


def test_fetch_fmp_rows_includes_us_listed_foreign_issuers() -> None:
    requested: list[httpx.URL] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(request.url)
        if request.url.path == "/stable/company-screener":
            return httpx.Response(
                200,
                json=[
                    {
                        "symbol": "NVO",
                        "companyName": "Novo Nordisk A/S",
                        "marketCap": 450000000000,
                        "sector": "Healthcare",
                        "country": "DK",
                        "exchange": "New York Stock Exchange",
                        "exchangeShortName": "NYSE",
                        "isEtf": False,
                        "isFund": False,
                    }
                ],
            )
        return httpx.Response(404, json={"error": "unexpected url"})

    rows = fetch_fmp_rows(
        "test-key",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        tickers_payload={
            "0": {"cik_str": 353259, "ticker": "NVO", "title": "NOVO NORDISK A S"},
        },
        settings=Settings(
            fmp_api_key="test-key",
            fmp_base_url="https://fmp.example",
            sec_user_agent="FinancialAnalystAgent (dev@example.com)",
        ),
    )

    screener_urls = [url for url in requested if "company-screener" in url.path]
    assert screener_urls
    assert all("country" not in url.params for url in screener_urls)
    assert {(row.ticker, row.cik, row.exchange) for row in rows} == {
        ("NVO", "0000353259", "NYSE")
    }


class _LillyUnavailableFacts(FakeFacts):
    """SEC fails for Eli Lilly; the other ranked companies report revenue."""

    def get_financials(
        self, company: str, metric: str, *, report_date: date | None = None
    ) -> SimpleNamespace:
        if company == "0000059478":
            raise ProviderError("SEC server error", details={"status_code": 503})
        return SimpleNamespace(
            company_name=company,
            ticker="",
            cik=company,
            metric=metric,
            value=Decimal(int(company[-6:])),
            currency="USD",
            start_date=date(2026, 4, 1),
            end_date=date(2026, 6, 30),
            filed_date=date(2026, 8, 1),
            form="10-Q",
            accession_number=f"{company}-26-000001",
            taxonomy="us-gaap",
            concept="Revenues",
            source_url="https://www.sec.gov/",
            derivation=None,
            newer_filing_end=None,
        )


def test_a_ranking_answers_with_the_companies_sec_could_serve() -> None:
    runtime = Runtime(
        completer=DemoCompleter(),
        facts=_LillyUnavailableFacts(),
        ranking=SnapshotRanking.from_path(FIXTURE_SNAPSHOT_PATH),
    )

    result = run_turn("top 3 healthcare companies by revenue", runtime)

    assert result.renderer is RendererKind.TABLE
    reasons = {row.company_name: row.reason for row in result.table_rows}
    assert reasons == {
        "Johnson & Johnson": None,
        "AbbVie Inc.": None,
        "Eli Lilly and Company": "source_unavailable",
    }


def test_snapshot_builder_refuses_to_write_empty_universe(tmp_path: Path) -> None:
    stub = tmp_path / "vendor.json"
    stub.write_text(
        json.dumps(
            [
                {
                    "symbol": "MSFT",
                    "companyName": "Microsoft Corporation",
                    "marketCap": 3100000000000,
                    "sector": "Technology",
                    "exchange": "NASDAQ Global Select",
                    "exchangeShortName": "NASDAQ",
                    "isEtf": False,
                    "isFund": False,
                }
            ]
        ),
        encoding="utf-8",
    )
    output = tmp_path / "universe_snapshot.json"
    output.write_text("do-not-clobber", encoding="utf-8")

    with pytest.raises(ValueError, match="empty"):
        main(["--input", str(stub), "--output", str(output)])

    assert output.read_text(encoding="utf-8") == "do-not-clobber"
