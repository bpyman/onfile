# Match metric phrases once and bind periods in one place

From a parallel `/simplify` review of the whole codebase (7 October 2026): seven read-only reviewers, one per area plus one across areas; 84 findings, consolidated into 12 tickets that never share a file. Cleanup only: **no behaviour may change**.

**Files (this ticket only):** `src/financial_analyst_agent/services/metric_catalog.py`, `src/financial_analyst_agent/request_wording.py`, `src/financial_analyst_agent/answer_notes.py`

**What to build:** Most of a turn's reading time is spent matching the same message against every metric phrase, again and again. `request_wording.py` builds the same change operations three times, and `answer_notes.py` rebuilds names and readings it could share. Make the phrase matching run once per message and remove the copies. This is cleanup only: every metric reading, window, patch and note must stay the same.

1. **Phrase matching reruns (metric_catalog.py:633-660, 718-731, 795-827, 848-858).** Profiling 6 recorded turns found about 6 full scans per turn and 9,760 `_phrase_spans` calls, taking 83 ms of 245 ms. Compile each phrase's `\b...\b` pattern once at import, as `(pattern, metric)` tuples for `_UNIQUE_PHRASES`, `_UNKNOWN_MEASURES` and `_AMBIGUOUS_PHRASES`, and have `_phrase_spans` take the compiled pattern. Put `@lru_cache(maxsize=256)` on `resolve_metric_phrases`, `resolve_metric_phrase` and `without_trailing_year_words`. All three are pure functions of a string that return immutable values. Check that no test monkeypatches the phrase tables under a cached call. Make `_with_prefixed_metric` reuse the matches `resolve_metric_phrases` already computed instead of calling `_phrase_matches` again.
2. **The trailing-year words are written twice** (request_wording.py:326-329 `TRAILING_YEAR`; metric_catalog.py:691-694 `_TRAILING_YEAR_WORDS`). Define the alternation string once in metric_catalog.py, as `TRAILING_YEAR_WORDS`. Compile `_TRAILING_YEAR_WORDS` there as `rf"\b(?:{TRAILING_YEAR_WORDS})\s+$"`, and `TRAILING_YEAR` in request_wording.py as `rf"\b(?:{TRAILING_YEAR_WORDS})\b"` with `re.I`. Both compiled patterns must stay character for character what they are today.
3. **`bind_periods_from_message` builds the change operations three times** (request_wording.py:898-904, 927-934, 953-962). Each copy also calls `comparison_asked(message)` again. Compute `base = comparison_asked(message)` once near the top; it is pure. Add `_change_operations(operations, *, across: bool, base, both: bool) -> tuple[str, ...]` that keeps the existing `if x not in operations` appends in the same order. Call it with `across=yoy or sequential`, and in the named branch with `or len(quarters) >= 2`.
4. **`parse_named_periods` (request_wording.py:697-760).** Define `free(start, end)` before the half-year loop and use it instead of the inline `any(...)` at 701. Add `_full_year(raw: str) -> int` for the two `int(raw_year) + (2000 if len(raw_year) == 2 else 0)` sites (703, 753).
5. **`_keep_window_for_change` (request_wording.py:1181-1182).** `_names_a_span(message) or parse_named_periods(message)` has the same truth value as `_names_a_window(message) or parse_named_periods(message)`. Use the shorter form, which also parses the named periods only once.
6. **`_refine_against` (request_wording.py:1250-1328).** Strip the message once (`stripped = message.strip()`) and use it in every `.match`. Add `_metrics_in_place(patch, metrics, current_spec)` for the "these metrics in place of the ones on screen" `_extend(...)`, which is built line for line in the `_SWITCH_TO_EDIT` branch (1274-1281) and in `_metric_swap` (1379-1385).
7. **"A year of quarters" is read twice.** `bind_periods_from_message` (request_wording.py:917) and `period_notes` (answer_notes.py:348) each run `YEAR_OF_QUARTERS.search(message)` beside the `WindowReading` they are handed. Add `year_of_quarters: bool = False` to `WindowReading`. Set it in `read_window` from the raw message **before** the `window_words()` reassignment, so the input it reads is unchanged, and read `window.year_of_quarters` at both sites.
8. **answer_notes.py names and dates.**
   - `missing_component_notes` (159-180) formats `"Name (date and date)"` and then, for one company, parses it back with `endswith(")")` and `partition(" (")`. Keep `named` as `(short, dates)` tuples, where the dates are present only when today's `(company, metric) in shown and dates` holds. Join them with parentheses only for the multi-company sentence. For one company, build `when` from `joined(map(format_date, dates))` and choose "that quarter" or "those quarters" from `len(dates) == 1`. Before changing it, confirm that no short name in the snapshot ends in ")"; for every other name the output is the same.
   - Add `_shown_name(company) -> str` (`short_name(company.name) or company.query`) and use it at the five ResolvedCompany sites (265, 286, 295, 300, 316).
   - In `_named_period_notes`, iterate over `dated` in the elif, and drop the `if ends:` check, which is always true there.

**Acceptance:** all tests pass; ruff and mypy are clean; phrase coverage stays 555 of 555; the rules planner still passes all 160 set 5 cases; `uv run python scripts/compare_answers.py` reports `0 of N conversations differ`. A profile of the same 6 recorded turns shows each message scanned for phrases once.

