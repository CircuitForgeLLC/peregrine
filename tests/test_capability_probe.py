from unittest.mock import patch
import yaml


def _cfg_dir(tmp_path):
    cfg = tmp_path / "config"
    cfg.mkdir()
    return cfg


def test_probe_model_capability_passes_on_valid_json_array(tmp_path, monkeypatch):
    import dev_api
    cfg = _cfg_dir(tmp_path)
    monkeypatch.setattr(dev_api, "_config_dir", lambda: cfg)
    with patch("scripts.llm_router.LLMRouter.complete", return_value='["a", "b"]'):
        result = dev_api._probe_model_capability("ollama", "llama3.1:8b")
    assert result["passed"] is True
    assert "checked_at" in result
    saved = yaml.safe_load((cfg / "llm.yaml").read_text())
    assert saved["model_capability_probes"]["ollama:llama3.1:8b"]["structured_output"]["passed"] is True


def test_probe_model_capability_fails_on_empty_response(tmp_path, monkeypatch):
    import dev_api
    cfg = _cfg_dir(tmp_path)
    monkeypatch.setattr(dev_api, "_config_dir", lambda: cfg)
    with patch("scripts.llm_router.LLMRouter.complete", return_value=""):
        result = dev_api._probe_model_capability("ollama", "meghan-cover-writer:latest")
    assert result["passed"] is False


def test_probe_model_capability_fails_on_non_json_prose(tmp_path, monkeypatch):
    import dev_api
    cfg = _cfg_dir(tmp_path)
    monkeypatch.setattr(dev_api, "_config_dir", lambda: cfg)
    with patch("scripts.llm_router.LLMRouter.complete", return_value="I can't do that."):
        result = dev_api._probe_model_capability("ollama", "meghan-cover-writer:latest")
    assert result["passed"] is False


def test_get_cached_probe_returns_none_when_never_run(tmp_path, monkeypatch):
    import dev_api
    cfg = _cfg_dir(tmp_path)
    monkeypatch.setattr(dev_api, "_config_dir", lambda: cfg)
    assert dev_api._get_cached_probe("ollama", "llama3.1:8b") is None


def test_get_cached_probe_returns_prior_result(tmp_path, monkeypatch):
    import dev_api
    cfg = _cfg_dir(tmp_path)
    monkeypatch.setattr(dev_api, "_config_dir", lambda: cfg)
    with patch("scripts.llm_router.LLMRouter.complete", return_value='["a", "b"]'):
        dev_api._probe_model_capability("ollama", "llama3.1:8b")
    cached = dev_api._get_cached_probe("ollama", "llama3.1:8b")
    assert cached["passed"] is True


def test_probe_model_endpoint_returns_error_when_backend_unreachable(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    import dev_api
    cfg = _cfg_dir(tmp_path)
    monkeypatch.setattr(dev_api, "_config_dir", lambda: cfg)
    client = TestClient(dev_api.app)
    with patch("scripts.llm_router.LLMRouter.complete", side_effect=RuntimeError("unreachable")):
        resp = client.post("/api/settings/system/probe-model", json={"backend": "ollama", "model": "llama3.1:8b"})
    assert resp.status_code == 200
    body = resp.json()
    assert body.get("error") == "unreachable"
    # distinct from a failed probe -- never conflated with passed: false
    assert "passed" not in body
