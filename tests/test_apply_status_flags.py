"""Apply list: a letter and a tailored resume are separate statuses (peregrine#256).

The list used to expose only has_cover_letter, drawn as a green check, so a job with just a draft
letter looked finished and the tailored resume had no status at all. has_optimized_resume is true
only once the resume has been approved, not while a review draft is waiting.
"""
import json
import sqlite3

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def db_path(tmp_path):
    from scripts.db import insert_job
    from scripts.db_migrate import migrate_db

    path = tmp_path / "staging.db"
    migrate_db(path)
    insert_job(path, {
        "title": "Member Services", "company": "Acme", "url": "https://example.test/job/1",
        "source": "manual", "location": "Remote", "is_remote": False,
        "salary": "", "description": "Greet members.", "date_found": "2026-11-20",
    })
    con = sqlite3.connect(path)
    con.execute("UPDATE jobs SET status = 'approved'")
    con.commit()
    con.close()
    return path


@pytest.fixture()
def client(db_path, monkeypatch):
    monkeypatch.setattr("dev_api.DB_PATH", db_path)
    from dev_api import app
    return TestClient(app)


def _job_id(db_path) -> int:
    con = sqlite3.connect(db_path)
    row = con.execute("SELECT id FROM jobs LIMIT 1").fetchone()
    con.close()
    return row[0]


def _set(db_path, **columns):
    con = sqlite3.connect(db_path)
    sets = ", ".join(f"{name} = ?" for name in columns)
    con.execute(f"UPDATE jobs SET {sets}", tuple(columns.values()))
    con.commit()
    con.close()


def _listed(client):
    rows = client.get("/api/jobs?status=approved&limit=10").json()
    assert len(rows) == 1
    return rows[0]


def test_a_new_job_has_neither_status(client):
    job = _listed(client)

    assert job["has_cover_letter"] is False
    assert job["has_optimized_resume"] is False


def test_a_generated_letter_does_not_mark_the_resume_as_done(client, db_path):
    _set(db_path, cover_letter="Dear team, ...")

    job = _listed(client)

    assert job["has_cover_letter"] is True
    assert job["has_optimized_resume"] is False


def test_an_approved_resume_does_not_mark_the_letter_as_done(client, db_path):
    _set(db_path, optimized_resume="Tailored resume text")

    job = _listed(client)

    assert job["has_cover_letter"] is False
    assert job["has_optimized_resume"] is True


def test_both_can_be_true_together(client, db_path):
    _set(db_path, cover_letter="Dear team", optimized_resume="Tailored resume text")

    job = _listed(client)

    assert job["has_cover_letter"] is True and job["has_optimized_resume"] is True


def test_a_review_draft_waiting_is_not_an_approved_resume(client, db_path):
    _set(db_path, resume_draft_json=json.dumps({"summary": "draft"}))

    assert _listed(client)["has_optimized_resume"] is False


def test_a_gap_report_alone_is_not_an_approved_resume(client, db_path):
    _set(db_path, ats_gap_report=json.dumps([{"term": "scheduling"}]))

    assert _listed(client)["has_optimized_resume"] is False


def test_the_list_does_not_carry_the_resume_or_letter_text(client, db_path):
    _set(db_path, cover_letter="SECRET LETTER", optimized_resume="SECRET RESUME")

    job = _listed(client)

    assert "cover_letter" not in job and "optimized_resume" not in job
    assert "SECRET" not in json.dumps(job)


def test_the_single_job_endpoint_reports_both_statuses(client, db_path):
    job_id = _job_id(db_path)
    _set(db_path, cover_letter="Dear team", optimized_resume="Tailored resume text")

    body = client.get(f"/api/jobs/{job_id}").json()

    assert body["has_cover_letter"] is True
    assert body["has_optimized_resume"] is True
    assert "optimized_resume" not in body


# ── Re-running the gap analysis must not wipe an approved resume ────────────────────────────────

def test_saving_only_a_gap_report_keeps_the_approved_resume(db_path):
    """task_runner saves a gap report with no resume text. That used to write NULL over the
    approved resume, so the status flipped back and the next approval had nothing to archive."""
    from scripts.db import get_optimized_resume, save_optimized_resume

    job_id = _job_id(db_path)
    save_optimized_resume(db_path, job_id=job_id, text="Approved resume text", gap_report="[]")

    save_optimized_resume(db_path, job_id=job_id, text="", gap_report='[{"term": "new"}]')

    saved = get_optimized_resume(db_path, job_id=job_id)
    assert saved["optimized_resume"] == "Approved resume text"
    assert saved["ats_gap_report"] == '[{"term": "new"}]'


def test_a_gap_rerun_then_a_new_approval_still_archives_the_previous_resume(db_path):
    from scripts.db import finalize_resume, get_resume_archive, save_optimized_resume

    job_id = _job_id(db_path)
    finalize_resume(db_path, job_id=job_id, final_text="First approved version")
    save_optimized_resume(db_path, job_id=job_id, text="", gap_report='[{"term": "x"}]')

    finalize_resume(db_path, job_id=job_id, final_text="Second approved version")

    archive = get_resume_archive(db_path, job_id=job_id)
    assert [entry["text"] for entry in archive] == ["First approved version"]


def test_the_gap_report_can_still_be_set_before_any_resume_exists(db_path):
    from scripts.db import get_optimized_resume, save_optimized_resume

    job_id = _job_id(db_path)
    save_optimized_resume(db_path, job_id=job_id, text="", gap_report='[{"term": "a"}]')

    saved = get_optimized_resume(db_path, job_id=job_id)
    assert saved["optimized_resume"] == ""
    assert saved["ats_gap_report"] == '[{"term": "a"}]'
