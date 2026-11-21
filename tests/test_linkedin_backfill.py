"""LinkedIn description backfill (peregrine#272): selection, writes, parsing and wiring.

JobSpy fetches every LinkedIn job page itself in a burst, LinkedIn answers many with HTTP 429, and
those jobs were saved with no description and never retried. The backfill retries them slowly.
Pacing, throttles, cooldown and the stop rules are in test_linkedin_backfill_pacing.py.
"""
import sqlite3
from unittest.mock import patch

import pytest

from scripts import linkedin_backfill as lb
from tests.linkedin_backfill_helpers import (
    GUEST_PREFIX,
    LONG_DESC,
    PARSED_DESC,
    POSTING_HTML,
    Clock,
    Pauses,
    Resp,
    ScriptedFetch,
    get_row,
    make_db,
    result,
    run,
    set_description,
    today,
)


@pytest.fixture(autouse=True)
def _fresh_state():
    lb.reset_state()
    yield
    lb.reset_state()


# ── what gets written ───────────────────────────────────────────────────────────────────────────

def test_a_200_response_fills_the_description_and_nothing_else_when_other_fields_exist(tmp_path):
    db, (job_id,) = make_db(tmp_path, {"title": "My Title", "company": "My Co", "location": "My Place"})

    res = run(db, ScriptedFetch(Resp()))

    row = get_row(db, job_id)
    assert row["description"] == PARSED_DESC
    assert (row["title"], row["company"], row["location"]) == ("My Title", "My Co", "My Place")
    assert (res.attempted, res.filled) == (1, 1)


def test_missing_title_company_or_location_are_filled_but_existing_ones_are_never_overwritten(tmp_path):
    db, (empty, partial, placeholder) = make_db(
        tmp_path,
        {},
        {"title": "Keep Title", "company": "", "location": "Keep Place"},
        {"title": "Importing…", "company": "Keep Co", "location": "  "},
    )

    run(db, ScriptedFetch(Resp()))

    filled = get_row(db, empty)
    assert (filled["title"], filled["company"], filled["location"]) == ("Care Coordinator", "Acme Health", "Remote, US")
    kept = get_row(db, partial)
    assert (kept["title"], kept["company"], kept["location"]) == ("Keep Title", "Acme Health", "Keep Place")
    imported = get_row(db, placeholder)
    assert (imported["title"], imported["company"], imported["location"]) == ("Care Coordinator", "Keep Co", "Remote, US")


def test_a_description_written_while_the_request_was_in_flight_is_never_overwritten(tmp_path):
    db, (job_id,) = make_db(tmp_path, {"title": "My Title"})
    mine = "The person pasted this description by hand while the backfill was running, it is long."

    def person_edits(_url):
        set_description(db, job_id, mine)

    res = run(db, ScriptedFetch(Resp(), on_call=person_edits))

    assert get_row(db, job_id)["description"] == mine
    assert (res.filled, res.skipped) == (0, 1)


def test_the_conditional_fill_helper_writes_only_what_is_still_empty(tmp_path):
    from scripts.db import fill_job_fields_if_empty
    db, (short, long_, placeholder) = make_db(
        tmp_path,
        {"description": "tiny", "company": "Kept Co"},
        {"description": LONG_DESC},
        {"title": "Importing..."},
    )
    fields = {"title": "T", "company": "C", "location": "L", "salary": "never"}

    assert fill_job_fields_if_empty(db, short, description="NEW", fields=fields, min_description_chars=50) is True
    assert fill_job_fields_if_empty(db, long_, description="NEW", fields=fields, min_description_chars=50) is False
    assert fill_job_fields_if_empty(db, placeholder, description="NEW", fields=fields, min_description_chars=50) is True

    row = get_row(db, short)
    assert (row["description"], row["title"], row["company"], row["location"], row["salary"]) == ("NEW", "T", "Kept Co", "L", "")
    assert get_row(db, long_)["description"] == LONG_DESC
    assert get_row(db, long_)["title"] == ""
    assert get_row(db, placeholder)["title"] == "T"


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
    db, _ids = make_db(tmp_path, *({"url": u} for u in [*good, *bad]))

    picked = lb.find_pending(db, 100)

    assert sorted(p["url"] for p in picked) == sorted(good)
    assert lb.count_pending(db) == 3


