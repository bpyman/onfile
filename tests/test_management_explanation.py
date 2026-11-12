"""A why question about a figure shows Management's explanation (ADR 0017, ticket 04).

Replayed on the recorded runtime, whose explanations are the model's answers from the
explanation evaluation (``data/explanation_recordings.json``), checked again as a live
answer is. The live path is the same step with a fake completer.
"""

from __future__ import annotations

import json
from dataclasses import replace
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import pytest

from conversation_replay import ask

COST_OF_REVENUE_WHY = "What caused Alphabet's cost of revenue to rise year over year last quarter?"
ALPHABET = ("0001652044", "0001652044-26-000071", "cost_of_revenue")


@pytest.fixture
def runtime():  # type: ignore[no-untyped-def]
    from financial_analyst_agent.runtime import recorded_runtime

    return recorded_runtime()


def _recorded_reply(key: tuple[str, str, str]) -> tuple[str, str]:
    from financial_analyst_agent.runtime import EXPLANATION_RECORDINGS

    for entry in json.loads(EXPLANATION_RECORDINGS.read_text(encoding="utf-8"))["recordings"]:
        if (entry["cik"], entry["accession"], entry["metric"]) == key:
            return entry["offered"], entry["reply"]
    raise AssertionError(f"no recording for {key}")


def _no_why_note(banners: tuple[str, ...]) -> bool:
    from financial_analyst_agent.answer_notes import WHY_NOTES

    return not set(banners) & set(WHY_NOTES)


def test_a_why_question_with_a_recording_shows_the_panel_with_its_paragraphs(runtime) -> None:  # type: ignore[no-untyped-def]
    from financial_analyst_agent.quote_lock import quotes_outside

    (answer,) = ask(runtime, COST_OF_REVENUE_WHY)
    assert answer.table is not None or answer.fact_card is not None
    panel = answer.explanation
    assert panel is not None
    assert panel.heading == "Management's explanation"
    assert panel.note is None
    (company,) = panel.companies
    assert company.source == "From Alphabet's 10-Q for the quarter ended Jun 30, 2026 · MD&A"
    assert company.unavailable is None
    assert company.explanation
    assert 1 <= len(company.paragraphs) <= 3
    texts = [paragraph.text for paragraph in company.paragraphs]
    # Every quotation is word for word in the paragraphs shown, and each links to its place.
    assert quotes_outside(company.explanation, texts) == []
    for paragraph in company.paragraphs:
        assert paragraph.url.startswith(company.filing_url + "#:~:text=")
    assert company.filing_url.endswith("/000165204426000071/goog-20260630.htm")
    assert company.mda_url.startswith(company.filing_url + "#:~:text=")
    # The panel replaces ADR 0016's note.
    assert _no_why_note(answer.banners)


def test_a_figure_then_why_shows_it_and_the_plain_lookup_shows_none(runtime) -> None:  # type: ignore[no-untyped-def]
    lookup, why = ask(runtime, "Nvidia operating income", "why?")
    assert lookup.explanation is None
    assert why.explanation is not None
    (company,) = why.explanation.companies
    assert company.company_name.startswith("NVIDIA")
    assert company.explanation and company.paragraphs
    # The figures show again with it.
    assert why.table is not None or why.fact_card is not None


@pytest.mark.parametrize("bare", ["why is that?", "how come?"])
def test_other_bare_whys_after_figures_show_it(runtime, bare: str) -> None:  # type: ignore[no-untyped-def]
    _, why = ask(runtime, "Alphabet cost of revenue", bare)
    assert why.explanation is not None
    assert why.explanation.companies[0].paragraphs


def test_a_plain_lookup_shows_none(runtime) -> None:  # type: ignore[no-untyped-def]
    (answer,) = ask(runtime, "Alphabet cost of revenue year over year")
    assert answer.explanation is None


def test_a_why_question_about_market_cap_keeps_the_note(runtime) -> None:  # type: ignore[no-untyped-def]
    from financial_analyst_agent.answer_notes import WHY_NOT_ANSWERED_NOTE
    from financial_analyst_agent.guide import WHY_MESSAGE

    (answer,) = ask(runtime, "What drove Apple's market cap?")
    assert answer.explanation is None
    assert WHY_NOT_ANSWERED_NOTE in answer.banners
    _, bare = ask(runtime, "Apple market cap", "why?")
    assert bare.explanation is None
    assert bare.message == WHY_MESSAGE


