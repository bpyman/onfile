"""One reading of a message's period words: windows, named periods, the stored form."""

from __future__ import annotations

import pytest

from financial_analyst_agent.graph.analysis_spec import NamedPeriodSpec, PeriodSelection, SpecPatch
from financial_analyst_agent.period_selection import WindowReading, read
from financial_analyst_agent.phrase_coverage import cases
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
        # A count and a unit with no recency word, after the metric.
        ("18 months", 6),
        ("2 years", 8),
        ("a couple of years", 8),
        ("6 quarters", 6),
        ("six quarters", 6),
        # A whole number of years and a half: that many years and two quarters more.
        ("the last year and a half", 6),
        ("a year and a half", 6),
        ("one and a half years", 6),
        ("two and a half years", 10),
        ("1.5 years", 6),
        ("the past 2.5 years", 10),
        ("over the last 2 and a half years", 10),
    ],
)
def test_a_window_reads_as_quarters(wording: str, quarters: int) -> None:
    reading = read(f"Apple revenue {wording}").reading

    assert reading.counted_window
    assert reading.asked_quarters == quarters
    assert reading.interpretation_notes == ()


@pytest.mark.parametrize(
    "wording",
    [
        "last quarter",
        "the past year",
        "three months ended June 2026",
        "2 quarters ago",
        "a year and a half ago",
        # A decimal that is not a half is left unread, not read by its last digit.
        "1.25 years",
        "top 5 banks",
        "Q3 2025",
        "fiscal 2025",
        "FY2024",
    ],
)
def test_wording_with_no_count_of_periods_is_no_window(wording: str) -> None:
    reading = read(f"Apple revenue {wording}").reading

    assert not reading.counted_window
    assert reading.asked_quarters is None


def test_a_trailing_twelve_month_figure_is_not_a_window_of_months() -> None:
    reading = read("Apple trailing 12-month revenue").reading

    assert not reading.counted_window
    assert reading.trailing_year


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
    reading = read(f"Apple revenue {wording}").reading

    assert reading.asked_quarters == quarters
    assert reading.interpretation_notes == (
        f"Read “{said}” as the latest {quarters} quarters; name a number of quarters to change it.",
    )


def test_a_window_past_the_cap_says_so() -> None:
    reading = read("Apple revenue over the last 15 years").reading

    assert reading.asked_quarters == 40
    assert reading.interpretation_notes == (
        "A window shows at most 40 quarters, so this asks for 40 rather than 60.",
    )


def test_decades_past_the_cap_say_so() -> None:
    reading = read("Apple revenue over the past two decades").reading

    assert reading.asked_quarters == 40
    assert reading.interpretation_notes == (
        "A window shows at most 40 quarters, so this asks for 40 rather than 80.",
    )


@pytest.mark.parametrize(
    ("message", "count"),
    [
        ("Apple revenue over the past decade", 40),
        ("show me Nvidia net income over the past 4 quarters", 4),
        ("Compare Pfizer and Merck revenue over the past six quarters", 6),
        ("what about over the past two years?", 8),
        ("Apple revenue 18 months", 6),
        ("MSFT net income a couple of years", 8),
    ],
)
def test_the_turn_binds_the_window_it_reads(message: str, count: int) -> None:
    patch = bind_periods_from_message(SpecPatch(mode="replace"), message)

    assert patch.set_periods == PeriodSelection(kind="last_n_quarters", count=count)


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        ("Apple revenue Q3 2024", (NamedPeriodSpec(year=2024, quarter=3),)),
        ("Nvidia margin in Q3 FY25", (NamedPeriodSpec(year=2025, quarter=3),)),
        ("revenue 2024 Q1", (NamedPeriodSpec(year=2024, quarter=1),)),
        ("third quarter of fiscal 2024", (NamedPeriodSpec(year=2024, quarter=3),)),
        ("Nvidia net income fiscal 2025", (NamedPeriodSpec(year=2025),)),
        ("FY24 revenue", (NamedPeriodSpec(year=2024),)),
        (
            "Walmart revenue calendar Q1 2026",
            (NamedPeriodSpec(year=2026, quarter=1, calendar=True),),
        ),
        ("Apple revenue in 2023", (NamedPeriodSpec(year=2023),)),
        (
            "Q3 2024 vs Q3 2023",
            (NamedPeriodSpec(year=2024, quarter=3), NamedPeriodSpec(year=2023, quarter=3)),
        ),
        ("Visa net margin 2Q 2026", (NamedPeriodSpec(year=2026, quarter=2),)),
        ("4QFY24 EPS", (NamedPeriodSpec(year=2024, quarter=4),)),
        (
            "Apple revenue H1 2026",
            (NamedPeriodSpec(year=2026, quarter=1), NamedPeriodSpec(year=2026, quarter=2)),
        ),
        (
            "revenue from 2022 to 2024",
            (NamedPeriodSpec(year=2024), NamedPeriodSpec(year=2023), NamedPeriodSpec(year=2022)),
        ),
        (
            "revenue for the quarter ended June 2026",
            (NamedPeriodSpec(year=2026, quarter=2, calendar=True),),
        ),
        ("revenue for the last 4 quarters", ()),
        ("Apple revenue since the start of 2024", ()),
        ("top 5 banks", ()),
    ],
)
def test_named_periods_are_read_from_the_question(
    question: str, expected: tuple[NamedPeriodSpec, ...]
) -> None:
    assert read(question).named == expected


