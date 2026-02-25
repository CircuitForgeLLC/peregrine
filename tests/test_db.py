import pytest
import sqlite3
from pathlib import Path
from unittest.mock import patch


def test_init_db_creates_jobs_table(tmp_path):
    """init_db creates a jobs table with correct schema."""
    from scripts.db import init_db
    db_path = tmp_path / "test.db"
    init_db(db_path)
    conn = sqlite3.connect(db_path)
    cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='jobs'")
    assert cursor.fetchone() is not None
    conn.close()


def test_insert_job_returns_id(tmp_path):
    """insert_job inserts a row and returns its id."""
    from scripts.db import init_db, insert_job
    db_path = tmp_path / "test.db"
    init_db(db_path)
    job = {
        "title": "CSM", "company": "Acme", "url": "https://example.com/1",
        "source": "linkedin", "location": "Remote", "is_remote": True,
        "salary": "$100k", "description": "Great role", "date_found": "2026-02-20",
    }
    row_id = insert_job(db_path, job)
    assert isinstance(row_id, int)
    assert row_id > 0


def test_insert_job_skips_duplicate_url(tmp_path):
    """insert_job returns None if URL already exists."""
    from scripts.db import init_db, insert_job
    db_path = tmp_path / "test.db"
    init_db(db_path)
    job = {"title": "CSM", "company": "Acme", "url": "https://example.com/1",
           "source": "linkedin", "location": "Remote", "is_remote": True,
           "salary": "", "description": "", "date_found": "2026-02-20"}
    insert_job(db_path, job)
    result = insert_job(db_path, job)
    assert result is None


def test_get_jobs_by_status(tmp_path):
    """get_jobs_by_status returns only jobs with matching status."""
    from scripts.db import init_db, insert_job, get_jobs_by_status, update_job_status
    db_path = tmp_path / "test.db"
    init_db(db_path)
    job = {"title": "CSM", "company": "Acme", "url": "https://example.com/1",
           "source": "linkedin", "location": "Remote", "is_remote": True,
           "salary": "", "description": "", "date_found": "2026-02-20"}
    row_id = insert_job(db_path, job)
    update_job_status(db_path, [row_id], "approved")
    approved = get_jobs_by_status(db_path, "approved")
    pending = get_jobs_by_status(db_path, "pending")
    assert len(approved) == 1
    assert len(pending) == 0


def test_update_job_status_batch(tmp_path):
    """update_job_status updates multiple rows at once."""
    from scripts.db import init_db, insert_job, update_job_status, get_jobs_by_status
    db_path = tmp_path / "test.db"
    init_db(db_path)
    ids = []
    for i in range(3):
        job = {"title": f"Job {i}", "company": "Co", "url": f"https://example.com/{i}",
               "source": "indeed", "location": "Remote", "is_remote": True,
               "salary": "", "description": "", "date_found": "2026-02-20"}
        ids.append(insert_job(db_path, job))
    update_job_status(db_path, ids, "rejected")
    assert len(get_jobs_by_status(db_path, "rejected")) == 3


def test_migrate_db_adds_columns_to_existing_db(tmp_path):
    """_migrate_db adds cover_letter and applied_at to a db created without them."""
    import sqlite3
    from scripts.db import _migrate_db
    db_path = tmp_path / "legacy.db"
    # Create old-style table without the new columns
    conn = sqlite3.connect(db_path)
    conn.execute("""CREATE TABLE jobs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT, company TEXT, url TEXT UNIQUE, status TEXT DEFAULT 'pending'
    )""")
    conn.commit()
    conn.close()
    _migrate_db(db_path)
    conn = sqlite3.connect(db_path)
    cols = {row[1] for row in conn.execute("PRAGMA table_info(jobs)").fetchall()}
    conn.close()
    assert "cover_letter" in cols
    assert "applied_at" in cols


