# One listing fake for every test that dates quarters

From the architecture review of 8 October 2026: period selection becomes one module, per `docs/process/tickets/period-selection/design.md` and ADR 0015. This ticket is the prefactor: tests only, **no source file changes**, so the module tickets can rewrite their tests against one fake.

**Files (this ticket only):** `tests/helpers.py`, `tests/unit/test_calendars_clarification_and_formatting.py`, `tests/unit/test_multi_period.py`, `tests/unit/test_follow_up_wording.py`, `tests/unit/test_clarification_checkpoint.py`, `tests/unit/test_company_names.py`, `tests/unit/test_concurrent_dispatch.py`, `tests/unit/test_conversation_edges.py`, `tests/unit/test_filers_rankings_and_narrowing.py`, `tests/unit/test_resumable_clarification.py`

**What to build:** Nine test files each define their own fake that lists a company's quarterly report dates or fiscal periods (`_Listing`, `_LongListing`, `_FiscalListing`, two `_PeriodFacts`, `_LookupFacts`, `_SlowFacts`, and the `_Facts` classes and inline fakes in the files above). Add one to `tests/helpers.py`, beside `FakeFacts`, and use it everywhere:

```python
class ListedFilings(FakeFacts):
    """Quarter ends and fiscal periods per company, keyed by the name a test asks by."""
    def __init__(self, quarters: Mapping[str, Sequence[date]] = {},
                 fiscal: Mapping[str, Sequence[FiscalPeriod]] = {},
                 *, failing: Collection[str] = (), annual: Collection[str] = ()): ...
    listed: list[tuple[str, int | None]]   # (company, limit) in call order
```

- `list_quarterly_report_dates(company, *, limit)` returns `quarters[company][:limit]`, newest first; a company given only `fiscal` periods lists their end dates; a company in `failing` raises `CompanyNotFoundError`.
- `fiscal_periods(company)` returns `fiscal[company]`; a company given only `quarters` gets calendar-year labels derived from them.
- `files_quarterly(company)` is `(company not in annual, company)`.
- `listed` records every listing call so tests can assert which company was listed, with what limit, and in what order (today's "adding a company lists only that company" and the fan-out tests).

Each local fake that also overrides `get_financials`, sleeps, counts quota or logs keeps doing so by subclassing `ListedFilings`; only its listing of report dates and fiscal periods is replaced. Where a test keys companies by CIK through `named_by_cik`, keep that wrapping. If a test needs listing behaviour the fake cannot express, leave that one and say so in the Answer rather than growing the fake for one test.

**Acceptance:** `uv run python -m pytest` passes with the same test count; ruff and mypy are clean; no file under `tests/` defines `list_quarterly_report_dates` or `fiscal_periods` except `FakeFacts` and `ListedFilings` in `tests/helpers.py` (a subclass may pass through to `super()` but not reimplement a listing). `scripts/compare_answers.py --against master` reports `0 of N conversations differ` (no source changed, so this is a formality).

Spec: `docs/process/tickets/period-selection/design.md` ("Tests").

**Blocked by:** None — can start immediately

**Status:** ready-for-agent
