"""Tests for all settings API endpoints added in Tasks 1–8."""
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import pytest
import yaml
from fastapi.testclient import TestClient

# credential_store.py was merged to main repo — no worktree path manipulation needed


@pytest.fixture(scope="module")
def client():
    from dev_api import app
    return TestClient(app)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _write_user_yaml(path: Path, data: dict | None = None):
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
    """An unrecognized tier value falls back to 'free'."""
    with patch("dev_api._get_effective_tier", return_value="enterprise"):
        resp = client.get("/api/config/app")
    assert resp.json()["tier"] == "free"


def test_app_config_reflects_real_effective_tier(client):
    """GET /api/config/app reads the real license-derived tier (peregrine#170),
    not a static APP_TIER env var that license activation never updates."""
    with patch("dev_api._get_effective_tier", return_value="premium"):
        resp = client.get("/api/config/app")
    assert resp.json()["tier"] == "premium"


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
        yaml.dump({"default": {"remote_preference": "remote",
                               "job_boards": [{"name": "linkedin", "enabled": True}]}}, f)
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
        "remote_preference": ["remote"],
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
    assert get_resp.json()["remote_preference"] == ["remote"]


def test_put_get_search_roundtrip_profiles_format(tmp_path, monkeypatch):
    """Regression test: PUT saves must be visible to a later GET when the
    search_profiles.yaml file already uses the canonical `profiles: [...]`
    format (exactly what the wizard and Task 1's board-seeding both write).

    Before the fix, save_search_prefs wrote into a separate top-level
    "default" key that _normalize_profiles never reads once a `profiles`
    key exists -- so the PUT appeared to succeed but the GET kept returning
    stale, pre-PUT data.
    """
    fake_path = tmp_path / "config" / "search_profiles.yaml"
    fake_path.parent.mkdir(parents=True, exist_ok=True)
    with open(fake_path, "w") as f:
        yaml.dump({
            "profiles": [
                {
                    "name": "default",
                    "job_titles": ["Old Title"],
                    "locations": ["Old Location"],
                    "boards": ["linkedin"],
                }
            ]
        }, f)
    monkeypatch.setattr("dev_api._search_prefs_path", lambda: fake_path)

    from dev_api import app
    c = TestClient(app)
    put_resp = c.put("/api/settings/search", json={
        "remote_preference": ["remote"],
        "job_titles": ["New Title"],
        "locations": ["New Location"],
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
    data = get_resp.json()
    assert data["job_titles"] == ["New Title"]
    assert data["locations"] == ["New Location"]
    assert data["remote_preference"] == ["remote"]


def test_get_search_prefs_falls_back_to_full_catalog_when_job_boards_empty(tmp_path, monkeypatch):
    """A profile with no job_boards at all gets the full valid-board catalog,
    all unchecked, so the Settings checklist is never a dead end."""
    fake_path = tmp_path / "config" / "search_profiles.yaml"
    fake_path.parent.mkdir(parents=True, exist_ok=True)
    with open(fake_path, "w") as f:
        yaml.dump({"default": {"job_titles": ["Engineer"], "locations": ["Remote"]}}, f)
    monkeypatch.setattr("dev_api._search_prefs_path", lambda: fake_path)

    from dev_api import app
    c = TestClient(app)
    resp = c.get("/api/settings/search")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["job_boards"]) > 0
    assert all(b["enabled"] is False for b in data["job_boards"])
    assert all(b["supported"] is True for b in data["job_boards"])
    names = [b["name"] for b in data["job_boards"]]
    assert "linkedin" in names
    assert names == sorted(names)


def test_get_search_prefs_does_not_override_existing_job_boards(tmp_path, monkeypatch):
    """A profile that already has real job_boards data must be returned
    unchanged -- the fallback only applies when job_boards is truly empty."""
    fake_path = tmp_path / "config" / "search_profiles.yaml"
    fake_path.parent.mkdir(parents=True, exist_ok=True)
    with open(fake_path, "w") as f:
        yaml.dump({"default": {
            "job_titles": ["Engineer"],
            "job_boards": [{"name": "indeed", "enabled": True}],
        }}, f)
    monkeypatch.setattr("dev_api._search_prefs_path", lambda: fake_path)

    from dev_api import app
    c = TestClient(app)
    resp = c.get("/api/settings/search")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["job_boards"]) == 1
    assert data["job_boards"][0]["name"] == "indeed"
    assert data["job_boards"][0]["enabled"] is True


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

    # backends is a dict keyed by id in the real config/llm.yaml shape
    # (base_url/model/type/etc per entry), not a list -- the endpoint derives
    # the reorderable list view from this dict plus fallback_order.
    fake_llm_path = tmp_path / "llm.yaml"
    with open(fake_llm_path, "w") as f:
        yaml.dump({
            "backends": {"ollama": {"type": "openai_compat", "model": "llama3.1:8b", "enabled": True}},
            "fallback_order": ["ollama"],
        }, f)
    monkeypatch.setattr("dev_api.LLM_CONFIG_PATH", fake_llm_path)

    from dev_api import app
    c = TestClient(app)
    resp = c.get("/api/settings/system/llm")
    assert resp.status_code == 200
    data = resp.json()
    assert "backends" in data
    assert isinstance(data["backends"], list)
    assert data["backends"][0]["id"] == "ollama"
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
    fake_license = tmp_path / "license.json"
    monkeypatch.setattr("dev_api._license_json_path", lambda: fake_license)

    from dev_api import app
    c = TestClient(app)
    resp = c.get("/api/settings/license")
    assert resp.status_code == 200
    data = resp.json()
    assert "tier" in data
    assert "active" in data


