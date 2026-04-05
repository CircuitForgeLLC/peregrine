"""Tests for app/components/ui_switcher.py.

Streamlit is not running during tests — mock all st.* calls.
"""
import sys
from pathlib import Path
from unittest.mock import patch
import pytest
import yaml

sys.path.insert(0, str(Path(__file__).parent.parent))


@pytest.fixture
def profile_yaml(tmp_path):
    data = {"name": "Test", "ui_preference": "streamlit", "wizard_complete": True}
    p = tmp_path / "user.yaml"
    p.write_text(yaml.dump(data))
    return p


def test_sync_cookie_injects_vue_js(profile_yaml, monkeypatch):
    """When ui_preference is vue, JS sets prgn_ui=vue."""
    import yaml as _yaml
    profile_yaml.write_text(_yaml.dump({"name": "T", "ui_preference": "vue"}))

    injected = []
    monkeypatch.setattr("streamlit.components.v1.html", lambda html, height=0: injected.append(html))
    monkeypatch.setattr("streamlit.query_params", {}, raising=False)

    from app.components.ui_switcher import sync_ui_cookie
    sync_ui_cookie(profile_yaml, tier="paid")

    assert any("prgn_ui=vue" in s for s in injected)


def test_sync_cookie_injects_streamlit_js(profile_yaml, monkeypatch):
    """When ui_preference is streamlit, JS sets prgn_ui=streamlit."""
    injected = []
    monkeypatch.setattr("streamlit.components.v1.html", lambda html, height=0: injected.append(html))
    monkeypatch.setattr("streamlit.query_params", {}, raising=False)

    from app.components.ui_switcher import sync_ui_cookie
    sync_ui_cookie(profile_yaml, tier="paid")

    assert any("prgn_ui=streamlit" in s for s in injected)


def test_sync_cookie_prgn_switch_param_overrides_yaml(profile_yaml, monkeypatch):
    """?prgn_switch=streamlit in query params resets ui_preference to streamlit."""
    import yaml as _yaml
    profile_yaml.write_text(_yaml.dump({"name": "T", "ui_preference": "vue"}))

    injected = []
    monkeypatch.setattr("streamlit.components.v1.html", lambda html, height=0: injected.append(html))
    monkeypatch.setattr("streamlit.query_params", {"prgn_switch": "streamlit"}, raising=False)

    with patch('app.components.ui_switcher._DEMO_MODE', False):
        from app.components.ui_switcher import sync_ui_cookie
        sync_ui_cookie(profile_yaml, tier="paid")

    # user.yaml should now say streamlit
    saved = _yaml.safe_load(profile_yaml.read_text())
    assert saved["ui_preference"] == "streamlit"
    # JS should set cookie to streamlit
    assert any("prgn_ui=streamlit" in s for s in injected)


def test_sync_cookie_free_tier_keeps_vue(profile_yaml, monkeypatch):
    """Free-tier user with vue preference keeps vue (vue_ui_beta is free tier).

    Previously this test verified a downgrade to streamlit. Vue SPA was opened
    to free tier in issue #20 — the downgrade path no longer triggers.
    """
    import yaml as _yaml
    profile_yaml.write_text(_yaml.dump({"name": "T", "ui_preference": "vue"}))

    injected = []
    monkeypatch.setattr("streamlit.components.v1.html", lambda html, height=0: injected.append(html))
    monkeypatch.setattr("streamlit.query_params", {}, raising=False)

    with patch('app.components.ui_switcher._DEMO_MODE', False):
        from app.components.ui_switcher import sync_ui_cookie
        sync_ui_cookie(profile_yaml, tier="free")

    saved = _yaml.safe_load(profile_yaml.read_text())
    assert saved["ui_preference"] == "vue"
    assert any("prgn_ui=vue" in s for s in injected)


def test_switch_ui_writes_yaml_and_calls_sync(profile_yaml, monkeypatch):
    """switch_ui(to='vue') writes user.yaml and calls sync."""
    import yaml as _yaml
    synced = []
    monkeypatch.setattr("streamlit.components.v1.html", lambda html, height=0: synced.append(html))
    monkeypatch.setattr("streamlit.query_params", {}, raising=False)
    monkeypatch.setattr("streamlit.rerun", lambda: None)

    with patch('app.components.ui_switcher._DEMO_MODE', False):
        from app.components.ui_switcher import switch_ui
        switch_ui(profile_yaml, to="vue", tier="paid")

    saved = _yaml.safe_load(profile_yaml.read_text())
    assert saved["ui_preference"] == "vue"
    assert any("prgn_ui=vue" in s for s in synced)
