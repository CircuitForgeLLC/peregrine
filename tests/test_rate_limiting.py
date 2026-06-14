"""Tests for per-user rate limiting on LLM generation endpoints.

Covers:
- _rate_key() in demo mode returns unique per-request key (no rate limiting)
- _rate_key() in cloud mode returns user_id segment from DB path
- _rate_key() in local mode falls back to client IP address
- rate_limit_exceeded_handler() returns 429 with Retry-After header
- Integration: hitting rate limit on a decorated endpoint returns 429
"""
import json
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from limits import parse as _limits_parse
from slowapi.errors import RateLimitExceeded
from slowapi.wrappers import Limit as _LimitWrapper
from starlette.requests import Request

from scripts.rate_limit import _rate_key, rate_limit_exceeded_handler


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_request(client_ip: str = "1.2.3.4") -> MagicMock:
    """Return a minimal mock Request with a client IP."""
    req = MagicMock(spec=Request)
    req.client = MagicMock()
    req.client.host = client_ip
    req.headers = {}
    req.scope = {"type": "http"}
    return req


def _make_rate_limit_exceeded(spec: str = "20/hour") -> RateLimitExceeded:
    """Construct a valid RateLimitExceeded (slowapi 0.1.9+ requires a Limit wrapper)."""
    limit_item = _limits_parse(spec)
    wrapper = _LimitWrapper(
        limit=limit_item,
        key_func=lambda r: "test",
        scope=None,
        per_method=False,
        methods=None,
        error_message=None,
        exempt_when=None,
        cost=1,
        override_defaults=False,
    )
    return RateLimitExceeded(wrapper)


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture()
def tmp_db(tmp_path):
    """Create a minimal staging.db in tmp_path and return its string path."""
    db_path = tmp_path / "staging.db"
    con = sqlite3.connect(str(db_path))
    con.executescript("""
        CREATE TABLE IF NOT EXISTS jobs (
            id INTEGER PRIMARY KEY,
            title TEXT, company TEXT, url TEXT, location TEXT,
            is_remote INTEGER DEFAULT 0, salary TEXT,
            match_score REAL, keyword_gaps TEXT, status TEXT,
            interview_date TEXT, rejection_stage TEXT,
            applied_at TEXT, phone_screen_at TEXT, interviewing_at TEXT,
            offer_at TEXT, hired_at TEXT, survey_at TEXT
        );
        CREATE TABLE IF NOT EXISTS background_tasks (
            id INTEGER PRIMARY KEY,
            task_type TEXT,
            job_id INTEGER,
            status TEXT DEFAULT 'queued',
            stage TEXT,
            error TEXT,
            params TEXT,
            finished_at TEXT
        );
    """)
    con.close()
    return str(db_path)


@pytest.fixture()
def client(tmp_db, monkeypatch):
    """TestClient wired to a fresh isolated DB."""
    monkeypatch.setenv("STAGING_DB", tmp_db)
    import dev_api
    monkeypatch.setattr(dev_api, "DB_PATH", tmp_db)
    monkeypatch.setattr(
        dev_api,
        "_request_db",
        type("CV", (), {"get": lambda self: tmp_db, "set": lambda *a: None})(),
    )
    return TestClient(dev_api.app)


# ── _rate_key(): demo mode ────────────────────────────────────────────────────

class TestRateKeyDemoMode:
    def test_returns_unique_key_per_request(self):
        """In demo mode each request gets a unique key so no limiting occurs."""
        req1 = _make_request()
        req2 = _make_request()
        with patch("dev_api.IS_DEMO", True), patch("dev_api._CLOUD_MODE", False):
            key1 = _rate_key(req1)
            key2 = _rate_key(req2)
        assert key1.startswith("demo-")
        assert key2.startswith("demo-")
        assert key1 != key2  # unique per request object

    def test_key_does_not_use_client_ip(self):
        """Demo key must not equal the client IP."""
        req = _make_request(client_ip="9.9.9.9")
        with patch("dev_api.IS_DEMO", True), patch("dev_api._CLOUD_MODE", False):
            key = _rate_key(req)
        assert "9.9.9.9" not in key


# ── _rate_key(): cloud mode ───────────────────────────────────────────────────

class TestRateKeyCloudMode:
    def test_returns_user_id_from_db_path(self, tmp_path):
        """Cloud mode extracts user_id (3rd-from-end path segment)."""
        cloud_db = str(tmp_path / "abc-user-123" / "peregrine" / "staging.db")
        req = _make_request()
        with (
            patch("dev_api.IS_DEMO", False),
            patch("dev_api._CLOUD_MODE", True),
            patch("dev_api._request_db") as mock_cv,
        ):
            mock_cv.get.return_value = cloud_db
            key = _rate_key(req)
        assert key == "abc-user-123"

    def test_falls_back_to_ip_when_db_path_is_none(self):
        """Cloud mode without a DB path (unauthenticated) falls back to IP."""
        req = _make_request(client_ip="10.0.0.1")
        with (
            patch("dev_api.IS_DEMO", False),
            patch("dev_api._CLOUD_MODE", True),
            patch("dev_api._request_db") as mock_cv,
        ):
            mock_cv.get.return_value = None
            key = _rate_key(req)
        assert key == "10.0.0.1"


# ── _rate_key(): local mode ───────────────────────────────────────────────────

