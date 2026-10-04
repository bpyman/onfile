"""Reading the analyst's reply to an open clarification (ADR 0004, ADR 0005).

The graph pauses on one open question. The next message either answers it
(a candidate's name, its number, "both", or another catalog metric), keeps it
open (a period for the held question, or an option out of range), or asks
something new, which sets the held question aside. These functions decide
which, deterministically; the model has no say in it.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from financial_analyst_agent.contracts import (
    ClarifyKind,
    ComparisonBase,
    RendererKind,
    TurnResult,
)
from financial_analyst_agent.graph.analysis_spec import AnalysisSpec, SpecPatch
from financial_analyst_agent.graph.state import (
    Clarification,
    PendingClarification,
    StructuredRequest,
)
from financial_analyst_agent.issuer_index import CompanyNames
from financial_analyst_agent.request_wording import bind_periods_from_message, is_removal
from financial_analyst_agent.services.metric_catalog import resolve_metric_phrase

_NEW_QUESTION = re.compile(r"\b(?:what|which|how|compare|versus|vs)\b|['’]s\b", re.IGNORECASE)
_ASKS = re.compile(r"\b(?:what|which|how|why|compare)\b|['’]s\b", re.IGNORECASE)
_MAX_ANSWER_WORDS = 6
_ORDINAL_WORDS = {"first": 1, "second": 2, "third": 3, "fourth": 4, "one": 1, "two": 2, "three": 3}
_ORDINAL_ANSWER = re.compile(
    r"(?:option |number |#)?(\d{1,2}|first|second|third|fourth|one|two|three)(?: one| option)?"
    r"|(?:the )?(first|second|third|fourth)(?: one| option)?"
)
# "all of them", "all three", "both": every option shown.
_EVERY_ANSWER = re.compile(
    r"(?:all|every|each)(?: of them| of those| three| 3| four| 4)?|everything|both"
)
# Words around an answer that choose nothing: "the net one please".
_ANSWER_FILLER = frozenset(
    """
    the one ones please pls i mean meant want wanted just show me option pick choose go
    with ok okay yes yeah use that thanks thank you lets let's do give figure
    """.split()  # noqa: SIM905
)
_ANSWER_PARTS = re.compile(r"\s*(?:,|&|\band\b|\bplus\b)\s*")
_ADD_WORDS = re.compile(r"(?:and|also|plus|add|include|with)\b", re.IGNORECASE)


@dataclass(frozen=True)
class ClarifyReply:
    """How a message answers an open clarification."""

    chosen: tuple[str, ...] = ()
    # "last 4 quarters": a period for the held question; the metric is still open.
    period_patch: SpecPatch | None = None
    # "4" when three options were shown: ask again.
    out_of_range: bool = False


def _candidate_named_by_word(candidates: tuple[str, ...], message: str) -> str | None:
    """ "net" or "per share" picks the one candidate whose name holds those words."""
    words = set(re.findall(r"[a-z]+", message.casefold())) - _ANSWER_FILLER
    if not words:
        return None
    named = [candidate for candidate in candidates if words <= set(candidate.split("_"))]
    return named[0] if len(named) == 1 else None


def match_clarification_answer(pending: PendingClarification, message: str) -> str | None:
    """The one candidate the message chooses, or None."""
    reply = clarification_reply(pending, message)
    return reply.chosen[0] if reply is not None and len(reply.chosen) == 1 else None


def clarification_reply(
    pending: PendingClarification, message: str, index: CompanyNames | None = None
) -> ClarifyReply | None:
    """How the message answers the open question; None when it asks a new one."""
    text = message.strip().casefold().rstrip(".!?")
    plain = " ".join(word for word in text.split() if word not in _ANSWER_FILLER) or text
    ordinal = _ORDINAL_ANSWER.fullmatch(plain) or _ORDINAL_ANSWER.fullmatch(text)
    if ordinal is not None:
        # "2" or "the second one" picks from the options as they were shown.
        raw = ordinal.group(1) or ordinal.group(2)
        position = int(raw) if raw.isdigit() else _ORDINAL_WORDS[raw]
        if 1 <= position <= len(pending.candidates):
            return ClarifyReply(chosen=(pending.candidates[position - 1],))
        return ClarifyReply(out_of_range=True)
    return CLARIFY_KINDS[pending.kind].read(_Answer(pending, message, text, plain, index))


@dataclass(frozen=True)
class _Answer:
    """A reply to an open question, as each kind's reader takes it."""

    pending: PendingClarification
    message: str
    # Casefolded, without end punctuation; ``plain`` also without filler words.
    text: str
    plain: str
    index: CompanyNames | None