def test_update_cover_letter(tmp_path):
    """update_cover_letter persists text to the DB."""
    from scripts.db import init_db, insert_job, update_cover_letter, get_jobs_by_status
    db_path = tmp_path / "test.db"
    init_db(db_path)
    job_id = insert_job(db_path, {
        "title": "CSM", "company": "Acme", "url": "https://ex.com/1",
        "source": "linkedin", "location": "Remote", "is_remote": True,
        "salary": "", "description": "", "date_found": "2026-02-20",
    })
    update_cover_letter(db_path, job_id, "Dear Hiring Manager,\nGreat role!")
    rows = get_jobs_by_status(db_path, "pending")
    assert rows[0]["cover_letter"] == "Dear Hiring Manager,\nGreat role!"


def test_mark_applied_sets_status_and_date(tmp_path):
    """mark_applied sets status='applied' and populates applied_at."""
    from scripts.db import init_db, insert_job, mark_applied, get_jobs_by_status
    db_path = tmp_path / "test.db"
    init_db(db_path)
    job_id = insert_job(db_path, {
        "title": "CSM", "company": "Acme", "url": "https://ex.com/1",
        "source": "linkedin", "location": "Remote", "is_remote": True,
        "salary": "", "description": "", "date_found": "2026-02-20",
    })
    mark_applied(db_path, [job_id])
    applied = get_jobs_by_status(db_path, "applied")
    assert len(applied) == 1
    assert applied[0]["status"] == "applied"
    assert applied[0]["applied_at"] is not None


# ── background_tasks tests ────────────────────────────────────────────────────

def test_init_db_creates_background_tasks_table(tmp_path):
    """init_db creates a background_tasks table."""
    from scripts.db import init_db
    db_path = tmp_path / "test.db"
    init_db(db_path)
    import sqlite3
    conn = sqlite3.connect(db_path)
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='background_tasks'"
    )
    assert cur.fetchone() is not None
    conn.close()


def test_insert_task_returns_id_and_true(tmp_path):
    """insert_task returns (task_id, True) for a new task."""
    from scripts.db import init_db, insert_job, insert_task
    db_path = tmp_path / "test.db"
    init_db(db_path)
    job_id = insert_job(db_path, {
        "title": "CSM", "company": "Acme", "url": "https://ex.com/1",
        "source": "linkedin", "location": "Remote", "is_remote": True,
        "salary": "", "description": "", "date_found": "2026-02-20",
    })
    task_id, is_new = insert_task(db_path, "cover_letter", job_id)
    assert isinstance(task_id, int) and task_id > 0
    assert is_new is True


def test_insert_task_deduplicates_active_task(tmp_path):
    """insert_task returns (existing_id, False) if a queued/running task already exists."""
    from scripts.db import init_db, insert_job, insert_task
    db_path = tmp_path / "test.db"
    init_db(db_path)
    job_id = insert_job(db_path, {
        "title": "CSM", "company": "Acme", "url": "https://ex.com/1",
        "source": "linkedin", "location": "Remote", "is_remote": True,
        "salary": "", "description": "", "date_found": "2026-02-20",
    })
    first_id, _ = insert_task(db_path, "cover_letter", job_id)
    second_id, is_new = insert_task(db_path, "cover_letter", job_id)
    assert second_id == first_id
    assert is_new is False


def test_insert_task_allows_different_types_same_job(tmp_path):
    """insert_task allows cover_letter and company_research for the same job concurrently."""
    from scripts.db import init_db, insert_job, insert_task
    db_path = tmp_path / "test.db"
    init_db(db_path)
    job_id = insert_job(db_path, {
        "title": "CSM", "company": "Acme", "url": "https://ex.com/1",
        "source": "linkedin", "location": "Remote", "is_remote": True,
        "salary": "", "description": "", "date_found": "2026-02-20",
    })
    _, cl_new = insert_task(db_path, "cover_letter", job_id)
    _, res_new = insert_task(db_path, "company_research", job_id)
    assert cl_new is True
    assert res_new is True