def test_jobs_with_enough_description_rejected_jobs_and_old_jobs_are_skipped(tmp_path):
    db, ids = make_db(
        tmp_path,
        {"description": LONG_DESC},
        {"status": "rejected"},
        {"status": "archived"},
        {"date_found": today(lb.MAX_AGE_DAYS + 5)},
        {"description": "   short   "},
        {"date_found": ""},
        {"status": "approved"},
    )

    picked = [p["id"] for p in lb.find_pending(db, 100)]

    assert picked == [ids[6], ids[5], ids[4]]  # newest first
    assert lb.count_pending(db) == 3


def test_the_limit_caps_the_attempts_and_remaining_counts_the_rest(tmp_path):
    db, _ = make_db(tmp_path, {}, {}, {}, {}, {})

    res = run(db, ScriptedFetch(Resp()), limit=2)

    assert (res.attempted, res.filled, res.remaining) == (2, 2, 3)


def test_the_target_url_is_always_the_fixed_linkedin_guest_endpoint(tmp_path):
    db, _ids = make_db(
        tmp_path,
        {"url": "https://uk.linkedin.com/jobs/view/777/?trk=evil&redirect=https://evil.example"},
        {"url": "https://www.linkedin.com/jobs/view/888/"},
    )
    fetch = ScriptedFetch(Resp())

    run(db, fetch)

    assert sorted(fetch.urls) == [GUEST_PREFIX + "777", GUEST_PREFIX + "888"]
    for kwargs in fetch.kwargs:
        assert "User-Agent" in kwargs["headers"]
        assert kwargs["timeout"] > 0


# ── jobs that can never be filled are remembered, in memory only ────────────────────────────────

def test_a_404_job_is_not_fetched_again_on_the_next_run_but_a_throttled_job_is(tmp_path):
    db, _ = make_db(tmp_path, {}, {})
    # newest first: job 2 gets the 404, job 1 gets the 429
    run(db, ScriptedFetch(Resp(404), Resp(429)))

    again = ScriptedFetch(Resp(429))
    run(db, again)

    assert again.urls == [GUEST_PREFIX + "1000"]


def test_410_and_an_empty_parse_are_remembered_too(tmp_path):
    db, _ = make_db(tmp_path, {}, {})
    run(db, ScriptedFetch(Resp(410), Resp(200, text="<html></html>")))

    again = ScriptedFetch(Resp())
    run(db, again)

    assert again.urls == []


def test_remembered_jobs_expire_after_24_hours(tmp_path):
    db, _ = make_db(tmp_path, {})
    clock = Clock(1000.0)
    run(db, ScriptedFetch(Resp(404)), clock=clock)

    clock.t = 1000.0 + lb.NEGATIVE_CACHE_SECONDS - 1
    early = ScriptedFetch(Resp())
    run(db, early, clock=clock)
    clock.t = 1000.0 + lb.NEGATIVE_CACHE_SECONDS + 1
    late = ScriptedFetch(Resp())
    run(db, late, clock=clock)

    assert early.urls == []
    assert late.urls == [GUEST_PREFIX + "1000"]


def test_the_memory_is_per_database(tmp_path):
    db_a, _ = make_db(tmp_path, {}, name="a.db")
    db_b, _ = make_db(tmp_path, {}, name="b.db")
    run(db_a, ScriptedFetch(Resp(404)))

    other = ScriptedFetch(Resp())
    run(db_b, other)

    assert other.urls == [GUEST_PREFIX + "1000"]