Not in this ticket: answer_notes.py's two `row.cik or row.company_name` sites (137, 142). They can switch to `TableRow.company_key` once ticket 06 lands.

**Findings covered:**
- reading/efficiency: metric-phrase matching reruns many times per turn (metric_catalog.py)
- across/reuse: trailing-year alternation spelled twice (request_wording.py:326-329, metric_catalog.py:691-694)
- reading/simplification: bind_periods_from_message builds change operations three times
- reading/simplification: parse_named_periods writes the overlap test and two-digit year twice
- reading/simplification: _keep_window_for_change repeats a check and parses named periods twice
- reading/simplification: _refine_against strips seven times and builds the metric-swap patch twice
- across/simplification: YEAR_OF_QUARTERS read beside WindowReading in period_notes and bind_periods_from_message
- graph/simplification: missing_component_notes formats then re-parses 'Name (dates)'
- graph/simplification: answer_notes short_name(company.name) or company.query five times; redundant dated filter and if ends
- across/simplification (ResolvedCompany half): short display name rebuilt inline in answer_notes

**Acceptance:** `uv run python -m pytest` passes; ruff and mypy are clean; `uv run python scripts/compare_answers.py` reports `0 of N conversations differ`; phrase coverage stays 555 of 555. If a step would change behaviour, or needs a file outside this ticket's list, leave it and say so in the Answer.

**Blocked by:** None — can start immediately

**Status:** resolved

## Answer

Shipped 7 October 2026. Every answer is unchanged: compare_answers reports `0 of 375 conversations differ from HEAD`; 2,335 tests pass (3 new); ruff and mypy are clean; phrase coverage stays 555 of 555; the rules planner passes all 160 held-out set 5 cases.

1. **Phrase matching runs once per message** (`metric_catalog.py`). Each phrase's `\b...\b` pattern is compiled at import into `_UNIQUE_PATTERNS` (with its `_NOT_FOLLOWED_BY` exclusion beside it), `_UNKNOWN_PATTERNS` and `_AMBIGUOUS_PATTERNS`; `_phrase_spans` takes the compiled pattern. `resolve_metric_phrases`, `resolve_metric_phrase` and `without_trailing_year_words` carry `@lru_cache(maxsize=256)`, as asked, and so do the two readings under them: `_longest_phrases`, the one scan of every unique phrase and unknown measure, which the full reading and the trailing-year words both start from, and `_phrase_matches`, the full reading. Both return tuples. `resolve_metric_phrase` reads the matches once and hands them to `_with_prefixed_metric`, which no longer scans. No test monkeypatches the phrase tables. A profile of six recorded turns (a four-quarter lookup, a two-company comparison, a ranking, a TTM figure, and a lookup with a segment follow-up) shows each of the seven distinct messages scanned exactly once: 1,925 `_phrase_spans` calls against the 9,760 the review measured.
2. **Trailing-year words spelled once.** `TRAILING_YEAR_WORDS` in `metric_catalog.py` is the alternation; `_TRAILING_YEAR_WORDS` and request_wording's `TRAILING_YEAR` are compiled from it, and a test holds `TRAILING_YEAR.pattern` to the literal it was.
3. **`bind_periods_from_message`** computes `base = comparison_asked(message)` once and builds its operations with `_change_operations(operations, *, across, base, both)` at all three sites, the named branch with `across=yoy or sequential or len(quarters) >= 2`.
4. **`parse_named_periods`** defines `free` before the half-year loop and uses it there; `_full_year(raw)` reads the two-digit years at both sites.
5. **`_keep_window_for_change`** checks `_names_a_window(message) or parse_named_periods(message)`.
6. **`_refine_against`** strips the message once; `_metrics_in_place(patch, metrics, current_spec)` builds the "these metrics in place of the ones on screen" patch for the `_SWITCH_TO_EDIT` branch and `_metric_swap`.
7. **`WindowReading.year_of_quarters`** is read in `read_window` from the raw message before the `window_words()` reassignment; `bind_periods_from_message` and `period_notes` read it from the window. A test on `read_window` covers "last year", "annual", a counted window and TTM.
8. **answer_notes.py.** `_shown_name(company)` replaces the five `short_name(company.name) or company.query` sites; `_named_period_notes` iterates `dated` in its elif and the always-true `if ends:` is gone.

**Left undone: the `missing_component_notes` rewrite (step 8, first bullet).** The step asked first to confirm that no snapshot short name ends in ")". Eleven do ("Telefonaktiebolaget LM Ericsson (publ)", "Jerash Holdings (US)", "ZTO Express (Cayman)", "Banco Santander (Brasil) S.A." among them), and for one of them alone today's parse-back reads the parenthesis as dates ("Jerash Holdings' EBITDA is missing for US: ... for that quarter"). The tuple form would correct that note, so it changes behaviour, and per this ticket it is left for a person: see `docs/process/rules-to-review.md`, entry of 2026-10-07 for this ticket.

Not touched, as the ticket says: answer_notes.py's two `row.cik or row.company_name` sites wait for ticket 06.
