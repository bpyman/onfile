"""One reading of a message's period words: windows, named periods, the stored form."""

from __future__ import annotations

import dataclasses

import pytest

from financial_analyst_agent.graph.analysis_spec import (
    AnalysisSpec,
    NamedPeriodSpec,
    PeriodSelection,
    SpecPatch,
)
from financial_analyst_agent.period_selection import ChangeAsked, WindowReading, read
from financial_analyst_agent.phrase_coverage import cases
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
    patch = read(message).bind(SpecPatch(mode="replace"), ChangeAsked.NONE)

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


# --- The change asked, and the binding --------------------------------------


def _change(**flags: object) -> ChangeAsked:
    return dataclasses.replace(ChangeAsked.NONE, **flags)


# "Apple revenue growth": year over year by convention, not named as such.
_GROWTH = _change(base="year_over_year", yoy=True)
# "year over year", "versus last year": named as such.
_EXPLICIT_YOY = _change(base="year_over_year", yoy=True, explicit_yoy=True)
# "quarter over quarter", "sequential instead".
_SEQUENTIAL = _change(base="sequential", sequential=True)
# "sequentially or versus last year".
_BOTH = _change(base="sequential", yoy=True, sequential=True, both=True, explicit_yoy=True)
# "How much did revenue change?": a change, but against what is not said.
_UNCLEAR = _change(base="unclear", change_words=True)
_Q4_2025 = NamedPeriodSpec(year=2025, quarter=4)
_ACROSS = ("across_periods",)
_ACROSS_YOY = ("across_periods", "year_over_year")
_EVERY_CHANGE = ("across_periods", "year_over_year", "sequential")


def _window(count: int, **fields: object) -> PeriodSelection:
    return PeriodSelection(kind="last_n_quarters", count=count, **fields)


def _named(*periods: NamedPeriodSpec, **fields: object) -> PeriodSelection:
    return PeriodSelection(kind="named", named=periods, **fields)


def test_no_change_asked_is_every_flag_off() -> None:
    every_flag_off = ChangeAsked(
        base=None,
        yoy=False,
        sequential=False,
        both=False,
        explicit_yoy=False,
        change_words=False,
        dropped=False,
    )

    assert every_flag_off == ChangeAsked.NONE


def test_bind_returns_the_patch_itself_when_the_words_say_nothing_about_periods() -> None:
    # A clarification tells a period reply from a metric by comparing the two.
    patch = SpecPatch(mode="extend", add_metrics=("gross_margin",))

    assert read("gross margin").bind(patch, ChangeAsked.NONE) is patch


