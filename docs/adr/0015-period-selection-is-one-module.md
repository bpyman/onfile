# Period selection is one module; change words enter as input

A question picks its quarters in three ways: the latest quarter, a window ("past six quarters", "since fiscal 2025") or named periods ("Q3 2024", "2023 to 2025"). Reading those words, dating them for each company from its filings, deciding which quarters are fetched only as comparison bases, writing the notes that say how the window was read, and labelling the period chip were spread over six modules joined by two records: `WindowReading`, stored on the request, and `PeriodSelection`, stored on the analysis spec. The two fixes that changed how a "since" window is dated each touched six or seven files; `calendar_groups` was recomputed in three; the notes searched the raw message again for words the reading already held; and a metric answer to a clarification lost the window note because the resumed request re-read its window from the reply (#103).

An architecture review (8 October 2026) chose this as the first module to deepen, and three interfaces were designed independently before one was picked (`docs/process/tickets/period-selection/design.md`).

## Decision

- **One module, `period_selection`, owns the period grammar, the dating, the base marking, the period notes and the period chip.** Its interface is one function, `read(message)`, whose result proposes, binds and rebases the period part of a spec patch, and one view, `Periods(spec)`, that dates a spec, groups its calendars, hides base-only rows, and writes its notes, chip label and quick actions. The module takes the facts provider as an argument and never builds it.
- **`PeriodSelection` stays the stored form, unchanged, and the module is a view over it.** It is persisted in thread records, pending clarifications, checkpoints and share links; the planners, the evaluation and phrase coverage read its fields as data. Replacing it would mean migrating stored state for no gain in depth. `WindowReading` likewise keeps its stored shape, gaining only `year_to_date`, left out of the dump when false.
- **The change words enter as input, not as something the module reads.** Which change a question asks for (growth, explicit year over year, "how did it change", sequential, both, or a dropped change) is read outside, by `request_wording`, into a typed value the module declares. The binding distinguishes all of these: growth defaults to five quarters, explicit year over year to eight, a bare change is asked about, and sequential needs base quarters. The module imports nothing from `request_wording`, `answer_notes` or `presentation`; they import it.
- **`compile_tasks` moves beside its one caller** in `spec_turn`, so `analysis_spec` holds only stored shapes and `apply_patch`, and the module can import it without a cycle.

## Consequences

- A window wording, a dating rule or a period note changes in one file; callers see no change. A new comparison-base rule touches the module's binding, dating and hiding, and the typed input it declares, still in two files.
- The reading of a question (a later candidate) can absorb `request_wording` without touching this module, because the dependency runs one way.
- Callers must still know the lifecycle's order: propose at request time only, bind before the company/metric edit and rebase after it, date after the filers are dropped and before compiling, hide bases before ordering rows, and splice the change banners between the two lists of period notes. The design record names each.
- The seam between change words and period words is seven flags wide. That is the width the behaviour needs; a narrower input would change answers.
- No behaviour changes. Every step is gated by replaying every recorded conversation against master.

## Considered options

- **A value object that carries reading and dating together through the turn**, with `PeriodSelection` derived from it and rebuilt on resume. Closest in depth, but it grew the stored `WindowReading` by four fields and asked `compile_tasks` to take calendars as a parameter at every call.
- **Flat pure functions, one per lifecycle point**, with the company/metric edit passed into the binding as a callback so the bind-then-rebase order disappears. The fewest ordering rules for callers, but fifteen names where two do, and the module learns that an edit step exists.
- **Read the change words inside the module too.** It would make the input simpler, but it puts a second reading of change words beside the one `request_wording` already has, and the Change module (a later candidate) would then have to reach into this one.
- **Leave the grammar where it is** and deepen only the dating. The grammar did change alone in six of eight recent window fixes, but the two that crossed reading and dating were the expensive ones, and the "since fiscal" path joins them through fields both sides must agree on.
