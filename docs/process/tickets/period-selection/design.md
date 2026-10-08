# Period selection: the module and its interface

Decided 8 October 2026 after an architecture review and a design-it-twice round (three independent designs; this is design A with two later decisions folded in). CONTEXT.md defines the term; ADR 0015 records why the seam sits here. The tickets in `issues/` each move one part of the lifecycle behind this interface. **No behaviour may change**: `scripts/compare_answers.py --against master` reports `0 of N conversations differ` after every ticket.

## Shape in one line

One function, `read`, and one view, `Periods`. Everything else hangs off their result types. Callers import `read`, `Periods`, and the three value types they exchange (`WindowReading`, `ChangeAsked`, `Dated`).

## Where it lives

`src/financial_analyst_agent/period_selection.py`. It imports `graph/analysis_spec.py` (`PeriodSelection`, `NamedPeriodSpec`, `AnalysisSpec`, `SpecPatch`, `MAX_QUARTERS_ASKED`), `services/fiscal_periods.py`, `contracts.py` (`FactsPort`, `TableRow`), `fan_out`, `guide`. It imports **nothing** from `request_wording`, `answer_notes` or `presentation`; they import it. `compile_tasks` moves from `analysis_spec` to `graph/spec_turn.py`, its one caller's home, so `analysis_spec` holds only stored shapes and `apply_patch`.

## Interface

```python
class WindowReading(BaseModel):
    """What one message's window words say, in the form the thread stores.
    Moved from request_wording unchanged: same nine fields, same dump. Gains
    year_to_date: bool = Field(default=False, exclude_if=lambda v: not v) so stored
    dumps are byte-identical. JSON carries no class name, so checkpoints load unchanged."""

@dataclass(frozen=True)
class ChangeAsked:
    """Which change the words ask for. Declared here as this module's input; built
    OUTSIDE by request_wording.change_asked(message). The module never searches the
    message for change words."""
    base: ComparisonBase | Literal["unclear"] | None   # comparison_asked
    yoy: bool          # YOY matched (growth, "how has it changed", ...)
    sequential: bool   # _SEQUENTIAL
    both: bool         # names_both_bases
    explicit_yoy: bool # EXPLICIT_YOY
    change_words: bool # _CHANGE
    dropped: bool      # drops_comparison
    NONE: ClassVar[ChangeAsked]

def read(message: str, *, stored: WindowReading | None = None) -> Words:
    """Pure. The one period grammar: counted windows, "since", named periods, half-years,
    year ranges, month quarters, "N years ago", latest/this quarter, sub-quarter and
    year-to-date words, unread specific periods. ``stored`` replaces the grammar's
    reading with the one a request already holds (a checkpointed request); named
    periods and cue words are still read from ``message``."""

@dataclass(frozen=True)
class Words:
    """The whole reading of one message. Not persisted; ``reading`` is its stored part."""
    message: str
    reading: WindowReading
    named: tuple[NamedPeriodSpec, ...]      # parse_named_periods, same order, no repeats
    names_a_window: bool                     # counted, "over the past year", or "since"

    def propose(self, patch: SpecPatch, *, model_quarters: int | None = None) -> SpecPatch:
        """Proposal time, before the request is stored. ``model_quarters`` is the planner's
        recent_quarters (None for a rank intent or a SpecPatch proposal): capped and set as
        the window, then the planner-window rule: the grammar's count beats it (logged when
        they differ), it stands only with a period cue, else set_periods=None."""

    def bind(self, patch: SpecPatch, change: ChangeAsked) -> SpecPatch:
        """The words' periods on the patch (today bind_periods_from_message): dropped change,
        since-window, TTM / year of quarters as 4, named periods (+ empty company_base_dates
        when sequential), "latest" resets, the 5/8 defaults, sequential's count+1/asked, and
        the across/yoy/both operations. Returns ``patch`` itself when nothing applies
        (clarify compares by equality). Runs BEFORE the company/metric edit, which reads
        set_periods."""

    def rebase(self, patch: SpecPatch, change: ChangeAsked, on_screen: AnalysisSpec) -> SpecPatch:
        """"Sequential instead" / "year over year instead" keep the quarters on screen
        (today _keep_window_for_change + _switch_to_sequential). Runs AFTER the
        company/metric edit: it acts only on patch.mode == "extend", which that edit sets."""

@dataclass(frozen=True)
class Periods:
    """View of spec.companies + spec.periods (+ as_of, constituents for the chip and notes).
    Every member but ``dated`` is pure and works on any PeriodSelection, dated or not."""
    spec: AnalysisSpec

    def dated(self, facts: FactsPort) -> Dated:
        """I/O. Lists quarter ends (list_quarterly_report_dates) or fiscal periods
        (fiscal_periods: named kinds and "since fiscal") per company, the first company
        (or first constituent) alone first, the rest via map_in_order under _or_none.
        Fills report_dates, count, asked, company_report_dates, company_base_dates.
        Dates already on the spec are kept (an added company lists only itself).
        latest_quarter and already-dated specs return the same spec object.
        Raises CompanyNotFoundError / SOURCE_FAILURES from the FIRST company's listing
        (the turn refuses); another company's failure leaves it unlisted; SessionQuotaError
        always propagates. Order: after resolve_spec, drop_funds, drop_annual_filers;
        before compile_tasks."""

    @property
    def groups(self) -> list[tuple[tuple[str, ...], tuple[date, ...]]]: ...  # calendar_groups
    def shown(self, rows: Sequence[TableRow]) -> list[TableRow]:
        """Rows without the fetched-but-not-shown bases (_without_base_quarters and
        _without_named_bases). Order: after merge_task_results, before ordering."""
    @property
    def chip(self) -> tuple[str, bool]: ...                       # _period_chip
    @property
    def quick_actions(self) -> tuple[tuple[str, str], ...]: ...   # (label, follow-up)
    def notes(self, reading: WindowReading, change: ChangeAsked, *, ranked_window: bool = False) -> PeriodNotes:
        """Finished text. ``reading.year_of_quarters`` and ``reading.year_to_date`` replace
        today's re-search of the message; ``change.yoy`` keeps the "last year" note off a
        year-over-year question."""

@dataclass(frozen=True)
class PeriodNotes:
    read: list[str]    # unread period, TTM / year of quarters, sub-quarter
    shown: list[str]   # year-to-date, ranked-shows-latest (ADR 0005), named-period notes,
                       # calendars differ, fiscal Q4 gap, capped/short window, since notes

@dataclass(frozen=True)
class Dated:
    spec: AnalysisSpec
    refusal: str | None   # finished text: the two named-period messages (after-latest-filing
                          # read here) or "Could not determine quarterly report dates..."
    @property
    def periods(self) -> Periods: ...
```

