"""Domain enumerations."""

from enum import StrEnum


class Metric(StrEnum):
    """Closed set of directly reported quarterly metrics."""

    REVENUE = "revenue"
    COST_OF_REVENUE = "cost_of_revenue"
    GROSS_PROFIT = "gross_profit"
    OPERATING_EXPENSES = "operating_expenses"
    OPERATING_INCOME = "operating_income"
    NET_INCOME = "net_income"
    RESEARCH_AND_DEVELOPMENT = "research_and_development"
    SELLING_GENERAL_AND_ADMINISTRATIVE = "selling_general_and_administrative"
    INTEREST_EXPENSE = "interest_expense"
    INCOME_TAX_EXPENSE = "income_tax_expense"
    PRETAX_INCOME = "pretax_income"
    EPS_DILUTED = "eps_diluted"
    EPS_BASIC = "eps_basic"
    OPERATING_CASH_FLOW = "operating_cash_flow"
    CAPITAL_EXPENDITURE = "capital_expenditure"
    DEPRECIATION_AMORTIZATION = "depreciation_amortization"
    DIVIDENDS_PAID = "dividends_paid"
    DIVIDENDS_PER_SHARE = "dividends_per_share"
    # Balance-sheet amounts at the quarter's end date, not over the quarter.
    CASH = "cash"
    SHAREHOLDERS_EQUITY = "shareholders_equity"
    # Equity including noncontrolling (minority) interests.
    TOTAL_EQUITY = "total_equity"
    # Net income over the four quarters ending on the report date (ADR 0008).
    NET_INCOME_TTM = "net_income_ttm"
    # The two halves of D&A, for filers that tag no combined line (Microsoft).
    DEPRECIATION = "depreciation"
    AMORTIZATION_OF_INTANGIBLES = "amortization_of_intangibles"
    # A bank's revenue, for banks that tag no total (M&T, Huntington).
    NET_INTEREST_INCOME = "net_interest_income"
    NONINTEREST_INCOME = "noninterest_income"


class FormType(StrEnum):
    """SEC form types relevant to quarterly reporting."""

    FORM_10_Q = "10-Q"
    FORM_10_Q_A = "10-Q/A"
    FORM_10_K = "10-K"
    FORM_10_K_A = "10-K/A"


QUARTERLY_FORMS = frozenset({FormType.FORM_10_Q, FormType.FORM_10_Q_A})
ANNUAL_FORMS = frozenset({FormType.FORM_10_K, FormType.FORM_10_K_A})
# 10-Ks are kept for the fiscal fourth quarter they cover (ADR 0007).
PERIODIC_FORMS = QUARTERLY_FORMS | ANNUAL_FORMS


class DataSourceKind(StrEnum):
    """Origin of a data value."""

    SEC_XBRL = "sec_xbrl"
