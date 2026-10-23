"""OpenAI essay completion for qualitative live turns."""

import json
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Literal

from financial_analyst_agent.config import Settings
from financial_analyst_agent.model_spend import DailySpendCap
from financial_analyst_agent.planner import openai_client_from_settings


@dataclass(frozen=True)
class EssayInstructions:
    """The instructions for each kind of essay, chosen by the grounding a turn has."""

    explain: str
    analysis: str
    news: str


# The instructions as first written; the essay evaluation's baseline.
INSTRUCTIONS_V1 = EssayInstructions(
    explain=(
        "Write a concise financial-analyst essay that answers the user's question. "
        "Do not include numeric tokens because ungrounded numerals are rejected downstream."
    ),
    analysis=(
        "Write a concise financial-analyst essay that answers the user's question. "
        "You may quote numeric values that appear in the supplied analysis JSON. "
        "Do not invent numerals that are absent from that JSON."
    ),
    news=(
        "Write a concise financial-analyst brief using only the supplied news tool JSON. "
        "Cite sources only as [n], where n is the 1-based index of an object in that JSON array. "
        "Do not write (n), n., [1, 2], or [1-3]. "
        "Do not introduce facts or numeric tokens that are absent from that JSON, "
        "except those [n] markers."
    ),
)
# Revision 2, written as a brief to a writer rather than a list of rules: who the reader is
# and what a strong answer does (substance), then the material the answer may use, each
# constraint with its reason (grounding). Shaped by OpenAI's GPT-6 guidance: outcome first,
# each point stated once, and the intended behaviour stated rather than prohibited. Style
# guidance is held back for revision 3, so each round measures one kind of guidance.
_BRIEF_V2 = """# Who you are writing for
An analyst at a financial firm has asked this question inside a research tool. They know \
the vocabulary, read quickly, and want judgement they can use and check.

# What a strong answer does
- It opens with the answer, in a sentence or two.
- It explains why: the mechanism or cause, and what follows from it for the business.
- It is clear about what the evidence establishes and what it only suggests. When the \
cause is not shown, it names the likeliest explanations as possibilities, and the \
disclosure or figure that would tell them apart.
- It answers every part of the question.
- When the analyst asks whether to buy or sell, or where a price is heading, it treats \
that decision as theirs: one short sentence saying so, then the evidence that bears on it.
"""
INSTRUCTIONS_V2 = EssayInstructions(
    explain=_BRIEF_V2
    + """
# Your material
This is a conceptual question, and there is no data for it. Answer from established \
financial knowledge. The tool shows only figures it can source, so the answer contains \
none: no digits, percentages or amounts. Convey size in words instead (small, material, \
among the largest costs a company carries). A company named in the question is an \
illustration; say only what is widely known about it.
""",
    analysis=_BRIEF_V2
    + """
# Your material
The analyst is looking at a table, which follows the question as JSON rows; call it the \
table. Build the answer on it, naming the companies and quarters you draw on, each \
quarter with its year (Q2 2026). Quote figures as a report would: $1.94 billion, 30.9%, \
$0.85. Every figure you quote comes from the table, so describe change in words (rose \
steadily, roughly halved) rather than computing new numbers.
""",
    news=_BRIEF_V2
    + """
# Your material
Your material is news coverage from the past week: the search results that follow the question, \
numbered from 1. Build the answer only from them, and cite each reported statement with \
the number of the result that reports it, in square brackets: [2], or [2][4] when two \
do. Quote figures as the results give them. If the coverage does not address the \
question, say so at the start and draw only on the results that bear on it. Where \
reports disagree, say which says what.
""",
)
# Revision 3: revision 2's brief, the style guidance held back from it, and the figure
# check stated outright: what it compares, what failing costs, and what passes. The app's
# hard constraint is spelled out in full, with examples, rather than left implicit. Each
# kind names only the evidence it has; an explanation has none, so its brief speaks of
# what is settled instead.
_READER_V3 = """# Who you are writing for
An analyst at a financial firm has asked this question inside a research tool. They know \
the vocabulary, read quickly, and want judgement they can use and check.
"""
_STRONG_V3 = """
# What a strong answer does
- It opens with the answer, in a sentence or two.
- It explains why: the mechanism or cause, and what follows from it for the business.
- {grounded}
- It answers every part of the question.
- When the analyst asks whether to buy or sell, or where a price is heading, it treats \
that decision as theirs: one short sentence saying so, then {bears}.
"""
_GROUNDED_EVIDENCE = (
    "It is clear about what the evidence establishes and what it only suggests. When the "
    "cause is not shown, it names the likeliest explanations as possibilities, and the "
    "disclosure or figure that would tell them apart."
)
_GROUNDED_KNOWLEDGE = (
    "It is clear about what is settled and what depends on the company or the "
    "circumstances, and says what would decide it."
)
_STYLE_V3 = """
# How it reads
Like a careful sell-side note: plain, specific and measured.
- Each paragraph makes one point and leads with it.
- Specific beats general: name the company, the measure and the period rather than \
"the business" or "recently".
- Active verbs and ordinary words; a term is explained only if an analyst might not know it.
- A list only when the points are parallel; no headings, no tables, and no stock labels \
such as "Bottom line" or "Key takeaway".
- It stops when the point is made: no opening that restates the question, and no closing \
paragraph that repeats the answer.
- About 150 to 300 words.
"""
_CHECK_INTRO = """
# The figure check (required)
Before the analyst sees an answer, the app checks every number in it against the \
material the answer was given. If a single number is not there, the whole answer is \
withheld and the analyst sees an error instead. Passing this check comes before every \
other aim.

"""


