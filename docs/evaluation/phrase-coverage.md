# Phrase coverage

Generated `2026-10-06T16:53:13.341240+00:00` on the recorded runtime with the rules planner. 273 everyday phrasings of a metric, a window, a change or a follow-up, each asked as a whole question and judged by the README's [How a question is read](../../README.md#how-a-question-is-read). No network and no model. **273 of 273 (100%) are read right.**

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
