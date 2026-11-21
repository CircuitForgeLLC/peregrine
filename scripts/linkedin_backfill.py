# scripts/linkedin_backfill.py
"""
Fill in LinkedIn job descriptions that were missed during discovery (peregrine#272).

JobSpy fetches every LinkedIn job page itself, one request per result, in a burst. LinkedIn throttles
the server address (HTTP 429), so many jobs were saved with a title and company but no description,
and nothing retried them. This module retries them slowly, a few at a time, at the start of the next
discovery run.

Safety rules:
  - The request target is always built here from the numeric job id, never from a stored host.
  - Requests go through scrape_url._fetch, so the hosted version's address checks apply.
  - Only one backfill runs at a time in the process, and after repeated throttling every backfill
    is skipped for COOLDOWN_SECONDS, because the hosted server shares one address across all tenants.
  - A write never overwrites text a person added in the meantime (one conditional statement).
  - Jobs LinkedIn says are gone are remembered in memory for a day so they are not asked about again.
  - Logs carry counts and exception type names only, never titles, companies, descriptions or URLs.

Manual run, self-hosted installs only:  python -m scripts.linkedin_backfill
It uses the default database. On the hosted version the default database is not a tenant database,
so the backfill there runs only from the discovery task, which passes the tenant's own database.
"""
import random
import re
import sqlite3
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse

from scripts import scrape_url
from scripts.db import fill_job_fields_if_empty

MIN_DESCRIPTION_CHARS = 50       # a description shorter than this counts as missing
DEFAULT_LIMIT = 25               # max jobs attempted per run
MAX_AGE_DAYS = 30                # ignore jobs first found longer ago than this
PAUSE_RANGE = (2.0, 4.0)         # seconds between requests, uniform random
MAX_CONSECUTIVE_THROTTLES = 3    # stop the batch after this many throttles in a row
MAX_TOTAL_THROTTLES = 5          # stop the batch after this many throttles in one run
MAX_CONSECUTIVE_ERRORS = 3       # stop the batch after this many errors in a row
RETRY_AFTER_CAP = 60.0           # never sleep longer than this for one Retry-After
COOLDOWN_SECONDS = 15 * 60       # after a stop for throttling, skip all backfills for this long
RUN_BUDGET_SECONDS = 180.0       # stop a run that has been going this long (no cooldown)
NEGATIVE_CACHE_SECONDS = 24 * 3600   # how long a gone or empty job is left alone
NEGATIVE_CACHE_MAX = 5000        # most jobs remembered at once, oldest evicted first

_GUEST_API = "https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/"
_DISCARDED_STATUSES = ("rejected", "archived")
_FILLABLE_FIELDS = ("title", "company", "location")
_THROTTLE_STATUSES = (429, 999, 403)  # 999 is LinkedIn's own bot block, 403 is a refusal
_GONE_STATUSES = (404, 410)
_THROTTLE_PAUSE_FACTOR = 3

# Process-wide state: one backfill at a time, a shared cooldown after throttling, and the memory
# of jobs that can never be filled. Everything except the run lock is guarded by _state_lock.
_run_lock = threading.Lock()
_state_lock = threading.Lock()
_cooldown_until = 0.0
_negative: dict[tuple[str, int], float] = {}


@dataclass(frozen=True)
class BackfillResult:
    attempted: int
    filled: int
    skipped: int
    throttled: int
    errors: int
    stopped_early: bool
    skipped_cooling_down: bool
    remaining: int


def reset_state() -> None:
    """Clear the cooldown and the memory of gone jobs. For tests."""
    global _cooldown_until
    with _state_lock:
        _cooldown_until = 0.0
        _negative.clear()


def _set_cooldown(deadline: float) -> None:
    global _cooldown_until
    with _state_lock:
        _cooldown_until = deadline


def _cooldown_deadline() -> float:
    with _state_lock:
        return _cooldown_until


def _remember_gone(db_path: Path, job_id: int, now: float) -> None:
    key = (str(db_path), job_id)
    with _state_lock:
        _negative.pop(key, None)  # re-inserting keeps dict order equal to age order
        while len(_negative) >= max(1, NEGATIVE_CACHE_MAX):
            _negative.pop(next(iter(_negative)))
        _negative[key] = now


def _remembered_ids(db_path: Path, now: float) -> set[int]:
    """Ids of jobs in db_path remembered as gone and not yet expired. Drops expired entries."""
    prefix = str(db_path)
    with _state_lock:
        for key in [k for k, t in _negative.items() if now - t >= NEGATIVE_CACHE_SECONDS]:
            del _negative[key]
        return {job_id for (path, job_id) in _negative if path == prefix}