def test_a_metric_outside_the_scope_keeps_the_note(runtime) -> None:  # type: ignore[no-untyped-def]
    from financial_analyst_agent.answer_notes import WHY_CHANGE_BANNER

    (answer,) = ask(runtime, "Why did Alphabet's operating margin rise year over year?")
    assert answer.explanation is None
    assert WHY_CHANGE_BANNER in answer.banners


def test_a_figure_from_a_10k_keeps_the_note(runtime) -> None:  # type: ignore[no-untyped-def]
    # Cisco's latest quarter is its fiscal fourth, derived from the 10-K, whose MD&A
    # explains the year.
    from financial_analyst_agent.answer_notes import WHY_CHANGE_BANNER

    (answer,) = ask(runtime, "Why did Cisco's revenue grow year over year?")
    assert answer.explanation is None
    assert WHY_CHANGE_BANNER in answer.banners


@pytest.mark.parametrize(
    "conversation",
    [
        ("Why did Alphabet's cost of revenue rise sequentially?",),
        ("Why did Alphabet's cost of revenue rise last quarter?", "the quarter before"),
    ],
)
def test_a_sequential_why_shows_the_year_over_year_route(runtime, conversation) -> None:  # type: ignore[no-untyped-def]
    from financial_analyst_agent.explanation import YEAR_OVER_YEAR_ONLY_NOTE

    answer = ask(runtime, *conversation)[-1]
    assert answer.explanation is not None
    assert answer.explanation.note == YEAR_OVER_YEAR_ONLY_NOTE
    assert YEAR_OVER_YEAR_ONLY_NOTE == (
        "This 10-Q explains the change against a year earlier, not the quarter before"
    )
    year_over_year = ask(runtime, COST_OF_REVENUE_WHY)[0].explanation
    assert year_over_year is not None
    assert answer.explanation.companies == year_over_year.companies


def test_a_recorded_answer_that_fails_the_quote_lock_shows_the_not_found_line(runtime) -> None:  # type: ignore[no-untyped-def]
    from financial_analyst_agent.explanation import NOT_FOUND_MESSAGE
    from financial_analyst_agent.runtime import RecordedExplanations

    offered, _ = _recorded_reply(ALPHABET)
    paraphrase = json.dumps(
        {"paragraphs": [1], "explanation": 'Costs rose on "more spending on data centers".'}
    )
    patched = replace(runtime, explanations=RecordedExplanations({ALPHABET: (offered, paraphrase)}))
    (answer,) = ask(patched, COST_OF_REVENUE_WHY)
    assert answer.explanation is not None
    (company,) = answer.explanation.companies
    assert company.unavailable == NOT_FOUND_MESSAGE
    assert (company.explanation, company.paragraphs) == ("", ())
    assert company.mda_url.startswith(company.filing_url + "#:~:text=")
    assert _no_why_note(answer.banners)


def test_nothing_found_shows_the_not_found_line(runtime) -> None:  # type: ignore[no-untyped-def]
    from financial_analyst_agent.explanation import NOT_FOUND_MESSAGE

    (answer,) = ask(runtime, "Why did Pfizer's cost of revenue rise year over year?")
    assert answer.explanation is not None
    assert answer.explanation.companies[0].unavailable == NOT_FOUND_MESSAGE


def test_a_question_with_no_recording_says_the_demo_has_none(runtime) -> None:  # type: ignore[no-untyped-def]
    from financial_analyst_agent.explanation import NOT_RECORDED_MESSAGE

    (answer,) = ask(runtime, "Why did Nvidia's revenue rise year over year?")
    assert answer.explanation is not None
    (company,) = answer.explanation.companies
    assert company.unavailable == NOT_RECORDED_MESSAGE
    assert NOT_RECORDED_MESSAGE == "The recorded demo has no explanation for this question"


