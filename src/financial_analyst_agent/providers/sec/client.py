"""Synchronous SEC EDGAR HTTP client."""

import json
import re
import threading
import time
import zlib
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import date
from email.utils import parsedate_to_datetime
from typing import Any, TypeVar

import httpx

from financial_analyst_agent.config import Settings
from financial_analyst_agent.domain.enums import PERIODIC_FORMS
from financial_analyst_agent.domain.errors import ProviderError, SessionQuotaError
from financial_analyst_agent.observability import call_provider, log_event
from financial_analyst_agent.providers.sec.company_facts import validate_companyfacts_response
from financial_analyst_agent.providers.sec.submissions import validate_submissions_response
from financial_analyst_agent.providers.sec.tickers import require_usable_company_tickers

_COMPANY_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
# SEC's latest filings of one form (and its amendments), newest first, as Atom.
_LATEST_FILINGS_URL = (
    "https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&type={form}"
    "&company=&dateb=&owner=include&start={start}&count={count}&output=atom"
)
# SEC's "recent" filings hold the last year or 1,000 filings, whichever is more.
# A bank filing thousands of prospectuses a year has only a year of 10-Qs there;
# older ones sit in numbered pages. Read pages until this much history is in hand.
_HISTORY_DAYS = 3 * 365 + 30
_MAX_OLDER_PAGES = 4
_PAGE_NAME = re.compile(r"CIK\d{10}-submissions-\d{3}\.json")
_MAX_RETRIES = 3
_DEFAULT_RETRY_DELAY_SECONDS = 1.0
_MAX_RETRY_DELAY_SECONDS = 5.0
# A longer Retry-After pauses every request in the process instead of being slept.
_MAX_RETRY_AFTER_SECONDS = 600.0
# Inflated a piece at a time, so a compressed bomb stops at the size cap.
_INFLATE_PIECE_BYTES = 1024 * 1024
# A real 10-Q runs to hundreds of kilobytes; less is an error page or an empty reply.
MIN_FILING_DOCUMENT_CHARS = 10_000
# SEC's page for a client it has flagged; it asks for about ten minutes of quiet.
_BLOCKED_MARKERS = (b"Undeclared Automated Tool", b"Request Rate Threshold Exceeded")

T = TypeVar("T")

# When the current turn's SEC time runs out (monotonic); unset outside a turn.
# The task pool copies the context, so a turn's workers share its deadline.
_TURN_DEADLINE: ContextVar[float | None] = ContextVar("sec_turn_deadline", default=None)


@contextmanager
def sec_turn_budget(seconds: float) -> Iterator[None]:
    """Allow the SEC requests made in this context ``seconds`` in all, then refuse them."""
    token = _TURN_DEADLINE.set(time.monotonic() + seconds)
    try:
        yield
    finally:
        _TURN_DEADLINE.reset(token)


def sec_turn_seconds_left() -> float:
    """The SEC time this turn has left; infinite outside a turn's budget."""
    deadline = _TURN_DEADLINE.get()
    return float("inf") if deadline is None else deadline - time.monotonic()


class _Pause:
    """Process-wide "SEC paused until T", from a Retry-After or SEC's block page."""

    def __init__(self) -> None:
        self._until = 0.0
        self._lock = threading.Lock()

    def extend(self, seconds: float) -> None:
        with self._lock:
            self._until = max(self._until, time.monotonic() + seconds)

    def remaining(self) -> float:
        with self._lock:
            return max(0.0, self._until - time.monotonic())

    def clear(self) -> None:
        with self._lock:
            self._until = 0.0


SEC_PAUSE = _Pause()


class _RateLimiter:
    """Space requests at least ``min_interval`` apart across threads.

    Each caller reserves the next free slot under the lock, then sleeps outside
    it, so concurrent workers queue instead of all reading the same timestamp.
    """

    def __init__(self, min_interval: float) -> None:
        self._min_interval = min_interval
        self._lock = threading.Lock()
        self._next_slot = 0.0

    def idle(self) -> bool:
        """Whether no request is queued for a slot."""
        with self._lock:
            return time.monotonic() >= self._next_slot

    def acquire(self) -> None:
        with self._lock:
            now = time.monotonic()
            slot = max(now, self._next_slot)
            self._next_slot = slot + self._min_interval
        wait = slot - now
        if wait > 0:
            time.sleep(wait)


