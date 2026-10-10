"""OpenAI essay completion for qualitative live turns."""

import json
from dataclasses import dataclass
from typing import Any, Literal

from financial_analyst_agent.config import Settings
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
# Every set the essay evaluation can run, by version.
INSTRUCTION_SETS: dict[str, EssayInstructions] = {"v1": INSTRUCTIONS_V1}
# What the app sends.
INSTRUCTIONS = INSTRUCTIONS_V1

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
        self, client: Any, model: str, instructions: EssayInstructions = INSTRUCTIONS
    ) -> None:
        self._client = client
        self._model = model
        self._instructions = instructions

    @classmethod
    def from_settings(cls, settings: Settings) -> "OpenAIEssayCompleter":
        client, _ = openai_client_from_settings(settings)
        return cls(client, settings.essay_model())

    def complete_essay(self, query: str, tool_json: str = "") -> str:
        _, instructions, input_text = essay_request(query, tool_json, self._instructions)
        response = self._client.responses.create(
            model=self._model,
            instructions=instructions,
            input=input_text,
        )
        return str(response.output_text)
