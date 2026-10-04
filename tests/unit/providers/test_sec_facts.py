"""Successor registrant lookup: try the accession-prefix CIK when needed."""

from datetime import date
from decimal import Decimal

import httpx
import pytest

from financial_analyst_agent.config import Settings
from financial_analyst_agent.domain.errors import (
    FilingNotFoundError,
    ProviderError,
    UnsupportedQuarterlyFactError,
)
from financial_analyst_agent.domain.models import FinancialFact
from financial_analyst_agent.providers.sec.client import SECClient
from financial_analyst_agent.sec_facts import SecFactLookup, _related_lookup_ciks

SUCCESSOR_CIK = "0002115436"
PREDECESSOR_CIK = "0000034088"
ACCESSION = "0000034088-26-000093"


def test_related_lookup_ciks_adds_only_a_verified_predecessor() -> None:
    assert _related_lookup_ciks(SUCCESSOR_CIK, PREDECESSOR_CIK) == (SUCCESSOR_CIK, PREDECESSOR_CIK)
    # An accession prefix that is a parent or a filing agent was never verified.
    assert _related_lookup_ciks(SUCCESSOR_CIK, None) == (SUCCESSOR_CIK,)
    assert _related_lookup_ciks(SUCCESSOR_CIK, SUCCESSOR_CIK) == (SUCCESSOR_CIK,)


def _submissions(cik: str, accession: str) -> dict[str, object]:
    return {
        "cik": int(cik),
        "name": "Exxon Mobil Corporation",
        "tickers": ["XOM"],
        "filings": {
            "recent": {
                "form": ["10-Q"],
                "accessionNumber": [accession],
                "filingDate": ["2026-08-03"],
                "reportDate": ["2026-06-30"],
                "primaryDocument": ["xom-20260630.htm"],
            }
        },
    }


def _empty_facts(cik: str) -> dict[str, object]:
    return {"cik": int(cik), "entityName": "Exxon Mobil Corporation", "facts": {"us-gaap": {}}}


def _quarterly_net_income_facts(cik: str, accession: str) -> dict[str, object]:
    return {
        "cik": int(cik),
        "entityName": "Exxon Mobil Corporation",
        "facts": {
            "us-gaap": {
                "NetIncomeLoss": {
                    "units": {
                        "USD": [
                            {
                                "start": "2026-04-01",
                                "end": "2026-06-30",
                                "val": 14525000000,
                                "accn": accession,
                                "form": "10-Q",
                                "filed": "2026-08-03",
                            }
                        ]
                    }
                }
            }
        },
    }


def _submissions_two_quarters(cik: str) -> dict[str, object]:
    return {
        "cik": int(cik),
        "name": "Exxon Mobil Corporation",
        "tickers": ["XOM"],
        "filings": {
            "recent": {
                "form": ["10-Q", "10-Q"],
                "accessionNumber": ["0000034088-26-000093", "0000034088-26-000050"],
                "filingDate": ["2026-08-03", "2026-05-05"],
                "reportDate": ["2026-06-30", "2026-03-31"],
                "primaryDocument": ["xom-20260630.htm", "xom-20260331.htm"],
            }
        },
    }


def _two_quarter_net_income_facts(cik: str) -> dict[str, object]:
    return {
        "cik": int(cik),
        "entityName": "Exxon Mobil Corporation",
        "facts": {
            "us-gaap": {
                "NetIncomeLoss": {
                    "units": {
                        "USD": [
                            {
                                "start": "2026-04-01",
                                "end": "2026-06-30",
                                "val": 14525000000,
                                "accn": "0000034088-26-000093",
                                "form": "10-Q",
                                "filed": "2026-08-03",
                            },
                            {
                                "start": "2026-01-01",
                                "end": "2026-03-31",
                                "val": 7713000000,
                                "accn": "0000034088-26-000050",
                                "form": "10-Q",
                                "filed": "2026-05-05",
                            },
                        ]
                    }
                }
            }
        },
    }


