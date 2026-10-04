"""News-and-explain through run_turn with an injected news adapter."""

from datetime import date
from types import SimpleNamespace

from financial_analyst_agent.contracts import Intent, NewsHit, RendererKind, Runtime, WorkflowPlan
from financial_analyst_agent.domain.errors import ProviderError
from financial_analyst_agent.news import FIXTURE_NEWS_QUERY
from financial_analyst_agent.runtime import recorded_runtime
from financial_analyst_agent.turn import run_turn

NVIDIA_SUPPLY_QUERY = "What is going on with NVIDIA supply chain?"
MICROSOFT_NEWS_QUERY = "What's going on with Microsoft?"
FIXTURE_HIT = NewsHit(
    title="NVIDIA flags CoWoS supply constraints",
    url="https://example.test/nvidia-supply-chain",
    snippet="Lead times remain extended after $12.3B of data-center demand.",
    score=0.91,
    published="2026-08-10",
)
GROUNDED_ESSAY = (
    "Coverage of NVIDIA's supply chain cited $12.3B of data-center demand "
    "and CoWoS constraints."
)


class _NewsCompleter:
    def complete(self, query: str, current_spec: object = None) -> WorkflowPlan:
        if query != NVIDIA_SUPPLY_QUERY:
            raise AssertionError(f"unexpected query: {query!r}")
        return WorkflowPlan(intent=Intent.NEWS_AND_EXPLAIN)


class _RewritingNewsCompleter:
    def complete(self, query: str, current_spec: object = None) -> WorkflowPlan:
        if query != NVIDIA_SUPPLY_QUERY:
            raise AssertionError(f"unexpected query: {query!r}")
        return WorkflowPlan(intent=Intent.NEWS_AND_EXPLAIN)


class _GroundedEssay:
    def complete_essay(self, query: str, tool_json: str = "") -> str:
        if query != NVIDIA_SUPPLY_QUERY:
            raise AssertionError(f"unexpected essay query: {query!r}")
        if "$12.3B" not in tool_json:
            raise AssertionError("essay must receive news hit JSON")
        return GROUNDED_ESSAY


class _ExplodingEssay:
    def complete_essay(self, query: str, tool_json: str = "") -> str:
        raise AssertionError("empty news hits must not fall back to a memory essay")


class _ExplodingFacts:
    def get_financials(
        self, company: str, metric: str, *, report_date: date | None = None
    ) -> SimpleNamespace:
        raise AssertionError("news_and_explain must not look up financials")


class _FixtureNews:
    def search_news(self, query: str) -> list[NewsHit]:
        if query != NVIDIA_SUPPLY_QUERY:
            raise AssertionError(f"unexpected search_news query: {query!r}")
        return [FIXTURE_HIT]


class _EmptyNews:
    def search_news(self, query: str) -> list[NewsHit]:
        return []


class _FailingNews:
    def search_news(self, query: str) -> list[NewsHit]:
        raise ProviderError("Tavily search failed", details={"query": query})


def _news_runtime(news: object, essay: object) -> Runtime:
    return Runtime(
        completer=_NewsCompleter(),
        facts=_ExplodingFacts(),
        news=news,
        essay=essay,
    )


def test_run_turn_news_and_explain_cites_fixture_hits() -> None:
    result = run_turn(NVIDIA_SUPPLY_QUERY, _news_runtime(_FixtureNews(), _GroundedEssay()))

    assert result.intent is Intent.NEWS_AND_EXPLAIN
    assert result.renderer is RendererKind.ESSAY
    assert result.essay == GROUNDED_ESSAY
    assert result.numeral_lock_extras == []
    assert result.table_rows == []
    assert [hit.url for hit in result.citations] == [FIXTURE_HIT.url]
    assert result.citations[0].published == FIXTURE_HIT.published

    assert len(result.tool_traces) == 1
    trace = result.tool_traces[0]
    assert trace.tool == "search_news"
    assert trace.args["query"] == NVIDIA_SUPPLY_QUERY
    assert trace.args["topic"] == "news"
    assert trace.args["max_results"] == 5
    assert [hit["url"] for hit in trace.provenance["hits"]] == [FIXTURE_HIT.url]


def test_run_turn_news_and_explain_uses_original_query_when_plan_rewrites_it() -> None:
    result = run_turn(
        NVIDIA_SUPPLY_QUERY,
        Runtime(
            completer=_RewritingNewsCompleter(),
            facts=_ExplodingFacts(),
            news=_FixtureNews(),
            essay=_GroundedEssay(),
        ),
    )

    assert result.renderer is RendererKind.ESSAY
    assert result.tool_traces[0].args["query"] == NVIDIA_SUPPLY_QUERY


def test_run_turn_news_and_explain_refuses_empty_hits_without_essay() -> None:
    result = run_turn(NVIDIA_SUPPLY_QUERY, _news_runtime(_EmptyNews(), _ExplodingEssay()))

    assert result.intent is Intent.NEWS_AND_EXPLAIN
    assert result.renderer is RendererKind.REFUSE
    assert result.essay is None
    assert result.citations == []
    assert result.table_rows == []
    assert result.tool_traces[0].tool == "search_news"
    assert result.tool_traces[0].args["query"] == NVIDIA_SUPPLY_QUERY
    assert result.message is not None
    assert "articles i can cite" in result.message.casefold()