def test_a_recording_for_other_paragraphs_is_not_replayed(runtime) -> None:  # type: ignore[no-untyped-def]
    from financial_analyst_agent.explanation import NOT_RECORDED_MESSAGE
    from financial_analyst_agent.runtime import RecordedExplanations

    _, reply = _recorded_reply(ALPHABET)
    patched = replace(runtime, explanations=RecordedExplanations({ALPHABET: ("0" * 16, reply)}))
    (answer,) = ask(patched, COST_OF_REVENUE_WHY)
    assert answer.explanation is not None
    assert answer.explanation.companies[0].unavailable == NOT_RECORDED_MESSAGE


def test_each_company_gets_its_own_explanation(runtime) -> None:  # type: ignore[no-untyped-def]
    (answer,) = ask(runtime, "Why did Alphabet and Amgen revenue grow year over year?")
    assert answer.explanation is not None
    names = [company.company_name for company in answer.explanation.companies]
    assert names == ["Alphabet Inc.", "Amgen Inc."]
    assert all(company.paragraphs for company in answer.explanation.companies)


# The live path: the same step, with the model behind a fake.


class _Completer:
    def __init__(self, reply: str | Exception) -> None:
        self.reply = reply
        self.asked: list[str] = []

    def complete_essay(self, query: str, tool_json: str = "") -> str:
        self.asked.append(query)
        if isinstance(self.reply, Exception):
            raise self.reply
        return self.reply


class _Explanations:
    def __init__(self, completer: Any) -> None:
        self._completer = completer
        self.keys: list[tuple[str, str, str]] = []

    def completer(self, cik: str, accession: str, metric: str) -> Any:
        self.keys.append((cik, accession, metric))
        return self._completer


def _live(runtime: Any, explanations: Any, **changes: Any) -> Any:
    """The recorded figures on a live runtime whose explanations come from ``explanations``."""
    from financial_analyst_agent.contracts import RuntimeKind

    return replace(runtime, kind=RuntimeKind.LIVE, explanations=explanations, **changes)


def _ask_live(runtime: Any, *messages: str) -> list[Any]:
    """Each answer on a live thread, presented, and the last turn's result."""
    import uuid

    from financial_analyst_agent.contracts import RuntimeKind
    from financial_analyst_agent.conversation import run_conversation_turn, start_thread
    from financial_analyst_agent.presentation import present_turn
    from financial_analyst_agent.thread_store import EphemeralThreadStore

    store = EphemeralThreadStore()
    thread_id = uuid.uuid4().hex
    start_thread(thread_id, RuntimeKind.LIVE, store=store)
    return [
        present_turn(run_conversation_turn(thread_id, message, runtime, store=store).result)
        for message in messages
    ]


def test_a_live_answer_is_asked_for_the_figures_filing_and_checked(runtime) -> None:  # type: ignore[no-untyped-def]
    _, reply = _recorded_reply(ALPHABET)
    completer = _Completer(reply)
    explanations = _Explanations(completer)
    (answer,) = _ask_live(_live(runtime, explanations), COST_OF_REVENUE_WHY)
    assert explanations.keys == [ALPHABET]
    [query] = completer.asked
    assert query.startswith(
        "Company: Alphabet\nFigure: cost of revenue, which rose year over year\n"
        "Quarter ended: 2026-06-30\n"
        f"Question: {COST_OF_REVENUE_WHY}\n\nParagraph 1: "
    )
    assert answer.explanation is not None
    (company,) = answer.explanation.companies
    assert company.unavailable is None and company.paragraphs


@pytest.mark.parametrize(
    "failure",
    ["spend_cap", "openai_off"],
)
def test_without_the_model_the_panel_says_so_and_links_the_mda(runtime, failure: str) -> None:  # type: ignore[no-untyped-def]
    from financial_analyst_agent.config import Settings
    from financial_analyst_agent.explanation import MODEL_UNAVAILABLE_MESSAGE
    from financial_analyst_agent.model_spend import SPEND_CAP_MESSAGE, SpendCapReached
    from financial_analyst_agent.runtime import LiveExplanations

    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    if failure == "spend_cap":
        explanations: Any = _Explanations(_Completer(SpendCapReached(SPEND_CAP_MESSAGE)))
    else:
        from financial_analyst_agent.model_spend import DailySpendCap

        explanations = LiveExplanations(settings, DailySpendCap(Decimal(1)), enabled=False)
    (answer,) = _ask_live(_live(runtime, explanations), COST_OF_REVENUE_WHY)
    assert answer.explanation is not None
    (company,) = answer.explanation.companies
    assert company.unavailable == MODEL_UNAVAILABLE_MESSAGE
    assert MODEL_UNAVAILABLE_MESSAGE == (
        "Management's explanation needs the language model, which is unavailable here"
    )
    assert company.mda_url.startswith(company.filing_url + "#:~:text=")
    # The figures still show.
    assert answer.table is not None or answer.fact_card is not None


