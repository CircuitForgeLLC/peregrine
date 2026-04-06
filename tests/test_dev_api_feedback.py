"""Tests for the /api/feedback routes in dev_api."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(monkeypatch):
    monkeypatch.delenv("CLOUD_MODE", raising=False)
    monkeypatch.delenv("DEMO_MODE", raising=False)
    monkeypatch.delenv("FORGEJO_API_TOKEN", raising=False)
    from dev_api import app
    return TestClient(app)


# ---------------------------------------------------------------------------
# GET /api/feedback/status
# ---------------------------------------------------------------------------

def test_status_disabled_when_no_token(client):
    """Status is disabled when FORGEJO_API_TOKEN is not set."""
    resp = client.get("/api/feedback/status")
    assert resp.status_code == 200
    assert resp.json() == {"enabled": False}


def test_status_enabled_with_token(monkeypatch):
    """Status is enabled when token is set and not in demo or cloud mode."""
    monkeypatch.delenv("CLOUD_MODE", raising=False)
    monkeypatch.delenv("DEMO_MODE", raising=False)
    monkeypatch.setenv("FORGEJO_API_TOKEN", "test-token")
    from dev_api import app
    c = TestClient(app)
    resp = c.get("/api/feedback/status")
    assert resp.status_code == 200
    assert resp.json() == {"enabled": True}


def test_status_disabled_in_demo_mode(monkeypatch):
    """Status is disabled when DEMO_MODE=1 even if token is present."""
    monkeypatch.setenv("DEMO_MODE", "1")
    monkeypatch.setenv("FORGEJO_API_TOKEN", "test-token")
    monkeypatch.delenv("CLOUD_MODE", raising=False)
    from dev_api import app
    c = TestClient(app)
    resp = c.get("/api/feedback/status")
    assert resp.status_code == 200
    assert resp.json() == {"enabled": False}


def test_status_disabled_in_cloud_mode(monkeypatch):
    """Status is disabled when CLOUD_MODE=1 (peregrine-specific rule).

    _CLOUD_MODE is evaluated at import time, so we patch the module-level
    bool rather than the env var (the module is already cached in sys.modules).
    """
    import dev_api as _dev_api_mod
    monkeypatch.setattr(_dev_api_mod, "_CLOUD_MODE", True)
    monkeypatch.setenv("FORGEJO_API_TOKEN", "test-token")
    monkeypatch.delenv("DEMO_MODE", raising=False)
    c = TestClient(_dev_api_mod.app)
    resp = c.get("/api/feedback/status")
    assert resp.status_code == 200
    assert resp.json() == {"enabled": False}


# ---------------------------------------------------------------------------
# POST /api/feedback
# ---------------------------------------------------------------------------

_FEEDBACK_PAYLOAD = {
    "title": "Test feedback",
    "description": "Something broke.",
    "type": "bug",
    "repro": "Click the button.",
    "tab": "Job Review",
    "submitter": "tester@example.com",
}


def test_post_feedback_503_when_no_token(client):
    """POST returns 503 when FORGEJO_API_TOKEN is not configured."""
    resp = client.post("/api/feedback", json=_FEEDBACK_PAYLOAD)
    assert resp.status_code == 503
    assert "FORGEJO_API_TOKEN" in resp.json()["detail"]


def test_post_feedback_403_in_demo_mode(monkeypatch):
    """POST returns 403 when DEMO_MODE=1."""
    monkeypatch.setenv("DEMO_MODE", "1")
    monkeypatch.setenv("FORGEJO_API_TOKEN", "test-token")
    monkeypatch.delenv("CLOUD_MODE", raising=False)
    from dev_api import app
    c = TestClient(app)
    resp = c.post("/api/feedback", json=_FEEDBACK_PAYLOAD)
    assert resp.status_code == 403
    assert "demo" in resp.json()["detail"].lower()


def test_post_feedback_200_creates_issue(monkeypatch):
    """POST returns 200 with issue_number and issue_url when Forgejo calls succeed."""
    monkeypatch.setenv("FORGEJO_API_TOKEN", "test-token")
    monkeypatch.delenv("CLOUD_MODE", raising=False)
    monkeypatch.delenv("DEMO_MODE", raising=False)

    mock_get_resp = MagicMock()
    mock_get_resp.ok = True
    mock_get_resp.json.return_value = [
        {"name": "beta-feedback", "id": 1},
        {"name": "needs-triage", "id": 2},
        {"name": "bug", "id": 3},
    ]

    mock_post_resp = MagicMock()
    mock_post_resp.ok = True
    mock_post_resp.json.return_value = {
        "number": 42,
        "html_url": "https://git.opensourcesolarpunk.com/Circuit-Forge/peregrine/issues/42",
    }

    with patch("circuitforge_core.api.feedback.requests.get", return_value=mock_get_resp), \
         patch("circuitforge_core.api.feedback.requests.post", return_value=mock_post_resp):
        from dev_api import app
        c = TestClient(app)
        resp = c.post("/api/feedback", json=_FEEDBACK_PAYLOAD)

    assert resp.status_code == 200
    body = resp.json()
    assert body["issue_number"] == 42
    assert "peregrine/issues/42" in body["issue_url"]
