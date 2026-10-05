# Numeral lock

Generated `2026-10-05T12:34:44.466088+00:00` on the recorded runtime. An essay about an answer may quote only the numbers in that answer's grounding, its table rows as JSON; the lock withholds an essay with any other number. Here the grounding of 10 recorded answers is quoted one value at a time, in each way below, and the lock is run on each sentence. No model is called: this measures the lock itself.

| A sentence that quotes | Should be withheld | Sentences | Withheld | Right |
| --- | :---: | ---: | ---: | ---: |
| the value exactly as the JSON holds it (22974000000, 0.3088273701) | no | 36 | 0 (0%) | 100% |
| the value as the window shows it ($22.97 B, 30.9%) | no | 36 | 36 (100%) | 0% |
| the shown value with its unit in words ($22.97 billion) | no | 36 | 36 (100%) | 0% |
| the shown value rounded to a whole number (about $23 billion) | no | 36 | 36 (100%) | 0% |
| the JSON value with its last digit changed | yes | 36 | 36 (100%) | 100% |
| the shown value with its last digit changed ($22.98 B) | yes | 36 | 36 (100%) | 100% |
| a number the answer does not hold (a growth rate of 17.3%) | yes | 36 | 36 (100%) | 100% |
| another company's value of the same metric, given as this company's | yes | 14 | 0 (0%) | 0% |
| a figure written out in words (twenty-three billion dollars) | yes | 36 | 0 (0%) | 0% |

How to read it: the lock compares digits. A number passes only when the same digits appear in the grounding, so it withholds any changed or invented figure, and also a true figure written the way the window shows it ($22.97 B, 30.9%) or rounded, because the grounding holds 22974000000 and 0.3088273701. It does not check meaning: a true value given to the wrong company passes, and so does a figure written in words. The essay prompt asks for numbers from the JSON as they are, so how often real essays are withheld depends on the model following that; this report does not measure that.

<details><summary>One sentence of each kind</summary>

- `exact_json` (passed): Eli Lilly and Company reported revenue of 22974000000 for the quarter.
- `as_shown` (withheld): Eli Lilly and Company reported revenue of $22.97 B for the quarter.
- `as_shown_in_words` (withheld): Eli Lilly and Company reported revenue of $22.97 billion for the quarter.
- `rounded` (withheld): Eli Lilly and Company reported revenue of about $23 billion for the quarter.
- `json_digit_changed` (withheld): Eli Lilly and Company reported revenue of 22974000001 for the quarter.
- `shown_digit_changed` (withheld): Eli Lilly and Company reported revenue of $22.98 B for the quarter.
- `invented` (withheld): Eli Lilly and Company reported revenue of 22974000000 for the quarter. That is growth of 17.3% from a year earlier.
- `misattributed` (passed): Eli Lilly and Company reported revenue of 15034000000 for the quarter.
- `in_words` (passed): Eli Lilly and Company reported revenue of twenty-three billion dollars for the quarter.

</details>