@pytest.mark.parametrize(
    ("message", "change", "periods", "added"),
    [
        # A counted window, with or without a change over it.
        ("Apple revenue over the past six quarters", ChangeAsked.NONE, _window(6), ()),
        ("Apple revenue over the past six quarters", _GROWTH, _window(6), _ACROSS_YOY),
        ("Apple revenue last 4 quarters yoy", _EXPLICIT_YOY, _window(4), _ACROSS_YOY),
        # A sequential window reads one quarter more than it shows.
        (
            "Apple revenue last 4 quarters quarter over quarter",
            _SEQUENTIAL,
            _window(5, asked=4),
            _ACROSS,
        ),
        # No window named: growth shows five quarters, explicit year over year eight,
        # a sequential change five, and a change with no base is read over five.
        ("Apple revenue growth", _GROWTH, _window(5), _ACROSS_YOY),
        ("Apple revenue year over year", _EXPLICIT_YOY, _window(8), _ACROSS_YOY),
        ("Apple revenue quarter over quarter", _SEQUENTIAL, _window(5), _ACROSS),
        ("How much did Apple's revenue change?", _UNCLEAR, _window(5), _ACROSS),
        ("Apple revenue sequentially or versus last year", _BOTH, _window(5), _EVERY_CHANGE),
        # A change over a window of two is over those two, not the five of growth.
        (
            "How much did Apple's revenue change over the last 2 quarters?",
            _change(base="year_over_year", change_words=True),
            _window(2),
            _ACROSS_YOY,
        ),
        # A change over "the past year" is over that year's four quarters.
        (
            "How did Apple's revenue change over the past year?",
            _change(base="year_over_year", yoy=True, change_words=True),
            _window(4),
            _ACROSS_YOY,
        ),
        # The trailing year and "last year" are four quarters, shown one by one.
        ("Apple TTM revenue", ChangeAsked.NONE, _window(4), ()),
        ("Apple revenue last year", ChangeAsked.NONE, _window(4), ()),
        # A "since" window names its year; the cap stands in for its count.
        ("Apple revenue since 2024", ChangeAsked.NONE, _window(40, since_year=2024), ()),
        (
            "Apple revenue since fiscal 2025 year over year",
            _EXPLICIT_YOY,
            _window(40, since_year=2025, since_fiscal=True),
            _ACROSS_YOY,
        ),
        (
            "Apple revenue since 2025 quarter over quarter",
            _SEQUENTIAL,
            _window(40, since_year=2025),
            _ACROSS,
        ),
        # Named periods: a change on one is on a window of it; a sequential change
        # reads the quarter before each named quarter once the dates are listed.
        ("Apple revenue Q4 2025", ChangeAsked.NONE, _named(_Q4_2025), ()),
        ("Apple revenue Q4 2025 yoy", _EXPLICIT_YOY, _named(_Q4_2025), _ACROSS_YOY),
        (
            "Apple revenue Q4 2025 quarter over quarter",
            _SEQUENTIAL,
            _named(_Q4_2025, company_base_dates=()),
            _ACROSS,
        ),
        (
            "Apple revenue Q3 2024 vs Q3 2023",
            ChangeAsked.NONE,
            _named(NamedPeriodSpec(year=2024, quarter=3), NamedPeriodSpec(year=2023, quarter=3)),
            _ACROSS,
        ),
        (
            "Apple revenue 2025 vs 2024",
            ChangeAsked.NONE,
            _named(NamedPeriodSpec(year=2025), NamedPeriodSpec(year=2024)),
            (),
        ),
        # Change words with no base are a change over at most one named period;
        # over two, the periods themselves are the answer.
        ("How much did Apple's revenue change in Q4 2025?", _UNCLEAR, _named(_Q4_2025), _ACROSS),
        (
            "How much did Apple's revenue change, 2025 vs 2024?",
            _change(change_words=True),
            _named(NamedPeriodSpec(year=2025), NamedPeriodSpec(year=2024)),
            (),
        ),
    ],
)
def test_bind_sets_the_periods_the_words_ask_for(
    message: str, change: ChangeAsked, periods: PeriodSelection, added: tuple[str, ...]
) -> None:
    patch = read(message).bind(SpecPatch(mode="replace"), change)

    assert patch.set_periods == periods
    assert patch.add_operations == added
    assert patch.remove_operations == ()


def test_bind_keeps_a_proposed_window_and_adds_the_change_asked_over_it() -> None:
    proposed = SpecPatch(mode="replace", set_periods=_window(6))

    patch = read("How has Nvidia's net income trended lately?").bind(proposed, _GROWTH)

    assert patch.set_periods == _window(6)
    assert patch.add_operations == _ACROSS_YOY


def test_bind_latest_resets_to_one_quarter_with_no_change() -> None:
    patch = read("latest").bind(SpecPatch(mode="extend"), ChangeAsked.NONE)

    assert patch.set_periods == PeriodSelection()
    assert patch.remove_operations == _EVERY_CHANGE


def test_bind_a_dropped_change_keeps_the_quarters_and_takes_every_change_away() -> None:
    patch = SpecPatch(
        mode="extend",
        add_operations=("order_by_metric", "year_over_year"),
        remove_operations=("sequential",),
    )

    bound = read("remove year over year").bind(patch, _change(dropped=True))

    assert bound.set_periods is None
    assert bound.add_operations == ("order_by_metric",)
    assert bound.remove_operations == ("sequential", "across_periods", "year_over_year")


# --- Rebasing a change follow-up on the quarters on screen -----------------


def _on_screen(periods: PeriodSelection, *operations: str) -> AnalysisSpec:
    return AnalysisSpec(metrics=("revenue",), periods=periods, operations=operations)


_YOY_BOUND = SpecPatch(mode="extend", set_periods=_window(8), add_operations=_ACROSS_YOY)
_SEQUENTIAL_BOUND = SpecPatch(mode="extend", set_periods=_window(5), add_operations=_ACROSS)


