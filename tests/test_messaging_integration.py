"""Integration tests for messaging endpoints."""
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from scripts.db_migrate import migrate_db


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    """Set up a fresh isolated DB wired to dev_api._request_db."""
    db = tmp_path / "test.db"
    monkeypatch.setenv("STAGING_DB", str(db))
    migrate_db(db)
    import dev_api
    monkeypatch.setattr(
        dev_api,
        "_request_db",
        type("CV", (), {"get": lambda self: str(db), "set": lambda *a: None})(),
    )
    monkeypatch.setattr(dev_api, "DB_PATH", str(db))
    return db


@pytest.fixture
def client(fresh_db):
    import dev_api
    return TestClient(dev_api.app)


# ---------------------------------------------------------------------------
# Messages
# ---------------------------------------------------------------------------

def test_create_and_list_message(client):
    """POST /api/messages creates a row; GET /api/messages?job_id= returns it."""
    payload = {
        "job_id": 1,
        "type": "email",
        "direction": "outbound",
        "subject": "Hello recruiter",
        "body": "I am very interested in this role.",
        "to_addr": "recruiter@example.com",
    }
    resp = client.post("/api/messages", json=payload)
    assert resp.status_code == 200, resp.text
    created = resp.json()
    assert created["subject"] == "Hello recruiter"
    assert created["job_id"] == 1

    resp = client.get("/api/messages", params={"job_id": 1})
    assert resp.status_code == 200
    messages = resp.json()
    assert any(m["id"] == created["id"] for m in messages)


def test_delete_message(client):
    """DELETE removes the message; subsequent GET no longer returns it."""
    resp = client.post("/api/messages", json={"type": "email", "direction": "outbound", "body": "bye"})
    assert resp.status_code == 200
    msg_id = resp.json()["id"]

    resp = client.delete(f"/api/messages/{msg_id}")
    assert resp.status_code == 200
    assert resp.json()["ok"] is True

    resp = client.get("/api/messages")
    assert resp.status_code == 200
    ids = [m["id"] for m in resp.json()]
    assert msg_id not in ids


def test_delete_message_not_found(client):
    """DELETE /api/messages/9999 returns 404."""
    resp = client.delete("/api/messages/9999")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------

def test_list_templates_has_builtins(client):
    """GET /api/message-templates includes the seeded built-in keys."""
    resp = client.get("/api/message-templates")
    assert resp.status_code == 200
    templates = resp.json()
    keys = {t["key"] for t in templates}
    assert "follow_up" in keys
    assert "thank_you" in keys


def test_template_create_update_delete(client):
    """Full lifecycle: create → update title → delete a user-defined template."""
    # Create
    resp = client.post("/api/message-templates", json={
        "title": "My Template",
        "category": "custom",
        "body_template": "Hello {{name}}",
    })
    assert resp.status_code == 200
    tmpl = resp.json()
    assert tmpl["title"] == "My Template"
    assert tmpl["is_builtin"] == 0
    tmpl_id = tmpl["id"]

    # Update title
    resp = client.put(f"/api/message-templates/{tmpl_id}", json={"title": "Updated Title"})
    assert resp.status_code == 200
    assert resp.json()["title"] == "Updated Title"

    # Delete
    resp = client.delete(f"/api/message-templates/{tmpl_id}")
    assert resp.status_code == 200
    assert resp.json()["ok"] is True

    # Confirm gone
    resp = client.get("/api/message-templates")
    ids = [t["id"] for t in resp.json()]
    assert tmpl_id not in ids


def test_builtin_template_put_returns_403(client):
    """PUT on a built-in template returns 403."""
    resp = client.get("/api/message-templates")
    builtin = next(t for t in resp.json() if t["is_builtin"] == 1)
    resp = client.put(f"/api/message-templates/{builtin['id']}", json={"title": "Hacked"})
    assert resp.status_code == 403


def test_builtin_template_delete_returns_403(client):
    """DELETE on a built-in template returns 403."""
    resp = client.get("/api/message-templates")
    builtin = next(t for t in resp.json() if t["is_builtin"] == 1)
    resp = client.delete(f"/api/message-templates/{builtin['id']}")
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Draft reply (tier gate)
# ---------------------------------------------------------------------------

def test_draft_without_llm_returns_402(fresh_db, monkeypatch):
    """POST /api/contacts/{id}/draft-reply with free tier + no LLM configured returns 402."""
    import dev_api
    from scripts.db import add_contact

    # Insert a job_contacts row via the db helper so schema changes stay in sync
    contact_id = add_contact(
        fresh_db,
        job_id=None,
        direction="inbound",
        subject="Test subject",
        from_addr="hr@example.com",
        body="We would like to schedule...",
    )

    # Ensure has_configured_llm returns False at both import locations
    monkeypatch.setattr("app.wizard.tiers.has_configured_llm", lambda *a, **kw: False)
    # Force free tier via the tiers module (not via header — header is no longer trusted)
    monkeypatch.setattr("app.wizard.tiers.effective_tier", lambda: "free")

    client = TestClient(dev_api.app)
    resp = client.post(f"/api/contacts/{contact_id}/draft-reply")
    assert resp.status_code == 402


# ---------------------------------------------------------------------------
# Approve
# ---------------------------------------------------------------------------

def test_approve_message(client):
    """POST /api/messages then POST /api/messages/{id}/approve returns body + approved_at."""
    resp = client.post("/api/messages", json={
        "type": "draft",
        "direction": "outbound",
        "body": "This is my draft reply.",
    })
    assert resp.status_code == 200
    msg_id = resp.json()["id"]
    assert resp.json()["approved_at"] is None

    resp = client.post(f"/api/messages/{msg_id}/approve")
    assert resp.status_code == 200
    data = resp.json()
    assert data["body"] == "This is my draft reply."
    assert data["approved_at"] is not None


def test_approve_message_not_found(client):
    """POST /api/messages/9999/approve returns 404."""
    resp = client.post("/api/messages/9999/approve")
    assert resp.status_code == 404
