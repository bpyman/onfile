"""Bounded, ordered fan-out of independent provider calls (ADR 0005)."""

from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from contextvars import copy_context

from financial_analyst_agent.domain.errors import SessionQuotaError

# Bound concurrent provider fan-out so a wide window cannot flood SEC/EDGAR.
DEFAULT_TASK_MAX_WORKERS = 8


def map_in_order[T, R](
    fn: Callable[[T], R],
    items: Sequence[T],
    *,
    max_workers: int = DEFAULT_TASK_MAX_WORKERS,
) -> list[R]:
    """``[fn(item) for item in items]``, with up to ``max_workers`` calls at once.

    Each call runs in its own copy of the caller's context, so it shares the
    turn's SEC deadline. Results keep ``items`` order. An error escaping a call
    (a ``SessionQuotaError``, say) is raised here, the earliest item's first,
    and calls not yet started are cancelled. SEC's request rate is held by the
    client's shared limiter, not by this pool.
    """
    if len(items) <= 1 or max_workers <= 1:
        return [fn(item) for item in items]
    pool = ThreadPoolExecutor(max_workers=min(max_workers, len(items)))
    try:
        futures = [pool.submit(copy_context().run, fn, item) for item in items]
        results = [future.result() for future in futures]
    except BaseException:
        pool.shutdown(wait=False, cancel_futures=True)
        raise
    pool.shutdown(wait=True)
    return results


def or_none[T](read: Callable[[], T]) -> T | None:
    """``read()``, or None when it fails.

    One company's failure must not refuse the whole window for the companies
    that do resolve: its cells report it. A spent session budget still stops
    the turn.
    """
    try:
        return read()
    except SessionQuotaError:
        raise
    except Exception:
        return None