def test_update_task_status_running(tmp_path):
    """update_task_status('running') sets started_at."""
    from scripts.db import init_db, insert_job, insert_task, update_task_status
    import sqlite3
    db_path = tmp_path / "test.db"
    init_db(db_path)
    job_id = insert_job(db_path, {
        "title": "CSM", "company": "Acme", "url": "https://ex.com/1",
        "source": "linkedin", "location": "Remote", "is_remote": True,
        "salary": "", "description": "", "date_found": "2026-02-20",
    })
    task_id, _ = insert_task(db_path, "cover_letter", job_id)
    update_task_status(db_path, task_id, "running")
    conn = sqlite3.connect(db_path)
    row = conn.execute("SELECT status, started_at FROM background_tasks WHERE id=?", (task_id,)).fetchone()
    conn.close()
    assert row[0] == "running"
    assert row[1] is not None


def test_update_task_status_completed(tmp_path):
    """update_task_status('completed') sets finished_at."""
    from scripts.db import init_db, insert_job, insert_task, update_task_status
    import sqlite3
    db_path = tmp_path / "test.db"
    init_db(db_path)
    job_id = insert_job(db_path, {
        "title": "CSM", "company": "Acme", "url": "https://ex.com/1",
        "source": "linkedin", "location": "Remote", "is_remote": True,
        "salary": "", "description": "", "date_found": "2026-02-20",
    })
    task_id, _ = insert_task(db_path, "cover_letter", job_id)
    update_task_status(db_path, task_id, "completed")
    conn = sqlite3.connect(db_path)
    row = conn.execute("SELECT status, finished_at FROM background_tasks WHERE id=?", (task_id,)).fetchone()
    conn.close()
    assert row[0] == "completed"
    assert row[1] is not None


def test_update_task_status_failed_stores_error(tmp_path):
    """update_task_status('failed') stores error message and sets finished_at."""
    from scripts.db import init_db, insert_job, insert_task, update_task_status
    import sqlite3
    db_path = tmp_path / "test.db"
    init_db(db_path)
    job_id = insert_job(db_path, {
        "title": "CSM", "company": "Acme", "url": "https://ex.com/1",
        "source": "linkedin", "location": "Remote", "is_remote": True,
        "salary": "", "description": "", "date_found": "2026-02-20",
    })
    task_id, _ = insert_task(db_path, "cover_letter", job_id)
    update_task_status(db_path, task_id, "failed", error="LLM timeout")
    conn = sqlite3.connect(db_path)
    row = conn.execute("SELECT status, error, finished_at FROM background_tasks WHERE id=?", (task_id,)).fetchone()
    conn.close()
    assert row[0] == "failed"
    assert row[1] == "LLM timeout"
    assert row[2] is not None


def test_get_active_tasks_returns_only_active(tmp_path):
    """get_active_tasks returns only queued/running tasks with job info joined."""
    from scripts.db import init_db, insert_job, insert_task, update_task_status, get_active_tasks
    db_path = tmp_path / "test.db"
    init_db(db_path)
    job_id = insert_job(db_path, {
        "title": "CSM", "company": "Acme", "url": "https://ex.com/1",
        "source": "linkedin", "location": "Remote", "is_remote": True,
        "salary": "", "description": "", "date_found": "2026-02-20",
    })
    active_id, _ = insert_task(db_path, "cover_letter", job_id)
    done_id, _ = insert_task(db_path, "company_research", job_id)
    update_task_status(db_path, done_id, "completed")

    tasks = get_active_tasks(db_path)
    assert len(tasks) == 1
    assert tasks[0]["id"] == active_id
    assert tasks[0]["company"] == "Acme"
    assert tasks[0]["title"] == "CSM"


def test_get_task_for_job_returns_latest(tmp_path):
    """get_task_for_job returns the most recent task for the given type+job."""
    from scripts.db import init_db, insert_job, insert_task, update_task_status, get_task_for_job
    db_path = tmp_path / "test.db"
    init_db(db_path)
    job_id = insert_job(db_path, {
        "title": "CSM", "company": "Acme", "url": "https://ex.com/1",
        "source": "linkedin", "location": "Remote", "is_remote": True,
        "salary": "", "description": "", "date_found": "2026-02-20",
    })
    first_id, _ = insert_task(db_path, "cover_letter", job_id)
    update_task_status(db_path, first_id, "completed")
    second_id, _ = insert_task(db_path, "cover_letter", job_id)  # allowed since first is done

    task = get_task_for_job(db_path, "cover_letter", job_id)
    assert task is not None
    assert task["id"] == second_id