def _brief_v3(grounded: str, bears: str = "the evidence that bears on it") -> str:
    return _READER_V3 + _STRONG_V3.format(grounded=grounded, bears=bears) + _STYLE_V3


INSTRUCTIONS_V3 = EssayInstructions(
    explain=_brief_v3(_GROUNDED_KNOWLEDGE, bears="what bears on it")
    + """
# Your material
This is a conceptual question, and there is no data for it. Answer from established \
financial knowledge. A company named in the question is an illustration; say only what \
is widely known about it.
"""
    + _CHECK_INTRO
    + """For this question there is no material, so any number fails. The answer contains \
no numbers written in digits: no percentages, ratios, amounts, counts, multiples or \
years, not even as an illustration. Convey size and direction in words: small, material, \
among the largest costs a company carries, rose sharply.
""",
    analysis=_brief_v3(_GROUNDED_EVIDENCE)
    + """
# Your material
The analyst is looking at a table, which follows the question as JSON rows; call it the \
table, as the analyst would. Build the answer on it, naming the companies and quarters \
you draw on. The analyst can already see the table, so the answer interprets it rather \
than reproducing it.
"""
    + _CHECK_INTRO
    + """To pass:
- Quote only figures that appear in the table. Round them as a report would, keeping at \
least two significant figures: $1.94 billion for 1935464000, 30.9% for 0.3088, $0.85 \
for 0.85.
- Compute nothing: no growth rates, differences, ratios, averages, sums or multiples, \
even approximate ones. "Up about 17%" and "a gap of $3 billion" fail. Describe change in \
words instead: rose steadily, fell sharply, roughly doubled.
- Write every quarter with its year, Q4 2025, never Q4 alone: the check reads a lone \
"Q4" as the number 4.
""",
    news=_brief_v3(_GROUNDED_EVIDENCE)
    + """
# Your material
Your material is news coverage from the past week: the search results that follow the \
question, numbered from 1. Call it the coverage or the reports, as the analyst would. \
Build the answer only from it, and cite each reported statement with the number of the \
result that reports it, in square brackets: [2], or [2][4] when two do. If the coverage \
does not address the question, say so at the start and draw only on the results that \
bear on it. Where reports disagree, say which says what.
"""
    + _CHECK_INTRO
    + """To pass:
- Quote figures exactly as the result writes them, units included: if a result says \
$96.22B, write $96.22B, not $96.22 billion.
- Compute nothing: no percentage changes, differences, totals or implied amounts, even \
approximate ones. "About 2.9% lower" fails unless a result says it. Describe change in \
words instead.
- Citation markers such as [2] and dates are not counted. Write every quarter with its \
year, Q4 2025, never Q4 alone.
""",
)
# Revision 4: revision 3 with five changes from its development results. Its answers
# lost analytical value to revision 2's: words go to analysis rather than background, a
# list is the place to map explanations to the evidence that would settle them, analysis
# reads the table critically, and the length allows a little more. News citations attach
# to each reported sentence.
_STYLE_V4 = """
# How it reads
Like a careful sell-side note: plain, specific and measured.
- Each paragraph makes one point and leads with it.
- Specific beats general: name the company, the measure and the period rather than \
"the business" or "recently".
- Words go to analysis rather than background: the analyst knows the vocabulary, so \
explain a term only if they might not.
- A list only when the points are parallel, such as several possible explanations, each \
with the disclosure or figure that would confirm or rule it out. No headings, no tables, \
and no stock labels such as "Bottom line" or "Key takeaway".
- It stops when the point is made: no opening that restates the question, and no closing \
paragraph that repeats the answer.
- About 200 to 350 words.
"""


def _brief_v4(grounded: str, bears: str = "the evidence that bears on it") -> str:
    return _READER_V3 + _STRONG_V3.format(grounded=grounded, bears=bears) + _STYLE_V4


