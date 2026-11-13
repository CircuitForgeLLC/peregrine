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
def client(db_path, tmp_path, monkeypatch):
    monkeypatch.setattr("dev_api.DB_PATH", db_path)
    # No profile unless a test asks for one, so nothing here reads a real user.yaml.
    monkeypatch.setattr("dev_api._user_yaml_path", lambda: str(tmp_path / "no-profile" / "user.yaml"))
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


# ── Identity on the approved resume (peregrine#242) ──────────────────────────────────────────
# The optimizer's struct carries no name or contact info, so every export had a blank header.

@pytest.fixture()
def profile(tmp_path, monkeypatch):
    """A user.yaml for the request, in place of the repo-level or per-tenant config dir."""
    path = tmp_path / "user.yaml"
    path.write_text(
        "name: Pat Example\nemail: pat@example.test\nphone: '5551234567'\n"
        "linkedin: https://linkedin.test/in/pat\n"
    )
    monkeypatch.setattr("dev_api._user_yaml_path", lambda: path)
    return path


def test_approve_adds_the_profile_identity_to_the_saved_resume(client, db_path, profile):
    job_id = _job_id(db_path)
    struct = {"career_summary": "Summary text.", "skills": ["Python"]}

    resp = client.post(f"/api/jobs/{job_id}/resume_optimizer/approve", json={"preview_struct": struct})

    assert resp.status_code == 200
    first_line = resp.json()["optimized_resume"].splitlines()[0]
    assert "Pat Example" in first_line and "pat@example.test" in first_line
    con = sqlite3.connect(db_path)
    saved = con.execute("SELECT resume_final_struct FROM jobs WHERE id=?", (job_id,)).fetchone()[0]
    con.close()
    assert "Pat Example" in saved


def test_export_yaml_includes_identity_for_a_resume_approved_before_the_fix(client, db_path, profile):
    """Already-approved resumes have a stored struct with no identity. Exports fill it in from
    the profile instead of needing a re-approve."""
    import json
    job_id = _job_id(db_path)
    con = sqlite3.connect(db_path)
    con.execute("UPDATE jobs SET resume_final_struct=? WHERE id=?", (json.dumps({"career_summary": "Old approval."}), job_id))
    con.commit()
    con.close()

    resp = client.get(f"/api/jobs/{job_id}/resume_optimizer/export-yaml")

    assert resp.status_code == 200
    assert "name: Pat Example" in resp.text
    assert "(555) 123-4567" in resp.text


def test_export_pdf_has_the_name_and_contact_line(client, db_path, profile, tmp_path):
    import pdfplumber
    job_id = _job_id(db_path)
    client.post(f"/api/jobs/{job_id}/resume_optimizer/approve", json={"preview_struct": {"career_summary": "Summary text."}})

    resp = client.get(f"/api/jobs/{job_id}/resume_optimizer/export-pdf")

    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    out = tmp_path / "export.pdf"
    out.write_bytes(resp.content)
    with pdfplumber.open(out) as pdf:
        lines = pdf.pages[0].extract_text().splitlines()
    assert lines[0] == "Pat Example"
    assert "pat@example.test" in lines[1]


def test_a_value_already_on_the_resume_wins_over_the_profile(client, db_path, profile):
    job_id = _job_id(db_path)
    client.post(f"/api/jobs/{job_id}/resume_optimizer/approve", json={"preview_struct": {"career_summary": "S.", "name": "Patricia E."}})

    resp = client.get(f"/api/jobs/{job_id}/resume_optimizer/export-yaml")

    assert "name: Patricia E." in resp.text
    assert "Pat Example" not in resp.text


def test_review_preview_shows_the_identity_before_anything_is_approved(client, db_path, profile):
    """The review step is what the user reads and edits, so the header has to be there already."""
    import json

    from scripts.db import save_resume_draft
    job_id = _job_id(db_path)
    draft = {"sections": [], "rewritten_struct": {"career_summary": "Draft summary.", "skills": ["Python"]}}
    save_resume_draft(db_path=db_path, job_id=job_id, draft_json=json.dumps(draft))

    resp = client.post(f"/api/jobs/{job_id}/resume_optimizer/review", json={"decisions": {}})

    assert resp.status_code == 200
    body = resp.json()
    assert body["preview_struct"]["name"] == "Pat Example"
    assert body["preview_struct"]["phone"] == "(555) 123-4567"
    assert body["preview_text"].splitlines()[0].startswith("Pat Example")


def test_a_missing_profile_changes_nothing(client, db_path, tmp_path, monkeypatch):
    monkeypatch.setattr("dev_api._user_yaml_path", lambda: tmp_path / "does-not-exist.yaml")
    job_id = _job_id(db_path)

    resp = client.post(f"/api/jobs/{job_id}/resume_optimizer/approve", json={"preview_struct": {"career_summary": "Summary text."}})

    assert resp.status_code == 200
    assert "Summary text" in resp.json()["optimized_resume"]
