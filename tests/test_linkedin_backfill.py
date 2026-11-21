"""LinkedIn description backfill (peregrine#272).

JobSpy fetches every LinkedIn job page itself in a burst, LinkedIn answers many with HTTP 429, and
those jobs were saved with no description and never retried. The backfill retries them slowly.
No test here touches the real network or the real sleep: fetch, sleep, uniform and now are injected.
"""
import sqlite3
import threading
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

from scripts import linkedin_backfill as lb

LONG_DESC = "A real description that is comfortably longer than the fifty character minimum."
GUEST_PREFIX = "https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/"

POSTING_HTML = (
    '<html><body>'
    '<h2 class="top-card-layout__title">Care Coordinator</h2>'
    '<a class="topcard__org-name-link">Acme Health</a>'
    '<span class="topcard__flavor--bullet">Remote, US</span>'
    '<div class="show-more-less-html__markup"><p>We run a virtual clinic and care team.</p><p>Schedule patients and answer questions.</p></div>'
    '</body></html>'
)
EMPTY_HTML = "<html><body><h2 class='top-card-layout__title'>Gone</h2></body></html>"


class Resp:
    def __init__(self, status=200, text=POSTING_HTML, headers=None):
        self.status_code = status
        self.text = text
        self.headers = headers or {}

    def raise_for_status(self):  # the backfill reads status_code itself
        raise AssertionError("the backfill must not call raise_for_status")


class ScriptedFetch:
    """Returns (or raises) the scripted items in order, repeating the last one."""

    def __init__(self, *items):
        self.items = list(items)
        self.urls = []
        self.kwargs = []

    def __call__(self, url, **kwargs):
        self.urls.append(url)
        self.kwargs.append(kwargs)
        item = self.items[min(len(self.urls) - 1, len(self.items) - 1)]
        if isinstance(item, Exception):
            raise item
        return item


class Clock:
    def __init__(self, start=1000.0):
        self.t = start

    def __call__(self):
        return self.t


class Pauses:
    def __init__(self, value=2.5):
        self.value = value
        self.sleeps = []
        self.bounds = []

    def sleep(self, seconds):
        self.sleeps.append(seconds)

    def uniform(self, lo, hi):
        self.bounds.append((lo, hi))
        return self.value


@pytest.fixture(autouse=True)
def _fresh_state():
    lb.reset_state()
    yield
    lb.reset_state()


def _today(days_ago=0):
    return (datetime.now() - timedelta(days=days_ago)).isoformat()[:10]  # noqa: DTZ005 -- naive on purpose, matches the stored date_found values


def _db(tmp_path, *jobs):
    """Build a migrated database holding the given job dicts. Returns (db_path, [ids])."""
    from scripts.db import init_db, insert_job
    db = tmp_path / "test.db"
    init_db(db)
    ids = []
    for i, job in enumerate(jobs):
        row = {
            "title": "", "company": "", "location": "", "source": "linkedin", "description": "",
            "url": f"https://www.linkedin.com/jobs/view/{1000 + i}/", "date_found": _today(),
        }
        row.update(job)
        ids.append(insert_job(db, row))
    return db, ids


def _row(db, job_id):
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    try:
        return dict(conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone())
    finally:
        conn.close()


def _run(db, fetch, pauses=None, clock=None, **kwargs):
    pauses = pauses or Pauses()
    clock = clock or Clock()
    return lb.backfill_linkedin_descriptions(
        db, fetch=fetch, sleep=pauses.sleep, uniform=pauses.uniform, now=clock, **kwargs,
    )


# ── what gets written ───────────────────────────────────────────────────────────────────────────

def test_a_200_response_fills_the_description_and_nothing_else_when_other_fields_exist(tmp_path):
    db, (job_id,) = _db(tmp_path, {"title": "My Title", "company": "My Co", "location": "My Place"})

    result = _run(db, ScriptedFetch(Resp()))

    row = _row(db, job_id)
    assert row["description"] == "We run a virtual clinic and care team.\nSchedule patients and answer questions."
    assert (row["title"], row["company"], row["location"]) == ("My Title", "My Co", "My Place")
    assert (result.attempted, result.filled) == (1, 1)


def test_missing_title_company_or_location_are_filled_but_existing_ones_are_never_overwritten(tmp_path):
    db, (empty, partial) = _db(
        tmp_path,
        {},
        {"title": "Keep Title", "company": "", "location": "Keep Place"},
    )

    _run(db, ScriptedFetch(Resp()))

    filled = _row(db, empty)
    assert (filled["title"], filled["company"], filled["location"]) == ("Care Coordinator", "Acme Health", "Remote, US")
    kept = _row(db, partial)
    assert (kept["title"], kept["company"], kept["location"]) == ("Keep Title", "Acme Health", "Keep Place")


