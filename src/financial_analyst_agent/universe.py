"""Dated universe snapshot: membership freeze for ranking."""

import json
import re
from collections import defaultdict
from collections.abc import Container, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, Field

from financial_analyst_agent.domain.errors import IneligibleIssuerError
from financial_analyst_agent.domain.serialization import DecimalStr

DEFAULT_SNAPSHOT_PATH = Path(__file__).parent / "data" / "universe_snapshot.json"
_INELIGIBLE_ISSUERS_PATH = Path(__file__).parent / "data" / "ineligible_issuers.json"
_SEC_FILER_NAMES_PATH = Path(__file__).parent / "data" / "sec_filer_names.json"
_FORMER_NAMES_PATH = Path(__file__).parent / "data" / "former_names.json"

US_EXCHANGES: frozenset[str] = frozenset(
    {
        "NYSE",
        "NASDAQ",
        "AMEX",
        "NYSEARCA",
        "NYSEAMERICAN",
        "NASDAQGS",
        "NASDAQGM",
        "NASDAQCM",
    }
)

INDUSTRY_ALIASES: dict[str, str] = {
    "healthcare": "Healthcare",
    "health care": "Healthcare",
    "finance": "Financial Services",
    "financials": "Financial Services",
    "financial services": "Financial Services",
    "technology": "Technology",
    "tech": "Technology",
    "information technology": "Technology",
    # GICS sector names for the snapshot's own (FMP) sectors.
    "consumer staples": "Consumer Defensive",
    "staples": "Consumer Defensive",
    "consumer discretionary": "Consumer Cyclical",
    "communications": "Communication Services",
    "materials": "Basic Materials",
}

# NYSE/NASDAQ product suffixes: preferreds, units, warrants, rights — not common shares.
_NON_COMMON_TICKER = re.compile(
    r"(?:-P[A-Z]?|-U(?:N)?|-W(?:S|T)?|-R)$",
    re.IGNORECASE,
)
_COMPACT_NASDAQ_NON_COMMON_TICKER = re.compile(r"^[A-Z]{4}[URW]$", re.IGNORECASE)
# FMP puts the instrument description in companyName; there is no securityType field.
_INSTRUMENT_TITLE = re.compile(
    r"\bpfd\b|preferred\s+stock|perpetual\s+preferred|\bwarrants?\b|"
    r"collateral\s+tr(?:ust|\b)|tr\s+secs|capital\s+trust|"
    r"notes?\s+due|senior\s+notes|"
    r"\d+(?:\.\d+)?\s*%|"
    r"\b(?:sr|senior)\s+nts?\b|"
    r"jr\s+sub(?:ordinated)?\s+nts?\b|"
    r"index\s+plus\s+trust|"
    r"\btrust\s+(?:for|series)\b|"
    r"\bstrats\b",
    re.IGNORECASE,
)
# Empirically vehicle-dominated FMP industries. Asset Management is not in this
# set: it mixes BlackRock with BDCs. Residual lookalikes are CIKs in
# ineligible_issuers.json (ADR 0001).
_NON_OPERATING_INDUSTRIES = frozenset(
    {
        "shell companies",
        "financial - conglomerates",
    }
)


