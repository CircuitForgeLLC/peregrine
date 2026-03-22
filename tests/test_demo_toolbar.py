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


def test_render_demo_toolbar_renders_pills(monkeypatch):
    """render_demo_toolbar renders tier selection pills."""
    session = {"simulated_tier": "paid"}
    calls = []

    def mock_button(label, key=None, type=None, use_container_width=False):
        calls.append(("button", label, key, type))
        return False  # button not clicked

    monkeypatch.setattr("streamlit.session_state", session, raising=False)
    monkeypatch.setattr("streamlit.container", lambda: __import__("contextlib").nullcontext())
    monkeypatch.setattr("streamlit.columns", lambda x: [__import__("contextlib").nullcontext() for _ in x])
    monkeypatch.setattr("streamlit.caption", lambda x: None)
    monkeypatch.setattr("streamlit.button", mock_button)
    monkeypatch.setattr("streamlit.divider", lambda: None)

    from app.components.demo_toolbar import render_demo_toolbar
    render_demo_toolbar()

    # Verify buttons were rendered for all tiers
    button_calls = [c for c in calls if c[0] == "button"]
    assert len(button_calls) == 3
    assert any("Paid ✓" in c[1] for c in button_calls)  # current tier marked
