"""Rank companies from a dated universe snapshot."""

from collections.abc import Collection
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from financial_analyst_agent.domain.errors import (
    AmbiguousCompanyError,
    CompanyNotFoundError,
    UnknownIndustryError,
)
from financial_analyst_agent.issuer_index import IssuerIndex, normalize
from financial_analyst_agent.providers.sec.company_resolver import resolve_company
from financial_analyst_agent.universe import (
    SnapshotGroups,
    UniverseCompany,
    UniverseSnapshot,
    allowed_industry_names,
    is_common_operating_listing,
    load_universe_snapshot,
    preferred_listing,
    resolve_industry_group,
)

# Companies a clarification offers for an ambiguous name.
_MAX_CHOICES = 4


@dataclass(frozen=True)
class RankTable:
    as_of: str
    source: str
    sector: str
    companies: tuple[UniverseCompany, ...]


class SnapshotRanking:
    """Sort a checked-in snapshot. Membership does not change at request time."""

    def __init__(self, snapshot: UniverseSnapshot, index: IssuerIndex | None = None) -> None:
        self._snapshot = snapshot
        # The planner's index, so a company resolves as the planner read it.
        self._index = index
        # The snapshot is immutable, so the operating-listing views are built once
        # instead of rescanning thousands of rows on every lookup.
        self._operating = tuple(
            company for company in snapshot.companies if is_common_operating_listing(company)
        )
        self._listings_by_cik: dict[str, list[UniverseCompany]] = {}
        for company in self._operating:
            self._listings_by_cik.setdefault(company.cik, []).append(company)
        self._by_ticker = {company.ticker.upper(): company for company in self._operating}
        self._groups = SnapshotGroups.of(snapshot)
        self._ticker_payload: dict[str, Any] = {
            str(index): {
                "ticker": company.ticker,
                "title": company.name,
                "cik_str": int(company.cik),
            }
            for index, company in enumerate(snapshot.companies)
            if is_common_operating_listing(company)
        }

    @classmethod
    def from_path(
        cls, path: Path | None = None, index: IssuerIndex | None = None
    ) -> "SnapshotRanking":
        return cls(load_universe_snapshot(path), index)

    @property
    def index(self) -> IssuerIndex:
        """The names that reach a member: the given index, or one built from the snapshot."""
        if self._index is None:
            self._index = IssuerIndex.build(self._snapshot.companies)
        return self._index

    def rank_companies(self, industry: str, limit: int) -> RankTable:
        group = resolve_industry_group(industry, self._groups)
        if group is None:
            allowed_names = allowed_industry_names(self._groups)
            allowed = ", ".join(allowed_names)
            raise UnknownIndustryError(
                f"Unknown industry {industry!r}. Allowed: {allowed}",
                details={"industry": industry, "allowed": list(allowed_names)},
            )
        ranked = [
            company
            for company in self._operating
            if group.includes(company) and company.files_quarterly
        ]
        by_cik: dict[str, list[UniverseCompany]] = {}
        for company in ranked:
            by_cik.setdefault(company.cik, []).append(company)
        selected = [preferred_listing(group) for group in by_cik.values()]
        selected.sort(key=lambda company: company.market_cap, reverse=True)
        selected = selected[: max(limit, 1)]
        return RankTable(
            as_of=self.snapshot_as_of(),
            source=self._snapshot.source,
            sector=group.label,
            companies=tuple(selected),
        )

    def member_ciks(self) -> Collection[str]:
        """Every snapshot member's CIK: the companies the snapshot has already judged."""
        return self._listings_by_cik.keys()

    def snapshot_companies(self) -> tuple[UniverseCompany, ...]:
        return tuple(self._snapshot.companies)

    def snapshot_as_of(self) -> str:
        return self._snapshot.as_of.isoformat()

    def snapshot_source(self) -> str:
        return self._snapshot.source

    def lookup_member(self, company: str) -> UniverseCompany:
        """The snapshot listing ``company`` names.

        The issuer index reads the name first, as the planner does: "Goldman
        Sachs", "Lilly", "Merck & Co." and "$TMO" each name one member. A name
        it does not hold whole goes to the SEC-style resolver, which may find
        it ambiguous. A ticker typed as one ("TEAM", "$COKE") is that listing,
        even where it is also another company's name or nickname.
        """
        typed = company.strip().removeprefix("$").rstrip(".")
        as_ticker = typed.isupper() or company.strip().startswith("$")
        listing = self._by_ticker.get(typed.upper()) if as_ticker else None
        if listing is not None:
            return preferred_listing(self._listings_by_cik[listing.cik])
        query = self.index.named(company)
        listing = self._by_ticker.get(query.upper()) if query is not None else None
        if listing is not None:
            return preferred_listing(self._listings_by_cik[listing.cik])
        shared = self.index.shared.get(normalize(company))
        if shared:
            # "Charles" is Charles Schwab or Charles River: the analyst picks, from
            # every company the index holds the name for, the largest first.
            return self._one_of(
                company, [self._by_ticker[t].cik for t in shared if t in self._by_ticker]
            )
        try:
            resolved = resolve_company(query or company, self._ticker_payload)
        except AmbiguousCompanyError as exc:
            matches = exc.details.get("matches", ())
            return self._one_of(company, [str(match["cik"]) for match in matches], exc)
        listings = self._listings_by_cik.get(resolved.cik)
        if not listings:
            raise CompanyNotFoundError(
                f"Company not found for query '{company}'",
                details={"query": company},
            )
        return preferred_listing(listings)

    def _one_of(
        self, company: str, ciks: list[str], cause: Exception | None = None
    ) -> UniverseCompany:
        """The member an ambiguous name means, or the members to ask between.

        The matches are raised as the snapshot's listings, largest first, so
        a clarification can offer "KO, CCEP or COKE" by name.
        """
        members = [
            preferred_listing(self._listings_by_cik[cik])
            for cik in dict.fromkeys(ciks)
            if cik in self._listings_by_cik
        ]
        if len(members) == 1:
            return members[0]
        if not members:
            raise CompanyNotFoundError(
                f"Company not found for query '{company}'", details={"query": company}
            ) from cause
        members.sort(key=lambda member: member.market_cap, reverse=True)
        raise AmbiguousCompanyError(
            f"“{company}” names more than one company",
            details={
                "query": company,
                "matches": [
                    {"cik": member.cik, "ticker": member.ticker, "title": member.name}
                    for member in members[:_MAX_CHOICES]
                ],
            },
        ) from cause

    def peers(
        self, cik: str, *, exclude: frozenset[str] = frozenset(), limit: int = 3
    ) -> tuple[UniverseCompany, ...]:
        """The largest other companies in ``cik``'s industry, for "add a peer" suggestions."""
        own = next((row for row in self._snapshot.companies if row.cik == cik), None)
        if own is None or not own.industry:
            return ()
        seen = {cik, *exclude}
        found: list[UniverseCompany] = []
        for row in self._operating:
            if row.industry == own.industry and row.cik not in seen and row.files_quarterly:
                seen.add(row.cik)
                found.append(row)
        found.sort(key=lambda row: row.market_cap, reverse=True)
        return tuple(found[:limit])
