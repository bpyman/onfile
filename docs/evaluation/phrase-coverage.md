# Phrase coverage

Generated `2026-10-07T23:41:38.233995+00:00` on the recorded runtime with the rules planner. 555 everyday phrasings of a metric, a window, a change or a follow-up, each asked as a whole question and judged by the README's [How a question is read](../../README.md#how-a-question-is-read). No network and no model. **555 of 555 (100%) are read right**; the live app's cascade would send 14 to the LLM planner.

| Group | Phrasings | Read right |
| --- | ---: | ---: |
| Metrics | 208 | 208 (100%) |
| Ambiguous metric words | 7 | 7 (100%) |
| Windows | 41 | 41 (100%) |
| Year over year | 11 | 11 (100%) |
| Growth with no metric | 5 | 5 (100%) |
| Quarter over quarter | 4 | 4 (100%) |
| A named period with a change | 1 | 1 (100%) |
| Both bases | 6 | 6 (100%) |
| Changes with no base | 10 | 10 (100%) |
| A change over a window | 13 | 13 (100%) |
| Idioms beside a company | 6 | 6 (100%) |
| Everyday-word names used as the word | 7 | 7 (100%) |
| A segment names its company | 7 | 7 (100%) |
| Overviews | 10 | 10 (100%) |
| Unknown measures | 19 | 19 (100%) |
| General questions | 21 | 21 (100%) |
| Rankings | 21 | 21 (100%) |
| Follow-ups | 19 | 19 (100%) |
| Change switches | 6 | 6 (100%) |
| Combinations | 98 | 98 (100%) |
| Follow-up combinations | 35 | 35 (100%) |

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
| `What's the EPS?` | no company | yes |
| `What is the EPS?` | no company | yes |
| `What's the revenue?` | no company | yes |
| `What was the revenue last quarter?` | no company | yes |
| `What was net income this quarter?` | no company | yes |
| `Net margin last quarter?` | no company | yes |
| `What was net interest income?` | no company | yes |

`SENT_TO_MODEL` in `phrase_coverage.py` lists them with the reason each is expected, and the test fails when the list and the cascade disagree.
