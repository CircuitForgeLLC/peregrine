import yaml
from fastapi.testclient import TestClient


def _cfg_dir(tmp_path):
    cfg = tmp_path / "config"
    cfg.mkdir()
    return cfg


def test_get_task_models_returns_empty_when_unset(tmp_path, monkeypatch):
    import dev_api
    cfg = _cfg_dir(tmp_path)
    monkeypatch.setattr(dev_api, "_config_dir", lambda: cfg)
    client = TestClient(dev_api.app)
    resp = client.get("/api/settings/system/task-models")
    assert resp.status_code == 200
    body = resp.json()
    assert body["primary"] is None
    assert body["research"] is None
    assert body["chat"] is None


def test_get_task_models_returns_saved_assignments(tmp_path, monkeypatch):
    import dev_api
    cfg = _cfg_dir(tmp_path)
    (cfg / "llm.yaml").write_text(yaml.dump({
        "task_models": {
            "research": {"backend": "ollama", "model": "llama3.1:8b"},
        }
    }))
    monkeypatch.setattr(dev_api, "_config_dir", lambda: cfg)
    client = TestClient(dev_api.app)
    resp = client.get("/api/settings/system/task-models")
    body = resp.json()
    assert body["research"] == {"backend": "ollama", "model": "llama3.1:8b"}
    assert body["primary"] is None


def test_get_task_models_migrates_legacy_cover_letter_model_once(tmp_path, monkeypatch):
    import dev_api
    cfg = _cfg_dir(tmp_path)
    (cfg / "llm.yaml").write_text(yaml.dump({
        "backends": {"cover_letter": {"type": "openai_compat", "model": "meghan-cover-writer:latest", "enabled": True}},
    }))
    monkeypatch.setattr(dev_api, "_config_dir", lambda: cfg)
    client = TestClient(dev_api.app)
    resp = client.get("/api/settings/system/task-models")
    body = resp.json()
    assert body["primary"] == {"backend": "ollama", "model": "meghan-cover-writer:latest"}
    saved = yaml.safe_load((cfg / "llm.yaml").read_text())
    assert saved["task_models"]["primary"]["model"] == "meghan-cover-writer:latest"


def test_put_task_models_saves_assignments(tmp_path, monkeypatch):
    import dev_api
    cfg = _cfg_dir(tmp_path)
    monkeypatch.setattr(dev_api, "_config_dir", lambda: cfg)
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
    import dev_api
    cfg = _cfg_dir(tmp_path)
    (cfg / "llm.yaml").write_text(yaml.dump({
        "task_models": {"chat": {"backend": "ollama", "model": "llama3.1:8b"}},
    }))
    monkeypatch.setattr(dev_api, "_config_dir", lambda: cfg)
    client = TestClient(dev_api.app)
    resp = client.put("/api/settings/system/task-models", json={"primary": None, "research": None, "chat": None})
    assert resp.status_code == 200
    saved = yaml.safe_load((cfg / "llm.yaml").read_text())
    assert saved["task_models"] == {"primary": None, "research": None, "chat": None}


def test_cover_letter_model_endpoints_removed(tmp_path, monkeypatch):
    import dev_api
    client = TestClient(dev_api.app)
    resp = client.get("/api/settings/llm/cover-letter-model")
    assert resp.status_code == 404


def test_get_task_models_includes_ollama_models(tmp_path, monkeypatch):
    import dev_api
    cfg = _cfg_dir(tmp_path)
    monkeypatch.setattr(dev_api, "_config_dir", lambda: cfg)
    monkeypatch.setattr(dev_api, "get_ollama_models", lambda: {"models": ["llama3.1:8b", "mistral:7b"]})
    client = TestClient(dev_api.app)
    resp = client.get("/api/settings/system/task-models")
    body = resp.json()
    assert "ollama_models" in body
    assert isinstance(body["ollama_models"], list)
    assert body["ollama_models"] == ["llama3.1:8b", "mistral:7b"]