def test_sec_fact_lookup_named_report_date_returns_that_quarter() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/company_tickers.json"):
            return httpx.Response(
                200,
                json={
                    "0": {
                        "cik_str": 34088,
                        "ticker": "XOM",
                        "title": "Exxon Mobil Corporation",
                    }
                },
            )
        if path.endswith(f"/submissions/CIK{PREDECESSOR_CIK}.json"):
            return httpx.Response(200, json=_submissions_two_quarters(PREDECESSOR_CIK))
        if path.endswith(f"/companyfacts/CIK{PREDECESSOR_CIK}.json"):
            return httpx.Response(200, json=_two_quarter_net_income_facts(PREDECESSOR_CIK))
        return httpx.Response(404, json={"error": path})

    settings = Settings(
        sec_user_agent="FinancialAnalystAgent (dev@example.com)",
        sec_max_requests_per_second=5.0,
    )
    client = SECClient(
        settings,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    lookup = SecFactLookup(settings, client=client)
    fact = lookup.get_financials(
        "XOM",
        "net_income",
        report_date=date(2026, 3, 31),
    )
    assert fact.value == Decimal("7713000000")
    assert fact.end_date == date(2026, 3, 31)
    assert fact.accession_number == "0000034088-26-000050"


def test_latest_steps_back_past_filings_companyfacts_lacks() -> None:
    submissions = _submissions_two_quarters(PREDECESSOR_CIK)
    recent = submissions["filings"]["recent"]  # type: ignore[index]
    recent["form"].insert(0, "10-Q")
    recent["accessionNumber"].insert(0, "0000034088-26-000120")
    recent["filingDate"].insert(0, "2026-11-03")
    recent["reportDate"].insert(0, "2026-09-30")
    recent["primaryDocument"].insert(0, "xom-20260930.htm")
    facts = _two_quarter_net_income_facts(PREDECESSOR_CIK)
    usd = facts["facts"]["us-gaap"]["NetIncomeLoss"]["units"]["USD"]  # type: ignore[index]
    del usd[0]

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/company_tickers.json"):
            return httpx.Response(
                200,
                json={"0": {"cik_str": 34088, "ticker": "XOM", "title": "Exxon Mobil Corporation"}},
            )
        if path.endswith(f"/submissions/CIK{PREDECESSOR_CIK}.json"):
            return httpx.Response(200, json=submissions)
        if path.endswith(f"/companyfacts/CIK{PREDECESSOR_CIK}.json"):
            return httpx.Response(200, json=facts)
        return httpx.Response(404, json={"error": path})

    settings = Settings(
        sec_user_agent="FinancialAnalystAgent (dev@example.com)",
        sec_max_requests_per_second=5.0,
    )
    client = SECClient(settings, client=httpx.Client(transport=httpx.MockTransport(handler)))

    fact = SecFactLookup(settings, client=client).get_financials("XOM", "net_income")

    assert fact.end_date == date(2026, 3, 31)
    assert fact.value == Decimal("7713000000")
    assert fact.newer_filing_end == date(2026, 9, 30)


def test_sec_fact_lookup_named_report_date_missing_does_not_use_latest() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/company_tickers.json"):
            return httpx.Response(
                200,
                json={
                    "0": {
                        "cik_str": 34088,
                        "ticker": "XOM",
                        "title": "Exxon Mobil Corporation",
                    }
                },
            )
        if path.endswith(f"/submissions/CIK{PREDECESSOR_CIK}.json"):
            return httpx.Response(200, json=_submissions_two_quarters(PREDECESSOR_CIK))
        if path.endswith(f"/companyfacts/CIK{PREDECESSOR_CIK}.json"):
            return httpx.Response(200, json=_two_quarter_net_income_facts(PREDECESSOR_CIK))
        return httpx.Response(404, json={"error": path})

    settings = Settings(
        sec_user_agent="FinancialAnalystAgent (dev@example.com)",
        sec_max_requests_per_second=5.0,
    )
    client = SECClient(
        settings,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    lookup = SecFactLookup(settings, client=client)
    with pytest.raises(UnsupportedQuarterlyFactError) as exc_info:
        lookup.get_financials("XOM", "net_income", report_date=date(2025, 12, 31))
    assert "2025-12-31" in str(exc_info.value.details.get("report_date", ""))



def _empty_facts(cik: str) -> dict[str, object]:
    return {"cik": int(cik), "entityName": "Exxon Mobil Corporation", "facts": {"us-gaap": {}}}


def _quarterly_net_income_facts(cik: str, accession: str) -> dict[str, object]:
    return {
        "cik": int(cik),
        "entityName": "Exxon Mobil Corporation",
        "facts": {
            "us-gaap": {
                "NetIncomeLoss": {
                    "units": {
                        "USD": [
                            {
                                "start": "2026-04-01",
                                "end": "2026-06-30",
                                "val": 14525000000,
                                "accn": accession,
                                "form": "10-Q",
                                "filed": "2026-08-03",
                            }
                        ]
                    }
                }
            }
        },
    }


def test_sec_fact_lookup_uses_accession_filer_when_successor_has_no_quarter() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/company_tickers.json"):
            return httpx.Response(
                200,
                json={
                    "0": {
                        "cik_str": 2115436,
                        "ticker": "XOM",
                        "title": "ExxonMobil Holdings Corp",
                    }
                },
            )
        if path.endswith(f"/submissions/CIK{SUCCESSOR_CIK}.json"):
            return httpx.Response(200, json=_submissions(SUCCESSOR_CIK, ACCESSION))
        if path.endswith(f"/companyfacts/CIK{SUCCESSOR_CIK}.json"):
            return httpx.Response(200, json=_empty_facts(SUCCESSOR_CIK))
        if path.endswith(f"/companyfacts/CIK{PREDECESSOR_CIK}.json"):
            return httpx.Response(200, json=_quarterly_net_income_facts(PREDECESSOR_CIK, ACCESSION))
        if path.endswith(f"/submissions/CIK{PREDECESSOR_CIK}.json"):
            # The old registrant's own list holds the joint report: verified.
            return httpx.Response(200, json=_submissions(PREDECESSOR_CIK, ACCESSION))
        return httpx.Response(404, json={"error": path})

    settings = Settings(
        sec_user_agent="FinancialAnalystAgent (dev@example.com)",
        sec_max_requests_per_second=5.0,
    )
    client = SECClient(
        settings,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    lookup = SecFactLookup(settings, client=client)
    fact = lookup.get_financials("ExxonMobil", "net_income")
    assert isinstance(fact, FinancialFact)
    # The listed company, with the quarter read from its predecessor's filing.
    assert fact.cik == SUCCESSOR_CIK
    assert f"/data/{int(PREDECESSOR_CIK)}/" in fact.source_url
    assert fact.ticker == "XOM"
    assert fact.value == Decimal("14525000000")
    assert fact.concept == "NetIncomeLoss"
    assert fact.accession_number == ACCESSION


def test_sec_fact_lookup_uses_accession_filer_when_successor_companyfacts_are_missing() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/company_tickers.json"):
            return httpx.Response(
                200,
                json={
                    "0": {
                        "cik_str": 2115436,
                        "ticker": "XOM",
                        "title": "ExxonMobil Holdings Corp",
                    }
                },
            )
        if path.endswith(f"/submissions/CIK{SUCCESSOR_CIK}.json"):
            return httpx.Response(200, json=_submissions(SUCCESSOR_CIK, ACCESSION))
        if path.endswith(f"/companyfacts/CIK{SUCCESSOR_CIK}.json"):
            return httpx.Response(404, json={"error": "not found"})
        if path.endswith(f"/companyfacts/CIK{PREDECESSOR_CIK}.json"):
            return httpx.Response(200, json=_quarterly_net_income_facts(PREDECESSOR_CIK, ACCESSION))
        if path.endswith(f"/submissions/CIK{PREDECESSOR_CIK}.json"):
            # The old registrant's own list holds the joint report: verified.
            return httpx.Response(200, json=_submissions(PREDECESSOR_CIK, ACCESSION))
        return httpx.Response(404, json={"error": path})

    settings = Settings(
        sec_user_agent="FinancialAnalystAgent (dev@example.com)",
        sec_max_requests_per_second=5.0,
    )
    client = SECClient(
        settings,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    lookup = SecFactLookup(settings, client=client)
    fact = lookup.get_financials("ExxonMobil", "net_income")
    assert isinstance(fact, FinancialFact)
    assert fact.cik == PREDECESSOR_CIK
    assert fact.ticker == "XOM"
    assert fact.value == Decimal("14525000000")
    assert fact.concept == "NetIncomeLoss"
    assert fact.accession_number == ACCESSION


def test_sec_fact_lookup_does_not_fallback_on_companyfacts_client_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/company_tickers.json"):
            return httpx.Response(
                200,
                json={
                    "0": {
                        "cik_str": 2115436,
                        "ticker": "XOM",
                        "title": "ExxonMobil Holdings Corp",
                    }
                },
            )
        if path.endswith(f"/submissions/CIK{SUCCESSOR_CIK}.json"):
            return httpx.Response(200, json=_submissions(SUCCESSOR_CIK, ACCESSION))
        if path.endswith(f"/companyfacts/CIK{SUCCESSOR_CIK}.json"):
            return httpx.Response(400, json={"error": "bad request"})
        return httpx.Response(404, json={"error": path})

    settings = Settings(
        sec_user_agent="FinancialAnalystAgent (dev@example.com)",
        sec_max_requests_per_second=5.0,
    )
    client = SECClient(
        settings,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    lookup = SecFactLookup(settings, client=client)
    with pytest.raises(ProviderError) as exc_info:
        lookup.get_financials("ExxonMobil", "net_income")
    assert exc_info.value.details.get("status_code") == 400


def test_sec_fact_lookup_converts_exhausted_companyfacts_404s_to_missing_fact() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/company_tickers.json"):
            return httpx.Response(
                200,
                json={
                    "0": {
                        "cik_str": 2115436,
                        "ticker": "XOM",
                        "title": "ExxonMobil Holdings Corp",
                    }
                },
            )
        if path.endswith(f"/submissions/CIK{SUCCESSOR_CIK}.json"):
            return httpx.Response(200, json=_submissions(SUCCESSOR_CIK, ACCESSION))
        if "/companyfacts/" in path:
            return httpx.Response(404, json={"error": "not found"})
        return httpx.Response(404, json={"error": path})

    settings = Settings(
        sec_user_agent="FinancialAnalystAgent (dev@example.com)",
        sec_max_requests_per_second=5.0,
    )
    client = SECClient(
        settings,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    lookup = SecFactLookup(settings, client=client)

    with pytest.raises(UnsupportedQuarterlyFactError) as exc_info:
        lookup.get_financials("ExxonMobil", "net_income")

    assert exc_info.value.details == {"metric": "net_income"}


def test_sec_fact_lookup_maps_missing_quarterly_filings_to_unsupported_fact() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/company_tickers.json"):
            return httpx.Response(
                200,
                json={
                    "0": {
                        "cik_str": 2115436,
                        "ticker": "XOM",
                        "title": "ExxonMobil Holdings Corp",
                    }
                },
            )
        if path.endswith(f"/submissions/CIK{SUCCESSOR_CIK}.json"):
            payload = _submissions(SUCCESSOR_CIK, ACCESSION)
            filings = payload["filings"]
            assert isinstance(filings, dict)
            recent = filings["recent"]
            assert isinstance(recent, dict)
            recent["form"] = ["10-K"]
            return httpx.Response(200, json=payload)
        if path.endswith(f"/companyfacts/CIK{SUCCESSOR_CIK}.json"):
            return httpx.Response(200, json=_empty_facts(SUCCESSOR_CIK))
        return httpx.Response(404, json={"error": path})

    settings = Settings(
        sec_user_agent="FinancialAnalystAgent (dev@example.com)",
        sec_max_requests_per_second=5.0,
    )
    lookup = SecFactLookup(
        settings,
        client=SECClient(
            settings,
            client=httpx.Client(transport=httpx.MockTransport(handler)),
        ),
    )

    with pytest.raises(UnsupportedQuarterlyFactError) as exc_info:
        lookup.get_financials("ExxonMobil", "net_income")

    assert not isinstance(exc_info.value, FilingNotFoundError)
    # A lone 10-K with no fiscal-year amount has no quarter to derive (ADR 0007).
    assert "quarter" in str(exc_info.value)


def test_sec_fact_lookup_reuses_sec_payloads_across_get_financials_calls() -> None:
    counts = {"tickers": 0, "submissions": 0, "companyfacts": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/company_tickers.json"):
            counts["tickers"] += 1
            return httpx.Response(
                200,
                json={
                    "0": {
                        "cik_str": 2115436,
                        "ticker": "XOM",
                        "title": "ExxonMobil Holdings Corp",
                    }
                },
            )
        if path.endswith(f"/submissions/CIK{SUCCESSOR_CIK}.json"):
            counts["submissions"] += 1
            return httpx.Response(200, json=_submissions(SUCCESSOR_CIK, ACCESSION))
        if path.endswith(f"/companyfacts/CIK{SUCCESSOR_CIK}.json"):
            counts["companyfacts"] += 1
            return httpx.Response(200, json=_empty_facts(SUCCESSOR_CIK))
        if path.endswith(f"/companyfacts/CIK{PREDECESSOR_CIK}.json"):
            counts["companyfacts"] += 1
            return httpx.Response(
                200, json=_quarterly_net_income_facts(PREDECESSOR_CIK, ACCESSION)
            )
        if path.endswith(f"/submissions/CIK{PREDECESSOR_CIK}.json"):
            # The old registrant's own list holds the joint report: verified.
            return httpx.Response(200, json=_submissions(PREDECESSOR_CIK, ACCESSION))
        return httpx.Response(404, json={"error": path})

    settings = Settings(
        sec_user_agent="FinancialAnalystAgent (dev@example.com)",
        sec_max_requests_per_second=5.0,
    )
    lookup = SecFactLookup(
        settings,
        client=SECClient(
            settings,
            client=httpx.Client(transport=httpx.MockTransport(handler)),
        ),
    )

    first = lookup.get_financials("ExxonMobil", "net_income")
    second = lookup.get_financials("ExxonMobil", "net_income")

    assert first.value == second.value == Decimal("14525000000")
    assert counts == {"tickers": 1, "submissions": 1, "companyfacts": 2}


def test_sec_fact_lookup_reuses_companyfacts_404_across_get_financials_calls() -> None:
    counts = {"companyfacts": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/company_tickers.json"):
            return httpx.Response(
                200,
                json={
                    "0": {
                        "cik_str": 2115436,
                        "ticker": "XOM",
                        "title": "ExxonMobil Holdings Corp",
                    }
                },
            )
        if path.endswith(f"/submissions/CIK{SUCCESSOR_CIK}.json"):
            return httpx.Response(200, json=_submissions(SUCCESSOR_CIK, ACCESSION))
        if path.endswith(f"/companyfacts/CIK{SUCCESSOR_CIK}.json"):
            counts["companyfacts"] += 1
            return httpx.Response(404, json={"error": "not found"})
        if path.endswith(f"/companyfacts/CIK{PREDECESSOR_CIK}.json"):
            counts["companyfacts"] += 1
            return httpx.Response(
                200, json=_quarterly_net_income_facts(PREDECESSOR_CIK, ACCESSION)
            )
        if path.endswith(f"/submissions/CIK{PREDECESSOR_CIK}.json"):
            # The old registrant's own list holds the joint report: verified.
            return httpx.Response(200, json=_submissions(PREDECESSOR_CIK, ACCESSION))
        return httpx.Response(404, json={"error": path})

    settings = Settings(
        sec_user_agent="FinancialAnalystAgent (dev@example.com)",
        sec_max_requests_per_second=5.0,
    )
    lookup = SecFactLookup(
        settings,
        client=SECClient(
            settings,
            client=httpx.Client(transport=httpx.MockTransport(handler)),
        ),
    )

    first = lookup.get_financials("ExxonMobil", "net_income")
    second = lookup.get_financials("ExxonMobil", "net_income")

    assert first.value == second.value == Decimal("14525000000")
    assert counts == {"companyfacts": 2}


def test_a_listing_on_the_ineligible_list_is_not_looked_up() -> None:
    from financial_analyst_agent.domain.errors import IneligibleIssuerError

    requested: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(request.url.path)
        if request.url.path.endswith("company_tickers.json"):
            return httpx.Response(
                200,
                json={"0": {"cik_str": 1287750, "ticker": "ARCC", "title": "ARES CAPITAL CORP"}},
            )
        return httpx.Response(404, json={"error": request.url.path})

    settings = Settings(
        sec_user_agent="FinancialAnalystAgent (dev@example.com)",
        sec_max_requests_per_second=5.0,
    )
    client = SECClient(settings, client=httpx.Client(transport=httpx.MockTransport(handler)))
    lookup = SecFactLookup(settings, client=client)
    with pytest.raises(IneligibleIssuerError) as exc_info:
        lookup.get_financials("ARCC", "eps_diluted")
    assert "not an operating company" in str(exc_info.value)
    assert not any("submissions" in path or "companyfacts" in path for path in requested)


def test_submissions_read_older_pages_until_three_years_are_covered() -> None:
    newest = {
        "cik": 19617,
        "name": "JPMorgan Chase & Co.",
        "tickers": ["JPM"],
        "filings": {
            "recent": {
                "form": ["424B2", "10-Q"],
                "accessionNumber": ["0000019617-26-000900", "0000019617-26-000800"],
                "filingDate": ["2026-09-01", "2026-08-03"],
                "reportDate": ["", "2026-06-30"],
                "primaryDocument": ["a.htm", "jpm-20260630.htm"],
            },
            "files": [
                {"name": "CIK0000019617-submissions-001.json"},
                {"name": "CIK0000019617-submissions-002.json"},
                {"name": "../../etc/passwd"},
            ],
        },
    }
    pages = {
        "CIK0000019617-submissions-001.json": {
            "form": ["10-Q"],
            "accessionNumber": ["0000019617-25-000615"],
            "filingDate": ["2025-08-05"],
            "reportDate": ["2025-06-30"],
            "primaryDocument": ["jpm-20250630.htm"],
        },
        "CIK0000019617-submissions-002.json": {
            "form": ["10-K"],
            "accessionNumber": ["0000019617-23-000100"],
            "filingDate": ["2023-02-21"],
            "reportDate": ["2022-12-31"],
        },
    }
    requested: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        name = request.url.path.rsplit("/", 1)[-1]
        requested.append(name)
        if name == "CIK0000019617.json":
            return httpx.Response(200, json=newest)
        return httpx.Response(200, json=pages[name])

    settings = Settings(sec_user_agent="FinancialAnalystAgent (dev@example.com)")
    client = SECClient(settings, client=httpx.Client(transport=httpx.MockTransport(handler)))

    recent = client.get_submissions("0000019617")["filings"]["recent"]

    assert recent["accessionNumber"][-2:] == ["0000019617-25-000615", "0000019617-23-000100"]
    # Every column stays the same length, filling a column a page lacks.
    assert {len(column) for column in recent.values()} == {4}
    assert recent["primaryDocument"][-1] == ""
    assert "passwd" not in " ".join(requested)


def test_periodic_filings_are_rebuilt_from_company_facts() -> None:
    from financial_analyst_agent.sec_facts import filings_from_company_facts

    def fact(
        end: str, accn: str, form: str = "10-Q", filed: str = "2025-08-05"
    ) -> dict[str, object]:
        return {"end": end, "val": 1, "accn": accn, "form": form, "filed": filed}

    payload = {
        "facts": {
            "dei": {
                "EntityCommonStockSharesOutstanding": {
                    "units": {"shares": [fact("2025-07-31", "0000019617-25-000615")]}
                }
            },
            "us-gaap": {
                "NetIncomeLoss": {
                    "units": {
                        "USD": [
                            fact("2025-06-30", "0000019617-25-000615"),
                            fact("2024-06-30", "0000019617-25-000615"),
                            fact("2025-06-30", "0000019617-25-000615"),
                            fact("2024-12-31", "0000019617-25-000100", "10-K", "2025-02-14"),
                            fact("2024-12-31", "0000019617-25-000200", "8-K", "2025-01-15"),
                            # A 10-K with more comparative facts than current ones.
                            *[fact("2024-12-31", "0000019617-25-000300", "10-K", "2025-02-20")] * 3,
                            *[fact("2023-12-31", "0000019617-25-000300", "10-K", "2025-02-20")] * 4,
                            # And one subsequent event, dated after the period.
                            fact("2025-02-10", "0000019617-25-000300", "10-K", "2025-02-20"),
                        ]
                    }
                }
            },
        }
    }

    filings = {filing.accession_number: filing for filing in filings_from_company_facts(payload)}

    assert set(filings) == {
        "0000019617-25-000615",
        "0000019617-25-000100",
        "0000019617-25-000300",
    }
    # The cover page's later shares date is not the report's period.
    assert filings["0000019617-25-000615"].report_date == date(2025, 6, 30)
    assert filings["0000019617-25-000100"].form == "10-K"
    assert filings["0000019617-25-000300"].report_date == date(2024, 12, 31)


def _plexus_lookup(revenue: int, gross: int, cost: int) -> SecFactLookup:
    cik, accession = "0000785786", "0000785786-26-000054"

    def entry(value: int) -> dict[str, object]:
        return {
            "start": "2026-04-05",
            "end": "2026-07-04",
            "val": value,
            "accn": accession,
            "form": "10-Q",
            "filed": "2026-08-05",
        }

    facts = {
        "cik": int(cik),
        "entityName": "PLEXUS CORP",
        "facts": {
            "us-gaap": {
                "RevenueFromContractWithCustomerExcludingAssessedTax": {
                    "units": {"USD": [entry(revenue)]}
                },
                "GrossProfit": {"units": {"USD": [entry(gross)]}},
                "CostOfGoodsAndServicesSold": {"units": {"USD": [entry(cost)]}},
            }
        },
    }
    submissions = {
        "cik": int(cik),
        "name": "PLEXUS CORP",
        "tickers": ["PLXS"],
        "filings": {
            "recent": {
                "form": ["10-Q"],
                "accessionNumber": [accession],
                "filingDate": ["2026-08-05"],
                "reportDate": ["2026-07-04"],
                "primaryDocument": ["plxs-20260704.htm"],
            }
        },
    }

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/company_tickers.json"):
            return httpx.Response(
                200, json={"0": {"cik_str": int(cik), "ticker": "PLXS", "title": "PLEXUS CORP"}}
            )
        if path.endswith(f"/submissions/CIK{cik}.json"):
            return httpx.Response(200, json=submissions)
        if path.endswith(f"/companyfacts/CIK{cik}.json"):
            return httpx.Response(200, json=facts)
        return httpx.Response(404, json={"error": path})

    settings = Settings(sec_user_agent="FinancialAnalystAgent (dev@example.com)")
    client = SECClient(settings, client=httpx.Client(transport=httpx.MockTransport(handler)))
    return SecFactLookup(settings, client=client)


def test_a_mis_scaled_revenue_is_gross_profit_plus_cost_of_revenue() -> None:
    fact = _plexus_lookup(1_304_778, 131_379_000, 1_173_399_000).get_financials("PLXS", "revenue")

    assert fact.value == Decimal("1304778000")
    assert fact.derivation is not None
    assert [part.metric for part in fact.derivation.parts] == ["gross_profit", "cost_of_revenue"]


def test_a_negative_gross_margin_keeps_the_filed_revenue() -> None:
    fact = _plexus_lookup(1_000, -200, 1_200).get_financials("PLXS", "revenue")

    assert fact.value == Decimal("1000")
    assert fact.derivation is None


class _RecordingSource:
    """A data source that fails on demand and notes what it was asked for."""

    def __init__(self, *, failing: str = "") -> None:
        self.calls: list[str] = []
        self.slots_free_at_download: list[int] = []
        self._failing = failing

    def get_company_tickers(self) -> dict[str, object]:
        self.calls.append("tickers")
        return {"0": {"cik_str": int(SUCCESSOR_CIK), "ticker": "XOM", "title": "Exxon Mobil"}}

    def get_submissions(self, cik: str, *, with_history: bool = True) -> dict[str, object]:
        self.calls.append(f"submissions:{cik}")
        if self._failing.startswith("submissions"):
            status = 404 if self._failing.endswith("404") else 503
            raise ProviderError("SEC error", details={"status_code": status})
        payload = _submissions(cik, ACCESSION)
        recent = payload["filings"]["recent"]  # type: ignore[index]
        # A bank's list: periodic reports among prospectuses, with extra columns.
        for column, value in (
            ("form", "424B2"),
            ("accessionNumber", "0000034088-26-000094"),
            ("filingDate", "2026-08-04"),
            ("reportDate", ""),
            ("primaryDocument", "prospectus.htm"),
        ):
            recent[column].append(value)
        recent["size"] = [1, 2]
        return payload

    def prefetch_company_facts(self, cik: str) -> None:
        from financial_analyst_agent import sec_facts

        self.calls.append(f"download:{cik}")
        self.slots_free_at_download.append(sec_facts._FACTS_PARSE_SLOTS._value)

    def get_company_facts(self, cik: str) -> dict[str, object]:
        self.calls.append(f"facts:{cik}")
        if self._failing == "facts":
            raise ProviderError("SEC request timed out", details={"retryable": False})
        return _quarterly_net_income_facts(cik, ACCESSION)

    def close(self) -> None:
        return None


@pytest.mark.parametrize("failing", ["submissions", "submissions-404", "facts"])
def test_a_failed_sec_document_is_not_asked_for_again_in_the_turn(failing: str) -> None:
    source = _RecordingSource(failing=failing)
    lookup = SecFactLookup(client=source)

    for metric in ("net_income", "revenue", "net_income"):
        with pytest.raises(ProviderError):
            lookup.get_financials("XOM", metric)

    document = failing.split("-")[0]
    asked = [call for call in source.calls if call.startswith(f"{document}:")]
    assert asked == [f"{document}:{SUCCESSOR_CIK}"]


def test_company_facts_are_downloaded_before_a_parse_slot_is_taken() -> None:
    source = _RecordingSource()

    SecFactLookup(client=source).get_financials("XOM", "net_income")

    assert source.calls.index(f"download:{SUCCESSOR_CIK}") < source.calls.index(
        f"facts:{SUCCESSOR_CIK}"
    )
    assert source.slots_free_at_download
    assert all(free == 2 for free in source.slots_free_at_download)


@pytest.mark.parametrize("value", ["12abc", True, None], ids=["text", "boolean", "missing"])
def test_malformed_facts_are_unreadable_not_unreported(value: object) -> None:
    from financial_analyst_agent.domain.errors import DataIntegrityError

    class _Malformed(_RecordingSource):
        def get_company_facts(self, cik: str) -> dict[str, object]:
            payload = _quarterly_net_income_facts(cik, ACCESSION)
            entry = payload["facts"]["us-gaap"]["NetIncomeLoss"]["units"]["USD"][0]  # type: ignore[index]
            entry["val"] = value
            return payload

    with pytest.raises(DataIntegrityError, match="could not be read"):
        SecFactLookup(client=_Malformed()).get_financials("XOM", "net_income")


def test_a_lookup_keeps_only_the_submissions_rows_and_columns_it_reads() -> None:
    lookup = SecFactLookup(client=_RecordingSource())

    lookup.get_financials("XOM", "net_income")

    kept = lookup._submissions_by_cik[SUCCESSOR_CIK]["filings"]["recent"]
    assert kept["form"] == ["10-Q"]
    assert set(kept) == {"form", "accessionNumber", "filingDate", "reportDate", "primaryDocument"}


BANK_ACCESSION = "0002115436-26-000093"


class _PagedSource(_RecordingSource):
    """A filer whose first submissions page may leave out its 10-Q, as a bank's does."""

    def __init__(self, *, ten_q_on_first_page: bool, history_fails: bool = False) -> None:
        super().__init__()
        self.pages_read: list[str] = []
        self._ten_q_on_first_page = ten_q_on_first_page
        self._history_fails = history_fails

    def get_submissions(self, cik: str, *, with_history: bool = True) -> dict[str, object]:
        self.pages_read.append("history" if with_history else "first page")
        if with_history and self._history_fails:
            raise ProviderError("SEC error", details={"status_code": 503})
        payload = _submissions(cik, BANK_ACCESSION)
        if not with_history and not self._ten_q_on_first_page:
            # A year of prospectuses and nothing else.
            payload["filings"]["recent"] = {  # type: ignore[index]
                "form": ["424B2"],
                "accessionNumber": ["0002115436-26-000094"],
                "filingDate": ["2026-08-04"],
                "reportDate": [""],
                "primaryDocument": ["prospectus.htm"],
            }
        return payload

    def get_company_facts(self, cik: str) -> dict[str, object]:
        return _quarterly_net_income_facts(cik, BANK_ACCESSION)


def test_a_lookup_reads_only_the_first_submissions_page() -> None:
    source = _PagedSource(ten_q_on_first_page=True)

    fact = SecFactLookup(client=source).get_financials("XOM", "net_income")

    assert fact.source_url.endswith("/xom-20260630.htm")
    assert source.pages_read == ["first page"]


def test_a_filing_only_company_facts_names_links_to_its_document_from_the_older_pages() -> None:
    source = _PagedSource(ten_q_on_first_page=False)
    lookup = SecFactLookup(client=source)

    fact = lookup.get_financials("XOM", "net_income")
    lookup.get_financials("XOM", "net_income")

    assert fact.value == Decimal("14525000000")
    assert fact.source_url.endswith("/000211543626000093/xom-20260630.htm")
    # The older pages are read once a turn, and only because a link needed them.
    assert source.pages_read == ["first page", "history"]


def test_without_the_older_pages_a_link_is_the_filings_index_page() -> None:
    source = _PagedSource(ten_q_on_first_page=False, history_fails=True)

    fact = SecFactLookup(client=source).get_financials("XOM", "net_income")

    assert fact.value == Decimal("14525000000")
    assert fact.source_url.endswith("/000211543626000093/0002115436-26-000093-index.htm")