class TestRateKeyLocalMode:
    def test_returns_client_ip(self):
        """Local (non-cloud, non-demo) mode uses the remote client IP."""
        req = _make_request(client_ip="192.168.1.50")
        with patch("dev_api.IS_DEMO", False), patch("dev_api._CLOUD_MODE", False):
            key = _rate_key(req)
        assert key == "192.168.1.50"

    def test_different_ips_produce_different_keys(self):
        """Two distinct client IPs produce distinct rate limit keys."""
        req_a = _make_request(client_ip="10.0.0.1")
        req_b = _make_request(client_ip="10.0.0.2")
        with patch("dev_api.IS_DEMO", False), patch("dev_api._CLOUD_MODE", False):
            key_a = _rate_key(req_a)
            key_b = _rate_key(req_b)
        assert key_a != key_b


# ── rate_limit_exceeded_handler() ─────────────────────────────────────────────

class TestRateLimitExceededHandler:
    def test_returns_429_status(self):
        """Handler always returns HTTP 429."""
        req = _make_request()
        exc = _make_rate_limit_exceeded("20/hour")
        response = rate_limit_exceeded_handler(req, exc)
        assert response.status_code == 429

    def test_body_has_error_field(self):
        """Response body includes error: rate_limit_exceeded."""
        req = _make_request()
        exc = _make_rate_limit_exceeded("20/hour")
        response = rate_limit_exceeded_handler(req, exc)
        body = json.loads(response.body)
        assert body["error"] == "rate_limit_exceeded"

    def test_body_has_retry_after_field(self):
        """Response body includes retry_after value."""
        req = _make_request()
        exc = _make_rate_limit_exceeded("20/hour")
        response = rate_limit_exceeded_handler(req, exc)
        body = json.loads(response.body)
        assert "retry_after" in body

    def test_retry_after_header_present(self):
        """Retry-After HTTP header is set on the response."""
        req = _make_request()
        exc = _make_rate_limit_exceeded("20/hour")
        response = rate_limit_exceeded_handler(req, exc)
        assert "Retry-After" in response.headers

    def test_retry_after_header_matches_body(self):
        """Retry-After header value matches the retry_after field in the body."""
        req = _make_request()
        exc = _make_rate_limit_exceeded("20/hour")
        response = rate_limit_exceeded_handler(req, exc)
        body = json.loads(response.body)
        assert response.headers["Retry-After"] == str(body["retry_after"])


# ── Integration: 429 on rate-limited endpoints ────────────────────────────────

def _patch_limiter_to_raise(exc: RateLimitExceeded):
    """Context manager: make the slowapi limiter fire for any request."""
    return patch(
        "slowapi.extension.Limiter._check_request_limit",
        side_effect=exc,
    )


class TestRateLimitIntegration:
    """Verify that when the limiter fires, the app returns 429 via the exception handler."""

    def test_cover_letter_generate_returns_429_on_limit(self, client):
        """When the rate limiter triggers, the cover letter endpoint returns 429."""
        exc = _make_rate_limit_exceeded("20/hour")
        with _patch_limiter_to_raise(exc):
            resp = client.post("/api/jobs/1/cover_letter/generate")
        assert resp.status_code == 429

    def test_research_generate_returns_429_on_limit(self, client):
        """When the rate limiter triggers, the research endpoint returns 429."""
        exc = _make_rate_limit_exceeded("10/hour")
        with _patch_limiter_to_raise(exc):
            resp = client.post("/api/jobs/1/research/generate")
        assert resp.status_code == 429

    def test_qa_suggest_returns_429_on_limit(self, client):
        """When the rate limiter triggers, the QA suggest endpoint returns 429."""
        exc = _make_rate_limit_exceeded("60/hour")
        with _patch_limiter_to_raise(exc):
            resp = client.post(
                "/api/jobs/1/qa/suggest",
                json={"question": "Why do you want this job?", "items": []},
            )
        assert resp.status_code == 429

    def test_survey_analyze_returns_429_on_limit(self, client):
        """When the rate limiter triggers, the survey analyze endpoint returns 429."""
        exc = _make_rate_limit_exceeded("30/hour")
        with _patch_limiter_to_raise(exc):
            resp = client.post(
                "/api/jobs/1/survey/analyze",
                json={"text": "Q: ...", "mode": "quick"},
            )
        assert resp.status_code == 429

    def test_cover_letter_generate_succeeds_when_not_limited(self, client):
        """Cover letter generate endpoint works normally when not rate-limited."""
        with patch("scripts.task_runner.submit_task", return_value=(1, True)):
            resp = client.post("/api/jobs/1/cover_letter/generate")
        # 200 = task queued; 403 = demo/cloud guard; 404/422 = DB/payload issue
        # Any non-5xx, non-429 response means the limiter did NOT block the request
        assert resp.status_code in (200, 403, 404, 422)

    def test_429_response_body_has_error_key(self, client):
        """429 responses from rate-limited endpoints include the error key."""
        exc = _make_rate_limit_exceeded("20/hour")
        with _patch_limiter_to_raise(exc):
            resp = client.post("/api/jobs/1/cover_letter/generate")
        assert resp.status_code == 429
        body = resp.json()
        assert body.get("error") == "rate_limit_exceeded"

    def test_429_response_has_retry_after_header(self, client):
        """429 responses include a Retry-After header."""
        exc = _make_rate_limit_exceeded("20/hour")
        with _patch_limiter_to_raise(exc):
            resp = client.post("/api/jobs/1/cover_letter/generate")
        assert resp.status_code == 429
        assert "retry-after" in resp.headers or "Retry-After" in resp.headers
