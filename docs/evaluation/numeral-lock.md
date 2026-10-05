# Numeral lock

Generated `2026-10-05T13:37:31.577751+00:00` on the recorded runtime. An essay about an answer may quote only the numbers in that answer's grounding, its table rows as JSON; the lock withholds an essay with any other number. Here the grounding of 10 recorded answers is quoted one value at a time, in each way below, and the lock is run on each sentence. No model is called: this measures the lock itself.

| A sentence that quotes | Should be withheld | Sentences | Withheld | Right |
| --- | :---: | ---: | ---: | ---: |
| the value exactly as the JSON holds it (22974000000, 0.3088273701) | no | 36 | 0 (0%) | 100% |
| the value as the window shows it ($22.97 B, 30.9%) | no | 36 | 0 (0%) | 100% |
| the shown value with its unit in words ($22.97 billion) | no | 36 | 0 (0%) | 100% |
| the shown value rounded to a whole number (about $23 billion) | no | 36 | 12 (33%) | 67% |
| the JSON value with its last digit changed | yes | 36 | 36 (100%) | 100% |
| the shown value with its last digit changed ($22.98 B) | yes | 36 | 36 (100%) | 100% |
| a number the answer does not hold (a growth rate of 17.3%) | yes | 36 | 36 (100%) | 100% |
| another company's value of the same metric, given as this company's | yes | 14 | 0 (0%) | 0% |
| a figure written out in words (twenty-three billion dollars) | yes | 36 | 0 (0%) | 0% |

How to read it: a number passes when the grounding holds it, or when it rounds from a grounded value at the precision it is written to, with at least two significant digits: $22.97 B, $22.97 billion, about $23 billion and 30.9% all round from 22974000000 or 0.3088273701. A digit changed at that precision, or a number nothing grounded rounds to, is withheld. A figure rounded to one significant digit (about $2 for $2.46) is too coarse to tie to one value and is withheld too: those are the rounded sentences withheld above.

It checks numbers, not meaning: a true value given to the wrong company passes, and so does a figure written in words. Until 5 October 2026 the lock matched digits exactly, and withheld every true figure written as the window shows it or rounded (100% of those sentences); exact quotes and changed or invented numbers were treated as now.

<details><summary>One sentence of each kind</summary>

- `exact_json` (passed): Eli Lilly and Company reported revenue of 22974000000 for the quarter.
- `as_shown` (passed): Eli Lilly and Company reported revenue of $22.97 B for the quarter.
- `as_shown_in_words` (passed): Eli Lilly and Company reported revenue of $22.97 billion for the quarter.
- `rounded` (passed): Eli Lilly and Company reported revenue of about $23 billion for the quarter.
- `json_digit_changed` (withheld): Eli Lilly and Company reported revenue of 22974000001 for the quarter.
- `shown_digit_changed` (withheld): Eli Lilly and Company reported revenue of $22.98 B for the quarter.
- `invented` (withheld): Eli Lilly and Company reported revenue of 22974000000 for the quarter. That is growth of 17.3% from a year earlier.
- `misattributed` (passed): Eli Lilly and Company reported revenue of 15034000000 for the quarter.
- `in_words` (passed): Eli Lilly and Company reported revenue of twenty-three billion dollars for the quarter.

</details>