Two lists in `PeriodNotes` because the growth and why-change banners (which stay in `answer_notes`) sit between the sub-quarter note and the year-to-date note today; the caller splices them.

## The call sites, after

```python
# turn_graph.request_from_proposal
words = read(message)
quarters = None if isinstance(proposal, SpecPatch) or proposal.intent is Intent.RANK else proposal.recent_quarters
patch = words.propose(lifted, model_quarters=quarters)
return StructuredRequest(patch=patch, wording=message, question=message, window=words.reading, ...)

# request_wording.refine_patch_from_message (stays outside; the period calls inside it)
def refine_patch_from_message(patch, message, current_spec, *, index=None, words: Words):
    change = change_asked(message)
    patch = words.bind(_without_word_uses(patch, message, index), change)
    if current_spec is None:
        return _with_segment_companies(patch, message)
    return words.rebase(_refine_against(patch, message, current_spec, index), change, current_spec)

# spec_turn.resolve_request
words = read(message, stored=request.window)
patch = refine_patch_from_message(patch, message, current_spec, index=..., words=words)
...
try:
    dated = Periods(spec).dated(runtime.facts)
except (CompanyNotFoundError, *SOURCE_FAILURES) as exc:
    return answered(_refusal(asked, visitor_message(exc, ...), ...), None)
if dated.refusal is not None:
    return answered(_empty_spec(asked, dated.refusal), None)
spec = dated.spec
tasks = compile_tasks(spec)          # now in spec_turn; uses Periods(spec).groups

# spec_turn.merge_analysis / annotate_analysis
merged = merged.model_copy(update={"table_rows": Periods(spec).shown(merged.table_rows)})
period = Periods(spec).notes(compiled.window, change_asked(compiled.wording), ranked_window=compiled.ranked_window_asked)
notes = [..., *metric_reading_notes(wording, spec), *period.read,
         *change_banners(wording, spec),        # growth-is-yoy, why-change: stay in answer_notes
         *period.shown, *short_ranking_notes(spec), ...]

# clarify._read_metric  (ask_again: words.bind(pending.patch, change) the same way)
words, change = read(message), change_asked(message)
if words.bind(SpecPatch(mode="extend"), change) != SpecPatch(mode="extend"):
    return ClarifyReply(period_patch=...)

# presentation
period, moved = Periods(spec).chip
periods = tuple(QuickAction(label, msg) for label, msg in Periods(spec).quick_actions)

# overview_trend / earlier_quarters: Periods(window_spec).dated(runtime.facts).spec
# rules_planner: len(read(normalized).named) >= 2
# request_wording.comparison_asked: read(message).names_a_window in place of _names_a_window
```

