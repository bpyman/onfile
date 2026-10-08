"""Everyday phrasings are read as the README says; the known gaps are exactly the ones listed."""

from datetime import date
from types import SimpleNamespace
from typing import Any

from financial_analyst_agent.phrase_coverage import KNOWN_GAPS, SENT_TO_MODEL, cases, run
from financial_analyst_agent.planner_evaluation import Observation


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


GROUPS_IN_REPORT_ORDER = [
    "Metrics",
    "Ambiguous metric words",
    "Windows",
    "Year over year",
    "Growth with no metric",
    "Quarter over quarter",
    "A named period with a change",
    "Both bases",
    "Changes with no base",
    "A change over a window",
    "Idioms beside a company",
    "Everyday-word names used as the word",
    "A segment names its company",
    "Overviews",
    "Unknown measures",
    "General questions",
    "Rankings",
    "Follow-ups",
    "Change switches",
    "Combinations",
    "Follow-up combinations",
]


def test_the_cases_keep_their_ids_groups_turns_and_expected_text() -> None:
    by_id = {case.case_id: case for case in cases()}

    assert list(dict.fromkeys(case.group for case in cases())) == GROUPS_IN_REPORT_ORDER
    assert len(by_id) == 555
    for case_id, group, turns, expected in (
        (
            "window:over the last 4 quarters",
            "Windows",
            ("Apple revenue over the last 4 quarters",),
            "last_n_quarters 4",
        ),
        (
            "window:apple revenue 2 years",
            "Windows",
            ("apple revenue 2 years",),
            "last_n_quarters 8",
        ),
        ("yoy:Apple revenue YoY", "Year over year", ("Apple revenue YoY",), "year-over-year rows"),
        (
            "qoq:Apple revenue QoQ",
            "Quarter over quarter",
            ("Apple revenue QoQ",),
            "sequential rows",
        ),
        (
            "growth:Is Apple growing?",
            "Growth with no metric",
            ("Is Apple growing?",),
            "AAPL; `revenue`; last_n_quarters 5; year_over_year rows",
        ),
        (
            "idiom:Merck and Pfizer net margin, apples with apples",
            "Idioms beside a company",
            ("Merck and Pfizer net margin, apples with apples",),
            "MRK, PFE; `net_margin`; latest_quarter",
        ),
        (
            "word use:any intel on Nvidia revenue?",
            "Everyday-word names used as the word",
            ("any intel on Nvidia revenue?",),
            "NVDA; `revenue`; latest_quarter",
        ),
        (
            "segment:Xbox sales",
            "A segment names its company",
            ("Xbox sales",),
            "MSFT; `revenue`; latest_quarter",
        ),
        (
            "overview:Give me the rundown on Apple and Microsoft",
            "Overviews",
            ("Give me the rundown on Apple and Microsoft",),
            "AAPL, MSFT; `revenue`, `net_income`, `gross_margin`, `operating_margin`, "
            "`net_margin`; latest_quarter",
        ),
        (
            "follow_up:Apple | add net income",
            "Follow-ups",
            ("Apple revenue over the last 4 quarters", "add net income"),
            "revenue and net income",
        ),
        (
            "combined_follow_up:Apple revenue | show that year over year",
            "Follow-up combinations",
            ("Apple revenue", "show that year over year"),
            "AAPL; `revenue`; year_over_year rows",
        ),
    ):
        case = by_id[case_id]
        assert (case.group, case.turns, case.expected) == (group, turns, expected), case_id


def test_the_window_phrasings_come_before_the_whole_window_questions() -> None:
    ids = [case.case_id for case in cases()]

    assert ids.index("window:in calendar Q1 2026") + 1 == ids.index(
        "window:pfizer net income over the last twelve months"
    )
    assert ids.index("window:Apple trailing 12-month revenue") + 1 == ids.index(
        "yoy:Apple revenue year over year"
    )


# The groups whose Expected column lists the companies, metrics, window and change rows.
READING_GROUPS = {
    "Growth with no metric",
    "Idioms beside a company",
    "Everyday-word names used as the word",
    "A segment names its company",
    "Overviews",
    "Combinations",
    "Follow-up combinations",
}


def _turn_as_expected(expected: str) -> tuple[Observation, Any]:
    """A turn read exactly as a reading case's Expected column says."""
    parts = expected.split("; ")
    tickers = frozenset(parts[0].split(", "))
    metrics = frozenset(metric.strip("`") for metric in parts[1].split(", "))
    comparison = parts[-1].removesuffix(" rows") if parts[-1].endswith(" rows") else None
    windows = parts[2 : len(parts) - (comparison is not None)]
    periods: tuple[str, int | None] = ("latest_quarter", None)
    if windows:
        kind, _, count = windows[0].partition(" ")
        periods = (kind, int(count) if count else None)
    seen = Observation("answer", "lookup", tickers, metrics, periods, frozenset())
    quarter = date(2025, 6, 28)
    rows = [SimpleNamespace(comparison=None, value="1", end_date=quarter)]
    if comparison is not None:
        rows.append(SimpleNamespace(comparison=comparison, value="1", end_date=quarter))
    return seen, SimpleNamespace(result=SimpleNamespace(table_rows=rows), analysis_spec=None)


def test_every_reading_cases_check_accepts_the_turn_its_expected_text_describes() -> None:
    reading = [case for case in cases() if case.group in READING_GROUPS]

    assert len(reading) > 100
    for case in reading:
        seen, turn = _turn_as_expected(case.expected)
        assert case.check(seen, turn), (case.case_id, case.expected)
        # Another company, and the check says no: the column is what is checked.
        other = Observation(
            "answer", "lookup", frozenset({"ZZZ"}), seen.metrics, seen.periods, frozenset()
        )
        assert not case.check(other, turn), case.case_id