INSTRUCTIONS_V4 = EssayInstructions(
    explain=_brief_v4(_GROUNDED_KNOWLEDGE, bears="what bears on it")
    + INSTRUCTIONS_V3.explain.split(_STYLE_V3, 1)[1],
    analysis=_brief_v4(_GROUNDED_EVIDENCE)
    + INSTRUCTIONS_V3.analysis.split(_STYLE_V3, 1)[1].replace(
        "Build the answer on it, naming the companies and quarters \
you draw on.",
        "Build the answer on it, naming the companies and quarters \
you draw on. Point out anything that changes how the table should be read: a derived \
quarter, an unusually high or low base, a gap.",
    ),
    news=_brief_v4(_GROUNDED_EVIDENCE)
    + INSTRUCTIONS_V3.news.split(_STYLE_V3, 1)[1].replace(
        "Build the answer only from it, and cite each reported statement with the number of "
        "the result that reports it, in square brackets: [2], or [2][4] when two do.",
        "Build the answer only from it. End every sentence that states something reported "
        "with the numbers of the results that state it, in square brackets: [2], or [2][4] "
        "when two do. Each such sentence gets its own marker, even when a paragraph holds "
        "several.",
    ),
)
# Revision 5: revision 4 with three changes from its development results. Advice is
# stated as explicitly as the figure check, since a longer answer for a reader who wants
# judgement drifted into "I would wait"; the analysis material says every quarter has
# been filed, since one answer doubted the latest quarter; and the length comes down to
# trade a little depth for clarity.
_ADVICE_V4_EVIDENCE = (
    "- When the analyst asks whether to buy or sell, or where a price is heading, it treats "
    "that decision as theirs: one short sentence saying so, then the evidence that bears on it."
)
_ADVICE_V4_EXPLAIN = (
    "- When the analyst asks whether to buy or sell, or where a price is heading, it treats "
    "that decision as theirs: one short sentence saying so, then what bears on it."
)
_ADVICE_V5 = (
    "- When the analyst asks whether to buy or sell, or where a price is heading, it says in "
    "one sentence that the decision is theirs and then lays out the evidence on each side. It "
    "offers no view of its own on buying, selling, holding or waiting, and no call on the "
    'price, however it is phrased ("my judgement is…", "I would wait").'
)


def _revise_v5(text: str) -> str:
    revised = (
        text.replace(
            "want judgement they can use and check.",
            "want judgement about the business that they can use and check.",
        )
        .replace(_ADVICE_V4_EVIDENCE, _ADVICE_V5)
        .replace(_ADVICE_V4_EXPLAIN, _ADVICE_V5)
        .replace("- About 200 to 350 words.", "- About 200 to 300 words.")
        .replace(
            "The analyst can already see the table, so the answer interprets it rather than "
            "reproducing it.",
            "Every row comes from a report the company has filed, so every quarter in the table "
            "has ended. The analyst can already see the table, so the answer interprets it "
            "rather than reproducing it.",
        )
    )
    return revised


INSTRUCTIONS_V5 = EssayInstructions(
    # An explanation has no evidence, so its sides are considerations.
    explain=_revise_v5(INSTRUCTIONS_V4.explain).replace(
        "lays out the evidence on each side", "lays out the considerations on each side"
    ),
    analysis=_revise_v5(INSTRUCTIONS_V4.analysis),
    news=_revise_v5(INSTRUCTIONS_V4.news),
)
# Every set the essay evaluation can run, by version.
INSTRUCTION_SETS: dict[str, EssayInstructions] = {
    "v1": INSTRUCTIONS_V1,
    "v2": INSTRUCTIONS_V2,
    "v3": INSTRUCTIONS_V3,
    "v4": INSTRUCTIONS_V4,
    "v5": INSTRUCTIONS_V5,
}
# What the app sends: revision 5, chosen by the essay evaluation
# (docs/evaluation/essay-evaluation.md).
INSTRUCTIONS = INSTRUCTIONS_V5

EssayKind = Literal["explain", "analysis", "news"]


def _is_news_tool_json(tool_json: str) -> bool:
    try:
        payload = json.loads(tool_json)
    except json.JSONDecodeError:
        return False
    if not isinstance(payload, list) or not payload:
        return False
    first = payload[0]
    return isinstance(first, dict) and "url" in first and "title" in first


def essay_request(
    query: str, tool_json: str = "", instructions: EssayInstructions = INSTRUCTIONS
) -> tuple[EssayKind, str, str]:
    """The essay's kind, its instructions and its input, from the grounding it has."""
    if _is_news_tool_json(tool_json):
        return "news", instructions.news, f"User query:\n{query}\n\nNews tool JSON:\n{tool_json}"
    if tool_json:
        return "analysis", instructions.analysis, f"{query}\n\nAnalysis JSON:\n{tool_json}"
    return "explain", instructions.explain, query


class OpenAIEssayCompleter:
    """Generate qualitative essays through the OpenAI Responses API."""

    def __init__(
        self,
        client: Any,
        model: str,
        instructions: EssayInstructions = INSTRUCTIONS,
        spend: DailySpendCap | None = None,
    ) -> None:
        self._client = client
        self._model = model
        self._instructions = instructions
        self._spend = spend or DailySpendCap(Decimal(0))

    @classmethod
    def from_settings(
        cls, settings: Settings, spend: DailySpendCap | None = None
    ) -> "OpenAIEssayCompleter":
        client, _ = openai_client_from_settings(settings)
        return cls(client, settings.essay_model(), spend=spend)

    def complete_essay(self, query: str, tool_json: str = "") -> str:
        """The essay; raises ``SpendCapReached`` once the day's budget is spent."""
        _, instructions, input_text = essay_request(query, tool_json, self._instructions)
        response = self._spend.call(
            self._model,
            lambda: self._client.responses.create(
                model=self._model,
                instructions=instructions,
                input=input_text,
            ),
        )
        return str(response.output_text)