def test_the_memory_is_capped_and_evicts_the_oldest(tmp_path, monkeypatch):
    monkeypatch.setattr(lb, "NEGATIVE_CACHE_MAX", 2)
    db, _ = make_db(tmp_path, {}, {}, {})  # processed newest first: 1002, 1001, 1000
    run(db, ScriptedFetch(Resp(404)))

    again = ScriptedFetch(Resp(429))
    run(db, again)

    assert again.urls == [GUEST_PREFIX + "1002"]  # the oldest entry was evicted


def test_remaining_excludes_remembered_jobs_and_they_do_not_starve_fresh_ones(tmp_path):
    db, _ = make_db(tmp_path, *({} for _ in range(6)))
    run(db, ScriptedFetch(Resp(404)), limit=3)  # remembers the newest three

    assert lb.count_pending(db, now=1000.0) == 3
    fresh = ScriptedFetch(Resp())
    res = run(db, fresh, limit=3)

    assert sorted(fresh.urls) == [GUEST_PREFIX + s for s in ("1000", "1001", "1002")]
    assert res.remaining == 0


# ── 200 outcomes and per-job failures ───────────────────────────────────────────────────────────

def test_an_empty_parsed_description_is_skipped_not_an_error(tmp_path):
    db, (job_id,) = make_db(tmp_path, {})

    res = run(db, ScriptedFetch(Resp(200, text="<html></html>")))

    assert (res.skipped, res.errors, res.throttled, res.filled) == (1, 0, 0, 0)
    assert get_row(db, job_id)["description"] == ""


def test_a_failure_while_handling_one_job_is_an_error_and_the_batch_continues(tmp_path, monkeypatch, capsys):
    import scripts.scrape_url as scrape
    db, _ = make_db(tmp_path, {"title": "SecretTitleXyz"}, {"title": "OtherTitleXyz"})
    monkeypatch.setattr(scrape, "_parse_linkedin_posting", lambda html: (_ for _ in ()).throw(ValueError("SecretTitleXyz")))

    res = run(db, ScriptedFetch(Resp()))

    assert (res.attempted, res.errors, res.filled, res.stopped_early) == (2, 2, 0, False)
    out = capsys.readouterr().out
    assert "[linkedin-backfill]" in out
    assert "ValueError" in out
    assert "SecretTitleXyz" not in out


def test_the_log_lines_never_contain_titles_companies_urls_or_descriptions(tmp_path, capsys):
    db, _ = make_db(
        tmp_path,
        {"title": "SecretTitleXyz", "company": "SecretCompanyXyz", "url": "https://www.linkedin.com/jobs/view/4242/"},
        {"title": "OtherTitleXyz", "company": "OtherCompanyXyz", "url": "https://www.linkedin.com/jobs/view/4343/"},
        {"title": "ThirdTitleXyz", "company": "ThirdCompanyXyz", "url": "https://www.linkedin.com/jobs/view/4444/"},
    )

    run(db, ScriptedFetch(Resp(), Resp(429), ConnectionError("boom https://www.linkedin.com/jobs/view/4444")))

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
    db, (job_id,) = make_db(tmp_path, {})
    pauses = Pauses()

    res = lb.backfill_linkedin_descriptions(db, sleep=pauses.sleep, uniform=pauses.uniform, now=Clock())

    assert used == [GUEST_PREFIX + "1000"]
    assert res.filled == 1
    assert get_row(db, job_id)["description"]


# ── discovery wiring ────────────────────────────────────────────────────────────────────────────

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
        (result(), 1, "1 new listing added"),
        (result(filled=12, remaining=8), 12,
         "12 new listings added, 12 LinkedIn descriptions filled, 8 LinkedIn descriptions still pending"),
        (result(filled=1), 0, "0 new listings added, 1 LinkedIn description filled"),
        (result(remaining=15), 2, "2 new listings added, 15 LinkedIn descriptions still pending"),
        (result(remaining=1), 2, "2 new listings added, 1 LinkedIn description still pending"),
        (result(skipped_cooling_down=True, remaining=0), 3, "3 new listings added"),
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
        "description": PARSED_DESC,
        "source": "linkedin",
    }
    assert _parse_linkedin_posting("<html></html>") == {"source": "linkedin"}
