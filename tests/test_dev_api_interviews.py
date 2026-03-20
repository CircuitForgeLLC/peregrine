"""Tests for new dev-api.py endpoints: stage signals, email sync, signal dismiss."""
import sqlite3
import tempfile
import os
import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def tmp_db(tmp_path):
    """Create a minimal staging.db schema in a temp dir."""
    db_path = str(tmp_path / "staging.db")
    con = sqlite3.connect(db_path)
    con.executescript("""
        CREATE TABLE jobs (
            id INTEGER PRIMARY KEY,
            title TEXT, company TEXT, url TEXT, location TEXT,
            is_remote INTEGER DEFAULT 0, salary TEXT,
            match_score REAL, keyword_gaps TEXT, status TEXT,
            interview_date TEXT, rejection_stage TEXT,
            applied_at TEXT, phone_screen_at TEXT, interviewing_at TEXT,
            offer_at TEXT, hired_at TEXT, survey_at TEXT
        );
        CREATE TABLE job_contacts (
            id INTEGER PRIMARY KEY,
            job_id INTEGER,
            subject TEXT,
            received_at TEXT,
            stage_signal TEXT,
            suggestion_dismissed INTEGER DEFAULT 0,
            body TEXT,
            from_addr TEXT
        );
        CREATE TABLE background_tasks (
            id INTEGER PRIMARY KEY,
            task_type TEXT,
            job_id INTEGER,
            status TEXT DEFAULT 'queued',
            finished_at TEXT
        );
        INSERT INTO jobs (id, title, company, status) VALUES
            (1, 'Engineer', 'Acme', 'applied'),
            (2, 'Designer', 'Beta', 'phone_screen');
        INSERT INTO job_contacts (id, job_id, subject, received_at, stage_signal, suggestion_dismissed) VALUES
            (10, 1, 'Interview confirmed', '2026-03-19T10:00:00', 'interview_scheduled', 0),
            (11, 1, 'Old neutral', '2026-03-18T09:00:00', 'neutral', 0),
            (12, 2, 'Offer letter', '2026-03-19T11:00:00', 'offer_received', 0),
            (13, 1, 'Already dismissed', '2026-03-17T08:00:00', 'positive_response', 1);
    """)
    con.close()
    return db_path


@pytest.fixture()
def client(tmp_db, monkeypatch):
    monkeypatch.setenv("STAGING_DB", tmp_db)
    # Re-import after env var is set so DB_PATH picks it up
    import importlib
    import dev_api
    importlib.reload(dev_api)
    return TestClient(dev_api.app)


# ── GET /api/interviews — stage signals batched ────────────────────────────

def test_interviews_includes_stage_signals(client):
    resp = client.get("/api/interviews")
    assert resp.status_code == 200
    jobs = {j["id"]: j for j in resp.json()}

    # job 1 should have exactly 1 undismissed non-excluded signal
    assert "stage_signals" in jobs[1]
    signals = jobs[1]["stage_signals"]
    assert len(signals) == 1
    assert signals[0]["stage_signal"] == "interview_scheduled"
    assert signals[0]["subject"] == "Interview confirmed"
    assert signals[0]["id"] == 10
    assert "body" in signals[0]
    assert "from_addr" in signals[0]

    # neutral signal excluded
    signal_types = [s["stage_signal"] for s in signals]
    assert "neutral" not in signal_types

    # dismissed signal excluded
    signal_ids = [s["id"] for s in signals]
    assert 13 not in signal_ids

    # job 2 has an offer signal
    assert len(jobs[2]["stage_signals"]) == 1
    assert jobs[2]["stage_signals"][0]["stage_signal"] == "offer_received"


def test_interviews_empty_signals_for_job_without_contacts(client, tmp_db):
    con = sqlite3.connect(tmp_db)
    con.execute("INSERT INTO jobs (id, title, company, status) VALUES (3, 'NoContact', 'Corp', 'survey')")
    con.commit(); con.close()
    resp = client.get("/api/interviews")
    jobs = {j["id"]: j for j in resp.json()}
    assert jobs[3]["stage_signals"] == []


# ── POST /api/email/sync ───────────────────────────────────────────────────

def test_email_sync_returns_202(client):
    resp = client.post("/api/email/sync")
    assert resp.status_code == 202
    assert "task_id" in resp.json()


def test_email_sync_inserts_background_task(client, tmp_db):
    client.post("/api/email/sync")
    con = sqlite3.connect(tmp_db)
    row = con.execute(
        "SELECT task_type, job_id, status FROM background_tasks WHERE task_type='email_sync'"
    ).fetchone()
    con.close()
    assert row is not None
    assert row[0] == "email_sync"
    assert row[1] == 0   # sentinel
    assert row[2] == "queued"


# ── GET /api/email/sync/status ─────────────────────────────────────────────

def test_email_sync_status_idle_when_no_tasks(client):
    resp = client.get("/api/email/sync/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "idle"
    assert body["last_completed_at"] is None


def test_email_sync_status_reflects_latest_task(client, tmp_db):
    con = sqlite3.connect(tmp_db)
    con.execute(
        "INSERT INTO background_tasks (task_type, job_id, status, finished_at) VALUES "
        "('email_sync', 0, 'completed', '2026-03-19T12:00:00')"
    )
    con.commit(); con.close()
    resp = client.get("/api/email/sync/status")
    body = resp.json()
    assert body["status"] == "completed"
    assert body["last_completed_at"] == "2026-03-19T12:00:00"


# ── POST /api/stage-signals/{id}/dismiss ──────────────────────────────────

def test_dismiss_signal_sets_flag(client, tmp_db):
    resp = client.post("/api/stage-signals/10/dismiss")
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}
    con = sqlite3.connect(tmp_db)
    row = con.execute(
        "SELECT suggestion_dismissed FROM job_contacts WHERE id = 10"
    ).fetchone()
    con.close()
    assert row[0] == 1


def test_dismiss_signal_404_for_missing_id(client):
    resp = client.post("/api/stage-signals/9999/dismiss")
    assert resp.status_code == 404


# ── Body/from_addr in signal response ─────────────────────────────────────

def test_interviews_signal_includes_body_and_from_addr(client):
    resp = client.get("/api/interviews")
    assert resp.status_code == 200
    jobs = {j["id"]: j for j in resp.json()}
    sig = jobs[1]["stage_signals"][0]
    # Fields must exist (may be None when DB column is NULL)
    assert "body" in sig
    assert "from_addr" in sig


# ── POST /api/stage-signals/{id}/reclassify ────────────────────────────────

def test_reclassify_signal_updates_label(client, tmp_db):
    resp = client.post("/api/stage-signals/10/reclassify",
                       json={"stage_signal": "positive_response"})
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}
    con = sqlite3.connect(tmp_db)
    row = con.execute(
        "SELECT stage_signal FROM job_contacts WHERE id = 10"
    ).fetchone()
    con.close()
    assert row[0] == "positive_response"


def test_reclassify_signal_invalid_label(client):
    resp = client.post("/api/stage-signals/10/reclassify",
                       json={"stage_signal": "not_a_real_label"})
    assert resp.status_code == 400


def test_reclassify_signal_404_for_missing_id(client):
    resp = client.post("/api/stage-signals/9999/reclassify",
                       json={"stage_signal": "neutral"})
    assert resp.status_code == 404