# EDGAR's fair-access limit is per host, so every client in the process shares one
# limiter per rate: a new client per turn must not reset the budget.
_SHARED_LIMITERS: dict[float, _RateLimiter] = {}
_SHARED_LIMITERS_LOCK = threading.Lock()


def _shared_limiter(min_interval: float) -> _RateLimiter:
    with _SHARED_LIMITERS_LOCK:
        limiter = _SHARED_LIMITERS.get(min_interval)
        if limiter is None:
            limiter = _RateLimiter(min_interval)
            _SHARED_LIMITERS[min_interval] = limiter
        return limiter


def usable_filing_document(text: str) -> bool:
    """Whether ``text`` can be a filing's HTML rather than an empty reply or an error page."""
    if len(text) < MIN_FILING_DOCUMENT_CHARS or "<html" not in text[:65536].lower():
        return False
    head = text[:4096].encode("utf-8", "replace")
    return not any(marker in head for marker in _BLOCKED_MARKERS)


def looks_like_json_object(body: bytes) -> bool:
    """A cheap check, before caching, that ``body`` is one whole JSON object."""
    stripped = body.strip()
    return stripped[:1] == b"{" and stripped[-1:] == b"}"


def _retry_after_seconds(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        pass
    try:
        when = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    return max(0.0, when.timestamp() - time.time())


class _Inflater:
    """Undo a gzip or deflate Content-Encoding a bounded piece at a time."""

    def __init__(self, encoding: str, url: str) -> None:
        coding = encoding.strip().lower()
        self._url = url
        self._zlib: Any = None
        if coding in ("gzip", "x-gzip", "deflate"):
            # 32 + MAX_WBITS reads either a gzip or a zlib header.
            self._zlib = zlib.decompressobj(32 + zlib.MAX_WBITS)
        elif coding not in ("", "identity"):
            raise ProviderError(
                "SEC response used an unsupported encoding",
                details={"url": url, "retryable": False},
            )

    def feed(self, data: bytes) -> Iterator[bytes]:
        if self._zlib is None:
            yield data
            return
        try:
            yield self._zlib.decompress(data, _INFLATE_PIECE_BYTES)
            while self._zlib.unconsumed_tail:
                yield self._zlib.decompress(self._zlib.unconsumed_tail, _INFLATE_PIECE_BYTES)
        except zlib.error as exc:
            raise ProviderError(
                "SEC response could not be decompressed",
                details={"url": self._url, "retryable": False},
            ) from exc


class SECClient:
    """HTTP client for SEC EDGAR JSON APIs with rate limiting and retry.

    Every request is bounded three ways: a per-read timeout, a wall-clock
    deadline for the whole response, and a cap on its decompressed size. A turn
    bounds its SEC time in all with ``sec_turn_budget``.
    """

    def __init__(self, settings: Settings, client: httpx.Client | None = None) -> None:
        self._settings = settings
        self._user_agent = settings.require_user_agent()
        self._timeout = settings.sec_timeout_seconds
        self._request_deadline = settings.sec_request_deadline_seconds
        self._max_bytes = settings.sec_max_response_bytes
        self._block_pause = settings.sec_block_pause_seconds
        self._owns_client = client is None
        self._client = client
        self._limiter = _shared_limiter(1.0 / settings.sec_max_requests_per_second)
        self._closed = False
        self._client_lock = threading.Lock()

    def idle(self) -> bool:
        """Whether SEC is neither paused nor busy with queued requests: background work may go."""
        return SEC_PAUSE.remaining() == 0 and self._limiter.idle()

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._owns_client and self._client is not None:
            self._client.close()
            self._client = None

    def _http(self) -> httpx.Client:
        with self._client_lock:
            if self._client is None:
                self._client = httpx.Client(timeout=self._timeout)
            return self._client

    def _acquire(self, url: str) -> None:
        """Take a request slot, unless SEC asked for quiet or the turn's time is up."""
        paused = SEC_PAUSE.remaining()
        if paused > 0:
            if paused > _MAX_RETRY_DELAY_SECONDS or paused >= sec_turn_seconds_left():
                raise ProviderError(
                    "SEC asked for a pause in requests",
                    details={"url": url, "retryable": False, "paused_seconds": round(paused)},
                )
            time.sleep(paused)
        if sec_turn_seconds_left() <= 0:
            raise ProviderError(
                "The turn's time for SEC requests is spent",
                details={"url": url, "retryable": False},
            )
        self._limiter.acquire()

    def _with_retries(self, url: str, once: Callable[[], T]) -> T:
        def _run() -> T:
            attempt = 0
            while True:
                self._acquire(url)
                try:
                    return once()
                except ProviderError as exc:
                    attempt += 1
                    if not exc.details.get("retryable") or attempt >= _MAX_RETRIES:
                        raise
                    delay = min(_DEFAULT_RETRY_DELAY_SECONDS * attempt, _MAX_RETRY_DELAY_SECONDS)
                    if delay >= sec_turn_seconds_left():
                        raise
                    time.sleep(delay)

        return call_provider("sec", _run, url=url)

    def _get(self, url: str, accept: str) -> tuple[bytes, str]:
        """The response body, decompressed, and its content type."""
        headers = {
            "User-Agent": self._user_agent,
            "Accept-Encoding": "gzip, deflate",
            "Accept": accept,
        }
        started = time.monotonic()
        deadline = started + min(self._request_deadline, sec_turn_seconds_left())
        timeout = httpx.Timeout(max(0.001, min(self._timeout, deadline - started)))
        try:
            with self._http().stream("GET", url, headers=headers, timeout=timeout) as response:
                if not 200 <= response.status_code <= 299:
                    self._raise_for_status(url, response)
                body = self._read_body(url, response, deadline)
                return body, response.headers.get("content-type", "")
        except httpx.TimeoutException as exc:
            # A hung SEC does not answer a second ask either, so no retry.
            raise ProviderError(
                "SEC request timed out",
                details={"url": url, "retryable": False},
            ) from exc
        except httpx.HTTPError as exc:
            raise ProviderError(
                "SEC request failed",
                details={"url": url, "retryable": True},
            ) from exc

    def _read_body(self, url: str, response: httpx.Response, deadline: float) -> bytes:
        declared = response.headers.get("content-length", "")
        if declared.isdigit() and int(declared) > self._max_bytes:
            raise ProviderError(
                "SEC response was too large", details={"url": url, "retryable": False}
            )
        if response.is_stream_consumed:
            # An in-memory response (a mock transport) arrives read and decoded.
            if len(response.content) > self._max_bytes:
                raise ProviderError(
                    "SEC response was too large", details={"url": url, "retryable": False}
                )
            return response.content
        inflater = _Inflater(response.headers.get("content-encoding", ""), url)
        chunks: list[bytes] = []
        size = 0
        for raw in response.iter_raw():
            # A per-read timeout never fires on a server that drips bytes.
            if time.monotonic() > deadline:
                raise ProviderError(
                    "SEC response took too long", details={"url": url, "retryable": False}
                )
            for piece in inflater.feed(raw):
                size += len(piece)
                if size > self._max_bytes:
                    raise ProviderError(
                        "SEC response was too large", details={"url": url, "retryable": False}
                    )
                chunks.append(piece)
        return b"".join(chunks)

    def _raise_for_status(self, url: str, response: httpx.Response) -> None:
        status = response.status_code
        if status in (429, 503):
            wait = _retry_after_seconds(response.headers.get("retry-after"))
            if wait is not None:
                SEC_PAUSE.extend(min(wait, _MAX_RETRY_AFTER_SECONDS))
                if wait > _MAX_RETRY_DELAY_SECONDS:
                    log_event("sec_paused", status_code=status, seconds=round(wait))
                    raise ProviderError(
                        "SEC asked for a pause in requests",
                        details={"url": url, "status_code": status, "retryable": False},
                    )
        if status == 403 and _blocked_page(response):
            SEC_PAUSE.extend(self._block_pause)
            log_event("sec_blocked", seconds=round(self._block_pause))
            raise ProviderError(
                "SEC refused this client's automated requests",
                details={"url": url, "status_code": status, "retryable": False},
            )
        if status == 429 or 500 <= status <= 599:
            raise ProviderError(
                "SEC rate limit exceeded" if status == 429 else "SEC server error",
                details={"url": url, "status_code": status, "retryable": True},
            )
        if 400 <= status <= 499:
            raise ProviderError(
                "SEC client error",
                details={"url": url, "status_code": status, "retryable": False},
            )
        raise ProviderError(
            "Unexpected SEC response status",
            details={"url": url, "status_code": status, "retryable": False},
        )

    def _fetch_json(self, url: str) -> object:
        def once() -> object:
            body, _content_type = self._get(url, "application/json")
            return _decode_json(url, body)

        return self._with_retries(url, once)

    def _fetch_json_document(self, url: str) -> bytes:
        def once() -> bytes:
            body, _content_type = self._get(url, "application/json")
            if not looks_like_json_object(body):
                raise ProviderError(
                    "SEC response was not a JSON object",
                    details={"url": url, "retryable": False},
                )
            return body

        return self._with_retries(url, once)

    def _fetch_body(self, url: str) -> str:
        def once() -> str:
            body, content_type = self._get(url, "text/html,application/xhtml+xml")
            text = body.decode(_charset(content_type), errors="replace")
            if not usable_filing_document(text):
                raise ProviderError(
                    "SEC returned no usable filing document",
                    details={"url": url, "retryable": True},
                )
            return text

        return self._with_retries(url, once)

    def get_latest_filings(self, form: str, start: int = 0, count: int = 100) -> str:
        """One page of SEC's latest filings of ``form`` and its amendments, as Atom XML."""
        url = _LATEST_FILINGS_URL.format(form=form, start=start, count=count)

        def once() -> str:
            body, content_type = self._get(url, "application/atom+xml")
            text = body.decode(_charset(content_type), errors="replace")
            if "<feed" not in text[:4096]:
                raise ProviderError(
                    "SEC returned no latest-filings feed",
                    details={"url": url, "retryable": True},
                )
            return text

        return self._with_retries(url, once)

    def get_filing_document(self, cik: str, accession: str, document: str) -> str:
        from financial_analyst_agent.providers.sec.urls import build_filing_document_url

        return self._fetch_body(build_filing_document_url(cik, accession, document))

    def get_company_tickers(self) -> dict[str, Any]:
        return require_usable_company_tickers(self._fetch_json(_COMPANY_TICKERS_URL))

    def get_submissions(self, cik: str, *, with_history: bool = True) -> dict[str, Any]:
        """A filer's submissions; ``with_history`` also reads older pages (see below)."""
        url = f"{self._settings.sec_base_url}/submissions/CIK{cik}.json"
        payload = self._fetch_json(url)
        if not isinstance(payload, dict):
            raise ProviderError(
                "SEC response JSON must be an object",
                details={"url": url, "retryable": False},
            )
        valid = validate_submissions_response(payload, cik, details={"url": url, "cik": cik})
        return with_older_pages(valid, self.get_submissions_page) if with_history else valid

    def get_submissions_page(self, name: str) -> dict[str, Any]:
        """One older submissions page, named by the filer's ``filings.files``."""
        if not _PAGE_NAME.fullmatch(name):
            raise ProviderError(
                "Not an SEC submissions page name", details={"page": name, "retryable": False}
            )
        url = f"{self._settings.sec_base_url}/submissions/{name}"
        older = self._fetch_json(url)
        if not isinstance(older, dict) or not isinstance(older.get("form"), list):
            raise ProviderError(
                "SEC submissions page must list forms", details={"url": url, "retryable": False}
            )
        return older

    def get_company_facts(self, cik: str) -> dict[str, Any]:
        return parse_company_facts_document(cik, self.get_company_facts_document(cik))

    def get_company_facts_document(self, cik: str) -> bytes:
        """Company facts as SEC sent them, unparsed, for a cache to keep.

        A bank's file parses to about 40 MB, so the parse waits for a parse slot
        (``SecFactLookup``) while the download does not.
        """
        url = f"{self._settings.sec_base_url}/api/xbrl/companyfacts/CIK{cik}.json"
        return self._fetch_json_document(url)


def parse_company_facts_document(cik: str, document: bytes) -> dict[str, Any]:
    """Decode and validate a company facts file, fetched or cached alike."""
    details = {"cik": cik}
    return validate_companyfacts_response(_decode_json(cik, document), cik, details=details)


def _decode_json(url: str, body: bytes) -> object:
    try:
        decoded: object = json.loads(body)
    except ValueError as exc:
        raise ProviderError(
            "SEC response was not valid JSON",
            details={"url": url, "retryable": False},
        ) from exc
    return decoded


def _blocked_page(response: httpx.Response) -> bool:
    """Whether a 403 is SEC's "undeclared automated tool" page, read only so far."""
    if response.is_stream_consumed:
        return any(marker in response.content[:65536] for marker in _BLOCKED_MARKERS)
    head = b""
    try:
        for raw in response.iter_raw():
            head += raw
            if len(head) >= 65536:
                break
        if response.headers.get("content-encoding", "").strip().lower() in ("gzip", "deflate"):
            head = zlib.decompressobj(32 + zlib.MAX_WBITS).decompress(head, 65536)
    except (httpx.HTTPError, zlib.error):
        return False
    return any(marker in head for marker in _BLOCKED_MARKERS)


def _charset(content_type: str) -> str:
    for part in content_type.split(";")[1:]:
        name, _, value = part.strip().partition("=")
        if name.strip().lower() != "charset":
            continue
        charset = value.strip().strip('"')
        try:
            "".encode(charset)
        except LookupError:
            break
        return charset
    return "utf-8"


def with_older_pages(
    payload: dict[str, Any], fetch_page: Callable[[str], object]
) -> dict[str, Any]:
    """Append older submission pages until ~3 years of 10-Qs and 10-Ks are covered.

    History is optional: a page that fails or is refused (the thread's SEC
    budget is spent) ends the reading, and the recent filings still answer.
    """
    filings = payload.get("filings")
    recent = filings.get("recent") if isinstance(filings, dict) else None
    pages = filings.get("files") if isinstance(filings, dict) else None
    if not isinstance(recent, dict) or not isinstance(pages, list):
        return payload
    for page in pages[:_MAX_OLDER_PAGES]:
        if _periodic_span_days(recent) >= _HISTORY_DAYS:
            break
        name = page.get("name") if isinstance(page, dict) else None
        if not isinstance(name, str) or not _PAGE_NAME.fullmatch(name):
            break
        try:
            older = fetch_page(name)
        except (ProviderError, SessionQuotaError):
            break
        if not isinstance(older, dict) or not isinstance(older.get("form"), list):
            break
        _append_page(recent, older)
    return payload

def _periodic_span_days(recent: dict[str, Any]) -> int:
    """Days between the newest and oldest 10-Q/10-K report dates in ``recent``."""
    dates: list[date] = []
    for form, raw in zip(recent.get("form", []), recent.get("reportDate", []), strict=False):
        if form in PERIODIC_FORMS and isinstance(raw, str):
            try:
                dates.append(date.fromisoformat(raw))
            except ValueError:
                continue
    return (max(dates) - min(dates)).days if dates else 0


def _append_page(recent: dict[str, Any], older: dict[str, Any]) -> None:
    """Extend every column of ``recent`` by an older page, keeping the columns equal."""
    count = len(older["form"])
    for key, values in recent.items():
        if not isinstance(values, list):
            continue
        extra = older.get(key)
        if isinstance(extra, list) and len(extra) == count:
            values.extend(extra)
        else:
            values.extend([""] * count)