def test_get_task_for_job_returns_none_when_absent(tmp_path):
    """get_task_for_job returns None when no task exists for that job+type."""
    from scripts.db import init_db, insert_job, get_task_for_job
    db_path = tmp_path / "test.db"
    init_db(db_path)
    job_id = insert_job(db_path, {
        "title": "CSM", "company": "Acme", "url": "https://ex.com/1",
        "source": "linkedin", "location": "Remote", "is_remote": True,
        "salary": "", "description": "", "date_found": "2026-02-20",
    })
    assert get_task_for_job(db_path, "cover_letter", job_id) is None


# ── company_research new-column tests ─────────────────────────────────────────

def test_company_research_has_new_columns(tmp_path):
    """init_db creates company_research with the four extended columns."""
    from scripts.db import init_db
    db = tmp_path / "test.db"
    init_db(db)
    conn = sqlite3.connect(db)
    cols = [r[1] for r in conn.execute("PRAGMA table_info(company_research)").fetchall()]
    conn.close()
    assert "tech_brief" in cols
    assert "funding_brief" in cols
    assert "competitors_brief" in cols
    assert "red_flags" in cols

def test_save_and_get_research_new_fields(tmp_path):
    """save_research persists and get_research returns the four new brief fields."""
    from scripts.db import init_db, insert_job, save_research, get_research
    db = tmp_path / "test.db"
    init_db(db)
    job_id = insert_job(db, {
        "title": "TAM", "company": "Acme", "url": "https://ex.com/1",
        "source": "linkedin", "location": "Remote", "is_remote": True,
        "salary": "", "description": "", "date_found": "2026-02-21",
    })

    save_research(db, job_id=job_id,
                  company_brief="overview", ceo_brief="ceo",
                  talking_points="points", raw_output="raw",
                  tech_brief="tech stack", funding_brief="series B",
                  competitors_brief="vs competitors", red_flags="none")
    r = get_research(db, job_id=job_id)
    assert r["tech_brief"] == "tech stack"
    assert r["funding_brief"] == "series B"
    assert r["competitors_brief"] == "vs competitors"
    assert r["red_flags"] == "none"


# ── stage_signal / suggestion_dismissed tests ─────────────────────────────────

def test_stage_signal_columns_exist(tmp_path):
    """init_db creates stage_signal and suggestion_dismissed columns on job_contacts."""
    from scripts.db import init_db
    db_path = tmp_path / "test.db"
    init_db(db_path)
    conn = sqlite3.connect(db_path)
    cols = {row[1] for row in conn.execute("PRAGMA table_info(job_contacts)").fetchall()}
    conn.close()
    assert "stage_signal" in cols
    assert "suggestion_dismissed" in cols


def test_add_contact_with_stage_signal(tmp_path):
    """add_contact stores stage_signal when provided."""
    from scripts.db import init_db, insert_job, add_contact, get_contacts
    db_path = tmp_path / "test.db"
    init_db(db_path)
    job_id = insert_job(db_path, {
        "title": "CSM", "company": "Acme", "url": "https://ex.com/1",
        "source": "linkedin", "location": "Remote", "is_remote": True,
        "salary": "", "description": "", "date_found": "2026-02-21",
    })
    add_contact(db_path, job_id=job_id, direction="inbound",
                subject="Interview invite", stage_signal="interview_scheduled")
    contacts = get_contacts(db_path, job_id=job_id)
    assert contacts[0]["stage_signal"] == "interview_scheduled"


