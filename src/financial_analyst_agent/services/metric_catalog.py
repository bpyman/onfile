"""Closed metric enum to XBRL concept candidate mapping."""

import re
from dataclasses import dataclass
from typing import Literal

from financial_analyst_agent.domain.enums import Metric
from financial_analyst_agent.domain.errors import UnknownMetricError

METRIC_CONCEPTS: dict[Metric, list[tuple[str, str]]] = {
    Metric.NET_INCOME: [
        ("us-gaap", "NetIncomeLoss"),
        ("us-gaap", "ProfitLoss"),
    ],
    Metric.REVENUE: [
        # The first of these the filing's own lines add up to wins, not merely
        # the first reported (``sec_facts._total_revenue``); a bank that tags
        # none of the totals gets net interest plus noninterest income.
        # The income statement's total first: contract revenue leaves out
        # insurance premiums, rent, financing income and membership fees
        # (Berkshire, Welltower, GM Financial, Walmart).
        ("us-gaap", "Revenues"),
        # Banks and brokers report net revenue (JPMorgan, Goldman, SoFi, American
        # Express); their contract revenue is fees only, without interest.
        ("us-gaap", "RevenuesNetOfInterestExpense"),
        # Utilities (NextEra, Duke).
        ("us-gaap", "RegulatedAndUnregulatedOperatingRevenue"),
        ("us-gaap", "RevenueFromContractWithCustomerExcludingAssessedTax"),
        ("us-gaap", "SalesRevenueNet"),
    ],
    Metric.COST_OF_REVENUE: [
        ("us-gaap", "CostOfRevenue"),
        ("us-gaap", "CostOfGoodsAndServicesSold"),
    ],
    Metric.GROSS_PROFIT: [
        ("us-gaap", "GrossProfit"),
    ],
    Metric.OPERATING_EXPENSES: [
        ("us-gaap", "OperatingExpenses"),
    ],
    Metric.OPERATING_INCOME: [
        ("us-gaap", "OperatingIncomeLoss"),
    ],
    Metric.RESEARCH_AND_DEVELOPMENT: [
        ("us-gaap", "ResearchAndDevelopmentExpense"),
        # Drug makers expense acquired in-process R&D separately (Lilly, Amgen, AbbVie).
        ("us-gaap", "ResearchAndDevelopmentExpenseExcludingAcquiredInProcessCost"),
    ],
    Metric.SELLING_GENERAL_AND_ADMINISTRATIVE: [
        ("us-gaap", "SellingGeneralAndAdministrativeExpense"),
    ],
    Metric.INTEREST_EXPENSE: [
        ("us-gaap", "InterestExpense"),
        ("us-gaap", "InterestExpenseDebt"),
    ],
    Metric.INCOME_TAX_EXPENSE: [
        ("us-gaap", "IncomeTaxExpenseBenefit"),
        ("us-gaap", "IncomeTaxExpenseBenefitContinuingOperations"),
    ],
    Metric.PRETAX_INCOME: [
        (
            "us-gaap",
            "IncomeLossFromContinuingOperationsBeforeIncomeTaxes"
            "ExtraordinaryItemsNoncontrollingInterest",
        ),
        ("us-gaap", "IncomeLossFromContinuingOperationsBeforeIncomeTaxes"),
        ("us-gaap", "PretaxIncomeLoss"),
    ],
    Metric.EPS_DILUTED: [
        ("us-gaap", "EarningsPerShareDiluted"),
        ("us-gaap", "EarningsPerShareBasicAndDiluted"),
    ],
    Metric.EPS_BASIC: [
        ("us-gaap", "EarningsPerShareBasic"),
        ("us-gaap", "EarningsPerShareBasicAndDiluted"),
    ],
    Metric.OPERATING_CASH_FLOW: [
        ("us-gaap", "NetCashProvidedByUsedInOperatingActivities"),
        ("us-gaap", "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations"),
    ],
    Metric.CAPITAL_EXPENDITURE: [
        ("us-gaap", "PaymentsToAcquirePropertyPlantAndEquipment"),
        ("us-gaap", "PaymentsToAcquireProductiveAssets"),
        # Lilly's "purchases of property and equipment".
        ("us-gaap", "PaymentsToAcquireOtherPropertyPlantAndEquipment"),
    ],
    Metric.DEPRECIATION_AMORTIZATION: [
        ("us-gaap", "DepreciationDepletionAndAmortization"),
        ("us-gaap", "DepreciationAmortizationAndAccretionNet"),
        ("us-gaap", "DepreciationAndAmortization"),
    ],
    Metric.DIVIDENDS_PAID: [
        ("us-gaap", "PaymentsOfDividendsCommonStock"),
        ("us-gaap", "PaymentsOfDividends"),
    ],
    Metric.DIVIDENDS_PER_SHARE: [
        # What a quarter paid first: Walmart declares a year's dividend in its
        # first quarter, so its declared figure reads $0.00 for the other three.
        ("us-gaap", "CommonStockDividendsPerShareCashPaid"),
        ("us-gaap", "CommonStockDividendsPerShareDeclared"),
    ],
    Metric.CASH: [
        ("us-gaap", "CashAndCashEquivalentsAtCarryingValue"),
        ("us-gaap", "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents"),
        ("us-gaap", "Cash"),
    ],
    Metric.SHAREHOLDERS_EQUITY: [
        ("us-gaap", "StockholdersEquity"),
        ("us-gaap", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"),
    ],
}
METRIC_CONCEPTS[Metric.DEPRECIATION] = [("us-gaap", "Depreciation")]
METRIC_CONCEPTS[Metric.AMORTIZATION_OF_INTANGIBLES] = [
    ("us-gaap", "AmortizationOfIntangibleAssets")
]
# The trailing year reads the same concepts as the quarter it sums.
METRIC_CONCEPTS[Metric.NET_INCOME_TTM] = METRIC_CONCEPTS[Metric.NET_INCOME]
METRIC_CONCEPTS[Metric.NET_INTEREST_INCOME] = [("us-gaap", "InterestIncomeExpenseNet")]
METRIC_CONCEPTS[Metric.NONINTEREST_INCOME] = [("us-gaap", "NoninterestIncome")]

# Totals that tell which revenue line is the income statement's total: costs and
# expenses plus operating income add up to it (Verra Mobility tags one segment
# as Revenues). Read with the catalog's own concepts.
REVENUE_CHECK_CONCEPTS: tuple[tuple[str, str], ...] = (("us-gaap", "CostsAndExpenses"),)
# Weighted diluted shares beside a per-share figure: a split shows as a jump.
SHARE_COUNT_CONCEPT = ("us-gaap", "WeightedAverageNumberOfDilutedSharesOutstanding")

# Costs that show "cost of revenue" is not all of a company's cost of revenue: an
# insurer's benefits and claims (UnitedHealth's medical costs) sit beside the cost
# of the products it sells. Revenue minus that cost is not a gross profit.
GROSS_PROFIT_EXCLUDING_CONCEPTS: tuple[tuple[str, str], ...] = (
    ("us-gaap", "PolicyholderBenefitsAndClaimsIncurredNet"),
    ("us-gaap", "PolicyholderBenefitsAndClaimsIncurredHealthCare"),
    ("us-gaap", "BenefitsLossesAndExpenses"),
)

# Every concept any metric or check reads; the rest of a facts file is dropped.
READ_CONCEPTS: frozenset[tuple[str, str]] = (
    frozenset(concept for candidates in METRIC_CONCEPTS.values() for concept in candidates)
    | frozenset(GROSS_PROFIT_EXCLUDING_CONCEPTS)
    | frozenset(REVENUE_CHECK_CONCEPTS)
    | {SHARE_COUNT_CONCEPT}
)

ValueKind = Literal["usd", "percent", "multiple", "per_share"]


@dataclass(frozen=True)
class MetricDisplay:
    """How the window names a metric and writes its value."""

    label: str
    # Dollars ("$1.20 B"), a percent ("27.1%"), a multiple ("12.4x") or per share ("$1.57").
    value_kind: ValueKind = "usd"


# Every metric the window can show, with its label and kind of value: the ones
# an analyst asks for, a formula's inputs, and the parts of a derived figure.
# Adding a metric adds its entry here (ADR 0005).
METRIC_DISPLAY: dict[str, MetricDisplay] = {
    "revenue": MetricDisplay("Revenue"),
    "cost_of_revenue": MetricDisplay("Cost of revenue"),
    "gross_profit": MetricDisplay("Gross profit"),
    "operating_expenses": MetricDisplay("Operating expenses"),
    "operating_income": MetricDisplay("Operating income"),
    "net_income": MetricDisplay("Net income"),
    "research_and_development": MetricDisplay("Research and development"),
    "selling_general_and_administrative": MetricDisplay("Selling, general and administrative"),
    "interest_expense": MetricDisplay("Interest expense"),
    "income_tax_expense": MetricDisplay("Income tax expense"),
    "pretax_income": MetricDisplay("Pretax income"),
    "eps_diluted": MetricDisplay("Diluted EPS", "per_share"),
    "eps_basic": MetricDisplay("Basic EPS", "per_share"),
    "operating_cash_flow": MetricDisplay("Operating cash flow"),
    "capital_expenditure": MetricDisplay("Capital expenditure"),
    "depreciation_amortization": MetricDisplay("Depreciation and amortization"),
    "dividends_paid": MetricDisplay("Dividends paid"),
    "dividends_per_share": MetricDisplay("Dividends per share", "per_share"),
    "cash": MetricDisplay("Cash and equivalents"),
    "shareholders_equity": MetricDisplay("Shareholders' equity"),
    "net_income_ttm": MetricDisplay("Net income (trailing year)"),
    "depreciation": MetricDisplay("Depreciation"),
    "amortization_of_intangibles": MetricDisplay("Amortization of intangibles"),
    "net_interest_income": MetricDisplay("Net interest income"),
    "noninterest_income": MetricDisplay("Noninterest income"),
    "gross_margin": MetricDisplay("Gross margin", "percent"),
    "operating_margin": MetricDisplay("Operating margin", "percent"),
    "net_margin": MetricDisplay("Net margin", "percent"),
    "rd_to_sales": MetricDisplay("R&D to sales", "percent"),
    "sga_ratio": MetricDisplay("SG&A ratio", "percent"),
    "effective_tax_rate": MetricDisplay("Effective tax rate", "percent"),
    "interest_coverage": MetricDisplay("Interest coverage", "multiple"),
    "free_cash_flow": MetricDisplay("Free cash flow"),
    "ebitda": MetricDisplay("EBITDA"),
    "return_on_equity": MetricDisplay("Return on equity", "percent"),
    "pe_ratio": MetricDisplay("P/E ratio", "multiple"),
    "market_cap": MetricDisplay("Market cap"),
    "price": MetricDisplay("Share price", "per_share"),
}

# Per-share amounts are reported in USD per share and are never derived by
# subtraction: the share count moves during the year (ADR 0007).
PER_SHARE_METRICS: frozenset[Metric] = frozenset(
    metric for metric in Metric if METRIC_DISPLAY[metric].value_kind == "per_share"
)
# Balance-sheet amounts: one value at the report date, never a duration (ADR 0008).
INSTANT_METRICS: frozenset[Metric] = frozenset({Metric.CASH, Metric.SHAREHOLDERS_EQUITY})
# Sums over the four quarters ending on the report date (ADR 0008).
TRAILING_YEAR_METRICS: frozenset[Metric] = frozenset({Metric.NET_INCOME_TTM})


def metric_unit(metric: Metric) -> str:
    """The companyfacts unit a metric is reported in."""
    return "USD/shares" if metric in PER_SHARE_METRICS else "USD"

MetricPhraseKind = Literal["unique", "ambiguous", "unknown"]


@dataclass(frozen=True)
class MetricPhraseResolution:
    kind: MetricPhraseKind
    metric: str | None = None
    metrics: tuple[str, ...] = ()
    candidates: tuple[str, ...] = ()

    @property
    def unique_metrics(self) -> tuple[str, ...]:
        """Metrics named by a unique resolution; empty for any other kind."""
        return self.metrics if self.kind == "unique" else ()


def get_concept_candidates(metric: Metric) -> list[tuple[str, str]]:
    """Return ordered (taxonomy, concept) candidates for a validated metric."""
    return METRIC_CONCEPTS[metric]


def parse_metric(term: str) -> Metric:
    """Parse a user metric term into a closed Metric enum value."""
    normalized = term.strip().lower().replace(" ", "_").replace("-", "_")
    try:
        return Metric(normalized)
    except ValueError:
        raise UnknownMetricError(
            f"Unknown metric '{term}'",
            details={"term": term, "allowed": [metric.value for metric in Metric]},
        ) from None


# A phrase that names a set of metrics rather than one ("margins").
ALL_MARGINS = "gross_margin+operating_margin+net_margin"


def _named_metrics(slug: str) -> tuple[str, ...]:
    return tuple(slug.split("+"))


_UNIQUE_PHRASES: tuple[tuple[str, str], ...] = (
    ("cost of goods and services", "cost_of_revenue"),
    ("cost of goods sold", "cost_of_revenue"),
    ("cost of sales", "cost_of_revenue"),
    ("cost of revenue", "cost_of_revenue"),
    ("cost_of_revenue", "cost_of_revenue"),
    ("cogs", "cost_of_revenue"),
    ("selling general and administrative", "selling_general_and_administrative"),
    ("selling, general and administrative", "selling_general_and_administrative"),
    ("selling_general_and_administrative", "selling_general_and_administrative"),
    ("sg&a ratio", "sga_ratio"),
    ("sga ratio", "sga_ratio"),
    ("sga_ratio", "sga_ratio"),
    ("sg&a", "selling_general_and_administrative"),
    ("sga", "selling_general_and_administrative"),
    ("research and development to sales", "rd_to_sales"),
    ("research and development", "research_and_development"),
    ("research_and_development", "research_and_development"),
    ("r&d to sales", "rd_to_sales"),
    ("rd to sales", "rd_to_sales"),
    ("r&d spend", "research_and_development"),
    ("r&d intensity", "rd_to_sales"),
    ("rd_to_sales", "rd_to_sales"),
    ("r&d", "research_and_development"),
    ("operating expenses", "operating_expenses"),
    ("operating_expenses", "operating_expenses"),
    ("operating costs", "operating_expenses"),
    ("opex", "operating_expenses"),
    ("operating profit margin", "operating_margin"),
    ("operating income", "operating_income"),
    ("operating_income", "operating_income"),
    ("operating profit", "operating_income"),
    ("operating earnings", "operating_income"),
    ("ebit", "operating_income"),
    ("operating margin", "operating_margin"),
    ("operating_margin", "operating_margin"),
    ("operating margins", "operating_margin"),
    ("ebit margin", "operating_margin"),
    ("gross profit margin", "gross_margin"),
    ("gross profit", "gross_profit"),
    ("gross_profit", "gross_profit"),
    ("gross margin", "gross_margin"),
    ("gross_margin", "gross_margin"),
    ("gross margins", "gross_margin"),
    ("effective tax rate", "effective_tax_rate"),
    ("effective_tax_rate", "effective_tax_rate"),
    ("tax rate", "effective_tax_rate"),
    ("income tax expense", "income_tax_expense"),
    ("income_tax_expense", "income_tax_expense"),
    ("tax expense", "income_tax_expense"),
    ("income tax", "income_tax_expense"),
    ("interest coverage ratio", "interest_coverage"),
    ("interest coverage", "interest_coverage"),
    ("interest_coverage", "interest_coverage"),
    ("interest expense", "interest_expense"),
    ("interest_expense", "interest_expense"),
    ("interest costs", "interest_expense"),
    ("income before tax", "pretax_income"),
    ("pre-tax income", "pretax_income"),
    ("pretax income", "pretax_income"),
    ("pretax_income", "pretax_income"),
    ("diluted earnings per share", "eps_diluted"),
    ("basic earnings per share", "eps_basic"),
    ("earnings per share", "eps_diluted"),
    ("diluted eps", "eps_diluted"),
    ("basic eps", "eps_basic"),
    ("eps_diluted", "eps_diluted"),
    ("eps_basic", "eps_basic"),
    ("per share", "eps_diluted"),
    ("eps", "eps_diluted"),
    ("free cash flow", "free_cash_flow"),
    ("free_cash_flow", "free_cash_flow"),
    ("fcf", "free_cash_flow"),
    ("operating cash flow", "operating_cash_flow"),
    ("cash flow from operations", "operating_cash_flow"),
    ("cash flow from operating activities", "operating_cash_flow"),
    ("cash from operations", "operating_cash_flow"),
    ("operating_cash_flow", "operating_cash_flow"),
    ("capital expenditures", "capital_expenditure"),
    ("capital expenditure", "capital_expenditure"),
    ("capital_expenditure", "capital_expenditure"),
    ("capital spending", "capital_expenditure"),
    ("capex", "capital_expenditure"),
    ("net profit margin", "net_margin"),
    ("net income", "net_income"),
    ("net_income", "net_income"),
    ("net profit", "net_income"),
    ("net earnings", "net_income"),
    ("earnings", "net_income"),
    ("bottom line", "net_income"),
    ("net margin", "net_margin"),
    ("net_margin", "net_margin"),
    ("net margins", "net_margin"),
    ("net sales", "revenue"),
    ("sales", "revenue"),
    ("revenue", "revenue"),
    ("rev", "revenue"),
    ("revs", "revenue"),
    ("top line", "revenue"),
    ("topline", "revenue"),
    ("turnover", "revenue"),
    # "How much did Apple earn?" asks for its profit after everything.
    ("earn", "net_income"),
    ("earned", "net_income"),
    ("depreciation and amortization", "depreciation_amortization"),
    ("depreciation & amortization", "depreciation_amortization"),
    ("depreciation_amortization", "depreciation_amortization"),
    ("d&a", "depreciation_amortization"),
    ("depreciation", "depreciation_amortization"),
    ("research spending", "research_and_development"),
    ("research spend", "research_and_development"),
    ("spend on research", "research_and_development"),
    ("spending on research", "research_and_development"),
    ("research costs", "research_and_development"),
    ("research expenses", "research_and_development"),
    ("ebitda", "ebitda"),
    ("return on equity", "return_on_equity"),
    ("return on shareholders equity", "return_on_equity"),
    ("return_on_equity", "return_on_equity"),
    ("roe", "return_on_equity"),
    ("price to earnings ratio", "pe_ratio"),
    ("price to earnings", "pe_ratio"),
    ("price-to-earnings ratio", "pe_ratio"),
    ("price-to-earnings", "pe_ratio"),
    ("price/earnings", "pe_ratio"),
    ("p/e ratio", "pe_ratio"),
    ("pe ratio", "pe_ratio"),
    ("p/e", "pe_ratio"),
    ("pe", "pe_ratio"),
    ("pe_ratio", "pe_ratio"),
    ("earnings multiple", "pe_ratio"),
    ("stock price", "price"),
    ("share price", "price"),
    ("stock prices", "price"),
    ("share prices", "price"),
    ("price per share", "price"),
    ("trading at", "price"),
    ("price", "price"),
    ("cash and cash equivalents", "cash"),
    ("cash and equivalents", "cash"),
    ("cash on hand", "cash"),
    ("cash balance", "cash"),
    ("cash pile", "cash"),
    ("cash position", "cash"),
    ("cash", "cash"),
    ("shareholders equity", "shareholders_equity"),
    ("shareholders' equity", "shareholders_equity"),
    ("stockholders equity", "shareholders_equity"),
    ("stockholders' equity", "shareholders_equity"),
    ("shareholder equity", "shareholders_equity"),
    ("shareholders_equity", "shareholders_equity"),
    ("book value", "shareholders_equity"),
    ("dividends per share", "dividends_per_share"),
    ("dividend per share", "dividends_per_share"),
    ("dividends_per_share", "dividends_per_share"),
    ("dps", "dividends_per_share"),
    ("dividends paid", "dividends_paid"),
    ("dividend payments", "dividends_paid"),
    ("dividend payouts", "dividends_paid"),
    ("cash dividends", "dividends_paid"),
    ("dividends_paid", "dividends_paid"),
    ("market capitalization", "market_cap"),
    ("market cap", "market_cap"),
    ("market_cap", "market_cap"),
    ("mkt cap", "market_cap"),
    ("market value", "market_cap"),
    ("valuation", "market_cap"),
    ("valued", "market_cap"),
    ("worth", "market_cap"),
    ("net worth", "shareholders_equity"),
    # Plural: "compare the margins" asks for all three.
    ("profit margins", ALL_MARGINS),
    ("margins", ALL_MARGINS),
)

_AMBIGUOUS_PHRASES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("profit margin", ("gross_margin", "operating_margin", "net_margin")),
    ("cash flow", ("operating_cash_flow", "free_cash_flow")),
    ("profit", ("gross_profit", "operating_income", "net_income")),
    ("income", ("net_income", "operating_income")),
    ("margin", ("gross_margin", "operating_margin", "net_margin")),
    ("gross", ("gross_profit", "gross_margin")),
    ("net", ("net_income", "net_margin")),
    ("interest", ("interest_expense", "interest_coverage")),
    ("tax", ("income_tax_expense", "effective_tax_rate")),
    ("dividends", ("dividends_per_share", "dividends_paid")),
    ("dividend", ("dividends_per_share", "dividends_paid")),
    ("equity", ("shareholders_equity", "return_on_equity")),
    # "How much money did Apple make?": the sales or what was left of them.
    ("money", ("revenue", "net_income")),
    # "Apple's biggest expense" ("costs" stays unknown, ADR 0004).
    ("expenses", ("cost_of_revenue", "operating_expenses")),
    ("expense", ("cost_of_revenue", "operating_expenses")),
)
# Parts of a company and operating figures the filings' structured data does
# not break out: "AWS revenue" is Amazon's total, "deliveries" is not a figure.
_SEGMENT_WORDS = re.compile(
    r"\b(?:aws|amazon web services|azure|iphones?|ipads?|macs?|wearables|google cloud"
    r"|youtube|instagram|whatsapp|xbox|data cent(?:er|re)s?|segments?|divisions?"
    r"|business units?|same[- ]store sales|comparable sales|comps|per employee|per user"
    r"|arpu|deliveries|subscribers|users|units sold|backlog|bookings|store count)\b",
    re.IGNORECASE,
)


