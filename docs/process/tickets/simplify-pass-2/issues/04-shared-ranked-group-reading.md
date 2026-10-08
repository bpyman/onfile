# Move the ranked-group reading out of the rules planner

From a parallel `/simplify` review of the whole codebase (7 October 2026): seven read-only reviewers, one per area plus one across areas; 84 findings, consolidated into 12 tickets that never share a file. Cleanup only: **no behaviour may change**.

**Files (this ticket only):** `src/financial_analyst_agent/rules_planner.py`, `src/financial_analyst_agent/ranked_wording.py`, `src/financial_analyst_agent/graph/turn_graph.py`, `src/financial_analyst_agent/guide.py`

**What to build:** The analysis graph imports `ranked_group` from rules_planner.py (turn_graph.py:86) to correct **both** planners' rankings, for example the set 5 "all US public companies" fix at turn_graph.py:206-224. ranked_group's own docstring says it reads the words "as this planner reads them". That puts a reading of words inside one planner, against ADR 0010/0011, and a group-wording fix for the LLM path has to edit planner code. Move the group reading into a shared module and remove the copies around it. This is a pure move with cleanups: no regex text changes and no plan or answer changes.

1. **Move, unchanged**, `ranked_group` and the group-reading helpers it calls (rules_planner.py:310-320, 435-561, 564-574, 816-860: `_RANK_WORDS`, `_WHICH_HIGHEST`, `_without_preamble`, `_group_by_metric`, `_group_named`, `_count_words_as_digits`, `_whole_counts`, `_ranked_industry`, `_clean_group`, `_INDUSTRY_WORDS` and whatever else they need) into a new `ranked_wording.py` next to request_wording.py. Do not put it in request_wording.py; another ticket owns that file. Give the names the rules planner still uses public names. rules_planner.py and turn_graph.py import them from ranked_wording. Do not change any pattern text.
2. **One preparation pipeline and one group reading.** `_whole_counts(_count_words_as_digits(expand_groups(plain_text(query))))` is written out in `ranked_group` (570) and in `complete` (607-610). `_without_preamble`, `_RANK_WORDS`, `_group_by_metric` and `_WHICH_HIGHEST` are combined in both `ranked_group` and `_plan` (679-685). Add `prepared(query) -> tuple[str, list[str]]` for the pipeline, and `ranking_group(ranking)` for the no-companies group reading. `ranked_group` uses both, and `_plan` uses `ranking_group` when `companies` is empty, so the group the graph checks cannot drift from the group the plan uses.
3. **Typed words, four copies.** `{word for mention in mentions for word in normalize(mention.typed).split()}` appears in `complete` (619-621), `_unfound_names` (922), `_unknown_term` (973) and `_names_only` (1004). Add `_typed_words(mentions) -> frozenset[str]` and call it from all four.
4. **A mention's short display name, five copies.** guide.py `_named_company` (358-359) and `unrecorded_companies` (345, with the `outside` index), and rules_planner.py `_mention_note` (578), `_left_out_of_ranking` (882) and `_ticker_notes` (898) each write `short_name(index.display_name(query)) or <fallback>`. Add `short_display_name(index: CompanyNames, query: str, fallback: str) -> str` to guide.py next to `short_name`, and call it from all five, passing each site's current fallback (`mention.query` or `mention.typed`).
5. **guide.py imports.** guide.py imports `resolve_metric_phrase(s)` inside three functions (253, 263, 291-294), although line 25 already imports from `services.metric_catalog`, so the local imports avoid no cycle. Move them to the top. `_named_company` and `_spec_company` (171-178, 351-359) return `(name, query)`, but every caller discards the query. Return `str | None` and simplify the call sites (197-200, 230, 243-246, 257).
6. **turn_graph.py `request_from_proposal` (206-224).** `isinstance(proposal, WorkflowPlan) and proposal.intent in (Intent.RANK, Intent.RANK_AND_LOOKUP)` is written in both the if and the elif. Compute `ranks` once and nest the two industry fixes under it, keeping their order and conditions.