# ── choosing jobs ───────────────────────────────────────────────────────────────────────────────

def _linkedin_job_id(url: str) -> str | None:
    """The numeric job id when url is a job page on linkedin.com or a subdomain, else None."""
    try:
        parsed = urlparse(url or "")
    except ValueError:
        return None
    host = (parsed.hostname or "").lower()
    if host != "linkedin.com" and not host.endswith(".linkedin.com"):
        return None
    return scrape_url._extract_linkedin_job_id(parsed.path or "")


def _candidates(db_path: Path, now: float) -> list[dict]:
    """Every job that looks like it lacks a description, newest first, minus remembered ones.
    Read-only. The remembered ones are removed here, after the query, so they never starve others."""
    cutoff = (datetime.now() - timedelta(days=MAX_AGE_DAYS)).isoformat()[:10]  # noqa: DTZ005 -- intentionally naive, matches the stored date_found values (see peregrine#179)
    placeholders = ",".join("?" * len(_DISCARDED_STATUSES))
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT id, url, title, company, location FROM jobs "
            "WHERE LENGTH(TRIM(COALESCE(description, ''))) < ? "
            f"AND COALESCE(status, '') NOT IN ({placeholders}) "
            "AND (date_found IS NULL OR date_found = '' OR date_found >= ?) "
            "AND url LIKE '%linkedin.com%' "
            "ORDER BY id DESC",
            (MIN_DESCRIPTION_CHARS, *_DISCARDED_STATUSES, cutoff),
        ).fetchall()
    finally:
        conn.close()
    skip = _remembered_ids(db_path, now)
    picked = []
    for row in rows:
        job_id = _linkedin_job_id(row["url"])
        if job_id and row["id"] not in skip:
            picked.append({**dict(row), "linkedin_job_id": job_id})
    return picked


def find_pending(db_path: Path, limit: int, now: float | None = None) -> list[dict]:
    """Up to limit LinkedIn jobs that need a description, newest first."""
    return _candidates(db_path, time.monotonic() if now is None else now)[: max(0, limit)]


def count_pending(db_path: Path, now: float | None = None) -> int:
    return len(_candidates(db_path, time.monotonic() if now is None else now))


# ── fetching ────────────────────────────────────────────────────────────────────────────────────

def _retry_after_seconds(headers) -> float | None:
    """Retry-After as whole seconds clamped to [0, cap], or None when absent or not all digits."""
    try:
        raw = headers.get("Retry-After")
    except AttributeError:
        return None
    if not isinstance(raw, str) or not re.fullmatch(r"[0-9]+", raw.strip()):
        return None
    digits = raw.strip()
    if len(digits) > 9:  # far past the cap, and avoids converting a huge number
        return RETRY_AFTER_CAP
    return float(min(int(digits), RETRY_AFTER_CAP))


def _throttle_pause(resp, uniform) -> float:
    """Seconds to wait after a throttle: never less than a normal pause, Retry-After if longer."""
    floor = uniform(*PAUSE_RANGE)
    retry_after = _retry_after_seconds(getattr(resp, "headers", None))
    if retry_after is None:
        return floor * _THROTTLE_PAUSE_FACTOR
    return max(retry_after, floor)


class _Batch:
    """Counters for one run."""

    def __init__(self) -> None:
        self.attempted = self.filled = self.skipped = self.throttled = self.errors = 0
        self.consecutive_throttles = 0
        self.consecutive_errors = 0
        self.stopped_early = False
        self.cooldown = False

    def ok(self) -> None:
        self.consecutive_throttles = 0
        self.consecutive_errors = 0

    def error(self) -> None:
        self.errors += 1
        self.consecutive_errors += 1


def _store_posting(db_path: Path, job: dict, parsed: dict, batch: _Batch) -> None:
    fields = {name: parsed[name] for name in _FILLABLE_FIELDS if parsed.get(name)}
    written = fill_job_fields_if_empty(
        db_path, job["id"], description=parsed["description"], fields=fields,
        min_description_chars=MIN_DESCRIPTION_CHARS,
    )
    if written:
        batch.filled += 1
    else:
        batch.skipped += 1  # someone filled it in meanwhile: nothing to do


