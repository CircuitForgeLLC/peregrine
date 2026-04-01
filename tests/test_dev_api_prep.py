"""Tests for interview prep endpoints: research GET/generate/task, contacts GET."""
import json
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    import sys
    sys.path.insert(0, "/Library/Development/CircuitForge/peregrine/.worktrees/feature-vue-spa")
    from dev_api import app
    return TestClient(app)


# ── /api/jobs/{id}/research ─────────────────────────────────────────────────

def test_get_research_found(client):
    """Returns research row (minus raw_output) when present."""
    import sqlite3
    mock_row = {
        "job_id": 1,
        "company_brief": "Acme Corp makes anvils.",
        "ceo_brief": "Wile E Coyote",
        "talking_points": "- Ask about roadrunner containment",
        "tech_brief": "Python, Rust",
        "funding_brief": "Series B",
        "red_flags": None,
        "accessibility_brief": None,
        "generated_at": "2026-03-20T12:00:00",
    }
    mock_db = MagicMock()
    mock_db.execute.return_value.fetchone.return_value = mock_row
    with patch("dev_api._get_db", return_value=mock_db):
        resp = client.get("/api/jobs/1/research")
    assert resp.status_code == 200
    data = resp.json()
    assert data["company_brief"] == "Acme Corp makes anvils."
    assert "raw_output" not in data


def test_get_research_not_found(client):
    """Returns 404 when no research row exists for job."""
    mock_db = MagicMock()
    mock_db.execute.return_value.fetchone.return_value = None
    with patch("dev_api._get_db", return_value=mock_db):
        resp = client.get("/api/jobs/99/research")
    assert resp.status_code == 404


# ── /api/jobs/{id}/research/generate ────────────────────────────────────────

def test_generate_research_new_task(client):
    """POST generate returns task_id and is_new=True for fresh submission."""
    with patch("scripts.task_runner.submit_task", return_value=(42, True)):
        resp = client.post("/api/jobs/1/research/generate")
    assert resp.status_code == 200
    data = resp.json()
    assert data["task_id"] == 42
    assert data["is_new"] is True


def test_generate_research_duplicate_task(client):
    """POST generate returns is_new=False when task already queued."""
    with patch("scripts.task_runner.submit_task", return_value=(17, False)):
        resp = client.post("/api/jobs/1/research/generate")
    assert resp.status_code == 200
    data = resp.json()
    assert data["is_new"] is False


def test_generate_research_error(client):
    """POST generate returns 500 when submit_task raises."""
    with patch("scripts.task_runner.submit_task", side_effect=Exception("LLM unavailable")):
        resp = client.post("/api/jobs/1/research/generate")
    assert resp.status_code == 500


# ── /api/jobs/{id}/research/task ────────────────────────────────────────────

def test_research_task_none(client):
    """Returns status=none when no background task exists for job."""
    mock_db = MagicMock()
    mock_db.execute.return_value.fetchone.return_value = None
    with patch("dev_api._get_db", return_value=mock_db):
        resp = client.get("/api/jobs/1/research/task")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "none"
    assert data["stage"] is None
    assert data["message"] is None


def test_research_task_running(client):
    """Returns current status/stage/message for an active task."""
    mock_row = {"status": "running", "stage": "Scraping company site", "error": None}
    mock_db = MagicMock()
    mock_db.execute.return_value.fetchone.return_value = mock_row
    with patch("dev_api._get_db", return_value=mock_db):
        resp = client.get("/api/jobs/1/research/task")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "running"
    assert data["stage"] == "Scraping company site"
    assert data["message"] is None


def test_research_task_failed(client):
    """Returns message (mapped from error column) for failed task."""
    mock_row = {"status": "failed", "stage": None, "error": "LLM timeout"}
    mock_db = MagicMock()
    mock_db.execute.return_value.fetchone.return_value = mock_row
    with patch("dev_api._get_db", return_value=mock_db):
        resp = client.get("/api/jobs/1/research/task")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "failed"
    assert data["message"] == "LLM timeout"


# ── /api/jobs/{id}/contacts ──────────────────────────────────────────────────

def test_get_contacts_empty(client):
    """Returns empty list when job has no contacts."""
    mock_db = MagicMock()
    mock_db.execute.return_value.fetchall.return_value = []
    with patch("dev_api._get_db", return_value=mock_db):
        resp = client.get("/api/jobs/1/contacts")
    assert resp.status_code == 200
    assert resp.json() == []


def test_get_contacts_list(client):
    """Returns list of contact dicts for job."""
    mock_rows = [
        {"id": 1, "direction": "inbound", "subject": "Interview next week",
         "from_addr": "hr@acme.com", "body": "Hi! We'd like to...", "received_at": "2026-03-19T10:00:00"},
        {"id": 2, "direction": "outbound", "subject": "Re: Interview next week",
         "from_addr": None, "body": "Thank you!", "received_at": "2026-03-19T11:00:00"},
    ]
    mock_db = MagicMock()
    mock_db.execute.return_value.fetchall.return_value = mock_rows
    with patch("dev_api._get_db", return_value=mock_db):
        resp = client.get("/api/jobs/1/contacts")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    assert data[0]["direction"] == "inbound"
    assert data[1]["direction"] == "outbound"


def test_get_contacts_ordered_by_received_at(client):
    """Most recent contacts appear first (ORDER BY received_at DESC)."""
    mock_db = MagicMock()
    mock_db.execute.return_value.fetchall.return_value = []
    with patch("dev_api._get_db", return_value=mock_db):
        resp = client.get("/api/jobs/99/contacts")
    # Verify the SQL contains ORDER BY received_at DESC
    call_args = mock_db.execute.call_args
    sql = call_args[0][0]
    assert "ORDER BY received_at DESC" in sql