# ── pacing and throttling ───────────────────────────────────────────────────────────────────────

def test_the_pause_is_between_requests_in_the_pause_range_and_not_before_the_first(tmp_path):
    db, _ = _db(tmp_path, {}, {}, {})
    pauses = Pauses(value=3.0)

    _run(db, ScriptedFetch(Resp()), pauses)

    assert pauses.bounds == [lb.PAUSE_RANGE, lb.PAUSE_RANGE]
    assert pauses.sleeps == [3.0, 3.0]


def test_a_single_429_honours_retry_after_clamped_and_the_batch_continues(tmp_path):
    db, _ids = _db(tmp_path, {}, {}, {})
    pauses = Pauses()
    fetch = ScriptedFetch(Resp(429, headers={"Retry-After": "9999"}), Resp(), Resp())

    result = _run(db, fetch, pauses)

    assert pauses.sleeps[0] == lb.RETRY_AFTER_CAP
    assert (result.throttled, result.filled, result.stopped_early) == (1, 2, False)
    assert len(fetch.urls) == 3


def test_retry_after_that_is_not_an_integer_is_ignored_and_the_default_pause_is_used(tmp_path):
    db, _ = _db(tmp_path, {}, {})
    pauses = Pauses(value=2.0)
    fetch = ScriptedFetch(Resp(429, headers={"Retry-After": "Wed, 21 Oct 2026 07:28:00 GMT"}), Resp())

    _run(db, fetch, pauses)

    assert pauses.sleeps == [2.0 * 3]


def test_three_consecutive_429s_stop_the_batch_and_set_the_cooldown(tmp_path):
    db, _ = _db(tmp_path, {}, {}, {}, {}, {})
    clock = Clock(500.0)
    fetch = ScriptedFetch(Resp(429))

    result = _run(db, fetch, clock=clock)

    assert len(fetch.urls) == lb.MAX_CONSECUTIVE_THROTTLES
    assert (result.throttled, result.stopped_early) == (3, True)
    assert result.remaining == 5
    again = ScriptedFetch(Resp())
    clock.t = 500.0 + lb.COOLDOWN_SECONDS - 1
    assert _run(db, again, clock=clock).skipped_cooling_down is True
    clock.t = 500.0 + lb.COOLDOWN_SECONDS + 1
    assert _run(db, again, clock=clock).skipped_cooling_down is False
    assert again.urls


def test_a_success_resets_the_consecutive_throttle_counter(tmp_path):
    db, _ = _db(tmp_path, {}, {}, {}, {}, {}, {})
    fetch = ScriptedFetch(Resp(429), Resp(429), Resp(), Resp(429), Resp(429), Resp())

    result = _run(db, fetch)

    assert len(fetch.urls) == 6
    assert (result.throttled, result.filled, result.stopped_early) == (4, 2, False)


def test_a_backfill_during_the_cooldown_makes_no_requests_and_touches_no_rows(tmp_path, monkeypatch):
    db, (job_id,) = _db(tmp_path, {})
    clock = Clock(10.0)
    monkeypatch.setattr(lb, "_cooldown_until", clock() + 100)
    fetch = ScriptedFetch(Resp())

    with patch.object(lb, "find_pending", side_effect=AssertionError("must not read the database")):
        result = _run(db, fetch, clock=clock)

    assert result.skipped_cooling_down is True
    assert fetch.urls == []
    assert _row(db, job_id)["description"] == ""


def test_a_second_concurrent_backfill_returns_immediately_without_requests(tmp_path):
    db, _ = _db(tmp_path, {})
    fetch = ScriptedFetch(Resp())

    assert lb._run_lock.acquire(blocking=False)
    try:
        done = []
        t = threading.Thread(target=lambda: done.append(_run(db, fetch)))
        t.start()
        t.join(timeout=5)
        assert not t.is_alive(), "the second backfill must not block waiting for the lock"
    finally:
        lb._run_lock.release()

    assert done[0].skipped_cooling_down is True
    assert fetch.urls == []


def test_the_limit_caps_the_attempts_and_remaining_counts_the_rest(tmp_path):
    db, _ = _db(tmp_path, {}, {}, {}, {}, {})

    result = _run(db, ScriptedFetch(Resp()), limit=2)

    assert (result.attempted, result.filled, result.remaining) == (2, 2, 3)


