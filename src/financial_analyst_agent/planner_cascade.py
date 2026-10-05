"""The rules planner first, and the LLM planner only where the rules planner is unsure.

Both planners propose a plan that the same code then resolves (ADR 0010, 0011),
so a cascade only chooses which proposal a turn uses. The rules planner is free
and answers in about a millisecond; the LLM planner costs a call and a second.
The rules planner's plan is kept unless it shows the planner was unsure: it
names something the code cannot resolve, or says it guessed. Then the LLM
planner plans the turn, and if that call fails the rules plan stands.
"""

from collections.abc import Callable
from typing import Any

from financial_analyst_agent.contracts import Completer, Intent, WorkflowPlan
from financial_analyst_agent.domain.errors import PlannerError
from financial_analyst_agent.graph.analysis_spec import SpecPatch
from financial_analyst_agent.services.metric_catalog import METRIC_DISPLAY

# Questions about figures: a plan for one needs a catalog metric.
_FIGURE_INTENTS = frozenset({Intent.LOOKUP, Intent.COMPARE, Intent.RANK_AND_LOOKUP})
_RANK_INTENTS = frozenset({Intent.RANK, Intent.RANK_AND_LOOKUP})


def unsure_reason(
    plan: WorkflowPlan | SpecPatch,
    knows_industry: Callable[[str], bool],
    *,
    follow_up: bool = False,
) -> str | None:
    """Why the rules planner's ``plan`` should go to the LLM planner, or None to keep it.

    A follow-up that names no company and no metric ("make it the last eight
    quarters", "show that year over year") is an edit of the analysis on
    screen, which the shared reading of its words applies (ADR 0010): the rules
    plan is kept. Otherwise:

    - ``notes``: it corrected a name, read a word as a company, or left part of
      the question unanswered.
    - ``metric``: a figures question with no catalog metric ("profit", "churn").
    - ``company``: a lookup or comparison that names no company.
    - ``industry``: a ranking of a group the snapshot does not know.
    - ``edit``: an edit it cannot place as adding or replacing companies.
    """
    if isinstance(plan, SpecPatch):
        moves_companies = bool(plan.add_companies or plan.remove_companies)
        return "edit" if plan.mode is None and moves_companies else None
    if plan.notes:
        return "notes"
    named = plan.company or plan.companies
    if follow_up and not named and plan.metric in (None, "unknown"):
        return None
    if plan.intent in _FIGURE_INTENTS and plan.metric not in (*METRIC_DISPLAY, "overview"):
        return "metric"
    if plan.intent in (Intent.LOOKUP, Intent.COMPARE) and not named:
        return "company"
    if plan.intent in _RANK_INTENTS and not knows_industry(plan.industry or ""):
        return "industry"
    return None


class CascadeCompleter:
    """Plans with ``rules``, and with ``llm`` when ``unsure_reason`` gives a reason.

    ``last_reason`` is why the latest turn went to the LLM planner (None when the
    rules plan was kept), for an evaluation to count. Anything else, such as
    the rules planner's issuer index, is the rules planner's.
    """

    def __init__(
        self, rules: Completer, llm: Completer, knows_industry: Callable[[str], bool]
    ) -> None:
        self._rules = rules
        self._llm = llm
        self._knows_industry = knows_industry
        self.last_reason: str | None = None

    def complete(self, query: str, current_spec: Any = None) -> WorkflowPlan | SpecPatch:
        plan = self._rules.complete(query, current_spec=current_spec)
        self.last_reason = unsure_reason(
            plan, self._knows_industry, follow_up=current_spec is not None
        )
        if self.last_reason is None:
            return plan
        try:
            return self._llm.complete(query, current_spec=current_spec)
        except PlannerError:
            return plan

    def __getattr__(self, name: str) -> Any:
        return getattr(self._rules, name)