def _handle_response(db_path: Path, job: dict, resp, batch: _Batch, uniform, now: float) -> float | None:
    """Record the outcome of one response. For a throttle returns the pause before the next request."""
    status = getattr(resp, "status_code", None)
    if status == 200:
        parsed = scrape_url._parse_linkedin_posting(resp.text or "")
        if parsed.get("description"):
            _store_posting(db_path, job, parsed, batch)
        else:
            batch.skipped += 1  # closed posting or a page variant: not an error
            _remember_gone(db_path, job["id"], now)
        batch.ok()
    elif status in _GONE_STATUSES:
        batch.skipped += 1
        _remember_gone(db_path, job["id"], now)
        batch.ok()
    elif status in _THROTTLE_STATUSES:
        batch.throttled += 1
        batch.consecutive_throttles += 1
        return _throttle_pause(resp, uniform)
    else:
        batch.error()
    return None


def _skipped_result() -> BackfillResult:
    return BackfillResult(0, 0, 0, 0, 0, False, True, 0)


def _fetch_one(db_path: Path, job: dict, fetch, uniform, now: float, batch: _Batch) -> float | None:
    """One request and its bookkeeping. Any failure is counted as an error, never raised."""
    try:
        resp = fetch(_GUEST_API + job["linkedin_job_id"],
                     headers=scrape_url._HEADERS, timeout=scrape_url._TIMEOUT)
        return _handle_response(db_path, job, resp, batch, uniform, now)
    except Exception as exc:  # noqa: BLE001 -- one bad job (network, database, parser) must not end the batch, it is counted
        batch.error()
        print(f"[linkedin-backfill] job failed: {type(exc).__name__}")
        return None


def _should_stop(batch: _Batch) -> bool:
    if batch.consecutive_throttles >= MAX_CONSECUTIVE_THROTTLES or batch.throttled >= MAX_TOTAL_THROTTLES:
        batch.cooldown = True
        return True
    return batch.consecutive_errors >= MAX_CONSECUTIVE_ERRORS


def _run_batch(db_path: Path, jobs: list[dict], fetch, sleep, uniform, now) -> _Batch:
    batch = _Batch()
    started = now()
    pause_next: float | None = None
    for index, job in enumerate(jobs):
        if now() - started >= RUN_BUDGET_SECONDS:
            batch.stopped_early = True  # out of time, but LinkedIn has not pushed back: no cooldown
            break
        if index:
            sleep(pause_next if pause_next is not None else uniform(*PAUSE_RANGE))
        batch.attempted += 1
        pause_next = _fetch_one(db_path, job, fetch, uniform, now(), batch)
        if _should_stop(batch):
            batch.stopped_early = True
            break
    if batch.cooldown:
        _set_cooldown(now() + COOLDOWN_SECONDS)
    return batch


def backfill_linkedin_descriptions(db_path: Path, *, limit: int = DEFAULT_LIMIT,
                                   fetch=None, sleep=None, uniform=None, now=None) -> BackfillResult:
    """Fetch missing descriptions for up to limit LinkedIn jobs in db_path. Never raises on a
    network failure. fetch, sleep, uniform and now are injectable for tests."""
    fetch = fetch or scrape_url._fetch
    sleep = sleep or time.sleep
    uniform = uniform or random.uniform
    now = now or time.monotonic

    if not _run_lock.acquire(blocking=False):
        return _skipped_result()
    try:
        if now() < _cooldown_deadline():
            return _skipped_result()
        batch = _run_batch(db_path, find_pending(db_path, limit, now()), fetch, sleep, uniform, now)
        remaining = count_pending(db_path, now())
    finally:
        _run_lock.release()

    result = BackfillResult(batch.attempted, batch.filled, batch.skipped, batch.throttled,
                            batch.errors, batch.stopped_early, False, remaining)
    if result.attempted:
        print(f"[linkedin-backfill] {summary_line(result)}")
    return result


def summary_line(result: BackfillResult) -> str:
    """Counts only: safe to log."""
    line = (f"filled {result.filled}, throttled {result.throttled}, errors {result.errors}, "
            f"{result.remaining} still pending")
    return line + (", stopped early" if result.stopped_early else "")


def _descriptions(n: int) -> str:
    return f"{n} LinkedIn description{'s' if n != 1 else ''}"


def completion_note(result: BackfillResult) -> str:
    """Text to append to the discovery completion message. Empty when there is nothing to say."""
    parts = []
    if result.filled:
        parts.append(f"{_descriptions(result.filled)} filled")
    if result.remaining and not result.skipped_cooling_down:
        parts.append(f"{_descriptions(result.remaining)} still pending")
    return "".join(f", {p}" for p in parts)


if __name__ == "__main__":
    from scripts.db import DEFAULT_DB

    outcome = backfill_linkedin_descriptions(DEFAULT_DB, limit=DEFAULT_LIMIT)
    print(f"[linkedin-backfill] {summary_line(outcome)}" if not outcome.skipped_cooling_down
          else "[linkedin-backfill] skipped, cooling down after throttling")