def _read_scope(answer: _Answer) -> ClarifyReply | None:
    for candidate in answer.pending.candidates:
        if answer.text == candidate.casefold():
            return ClarifyReply(chosen=(candidate,))
    return None


def _read_company(answer: _Answer) -> ClarifyReply | None:
    named = _company_named(answer.pending, answer.text, answer.index)
    return ClarifyReply(chosen=(named,)) if named is not None else None


def _read_comparison(answer: _Answer) -> ClarifyReply | None:
    if _asks_anew(answer.message, answer.index):
        # "Microsoft net income last quarter" names a quarter, but is a new question.
        return None
    base = _comparison_named(answer.text)
    return ClarifyReply(chosen=(base,)) if base is not None else None


def _read_metric(answer: _Answer) -> ClarifyReply | None:
    pending, message, plain, index = answer.pending, answer.message, answer.plain, answer.index
    if _NEW_QUESTION.search(message) or len(message.split()) > _MAX_ANSWER_WORDS:
        # "What was Microsoft's net income?" names a candidate but is a new
        # question; answering the held patch would drop its company.
        return None
    if index is not None and index.find(message):
        # "Microsoft net margin" is a question about Microsoft.
        return None
    if _EVERY_ANSWER.fullmatch(plain) and (plain != "both" or len(pending.candidates) == 2):
        return ClarifyReply(chosen=pending.candidates)
    chosen = _metrics_named(pending.candidates, plain)
    if chosen:
        return ClarifyReply(chosen=chosen)
    periods = bind_periods_from_message(SpecPatch(mode="extend"), message)
    if periods != SpecPatch(mode="extend"):
        return ClarifyReply(period_patch=periods)
    return None


_YEAR_ANSWER = re.compile(r"\b(?:year|yoy|annual|annually|yearly)\b")
_QUARTER_ANSWER = re.compile(r"\b(?:quarter|qoq|sequential|sequentially|before|previous|prior)\b")


def _asks_anew(message: str, index: CompanyNames | None) -> bool:
    """Whether a reply is a question of its own: it asks, names a company or a metric.

    "vs the previous quarter" answers "Compared with what?", so "vs" alone asks nothing.
    """
    if _ASKS.search(message):
        return True
    if resolve_metric_phrase(message).kind != "unknown":
        return True
    return index is not None and bool(index.find(message))


def _comparison_named(text: str) -> ComparisonBase | None:
    """ "year over year", "the quarter before", "sequential": one base, or None."""
    if text == "year_over_year":
        return "year_over_year"
    if text == "sequential":
        return "sequential"
    if len(text.split()) > _MAX_ANSWER_WORDS:
        return None
    words = text.replace("-", " ").replace("_", " ")
    year = _YEAR_ANSWER.search(words) is not None
    # "the same quarter a year earlier" names a year; "the quarter before" does not.
    quarter = _QUARTER_ANSWER.search(words) is not None and not year
    if year:
        return "year_over_year"
    return "sequential" if quarter else None


