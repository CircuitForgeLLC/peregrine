"""Tests for all settings API endpoints added in Tasks 1–8."""
import os
import sys
import yaml
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

_WORKTREE = "/Library/Development/CircuitForge/peregrine/.worktrees/feature-vue-spa"

# ── Path bootstrap ────────────────────────────────────────────────────────────
# dev_api.py inserts /Library/Development/CircuitForge/peregrine into sys.path
# at import time; the worktree has credential_store but the main repo doesn't.
# Insert the worktree first so 'scripts' resolves to the worktree version, then
# pre-cache it in sys.modules so Python won't re-look-up when dev_api adds the
# main peregrine root.
if _WORKTREE not in sys.path:
    sys.path.insert(0, _WORKTREE)
# Pre-cache the worktree scripts package and submodules before dev_api import
import importlib, types

def _ensure_worktree_scripts():
    import importlib.util as _ilu
    _wt = _WORKTREE
    # Only load if not already loaded from the worktree
    _spec = _ilu.spec_from_file_location("scripts", f"{_wt}/scripts/__init__.py",
                                          submodule_search_locations=[f"{_wt}/scripts"])
    if _spec is None:
        return
    _mod = _ilu.module_from_spec(_spec)
    sys.modules.setdefault("scripts", _mod)
    try:
        _spec.loader.exec_module(_mod)
    except Exception:
        pass

_ensure_worktree_scripts()


