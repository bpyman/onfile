"""Each metric's label and kind of value come from its catalog entry."""

from financial_analyst_agent.contracts import (
    ALLOWED_METRICS,
    FORMULA_COMPONENTS,
    MULTIPLE_FORMULAS,
    PER_SHARE_METRICS,
    PERCENT_FORMULAS,
)
from financial_analyst_agent.domain.enums import Metric
from financial_analyst_agent.presentation import chart_value_kind, format_field_name
from financial_analyst_agent.services.metric_catalog import METRIC_DISPLAY


def test_every_metric_the_window_can_show_has_a_catalog_entry() -> None:
    inputs = {name for parts in FORMULA_COMPONENTS.values() for name in parts}
    shown = {*ALLOWED_METRICS, *(metric.value for metric in Metric), *inputs}
    assert shown == set(METRIC_DISPLAY)


def test_the_value_kinds_contracts_lists_are_read_from_the_catalog() -> None:
    assert PERCENT_FORMULAS == (
        "gross_margin",
        "operating_margin",
        "net_margin",
        "rd_to_sales",
        "sga_ratio",
        "effective_tax_rate",
        "return_on_equity",
    )
    assert MULTIPLE_FORMULAS == ("interest_coverage", "pe_ratio")
    assert PER_SHARE_METRICS == ("eps_diluted", "eps_basic", "dividends_per_share", "price")


def test_the_presentation_names_and_formats_a_metric_from_its_entry() -> None:
    assert format_field_name("pe_ratio") == "P/E ratio"
    # Spelt out once in the catalog rather than title-cased from the slug.
    assert format_field_name("amortization_of_intangibles") == "Amortization of intangibles"
    assert format_field_name("company_name") == "Company"
    assert chart_value_kind("price") == "per_share"
    assert chart_value_kind("revenue") == "usd"
