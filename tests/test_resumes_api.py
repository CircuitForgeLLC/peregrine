"""Tests for /api/resumes/* endpoints."""
import io
import sqlite3

import pytest
from fastapi.testclient import TestClient

from scripts.db_migrate import migrate_db


@pytest.fixture
def client(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    migrate_db(db_path)
    monkeypatch.setenv("STAGING_DB", str(db_path))
    import dev_api
    monkeypatch.setattr(dev_api, "_request_db",
                        type("CV", (), {"get": lambda self: str(db_path), "set": lambda *a: None})())
    return TestClient(dev_api.app), db_path


def test_create_and_list(client):
    c, db = client
    resp = c.post("/api/resumes", json={"name": "Base", "text": "Resume text here"})
    assert resp.status_code == 200
    r = resp.json()
    assert r["name"] == "Base"
    assert r["word_count"] == 3

    resp2 = c.get("/api/resumes")
    assert len(resp2.json()["resumes"]) == 1


def test_get_single(client):
    c, db = client
    created = c.post("/api/resumes", json={"name": "Test", "text": "text"}).json()
    fetched = c.get(f"/api/resumes/{created['id']}").json()
    assert fetched["name"] == "Test"


def test_patch_resume(client):
    c, db = client
    created = c.post("/api/resumes", json={"name": "Old", "text": "old text"}).json()
    updated = c.patch(f"/api/resumes/{created['id']}", json={"name": "New"}).json()
    assert updated["name"] == "New"
    assert updated["text"] == "old text"


def test_delete_resume(client):
    c, db = client
    a = c.post("/api/resumes", json={"name": "A", "text": "text a"}).json()
    b = c.post("/api/resumes", json={"name": "B", "text": "text b"}).json()
    resp = c.delete(f"/api/resumes/{a['id']}")
    assert resp.status_code == 200
    assert len(c.get("/api/resumes").json()["resumes"]) == 1


def test_delete_only_resume_rejected(client):
    c, db = client
    r = c.post("/api/resumes", json={"name": "Only", "text": "text"}).json()
    resp = c.delete(f"/api/resumes/{r['id']}")
    assert resp.status_code == 409


def test_set_default(client):
    c, db = client
    a = c.post("/api/resumes", json={"name": "A", "text": "text a"}).json()
    b = c.post("/api/resumes", json={"name": "B", "text": "text b"}).json()
    c.post(f"/api/resumes/{a['id']}/set-default")
    c.post(f"/api/resumes/{b['id']}/set-default")
    resumes = {r["id"]: r for r in c.get("/api/resumes").json()["resumes"]}
    assert resumes[a["id"]]["is_default"] == 0
    assert resumes[b["id"]]["is_default"] == 1


def test_import_txt(client):
    c, db = client
    f = io.BytesIO(b"Software engineer with ten years experience building distributed systems.")
    resp = c.post("/api/resumes/import", files={"file": ("resume.txt", f, "text/plain")},
                  data={"name": "Imported"})
    assert resp.status_code == 200
    r = resp.json()
    assert r["source"] == "import"
    assert r["word_count"] > 0


def test_import_yaml(client):
    c, db = client
    yaml_content = b"""
career_summary: Experienced engineer.
experience:
  - title: Staff Engineer
    company: Acme
    start_date: 01/2020
    end_date: Present
    bullets:
      - Led platform redesign serving 2M users
skills:
  - Python
  - FastAPI
"""
    f = io.BytesIO(yaml_content)
    resp = c.post("/api/resumes/import", files={"file": ("resume.yaml", f, "application/x-yaml")})
    assert resp.status_code == 200
    r = resp.json()
    assert r["source"] == "import"
    assert r["struct_json"] is not None


def test_per_job_resume_endpoints(client):
    c, db = client
    conn = sqlite3.connect(db)
    conn.execute("INSERT INTO jobs (id, title, company, source) VALUES (1, 'Eng', 'Co', 'test')")
    conn.commit()
    conn.close()

    r = c.post("/api/resumes", json={"name": "Default", "text": "default text"}).json()
    c.post(f"/api/resumes/{r['id']}/set-default")

    result = c.get("/api/jobs/1/resume").json()
    assert result["id"] == r["id"]

    specific = c.post("/api/resumes", json={"name": "Specific", "text": "specific text"}).json()
    c.patch("/api/jobs/1/resume", json={"resume_id": specific["id"]})
    result2 = c.get("/api/jobs/1/resume").json()
    assert result2["id"] == specific["id"]
