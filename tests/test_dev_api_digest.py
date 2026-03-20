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


# ── POST /api/digest-queue/{id}/extract-links ───────────────────────────────

def _add_digest_entry(tmp_db, contact_id=10):
    """Helper: insert a digest_queue row and return its id."""
    con = sqlite3.connect(tmp_db)
    cur = con.execute("INSERT INTO digest_queue (job_contact_id) VALUES (?)", (contact_id,))
    entry_id = cur.lastrowid
    con.commit()
    con.close()
    return entry_id


def test_digest_extract_links(client, tmp_db):
    entry_id = _add_digest_entry(tmp_db)
    resp = client.post(f"/api/digest-queue/{entry_id}/extract-links")
    assert resp.status_code == 200
    links = resp.json()["links"]

    # greenhouse.io link should be present with score=2
    gh_links = [l for l in links if "greenhouse.io" in l["url"]]
    assert len(gh_links) == 1
    assert gh_links[0]["score"] == 2

    # lever.co link should be present with score=2
    lever_links = [l for l in links if "lever.co" in l["url"]]
    assert len(lever_links) == 1
    assert lever_links[0]["score"] == 2

    # Each link must have a hint key (may be empty string for links at start of body)
    for link in links:
        assert "hint" in link


def test_digest_extract_links_filters_trackers(client, tmp_db):
    entry_id = _add_digest_entry(tmp_db)
    resp = client.post(f"/api/digest-queue/{entry_id}/extract-links")
    assert resp.status_code == 200
    links = resp.json()["links"]
    urls = [l["url"] for l in links]
    # Unsubscribe URL should be excluded
    assert not any("unsubscribe" in u for u in urls)


def test_digest_extract_links_404(client):
    resp = client.post("/api/digest-queue/9999/extract-links")
    assert resp.status_code == 404


# ── POST /api/digest-queue/{id}/queue-jobs ──────────────────────────────────

def test_digest_queue_jobs(client, tmp_db):
    entry_id = _add_digest_entry(tmp_db)
    resp = client.post(
        f"/api/digest-queue/{entry_id}/queue-jobs",
        json={"urls": ["https://greenhouse.io/acme/jobs/456"]},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["queued"] == 1
    assert data["skipped"] == 0

    con = sqlite3.connect(tmp_db)
    row = con.execute(
        "SELECT source, status FROM jobs WHERE url = 'https://greenhouse.io/acme/jobs/456'"
    ).fetchone()
    con.close()
    assert row is not None
    assert row[0] == "digest"
    assert row[1] == "pending"


def test_digest_queue_jobs_skips_duplicates(client, tmp_db):
    entry_id = _add_digest_entry(tmp_db)
    resp = client.post(
        f"/api/digest-queue/{entry_id}/queue-jobs",
        json={"urls": [
            "https://greenhouse.io/acme/jobs/789",
            "https://greenhouse.io/acme/jobs/789",  # same URL twice in one call
        ]},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["queued"] == 1
    assert data["skipped"] == 1

    con = sqlite3.connect(tmp_db)
    count = con.execute(
        "SELECT COUNT(*) FROM jobs WHERE url = 'https://greenhouse.io/acme/jobs/789'"
    ).fetchone()[0]
    con.close()
    assert count == 1


def test_digest_queue_jobs_skips_invalid_urls(client, tmp_db):
    entry_id = _add_digest_entry(tmp_db)
    resp = client.post(
        f"/api/digest-queue/{entry_id}/queue-jobs",
        json={"urls": ["", "ftp://bad.example.com", "https://valid.greenhouse.io/job/1"]},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["queued"] == 1
    assert data["skipped"] == 2


def test_digest_queue_jobs_empty_urls(client, tmp_db):
    entry_id = _add_digest_entry(tmp_db)
    resp = client.post(f"/api/digest-queue/{entry_id}/queue-jobs", json={"urls": []})
    assert resp.status_code == 400


def test_digest_queue_jobs_404(client):
    resp = client.post("/api/digest-queue/9999/queue-jobs", json={"urls": ["https://example.com"]})
    assert resp.status_code == 404


# ── DELETE /api/digest-queue/{id} ───────────────────────────────────────────

def test_digest_delete(client, tmp_db):
    entry_id = _add_digest_entry(tmp_db)
    resp = client.delete(f"/api/digest-queue/{entry_id}")
    assert resp.status_code == 200
    assert resp.json()["ok"] is True

    # Second delete → 404
    resp2 = client.delete(f"/api/digest-queue/{entry_id}")
    assert resp2.status_code == 404
