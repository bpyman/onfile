"""The numeral-lock measurement quotes each value in known ways and runs the real lock."""

from financial_analyst_agent.numeral_lock_evaluation import KINDS, Quote, measure, sentences


def test_each_kind_quotes_the_value_as_it_says() -> None:
    lilly = Quote("Eli Lilly and Company", "revenue", "22974000000", "$22.97 B")
    pfizer = Quote("Pfizer Inc.", "revenue", "15034000000", "$15.03 B")

    written = {
        kind.name: sentence
        for kind, quote, sentence in sentences([lilly, pfizer])
        if quote is lilly
    }

    assert "22974000000" in written["exact_json"]
    assert "$22.97 B" in written["as_shown"]
    assert "$22.97 billion" in written["as_shown_in_words"]
    assert "about $23 billion" in written["rounded"]
    assert "22974000001" in written["json_digit_changed"]
    assert "$22.98 B" in written["shown_digit_changed"]
    assert "17.3%" in written["invented"] and "22974000000" in written["invented"]
    assert "15034000000" in written["misattributed"]
    assert set(written) == {kind.name for kind in KINDS}


def test_the_lock_keeps_exact_quotes_and_withholds_changed_and_invented_numbers() -> None:
    report = measure(("Compare Eli Lilly and Pfizer revenue and net margin",))
    by_name = {kind["name"]: kind for kind in report["kinds"]}

    assert report["answers"] == 1
    assert by_name["exact_json"]["withheld"] == 0
    for name in ("json_digit_changed", "shown_digit_changed", "invented"):
        assert by_name[name]["withheld"] == by_name[name]["sentences"] > 0
