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
  - Logs carry counts only, never titles, companies, descriptions or URLs.

Manual run:  python -m scripts.linkedin_backfill
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
from scripts.db import update_job_fields

MIN_DESCRIPTION_CHARS = 50       # a description shorter than this counts as missing
DEFAULT_LIMIT = 25               # max jobs attempted per run
MAX_AGE_DAYS = 30                # ignore jobs first found longer ago than this
PAUSE_RANGE = (2.0, 4.0)         # seconds between requests, uniform random
MAX_CONSECUTIVE_THROTTLES = 3    # stop the batch after this many 429s in a row
MAX_CONSECUTIVE_ERRORS = 3       # stop the batch after this many network errors in a row
RETRY_AFTER_CAP = 60.0           # never sleep longer than this for one Retry-After
COOLDOWN_SECONDS = 15 * 60       # after a stop for throttling, skip all backfills for this long

_GUEST_API = "https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/"
_DISCARDED_STATUSES = ("rejected", "archived")
_FILLABLE_FIELDS = ("title", "company", "location")
_THROTTLE_PAUSE_FACTOR = 3

# Process-wide state: one backfill at a time, and a shared cooldown after throttling.
_run_lock = threading.Lock()
_state_lock = threading.Lock()
_cooldown_until = 0.0


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
    """Clear the cooldown. For tests."""
    global _cooldown_until
    with _state_lock:
        _cooldown_until = 0.0


def _set_cooldown(deadline: float) -> None:
    global _cooldown_until
    with _state_lock:
        _cooldown_until = deadline


def _cooldown_deadline() -> float:
    with _state_lock:
        return _cooldown_until


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


def _candidates(db_path: Path) -> list[dict]:
    """Every job that looks like it lacks a description, newest first. Read-only."""
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
    picked = []
    for row in rows:
        job_id = _linkedin_job_id(row["url"])
        if job_id:
            picked.append({**dict(row), "linkedin_job_id": job_id})
    return picked


def find_pending(db_path: Path, limit: int) -> list[dict]:
    """Up to limit LinkedIn jobs that need a description, newest first."""
    return _candidates(db_path)[: max(0, limit)]


def count_pending(db_path: Path) -> int:
    return len(_candidates(db_path))


# ── fetching ────────────────────────────────────────────────────────────────────────────────────

def _retry_after_seconds(headers) -> float | None:
    """Retry-After as whole seconds clamped to the cap, or None when absent or not an integer."""
    try:
        raw = headers.get("Retry-After")
    except AttributeError:
        return None
    if not isinstance(raw, str) or not re.fullmatch(r"[0-9]{1,9}", raw.strip()):
        return None
    return float(min(int(raw.strip()), RETRY_AFTER_CAP))


def _updates_from_posting(job: dict, parsed: dict) -> dict:
    """The description, plus title, company and location only where the stored value is empty."""
    fields = {"description": parsed["description"]}
    for name in _FILLABLE_FIELDS:
        if not (job.get(name) or "").strip() and parsed.get(name):
            fields[name] = parsed[name]
    return fields


class _Batch:
    """Counters for one run."""

    def __init__(self) -> None:
        self.attempted = self.filled = self.skipped = self.throttled = self.errors = 0
        self.consecutive_throttles = 0
        self.consecutive_errors = 0
        self.stopped_early = False

    def ok(self) -> None:
        self.consecutive_throttles = 0
        self.consecutive_errors = 0


def _handle_response(db_path: Path, job: dict, resp, batch: _Batch, uniform) -> float | None:
    """Record the outcome of one response. For a 429 returns the pause before the next request
    (Retry-After when sent, else three times the usual pause), otherwise None."""
    status = getattr(resp, "status_code", None)
    if status == 200:
        parsed = scrape_url._parse_linkedin_posting(resp.text or "")
        if parsed.get("description"):
            update_job_fields(db_path, job["id"], _updates_from_posting(job, parsed))
            batch.filled += 1
        else:
            batch.skipped += 1  # closed posting or a page variant: not an error
        batch.ok()
    elif status in (404, 410):
        batch.skipped += 1
        batch.ok()
    elif status == 429:
        batch.throttled += 1
        batch.consecutive_throttles += 1
        retry_after = _retry_after_seconds(getattr(resp, "headers", None))
        if retry_after is not None:
            return retry_after
        return uniform(*PAUSE_RANGE) * _THROTTLE_PAUSE_FACTOR
    else:
        batch.errors += 1
        batch.consecutive_errors += 1
    return None


def _skipped_result() -> BackfillResult:
    return BackfillResult(0, 0, 0, 0, 0, False, True, 0)


def _run_batch(db_path: Path, jobs: list[dict], fetch, sleep, uniform, now) -> _Batch:
    batch = _Batch()
    pause_next: float | None = None
    for index, job in enumerate(jobs):
        if index:
            sleep(pause_next if pause_next is not None else uniform(*PAUSE_RANGE))
        pause_next = None
        batch.attempted += 1
        try:
            resp = fetch(_GUEST_API + job["linkedin_job_id"],
                         headers=scrape_url._HEADERS, timeout=scrape_url._TIMEOUT)
        except Exception:  # noqa: BLE001 -- a network failure must never escape the batch, it is counted instead
            batch.errors += 1
            batch.consecutive_errors += 1
        else:
            pause_next = _handle_response(db_path, job, resp, batch, uniform)
        if batch.consecutive_throttles >= MAX_CONSECUTIVE_THROTTLES:
            batch.stopped_early = True
            _set_cooldown(now() + COOLDOWN_SECONDS)
            break
        if batch.consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
            batch.stopped_early = True
            break
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
        jobs = find_pending(db_path, limit)
        batch = _run_batch(db_path, jobs, fetch, sleep, uniform, now)
    finally:
        _run_lock.release()

    remaining = count_pending(db_path)
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


def completion_note(result: BackfillResult) -> str:
    """Text to append to the discovery completion message. Empty when there is nothing to say."""
    parts = []
    if result.filled:
        parts.append(f"{result.filled} LinkedIn description{'s' if result.filled != 1 else ''} filled")
    if result.remaining and not result.skipped_cooling_down:
        parts.append(f"{result.remaining} still pending")
    return "".join(f", {p}" for p in parts)


if __name__ == "__main__":
    from scripts.db import DEFAULT_DB

    outcome = backfill_linkedin_descriptions(DEFAULT_DB, limit=DEFAULT_LIMIT)
    print(f"[linkedin-backfill] {summary_line(outcome)}" if not outcome.skipped_cooling_down
          else "[linkedin-backfill] skipped, cooling down after throttling")