def _company_named(
    pending: PendingClarification, text: str, index: CompanyNames | None
) -> str | None:
    """The one offered company an answer names: "COKE", "Coca-Cola Consolidated".

    An answer naming none of them, or more than one, is a new question.
    """
    if len(text.split()) > _MAX_ANSWER_WORDS:
        return None
    for ticker in pending.candidates:
        if text == ticker.casefold():
            return ticker
    if index is not None:
        named = {mention.query for mention in index.find(text, company_slot=True)}
        offered = [ticker for ticker in pending.candidates if ticker in named]
        if len(offered) == 1 and named <= set(pending.candidates):
            return offered[0]
    # "the consolidated one": words only one candidate's name holds.
    words = set(re.findall(r"[a-z0-9]+", text)) - _ANSWER_FILLER
    words -= set(re.findall(r"[a-z0-9]+", pending.subject.casefold()))
    if not words:
        return None
    labels = pending.labels or pending.candidates
    holding = [
        ticker
        for ticker, label in zip(pending.candidates, labels, strict=False)
        if words <= set(re.findall(r"[a-z0-9]+", label.casefold()))
    ]
    return holding[0] if len(holding) == 1 else None


def _metrics_named(candidates: tuple[str, ...], text: str) -> tuple[str, ...]:
    """The metrics an answer names: "net", "gross and net", or any catalog name."""
    resolved = resolve_metric_phrase(text)
    if resolved.kind == "unique":
        metrics = resolved.unique_metrics
        if len(metrics) == 1 and metrics[0] not in candidates:
            # "per share" names EPS on its own, but here it picks dividends per share.
            named = _candidate_named_by_word(candidates, text)
            if named is not None:
                return (named,)
        # Another catalog metric ("gross margin" when asked about profit) answers too.
        return metrics
    parts = [_candidate_named_by_word(candidates, part) for part in _ANSWER_PARTS.split(text)]
    if parts and all(parts):
        return tuple(dict.fromkeys(name for name in parts if name is not None))
    return ()


def pending_from_clarify(
    result: TurnResult, patch: SpecPatch, question: str = ""
) -> PendingClarification | None:
    """The held analysis behind a CLARIFY answer; None for any other answer."""
    if result.renderer is not RendererKind.CLARIFY or not result.candidates:
        return None
    if result.clarify_kind is None:
        raise ValueError("clarify result is missing clarify_kind")
    metric_role: Literal["add", "remove"] = "remove" if is_removal(question) else "add"
    return PendingClarification(
        kind=result.clarify_kind,
        candidates=result.candidates,
        patch=patch,
        intent=result.intent,
        metric_role=metric_role,
        question=question,
        subject=result.clarify_subject or "",
        labels=result.candidate_labels,
    )


def resumed_request(
    pending: PendingClarification,
    chosen: tuple[str, ...],
    message: str,
    current_spec: AnalysisSpec | None,
) -> StructuredRequest:
    """The held analysis with the analyst's choice filled in, ready to resolve again."""
    return CLARIFY_KINDS[pending.kind].resume(pending, chosen, message, current_spec)


def _resume_metric(
    pending: PendingClarification,
    chosen: tuple[str, ...],
    message: str,
    current_spec: AnalysisSpec | None,
) -> StructuredRequest:
    wording = message
    if resolve_metric_phrase(message).metrics != chosen:
        # The turn reads its wording too: "2" or "net" names no one metric, the choice does.
        wording = " and ".join(name.replace("_", " ") for name in chosen)
    if pending.metric_role == "remove":
        patch = pending.patch.model_copy(update={"remove_metrics": chosen, "add_metrics": ()})
    else:
        patch = pending.patch.model_copy(update={"add_metrics": chosen})
        if patch.add_companies and not _ADD_WORDS.match(pending.question.strip()):
            # "Apple margin" after Microsoft revenue is a question of its own:
            # the chosen margin replaces revenue rather than joining it.
            patch = patch.model_copy(update={"mode": "replace", "remove_companies": ()})
    if patch.mode is None and current_spec is None:
        patch = patch.model_copy(update={"mode": "replace"})
    return StructuredRequest(patch=patch, wording=wording, question=pending.question or message)


def _resume_comparison(
    pending: PendingClarification,
    chosen: tuple[str, ...],
    message: str,
    current_spec: AnalysisSpec | None,
) -> StructuredRequest:
    # The held question again, its changes measured as chosen.
    return StructuredRequest(
        patch=pending.patch,
        wording=pending.question or message,
        question=pending.question or message,
        comparison="year_over_year" if chosen[0] == "year_over_year" else "sequential",
    )