def _ineligible_issuer_ciks(path: Path = _INELIGIBLE_ISSUERS_PATH) -> frozenset[str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return frozenset(str(issuer["cik"]) for issuer in payload["issuers"])


INELIGIBLE_ISSUER_CIKS = _ineligible_issuer_ciks()


def sec_filer_names(path: Path = _SEC_FILER_NAMES_PATH) -> tuple[tuple[str, str], ...]:
    """(ticker, SEC name) of listed operating filers the snapshot leaves out.

    Subsidiaries that file their own 10-Qs (Southern California Edison) and
    other listings outside the freeze; scripts/build_sec_filer_names.py writes them.
    """
    payload = json.loads(path.read_text(encoding="utf-8"))
    return tuple((filer["ticker"], filer["name"]) for filer in payload["filers"])


def former_names(path: Path = _FORMER_NAMES_PATH) -> tuple[tuple[str, str], ...]:
    """(ticker, name) of names larger companies used to file under ("Facebook Inc").

    scripts/build_former_names.py writes them from SEC submissions.
    """
    payload = json.loads(path.read_text(encoding="utf-8"))
    return tuple((row["ticker"], row["name"]) for row in payload["names"])


def ineligible_issuers(path: Path = _INELIGIBLE_ISSUERS_PATH) -> tuple[tuple[str, str], ...]:
    """(ticker, SEC name) of the funds and other listings the analyst does not cover."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    return tuple(
        (str(issuer["ticker"]), str(issuer.get("name") or ""))
        for issuer in payload["issuers"]
        if issuer.get("ticker")
    )


# The SEC name of each ineligible issuer by ticker, for a note that names a fund
# the recorded runtime cannot identify ("SPY").
INELIGIBLE_ISSUER_NAMES: dict[str, str] = {
    ticker.upper(): name for ticker, name in ineligible_issuers()
}


class UniverseCompany(BaseModel):
    cik: str = Field(min_length=10, max_length=10, pattern=r"^\d{10}$")
    name: str
    ticker: str
    sector: str
    exchange: str = ""
    market_cap: DecimalStr
    # Share price at the snapshot's as_of, from the same vendor row as market_cap.
    # Snapshots built before prices were recorded leave it out.
    price: DecimalStr | None = None
    is_etf: bool = False
    is_fund: bool = False
    industry: str = ""
    # Foreign private issuers (20-F/40-F) have no 10-Q facts to rank on.
    # Older snapshots predate the flag, so absent means it files quarterly.
    files_quarterly: bool = True


def is_common_operating_listing(company: UniverseCompany) -> bool:
    """True for common shares of operating issuers, not funds, shells, or structured products."""
    return _is_common_share(company) and _is_operating_issuer(company)


def sec_identity_is_operating(cik: str, title: str) -> bool:
    """Judge a looked-up company with what SEC identity shows (ADR 0002).

    The ineligible CIK list and instrument words in the SEC title ("5.25% Notes",
    "Capital Trust") mark a non-operating listing. Ticker suffixes do not: a
    utility or insurer whose only listed shares are preferreds (Southern
    California Edison) still files 10-Qs as an operating company.
    """
    return cik not in INELIGIBLE_ISSUER_CIKS and _INSTRUMENT_TITLE.search(title) is None


def require_operating(cik: str, title: str, listed_ciks: Container[str]) -> None:
    """Refuse a company that is not an operating company (ADR 0001, 0002).

    A CIK on the ineligible list is never operating, even a snapshot member's
    listed there since the snapshot was built. A snapshot member is otherwise
    operating: the snapshot already applied the membership rule. Any other
    company is judged by its SEC title.
    """
    if cik in INELIGIBLE_ISSUER_CIKS or (
        cik not in listed_ciks and not sec_identity_is_operating(cik, title)
    ):
        raise IneligibleIssuerError(
            f"{title} is not an operating company (it is a fund, business "
            "development company or similar listing), so its 10-Q figures are "
            "outside what this analyst covers.",
            details={"cik": cik},
        )


def _is_common_share(company: UniverseCompany) -> bool:
    if company.is_etf or company.is_fund:
        return False
    if _NON_COMMON_TICKER.search(company.ticker.strip()):
        return False
    compact_nasdaq_product = _COMPACT_NASDAQ_NON_COMMON_TICKER.fullmatch(company.ticker.strip())
    if company.exchange.upper().startswith("NASDAQ") and compact_nasdaq_product:
        return False
    return _INSTRUMENT_TITLE.search(company.name) is None


def _is_operating_issuer(company: UniverseCompany) -> bool:
    if company.cik in INELIGIBLE_ISSUER_CIKS:
        return False
    return company.industry.strip().casefold() not in _NON_OPERATING_INDUSTRIES


def preferred_listing(rows: Sequence[UniverseCompany]) -> UniverseCompany:
    """Pick the common operating listing for one CIK.

    Note/preferred tickers are often a longer extension of the common symbol
    (SO vs SOMN) and can carry inflated vendor market caps.
    """
    listings = list(rows)
    if len(listings) == 1:
        return listings[0]
    tickers = [row.ticker.strip().upper() for row in listings]
    stems = [
        row
        for row, ticker in zip(listings, tickers, strict=True)
        if not any(ticker != other and ticker.startswith(other) for other in tickers)
    ]
    if not stems:
        stems = listings
    return min(stems, key=lambda row: (len(row.ticker), -row.market_cap))


def _primary_or_preferred(rows: Sequence[UniverseCompany], primary: str | None) -> UniverseCompany:
    for row in rows:
        if primary is not None and row.ticker.strip().upper() == primary:
            return row
    return preferred_listing(rows)


class UniverseSnapshot(BaseModel):
    as_of: datetime
    source: str = "universe_snapshot"
    companies: list[UniverseCompany] = Field(default_factory=list)


def load_universe_snapshot(path: Path | None = None) -> UniverseSnapshot:
    snapshot_path = path or DEFAULT_SNAPSHOT_PATH
    return UniverseSnapshot.model_validate_json(snapshot_path.read_text(encoding="utf-8"))


def write_universe_snapshot(snapshot: UniverseSnapshot, path: Path | None = None) -> Path:
    snapshot_path = path or DEFAULT_SNAPSHOT_PATH
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    snapshot_path.write_text(
        _snapshot_json(snapshot) + "\n",
        encoding="utf-8",
    )
    return snapshot_path


def _snapshot_json(snapshot: UniverseSnapshot) -> str:
    payload = snapshot.model_dump(mode="json")
    for company in payload["companies"]:
        if not company.get("industry"):
            company.pop("industry", None)
        if company.get("price") is None:
            company.pop("price", None)
        # Only exceptions are written, so annotating a snapshot touches only them.
        if company.get("files_quarterly", True):
            company.pop("files_quarterly", None)
    return json.dumps(payload, indent=2)


def build_universe_snapshot(
    rows: Sequence[UniverseCompany],
    *,
    as_of: datetime,
    source: str = "universe_snapshot",
    primary_tickers: Mapping[str, str] | None = None,
) -> UniverseSnapshot:
    """Filter a vendor dump into the dated operating-company freeze the rank adapter reads.

    ``primary_tickers`` maps a CIK to the ticker SEC lists first for it. When
    that listing survives the filters it wins: a note on its own stem (Comcast's
    CCZ beside CMCSA, Aegon's AEFC beside AEG) is otherwise indistinguishable
    from a share class.
    """
    eligible = [
        row
        for row in rows
        if is_common_operating_listing(row) and row.exchange.upper() in US_EXCHANGES and row.sector
    ]
    eligible.sort(key=lambda row: row.market_cap, reverse=True)
    by_cik: dict[str, list[UniverseCompany]] = defaultdict(list)
    for row in eligible:
        by_cik[row.cik].append(row)
    primary = primary_tickers or {}
    companies = [_primary_or_preferred(group, primary.get(cik)) for cik, group in by_cik.items()]
    companies.sort(key=lambda row: row.market_cap, reverse=True)
    return UniverseSnapshot(as_of=as_of, source=source, companies=companies)


# Marks an INDUSTRY_GROUP_ALIASES value that names every industry starting
# with the text before it.
_PREFIX = "*"

# Everyday words for groups narrower than a sector, matched against each
# company's ``industry``. A value ending in "*" matches every industry with
# that prefix ("Banks -*" covers "Banks - Regional" and "Banks - Diversified";
# "Oil & Gas*" covers "Oil & Gas Integrated" and "Oil & Gas Midstream").
INDUSTRY_GROUP_ALIASES: dict[str, tuple[str, ...]] = {
    "semiconductor": ("Semiconductors",),
    "semi": ("Semiconductors",),
    "chip": ("Semiconductors",),
    "chipmaker": ("Semiconductors",),
    "chip maker": ("Semiconductors",),
    "software": ("Software -*",),
    "bank": ("Banks", "Banks -*"),
    "banking": ("Banks", "Banks -*"),
    # "Big banks" and "big pharma" are the money-center banks and the large drugmakers.
    "big bank": ("Banks - Diversified",),
    "big pharma": ("Drug Manufacturers - General",),
    "biotech": ("Biotechnology",),
    "pharma": ("Drug Manufacturers -*", "Medical - Pharmaceuticals"),
    "pharmaceutical": ("Drug Manufacturers -*", "Medical - Pharmaceuticals"),
    "drugmaker": ("Drug Manufacturers -*",),
    "drug maker": ("Drug Manufacturers -*",),
    "insurer": ("Insurance -*",),
    "insurance": ("Insurance -*",),
    "reit": ("REIT -*",),
    "oil": ("Oil & Gas*",),
    "oil and gas": ("Oil & Gas*",),
    "oil & gas": ("Oil & Gas*",),
    "retailer": (
        "Specialty Retail",
        "Discount Stores",
        "Department Stores",
        "Apparel - Retail",
        "Grocery Stores",
        "Home Improvement",
    ),
    "retail": (
        "Specialty Retail",
        "Discount Stores",
        "Department Stores",
        "Apparel - Retail",
        "Grocery Stores",
        "Home Improvement",
    ),
    "airline": ("Airlines, Airports & Air Services",),
    "automaker": ("Auto - Manufacturers",),
    "carmaker": ("Auto - Manufacturers",),
    "car maker": ("Auto - Manufacturers",),
    "auto": ("Auto -*",),
    "defense": ("Aerospace & Defense",),
    "aerospace": ("Aerospace & Defense",),
    "telecom": ("Telecommunications Services",),
    "medical device": ("Medical - Devices",),
    "medtech": ("Medical - Devices", "Medical - Instruments & Supplies"),
    "restaurant": ("Restaurants",),
    "hotel": ("Travel Lodging", "REIT - Hotel & Motel"),
    "lodging": ("Travel Lodging",),
    "payment": ("Financial - Credit Services",),
    "credit card": ("Financial - Credit Services",),
    "railroad": ("Railroads",),
    "beverage": ("Beverages -*",),
    "internet": ("Internet Content & Information",),
    "asset manager": ("Asset Management",),
    "asset management": ("Asset Management",),
}


@dataclass(frozen=True)
class IndustryGroup:
    """What a ranking request covers: one sector, or named industries."""

    label: str
    sector: str | None = None
    industries: frozenset[str] = frozenset()
    # "Top 10 companies by net income": every sector in the snapshot.
    everything: bool = False

    def includes(self, company: UniverseCompany) -> bool:
        if self.everything:
            return True
        if self.sector is not None:
            return company.sector == self.sector
        return company.industry in self.industries


def _singular(word: str) -> str:
    return word[:-1] if word.endswith("s") and not word.endswith("ss") else word


_GROUP_SUFFIX = re.compile(
    r"\s+(?:companies|company|stocks|firms|names|sector|industry)$", re.IGNORECASE
)


def _normalize_group(text: str) -> str:
    text = _GROUP_SUFFIX.sub("", " ".join(text.strip().casefold().split()))
    return " ".join(_singular(word) for word in text.split())


@dataclass(frozen=True)
class SnapshotGroups:
    """The sectors and industries a snapshot's members fall in, scanned once."""

    sectors: frozenset[str]
    industries: frozenset[str]

    @classmethod
    def of(cls, snapshot: UniverseSnapshot) -> "SnapshotGroups":
        return cls(
            sectors=frozenset(company.sector for company in snapshot.companies),
            industries=frozenset(
                company.industry for company in snapshot.companies if company.industry
            ),
        )


def resolve_industry(industry: str, groups: SnapshotGroups) -> str | None:
    normalized = " ".join(industry.strip().casefold().split())
    if normalized in INDUSTRY_ALIASES:
        return INDUSTRY_ALIASES[normalized]
    for sector in groups.sectors:
        if sector.casefold() == normalized:
            return sector
    return None


# The industry a ranking with none named ranks: every snapshot member.
WHOLE_MARKET = "companies"

# Words that name no industry at all ("top 10 companies", "largest US stocks",
# "biggest public companies"): rank the whole snapshot. Compared after
# ``_normalize_group``, which drops "companies" and singularizes ("us" -> "u").
_WHOLE_SNAPSHOT = frozenset(
    {"", "companie", "company", "stock", "firm", "all", "public", "u", "american",
     "listed", "businesse", "corporation"}
)


def _names(pattern: str, industry: str) -> bool:
    """Whether an alias value names a snapshot industry: equal, or its marked prefix."""
    if pattern.endswith(_PREFIX):
        return industry.startswith(pattern[: -len(_PREFIX)])
    return industry == pattern


def resolve_industry_group(industry: str, groups: SnapshotGroups) -> IndustryGroup | None:
    """A sector by name or alias, else the industries an everyday word names.

    "technology" is a sector; "semiconductors", "banks", or "software companies"
    are industries inside one, ranked on their own.
    """
    if industry.strip() and _normalize_group(industry) in _WHOLE_SNAPSHOT:
        return IndustryGroup(label="All companies", everything=True)
    sector = resolve_industry(industry, groups) or resolve_industry(
        _normalize_group(industry), groups
    )
    if sector is not None:
        return IndustryGroup(label=sector, sector=sector)
    wanted = _normalize_group(industry)
    if not wanted:
        return None
    present = groups.industries
    patterns = INDUSTRY_GROUP_ALIASES.get(wanted, ())
    matched = {name for name in present for pattern in patterns if _names(pattern, name)}
    if not matched:
        matched = {name for name in present if _normalize_group(name) == wanted}
    if not matched:
        # "regional banks" names "Banks - Regional" word for word.
        words = set(wanted.split())
        matched = {name for name in present if words <= set(_normalize_group(name).split())}
    if not matched:
        return None
    if len(matched) == 1:
        label = next(iter(matched))
    else:
        label = _GROUP_SUFFIX.sub("", " ".join(industry.split())).strip()
        label = label[:1].upper() + label[1:]
        label = re.sub(r"\breits?\b", "REITs", label, flags=re.IGNORECASE)
    return IndustryGroup(label=label, industries=frozenset(matched))


def allowed_industry_names(groups: SnapshotGroups) -> tuple[str, ...]:
    aliases = ("finance", "healthcare", "technology")
    sectors = tuple(sorted(groups.sectors))
    seen: list[str] = []
    folded: set[str] = set()
    for name in (*sectors, *aliases):
        # "healthcare" the alias repeats "Healthcare" the sector, which is kept.
        if name.casefold() not in folded:
            seen.append(name)
            folded.add(name.casefold())
    return tuple(seen)
