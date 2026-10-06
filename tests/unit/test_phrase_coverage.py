"""Everyday phrasings are read as the README says; the known gaps are exactly the ones listed."""

from financial_analyst_agent.phrase_coverage import KNOWN_GAPS, SENT_TO_MODEL, cases, run


def test_the_phrase_cases_are_unique_and_the_gaps_are_cases() -> None:
    ids = [case.case_id for case in cases()]

    assert len(ids) == len(set(ids))
    assert set(ids) >= KNOWN_GAPS
    assert set(ids) >= SENT_TO_MODEL


def test_every_phrasing_is_read_right_except_the_known_gaps() -> None:
    outcomes = run()
    misread = {o.case.case_id: o.seen for o in outcomes if not o.passed}

    # A phrasing read wrong that is not a known gap is a regression.
    assert {case: seen for case, seen in misread.items() if case not in KNOWN_GAPS} == {}
    # A known gap read right is fixed: take it off KNOWN_GAPS.
    assert sorted(KNOWN_GAPS - set(misread)) == []
    # The live cascade sends exactly the expected phrasings to the LLM planner.
    sent = {o.case.case_id: o.sent_to_model for o in outcomes if o.sent_to_model}
    assert {case: why for case, why in sent.items() if case not in SENT_TO_MODEL} == {}
    assert sorted(SENT_TO_MODEL - set(sent)) == []