def test_run_turn_news_and_explain_refuses_provider_failure_without_essay() -> None:
    result = run_turn(NVIDIA_SUPPLY_QUERY, _news_runtime(_FailingNews(), _ExplodingEssay()))

    assert result.intent is Intent.NEWS_AND_EXPLAIN
    assert result.renderer is RendererKind.REFUSE
    assert result.essay is None
    assert result.citations == []
    assert len(result.tool_traces) == 1
    trace = result.tool_traces[0]
    assert trace.tool == "search_news"
    assert trace.args["query"] == NVIDIA_SUPPLY_QUERY
    assert trace.provenance["error"] == {
        "code": "provider_error",
        "message": "Tavily search failed",
    }
    assert result.message is not None
    assert "unavailable" in result.message.casefold()


class _InventedDollarEssay:
    def complete_essay(self, query: str, tool_json: str = "") -> str:
        return "NVIDIA will ship $29.8B of extra GPUs next quarter."


class _BracketCiteEssay:
    def complete_essay(self, query: str, tool_json: str = "") -> str:
        return "Packaging remains tight [1] after $12.3B of data-center demand."


class _BareIndexEssay:
    def complete_essay(self, query: str, tool_json: str = "") -> str:
        return "Source 1 and source 2 and source 3 flag CoWoS constraints after $12.3B of demand."


class _OutOfRangeCiteEssay:
    def complete_essay(self, query: str, tool_json: str = "") -> str:
        return "See [6] after $12.3B of data-center demand."


class _CombinedCiteEssay:
    def complete_essay(self, query: str, tool_json: str = "") -> str:
        return "See [1, 2] after $12.3B of data-center demand."


def test_run_turn_news_and_explain_allows_hit_numbers_but_locks_novel_dollars() -> None:
    result = run_turn(
        NVIDIA_SUPPLY_QUERY,
        _news_runtime(_FixtureNews(), _InventedDollarEssay()),
    )

    assert result.intent is Intent.NEWS_AND_EXPLAIN
    assert result.renderer is RendererKind.REFUSE
    assert result.essay is None
    assert result.numeral_lock_extras
    assert any("29.8" in extra for extra in result.numeral_lock_extras)


def test_run_turn_news_allows_bracket_citation_to_a_hit() -> None:
    result = run_turn(
        NVIDIA_SUPPLY_QUERY,
        _news_runtime(_FixtureNews(), _BracketCiteEssay()),
    )

    assert result.renderer is RendererKind.ESSAY
    assert result.essay is not None
    assert "[1]" in result.essay
    assert result.numeral_lock_extras == []


def test_run_turn_news_refuses_bare_citation_numbers() -> None:
    result = run_turn(
        NVIDIA_SUPPLY_QUERY,
        _news_runtime(_FixtureNews(), _BareIndexEssay()),
    )

    assert result.renderer is RendererKind.REFUSE
    assert result.essay is None
    assert "1" in result.numeral_lock_extras
    assert "2" in result.numeral_lock_extras
    assert "3" in result.numeral_lock_extras


def test_run_turn_news_refuses_out_of_range_citation() -> None:
    result = run_turn(
        NVIDIA_SUPPLY_QUERY,
        _news_runtime(_FixtureNews(), _OutOfRangeCiteEssay()),
    )

    assert result.renderer is RendererKind.REFUSE
    assert result.essay is None
    assert any(extra == "6" for extra in result.numeral_lock_extras)


def test_run_turn_news_refuses_combined_citation_markers() -> None:
    result = run_turn(
        NVIDIA_SUPPLY_QUERY,
        _news_runtime(_FixtureNews(), _CombinedCiteEssay()),
    )

    assert result.renderer is RendererKind.REFUSE
    assert result.essay is None


class _MixedNews:
    def search_news(self, query: str) -> list[NewsHit]:
        return [
            NewsHit(title="", url="https://example.test/missing-title"),
            NewsHit(title="No URL", url=""),
            FIXTURE_HIT,
        ]


def test_run_turn_news_and_explain_drops_hits_missing_title_or_url() -> None:
    result = run_turn(NVIDIA_SUPPLY_QUERY, _news_runtime(_MixedNews(), _GroundedEssay()))

    assert result.renderer is RendererKind.ESSAY
    assert [hit.url for hit in result.citations] == [FIXTURE_HIT.url]


def test_recorded_runtime_news_and_explain_uses_recorded_hits() -> None:
    result = run_turn(FIXTURE_NEWS_QUERY, recorded_runtime())

    assert result.intent is Intent.NEWS_AND_EXPLAIN
    assert result.renderer is RendererKind.ESSAY
    assert result.essay is not None
    assert result.essay.strip()
    assert "Hormuz" in result.essay
    assert "$1.2B" in result.essay
    assert result.numeral_lock_extras == []
    assert result.citations
    assert all(hit.title and hit.url for hit in result.citations)
    trace = result.tool_traces[0]
    assert trace.tool == "search_news"
    assert trace.args["query"] == FIXTURE_NEWS_QUERY
    assert trace.args["topic"] == "news"
    assert trace.args["max_results"] == 5


def test_recorded_runtime_refuses_news_without_matching_recording() -> None:
    result = run_turn(MICROSOFT_NEWS_QUERY, recorded_runtime())

    assert result.intent is Intent.NEWS_AND_EXPLAIN
    assert result.renderer is RendererKind.REFUSE
    assert result.essay is None
    assert result.citations == []
    assert result.message is not None
    assert "articles i can cite" in result.message.casefold()
