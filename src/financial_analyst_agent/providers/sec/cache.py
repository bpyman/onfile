"""Disk cache in front of a live SEC data source."""

from __future__ import annotations

import gzip
import json
import os
import re
import stat
import tempfile
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from pathlib import Path
from threading import Lock
from typing import Any

from financial_analyst_agent.domain.errors import DataIntegrityError, ProviderError
from financial_analyst_agent.observability import log_event
from financial_analyst_agent.providers.sec.client import (
    looks_like_json_object,
    usable_filing_document,
    with_older_pages,
)
from financial_analyst_agent.providers.sec.company_facts import validate_companyfacts_response
from financial_analyst_agent.providers.sec.filing_watch import FilingWatch
from financial_analyst_agent.session import SessionBudget

_JSON_FRESH_SECONDS = 3600
# A company's files: its facts and their digest, its no-facts marker, its submissions
# and their older pages.
_COMPANY_FILE = re.compile(r"(?:facts|submissions|digest)-(?:CIK)?(\d{10})")
# A temp file this old belongs to no write in progress: its writer died.
_STALE_TEMP_SECONDS = 3600
_SWEEP_INTERVAL_SECONDS = 600
# A sweep trims to this share of the budget, so the next write does not start another.
_SWEEP_TARGET = 0.9

_FILL_LOCKS: dict[str, Lock] = {}
_FILL_LOCKS_GUARD = Lock()
_LAST_SWEEP: dict[str, float] = {}
_LAST_SWEEP_GUARD = Lock()


def _lock_for(path: Path) -> Lock:
    key = str(path.resolve())
    with _FILL_LOCKS_GUARD:
        lock = _FILL_LOCKS.get(key)
        if lock is None:
            lock = Lock()
            _FILL_LOCKS[key] = lock
        return lock


_UNREADABLE = object()