@pytest.mark.parametrize(
    ("message", "change", "patch", "on_screen"),
    [
        # Nothing on screen to keep: the latest quarter, or a window of one.
        ("show that year over year", _EXPLICIT_YOY, _YOY_BOUND, PeriodSelection()),
        ("show that year over year", _EXPLICIT_YOY, _YOY_BOUND, _window(1)),
        # The follow-up names its own quarters.
        ("show that year over year for the last 3 quarters", _EXPLICIT_YOY, _YOY_BOUND, _window(6)),
        ("show that year over year for Q4 2025", _EXPLICIT_YOY, _YOY_BOUND, _window(6)),
        ("TTM revenue year over year", _EXPLICIT_YOY, _YOY_BOUND, _window(6)),
        ("year over year since 2024", _EXPLICIT_YOY, _YOY_BOUND, _window(6)),
        # No base to rebase on, or no periods bound, or not an edit.
        ("add net income", ChangeAsked.NONE, SpecPatch(mode="extend"), _window(6)),
        ("why did revenue drop?", _change(base="unclear", yoy=True), _YOY_BOUND, _window(6)),
        (
            "show that year over year",
            _EXPLICIT_YOY,
            SpecPatch(mode="extend", add_operations=_ACROSS_YOY),
            _window(6),
        ),
        (
            "show that year over year",
            _EXPLICIT_YOY,
            _YOY_BOUND.model_copy(update={"mode": "replace"}),
            _window(6),
        ),
    ],
)
def test_rebase_leaves_the_patch_alone_unless_a_change_follow_up_keeps_the_screen(
    message: str, change: ChangeAsked, patch: SpecPatch, on_screen: PeriodSelection
) -> None:
    assert read(message).rebase(patch, change, _on_screen(on_screen)) is patch


def test_rebase_a_year_over_year_follow_up_keeps_a_counted_window() -> None:
    rebased = read("show that year over year").rebase(
        _YOY_BOUND, _EXPLICIT_YOY, _on_screen(_window(6), "across_periods")
    )

    assert rebased.set_periods is None
    assert rebased.add_operations == _ACROSS_YOY
    assert rebased.remove_operations == ("sequential",)


def test_rebase_year_over_year_after_a_sequential_named_period_reads_no_base_quarter() -> None:
    on_screen = _named(NamedPeriodSpec(year=2025), company_base_dates=())

    rebased = read("show that year over year").rebase(
        _YOY_BOUND, _EXPLICIT_YOY, _on_screen(on_screen, "across_periods")
    )

    assert rebased.set_periods == _named(NamedPeriodSpec(year=2025))
    assert rebased.remove_operations == ("sequential",)


@pytest.mark.parametrize(
    ("on_screen", "periods"),
    [
        # The quarter before the oldest one shown is read as its base, not shown.
        (_window(6), _window(7, asked=6)),
        # A named period reads the quarter before each named quarter the same way.
        (
            _named(NamedPeriodSpec(year=2025)),
            _named(NamedPeriodSpec(year=2025), company_base_dates=()),
        ),
        # Already read with its base, or every quarter since a year: unchanged.
        (_window(7, asked=6), None),
        (_window(40, since_year=2024), None),
    ],
)
def test_rebase_a_sequential_follow_up_switches_the_change_and_keeps_the_screen(
    on_screen: PeriodSelection, periods: PeriodSelection | None
) -> None:
    rebased = read("sequential instead").rebase(
        _SEQUENTIAL_BOUND, _SEQUENTIAL, _on_screen(on_screen, *_ACROSS_YOY)
    )

    assert rebased.set_periods == periods
    assert rebased.add_operations == _ACROSS
    assert rebased.remove_operations == ("year_over_year", "sequential")


def test_rebase_both_bases_keep_the_screen_and_show_both_changes() -> None:
    bound = SpecPatch(mode="extend", set_periods=_window(5), add_operations=_EVERY_CHANGE)

    rebased = read("sequentially or versus last year").rebase(
        bound, _BOTH, _on_screen(_window(6), "across_periods")
    )

    assert rebased.set_periods == _window(7, asked=6)
    assert rebased.add_operations == _EVERY_CHANGE
    assert rebased.remove_operations == ()