def segment_term(question: str) -> str | None:
    """The segment or operating figure a question names ("iPhone", "per employee")."""
    match = _SEGMENT_WORDS.search(question)
    return match.group(0) if match is not None else None


def segment_note(term: str) -> str:
    return (
        f"Filings' structured data reports company-wide totals, not segments or "
        f"operating figures such as “{term}”, so this shows the company-wide figure."
    )
# A unique phrase that is part of a longer name it does not mean: the "cash"
# in "cash flow" and "cash from operations", the "price" in "price target".
_NOT_FOLLOWED_BY: dict[str, re.Pattern[str]] = {
    "cash": re.compile(r"\s+(?:flows?|from|generation|burn|conversion)\b"),
    "price": re.compile(r"\s+(?:targets?|increases?|hikes?|cuts?|war|elasticity)\b"),
}


def metric_phrases() -> tuple[str, ...]:
    """Every phrase the catalog reads as a metric, unique or ambiguous, longest first."""
    phrases = {phrase for phrase, _ in _UNIQUE_PHRASES} | {
        phrase for phrase, _ in _AMBIGUOUS_PHRASES
    }
    return tuple(sorted(phrases, key=len, reverse=True))


def _phrase_spans(query: str, phrase: str) -> list[tuple[int, int]]:
    return [
        (match.start(), match.end()) for match in re.finditer(rf"\b{re.escape(phrase)}\b", query)
    ]