def _resume_company(
    pending: PendingClarification,
    chosen: tuple[str, ...],
    message: str,
    current_spec: AnalysisSpec | None,
) -> StructuredRequest:
    # The held question again, with the chosen company for the ambiguous name.
    answer = chosen[0]
    companies = pending.patch.add_companies
    if pending.subject in companies:
        companies = tuple(answer if name == pending.subject else name for name in companies)
    else:
        companies = (*companies, answer)
    patch = pending.patch.model_copy(update={"add_companies": companies})
    return StructuredRequest(
        patch=patch,
        wording=pending.question or message,
        question=pending.question or message,
        company_choice=(pending.subject, answer),
    )


def _resume_scope(
    pending: PendingClarification,
    chosen: tuple[str, ...],
    message: str,
    current_spec: AnalysisSpec | None,
) -> StructuredRequest:
    # The held question is what the chosen scope answers.
    mode: Literal["extend", "replace"] = "extend" if chosen[0] == "extend" else "replace"
    patch = pending.patch.model_copy(update={"mode": mode})
    question = pending.question or message
    return StructuredRequest(patch=patch, wording=question, question=question)


def ask_again(
    pending: PendingClarification,
    reply: ClarifyReply,
    message: str,
    current_spec: AnalysisSpec | None,
) -> Clarification:
    """Keep the open question: a period noted for it, or an option out of range."""
    if reply.period_patch is not None:
        patch = bind_periods_from_message(pending.patch, message)
        note = f"Noted “{message.strip()}”. Pick a metric to see it for that period."
    else:
        patch = pending.patch
        count = len(pending.candidates)
        hint = CLARIFY_KINDS[pending.kind].hint
        note = f"There are {count} options: pick 1 to {count}, {hint}."
    result = TurnResult(
        intent=pending.intent,
        tool_traces=[],
        renderer=RendererKind.CLARIFY,
        candidates=pending.candidates,
        clarify_kind=pending.kind,
        candidate_labels=pending.labels,
        clarify_subject=pending.subject or None,
        banners=[note],
    )
    return Clarification(
        pending=pending.model_copy(update={"patch": patch}),
        result=result,
        analysis_spec=current_spec,
    )


@dataclass(frozen=True)
class ClarifyKindRules:
    """What one kind of clarification asks, and how its answer is read and used."""

    # The question the window shows; a company's names the ambiguous ``{subject}``.
    prompt: str
    # Said beside "pick 1 to N" when an answer is out of range.
    hint: str
    read: Callable[[_Answer], ClarifyReply | None]
    resume: Callable[
        [PendingClarification, tuple[str, ...], str, AnalysisSpec | None], StructuredRequest
    ]


# Every kind of clarification, in one place: a new kind is one entry here.
CLARIFY_KINDS: dict[ClarifyKind, ClarifyKindRules] = {
    "ambiguous_metric": ClarifyKindRules(
        prompt="Which metric do you mean?",
        hint="or type the metric's name",
        read=_read_metric,
        resume=_resume_metric,
    ),
    "ambiguous_mode": ClarifyKindRules(
        prompt="Add to the current analysis, or start a new one?",
        hint="or type “extend” or “replace”",
        read=_read_scope,
        resume=_resume_scope,
    ),
    "ambiguous_company": ClarifyKindRules(
        prompt="Which company do you mean by “{subject}”?",
        hint="or type the company's ticker",
        read=_read_company,
        resume=_resume_company,
    ),
    "ambiguous_comparison": ClarifyKindRules(
        prompt="Compared with what?",
        hint="or say “year over year” or “the quarter before”",
        read=_read_comparison,
        resume=_resume_comparison,
    ),
}


def clarify_prompt(kind: ClarifyKind | None, subject: str | None = None) -> str:
    """The question a clarification asks; a result saved without a kind asks for a metric."""
    rules = CLARIFY_KINDS[kind or "ambiguous_metric"]
    return rules.prompt.format(subject=subject or "that name")