## What the implementation hides

Every regex of the grammar and which text each one reads (raw message vs `window_words`); count words, the cap, the "a few = 4" and months-rounded notes; the 5/8 defaults, `count+1`/`asked` for sequential, `MAX_SINCE_QUARTERS`; which listing a window needs (report dates vs fiscal periods) and `dates_for`, `quarters_since*`, `_quarters_before`, `_span_asked`; the fan-out and `_or_none`; the first-company asymmetry; `_same_grid`/`_quarter_phase` grouping; base-row hiding for both kinds; the after-latest-filing check; all refusal, note and chip wording.

## Tests

The facts provider enters only as the `FactsPort` argument of `Periods.dated`; the module never touches `Runtime`. One shared fake in `tests/helpers.py` replaces the nine local listing fakes:

```python
class ListedFilings(FakeFacts):
    """Quarter ends and fiscal periods per company; keyed by the name a test asks by."""
    def __init__(self, quarters: Mapping[str, Sequence[date]] = {},
                 fiscal: Mapping[str, Sequence[FiscalPeriod]] = {},
                 *, failing: Collection[str] = (), annual: Collection[str] = ()): ...
    listed: list[tuple[str, int | None]]   # (company, limit) in call order, for fan-out asserts
```

Tests cross the interface: `read` tables assert `Words.reading`, `named` and `bind`'s `set_periods`/operations given a hand-built `ChangeAsked`; `propose` keeps/overrules/drops a model window; `rebase` on each on-screen kind; `Periods.dated` with `ListedFilings` asserts dates, `asked`, `company_base_dates`, `refusal`, and the error asymmetry; `groups`, `shown`, `chip`, `quick_actions`, `notes` on dated specs; a persistence test that `WindowReading.model_dump()` is unchanged over a wording corpus. Each ticket rewrites the tests of what it absorbs and deletes the old ones; hand-built `PeriodSelection`s stay only where a test is about the stored shape itself.

## Behaviour-preservation checklist

Every ticket checks the items that touch its part:

- [ ] **Never bind at proposal time.** After "Apple revenue last 6 quarters" plus an ambiguous metric, the held patch keeps the planner's count and resume rebinds from the reply. `propose` and `bind` stay separate.
- [ ] **Keep the seven `ChangeAsked` flags.** Growth (5 quarters), explicit yoy (8), "how did it change" (asked about) and sequential (bases) bind differently. `change_asked` computes `base` with `read(message).names_a_window`, as `comparison_asked` does now.
- [ ] **Banner order.** The year-to-date note sits after the why-change banner; `PeriodNotes.read` / `.shown` preserve it.
- [ ] **Which text each regex reads.** `YEAR_OF_QUARTERS` and `SINCE_YEAR` (in `names_a_window`) search the raw message; `asked_window`, `SPECIFIC_PERIOD`, `SUB_QUARTER` search `window_words(message)`; `since_year` is read only when no counted window matched.
- [ ] **After-latest-filing** re-lists the first company's fiscal periods today; reuse the listing only once it is shown that no trace or quota counts the second call. Otherwise call again.
- [ ] **First-company asymmetry and fan-out**: the first listing is unwrapped, the rest `_or_none` under `map_in_order` in spec order; `SessionQuotaError` re-raises.
- [ ] **`bind` identity**: `clarify` detects a period reply by `!=` against an empty extend patch, so `bind` returns an equal patch when nothing is read.
- [ ] **`WindowReading.year_to_date`** uses `exclude_if`, or every stored dump and compared spec gains a key.
- [ ] **`set_periods` presence**: `_refine_against` and `apply_patch` branch on `set_periods is None`; `bind`/`rebase` emit `None` exactly where today's code does.
- [ ] **Row identity** in `shown` is `row.cik or row.company_name`, as both `_without_*` functions use, not `ResolvedCompany.key`.
- [ ] **Undated windows still compile** (`overview_trend`): `dated` returns the undated spec rather than raising or refusing.
- [ ] **No re-exports.** When a name moves, callers switch; `request_wording` does not re-export it.
