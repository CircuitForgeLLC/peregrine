"""Unit tests for E2E harness models and helper utilities."""
import fnmatch
import pytest
from unittest.mock import patch, MagicMock
import time
from tests.e2e.models import ErrorRecord, ModeConfig, diff_errors
import tests.e2e.modes.cloud as cloud_mod  # imported early so load_dotenv runs before any monkeypatch


def test_error_record_equality():
    a = ErrorRecord(type="exception", message="boom", element_html="<div>boom</div>")
    b = ErrorRecord(type="exception", message="boom", element_html="<div>boom</div>")
    assert a == b


def test_error_record_inequality():
    a = ErrorRecord(type="exception", message="boom", element_html="")
    b = ErrorRecord(type="alert", message="boom", element_html="")
    assert a != b


def test_diff_errors_returns_new_only():
    before = [ErrorRecord("exception", "old error", "")]
    after = [
        ErrorRecord("exception", "old error", ""),
        ErrorRecord("alert", "new error", ""),
    ]
    result = diff_errors(before, after)
    assert result == [ErrorRecord("alert", "new error", "")]


def test_diff_errors_empty_when_no_change():
    errors = [ErrorRecord("exception", "x", "")]
    assert diff_errors(errors, errors) == []


def test_diff_errors_empty_before():
    after = [ErrorRecord("alert", "boom", "")]
    assert diff_errors([], after) == after


def test_mode_config_expected_failure_match():
    config = ModeConfig(
        name="demo",
        base_url="http://localhost:8504",
        auth_setup=lambda ctx: None,
        expected_failures=["Fetch*", "Generate Cover Letter"],
        results_dir=None,
        settings_tabs=["👤 My Profile"],
    )
    assert config.matches_expected_failure("Fetch New Jobs")
    assert config.matches_expected_failure("Generate Cover Letter")
    assert not config.matches_expected_failure("View Jobs")


def test_mode_config_no_expected_failures():
    config = ModeConfig(
        name="local",
        base_url="http://localhost:8502",
        auth_setup=lambda ctx: None,
        expected_failures=[],
        results_dir=None,
        settings_tabs=[],
    )
    assert not config.matches_expected_failure("Fetch New Jobs")


def test_get_jwt_strategy_b_fallback(monkeypatch):
    """Falls back to persistent JWT when no email env var set."""
    monkeypatch.delenv("E2E_DIRECTUS_EMAIL", raising=False)
    monkeypatch.setenv("E2E_DIRECTUS_JWT", "persistent.jwt.token")
    cloud_mod._token_cache.update({"token": None, "expires_at": 0.0})
    assert cloud_mod._get_jwt() == "persistent.jwt.token"


def test_get_jwt_strategy_b_raises_if_no_token(monkeypatch):
    """Raises if neither email nor JWT env var is set."""
    monkeypatch.delenv("E2E_DIRECTUS_EMAIL", raising=False)
    monkeypatch.delenv("E2E_DIRECTUS_JWT", raising=False)
    cloud_mod._token_cache.update({"token": None, "expires_at": 0.0})
    with pytest.raises(RuntimeError, match="Cloud mode requires"):
        cloud_mod._get_jwt()


def test_get_jwt_strategy_a_login(monkeypatch):
    """Strategy A: calls Directus /auth/login and caches token."""
    monkeypatch.setenv("E2E_DIRECTUS_EMAIL", "e2e@circuitforge.tech")
    monkeypatch.setenv("E2E_DIRECTUS_PASSWORD", "testpass")
    monkeypatch.setenv("E2E_DIRECTUS_URL", "http://fake-directus:8055")
    cloud_mod._token_cache.update({"token": None, "expires_at": 0.0})

    mock_resp = MagicMock()
    mock_resp.json.return_value = {"data": {"access_token": "fresh.jwt", "expires": 900_000}}
    mock_resp.raise_for_status = lambda: None

    with patch("tests.e2e.modes.cloud.requests.post", return_value=mock_resp) as mock_post:
        token = cloud_mod._get_jwt()

    assert token == "fresh.jwt"
    mock_post.assert_called_once()
    assert cloud_mod._token_cache["token"] == "fresh.jwt"


def test_get_jwt_uses_cache(monkeypatch):
    """Returns cached token if not yet expired."""
    monkeypatch.setenv("E2E_DIRECTUS_EMAIL", "e2e@circuitforge.tech")
    cloud_mod._token_cache.update({"token": "cached.jwt", "expires_at": time.time() + 500})
    with patch("tests.e2e.modes.cloud.requests.post") as mock_post:
        token = cloud_mod._get_jwt()
    assert token == "cached.jwt"
    mock_post.assert_not_called()
