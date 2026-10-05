"""The recorded runtime summarizes only the filing changes its summary was written for.

Kept out of tests/unit for the reason tests/test_tester_conversations.py gives:
a recorded runtime used after tests/unit/test_contracts_import reloads the
conversation modules carries enum members the reloaded seam does not recognise.
"""

from __future__ import annotations

import json

import pytest


@pytest.fixture
def runtime():  # type: ignore[no-untyped-def]
    from financial_analyst_agent.runtime import recorded_runtime

    return recorded_runtime()


def _ask(runtime, question: str):  # type: ignore[no-untyped-def]
    from financial_analyst_agent.presentation import present_turn
    from financial_analyst_agent.turn import run_turn

    result = run_turn(question, runtime)
    return result, present_turn(result)


def _between() -> str:
    from financial_analyst_agent.runtime import RECORDED_FILING_NEWER, RECORDED_FILING_OLDER

    return f"between {RECORDED_FILING_OLDER} and {RECORDED_FILING_NEWER}"


def test_the_recorded_microsoft_pair_gets_a_summary_of_both_sections(runtime) -> None:  # type: ignore[no-untyped-def]
    from financial_analyst_agent.contracts import MODEL_ANALYSIS_BANNER
    from financial_analyst_agent.runtime import RECORDED_DISCLOSURE_SUMMARIES

    result, presented = _ask(
        runtime, f"Summarize what changed in Microsoft's MD&A and Risk Factors {_between()}"
    )

    assert {change.section for change in result.disclosure_changes} == {"mda", "risk_factors"}
    assert result.essay == " ".join(RECORDED_DISCLOSURE_SUMMARIES.values())
    assert result.numeral_lock_extras == []
    assert MODEL_ANALYSIS_BANNER in result.banners
    assert presented.essay == result.essay


def test_one_section_gets_only_that_section_summary(runtime) -> None:  # type: ignore[no-untyped-def]
    from financial_analyst_agent.runtime import (
        RECORDED_DISCLOSURE_SUMMARIES,
        RECORDED_FILING_NEWER,
        RECORDED_FILING_OLDER,
    )

    result, _ = _ask(runtime, "Summarize changes in Microsoft's MD&A")

    assert {change.section for change in result.disclosure_changes} == {"mda"}
    assert result.essay == RECORDED_DISCLOSURE_SUMMARIES[
        (RECORDED_FILING_OLDER, RECORDED_FILING_NEWER, "mda")
    ]
    assert "Risk Factors" not in (result.essay or "")


@pytest.mark.parametrize("company", ["UnitedHealth", "Apple"])
def test_another_company_shows_its_changes_without_a_summary(runtime, company: str) -> None:  # type: ignore[no-untyped-def]
    from financial_analyst_agent.contracts import MODEL_ANALYSIS_BANNER, RendererKind
    from financial_analyst_agent.runtime import RECORDED_SUMMARY_MISSING

    result, presented = _ask(runtime, f"Summarize changes in {company}'s MD&A")

    assert result.renderer is RendererKind.TABLE
    assert result.disclosure_changes
    assert result.essay is None
    assert MODEL_ANALYSIS_BANNER not in result.banners
    # The side-by-side changes still show, and the window says why there is no summary.
    assert presented.essay is None
    assert presented.disclosures
    assert RECORDED_SUMMARY_MISSING in presented.banners


def test_the_summary_is_keyed_by_the_evidence_not_the_prompt() -> None:
    from financial_analyst_agent.domain.errors import ProviderError
    from financial_analyst_agent.runtime import (
        RECORDED_FILING_NEWER,
        RECORDED_FILING_OLDER,
        RecordedEssayCompleter,
    )

    topic = "Summarize only the following disclosure changes for Microsoft Corporation."
    change = {
        "older_accession": RECORDED_FILING_OLDER,
        "newer_accession": RECORDED_FILING_NEWER,
        "section": "risk_factors",
    }
    completer = RecordedEssayCompleter()

    summary = completer.complete_essay(topic, json.dumps([change]))
    assert summary.startswith("Across the Risk Factors")
    for evidence in (
        [{**change, "newer_accession": "0000731766-26-000197"}],
        [change, {**change, "older_accession": "0000731766-25-000236"}],
        [],
    ):
        with pytest.raises(ProviderError):
            completer.complete_essay(topic, json.dumps(evidence))


def test_recorded_explain_essay_answers_after_a_lookup_and_names_its_runtime() -> None:
    from financial_analyst_agent.domain.errors import ProviderError
    from financial_analyst_agent.runtime import (
        FIXTURE_EXPLAIN_ESSAY,
        FIXTURE_EXPLAIN_QUERY,
        RecordedEssayCompleter,
    )

    grounding = json.dumps([{"ticker": "AAPL", "value": "109420000000"}])
    assert RecordedEssayCompleter().complete_essay(FIXTURE_EXPLAIN_QUERY, grounding) == (
        FIXTURE_EXPLAIN_ESSAY
    )
    with pytest.raises(ProviderError, match="Switch to Live"):
        RecordedEssayCompleter().complete_essay("Why is the sky blue?")
    with pytest.raises(ProviderError, match="OpenAI key") as refused:
        RecordedEssayCompleter(live=True).complete_essay("Why is the sky blue?", grounding)
    assert "live runtime" not in str(refused.value)


def test_recorded_replay_takes_a_question_however_it_is_punctuated() -> None:
    from financial_analyst_agent.news import FIXTURE_NEWS_QUERY, RecordedNewsSearch
    from financial_analyst_agent.runtime import (
        FIXTURE_EXPLAIN_ESSAY,
        FIXTURE_EXPLAIN_QUERY,
        RecordedEssayCompleter,
    )

    assert RecordedNewsSearch().search_news(f"  {FIXTURE_NEWS_QUERY.upper()}? ")
    assert RecordedEssayCompleter().complete_essay(FIXTURE_EXPLAIN_QUERY.rstrip("?") + ".") == (
        FIXTURE_EXPLAIN_ESSAY
    )


def test_capability_examples_are_ones_the_runtime_can_answer() -> None:
    from financial_analyst_agent.storefront import CAPABILITIES, capabilities_for

    recorded = capabilities_for(
        live_news=False, live_essays=False, recorded_news="NEWS?", recorded_essay="ESSAY?"
    )
    live = capabilities_for(
        live_news=True, live_essays=True, recorded_news="NEWS?", recorded_essay="ESSAY?"
    )

    examples = [example for _, group in recorded for example in group]
    assert "NEWS?" in examples and "ESSAY?" in examples
    assert live == CAPABILITIES


def test_live_without_news_or_a_model_does_not_advertise_them() -> None:
    from financial_analyst_agent.storefront import CAPABILITIES, capabilities_for

    keyless = capabilities_for(
        live_news=False,
        live_essays=False,
        recorded_news="NEWS?",
        recorded_essay="ESSAY?",
        live=True,
    )

    descriptions = [description for description, _ in keyless]
    examples = [example for _, group in keyless for example in group]
    assert len(keyless) == len(CAPABILITIES) - 2
    assert not any("news" in description.lower() for description in descriptions)
    assert "NEWS?" not in examples and "ESSAY?" not in examples
