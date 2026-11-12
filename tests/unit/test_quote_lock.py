"""The quote lock: every quotation in a model's explanation is in the paragraphs, word for word."""

from financial_analyst_agent.quote_lock import quotes_outside

PARAGRAPH = (
    "Total revenues increased $1.2 billion, or 9%, compared with the same quarter of "
    "2025, primarily due to higher sales of HIV products. This was partially offset by "
    "lower sales of oncology products."
)
OTHER = "Gross margin was 54.2% in the quarter, reflecting a favourable product mix."


def test_a_verbatim_quotation_passes() -> None:
    text = 'Revenue rose "primarily due to higher sales of HIV products".'
    assert quotes_outside(text, [OTHER, PARAGRAPH]) == []


def test_a_paraphrase_inside_quotation_marks_is_outside() -> None:
    text = 'Revenue rose on "higher HIV product sales".'
    assert quotes_outside(text, [PARAGRAPH]) == ["higher HIV product sales"]


def test_two_sentences_joined_into_one_quotation_are_outside() -> None:
    text = 'Management cites "higher sales of HIV products, partially offset by lower sales".'
    assert quotes_outside(text, [PARAGRAPH]) == [
        "higher sales of HIV products, partially offset by lower sales"
    ]


def test_a_curly_quoted_copy_passes_and_whitespace_does_not_matter() -> None:
    text = "Revenue rose “primarily due to  higher\nsales of HIV products”."
    assert quotes_outside(text, [PARAGRAPH]) == []
    # Quote characters inside the source normalise too: a curly apostrophe, a hard space.
    source = "Demand for the company’s accelerators grew in the quarter."
    assert quotes_outside("“the company's accelerators grew”", [source]) == []


def test_an_unquoted_paraphrase_is_allowed() -> None:
    text = "Revenue rose mainly because HIV products sold more, net of weaker oncology."
    assert quotes_outside(text, [PARAGRAPH]) == []


def test_a_short_quotation_is_checked_too() -> None:
    assert quotes_outside('Sales were "strong".', [PARAGRAPH]) == ["strong"]
    assert quotes_outside('Sales of "HIV products" rose.', [PARAGRAPH]) == []


def test_case_and_punctuation_are_not_forgiven() -> None:
    assert quotes_outside('"Primarily due to higher sales"', [PARAGRAPH]) == [
        "Primarily due to higher sales"
    ]
    assert quotes_outside('"increased $1.2 billion or 9%"', [PARAGRAPH]) == [
        "increased $1.2 billion or 9%"
    ]


def test_an_unclosed_quotation_runs_to_the_end_and_is_checked() -> None:
    assert quotes_outside('Revenue rose "on higher sales of everything', [PARAGRAPH]) == [
        "on higher sales of everything"
    ]


def test_with_no_sources_every_quotation_is_outside() -> None:
    assert quotes_outside('"primarily due to"', []) == ["primarily due to"]