def test_the_live_completer_charges_the_shared_daily_cap(
    runtime: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    from financial_analyst_agent import explanation
    from financial_analyst_agent.config import Settings
    from financial_analyst_agent.explanation import MODEL_UNAVAILABLE_MESSAGE
    from financial_analyst_agent.model_spend import DailySpendCap
    from financial_analyst_agent.runtime import LiveExplanations

    _, reply = _recorded_reply(ALPHABET)
    sent: list[dict[str, object]] = []

    def create(**request: object) -> SimpleNamespace:
        sent.append(request)
        usage = SimpleNamespace(input_tokens=1_000_000, output_tokens=0)
        return SimpleNamespace(output_text=reply, usage=usage)

    client = SimpleNamespace(responses=SimpleNamespace(create=create))
    monkeypatch.setattr(explanation, "openai_client_from_settings", lambda s: (client, "m"))
    settings = Settings(_env_file=None, openai_essay_model="gpt-6.1-sol")  # type: ignore[call-arg]
    spend = DailySpendCap(Decimal(2))
    live = _live(runtime, LiveExplanations(settings, spend, enabled=True))
    (first,) = _ask_live(live, COST_OF_REVENUE_WHY)
    assert first.explanation is not None and first.explanation.companies[0].paragraphs
    assert sent[0]["model"] == "gpt-6.1-sol"
    assert spend.spent_today == Decimal(2)
    # The day's budget is spent: the next one is not sent.
    (second,) = _ask_live(live, COST_OF_REVENUE_WHY)
    assert second.explanation is not None
    assert second.explanation.companies[0].unavailable == MODEL_UNAVAILABLE_MESSAGE
    assert len(sent) == 1


@pytest.mark.parametrize("kind", ["recorded", "live"])
def test_a_filing_that_cannot_be_read_never_fails_the_turn(runtime, kind: str) -> None:  # type: ignore[no-untyped-def]
    from financial_analyst_agent.contracts import RuntimeKind
    from financial_analyst_agent.domain.errors import ProviderError
    from financial_analyst_agent.explanation import (
        FILING_UNREADABLE_MESSAGE,
        NOT_RECORDED_MESSAGE,
    )

    source = runtime.filings

    class _Unreadable:
        def __getattr__(self, name: str) -> Any:
            return getattr(source, name)

        def get_filing_document(self, cik: str, accession: str, document: str) -> str:
            raise ProviderError("SEC did not answer")

    patched = replace(runtime, filings=_Unreadable(), kind=RuntimeKind(kind))
    asking = ask if kind == "recorded" else _ask_live
    (answer,) = asking(patched, COST_OF_REVENUE_WHY)
    assert answer.table is not None or answer.fact_card is not None
    assert answer.explanation is not None
    expected = NOT_RECORDED_MESSAGE if kind == "recorded" else FILING_UNREADABLE_MESSAGE
    assert answer.explanation.companies[0].unavailable == expected


def test_the_live_runtime_wires_the_explanation_model_only_with_openai() -> None:
    from financial_analyst_agent.config import Settings
    from financial_analyst_agent.explanation import ExplanationUnavailable
    from financial_analyst_agent.runtime import LiveExplanations, live_runtime

    settings = Settings(  # type: ignore[call-arg]
        _env_file=None, openai_api_key="", sec_user_agent="OnfileTests (test@example.com)"
    )
    built = live_runtime(settings)
    assert isinstance(built.explanations, LiveExplanations)
    completer = built.explanations.completer(*ALPHABET)
    with pytest.raises(ExplanationUnavailable):
        completer.complete_essay("Company: Alphabet")
