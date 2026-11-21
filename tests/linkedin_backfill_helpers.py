"""Shared fakes and builders for the LinkedIn backfill tests (peregrine#272).

No test using these touches the real network or the real sleep: fetch, sleep, uniform and now are
injected into the backfill.
"""
import sqlite3
from datetime import datetime, timedelta

from scripts import linkedin_backfill as lb

LONG_DESC = "A real description that is comfortably longer than the fifty character minimum."
GUEST_PREFIX = "https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/"
PARSED_DESC = "We run a virtual clinic and care team.\nSchedule patients and answer questions."

POSTING_HTML = (
    '<html><body>'
    '<h2 class="top-card-layout__title">Care Coordinator</h2>'
    '<a class="topcard__org-name-link">Acme Health</a>'
    '<span class="topcard__flavor--bullet">Remote, US</span>'
    '<div class="show-more-less-html__markup"><p>We run a virtual clinic and care team.</p>'
    '<p>Schedule patients and answer questions.</p></div>'
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
    """Returns (or raises) the scripted items in order, repeating the last one.
    An item may also be a callable taking the url and returning a response."""

    def __init__(self, *items, on_call=None):
        self.items = list(items)
        self.urls = []
        self.kwargs = []
        self.on_call = on_call

    def __call__(self, url, **kwargs):
        self.urls.append(url)
        self.kwargs.append(kwargs)
        if self.on_call:
            self.on_call(url)
        item = self.items[min(len(self.urls) - 1, len(self.items) - 1)]
        if isinstance(item, Exception):
            raise item
        return item(url) if callable(item) else item


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


def today(days_ago=0):
    return (datetime.now() - timedelta(days=days_ago)).isoformat()[:10]  # noqa: DTZ005 -- naive on purpose, matches the stored date_found values


def make_db(tmp_path, *jobs, name="test.db"):
    """Build a migrated database holding the given job dicts. Returns (db_path, [ids])."""
    from scripts.db import init_db, insert_job
    db = tmp_path / name
    init_db(db)
    ids = []
    for i, job in enumerate(jobs):
        row = {
            "title": "", "company": "", "location": "", "source": "linkedin", "description": "",
            "url": f"https://www.linkedin.com/jobs/view/{1000 + i}/", "date_found": today(),
        }
        row.update(job)
        ids.append(insert_job(db, row))
    return db, ids


def get_row(db, job_id):
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    try:
        return dict(conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone())
    finally:
        conn.close()


def set_description(db, job_id, text):
    conn = sqlite3.connect(db)
    try:
        conn.execute("UPDATE jobs SET description=? WHERE id=?", (text, job_id))
        conn.commit()
    finally:
        conn.close()


def run(db, fetch, pauses=None, clock=None, **kwargs):
    pauses = pauses or Pauses()
    clock = clock or Clock()
    return lb.backfill_linkedin_descriptions(
        db, fetch=fetch, sleep=pauses.sleep, uniform=pauses.uniform, now=clock, **kwargs,
    )


def result(**overrides):
    base = {"attempted": 0, "filled": 0, "skipped": 0, "throttled": 0, "errors": 0,
            "stopped_early": False, "skipped_cooling_down": False, "remaining": 0}
    return lb.BackfillResult(**{**base, **overrides})
