"""Conversation edges a code review found: held questions, shared names, follow-ups."""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest

from financial_analyst_agent.contracts import RendererKind, Runtime, TurnResult
from financial_analyst_agent.conversation import run_conversation_turn
from financial_analyst_agent.domain.errors import AmbiguousCompanyError
from financial_analyst_agent.graph.state import Clarification, PendingClarification
from financial_analyst_agent.graph.turn_graph import _restored_whole, names_index
from financial_analyst_agent.ranking import SnapshotRanking
from financial_analyst_agent.rules_planner import DemoCompleter, issuer_index
from financial_analyst_agent.runtime import recorded_runtime
from financial_analyst_agent.thread_store import EphemeralThreadStore
from helpers import FakeFacts


def _conversation(runtime: Runtime, *messages: str) -> list[TurnResult]:
    store = EphemeralThreadStore()
    thread = uuid.uuid4().hex
    return [run_conversation_turn(thread, m, runtime, store=store).result for m in messages]


def test_an_llm_planned_turn_reads_names_with_the_rankings_index() -> None:
    ranking = SnapshotRanking.from_path(None, issuer_index())
    runtime = SimpleNamespace(ranking=ranking, completer=SimpleNamespace())

    assert names_index(runtime) is ranking.index


def test_a_clarification_restored_with_unvalidated_fields_is_not_resumed() -> None:
    result = TurnResult(intent="lookup", tool_traces=[], renderer=RendererKind.CLARIFY)
    whole = Clarification(
        pending=PendingClarification(
            kind="ambiguous_metric", candidates=("net_income",), patch={"mode": "replace"}
        ),
        result=result,
    )
    # LangGraph rebuilds a model whose saved fields no longer validate with
    # model_construct, which leaves plain dicts behind.
    broken = Clarification.model_construct(pending={"kind": "renamed"}, result=result)

    assert _restored_whole(whole)
    assert not _restored_whole(broken)


def test_the_set_aside_note_is_not_put_on_a_new_question() -> None:
    asked, again = _conversation(
        recorded_runtime(), "What was Google's profit?", "What was Microsoft's margin?"
    )

    assert asked.renderer is RendererKind.CLARIFY
    assert again.renderer is RendererKind.CLARIFY
    assert not any("set aside" in banner for banner in again.banners)


@pytest.mark.parametrize(
    "new_question",
    ["Microsoft net income last quarter", "What was Microsoft's revenue this year?"],
)
def test_a_new_question_is_not_taken_as_the_base_of_a_change(new_question: str) -> None:
    _, answer = _conversation(recorded_runtime(), "how has Apple revenue changed?", new_question)

    assert answer.renderer is not RendererKind.CLARIFY
    assert {row.ticker for row in answer.table_rows} == {"MSFT"}


def test_why_did_revenue_drop_asks_what_to_compare_against() -> None:
    _, asked = _conversation(recorded_runtime(), "Apple revenue", "why did revenue drop?")

    assert asked.clarify_kind == "ambiguous_comparison"


@pytest.mark.parametrize("reply", ["year over year", "sequential"])
def test_how_much_revenue_changed_asks_then_answers_as_how_it_changed_does(reply: str) -> None:
    runtime = recorded_runtime()
    asked, answer = _conversation(runtime, "How much did Intel's revenue change?", reply)
    _, changed = _conversation(runtime, "How has Intel's revenue changed?", reply)

    assert asked.clarify_kind == "ambiguous_comparison"
    assert answer.renderer is RendererKind.TABLE
    assert answer.table_rows == changed.table_rows


@pytest.mark.parametrize(
    ("name", "first"),
    [("Charles", ("SCHW", "CRL")), ("Coca", ("KO", "CCEP")), ("Lincoln", ("LECO", "LNC"))],
)
def test_a_shared_first_name_always_asks(name: str, first: tuple[str, str]) -> None:
    ranking = SnapshotRanking.from_path(None, issuer_index())

    with pytest.raises(AmbiguousCompanyError) as raised:
        ranking.lookup_member(name)

    assert tuple(m["ticker"] for m in raised.value.details["matches"])[:2] == first


@pytest.mark.parametrize("edit", ["add target", "include block too"])
def test_an_everyday_word_name_is_added_in_lower_case(edit: str) -> None:
    from financial_analyst_agent.contracts import Intent

    class _Facts(FakeFacts):
        """No quarters are listed, as FakeFacts has it; no fact is found."""

        def get_financials(self, company: str, metric: str, **_: object) -> SimpleNamespace:
            raise LookupError(company)

    index = issuer_index()
    runtime = Runtime(
        completer=DemoCompleter(index),
        facts=_Facts(),  # type: ignore[arg-type]
        ranking=SnapshotRanking.from_path(None, index),
    )
    store = EphemeralThreadStore()
    run_conversation_turn("t1", "Walmart revenue", runtime, store=store)
    turn = run_conversation_turn("t1", edit, runtime, store=store)

    assert turn.result.intent is Intent.COMPARE
    assert turn.analysis_spec is not None
    added = {"add target": "TGT", "include block too": "XYZ"}[edit]
    assert [company.ticker for company in turn.analysis_spec.companies] == ["WMT", added]


def test_a_named_year_the_filings_hold_only_part_of_says_so() -> None:
    (answer,) = _conversation(recorded_runtime(), "Apple revenue 2024")

    assert "The filings here hold 2 of the 4 quarters in Fiscal 2024 for Apple." in answer.banners