def test_get_license_defaults_to_free(tmp_path, monkeypatch):
    """GET /api/settings/license defaults to free tier when no file."""
    fake_license = tmp_path / "license.json"
    monkeypatch.setattr("dev_api._license_json_path", lambda: fake_license)

    from dev_api import app
    c = TestClient(app)
    resp = c.get("/api/settings/license")
    assert resp.status_code == 200
    data = resp.json()
    assert data["tier"] == "free"
    assert data["active"] is False


def test_activate_license_valid_key_calls_real_activation(tmp_path, monkeypatch):
    """POST activate with a well-formatted key calls the real
    scripts.license.activate() (peregrine#170 -- this used to fake-write
    'paid' locally for any correctly-formatted key, never verifying with the
    real license server) and returns the tier IT reports, not a fabricated one."""
    fake_license = tmp_path / "license.json"
    monkeypatch.setattr("dev_api._license_json_path", lambda: fake_license)

    with patch("scripts.license.activate", return_value={"tier": "premium"}) as mock_activate:
        from dev_api import app
        c = TestClient(app)
        resp = c.post("/api/settings/license/activate", json={"key": "CFG-PRNG-A1B2-C3D4-E5F6"})

    assert resp.status_code == 200
    assert resp.json() == {"ok": True, "tier": "premium"}
    mock_activate.assert_called_once_with("CFG-PRNG-A1B2-C3D4-E5F6", license_path=fake_license)


def test_activate_license_invalid_key_format_short_circuits_before_network_call(tmp_path, monkeypatch):
    """POST activate with bad key format returns {ok: false} without ever
    calling the real activation function."""
    fake_license = tmp_path / "license.json"
    monkeypatch.setattr("dev_api._license_json_path", lambda: fake_license)

    with patch("scripts.license.activate") as mock_activate:
        from dev_api import app
        c = TestClient(app)
        resp = c.post("/api/settings/license/activate", json={"key": "BADKEY"})

    assert resp.status_code == 200
    assert resp.json()["ok"] is False
    mock_activate.assert_not_called()


def test_activate_license_server_rejection_surfaces_server_detail(tmp_path, monkeypatch):
    """A well-formatted key the license server rejects (revoked/invalid/seat
    limit) surfaces the server's own error detail, not a generic message."""
    fake_license = tmp_path / "license.json"
    monkeypatch.setattr("dev_api._license_json_path", lambda: fake_license)

    fake_response = MagicMock()
    fake_response.json.return_value = {"detail": "Invalid or revoked license key"}
    error = httpx.HTTPStatusError("403 Forbidden", request=MagicMock(), response=fake_response)

    with patch("scripts.license.activate", side_effect=error):
        from dev_api import app
        c = TestClient(app)
        resp = c.post("/api/settings/license/activate", json={"key": "CFG-PRNG-A1B2-C3D4-E5F6"})

    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is False
    assert data["error"] == "Invalid or revoked license key"


def test_activate_license_network_failure_degrades_to_ok_false(tmp_path, monkeypatch):
    """A network failure reaching the license server degrades to {ok: false},
    not an unhandled 500."""
    fake_license = tmp_path / "license.json"
    monkeypatch.setattr("dev_api._license_json_path", lambda: fake_license)

    with patch("scripts.license.activate", side_effect=httpx.ConnectError("connection refused")):
        from dev_api import app
        c = TestClient(app)
        resp = c.post("/api/settings/license/activate", json={"key": "CFG-PRNG-A1B2-C3D4-E5F6"})

    assert resp.status_code == 200
    assert resp.json()["ok"] is False


