"""Tests for app/components/demo_toolbar.py."""
import sys, os
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

# Ensure DEMO_MODE is set so the module initialises correctly
os.environ["DEMO_MODE"] = "true"


def test_set_simulated_tier_updates_session_state(monkeypatch):
    """set_simulated_tier writes to st.session_state.simulated_tier."""
    session = {}
    injected = []
    monkeypatch.setattr("streamlit.components.v1.html", lambda h, height=0: injected.append(h))
    monkeypatch.setattr("streamlit.session_state", session, raising=False)
    monkeypatch.setattr("streamlit.rerun", lambda: None)

    from unittest.mock import patch
    with patch('app.components.demo_toolbar._DEMO_MODE', True):
        from importlib import reload
        import app.components.demo_toolbar as m
        reload(m)
        m.set_simulated_tier("premium")

    assert session.get("simulated_tier") == "premium"
    assert any("prgn_demo_tier=premium" in h for h in injected)


def test_set_simulated_tier_invalid_ignored(monkeypatch):
    """Invalid tier strings are rejected."""
    session = {}
    monkeypatch.setattr("streamlit.components.v1.html", lambda h, height=0: None)
    monkeypatch.setattr("streamlit.session_state", session, raising=False)
    monkeypatch.setattr("streamlit.rerun", lambda: None)

    from unittest.mock import patch
    with patch('app.components.demo_toolbar._DEMO_MODE', True):
        from importlib import reload
        import app.components.demo_toolbar as m
        reload(m)
        m.set_simulated_tier("ultramax")

    assert "simulated_tier" not in session


def test_get_simulated_tier_defaults_to_paid(monkeypatch):
    """Returns 'paid' when no tier is set yet."""
    monkeypatch.setattr("streamlit.session_state", {}, raising=False)
    monkeypatch.setattr("streamlit.query_params", {}, raising=False)

    from app.components.demo_toolbar import get_simulated_tier
    assert get_simulated_tier() == "paid"


def test_get_simulated_tier_reads_session(monkeypatch):
    """Returns tier from st.session_state when set."""
    monkeypatch.setattr("streamlit.session_state", {"simulated_tier": "free"}, raising=False)
    monkeypatch.setattr("streamlit.query_params", {}, raising=False)

    from app.components.demo_toolbar import get_simulated_tier
    assert get_simulated_tier() == "free"
