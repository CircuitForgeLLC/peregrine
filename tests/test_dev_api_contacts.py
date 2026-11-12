"""Tests for GET /api/contacts: stage_signal filtering and total count
respecting active filters (peregrine gap fix -- contacts list had no way
to filter to unreviewed emails, and `total` ignored direction/search too)."""
import sqlite3

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def tmp_db(tmp_path):
    from scripts.db import init_db
    db_path = tmp_path / "staging.db"
    init_db(db_path)
    con = sqlite3.connect(db_path)
    con.execute("INSERT INTO jobs (id, title, company, status) VALUES (1, 'Engineer', 'Acme', 'applied')")
    con.executemany(
        "INSERT INTO job_contacts (id, job_id, direction, subject, from_addr, received_at, stage_signal) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        [
            (1, 1, "inbound", "Interview confirmed", "a@co.com", "2026-03-19T10:00:00", "interview_scheduled"),
            (2, 1, "inbound", "Newsletter", "b@co.com", "2026-03-18T09:00:00", None),
            (3, 1, "inbound", "Old neutral", "c@co.com", "2026-03-17T08:00:00", "neutral"),
            (4, 1, "outbound", "My reply", "me@co.com", "2026-03-16T08:00:00", None),
        ],
    )
    con.commit()
    con.close()
    return db_path


@pytest.fixture()
def client(tmp_db, monkeypatch):
    monkeypatch.setattr("dev_api.DB_PATH", tmp_db)
    from dev_api import app
    return TestClient(app)


def test_stage_signal_needs_review_matches_null_and_neutral(client):
    resp = client.get("/api/contacts?stage_signal=needs_review")
    assert resp.status_code == 200
    data = resp.json()
    # 2 (null), 3 (neutral), and 4 (null, outbound) all count as needs-review
    ids = {c["id"] for c in data["contacts"]}
    assert ids == {2, 3, 4}
    assert data["total"] == 3


def test_stage_signal_exact_match(client):
    resp = client.get("/api/contacts?stage_signal=interview_scheduled")
    assert resp.status_code == 200
    data = resp.json()
    assert [c["id"] for c in data["contacts"]] == [1]
    assert data["total"] == 1


def test_no_stage_signal_filter_returns_all(client):
    resp = client.get("/api/contacts")
    assert resp.status_code == 200
    assert resp.json()["total"] == 4


def test_total_respects_direction_filter(client):
    resp = client.get("/api/contacts?direction=outbound")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert [c["id"] for c in data["contacts"]] == [4]


def test_total_respects_search_filter(client):
    resp = client.get("/api/contacts?search=newsletter")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert [c["id"] for c in data["contacts"]] == [2]


def test_combined_direction_and_stage_signal_filters(client):
    resp = client.get("/api/contacts?direction=inbound&stage_signal=needs_review")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2
    assert {c["id"] for c in data["contacts"]} == {2, 3}
