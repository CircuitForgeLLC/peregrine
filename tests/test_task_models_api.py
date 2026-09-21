import yaml
from fastapi.testclient import TestClient

import dev_api


def _cfg_dir(tmp_path):
    cfg = tmp_path / "config"
    cfg.mkdir()
    return cfg


def _isolate_config(monkeypatch, cfg):
    """Point BOTH config surfaces at the test's tmp dir.

    The task-models endpoints read/write the file LLMRouter() itself reads
    (scripts.llm_router.CONFIG_PATH, i.e. <repo>/config/llm.yaml) -- NOT
    dev_api._config_dir(), which is the per-user data directory and a
    genuinely different path in the Docker deployment. _config_dir() is still
    redirected here because the capability-probe cache lives there.
    """
    monkeypatch.setattr(dev_api, "_config_dir", lambda: cfg)
    monkeypatch.setattr(dev_api, "LLM_ROUTER_CONFIG_PATH", cfg / "llm.yaml")


def test_get_task_models_returns_empty_when_unset(tmp_path, monkeypatch):
    cfg = _cfg_dir(tmp_path)
    _isolate_config(monkeypatch, cfg)
    client = TestClient(dev_api.app)
    resp = client.get("/api/settings/system/task-models")
    assert resp.status_code == 200
    body = resp.json()
    assert body["primary"] is None
    assert body["research"] is None
    assert body["chat"] is None


def test_get_task_models_returns_saved_assignments(tmp_path, monkeypatch):
    cfg = _cfg_dir(tmp_path)
    (cfg / "llm.yaml").write_text(yaml.dump({
        "task_models": {
            "research": {"backend": "ollama", "model": "llama3.1:8b"},
        }
    }))
    _isolate_config(monkeypatch, cfg)
    client = TestClient(dev_api.app)
    resp = client.get("/api/settings/system/task-models")
    body = resp.json()
    assert body["research"] == {"backend": "ollama", "model": "llama3.1:8b"}
    assert body["primary"] is None


def test_get_task_models_migrates_legacy_cover_letter_model_once(tmp_path, monkeypatch):
    cfg = _cfg_dir(tmp_path)
    (cfg / "llm.yaml").write_text(yaml.dump({
        "backends": {"cover_letter": {"type": "openai_compat", "model": "meghan-cover-writer:latest", "enabled": True}},
    }))
    _isolate_config(monkeypatch, cfg)
    client = TestClient(dev_api.app)
    resp = client.get("/api/settings/system/task-models")
    body = resp.json()
    assert body["primary"] == {"backend": "ollama", "model": "meghan-cover-writer:latest"}
    saved = yaml.safe_load((cfg / "llm.yaml").read_text())
    assert saved["task_models"]["primary"]["model"] == "meghan-cover-writer:latest"


def test_put_task_models_saves_assignments(tmp_path, monkeypatch):
    cfg = _cfg_dir(tmp_path)
    _isolate_config(monkeypatch, cfg)
    client = TestClient(dev_api.app)
    resp = client.put("/api/settings/system/task-models", json={
        "primary": {"backend": "ollama", "model": "meghan-cover-writer:latest"},
        "research": {"backend": "ollama", "model": "llama3.1:8b"},
        "chat": {"backend": "ollama", "model": "llama3.1:8b"},
    })
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}
    saved = yaml.safe_load((cfg / "llm.yaml").read_text())
    assert saved["task_models"]["primary"]["model"] == "meghan-cover-writer:latest"
    assert saved["task_models"]["research"]["model"] == "llama3.1:8b"


def test_put_task_models_can_clear_an_assignment(tmp_path, monkeypatch):
    cfg = _cfg_dir(tmp_path)
    (cfg / "llm.yaml").write_text(yaml.dump({
        "task_models": {"chat": {"backend": "ollama", "model": "llama3.1:8b"}},
    }))
    _isolate_config(monkeypatch, cfg)
    client = TestClient(dev_api.app)
    resp = client.put("/api/settings/system/task-models", json={"primary": None, "research": None, "chat": None})
    assert resp.status_code == 200
    saved = yaml.safe_load((cfg / "llm.yaml").read_text())
    assert saved["task_models"] == {"primary": None, "research": None, "chat": None}


def test_cover_letter_model_endpoints_removed(tmp_path, monkeypatch):
    client = TestClient(dev_api.app)
    resp = client.get("/api/settings/llm/cover-letter-model")
    assert resp.status_code == 404


def test_get_task_models_includes_ollama_models(tmp_path, monkeypatch):
    cfg = _cfg_dir(tmp_path)
    _isolate_config(monkeypatch, cfg)
    monkeypatch.setattr(dev_api, "get_ollama_models", lambda: {"models": ["llama3.1:8b", "mistral:7b"]})
    client = TestClient(dev_api.app)
    resp = client.get("/api/settings/system/task-models")
    body = resp.json()
    assert "ollama_models" in body
    assert isinstance(body["ollama_models"], list)
    assert body["ollama_models"] == ["llama3.1:8b", "mistral:7b"]