def _nonoverlapping_unique_matches(query: str) -> list[tuple[int, int, str]]:
    found: list[tuple[int, int, str]] = []
    for phrase, metric in _UNIQUE_PHRASES:
        excluded = _NOT_FOLLOWED_BY.get(phrase)
        for start, end in _phrase_spans(query, phrase):
            if excluded is not None and excluded.match(query, end):
                continue
            found.append((start, end, metric))
    found.sort(key=lambda item: (item[0] - item[1], item[0]))
    accepted: list[tuple[int, int, str]] = []
    for start, end, metric in found:
        if any(
            not (end <= other_start or start >= other_end) for other_start, other_end, _ in accepted
        ):
            continue
        accepted.append((start, end, metric))
    accepted.sort(key=lambda item: item[0])
    return accepted


def _spans_overlap(start: int, end: int, occupied: list[tuple[int, int]]) -> bool:
    return any(
        not (end <= other_start or start >= other_end) for other_start, other_end in occupied
    )


def _nonoverlapping_ambiguous_matches(
    query: str, occupied: list[tuple[int, int]]
) -> list[tuple[int, int, tuple[str, ...]]]:
    found: list[tuple[int, int, tuple[str, ...]]] = []
    for phrase, candidates in _AMBIGUOUS_PHRASES:
        for start, end in _phrase_spans(query, phrase):
            if _spans_overlap(start, end, occupied):
                continue
            found.append((start, end, candidates))
    found.sort(key=lambda item: (item[0] - item[1], item[0]))
    accepted: list[tuple[int, int, tuple[str, ...]]] = []
    accepted_spans: list[tuple[int, int]] = []
    for start, end, candidates in found:
        if _spans_overlap(start, end, accepted_spans):
            continue
        accepted.append((start, end, candidates))
        accepted_spans.append((start, end))
    accepted.sort(key=lambda item: item[0])
    return accepted