@pytest.mark.parametrize(
    ("message", "names_a_window"),
    [
        ("Apple revenue over the past 10 quarters", True),
        ("Apple revenue over the last year", True),
        ("Apple revenue since 2023", True),
        # A window of one quarter names none; "since 2025 year over year" is a window.
        ("Apple revenue last quarter", False),
        ("Apple revenue Q3 2024 vs Q3 2023", False),
        ("Apple revenue since 2025 year over year", True),
        ("Apple revenue", False),
    ],
)
def test_whether_the_words_name_a_window(message: str, names_a_window: bool) -> None:
    assert read(message).names_a_window is names_a_window


def test_the_reading_holds_what_the_notes_say_about_the_window() -> None:
    approximate = read("Apple revenue over the past several months").reading
    assert approximate.asked_quarters == 2
    assert approximate.interpretation_notes
    assert read("Apple TTM revenue").reading.trailing_year
    since = read("Apple revenue since 2000").reading
    # A "since" window names its year; how many quarters that is waits for the
    # companies' report dates, so the reading counts none.
    assert (since.since_year, since.asked_quarters) == (2000, None)
    assert read("Apple revenue for the quarter ended April 2026").reading.unread_named_period == (
        "April 2026"
    )
    assert read("Apple revenue last month").reading.sub_quarter
    assert read("Apple revenue last year").reading.year_of_quarters
    assert read("Apple annual revenue").reading.year_of_quarters
    assert not read("Apple revenue last 4 quarters").reading.year_of_quarters
    assert not read("Apple TTM revenue").reading.year_of_quarters


@pytest.mark.parametrize(
    ("message", "year_to_date"),
    [
        ("Apple YTD revenue", True),
        ("Apple revenue year to date", True),
        ("Apple year-to-date revenue", True),
        ("Apple revenue last 4 quarters", False),
    ],
)
def test_year_to_date_words_are_read_into_the_reading(message: str, year_to_date: bool) -> None:
    assert read(message).reading.year_to_date is year_to_date


_STORED_FIELDS = {
    "asked_quarters",
    "counted_window",
    "interpretation_notes",
    "trailing_year",
    "year_of_quarters",
    "since_year",
    "since_fiscal",
    "unread_named_period",
    "sub_quarter",
}


def test_the_stored_reading_dumps_as_before_over_every_phrasing() -> None:
    # Checkpoints and thread records hold the reading: a new field would reach
    # every stored dump, so it is left out unless it is set.
    assert WindowReading().model_dump() == {
        "asked_quarters": None,
        "counted_window": False,
        "interpretation_notes": (),
        "trailing_year": False,
        "year_of_quarters": False,
        "since_year": None,
        "since_fiscal": False,
        "unread_named_period": None,
        "sub_quarter": False,
    }
    wordings = [turn for case in cases() for turn in case.turns]
    assert len(wordings) > 500
    for wording in wordings:
        reading = read(wording).reading
        dumped = reading.model_dump()
        if reading.year_to_date:
            assert set(dumped) == _STORED_FIELDS | {"year_to_date"}, wording
        else:
            assert set(dumped) == _STORED_FIELDS, wording
        assert WindowReading.model_validate(dumped) == reading, wording
    assert read("Apple YTD revenue").reading.model_dump()["year_to_date"] is True


def test_a_stored_reading_replaces_the_grammars_but_not_the_named_periods() -> None:
    # A checkpointed request keeps the reading of the question it held; the
    # periods a reply names are still its own.
    held = read("Apple margin over the past few quarters").reading
    words = read("gross margin Q3 2024", stored=held)

    assert words.reading is held
    assert words.reading.asked_quarters == 4
    assert words.named == (NamedPeriodSpec(year=2024, quarter=3),)
    assert words.message == "gross margin Q3 2024"


@pytest.mark.parametrize(
    ("question", "ticker"),
    [
        ("Raytheon Technologies revenue", "RTX"),
        ("Apple Computer revenue", "AAPL"),
    ],
)
def test_a_former_name_finds_the_company(question: str, ticker: str) -> None:
    assert [mention.query for mention in issuer_index().find(question)] == [ticker]
