"""Tests for POST /api/jobs/{id}/resume_optimizer/approve and the export
endpoints that depend on it (peregrine, found 2026-09-24 live in cloud):
this endpoint had zero test coverage, which is exactly how a missing
jobs.resume_final_struct column shipped and broke resume save/export for
every user until a tenant actually hit it in production."""
import sqlite3

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def db_path(tmp_path):
    """A real, fully-migrated staging.db -- runs the actual migration
    runner (scripts.db_migrate.migrate_db), the same code path _get_db()
    uses in production, so this test would have caught the missing-column
    bug directly rather than needing a hand-rolled schema fixture."""
    from scripts.db import insert_job
    from scripts.db_migrate import migrate_db

    path = tmp_path / "staging.db"
    migrate_db(path)
    insert_job(path, {
        "title": "Senior Engineer", "company": "Acme", "url": "https://example.test/job/1",
        "source": "manual", "location": "Remote", "is_remote": True,
        "salary": "", "description": "", "date_found": "2026-09-24",
    })
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


def test_approve_resume_saves_struct_and_returns_text(client, db_path):
    job_id = _job_id(db_path)
    struct = {
        "career_summary": "Experienced engineer.",
        "experience": [{"company": "Acme", "title": "Engineer", "bullets": ["Did things."]}],
        "skills": ["Python"],
    }
    resp = client.post(
        f"/api/jobs/{job_id}/resume_optimizer/approve",
        json={"preview_struct": struct},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["optimized_resume"]
    assert "Experienced engineer" in data["optimized_resume"] or "Did things" in data["optimized_resume"]

    con = sqlite3.connect(db_path)
    row = con.execute("SELECT resume_final_struct FROM jobs WHERE id=?", (job_id,)).fetchone()
    con.close()
    assert row[0] is not None
    assert "career_summary" in row[0]


def test_approve_resume_requires_preview_struct(client, db_path):
    job_id = _job_id(db_path)
    resp = client.post(f"/api/jobs/{job_id}/resume_optimizer/approve", json={})
    assert resp.status_code == 400


def test_export_yaml_after_approve_returns_the_saved_struct(client, db_path):
    job_id = _job_id(db_path)
    struct = {"career_summary": "Summary text.", "skills": ["Python", "SQL"]}
    client.post(f"/api/jobs/{job_id}/resume_optimizer/approve", json={"preview_struct": struct})

    resp = client.get(f"/api/jobs/{job_id}/resume_optimizer/export-yaml")
    assert resp.status_code == 200
    assert "Summary text" in resp.text
    assert "Python" in resp.text


def test_export_yaml_before_approve_returns_404(client, db_path):
    job_id = _job_id(db_path)
    resp = client.get(f"/api/jobs/{job_id}/resume_optimizer/export-yaml")
    assert resp.status_code == 404
