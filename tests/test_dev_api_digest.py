"""Tests for digest queue API endpoints."""
import sqlite3
import os
import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def tmp_db(tmp_path):
    """Create minimal schema in a temp dir with one job_contacts row."""
    db_path = str(tmp_path / "staging.db")
    con = sqlite3.connect(db_path)
    con.executescript("""
        CREATE TABLE jobs (
            id INTEGER PRIMARY KEY,
            title TEXT, company TEXT, url TEXT UNIQUE, location TEXT,
            is_remote INTEGER DEFAULT 0, salary TEXT,
            match_score REAL, keyword_gaps TEXT, status TEXT DEFAULT 'pending',
            date_found TEXT, description TEXT, source TEXT
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
        CREATE TABLE digest_queue (
            id INTEGER PRIMARY KEY,
            job_contact_id INTEGER NOT NULL REFERENCES job_contacts(id),
            created_at TEXT DEFAULT (datetime('now')),
            UNIQUE(job_contact_id)
        );
        INSERT INTO jobs (id, title, company, url, status, source, date_found)
            VALUES (1, 'Engineer', 'Acme', 'https://acme.com/job/1', 'applied', 'test', '2026-03-19');
        INSERT INTO job_contacts (id, job_id, subject, received_at, stage_signal, body, from_addr)
            VALUES (
                10, 1, 'TechCrunch Jobs Weekly', '2026-03-19T10:00:00', 'digest',
                '<html><body>Apply at <a href="https://greenhouse.io/acme/jobs/456">Senior Engineer</a> or <a href="https://lever.co/globex/staff">Staff Designer</a>. Unsubscribe: https://unsubscribe.example.com/remove</body></html>',
                'digest@techcrunch.com'
            );
    """)
    con.close()
    return db_path


@pytest.fixture()
def client(tmp_db, monkeypatch):
    monkeypatch.setenv("STAGING_DB", tmp_db)
    import importlib
    import dev_api
    importlib.reload(dev_api)
    return TestClient(dev_api.app)


# ── GET /api/digest-queue ───────────────────────────────────────────────────

def test_digest_queue_list_empty(client):
    resp = client.get("/api/digest-queue")
    assert resp.status_code == 200
    assert resp.json() == []


def test_digest_queue_list_with_entry(client, tmp_db):
    con = sqlite3.connect(tmp_db)
    con.execute("INSERT INTO digest_queue (job_contact_id) VALUES (10)")
    con.commit()
    con.close()

    resp = client.get("/api/digest-queue")
    assert resp.status_code == 200
    entries = resp.json()
    assert len(entries) == 1
    assert entries[0]["job_contact_id"] == 10
    assert entries[0]["subject"] == "TechCrunch Jobs Weekly"
    assert entries[0]["from_addr"] == "digest@techcrunch.com"
    assert "body" in entries[0]
    assert "created_at" in entries[0]


# ── POST /api/digest-queue ──────────────────────────────────────────────────

def test_digest_queue_add(client, tmp_db):
    resp = client.post("/api/digest-queue", json={"job_contact_id": 10})
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["created"] is True

    con = sqlite3.connect(tmp_db)
    row = con.execute("SELECT * FROM digest_queue WHERE job_contact_id = 10").fetchone()
    con.close()
    assert row is not None


def test_digest_queue_add_duplicate(client):
    client.post("/api/digest-queue", json={"job_contact_id": 10})
    resp = client.post("/api/digest-queue", json={"job_contact_id": 10})
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["created"] is False


def test_digest_queue_add_missing_contact(client):
    resp = client.post("/api/digest-queue", json={"job_contact_id": 9999})
    assert resp.status_code == 404