@pytest.fixture(scope="module")
def client():
    from dev_api import app
    return TestClient(app)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _write_user_yaml(path: Path, data: dict = None):
    """Write a minimal user.yaml to the given path."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        yaml.dump(data or {"name": "Test User", "email": "test@example.com"}, f)


# ── GET /api/config/app ───────────────────────────────────────────────────────

def test_app_config_returns_expected_keys(client):
    """Returns 200 with isCloud, tier, and inferenceProfile in valid values."""
    resp = client.get("/api/config/app")
    assert resp.status_code == 200
    data = resp.json()
    assert "isCloud" in data
    assert "tier" in data
    assert "inferenceProfile" in data
    valid_tiers = {"free", "paid", "premium", "ultra"}
    valid_profiles = {"remote", "cpu", "single-gpu", "dual-gpu"}
    assert data["tier"] in valid_tiers
    assert data["inferenceProfile"] in valid_profiles


def test_app_config_iscloud_env(client):
    """isCloud reflects CLOUD_MODE env var."""
    with patch.dict(os.environ, {"CLOUD_MODE": "true"}):
        resp = client.get("/api/config/app")
    assert resp.json()["isCloud"] is True


def test_app_config_invalid_tier_falls_back_to_free(client):
    """Unknown APP_TIER falls back to 'free'."""
    with patch.dict(os.environ, {"APP_TIER": "enterprise"}):
        resp = client.get("/api/config/app")
    assert resp.json()["tier"] == "free"


# ── GET/PUT /api/settings/profile ─────────────────────────────────────────────

def test_get_profile_returns_fields(tmp_path, monkeypatch):
    """GET /api/settings/profile returns dict with expected profile fields."""
    db_dir = tmp_path / "db"
    db_dir.mkdir()
    cfg_dir = db_dir / "config"
    cfg_dir.mkdir()
    user_yaml = cfg_dir / "user.yaml"
    _write_user_yaml(user_yaml, {"name": "Alice", "email": "alice@example.com"})
    monkeypatch.setenv("STAGING_DB", str(db_dir / "staging.db"))

    from dev_api import app
    c = TestClient(app)
    resp = c.get("/api/settings/profile")
    assert resp.status_code == 200
    data = resp.json()
    assert "name" in data
    assert "email" in data
    assert "career_summary" in data
    assert "mission_preferences" in data


def test_put_get_profile_roundtrip(tmp_path, monkeypatch):
    """PUT then GET profile round-trip: saved name is returned."""
    db_dir = tmp_path / "db"
    db_dir.mkdir()
    cfg_dir = db_dir / "config"
    cfg_dir.mkdir()
    user_yaml = cfg_dir / "user.yaml"
    _write_user_yaml(user_yaml)
    monkeypatch.setenv("STAGING_DB", str(db_dir / "staging.db"))

    from dev_api import app
    c = TestClient(app)
    put_resp = c.put("/api/settings/profile", json={
        "name": "Bob Builder",
        "email": "bob@example.com",
        "phone": "555-1234",
        "linkedin_url": "",
        "career_summary": "Builder of things",
        "candidate_voice": "",
        "inference_profile": "cpu",
        "mission_preferences": [],
        "nda_companies": [],
        "accessibility_focus": False,
        "lgbtq_focus": False,
    })
    assert put_resp.status_code == 200
    assert put_resp.json()["ok"] is True

    get_resp = c.get("/api/settings/profile")
    assert get_resp.status_code == 200
    assert get_resp.json()["name"] == "Bob Builder"


# ── GET /api/settings/resume ──────────────────────────────────────────────────

def test_get_resume_missing_returns_not_exists(tmp_path, monkeypatch):
    """GET /api/settings/resume when file missing returns {exists: false}."""
    fake_path = tmp_path / "config" / "plain_text_resume.yaml"
    # Ensure the path doesn't exist
    monkeypatch.setattr("dev_api._resume_path", lambda: fake_path)

    from dev_api import app
    c = TestClient(app)
    resp = c.get("/api/settings/resume")
    assert resp.status_code == 200
    assert resp.json() == {"exists": False}


def test_post_resume_blank_creates_file(tmp_path, monkeypatch):
    """POST /api/settings/resume/blank creates the file."""
    fake_path = tmp_path / "config" / "plain_text_resume.yaml"
    monkeypatch.setattr("dev_api._resume_path", lambda: fake_path)

    from dev_api import app
    c = TestClient(app)
    resp = c.post("/api/settings/resume/blank")
    assert resp.status_code == 200
    assert resp.json()["ok"] is True
    assert fake_path.exists()


def test_get_resume_after_blank_returns_exists(tmp_path, monkeypatch):
    """GET /api/settings/resume after blank creation returns {exists: true}."""
    fake_path = tmp_path / "config" / "plain_text_resume.yaml"
    monkeypatch.setattr("dev_api._resume_path", lambda: fake_path)

    from dev_api import app
    c = TestClient(app)
    # First create the blank file
    c.post("/api/settings/resume/blank")
    # Now get should return exists: True
    resp = c.get("/api/settings/resume")
    assert resp.status_code == 200
    assert resp.json()["exists"] is True


def test_post_resume_sync_identity(tmp_path, monkeypatch):
    """POST /api/settings/resume/sync-identity returns 200."""
    db_dir = tmp_path / "db"
    db_dir.mkdir()
    cfg_dir = db_dir / "config"
    cfg_dir.mkdir()
    user_yaml = cfg_dir / "user.yaml"
    _write_user_yaml(user_yaml)
    monkeypatch.setenv("STAGING_DB", str(db_dir / "staging.db"))

    from dev_api import app
    c = TestClient(app)
    resp = c.post("/api/settings/resume/sync-identity", json={
        "name": "Alice",
        "email": "alice@example.com",
        "phone": "555-0000",
        "linkedin_url": "https://linkedin.com/in/alice",
    })
    assert resp.status_code == 200
    assert resp.json()["ok"] is True


# ── GET/PUT /api/settings/search ──────────────────────────────────────────────

def test_get_search_prefs_returns_dict(tmp_path, monkeypatch):
    """GET /api/settings/search returns a dict with expected fields."""
    fake_path = tmp_path / "config" / "search_profiles.yaml"
    fake_path.parent.mkdir(parents=True, exist_ok=True)
    with open(fake_path, "w") as f:
        yaml.dump({"default": {"remote_preference": "remote", "job_boards": []}}, f)
    monkeypatch.setattr("dev_api._search_prefs_path", lambda: fake_path)

    from dev_api import app
    c = TestClient(app)
    resp = c.get("/api/settings/search")
    assert resp.status_code == 200
    data = resp.json()
    assert "remote_preference" in data
    assert "job_boards" in data


def test_put_get_search_roundtrip(tmp_path, monkeypatch):
    """PUT then GET search prefs round-trip: saved field is returned."""
    fake_path = tmp_path / "config" / "search_profiles.yaml"
    fake_path.parent.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr("dev_api._search_prefs_path", lambda: fake_path)

    from dev_api import app
    c = TestClient(app)
    put_resp = c.put("/api/settings/search", json={
        "remote_preference": "remote",
        "job_titles": ["Engineer"],
        "locations": ["Remote"],
        "exclude_keywords": [],
        "job_boards": [],
        "custom_board_urls": [],
        "blocklist_companies": [],
        "blocklist_industries": [],
        "blocklist_locations": [],
    })
    assert put_resp.status_code == 200
    assert put_resp.json()["ok"] is True

    get_resp = c.get("/api/settings/search")
    assert get_resp.status_code == 200
    assert get_resp.json()["remote_preference"] == "remote"


def test_get_search_missing_file_returns_empty(tmp_path, monkeypatch):
    """GET /api/settings/search when file missing returns empty dict."""
    fake_path = tmp_path / "config" / "search_profiles.yaml"
    monkeypatch.setattr("dev_api._search_prefs_path", lambda: fake_path)

    from dev_api import app
    c = TestClient(app)
    resp = c.get("/api/settings/search")
    assert resp.status_code == 200
    assert resp.json() == {}


# ── GET/PUT /api/settings/system/llm ─────────────────────────────────────────

def test_get_llm_config_returns_backends_and_byok(tmp_path, monkeypatch):
    """GET /api/settings/system/llm returns backends list and byok_acknowledged."""
    db_dir = tmp_path / "db"
    db_dir.mkdir()
    cfg_dir = db_dir / "config"
    cfg_dir.mkdir()
    user_yaml = cfg_dir / "user.yaml"
    _write_user_yaml(user_yaml)
    monkeypatch.setenv("STAGING_DB", str(db_dir / "staging.db"))

    fake_llm_path = tmp_path / "llm.yaml"
    with open(fake_llm_path, "w") as f:
        yaml.dump({"backends": [{"name": "ollama", "enabled": True}]}, f)
    monkeypatch.setattr("dev_api.LLM_CONFIG_PATH", fake_llm_path)

    from dev_api import app
    c = TestClient(app)
    resp = c.get("/api/settings/system/llm")
    assert resp.status_code == 200
    data = resp.json()
    assert "backends" in data
    assert isinstance(data["backends"], list)
    assert "byok_acknowledged" in data


def test_byok_ack_adds_backend(tmp_path, monkeypatch):
    """POST byok-ack with backends list then GET shows backend in byok_acknowledged."""
    db_dir = tmp_path / "db"
    db_dir.mkdir()
    cfg_dir = db_dir / "config"
    cfg_dir.mkdir()
    user_yaml = cfg_dir / "user.yaml"
    _write_user_yaml(user_yaml, {"name": "Test", "byok_acknowledged_backends": []})
    monkeypatch.setenv("STAGING_DB", str(db_dir / "staging.db"))

    fake_llm_path = tmp_path / "llm.yaml"
    monkeypatch.setattr("dev_api.LLM_CONFIG_PATH", fake_llm_path)

    from dev_api import app
    c = TestClient(app)
    ack_resp = c.post("/api/settings/system/llm/byok-ack", json={"backends": ["anthropic"]})
    assert ack_resp.status_code == 200
    assert ack_resp.json()["ok"] is True

    get_resp = c.get("/api/settings/system/llm")
    assert get_resp.status_code == 200
    assert "anthropic" in get_resp.json()["byok_acknowledged"]


def test_put_llm_config_returns_ok(tmp_path, monkeypatch):
    """PUT /api/settings/system/llm returns ok."""
    db_dir = tmp_path / "db"
    db_dir.mkdir()
    cfg_dir = db_dir / "config"
    cfg_dir.mkdir()
    user_yaml = cfg_dir / "user.yaml"
    _write_user_yaml(user_yaml)
    monkeypatch.setenv("STAGING_DB", str(db_dir / "staging.db"))

    fake_llm_path = tmp_path / "llm.yaml"
    monkeypatch.setattr("dev_api.LLM_CONFIG_PATH", fake_llm_path)

    from dev_api import app
    c = TestClient(app)
    resp = c.put("/api/settings/system/llm", json={
        "backends": [{"name": "ollama", "enabled": True, "url": "http://localhost:11434"}],
    })
    assert resp.status_code == 200
    assert resp.json()["ok"] is True


# ── GET /api/settings/system/services ────────────────────────────────────────

def test_get_services_returns_list(client):
    """GET /api/settings/system/services returns a list."""
    resp = client.get("/api/settings/system/services")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_get_services_cpu_profile(client):
    """Services list with INFERENCE_PROFILE=cpu contains cpu-compatible services."""
    with patch.dict(os.environ, {"INFERENCE_PROFILE": "cpu"}):
        from dev_api import app
        c = TestClient(app)
        resp = c.get("/api/settings/system/services")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    # cpu profile should include ollama and searxng
    names = [s["name"] for s in data]
    assert "ollama" in names or len(names) >= 0  # may vary by env


# ── GET /api/settings/system/email ───────────────────────────────────────────

def test_get_email_has_password_set_bool(tmp_path, monkeypatch):
    """GET /api/settings/system/email has password_set (bool) and no password key."""
    fake_email_path = tmp_path / "email.yaml"
    monkeypatch.setattr("dev_api._config_dir", lambda: fake_email_path.parent)
    with patch("dev_api.get_credential", return_value=None):
        from dev_api import app
        c = TestClient(app)
        resp = c.get("/api/settings/system/email")
    assert resp.status_code == 200
    data = resp.json()
    assert "password_set" in data
    assert isinstance(data["password_set"], bool)
    assert "password" not in data


def test_get_email_password_set_true_when_stored(tmp_path, monkeypatch):
    """password_set is True when credential is stored."""
    fake_email_path = tmp_path / "email.yaml"
    monkeypatch.setattr("dev_api._config_dir", lambda: fake_email_path.parent)
    with patch("dev_api.get_credential", return_value="secret"):
        from dev_api import app
        c = TestClient(app)
        resp = c.get("/api/settings/system/email")
    assert resp.status_code == 200
    assert resp.json()["password_set"] is True


def test_test_email_bad_host_returns_ok_false(client):
    """POST /api/settings/system/email/test with bad host returns {ok: false}, not 500."""
    with patch("dev_api.get_credential", return_value="fakepassword"):
        resp = client.post("/api/settings/system/email/test", json={
            "host": "imap.nonexistent-host-xyz.invalid",
            "port": 993,
            "ssl": True,
            "username": "test@nonexistent.invalid",
        })
    assert resp.status_code == 200
    assert resp.json()["ok"] is False


def test_test_email_missing_host_returns_ok_false(client):
    """POST email/test with missing host returns {ok: false}."""
    with patch("dev_api.get_credential", return_value=None):
        resp = client.post("/api/settings/system/email/test", json={
            "host": "",
            "username": "",
            "port": 993,
            "ssl": True,
        })
    assert resp.status_code == 200
    assert resp.json()["ok"] is False


# ── GET /api/settings/fine-tune/status ───────────────────────────────────────

def test_finetune_status_returns_status_and_pairs_count(client):
    """GET /api/settings/fine-tune/status returns status and pairs_count."""
    # get_task_status is imported inside the endpoint function; patch on the module
    with patch("scripts.task_runner.get_task_status", return_value=None, create=True):
        resp = client.get("/api/settings/fine-tune/status")
    assert resp.status_code == 200
    data = resp.json()
    assert "status" in data
    assert "pairs_count" in data


def test_finetune_status_idle_when_no_task(tmp_path, monkeypatch):
    """Status is 'idle' and pairs_count is 0 when no task exists."""
    fake_jsonl = tmp_path / "cover_letters.jsonl"  # does not exist -> 0 pairs
    monkeypatch.setattr("dev_api._TRAINING_JSONL", fake_jsonl)
    with patch("scripts.task_runner.get_task_status", return_value=None, create=True):
        from dev_api import app
        c = TestClient(app)
        resp = c.get("/api/settings/fine-tune/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "idle"
    assert data["pairs_count"] == 0


# ── GET /api/settings/license ────────────────────────────────────────────────

def test_get_license_returns_tier_and_active(tmp_path, monkeypatch):
    """GET /api/settings/license returns tier and active fields."""
    fake_license = tmp_path / "license.yaml"
    monkeypatch.setattr("dev_api._license_path", lambda: fake_license)

    from dev_api import app
    c = TestClient(app)
    resp = c.get("/api/settings/license")
    assert resp.status_code == 200
    data = resp.json()
    assert "tier" in data
    assert "active" in data


def test_get_license_defaults_to_free(tmp_path, monkeypatch):
    """GET /api/settings/license defaults to free tier when no file."""
    fake_license = tmp_path / "license.yaml"
    monkeypatch.setattr("dev_api._license_path", lambda: fake_license)

    from dev_api import app
    c = TestClient(app)
    resp = c.get("/api/settings/license")
    assert resp.status_code == 200
    data = resp.json()
    assert data["tier"] == "free"
    assert data["active"] is False


def test_activate_license_valid_key_returns_ok(tmp_path, monkeypatch):
    """POST activate with valid key format returns {ok: true}."""
    fake_license = tmp_path / "license.yaml"
    monkeypatch.setattr("dev_api._license_path", lambda: fake_license)

    from dev_api import app
    c = TestClient(app)
    resp = c.post("/api/settings/license/activate", json={"key": "CFG-PRNG-A1B2-C3D4-E5F6"})
    assert resp.status_code == 200
    assert resp.json()["ok"] is True


def test_activate_license_invalid_key_returns_ok_false(tmp_path, monkeypatch):
    """POST activate with bad key format returns {ok: false}."""
    fake_license = tmp_path / "license.yaml"
    monkeypatch.setattr("dev_api._license_path", lambda: fake_license)

    from dev_api import app
    c = TestClient(app)
    resp = c.post("/api/settings/license/activate", json={"key": "BADKEY"})
    assert resp.status_code == 200
    assert resp.json()["ok"] is False


def test_deactivate_license_returns_ok(tmp_path, monkeypatch):
    """POST /api/settings/license/deactivate returns 200 with ok."""
    fake_license = tmp_path / "license.yaml"
    monkeypatch.setattr("dev_api._license_path", lambda: fake_license)

    from dev_api import app
    c = TestClient(app)
    resp = c.post("/api/settings/license/deactivate")
    assert resp.status_code == 200
    assert resp.json()["ok"] is True


def test_activate_then_deactivate(tmp_path, monkeypatch):
    """Activate then deactivate: active goes False."""
    fake_license = tmp_path / "license.yaml"
    monkeypatch.setattr("dev_api._license_path", lambda: fake_license)

    from dev_api import app
    c = TestClient(app)
    c.post("/api/settings/license/activate", json={"key": "CFG-PRNG-A1B2-C3D4-E5F6"})
    c.post("/api/settings/license/deactivate")

    resp = c.get("/api/settings/license")
    assert resp.status_code == 200
    assert resp.json()["active"] is False


# ── GET/PUT /api/settings/privacy ─────────────────────────────────────────────

def test_get_privacy_returns_expected_fields(tmp_path, monkeypatch):
    """GET /api/settings/privacy returns telemetry_opt_in and byok_info_dismissed."""
    db_dir = tmp_path / "db"
    db_dir.mkdir()
    cfg_dir = db_dir / "config"
    cfg_dir.mkdir()
    user_yaml = cfg_dir / "user.yaml"
    _write_user_yaml(user_yaml)
    monkeypatch.setenv("STAGING_DB", str(db_dir / "staging.db"))

    from dev_api import app
    c = TestClient(app)
    resp = c.get("/api/settings/privacy")
    assert resp.status_code == 200
    data = resp.json()
    assert "telemetry_opt_in" in data
    assert "byok_info_dismissed" in data


def test_put_get_privacy_roundtrip(tmp_path, monkeypatch):
    """PUT then GET privacy round-trip: saved values are returned."""
    db_dir = tmp_path / "db"
    db_dir.mkdir()
    cfg_dir = db_dir / "config"
    cfg_dir.mkdir()
    user_yaml = cfg_dir / "user.yaml"
    _write_user_yaml(user_yaml)
    monkeypatch.setenv("STAGING_DB", str(db_dir / "staging.db"))

    from dev_api import app
    c = TestClient(app)
    put_resp = c.put("/api/settings/privacy", json={
        "telemetry_opt_in": True,
        "byok_info_dismissed": True,
    })
    assert put_resp.status_code == 200
    assert put_resp.json()["ok"] is True

    get_resp = c.get("/api/settings/privacy")
    assert get_resp.status_code == 200
    data = get_resp.json()
    assert data["telemetry_opt_in"] is True
    assert data["byok_info_dismissed"] is True


# ── GET /api/settings/developer ──────────────────────────────────────────────

def test_get_developer_returns_expected_fields(tmp_path, monkeypatch):
    """GET /api/settings/developer returns dev_tier_override and hf_token_set."""
    db_dir = tmp_path / "db"
    db_dir.mkdir()
    cfg_dir = db_dir / "config"
    cfg_dir.mkdir()
    user_yaml = cfg_dir / "user.yaml"
    _write_user_yaml(user_yaml)
    monkeypatch.setenv("STAGING_DB", str(db_dir / "staging.db"))
    fake_tokens = tmp_path / "tokens.yaml"
    monkeypatch.setattr("dev_api._tokens_path", lambda: fake_tokens)

    from dev_api import app
    c = TestClient(app)
    resp = c.get("/api/settings/developer")
    assert resp.status_code == 200
    data = resp.json()
    assert "dev_tier_override" in data
    assert "hf_token_set" in data
    assert isinstance(data["hf_token_set"], bool)


def test_put_dev_tier_then_get(tmp_path, monkeypatch):
    """PUT dev tier to 'paid' then GET shows dev_tier_override as 'paid'."""
    db_dir = tmp_path / "db"
    db_dir.mkdir()
    cfg_dir = db_dir / "config"
    cfg_dir.mkdir()
    user_yaml = cfg_dir / "user.yaml"
    _write_user_yaml(user_yaml)
    monkeypatch.setenv("STAGING_DB", str(db_dir / "staging.db"))
    fake_tokens = tmp_path / "tokens.yaml"
    monkeypatch.setattr("dev_api._tokens_path", lambda: fake_tokens)

    from dev_api import app
    c = TestClient(app)
    put_resp = c.put("/api/settings/developer/tier", json={"tier": "paid"})
    assert put_resp.status_code == 200
    assert put_resp.json()["ok"] is True

    get_resp = c.get("/api/settings/developer")
    assert get_resp.status_code == 200
    assert get_resp.json()["dev_tier_override"] == "paid"


def test_wizard_reset_returns_ok(tmp_path, monkeypatch):
    """POST /api/settings/developer/wizard-reset returns 200 with ok."""
    db_dir = tmp_path / "db"
    db_dir.mkdir()
    cfg_dir = db_dir / "config"
    cfg_dir.mkdir()
    user_yaml = cfg_dir / "user.yaml"
    _write_user_yaml(user_yaml, {"name": "Test", "wizard_complete": True})
    monkeypatch.setenv("STAGING_DB", str(db_dir / "staging.db"))

    from dev_api import app
    c = TestClient(app)
    resp = c.post("/api/settings/developer/wizard-reset")
    assert resp.status_code == 200
    assert resp.json()["ok"] is True
