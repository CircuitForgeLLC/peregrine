import pytest
import os
from unittest.mock import patch, MagicMock
from pathlib import Path


def test_resolve_session_is_noop_in_local_mode(monkeypatch):
    """resolve_session() does nothing when CLOUD_MODE is not set."""
    monkeypatch.delenv("CLOUD_MODE", raising=False)
    # Must reimport after env change
    import importlib
    import app.cloud_session as cs
    importlib.reload(cs)
    # Should return without touching st
    cs.resolve_session("peregrine")  # no error = pass


def test_resolve_session_sets_db_path(tmp_path, monkeypatch):
    """resolve_session() sets st.session_state.db_path from a valid JWT."""
    monkeypatch.setenv("CLOUD_MODE", "true")
    import importlib
    import app.cloud_session as cs
    importlib.reload(cs)

    mock_state = {}
    with patch.object(cs, "validate_session_jwt", return_value="user-uuid-123"), \
         patch.object(cs, "st") as mock_st, \
         patch.object(cs, "CLOUD_DATA_ROOT", tmp_path):
        mock_st.session_state = mock_state
        mock_st.context.headers = {"x-cf-session": "cf_session=valid.jwt.token"}
        cs.resolve_session("peregrine")

    assert mock_state["user_id"] == "user-uuid-123"
    assert mock_state["db_path"] == tmp_path / "user-uuid-123" / "peregrine" / "staging.db"


def test_resolve_session_creates_user_dir(tmp_path, monkeypatch):
    """resolve_session() creates the user data directory on first login."""
    monkeypatch.setenv("CLOUD_MODE", "true")
    import importlib
    import app.cloud_session as cs
    importlib.reload(cs)

    mock_state = {}
    with patch.object(cs, "validate_session_jwt", return_value="new-user"), \
         patch.object(cs, "st") as mock_st, \
         patch.object(cs, "CLOUD_DATA_ROOT", tmp_path):
        mock_st.session_state = mock_state
        mock_st.context.headers = {"x-cf-session": "cf_session=valid.jwt.token"}
        cs.resolve_session("peregrine")

    assert (tmp_path / "new-user" / "peregrine").is_dir()
    assert (tmp_path / "new-user" / "peregrine" / "config").is_dir()
    assert (tmp_path / "new-user" / "peregrine" / "data").is_dir()


def test_resolve_session_idempotent(monkeypatch):
    """resolve_session() skips if user_id already in session state."""
    monkeypatch.setenv("CLOUD_MODE", "true")
    import importlib
    import app.cloud_session as cs
    importlib.reload(cs)

    with patch.object(cs, "st") as mock_st:
        mock_st.session_state = {"user_id": "existing-user"}
        # Should not try to read headers or validate JWT
        cs.resolve_session("peregrine")
        # context.headers should never be accessed
        mock_st.context.headers.__getitem__.assert_not_called() if hasattr(mock_st.context, 'headers') else None


def test_get_db_path_returns_session_path(tmp_path, monkeypatch):
    """get_db_path() returns session-scoped path when set."""
    import importlib
    import app.cloud_session as cs
    importlib.reload(cs)

    session_db = tmp_path / "staging.db"
    with patch.object(cs, "st") as mock_st:
        mock_st.session_state = {"db_path": session_db}
        result = cs.get_db_path()
    assert result == session_db


def test_get_db_path_falls_back_to_default(monkeypatch):
    """get_db_path() returns DEFAULT_DB when no session path set."""
    monkeypatch.delenv("CLOUD_MODE", raising=False)
    import importlib
    import app.cloud_session as cs
    importlib.reload(cs)
    from scripts.db import DEFAULT_DB

    with patch.object(cs, "st") as mock_st:
        mock_st.session_state = {}
        result = cs.get_db_path()
    assert result == DEFAULT_DB
