"""Typed state of the analysis graph (ADR 0005).

Run state is what one turn proposes, resolves, and answers: it lives in the
graph's channels and is checkpointed only while the graph is paused on a
clarification. Thread state (the active analysis spec, the last answer, the
evidence) stays in the thread record and reaches the graph as per-turn
context, never as a channel. Evidence is referenced by identifier, so a
checkpoint holds the held question and its patch, not fetched facts.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal, TypedDict

from pydantic import BaseModel, Field, model_validator

from financial_analyst_agent.contracts import (
    ClarifyKind,
    ComparisonBase,
    FilingForm,
    Intent,
    Runtime,
    TurnResult,
)
from financial_analyst_agent.graph.analysis_spec import AnalysisSpec, CompiledTask, SpecPatch
from financial_analyst_agent.period_selection import WindowReading, read


@dataclass(frozen=True)
class TurnDeps:
    """The graph's per-turn context (LangGraph ``context``): read by nodes, never checkpointed.

    ``runtime`` is the provider set, its facts port wrapped with the thread's
    evidence cache. ``active_spec`` is the thread's analysis when the turn began;
    ``grounding`` reads the deterministic rows of the thread's last answer, on demand,
    for an essay's numeral lock.
    """

    runtime: Runtime
    active_spec: AnalysisSpec | None
    grounding: Callable[[], str]
    max_workers: int
    on_progress: Callable[[int, int], None] | None = None


class PendingClarification(BaseModel):
    """Analysis held awaiting the analyst's answer. Nothing has been fetched."""

    kind: ClarifyKind
    candidates: tuple[str, ...]
    patch: SpecPatch
    intent: Intent = Intent.LOOKUP
    metric_role: Literal["add", "remove"] = "add"
    # The question that was held, so an answer like "replace" resumes it rather
    # than being read as a question of its own. Empty in threads saved before.
    question: str = ""
    # For "which company": the name that was ambiguous, and how each candidate
    # was shown ("Coca-Cola Consolidated (COKE)").
    subject: str = ""
    labels: tuple[str, ...] = ()


class StructuredRequest(BaseModel):
    """A number-path request: the model's proposed patch, never executed as given.

    ``wording`` is what deterministic resolution reads for metrics and periods
    (ADR 0004: the analyst's words, not a model slug). ``question`` is what a
    clarification would hold. ``window`` is the one reading of the wording's
    window words, read here when the request is made or loaded. ``intent`` is
    the closed intent the planner named, if any; refusals name it.
    """

    patch: SpecPatch
    wording: str
    question: str
    window: WindowReading = Field(default_factory=lambda data: read(data["wording"]).reading)
    intent: Intent | None = None
    # The planner's notes (a corrected company name), shown before the answer's own.
    notes: tuple[str, ...] = ()
    # Companies the analyst named that the recorded runtime has no filings for.
    unrecorded: tuple[str, ...] = ()
    # What a change is measured against, as the analyst chose when asked.
    comparison: ComparisonBase | None = None
    # A shared name the analyst was asked about, and the ticker they chose
    # ("Lincoln", "LNC"): the held wording names the company again on resume.
    company_choice: tuple[str, str] | None = None

    @model_validator(mode="before")
    @classmethod
    def _read_window(cls, value: Any) -> Any:
        # A checkpoint saved while the window was optional holds "window": null;
        # it is read from the wording as a request made without one is.
        if isinstance(value, dict) and "window" in value and value["window"] is None:
            return {key: item for key, item in value.items() if key != "window"}
        return value


QualitativeIntent = Literal[Intent.EXPLAIN, Intent.NEWS_AND_EXPLAIN, Intent.EXPLORATORY_RESEARCH]


class QualitativeRequest(BaseModel):
    """An essay request: explanation, current events, or exploratory research."""

    intent: QualitativeIntent
    topic: str


# The filing sections a comparison reads.
SectionId = Literal["mda", "risk_factors"]


class FilingChangeRequest(BaseModel):
    """Two filings of one company to compare, read from the question once (ADR 0010).

    ``filing_change.bind_filing_change`` fills it from the planner's plan and the
    question's words; the comparison reads only this.
    """

    company: str = ""
    # Both empty: the latest filing against the one a year earlier.
    older_accession: str = ""
    newer_accession: str = ""
    # Every accession number the question gave, in order: more than two, or one
    # given twice, is refused.
    named_accessions: tuple[str, ...] = ()
    sections: tuple[SectionId, ...] = ("mda",)
    form: FilingForm = "10-Q"
    # Asked for the model's summary of the changes as well as the changes.
    summarize: bool = False
    # Further companies named: a comparison covers one company at a time.
    other_companies: tuple[str, ...] = ()


AnalystRequest = StructuredRequest | QualitativeRequest | FilingChangeRequest


class CompiledAnalysis(BaseModel):
    """A resolved, validated spec and its typed tasks: the structured subgraph's input."""

    spec: AnalysisSpec
    tasks: tuple[CompiledTask, ...]
    patch: SpecPatch
    wording: str
    window: WindowReading = Field(default_factory=WindowReading)
    # The analysis the patch was applied to, to say what was already in it.
    prior_spec: AnalysisSpec | None = None
    notes: tuple[str, ...] = ()
    annual_filers: tuple[str, ...] = ()
    # Funds named beside a company, left out of the table: (ticker, SEC name).
    funds: tuple[tuple[str, str], ...] = ()
    unrecorded: tuple[str, ...] = ()
    # A ranking asked over a window it does not show: its note says so.
    ranked_window_asked: bool = False


class Clarification(BaseModel):
    """What the graph pauses on: the held question and the answer that asks it.

    ``result`` is the CLARIFY answer shown for this turn; ``analysis_spec`` is the
    analysis that answer stands for (none for a new question, the thread's own
    when a question is asked again).
    """

    pending: PendingClarification
    result: TurnResult
    analysis_spec: AnalysisSpec | None = None


class AnalysisRun(TypedDict):
    """The parent graph's channels: one turn's run state."""

    # The analyst's message, markdown stripped. A clarification resume replaces it.
    message: str
    request: AnalystRequest | None
    # Set while the graph waits on (or is about to ask) the one open question.
    clarification: Clarification | None
    # The patch as resolution applied it.
    patch: SpecPatch | None
    compiled: CompiledAnalysis | None
    result: TurnResult | None
    # The analysis this turn answered, and the one the thread keeps after it.
    analysis_spec: AnalysisSpec | None
    thread_spec: AnalysisSpec | None
    # This turn set an open clarification aside to answer a new question.
    set_aside: bool


def fresh_run(message: str) -> AnalysisRun:
    """Every channel for a new turn, so nothing carries over from an earlier one."""
    return AnalysisRun(
        message=message,
        request=None,
        clarification=None,
        patch=None,
        compiled=None,
        result=None,
        analysis_spec=None,
        thread_spec=None,
        set_aside=False,
    )


# Every model the checkpoint may hold, for the deserialization allowlist.
CHECKPOINTED_TYPES: tuple[type, ...] = (
    PendingClarification,
    StructuredRequest,
    QualitativeRequest,
    FilingChangeRequest,
    CompiledAnalysis,
    Clarification,
    SpecPatch,
    AnalysisSpec,
    TurnResult,
)
