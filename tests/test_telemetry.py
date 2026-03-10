import pytest
import os
from unittest.mock import patch, MagicMock, call


def test_no_op_in_local_mode(monkeypatch):
    """log_usage_event() is completely silent when CLOUD_MODE is not set."""
    monkeypatch.delenv("CLOUD_MODE", raising=False)
    import importlib
    import app.telemetry as tel
    importlib.reload(tel)
    # Should not raise, should not touch anything
    tel.log_usage_event("user-1", "peregrine", "any_event")


def test_event_not_logged_when_all_disabled(monkeypatch):
    """No DB write when telemetry all_disabled is True."""
    monkeypatch.setenv("CLOUD_MODE", "true")
    import importlib
    import app.telemetry as tel
    importlib.reload(tel)

    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
    mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

    with patch.object(tel, "get_platform_conn", return_value=mock_conn), \
         patch.object(tel, "get_consent", return_value={"all_disabled": True, "usage_events_enabled": True}):
        tel.log_usage_event("user-1", "peregrine", "cover_letter_generated")

    mock_cursor.execute.assert_not_called()


def test_event_not_logged_when_usage_events_disabled(monkeypatch):
    """No DB write when usage_events_enabled is False."""
    monkeypatch.setenv("CLOUD_MODE", "true")
    import importlib
    import app.telemetry as tel
    importlib.reload(tel)

    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
    mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

    with patch.object(tel, "get_platform_conn", return_value=mock_conn), \
         patch.object(tel, "get_consent", return_value={"all_disabled": False, "usage_events_enabled": False}):
        tel.log_usage_event("user-1", "peregrine", "cover_letter_generated")

    mock_cursor.execute.assert_not_called()


def test_event_logged_when_consent_given(monkeypatch):
    """Usage event is written to usage_events table when consent is given."""
    monkeypatch.setenv("CLOUD_MODE", "true")
    import importlib
    import app.telemetry as tel
    importlib.reload(tel)

    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
    mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

    with patch.object(tel, "get_platform_conn", return_value=mock_conn), \
         patch.object(tel, "get_consent", return_value={"all_disabled": False, "usage_events_enabled": True}):
        tel.log_usage_event("user-1", "peregrine", "cover_letter_generated", {"words": 350})

    mock_cursor.execute.assert_called_once()
    sql = mock_cursor.execute.call_args[0][0]
    assert "usage_events" in sql
    mock_conn.commit.assert_called_once()


def test_telemetry_never_crashes_app(monkeypatch):
    """log_usage_event() swallows all exceptions — must never crash the app."""
    monkeypatch.setenv("CLOUD_MODE", "true")
    import importlib
    import app.telemetry as tel
    importlib.reload(tel)

    with patch.object(tel, "get_platform_conn", side_effect=Exception("DB down")):
        # Should not raise
        tel.log_usage_event("user-1", "peregrine", "any_event")
