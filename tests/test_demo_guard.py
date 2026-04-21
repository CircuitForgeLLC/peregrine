"""IS_DEMO write-block guard tests."""
import importlib
import os
import sqlite3

import pytest
from fastapi.testclient import TestClient

_SCHEMA = """
CREATE TABLE jobs (
    id INTEGER PRIMARY KEY, title TEXT, company TEXT, url TEXT,
    location TEXT, is_remote INTEGER DEFAULT 0, salary TEXT,
    match_score REAL, keyword_gaps TEXT, status TEXT DEFAULT 'pending',
    date_found TEXT, cover_letter TEXT, interview_date TEXT,
    rejection_stage TEXT, applied_at TEXT, phone_screen_at TEXT,
    interviewing_at TEXT, offer_at TEXT, hired_at TEXT,
    survey_at TEXT, date_posted TEXT, hired_feedback TEXT
);
CREATE TABLE background_tasks (
    id INTEGER PRIMARY KEY, task_type TEXT, job_id INTEGER,
    status TEXT DEFAULT 'queued', finished_at TEXT
);
"""


def _make_db(path: str) -> None:
    con = sqlite3.connect(path)
    con.executescript(_SCHEMA)
    con.execute(
        "INSERT INTO jobs (id, title, company, url, status) VALUES (1,'UX Designer','Spotify','https://ex.com/1','pending')"
    )
    con.execute(
        "INSERT INTO jobs (id, title, company, url, status) VALUES (2,'Designer','Figma','https://ex.com/2','hired')"
    )
    con.commit()
    con.close()


@pytest.fixture()
def demo_client(tmp_path, monkeypatch):
    db_path = str(tmp_path / "staging.db")
    _make_db(db_path)
    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.setenv("STAGING_DB", db_path)
    import dev_api
    importlib.reload(dev_api)
    return TestClient(dev_api.app)


@pytest.fixture()
def normal_client(tmp_path, monkeypatch):
    db_path = str(tmp_path / "staging.db")
    _make_db(db_path)
    monkeypatch.delenv("DEMO_MODE", raising=False)
    monkeypatch.setenv("STAGING_DB", db_path)
    import dev_api
    importlib.reload(dev_api)
    return TestClient(dev_api.app)


class TestDemoWriteBlock:
    def test_approve_blocked_in_demo(self, demo_client):
        r = demo_client.post("/api/jobs/1/approve")
        assert r.status_code == 403
        assert r.json()["detail"] == "demo-write-blocked"

    def test_reject_blocked_in_demo(self, demo_client):
        r = demo_client.post("/api/jobs/1/reject")
        assert r.status_code == 403
        assert r.json()["detail"] == "demo-write-blocked"

    def test_cover_letter_generate_blocked_in_demo(self, demo_client):
        r = demo_client.post("/api/jobs/1/cover_letter/generate")
        assert r.status_code == 403
        assert r.json()["detail"] == "demo-write-blocked"

    def test_hired_feedback_blocked_in_demo(self, demo_client):
        r = demo_client.post("/api/jobs/2/hired-feedback", json={"factors": [], "notes": ""})
        assert r.status_code == 403
        assert r.json()["detail"] == "demo-write-blocked"

    def test_approve_allowed_in_normal_mode(self, normal_client):
        r = normal_client.post("/api/jobs/1/approve")
        assert r.status_code != 403

    def test_config_reports_is_demo_true(self, demo_client):
        r = demo_client.get("/api/config/app")
        assert r.status_code == 200
        assert r.json()["isDemo"] is True