def test_get_unread_stage_signals(tmp_path):
    """get_unread_stage_signals returns only non-neutral, non-dismissed signals."""
    from scripts.db import (init_db, insert_job, add_contact,
                            get_unread_stage_signals, dismiss_stage_signal)
    db_path = tmp_path / "test.db"
    init_db(db_path)
    job_id = insert_job(db_path, {
        "title": "CSM", "company": "Acme", "url": "https://ex.com/1",
        "source": "linkedin", "location": "Remote", "is_remote": True,
        "salary": "", "description": "", "date_found": "2026-02-21",
    })
    c1 = add_contact(db_path, job_id=job_id, direction="inbound",
                     subject="Interview invite", stage_signal="interview_scheduled")
    add_contact(db_path, job_id=job_id, direction="inbound",
                subject="Auto-confirm", stage_signal="neutral")
    signals = get_unread_stage_signals(db_path, job_id)
    assert len(signals) == 1
    assert signals[0]["stage_signal"] == "interview_scheduled"

    dismiss_stage_signal(db_path, c1)
    assert get_unread_stage_signals(db_path, job_id) == []


def test_get_email_leads(tmp_path):
    """get_email_leads returns only source='email' pending jobs."""
    from scripts.db import init_db, insert_job, get_email_leads
    db_path = tmp_path / "test.db"
    init_db(db_path)
    insert_job(db_path, {
        "title": "CSM", "company": "Acme", "url": "https://ex.com/1",
        "source": "linkedin", "location": "Remote", "is_remote": True,
        "salary": "", "description": "", "date_found": "2026-02-21",
    })
    insert_job(db_path, {
        "title": "TAM", "company": "Wiz", "url": "email://wiz.com/abc123",
        "source": "email", "location": "", "is_remote": 0,
        "salary": "", "description": "Hi Alex…", "date_found": "2026-02-21",
    })
    leads = get_email_leads(db_path)
    assert len(leads) == 1
    assert leads[0]["company"] == "Wiz"
    assert leads[0]["source"] == "email"


def test_get_all_message_ids(tmp_path):
    """get_all_message_ids returns all message IDs across jobs."""
    from scripts.db import init_db, insert_job, add_contact, get_all_message_ids
    db_path = tmp_path / "test.db"
    init_db(db_path)
    job_id = insert_job(db_path, {
        "title": "CSM", "company": "Acme", "url": "https://ex.com/1",
        "source": "linkedin", "location": "Remote", "is_remote": True,
        "salary": "", "description": "", "date_found": "2026-02-21",
    })
    add_contact(db_path, job_id=job_id, message_id="<msg-001@acme.com>")
    add_contact(db_path, job_id=job_id, message_id="<msg-002@acme.com>")
    mids = get_all_message_ids(db_path)
    assert "<msg-001@acme.com>" in mids
    assert "<msg-002@acme.com>" in mids


# ── survey_responses tests ────────────────────────────────────────────────────

def test_survey_responses_table_created(tmp_path):
    """init_db creates survey_responses table."""
    from scripts.db import init_db
    db_path = tmp_path / "test.db"
    init_db(db_path)
    import sqlite3
    conn = sqlite3.connect(db_path)
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='survey_responses'"
    )
    assert cur.fetchone() is not None
    conn.close()


def test_survey_at_column_exists(tmp_path):
    """jobs table has survey_at column after init_db."""
    from scripts.db import init_db
    db_path = tmp_path / "test.db"
    init_db(db_path)
    import sqlite3
    conn = sqlite3.connect(db_path)
    cols = [row[1] for row in conn.execute("PRAGMA table_info(jobs)").fetchall()]
    assert "survey_at" in cols
    conn.close()


def test_insert_and_get_survey_response(tmp_path):
    """insert_survey_response inserts a row; get_survey_responses returns it."""
    from scripts.db import init_db, insert_job, insert_survey_response, get_survey_responses
    db_path = tmp_path / "test.db"
    init_db(db_path)
    job_id = insert_job(db_path, {
        "title": "CSM", "company": "Acme", "url": "https://ex.com/1",
        "source": "linkedin", "location": "Remote", "is_remote": True,
        "salary": "", "description": "", "date_found": "2026-02-23",
    })
    row_id = insert_survey_response(
        db_path, job_id=job_id, survey_name="Culture Fit",
        source="text_paste", raw_input="Q1: A B C", mode="quick",
        llm_output="1. B — collaborative", reported_score="82%",
    )
    assert isinstance(row_id, int)
    responses = get_survey_responses(db_path, job_id=job_id)
    assert len(responses) == 1
    assert responses[0]["survey_name"] == "Culture Fit"
    assert responses[0]["reported_score"] == "82%"