def resolve_metric_phrases(query: str) -> tuple[MetricPhraseResolution, ...]:
    """Classify each metric phrase in the user question, left to right."""
    normalized = query.casefold()
    unique_matches = _nonoverlapping_unique_matches(normalized)
    occupied = [(start, end) for start, end, _metric in unique_matches]
    ambiguous_matches = _nonoverlapping_ambiguous_matches(normalized, occupied)

    ordered: list[tuple[int, MetricPhraseResolution]] = [
        (
            start,
            MetricPhraseResolution(
                kind="unique",
                metric=None if "+" in metric else metric,
                metrics=_named_metrics(metric),
            ),
        )
        for start, _end, metric in unique_matches
    ]
    ordered.extend(
        (start, MetricPhraseResolution(kind="ambiguous", candidates=candidates))
        for start, _end, candidates in ambiguous_matches
    )
    ordered.sort(key=lambda item: item[0])
    return tuple(resolution for _start, resolution in ordered)


def resolve_metric_phrase(query: str) -> MetricPhraseResolution:
    """Classify metric phrases for the one-shot turn seam."""
    phrases = resolve_metric_phrases(query)
    if not phrases:
        return MetricPhraseResolution(kind="unknown")
    for phrase in phrases:
        if phrase.kind == "ambiguous":
            return _with_prefixed_metric(query, phrase)
    uniques = [phrase for phrase in phrases if phrase.kind == "unique"]
    if len(uniques) == 1:
        return uniques[0]
    if len(uniques) > 1:
        # "Apple's revenue and Microsoft's revenue" names one metric twice.
        metrics = tuple(dict.fromkeys(metric for phrase in uniques for metric in phrase.metrics))
        if len(metrics) == 1:
            return MetricPhraseResolution(kind="unique", metric=metrics[0], metrics=metrics)
        return MetricPhraseResolution(kind="unique", metrics=metrics)
    return MetricPhraseResolution(kind="unknown")


def _with_prefixed_metric(
    query: str, phrase: MetricPhraseResolution
) -> MetricPhraseResolution:
    """Offer the metric named just before "margin" ("free cash flow margin").

    The catalog has no such ratio, but the metric itself is a likely answer and
    the margins alone would not include it.
    """
    normalized = query.casefold()
    unique = _nonoverlapping_unique_matches(normalized)
    occupied = [(start, end) for start, end, _metric in unique]
    ambiguous = _nonoverlapping_ambiguous_matches(normalized, occupied)
    prefixed = [
        named
        for _start, end, metric in unique
        for amb_start, _amb_end, _candidates in ambiguous
        if normalized[end:amb_start].strip() == ""
        for named in _named_metrics(metric)
    ]
    if not prefixed:
        return phrase
    candidates = tuple(dict.fromkeys([*prefixed, *phrase.candidates]))
    return MetricPhraseResolution(kind="ambiguous", candidates=candidates)