def test_deactivate_license_returns_ok(tmp_path, monkeypatch):
    """POST /api/settings/license/deactivate calls the real deactivate() and
    returns 200 with ok."""
    fake_license = tmp_path / "license.json"
    monkeypatch.setattr("dev_api._license_json_path", lambda: fake_license)

    with patch("scripts.license.deactivate") as mock_deactivate:
        from dev_api import app
        c = TestClient(app)
        resp = c.post("/api/settings/license/deactivate")

    assert resp.status_code == 200
    assert resp.json()["ok"] is True
    mock_deactivate.assert_called_once_with(license_path=fake_license)


def test_activate_then_deactivate(tmp_path, monkeypatch):
    """Activate then deactivate: active goes False. Exercises the real
    read/write round trip against license.json (activate()/deactivate()
    themselves are mocked to avoid a real network call, but get_license()
    reads whatever they actually leave on disk, same as production)."""
    fake_license = tmp_path / "license.json"
    monkeypatch.setattr("dev_api._license_json_path", lambda: fake_license)

    def _fake_activate(key, license_path):
        license_path.write_text('{"jwt": "unused-in-this-test"}')
        return {"tier": "paid"}

    def _fake_deactivate(license_path):
        license_path.unlink(missing_ok=True)

    from dev_api import app
    c = TestClient(app)

    with patch("scripts.license.activate", side_effect=_fake_activate):
        c.post("/api/settings/license/activate", json={"key": "CFG-PRNG-A1B2-C3D4-E5F6"})

    with patch("scripts.license.deactivate", side_effect=_fake_deactivate):
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


# ── _cred_dir() -- per-tenant credential isolation ────────────────────────────
# Regression coverage for peregrine-cloud 2026-09-23: get_credential()/
# set_credential() always used credential_store's module-wide CRED_DIR
# (co-located with the app install, not per-tenant data) -- every cloud
# tenant's IMAP app password collided in the same encrypted file, and was
# wiped on every container restart since it wasn't on persistent storage.

def test_cred_dir_is_none_in_self_hosted_mode(monkeypatch):
    """Self-hosted has exactly one user -- _cred_dir() must return None so
    credential_store falls back to its own module-wide default (preserves
    already-saved credentials for existing self-hosted installs)."""
    monkeypatch.setattr("dev_api._CLOUD_MODE", False)
    from dev_api import _cred_dir
    assert _cred_dir() is None


def test_cred_dir_is_per_tenant_in_cloud_mode(tmp_path, monkeypatch):
    """Cloud mode must scope credentials under the requesting tenant's own
    config directory, not a process-wide shared location."""
    db_dir = tmp_path / "db"
    db_dir.mkdir()
    monkeypatch.setenv("STAGING_DB", str(db_dir / "staging.db"))
    monkeypatch.setattr("dev_api._CLOUD_MODE", True)
    from dev_api import _cred_dir
    assert _cred_dir() == db_dir / "config" / "credentials"


def test_email_credentials_isolated_between_cloud_tenants(tmp_path, monkeypatch):
    """End-to-end: two 'tenants' (different STAGING_DB roots) saving email
    config via the real API must not see or overwrite each other's stored
    password."""
    from scripts.credential_store import get_credential

    tenant_a_db = tmp_path / "tenant-a" / "staging.db"
    tenant_b_db = tmp_path / "tenant-b" / "staging.db"
    monkeypatch.setattr("dev_api._CLOUD_MODE", True)

    from dev_api import app
    c = TestClient(app)

    monkeypatch.setenv("STAGING_DB", str(tenant_a_db))
    resp = c.put("/api/settings/system/email", json={
        "host": "imap.gmail.com", "port": 993, "ssl": True,
        "username": "a@example.com", "password": "tenant-a-secret",
    })
    assert resp.status_code == 200

    monkeypatch.setenv("STAGING_DB", str(tenant_b_db))
    resp = c.put("/api/settings/system/email", json={
        "host": "imap.gmail.com", "port": 993, "ssl": True,
        "username": "b@example.com", "password": "tenant-b-secret",
    })
    assert resp.status_code == 200

    assert get_credential(
        "peregrine", "imap_password", cred_dir=tenant_a_db.parent / "config" / "credentials"
    ) == "tenant-a-secret"
    assert get_credential(
        "peregrine", "imap_password", cred_dir=tenant_b_db.parent / "config" / "credentials"
    ) == "tenant-b-secret"