# ── other outcomes ──────────────────────────────────────────────────────────────────────────────

def test_404_and_410_are_skipped_without_counting_as_a_throttle(tmp_path):
    db, _ = _db(tmp_path, {}, {}, {}, {})
    fetch = ScriptedFetch(Resp(404), Resp(410), Resp(404), Resp(410))

    result = _run(db, fetch)

    assert (result.skipped, result.throttled, result.errors, result.stopped_early) == (4, 0, 0, False)
    assert len(fetch.urls) == 4


def test_an_empty_parsed_description_is_skipped_not_an_error(tmp_path):
    db, (job_id,) = _db(tmp_path, {})

    result = _run(db, ScriptedFetch(Resp(200, text=EMPTY_HTML)))

    assert (result.skipped, result.errors, result.throttled, result.filled) == (1, 0, 0, 0)
    assert _row(db, job_id)["description"] == ""


def test_network_errors_are_counted_and_three_in_a_row_stop_the_batch_and_never_raise(tmp_path):
    db, _ = _db(tmp_path, {}, {}, {}, {}, {})
    fetch = ScriptedFetch(ConnectionError("boom"), Resp(500), TimeoutError("slow"))

    result = _run(db, fetch)

    assert len(fetch.urls) == lb.MAX_CONSECUTIVE_ERRORS
    assert (result.errors, result.stopped_early) == (3, True)
    assert result.remaining == 5


# ── which jobs ──────────────────────────────────────────────────────────────────────────────────

def test_only_linkedin_job_urls_with_a_numeric_id_on_a_linkedin_host_are_picked(tmp_path):
    good = [
        "https://www.linkedin.com/jobs/view/111/",
        "https://linkedin.com/jobs/view/222",
        "https://uk.linkedin.com/jobs/view/333/?trk=x",
    ]
    bad = [
        "https://evil.example/jobs/view/123?x=linkedin.com",
        "https://www.linkedin.com.evil.example/jobs/view/123",
        "https://www.linkedin.com/jobs/view/not-a-number/",
        "https://www.linkedin.com/in/someone/",
        "https://example.com/jobs/view/444",
        "",
    ]
    db, _ids = _db(tmp_path, *({"url": u} for u in [*good, *bad]))

    picked = lb.find_pending(db, 100)

    assert sorted(p["url"] for p in picked) == sorted(good)
    assert lb.count_pending(db) == 3


def test_jobs_with_enough_description_rejected_jobs_and_old_jobs_are_skipped(tmp_path):
    db, ids = _db(
        tmp_path,
        {"description": LONG_DESC},
        {"status": "rejected"},
        {"status": "archived"},
        {"date_found": _today(lb.MAX_AGE_DAYS + 5)},
        {"description": "   short   "},
        {"date_found": ""},
        {"status": "approved"},
    )

    picked = [p["id"] for p in lb.find_pending(db, 100)]

    assert picked == [ids[6], ids[5], ids[4]]  # newest first
    assert lb.count_pending(db) == 3


def test_the_target_url_is_always_the_fixed_linkedin_guest_endpoint(tmp_path):
    db, _ids = _db(
        tmp_path,
        {"url": "https://uk.linkedin.com/jobs/view/777/?trk=evil&redirect=https://evil.example"},
        {"url": "https://www.linkedin.com/jobs/view/888/"},
    )
    fetch = ScriptedFetch(Resp())

    _run(db, fetch)

    assert sorted(fetch.urls) == [GUEST_PREFIX + "777", GUEST_PREFIX + "888"]
    for kwargs in fetch.kwargs:
        assert "User-Agent" in kwargs["headers"]
        assert kwargs["timeout"] > 0


# ── privacy, hosted mode and discovery wiring ───────────────────────────────────────────────────

def test_the_log_lines_never_contain_titles_companies_urls_or_descriptions(tmp_path, capsys):
    db, _ = _db(
        tmp_path,
        {"title": "SecretTitleXyz", "company": "SecretCompanyXyz", "url": "https://www.linkedin.com/jobs/view/4242/"},
        {"title": "OtherTitleXyz", "company": "OtherCompanyXyz", "url": "https://www.linkedin.com/jobs/view/4343/"},
        {"title": "ThirdTitleXyz", "company": "ThirdCompanyXyz", "url": "https://www.linkedin.com/jobs/view/4444/"},
    )

    _run(db, ScriptedFetch(Resp(), Resp(429), ConnectionError("boom https://www.linkedin.com/jobs/view/4444")))

    out = capsys.readouterr().out
    assert "[linkedin-backfill]" in out
    for secret in ("SecretTitleXyz", "SecretCompanyXyz", "OtherTitleXyz", "OtherCompanyXyz",
                   "linkedin.com", "We run a virtual clinic", "Care Coordinator", "Acme Health", "boom"):
        assert secret not in out