def test_get_task_models_writes_task_models_into_the_file_llmrouter_reads(tmp_path, monkeypatch):
    """Regression guard: the assignments must land in the same file
    LLMRouter() loads, or complete_task() would never see them."""
    from scripts.llm_router import LLMRouter
    cfg = _cfg_dir(tmp_path)
    (cfg / "llm.yaml").write_text(yaml.dump({
        "backends": {"ollama": {"type": "openai_compat", "model": "m", "enabled": True}},
        "fallback_order": ["ollama"],
    }))
    _isolate_config(monkeypatch, cfg)
    client = TestClient(dev_api.app)
    resp = client.put("/api/settings/system/task-models", json={
        "primary": None,
        "research": {"backend": "ollama", "model": "llama3.1:8b"},
        "chat": None,
    })
    assert resp.status_code == 200

    router = LLMRouter(cfg / "llm.yaml")
    assert router.config["task_models"]["research"] == {"backend": "ollama", "model": "llama3.1:8b"}
    # the pre-existing keys in that same file survived the write
    assert router.config["fallback_order"] == ["ollama"]


def test_get_task_models_returns_cached_probe_state_for_assigned_models(tmp_path, monkeypatch):
    cfg = _cfg_dir(tmp_path)
    (cfg / "llm.yaml").write_text(yaml.dump({
        "task_models": {"research": {"backend": "ollama", "model": "llama3.1:8b"}},
        "model_capability_probes": {
            "ollama:llama3.1:8b": {"structured_output": {"passed": False, "checked_at": "2026-09-18T00:00:00+00:00"}},
            "ollama:unassigned:7b": {"structured_output": {"passed": True, "checked_at": "2026-09-18T00:00:00+00:00"}},
        },
    }))
    _isolate_config(monkeypatch, cfg)
    client = TestClient(dev_api.app)
    body = client.get("/api/settings/system/task-models").json()
    assert body["probes"] == {"ollama:llama3.1:8b": {"passed": False}}


def test_get_task_models_probes_empty_when_never_probed(tmp_path, monkeypatch):
    cfg = _cfg_dir(tmp_path)
    (cfg / "llm.yaml").write_text(yaml.dump({
        "task_models": {"research": {"backend": "ollama", "model": "llama3.1:8b"}},
    }))
    _isolate_config(monkeypatch, cfg)
    client = TestClient(dev_api.app)
    assert client.get("/api/settings/system/task-models").json()["probes"] == {}


def test_get_task_models_cloud_mode_does_not_touch_shared_readonly_file(tmp_path):
    """Regression test for peregrine#173: in cloud mode, GET must never try
    to write to LLM_ROUTER_CONFIG_PATH (the shared file compose.cloud.yml
    mounts read-only) -- it must read/write a per-tenant file instead."""
    import os
    from unittest.mock import patch

    from fastapi.testclient import TestClient

    from dev_api import app

    shared_llm_yaml = tmp_path / "shared" / "llm.yaml"
    shared_llm_yaml.parent.mkdir(parents=True)
    shared_llm_yaml.write_text("backends: {}\nfallback_order: []\n")
    shared_llm_yaml.chmod(0o444)  # actually read-only, matching the real bug's failure mode

    tenant_db = tmp_path / "tenant" / "staging.db"

    client = TestClient(app)
    with patch.dict(os.environ, {"CLOUD_MODE": "true"}, clear=False), \
         patch("dev_api._CLOUD_MODE", True), \
         patch("dev_api.LLM_ROUTER_CONFIG_PATH", shared_llm_yaml), \
         patch("dev_api._request_db") as mock_ctx, \
         patch("dev_api.DB_PATH", str(tenant_db)):
        mock_ctx.get.return_value = str(tenant_db)
        r = client.get("/api/settings/system/task-models")

    assert r.status_code == 200
    shared_llm_yaml.chmod(0o644)  # restore for cleanup


def test_save_and_get_task_models_cloud_mode_persists_per_tenant(tmp_path):
    """Round-trip: cloud mode PUT then GET must return what was saved, from
    a per-tenant file under this tenant's own config dir."""
    import os
    from unittest.mock import patch

    from fastapi.testclient import TestClient

    from dev_api import app

    shared_llm_yaml = tmp_path / "shared" / "llm.yaml"
    shared_llm_yaml.parent.mkdir(parents=True)
    shared_llm_yaml.write_text("backends: {}\nfallback_order: []\n")

    tenant_db = tmp_path / "tenant" / "staging.db"

    client = TestClient(app)
    with patch.dict(os.environ, {"CLOUD_MODE": "true"}, clear=False), \
         patch("dev_api._CLOUD_MODE", True), \
         patch("dev_api.LLM_ROUTER_CONFIG_PATH", shared_llm_yaml), \
         patch("dev_api._request_db") as mock_ctx, \
         patch("dev_api.DB_PATH", str(tenant_db)):
        mock_ctx.get.return_value = str(tenant_db)
        put_resp = client.put("/api/settings/system/task-models", json={
            "primary": {"backend": "ollama", "model": "tenant-model"},
            "research": None,
            "chat": None,
        })
        assert put_resp.status_code == 200
        get_resp = client.get("/api/settings/system/task-models")

    assert get_resp.json()["primary"] == {"backend": "ollama", "model": "tenant-model"}

    # The shared file must remain byte-for-byte untouched.
    assert shared_llm_yaml.read_text() == "backends: {}\nfallback_order: []\n"

    # The per-tenant file must exist at the expected path.
    tenant_task_models_path = tenant_db.parent / "config" / "task_models.yaml"
    assert tenant_task_models_path.exists()
