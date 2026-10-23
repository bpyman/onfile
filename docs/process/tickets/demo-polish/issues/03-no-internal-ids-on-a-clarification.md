# A clarification shows no internal ids

From the product review (presentation fixes). On the live demo, "Why did Target's gross margin jump last quarter?" asked "Compared with what?" with two buttons, "The same quarter a year earlier (year over year)" and "The quarter before (sequential)". Under each label, in small mono type, sat `year_over_year` and `sequential`. The first is an internal id, not words a visitor would type.

**Files (this ticket only):** `web/components/clarify.tsx`, its test, and whatever renders the analyst's message after a button is pressed (`web/components/thread.tsx` or the message component), with tests.

**What to build:** `clarify.tsx` shows the slug under the label when `choice.slug.replaceAll("_", " ")` differs from the whole label. Its comment says the slug is shown because it is "what the button sends", which is useful when the words differ ("net income" under "Net income (NetIncomeLoss)"). Change the rule so a visitor never sees an id:

- Show the slug as words (underscores as spaces).
- Show it only when those words are not already in the label (case-insensitive containment, not equality). "(year over year)" is in the first label, so nothing is shown under it.
- Check what the analyst's own message reads after a button is pressed. If the thread shows `year_over_year` as the visitor's message, show the words ("year over year") instead, without changing what is sent to the API.

**Acceptance:**
- Component tests: a comparison-base clarification shows no slug line, and no underscore appears anywhere in the rendered clarification.
- A metric clarification whose slug words differ from the label still shows them.
- If the message bubble needed a change, a test pins it.
- `npm run lint`, `npx tsc --noEmit`, `npx vitest run` and `npm run build` pass. On this Windows machine `npm run build` fails under Git Bash with Turbopack error 0xc0000142 and passes from PowerShell (`powershell -Command "cd web; npm run build"`), so run it there.
- The Python answers are untouched: `compare_answers.py` reports 0 differences.

**Blocked by:** None — can start immediately

**Status:** ready-for-agent
