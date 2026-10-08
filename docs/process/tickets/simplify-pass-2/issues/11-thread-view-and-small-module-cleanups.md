# Memoise stored turns' presentations and tidy clarify, config and planner

From a parallel `/simplify` review of the whole codebase (7 October 2026): seven read-only reviewers, one per area plus one across areas; 84 findings, consolidated into 12 tickets that never share a file. Cleanup only: **no behaviour may change**.

**Files (this ticket only):** `src/financial_analyst_agent/thread_store.py`, `src/financial_analyst_agent/api.py`, `src/financial_analyst_agent/graph/clarify.py`, `src/financial_analyst_agent/config.py`, `src/financial_analyst_agent/planner.py`, `src/financial_analyst_agent/planner_cascade.py`

**What to build:** GET /api/threads/{id} re-reads and re-presents every stored turn on every call, and a few small modules keep two copies of one rule. Remove the repeated work and the copies. No API response, clarification reading, configuration error or plan may change.

1. **One guard for an unreadable stored answer** (thread_store.py:146-164). `resolve_results` and `resolve_last_result` each wrap `evidence.get_result` in `except (KeyError, OSError, ValueError)`. Add `_result_or_none(evidence, ref) -> TurnResult | None`. `resolve_results` becomes a comprehension that filters out None, and `resolve_last_result` becomes one call. Add a sibling that yields `(ref, result)` pairs for step 2.
2. **`thread_view` re-presents every turn (api.py:394-445).** Each poll and each finished turn re-reads every stored result and re-runs `present_turn` and `asdict`: up to 25 loads and 25 presentations per call, although stored results never change once written. Memoise each turn's presentation by `(thread_id, ref)` in a small bounded cache, cleared when the store is cleared. Rebuild only the turn-level fields that depend on thread state (`index`, `clarify_enabled`). First confirm that `present_turn` reads nothing but the stored result, such as the runtime kind or settings. If it reads anything else, include that in the key. The JSON for every thread must stay the same.
3. **Two answer readers in clarify.py (67-73, 195-206).** `_candidate_named_by_word` and the tail of `_company_named` both pick the one option whose words contain the answer's words, after filler is removed. Add `_only_option_holding(words: set[str], options: Iterable[tuple[str, set[str]]]) -> str | None`. The metric reader passes `(candidate, set(candidate.split("_")))`. The company reader passes `(ticker, words of label)` after its own subject-word subtraction. Keep each reader's filler handling and its unique-match rule exactly.
4. **config.py (213-227, 237-271).** Merge `validate_fmp_base_url` and `validate_tavily_base_url` into one `@field_validator("fmp_base_url", "tavily_base_url")` that names the field through `info.field_name`, as `validate_positive_seconds` already does. Add `_required(self, field: str, purpose: str) -> str`, which strips `getattr(self, field)` and raises the shared `ConfigurationError` message with `field.upper()`. Each `require_*` method keeps its public name and becomes one call. Every error message must stay word for word the same.
5. **The overview plan value, three copies** (planner.py:25, 52; planner_cascade.py:53). Import `OVERVIEW_PLAN` from request_wording into planner.py and planner_cascade.py, and delete `_OVERVIEW` and the literal "overview". request_wording does not import planner, so no cycle arises.
6. **The response schema chosen twice** (planner.py:368-370). `complete` recomputes `schema = Plan if current_spec is None else FollowUpPlan`; use `parsed = response_format.model_validate(parsed)` instead.

**Acceptance:** all tests pass, including the API and clarify tests; ruff and mypy are clean; a GET of a 10-turn stored thread returns the same JSON before and after, and a second GET calls `present_turn` for no stored turn; `uv run python scripts/compare_answers.py` reports `0 of N conversations differ`.

**Findings covered:**
- graph/simplification: thread_store resolve_results and resolve_last_result repeat the unreadable-answer guard
- turn/efficiency: thread_view re-reads and re-presents every stored turn on every GET
- graph/simplification: _candidate_named_by_word and _company_named both pick the only option holding the answer's words
- turn/simplification: config validators and require_* methods repeat one pattern
- reading/reuse: overview plan value spelled out three times (planner.py, planner_cascade.py, request_wording.py)
- reading/simplification: planner.complete recomputes the response schema

**Acceptance:** `uv run python -m pytest` passes; ruff and mypy are clean; `uv run python scripts/compare_answers.py` reports `0 of N conversations differ`; phrase coverage stays 555 of 555. If a step would change behaviour, or needs a file outside this ticket's list, leave it and say so in the Answer.

**Blocked by:** None — can start immediately

**Status:** ready-for-agent
