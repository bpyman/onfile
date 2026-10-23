"""A daily ceiling on what the live runtime spends on OpenAI.

The public demo answers anyone, and nothing in OpenAI's API stops a busy day from
spending without limit. Each planner and essay request is priced from the tokens
its response reports and added to the day's total (UTC). Once the total reaches
the ceiling, requests stop until the next day: the planner falls back to the rules
plan, and a written answer says why it is missing. Figures never need the model.

The check comes before a request and the charge after it, so turns already in
flight can carry the day a little past the ceiling (at most one request each).
"""

from __future__ import annotations

import json
import os
import threading
from collections.abc import Callable
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from financial_analyst_agent.domain.errors import ProviderError
from financial_analyst_agent.observability import log_event

# US dollars per million input and output tokens.
MODEL_PRICES: dict[str, tuple[float, float]] = {
    "gpt-5.6-terra": (2.0, 12.0),
    "gpt-6.1-sol": (2.0, 10.0),
}
_MILLION = Decimal(1_000_000)

SPEND_CAP_MESSAGE = (
    "Written answers are paused for today: the demo's daily budget for the language "
    "model is used up. Figures from filings still work, and written answers return "
    "tomorrow (UTC)."
)


class SpendCapReached(ProviderError):
    """The day's OpenAI budget is spent; raised before a request is sent."""

    code = "model_budget_spent"
    public = True


def request_cost(model: str, response: Any) -> Decimal:
    """What a response cost, from the usage it reports.

    A model without a listed price is charged at the dearest listed one, so an
    unpriced model cannot spend past the ceiling unnoticed.
    """
    usage = getattr(response, "usage", None)
    if usage is None:
        return Decimal(0)
    # The Responses API reports input/output tokens; Chat Completions, prompt/completion.
    input_tokens = getattr(usage, "input_tokens", None) or getattr(usage, "prompt_tokens", 0)
    output_tokens = getattr(usage, "output_tokens", None) or getattr(
        usage, "completion_tokens", 0
    )
    price_in, price_out = MODEL_PRICES.get(
        model, max(MODEL_PRICES.values(), key=lambda prices: prices[1])
    )
    return (
        Decimal(int(input_tokens or 0)) * Decimal(str(price_in))
        + Decimal(int(output_tokens or 0)) * Decimal(str(price_out))
    ) / _MILLION


def _utc_today() -> date:
    return datetime.now(UTC).date()


class DailySpendCap:
    """The day's OpenAI spend against ``limit_usd``; a limit of 0 means no ceiling.

    With a ``path``, the day's total is kept in that file, so a restart does not
    reset it.
    """

    def __init__(
        self,
        limit_usd: Decimal,
        path: Path | None = None,
        *,
        today: Callable[[], date] = _utc_today,
    ) -> None:
        self._limit = limit_usd
        self._path = path
        self._today = today
        self._lock = threading.Lock()
        self._day, self._spent = self._load()

    @property
    def spent_today(self) -> Decimal:
        with self._lock:
            self._roll_over()
            return self._spent

    def call[T](self, model: str, request: Callable[[], T]) -> T:
        """Send ``request`` if today's budget allows, and charge what it cost."""
        with self._lock:
            self._roll_over()
            if self._limit > 0 and self._spent >= self._limit:
                log_event("model_budget_spent", spent_usd=str(self._spent))
                raise SpendCapReached(SPEND_CAP_MESSAGE)
        response = request()
        cost = request_cost(model, response)
        if cost:
            with self._lock:
                self._roll_over()
                self._spent += cost
                self._save()
        return response

    def _roll_over(self) -> None:
        today = self._today()
        if today != self._day:
            self._day, self._spent = today, Decimal(0)

    def _load(self) -> tuple[date, Decimal]:
        today = self._today()
        if self._path is None or not self._path.exists():
            return today, Decimal(0)
        try:
            saved = json.loads(self._path.read_text(encoding="utf-8"))
            day = date.fromisoformat(saved["day"])
            spent = Decimal(saved["spent_usd"])
        except (OSError, ValueError, KeyError, TypeError, ArithmeticError):
            return today, Decimal(0)
        return (day, spent) if day == today else (today, Decimal(0))

    def _save(self) -> None:
        if self._path is None:
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        partial = self._path.with_suffix(".tmp")
        partial.write_text(
            json.dumps({"day": self._day.isoformat(), "spent_usd": str(self._spent)}),
            encoding="utf-8",
        )
        os.replace(partial, self._path)