def test_get_interview_jobs_includes_survey(tmp_path):
    """get_interview_jobs returns survey-stage jobs."""
    from scripts.db import init_db, insert_job, update_job_status, get_interview_jobs
    db_path = tmp_path / "test.db"
    init_db(db_path)
    job_id = insert_job(db_path, {
        "title": "CSM", "company": "Acme", "url": "https://ex.com/2",
        "source": "linkedin", "location": "Remote", "is_remote": True,
        "salary": "", "description": "", "date_found": "2026-02-23",
    })
    update_job_status(db_path, [job_id], "survey")
    result = get_interview_jobs(db_path)
    assert any(j["id"] == job_id for j in result.get("survey", []))


def test_advance_to_survey_sets_survey_at(tmp_path):
    """advance_to_stage('survey') sets survey_at timestamp."""
    from scripts.db import init_db, insert_job, update_job_status, advance_to_stage, get_job_by_id
    db_path = tmp_path / "test.db"
    init_db(db_path)
    job_id = insert_job(db_path, {
        "title": "CSM", "company": "Acme", "url": "https://ex.com/3",
        "source": "linkedin", "location": "Remote", "is_remote": True,
        "salary": "", "description": "", "date_found": "2026-02-23",
    })
    update_job_status(db_path, [job_id], "applied")
    advance_to_stage(db_path, job_id=job_id, stage="survey")
    job = get_job_by_id(db_path, job_id=job_id)
    assert job["status"] == "survey"
    assert job["survey_at"] is not None


def test_update_job_fields(tmp_path):
    from scripts.db import init_db, insert_job, update_job_fields
    db = tmp_path / "test.db"
    init_db(db)
    job_id = insert_job(db, {
        "title": "Importing…", "company": "", "url": "https://example.com/job/1",
        "source": "manual", "location": "", "description": "", "date_found": "2026-02-24",
    })
    update_job_fields(db, job_id, {
        "title": "Customer Success Manager",
        "company": "Acme Corp",
        "location": "San Francisco, CA",
        "description": "Great role.",
        "salary": "$120k",
        "is_remote": 1,
    })
    import sqlite3
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    row = dict(conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone())
    conn.close()
    assert row["title"] == "Customer Success Manager"
    assert row["company"] == "Acme Corp"
    assert row["description"] == "Great role."
    assert row["is_remote"] == 1


def test_update_job_fields_ignores_unknown_columns(tmp_path):
    from scripts.db import init_db, insert_job, update_job_fields
    db = tmp_path / "test.db"
    init_db(db)
    job_id = insert_job(db, {
        "title": "Importing…", "company": "", "url": "https://example.com/job/2",
        "source": "manual", "location": "", "description": "", "date_found": "2026-02-24",
    })
    # Should not raise even with an unknown column
    update_job_fields(db, job_id, {"title": "Real Title", "nonexistent_col": "ignored"})
    import sqlite3
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    row = dict(conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone())
    conn.close()
    assert row["title"] == "Real Title"


def test_insert_task_with_params(tmp_path):
    from scripts.db import init_db, insert_task
    db = tmp_path / "t.db"
    init_db(db)
    import json
    params = json.dumps({"section": "career_summary"})
    task_id, is_new = insert_task(db, "wizard_generate", 0, params=params)
    assert is_new is True
    # Second call with same params = dedup
    task_id2, is_new2 = insert_task(db, "wizard_generate", 0, params=params)
    assert is_new2 is False
    assert task_id == task_id2
    # Different section = new task
    params2 = json.dumps({"section": "job_titles"})
    task_id3, is_new3 = insert_task(db, "wizard_generate", 0, params=params2)
    assert is_new3 is True
