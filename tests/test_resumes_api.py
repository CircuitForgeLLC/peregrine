"""Tests for /api/resumes/* endpoints."""
import io
import sqlite3
from unittest.mock import patch

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


import json as _json


def test_score_endpoint_queues_task_and_status_round_trips(client):
    c, db = client
    struct = dict(name="Jane Doe", career_summary="A developer.",
                  experience=[], education=[], skills=[], achievements=[])
    resume = c.post("/api/resumes", json=dict(
        name="Test Resume", text="Jane Doe\nSUMMARY\nA developer.",
        struct_json=_json.dumps(struct),
    )).json()

    resume_id = resume["id"]
    resp = c.post("/api/resumes/" + str(resume_id) + "/score")
    assert resp.status_code == 200
    assert "task_id" in resp.json()

    status_resp = c.get("/api/resumes/" + str(resume_id) + "/score/task")
    assert status_resp.status_code == 200
    assert status_resp.json()["status"] in ("queued", "running", "completed")


def test_get_score_before_scoring_returns_null(client):
    c, db = client
    resume = c.post("/api/resumes", json=dict(name="Unscored", text="x")).json()
    resp = c.get("/api/resumes/" + str(resume["id"]) + "/score")
    assert resp.status_code == 200
    assert resp.json() == dict(score=None, scored_at=None)


def test_apply_suggestion_updates_resume_text(client):
    c, db = client
    struct = {"career_summary": "A developer.", "experience": [], "education": [],
              "skills": ["Python"], "achievements": []}
    resume = c.post("/api/resumes", json={
        "name": "Test", "text": "A developer.", "struct_json": _json.dumps(struct),
    }).json()
    resp = c.post(
        f"/api/resumes/{resume['id']}/score/apply-suggestion",
        json={"suggestion": {"section": "skills", "before": "Python", "after": "Python 3"}},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert "Python 3" in _json.loads(body["resume"]["struct_json"])["skills"]


def test_apply_suggestion_rejects_hallucinated_content(client):
    c, db = client
    struct = {"career_summary": "A developer.", "experience": [
        {"title": "Developer", "company": "Acme", "bullets": ["Did work"]}
    ], "education": [], "skills": [], "achievements": []}
    resume = c.post("/api/resumes", json={
        "name": "Test", "text": "A developer.", "struct_json": _json.dumps(struct),
    }).json()
    resp = c.post(
        f"/api/resumes/{resume['id']}/score/apply-suggestion",
        json={"suggestion": {"section": "experience", "target": "Globex Inc|CTO",
                              "before": "Did work", "after": "Served as CTO of Globex Inc"}},
    )
    assert resp.status_code == 409


def test_apply_suggestion_404_when_resume_missing(client):
    c, db = client
    resp = c.post(
        "/api/resumes/99999/score/apply-suggestion",
        json={"suggestion": {"section": "skills", "before": "Python", "after": "Python 3"}},
    )
    assert resp.status_code == 404


def test_apply_suggestion_409_when_no_struct_json(client):
    c, db = client
    resume = c.post("/api/resumes", json={"name": "NoStruct", "text": "plain text only"}).json()
    resp = c.post(
        f"/api/resumes/{resume['id']}/score/apply-suggestion",
        json={"suggestion": {"section": "skills", "before": "Python", "after": "Python 3"}},
    )
    assert resp.status_code == 409


def test_score_persists_struct_json_when_missing_and_unblocks_apply(client):
    from pathlib import Path as _Path

    from scripts.task_runner import _run_task
    c, db = client
    resume_text = 'Jane Doe\njane@example.com\n\nExperience\nSoftware Engineer | Acme Corp\nJan 2020 - Dec 2023\n\u2022 Built things\n\nSkills\nPython, SQL'
    resume = c.post('/api/resumes', json={'name': 'No Struct', 'text': resume_text}).json()
    assert resume['struct_json'] is None
    fake_llm_json = '{"overall_score": 6, "summary": "ok", "strengths": [], "improvements": [], "suggestions": [{"id": "sugg-1", "section": "skills", "before": "Python", "after": "Python 3", "rationale": "x"}]}'
    with patch('scripts.resume_scorer.LLMRouter') as mock_router_cls:
        mock_router_cls.return_value.complete.return_value = fake_llm_json
        _run_task(_Path(db), 1, 'resume_score', 0, params=_json.dumps(dict(resume_id=resume['id'])))
    updated = c.get('/api/resumes/' + str(resume['id'])).json()
    assert updated['struct_json'] is not None
    struct = _json.loads(updated['struct_json'])
    assert 'skills' in struct
    apply_resp = c.post('/api/resumes/' + str(resume['id']) + '/score/apply-suggestion', json={'suggestion': {'section': 'skills', 'before': 'Python', 'after': 'Python 3'}})
    assert apply_resp.status_code == 200


def test_apply_suggestion_422_when_before_text_does_not_match(client):
    c, db = client
    struct = {'career_summary': 'A developer.', 'experience': [], 'education': [], 'skills': ['Python'], 'achievements': []}
    resume = c.post('/api/resumes', json={'name': 'Test', 'text': 'A developer.', 'struct_json': _json.dumps(struct)}).json()
    resp = c.post('/api/resumes/' + str(resume['id']) + '/score/apply-suggestion', json={'suggestion': {'section': 'skills', 'before': 'text that does not exist', 'after': 'new text'}})
    assert resp.status_code == 422


def test_apply_suggestion_creates_backup_before_overwrite(client):
    c, db = client
    struct = {'career_summary': 'A developer.', 'experience': [], 'education': [], 'skills': ['Python'], 'achievements': []}
    resume = c.post('/api/resumes', json={'name': 'Backup Me', 'text': 'A developer.', 'struct_json': _json.dumps(struct)}).json()
    before_count = len(c.get('/api/resumes').json()['resumes'])
    resp = c.post('/api/resumes/' + str(resume['id']) + '/score/apply-suggestion', json={'suggestion': {'section': 'skills', 'before': 'Python', 'after': 'Python 3'}})
    assert resp.status_code == 200
    all_resumes = c.get('/api/resumes').json()['resumes']
    assert len(all_resumes) == before_count + 1
    backups = [r for r in all_resumes if r['source'] == 'pre-apply-backup']
    assert len(backups) == 1
    assert 'Backup Me' in backups[0]['name']
    backup_struct = _json.loads(backups[0]['struct_json'])
    assert backup_struct['skills'] == ['Python']