**Acceptance:** all tests pass; ruff and mypy are clean; nothing in `graph/` imports `rules_planner`; phrase coverage stays 555 of 555; the rules planner still passes all 160 set 5 cases; `uv run python scripts/compare_answers.py` reports `0 of N conversations differ`.

Spec: ADR 0010, ADR 0011.

**Findings covered:**
- across/altitude: ranked_group and the group grammar live in the rules planner and the graph imports them
- reading/simplification: ranked_group copies the query-preparation pipeline and ranking-group logic of complete and _plan
- reading/reuse: typed-words comprehension written four times in rules_planner
- reading/reuse: short_name(index.display_name(query)) or fallback in five places (guide.py, rules_planner.py)
- reading/simplification: guide.py local imports of resolve_metric_phrase(s); _named_company/_spec_company return an unused query
- graph/simplification (partial): request_from_proposal repeats the rank-intent test in the if and the elif

**Acceptance:** `uv run python -m pytest` passes; ruff and mypy are clean; `uv run python scripts/compare_answers.py` reports `0 of N conversations differ`; phrase coverage stays 555 of 555. If a step would change behaviour, or needs a file outside this ticket's list, leave it and say so in the Answer.

**Blocked by:** None — can start immediately

**Status:** resolved

## Answer

Shipped 7 October 2026. Cleanup only: compare_answers reports `0 of 375 conversations differ from HEAD`.

1. **`ranked_wording.py` (new, next to request_wording.py)** holds the group reading, moved from rules_planner.py with every pattern's text unchanged (each string literal of the moved blocks was checked to appear verbatim): the count words and their patterns, `_count_words_as_digits`, `_whole_counts`, `_without_preamble`, `_group_by_metric`, `_industry_from_query`, `_ranked_industry`, `_clean_group`, `_plural_group`, `_INDUSTRY_WORDS` and `_group_named`. The names the rules planner still uses are public: `RANK_WORDS`, `WHICH_HIGHEST`, `GROUP_COUNT` (for `_limit`), `without_preamble`, `group_by_metric`, `group_named`. `ranked_group` is public there, and turn_graph.py imports it from ranked_wording; nothing under `graph/` imports rules_planner (a test checks).
2. **One pipeline, one group reading.** `prepared(query)` is the preparation pipeline, called by `complete` and `ranked_group`. `ranking_group(ranking)` is the no-companies group reading; `ranked_group` is `ranking_group(without_preamble(...))` over the prepared, lower-cased words, and `_plan` calls `ranking_group` when `companies` is empty (beside a named company it still reads the ranking words alone, `group_named(ranking, None, None)`, as before). `_plan` keeps its own `which`, `rank_words` and `group_by` to decide whether the question ranks and whether it orders by the metric.
3. **`_typed_words(mentions)`** in rules_planner.py replaces the four copies of the typed-words comprehension (`complete`, `_unfound_names`, `_unknown_term`, `_names_only`).
4. **`short_display_name(index, query, fallback)`** in guide.py next to `short_name`, called at the five sites with each site's fallback: guide `_named_company` and `unrecorded_companies`, rules_planner `_mention_note`, `_left_out_of_ranking` and `_ticker_notes`. rules_planner imports it instead of `short_name`.
5. **guide.py**: `resolve_metric_phrase(s)` imported at the top, the three local imports removed; `_named_company` and `_spec_company` return `str | None`, and the four call sites use the name directly.
6. **turn_graph.py `request_from_proposal`**: the rank-intent test is written once (`isinstance(proposal, WorkflowPlan) and proposal.intent in _RANK_INTENTS`) with the two industry fixes nested under it in their order and with their conditions.

Checks: 2,349 tests pass (11 new: `tests/unit/test_ranked_wording.py`, and `short_display_name` in `test_planner_rules.py`); ruff and mypy clean; phrase coverage 555 of 555 (report not regenerated); the rules planner passes 160 of 160 held-out set 5 cases (report not regenerated).