def test_hosted_mode_uses_the_guarded_session_and_never_plain_requests_get(tmp_path, monkeypatch):
    import scripts.scrape_url as scrape

    used = []

    class FakeSafeSession:
        def get(self, url, **kwargs):
            used.append(url)
            return Resp()

    monkeypatch.setenv("CLOUD_MODE", "true")
    monkeypatch.setattr(scrape.safe_net, "SafeSession", FakeSafeSession)
    monkeypatch.setattr(scrape.requests, "get", lambda *a, **k: pytest.fail("plain requests.get used when hosted"))
    db, (job_id,) = _db(tmp_path, {})
    pauses = Pauses()

    result = lb.backfill_linkedin_descriptions(db, sleep=pauses.sleep, uniform=pauses.uniform, now=Clock())

    assert used == [GUEST_PREFIX + "1000"]
    assert result.filled == 1
    assert _row(db, job_id)["description"]


def _discovery_task(tmp_path):
    from scripts.db import init_db, insert_task
    db = tmp_path / "task.db"
    init_db(db)
    task_id, _ = insert_task(db, "discovery", 0)
    return db, task_id


def _task(db, task_id):
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    try:
        return dict(conn.execute("SELECT * FROM background_tasks WHERE id=?", (task_id,)).fetchone())
    finally:
        conn.close()


def _result(**overrides):
    base = {"attempted": 0, "filled": 0, "skipped": 0, "throttled": 0, "errors": 0,
            "stopped_early": False, "skipped_cooling_down": False, "remaining": 0}
    return lb.BackfillResult(**{**base, **overrides})


def test_the_discovery_task_runs_the_backfill_first_and_survives_its_failure(tmp_path, monkeypatch):
    from scripts.task_runner import _run_task
    monkeypatch.delenv("DEMO_MODE", raising=False)
    calls = []
    db, task_id = _discovery_task(tmp_path)

    def fake_backfill(db_path, **kwargs):
        calls.append(("backfill", db_path))
        raise RuntimeError("linkedin exploded")

    def fake_discovery(db_path, **kwargs):
        calls.append(("discovery", db_path))
        return 4

    with patch("scripts.linkedin_backfill.backfill_linkedin_descriptions", fake_backfill), \
         patch("scripts.discover.run_discovery", fake_discovery):
        _run_task(db, task_id, "discovery", 0)

    assert calls == [("backfill", db), ("discovery", db)]
    task = _task(db, task_id)
    assert task["status"] == "completed"
    assert task["error"] == "4 new listings added"


def test_the_discovery_completion_message_mentions_linkedin_only_when_relevant(tmp_path, monkeypatch):
    from scripts.task_runner import _run_task
    monkeypatch.delenv("DEMO_MODE", raising=False)

    cases = [
        (_result(), 1, "1 new listing added"),
        (_result(filled=12, remaining=8), 12, "12 new listings added, 12 LinkedIn descriptions filled, 8 still pending"),
        (_result(filled=1), 0, "0 new listings added, 1 LinkedIn description filled"),
        (_result(remaining=15), 2, "2 new listings added, 15 still pending"),
        (_result(skipped_cooling_down=True, remaining=0), 3, "3 new listings added"),
    ]
    for n, (res, new, expected) in enumerate(cases):
        sub = tmp_path / f"case{n}"
        sub.mkdir()
        db, task_id = _discovery_task(sub)
        with patch("scripts.linkedin_backfill.backfill_linkedin_descriptions", lambda *a, _r=res, **k: _r), \
             patch("scripts.discover.run_discovery", lambda *a, _n=new, **k: _n):
            _run_task(db, task_id, "discovery", 0)
        assert _task(db, task_id)["error"] == expected


# ── the shared parser ───────────────────────────────────────────────────────────────────────────

def test_the_linkedin_parser_is_shared():
    from scripts.scrape_url import _parse_linkedin_posting

    parsed = _parse_linkedin_posting(POSTING_HTML)

    assert parsed == {
        "title": "Care Coordinator",
        "company": "Acme Health",
        "location": "Remote, US",
        "description": "We run a virtual clinic and care team.\nSchedule patients and answer questions.",
        "source": "linkedin",
    }
    assert _parse_linkedin_posting("<html></html>") == {"source": "linkedin"}
