"""One grammar for a window's wording (recency word, count and unit), and former names."""

from __future__ import annotations

import pytest

from financial_analyst_agent.graph.analysis_spec import PeriodSelection, SpecPatch
from financial_analyst_agent.period_window import asked_window
from financial_analyst_agent.request_wording import bind_periods_from_message
from financial_analyst_agent.rules_planner import issuer_index


@pytest.mark.parametrize(
    ("wording", "quarters"),
    [
        ("over the past 4 quarters", 4),
        ("over the past six quarters", 6),
        ("the trailing seven quarters", 7),
        ("for the previous nine quarters", 9),
        ("most recent twelve quarters", 12),
        ("prior 5 quarters", 5),
        ("past eleven quarters", 11),
        ("last twenty-four quarters", 24),
        ("the 4 most recent quarters", 4),
        ("in each of the most recent 6 quarters", 6),
        ("over 8 quarters", 8),
        ("last 4 qtrs", 4),
        ("the last couple of quarters", 2),
        ("for a couple quarters", 2),
        ("a dozen past quarters", 12),
        ("over the past three years", 12),
        ("trailing four years", 16),
        ("past 2 fiscal years", 8),
        ("the last 18 months", 6),
        ("last 0 quarters", 1),
        ("over the past decade", 40),
        ("the last decade", 40),
        ("for the previous decade", 40),
        ("over the past one decade", 40),
    ],
)
def test_a_window_reads_as_quarters(wording: str, quarters: int) -> None:
    window = asked_window(f"Apple revenue {wording}")

    assert window is not None
    assert window.quarters == quarters
    assert window.notes() == []


@pytest.mark.parametrize(
    "wording",
    [
        "last quarter",
        "the past year",
        "three months ended June 2026",
        "2 quarters ago",
        "top 5 banks",
        "Q3 2025",
    ],
)
def test_wording_with_no_count_of_periods_is_no_window(wording: str) -> None:
    assert asked_window(f"Apple revenue {wording}") is None


@pytest.mark.parametrize(
    ("wording", "quarters", "said"),
    [
        ("over the last few quarters", 4, "last few quarters"),
        ("last several quarters", 4, "last several quarters"),
        ("last 4 months", 2, "last 4 months"),
    ],
)
def test_a_window_with_no_exact_count_says_how_it_was_read(
    wording: str, quarters: int, said: str
) -> None:
    window = asked_window(f"Apple revenue {wording}")

    assert window is not None
    assert window.quarters == quarters
    assert window.notes() == [
        f"Read “{said}” as the latest {quarters} quarters; name a number of quarters to change it."
    ]


def test_a_window_past_the_cap_says_so() -> None:
    window = asked_window("Apple revenue over the last 15 years")

    assert window is not None
    assert window.quarters == 40
    assert window.notes() == [
        "A window shows at most 40 quarters, so this asks for 40 rather than 60."
    ]


def test_decades_past_the_cap_say_so() -> None:
    window = asked_window("Apple revenue over the past two decades")

    assert window is not None
    assert window.quarters == 40
    assert window.notes() == [
        "A window shows at most 40 quarters, so this asks for 40 rather than 80."
    ]


@pytest.mark.parametrize(
    ("message", "count"),
    [
        ("Apple revenue over the past decade", 40),
        ("show me Nvidia net income over the past 4 quarters", 4),
        ("Compare Pfizer and Merck revenue over the past six quarters", 6),
        ("what about over the past two years?", 8),
    ],
)
def test_the_turn_binds_the_window_it_reads(message: str, count: int) -> None:
    patch = bind_periods_from_message(SpecPatch(mode="replace"), message)

    assert patch.set_periods == PeriodSelection(kind="last_n_quarters", count=count)


@pytest.mark.parametrize(
    ("question", "ticker"),
    [
        ("Raytheon Technologies revenue", "RTX"),
        ("Apple Computer revenue", "AAPL"),
    ],
)
def test_a_former_name_finds_the_company(question: str, ticker: str) -> None:
    assert [mention.query for mention in issuer_index().find(question)] == [ticker]
