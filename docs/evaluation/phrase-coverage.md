# Phrase coverage

Generated `2026-10-06T17:36:44.323046+00:00` on the recorded runtime with the rules planner. 273 everyday phrasings of a metric, a window, a change or a follow-up, each asked as a whole question and judged by the README's [How a question is read](../../README.md#how-a-question-is-read). No network and no model. **273 of 273 (100%) are read right**; the live app's cascade would send 7 to the LLM planner.

| Group | Phrasings | Read right |
| --- | ---: | ---: |
| Metrics | 204 | 204 (100%) |
| Ambiguous metric words | 7 | 7 (100%) |
| Windows | 24 | 24 (100%) |
| Year over year | 11 | 11 (100%) |
| Quarter over quarter | 4 | 4 (100%) |
| Changes with no base | 4 | 4 (100%) |
| Follow-ups | 19 | 19 (100%) |

## Not read right

None.

Each miss is a gap in the shared reading of words, which every planner passes through (ADR 0010, 0011); `KNOWN_GAPS` in `phrase_coverage.py` lists them, and the test fails when a phrasing outside it is misread, or one on it starts being read right.

## Sent to the LLM planner

The live app plans with the cascade (ADR 0012): the rules planner, and the LLM planner on a turn the rules planner is unsure of. Here a stand-in that declines takes the LLM planner's place, so every answer above is the rules planner's. These are the phrasings the live app would send on, and so could read differently from this report.

| Question | Why the rules planner is unsure | Read right here |
| --- | --- | --- |
| `What was Apple's profit?` | no catalog metric | yes |
| `What was Apple's income?` | no catalog metric | yes |
| `What was Apple's margin?` | no catalog metric | yes |
| `What was Apple's cash flow?` | no catalog metric | yes |
| `What was Apple's interest?` | no catalog metric | yes |
| `What was Apple's expenses?` | no catalog metric | yes |
| `What was Apple's dividends?` | no catalog metric | yes |

`SENT_TO_MODEL` in `phrase_coverage.py` lists them with the reason each is expected, and the test fails when the list and the cascade disagree.