def _read_json(path: Path) -> object:
    """A cached object, or ``_UNREADABLE`` when the file is damaged and must be refetched."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError):
        return _UNREADABLE
    # Every SEC document cached here is an object; anything else is damage.
    return payload if isinstance(payload, dict) else _UNREADABLE


def _read_document(path: Path) -> str | None:
    """A cached filing document, or ``None`` when absent, unreadable, or not a filing."""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    return text if usable_filing_document(text) else None


def _unlink_quietly(path: Path) -> None:
    with suppress(OSError):
        path.unlink(missing_ok=True)


def _write_atomic(path: Path, data: bytes) -> bool:
    """Write the whole file or nothing; a full or read-only disk only costs the cache."""
    try:
        handle, temp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    except OSError as exc:
        log_event("sec_cache_write_failed", file=path.name, error=type(exc).__name__)
        return False
    try:
        with os.fdopen(handle, "wb") as out:
            out.write(data)
        os.replace(temp, path)
    except OSError as exc:
        _unlink_quietly(Path(temp))
        log_event("sec_cache_write_failed", file=path.name, error=type(exc).__name__)
        return False
    return True


def sweep_cache(directory: Path, max_bytes: int, *, now: float | None = None) -> int:
    """Delete the oldest cached files until ``directory`` fits ``max_bytes``.

    Temp files a dead writer left behind go too. Returns how many files were removed.
    """
    clock = time.time() if now is None else now
    kept: list[tuple[float, int, Path]] = []
    removed = 0
    try:
        paths = list(directory.iterdir())
    except OSError:
        return 0
    for path in paths:
        try:
            info = path.stat()
        except OSError:
            continue
        if not stat.S_ISREG(info.st_mode):
            continue
        if path.name.endswith(".tmp"):
            if clock - info.st_mtime > _STALE_TEMP_SECONDS:
                _unlink_quietly(path)
                removed += 1
            continue
        kept.append((info.st_mtime, info.st_size, path))
    total = sum(size for _mtime, size, _path in kept)
    if total <= max_bytes:
        return removed
    for _mtime, size, path in sorted(kept):
        if total <= max_bytes * _SWEEP_TARGET:
            break
        _unlink_quietly(path)
        total -= size
        removed += 1
    log_event("sec_cache_swept", removed=removed, bytes_kept=total)
    return removed


def _sweep_soon(directory: Path, max_bytes: int) -> None:
    """Start a sweep beside the request at most once per interval per directory."""
    key = str(directory)
    now = time.monotonic()
    with _LAST_SWEEP_GUARD:
        last = _LAST_SWEEP.get(key)
        if last is not None and now - last < _SWEEP_INTERVAL_SECONDS:
            return
        _LAST_SWEEP[key] = now
    threading.Thread(
        target=sweep_cache, args=(directory, max_bytes), name="sec-cache-sweep", daemon=True
    ).start()


class CachingSECDataSource:
    """Cache SEC JSON for one hour and accession-pinned HTML indefinitely.

    With a filing ``watch``, a company's files (its facts and submissions) last
    until it files again instead, up to a week (ADR 0013); the watch says how long.

    Nothing is cached that is not a whole document: JSON must be an object and
    a filing must look like one. Writes are best effort, a fill waits at most
    ``fill_wait_seconds`` for another request fetching the same file, and the
    directory is kept under ``max_bytes`` when that is given.
    """

    def __init__(
        self,
        inner: Any,
        cache_dir: Path,
        *,
        budget: SessionBudget | None = None,
        fill_wait_seconds: float = 30.0,
        max_bytes: int | None = None,
        watch: FilingWatch | None = None,
    ) -> None:
        self._inner = inner
        self._watch = watch
        self._dir = cache_dir
        try:
            self._dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            # Turns still answer, uncached.
            log_event("sec_cache_unavailable", error=type(exc).__name__)
        self._budget = budget
        self._fill_wait = fill_wait_seconds
        self._max_bytes = max_bytes
        # Facts fetched but not written (a full disk), until the parse reads them.
        self._held: dict[str, bytes] = {}

    def close(self) -> None:
        close = getattr(self._inner, "close", None)
        if callable(close):
            close()

    def get_company_tickers(self) -> dict[str, Any]:
        return self._json("tickers.json", self._inner.get_company_tickers)

    def get_submissions(self, cik: str, *, with_history: bool = True) -> dict[str, Any]:
        """A filer's submissions; ``with_history`` also reads older pages (``with_older_pages``)."""
        page = getattr(self._inner, "get_submissions_page", None)
        if not callable(page):
            fetch = lambda: self._inner.get_submissions(cik)  # noqa: E731
        else:
            # Older pages are read here, one cached and charged request each.
            fetch = lambda: self._inner.get_submissions(cik, with_history=False)  # noqa: E731
        payload = self._json(f"submissions-{cik}.json", fetch)
        if not with_history or not callable(page):
            return payload
        return with_older_pages(
            payload, lambda name: self._json(f"submissions-{name}", lambda: page(name))
        )

    def read_facts_digest(self, cik: str) -> tuple[tuple[str, int, int], bytes] | None:
        """A company's facts digest and its stamp, when a fresh one is on disk.

        A digest is what a lookup keeps of a company's facts (``sec_facts``): a
        tenth of the facts file's size, and decoded in milliseconds. It is as
        fresh as the facts file it was made from, by the same rule.
        """
        path = self._dir / f"digest-{cik}.json.gz"
        if not self._json_is_fresh(path):
            return None
        try:
            info = path.stat()
            data = gzip.decompress(path.read_bytes())
        except (OSError, EOFError, gzip.BadGzipFile):
            return None
        return (str(path.resolve()), info.st_mtime_ns, info.st_size), data

    def write_facts_digest(
        self, cik: str, data: bytes, *, fetched: float
    ) -> tuple[str, int, int] | None:
        """Keep a company's facts digest in place of its facts file; its stamp, if written.

        ``fetched`` is when the facts file was fetched: the digest is dated then,
        so a filing between the fetch and this write still makes it out of date.
        """
        path = self._dir / f"digest-{cik}.json.gz"
        # Level 6 compresses a digest nearly as well as 9, at a fraction of the CPU.
        if not self._write(path, gzip.compress(data, compresslevel=6)):
            return None
        try:
            os.utime(path, (fetched, fetched))
            info = path.stat()
        except OSError:
            _unlink_quietly(path)
            return None
        # The digest is all a lookup reads of the facts file, at a tenth of its size.
        _unlink_quietly(self._dir / f"facts-{cik}.json")
        return (str(path.resolve()), info.st_mtime_ns, info.st_size)

    def company_written(self, name: str) -> float | None:
        """When a cached file was written (``digest-{cik}.json.gz``, ``submissions-{cik}.json``)."""
        try:
            return (self._dir / name).stat().st_mtime
        except OSError:
            return None

    def company_facts_stamp(self, cik: str) -> tuple[str, int, int] | None:
        """Which copy of a company's facts file is on disk: its path, modified time and size.

        None without a fresh file on disk (none yet, expired, or held in memory
        after a failed write). A refresh rewrites the file, so its stamp changes.
        """
        path = self._dir / f"facts-{cik}.json"
        if cik in self._held or not self._json_is_fresh(path):
            return None
        try:
            info = path.stat()
        except OSError:
            return None
        return (str(path.resolve()), info.st_mtime_ns, info.st_size)

    def prefetch_company_facts(self, cik: str) -> None:
        """Bring a company's facts file in without parsing it.

        The network part of a facts read, so a caller can do it before taking a
        parse slot and never hold one across a slow download.
        """
        path = self._dir / f"facts-{cik}.json"
        if cik in self._held or self._json_is_fresh(path):
            return
        self._raise_if_missing(cik)
        with self._filling(path):
            if self._json_is_fresh(path):
                return
            if self._budget is not None:
                self._budget.consume_live_sec()
            try:
                document = self._facts_document(cik)
            except ProviderError as exc:
                if exc.details.get("status_code") == 404:
                    # Many filers (funds, trusts, predecessor CIKs) have no
                    # companyfacts at all; remember that as long as the company's
                    # other files last (the hour, or ADR 0013's rule).
                    self._write(self._dir / f"facts-{cik}.missing", b"")
                raise
            if not self._write(path, document):
                self._held[cik] = document

    def get_company_facts(self, cik: str) -> dict[str, Any]:
        self._raise_if_missing(cik)
        path = self._dir / f"facts-{cik}.json"
        for _attempt in range(2):
            self.prefetch_company_facts(cik)
            payload = self._load_facts(cik, path)
            if payload is not None:
                break
            # A damaged file: fetch it once more.
            _unlink_quietly(path)
        else:
            raise ProviderError(
                "SEC company facts could not be read", details={"cik": cik, "retryable": False}
            )
        if callable(getattr(self._inner, "get_company_facts_document", None)):
            # Raw documents are checked here, as they are parsed.
            try:
                validate_companyfacts_response(payload, cik, details={"cik": cik})
            except (ProviderError, DataIntegrityError):
                _unlink_quietly(path)
                raise
        return payload

    def get_filing_document(self, cik: str, accession: str, document: str) -> str:
        getter = getattr(self._inner, "get_filing_document", None)
        if not callable(getter):
            raise AttributeError("inner SEC source does not fetch filing documents")
        safe = "".join(ch if ch.isalnum() or ch in "-._" else "_" for ch in document)
        path = self._dir / f"html-{cik}-{accession}-{safe}"
        cached = _read_document(path)
        if cached is not None:
            return cached
        with self._filling(path):
            cached = _read_document(path)
            if cached is not None:
                return cached
            if self._budget is not None:
                self._budget.consume_live_sec()
            text = str(getter(cik, accession, document))
            if not usable_filing_document(text):
                raise ProviderError(
                    "SEC returned no usable filing document",
                    details={"document": document, "retryable": False},
                )
            self._write(path, text.encode("utf-8"))
            return text

    def _facts_document(self, cik: str) -> bytes:
        fetch = getattr(self._inner, "get_company_facts_document", None)
        if callable(fetch):
            document = bytes(fetch(cik))
        else:
            document = json.dumps(self._inner.get_company_facts(cik)).encode("utf-8")
        if not looks_like_json_object(document):
            raise ProviderError(
                "SEC company facts were not a JSON object",
                details={"cik": cik, "retryable": False},
            )
        return document

    def _load_facts(self, cik: str, path: Path) -> dict[str, Any] | None:
        document = self._held.pop(cik, None)
        if document is None:
            try:
                document = path.read_bytes()
            except OSError:
                return None
        try:
            payload = json.loads(document)
        except ValueError:
            return None
        return payload if isinstance(payload, dict) else None

    def _raise_if_missing(self, cik: str) -> None:
        if self._json_is_fresh(self._dir / f"facts-{cik}.missing"):
            raise ProviderError(
                "No SEC companyfacts response exists for the issuer",
                details={"cik": cik, "status_code": 404},
            )

    def _json(self, name: str, fetch: Any) -> dict[str, Any]:
        path = self._dir / name
        if self._json_is_fresh(path) and isinstance(cached := _read_json(path), dict):
            return cached
        with self._filling(path):
            if self._json_is_fresh(path) and isinstance(cached := _read_json(path), dict):
                return cached
            if self._budget is not None:
                self._budget.consume_live_sec()
            payload = fetch()
            if not isinstance(payload, dict):
                raise ProviderError(
                    "SEC response JSON must be an object",
                    details={"file": name, "retryable": False},
                )
            self._write(path, json.dumps(payload).encode("utf-8"))
            return payload

    @contextmanager
    def _filling(self, path: Path) -> Iterator[None]:
        """Hold the fill lock for ``path``; a fetch that outlasts the wait is not waited for."""
        lock = _lock_for(path)
        if not lock.acquire(timeout=self._fill_wait):
            raise ProviderError(
                "Another request is still fetching this SEC document",
                details={"file": path.name, "retryable": False},
            )
        try:
            yield
        finally:
            lock.release()

    def _write(self, path: Path, data: bytes) -> bool:
        written = _write_atomic(path, data)
        if written and self._max_bytes is not None:
            _sweep_soon(self._dir, self._max_bytes)
        return written

    def _json_is_fresh(self, path: Path) -> bool:
        try:
            written = path.stat().st_mtime
        except OSError:
            return False
        lifetime: float = _JSON_FRESH_SECONDS
        company = _COMPANY_FILE.match(path.name)
        if self._watch is not None and company is not None:
            lifetime = self._watch.lifetime(company.group(1), written)
        return time.time() - written < lifetime
