import os
from unittest.mock import patch

import yaml
from fastapi.testclient import TestClient

from dev_api import app

client = TestClient(app)


def _write_user_yaml(path, data=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data or {}))


def _read_user_yaml(path):
    return yaml.safe_load(path.read_text())


class TestLlmBackendSettings:
    def test_get_returns_key_presence_not_plaintext(self, tmp_path):
        yaml_path = tmp_path / "config" / "user.yaml"
        _write_user_yaml(yaml_path, {"services": {"ollama_host": "10.1.10.5", "ollama_port": 11500}})
        env_path = tmp_path / ".env"
        env_path.write_text("ANTHROPIC_API_KEY=sk-ant-secret\n")
        with patch("dev_api._wizard_yaml_path", return_value=str(yaml_path)):
            with patch("dev_api._env_path", return_value=env_path):
                r = client.get("/api/settings/system/llm-backend")
        assert r.status_code == 200
        body = r.json()
        assert body["anthropic_key_set"] is True
        assert "sk-ant-secret" not in r.text
        assert body["ollama_host"] == "10.1.10.5"
        assert body["ollama_port"] == 11500

    def test_get_returns_defaults_when_nothing_configured(self, tmp_path):
        yaml_path = tmp_path / "config" / "user.yaml"
        _write_user_yaml(yaml_path, {})
        env_path = tmp_path / ".env"
        with patch("dev_api._wizard_yaml_path", return_value=str(yaml_path)):
            with patch("dev_api._env_path", return_value=env_path):
                r = client.get("/api/settings/system/llm-backend")
        assert r.status_code == 200
        body = r.json()
        assert body["anthropic_key_set"] is False
        assert body["openai_key_set"] is False
        assert body["ollama_host"] == ""
        assert body["ollama_port"] == 11434

    def test_post_writes_anthropic_key_to_env(self, tmp_path):
        yaml_path = tmp_path / "config" / "user.yaml"
        _write_user_yaml(yaml_path, {})
        env_path = tmp_path / ".env"
        with patch("dev_api._wizard_yaml_path", return_value=str(yaml_path)):
            with patch("dev_api._env_path", return_value=env_path):
                r = client.post("/api/settings/system/llm-backend", json={
                    "anthropic_key": "sk-ant-new",
                })
        assert r.status_code == 200
        assert "ANTHROPIC_API_KEY=sk-ant-new" in env_path.read_text()

    def test_post_preserves_existing_env_lines_not_touched(self, tmp_path):
        yaml_path = tmp_path / "config" / "user.yaml"
        _write_user_yaml(yaml_path, {})
        env_path = tmp_path / ".env"
        env_path.write_text("SOME_OTHER_KEY=unrelated\n")
        with patch("dev_api._wizard_yaml_path", return_value=str(yaml_path)):
            with patch("dev_api._env_path", return_value=env_path):
                client.post("/api/settings/system/llm-backend", json={"anthropic_key": "sk-ant-new"})
        content = env_path.read_text()
        assert "SOME_OTHER_KEY=unrelated" in content
        assert "ANTHROPIC_API_KEY=sk-ant-new" in content

    def test_post_writes_services_to_user_yaml(self, tmp_path):
        yaml_path = tmp_path / "config" / "user.yaml"
        _write_user_yaml(yaml_path, {})
        env_path = tmp_path / ".env"
        with patch("dev_api._wizard_yaml_path", return_value=str(yaml_path)):
            with patch("dev_api._env_path", return_value=env_path):
                r = client.post("/api/settings/system/llm-backend", json={
                    "ollama_host": "10.1.10.5",
                    "ollama_port": 11500,
                })
        assert r.status_code == 200
        saved = _read_user_yaml(yaml_path)
        assert saved["services"]["ollama_host"] == "10.1.10.5"
        assert saved["services"]["ollama_port"] == 11500

    def test_post_preserves_unrelated_existing_services_keys(self, tmp_path):
        yaml_path = tmp_path / "config" / "user.yaml"
        _write_user_yaml(yaml_path, {"services": {
            "vllm_host": "10.1.10.9",
            "ollama_host": "old-host",
        }})
        env_path = tmp_path / ".env"
        with patch("dev_api._wizard_yaml_path", return_value=str(yaml_path)):
            with patch("dev_api._env_path", return_value=env_path):
                r = client.post("/api/settings/system/llm-backend", json={
                    "ollama_host": "10.1.10.5",
                })
        assert r.status_code == 200
        saved = _read_user_yaml(yaml_path)
        assert saved["services"]["vllm_host"] == "10.1.10.9"
        assert saved["services"]["ollama_host"] == "10.1.10.5"

    def test_post_writes_inference_profile_to_user_yaml(self, tmp_path):
        yaml_path = tmp_path / "config" / "user.yaml"
        _write_user_yaml(yaml_path, {})
        env_path = tmp_path / ".env"
        with patch("dev_api._wizard_yaml_path", return_value=str(yaml_path)):
            with patch("dev_api._env_path", return_value=env_path):
                r = client.post("/api/settings/system/llm-backend", json={
                    "inference_profile": "dual-gpu",
                })
        assert r.status_code == 200
        saved = _read_user_yaml(yaml_path)
        assert saved["inference_profile"] == "dual-gpu"

    def test_post_blank_inference_profile_does_not_clobber_existing(self, tmp_path):
        yaml_path = tmp_path / "config" / "user.yaml"
        _write_user_yaml(yaml_path, {"inference_profile": "single-gpu"})
        env_path = tmp_path / ".env"
        with patch("dev_api._wizard_yaml_path", return_value=str(yaml_path)):
            with patch("dev_api._env_path", return_value=env_path):
                r = client.post("/api/settings/system/llm-backend", json={
                    "ollama_host": "10.1.10.5",
                })
        assert r.status_code == 200
        saved = _read_user_yaml(yaml_path)
        assert saved["inference_profile"] == "single-gpu"

    def test_get_returns_inference_profile(self, tmp_path):
        yaml_path = tmp_path / "config" / "user.yaml"
        _write_user_yaml(yaml_path, {"inference_profile": "cpu"})
        env_path = tmp_path / ".env"
        with patch("dev_api._wizard_yaml_path", return_value=str(yaml_path)):
            with patch("dev_api._env_path", return_value=env_path):
                r = client.get("/api/settings/system/llm-backend")
        assert r.status_code == 200
        assert r.json()["inference_profile"] == "cpu"

    def test_post_blank_key_does_not_overwrite_existing_env_value(self, tmp_path):
        yaml_path = tmp_path / "config" / "user.yaml"
        _write_user_yaml(yaml_path, {})
        env_path = tmp_path / ".env"
        env_path.write_text("ANTHROPIC_API_KEY=sk-ant-keepme\n")
        with patch("dev_api._wizard_yaml_path", return_value=str(yaml_path)):
            with patch("dev_api._env_path", return_value=env_path):
                client.post("/api/settings/system/llm-backend", json={"anthropic_key": ""})
        assert "ANTHROPIC_API_KEY=sk-ant-keepme" in env_path.read_text()

    def test_post_rejects_newline_in_anthropic_key(self, tmp_path):
        yaml_path = tmp_path / "config" / "user.yaml"
        _write_user_yaml(yaml_path, {})
        env_path = tmp_path / ".env"
        with patch("dev_api._wizard_yaml_path", return_value=str(yaml_path)):
            with patch("dev_api._env_path", return_value=env_path):
                r = client.post("/api/settings/system/llm-backend", json={
                    "anthropic_key": "x\nGPU_SERVER_URL=http://evil",
                })
        assert r.status_code == 400
        assert not env_path.exists()

    def test_post_rejects_newline_in_openai_url_and_key(self, tmp_path):
        yaml_path = tmp_path / "config" / "user.yaml"
        _write_user_yaml(yaml_path, {})
        env_path = tmp_path / ".env"
        with patch("dev_api._wizard_yaml_path", return_value=str(yaml_path)):
            with patch("dev_api._env_path", return_value=env_path):
                r = client.post("/api/settings/system/llm-backend", json={
                    "openai_url": "http://x\r\nEVIL=1",
                })
        assert r.status_code == 400
        assert not env_path.exists()

        with patch("dev_api._wizard_yaml_path", return_value=str(yaml_path)):
            with patch("dev_api._env_path", return_value=env_path):
                r = client.post("/api/settings/system/llm-backend", json={
                    "openai_key": "sk-x\nEVIL=1",
                })
        assert r.status_code == 400
        assert not env_path.exists()

    def test_post_sets_env_file_permissions_to_owner_only(self, tmp_path):
        yaml_path = tmp_path / "config" / "user.yaml"
        _write_user_yaml(yaml_path, {})
        env_path = tmp_path / ".env"
        with patch("dev_api._wizard_yaml_path", return_value=str(yaml_path)):
            with patch("dev_api._env_path", return_value=env_path):
                r = client.post("/api/settings/system/llm-backend", json={
                    "anthropic_key": "sk-ant-new",
                })
        assert r.status_code == 200
        mode = os.stat(env_path).st_mode & 0o777
        assert mode == 0o600


class TestOllamaModelConfig:
    def test_get_returns_configured_ollama_model(self, tmp_path):
        yaml_path = tmp_path / "config" / "user.yaml"
        _write_user_yaml(yaml_path, {})
        llm_yaml_path = tmp_path / "config" / "llm.yaml"
        llm_yaml_path.parent.mkdir(parents=True, exist_ok=True)
        llm_yaml_path.write_text(yaml.safe_dump({
            "backends": {"ollama": {"model": "llama3.1:8b", "type": "openai_compat"}},
        }))
        env_path = tmp_path / ".env"
        with patch("dev_api._wizard_yaml_path", return_value=str(yaml_path)):
            with patch("dev_api._env_path", return_value=env_path):
                with patch("dev_api.LLM_CONFIG_PATH", llm_yaml_path):
                    r = client.get("/api/settings/system/llm-backend")
        assert r.status_code == 200
        assert r.json()["ollama_model"] == "llama3.1:8b"

    def test_get_returns_empty_ollama_model_when_llm_yaml_missing(self, tmp_path):
        yaml_path = tmp_path / "config" / "user.yaml"
        _write_user_yaml(yaml_path, {})
        llm_yaml_path = tmp_path / "config" / "llm.yaml"
        env_path = tmp_path / ".env"
        with patch("dev_api._wizard_yaml_path", return_value=str(yaml_path)):
            with patch("dev_api._env_path", return_value=env_path):
                with patch("dev_api.LLM_CONFIG_PATH", llm_yaml_path):
                    r = client.get("/api/settings/system/llm-backend")
        assert r.status_code == 200
        assert r.json()["ollama_model"] == ""

    def test_post_writes_ollama_model_to_llm_yaml(self, tmp_path):
        yaml_path = tmp_path / "config" / "user.yaml"
        _write_user_yaml(yaml_path, {})
        llm_yaml_path = tmp_path / "config" / "llm.yaml"
        llm_yaml_path.parent.mkdir(parents=True, exist_ok=True)
        llm_yaml_path.write_text(yaml.safe_dump({
            "backends": {"ollama": {"model": "llama3.2:3b", "type": "openai_compat"}},
        }))
        env_path = tmp_path / ".env"
        with patch("dev_api._wizard_yaml_path", return_value=str(yaml_path)):
            with patch("dev_api._env_path", return_value=env_path):
                with patch("dev_api.LLM_CONFIG_PATH", llm_yaml_path):
                    r = client.post("/api/settings/system/llm-backend", json={
                        "ollama_model": "llama3.1:8b",
                    })
        assert r.status_code == 200
        saved = yaml.safe_load(llm_yaml_path.read_text())
        assert saved["backends"]["ollama"]["model"] == "llama3.1:8b"

    def test_post_preserves_other_llm_yaml_backends_on_model_change(self, tmp_path):
        yaml_path = tmp_path / "config" / "user.yaml"
        _write_user_yaml(yaml_path, {})
        llm_yaml_path = tmp_path / "config" / "llm.yaml"
        llm_yaml_path.parent.mkdir(parents=True, exist_ok=True)
        llm_yaml_path.write_text(yaml.safe_dump({
            "backends": {
                "ollama": {"model": "llama3.2:3b", "type": "openai_compat"},
                "anthropic": {"model": "claude-sonnet-4-6", "type": "anthropic"},
            },
            "fallback_order": ["ollama", "anthropic"],
        }))
        env_path = tmp_path / ".env"
        with patch("dev_api._wizard_yaml_path", return_value=str(yaml_path)):
            with patch("dev_api._env_path", return_value=env_path):
                with patch("dev_api.LLM_CONFIG_PATH", llm_yaml_path):
                    r = client.post("/api/settings/system/llm-backend", json={
                        "ollama_model": "llama3.1:8b",
                    })
        assert r.status_code == 200
        saved = yaml.safe_load(llm_yaml_path.read_text())
        assert saved["backends"]["anthropic"]["model"] == "claude-sonnet-4-6"
        assert saved["fallback_order"] == ["ollama", "anthropic"]

    def test_post_with_only_ollama_model_preserves_existing_host_and_port(self, tmp_path):
        """A partial payload (e.g. just switching the model) must not wipe a
        previously configured ollama_host/port back to blank/default --
        exactly the bug hit live: switching the model via curl with only
        {"ollama_model": "..."} silently reset ollama_host to "" and broke
        model discovery entirely."""
        yaml_path = tmp_path / "config" / "user.yaml"
        _write_user_yaml(yaml_path, {"services": {
            "ollama_host": "host.docker.internal",
            "ollama_port": 11500,
        }})
        llm_yaml_path = tmp_path / "config" / "llm.yaml"
        llm_yaml_path.parent.mkdir(parents=True, exist_ok=True)
        llm_yaml_path.write_text(yaml.safe_dump({
            "backends": {"ollama": {"model": "llama3.2:3b", "type": "openai_compat"}},
        }))
        env_path = tmp_path / ".env"
        with patch("dev_api._wizard_yaml_path", return_value=str(yaml_path)):
            with patch("dev_api._env_path", return_value=env_path):
                with patch("dev_api.LLM_CONFIG_PATH", llm_yaml_path):
                    r = client.post("/api/settings/system/llm-backend", json={
                        "ollama_model": "llama3.1:8b",
                    })
        assert r.status_code == 200
        saved = _read_user_yaml(yaml_path)
        assert saved["services"]["ollama_host"] == "host.docker.internal"
        assert saved["services"]["ollama_port"] == 11500

    def test_post_blank_ollama_model_does_not_clobber_existing(self, tmp_path):
        yaml_path = tmp_path / "config" / "user.yaml"
        _write_user_yaml(yaml_path, {})
        llm_yaml_path = tmp_path / "config" / "llm.yaml"
        llm_yaml_path.parent.mkdir(parents=True, exist_ok=True)
        llm_yaml_path.write_text(yaml.safe_dump({
            "backends": {"ollama": {"model": "llama3.1:8b", "type": "openai_compat"}},
        }))
        env_path = tmp_path / ".env"
        with patch("dev_api._wizard_yaml_path", return_value=str(yaml_path)):
            with patch("dev_api._env_path", return_value=env_path):
                with patch("dev_api.LLM_CONFIG_PATH", llm_yaml_path):
                    r = client.post("/api/settings/system/llm-backend", json={
                        "ollama_host": "10.1.10.5",
                    })
        assert r.status_code == 200
        saved = yaml.safe_load(llm_yaml_path.read_text())
        assert saved["backends"]["ollama"]["model"] == "llama3.1:8b"


class TestOllamaModelsList:
    def test_lists_models_from_configured_services_host(self, tmp_path):
        yaml_path = tmp_path / "config" / "user.yaml"
        _write_user_yaml(yaml_path, {"services": {"ollama_host": "10.1.10.5", "ollama_port": 11500}})
        fake_resp = type("R", (), {
            "status_code": 200,
            "json": lambda self: {"models": [{"name": "llama3.1:8b"}, {"name": "llama3.2:3b"}]},
        })()
        with patch("dev_api._wizard_yaml_path", return_value=str(yaml_path)):
            with patch("dev_api.requests.get", return_value=fake_resp) as mock_get:
                r = client.get("/api/settings/llm/ollama-models")
        assert r.status_code == 200
        assert r.json()["models"] == ["llama3.1:8b", "llama3.2:3b"]
        called_url = mock_get.call_args[0][0]
        assert "10.1.10.5:11500" in called_url

    def test_falls_back_to_env_var_when_configured_host_is_localhost(self, tmp_path):
        """"localhost" saved into services.ollama_host is a stale UI default
        (the old wizard's field placeholder) that's never actually reachable
        from inside this app's own Docker container -- Ollama on the host
        machine or an adopted external instance must be reached via
        OLLAMA_HOST (typically host.docker.internal). Trusting a saved
        "localhost" here would silently break model discovery."""
        yaml_path = tmp_path / "config" / "user.yaml"
        _write_user_yaml(yaml_path, {"services": {"ollama_host": "localhost", "ollama_port": 11434}})
        fake_resp = type("R", (), {
            "status_code": 200,
            "json": lambda self: {"models": [{"name": "llama3.1:8b"}]},
        })()
        with patch("dev_api._wizard_yaml_path", return_value=str(yaml_path)):
            with patch.dict(os.environ, {"OLLAMA_HOST": "http://host.docker.internal:11434"}):
                with patch("dev_api._running_in_docker", return_value=True):
                    with patch("dev_api.requests.get", return_value=fake_resp) as mock_get:
                        r = client.get("/api/settings/llm/ollama-models")
        assert r.status_code == 200
        assert r.json()["models"] == ["llama3.1:8b"]
        called_url = mock_get.call_args[0][0]
        assert "host.docker.internal" in called_url


    def test_host_override_queries_that_host_instead_of_configured_one(self, tmp_path):
        """After Detect finds a host, the frontend needs to see that host's
        models immediately, before the user clicks Save -- an explicit
        host/port query param takes priority over the saved config."""
        yaml_path = tmp_path / "config" / "user.yaml"
        _write_user_yaml(yaml_path, {"services": {"ollama_host": "10.1.10.5", "ollama_port": 11500}})
        fake_resp = type("R", (), {
            "status_code": 200,
            "json": lambda self: {"models": [{"name": "llama3.1:8b"}]},
        })()
        with patch("dev_api._wizard_yaml_path", return_value=str(yaml_path)):
            with patch("dev_api.requests.get", return_value=fake_resp) as mock_get:
                r = client.get("/api/settings/llm/ollama-models?host=host.docker.internal&port=11434")
        assert r.status_code == 200
        assert r.json()["models"] == ["llama3.1:8b"]
        called_url = mock_get.call_args[0][0]
        assert "host.docker.internal:11434" in called_url

    def test_no_override_still_uses_configured_host(self, tmp_path):
        yaml_path = tmp_path / "config" / "user.yaml"
        _write_user_yaml(yaml_path, {"services": {"ollama_host": "10.1.10.5", "ollama_port": 11500}})
        fake_resp = type("R", (), {
            "status_code": 200,
            "json": lambda self: {"models": [{"name": "llama3.1:8b"}]},
        })()
        with patch("dev_api._wizard_yaml_path", return_value=str(yaml_path)):
            with patch("dev_api.requests.get", return_value=fake_resp) as mock_get:
                r = client.get("/api/settings/llm/ollama-models")
        assert r.status_code == 200
        called_url = mock_get.call_args[0][0]
        assert "10.1.10.5:11500" in called_url


class TestVllmHostPortConfig:
    def test_get_returns_configured_vllm_host_and_port(self, tmp_path):
        yaml_path = tmp_path / "config" / "user.yaml"
        _write_user_yaml(yaml_path, {"services": {"vllm_host": "10.1.10.9", "vllm_port": 8001}})
        env_path = tmp_path / ".env"
        with patch("dev_api._wizard_yaml_path", return_value=str(yaml_path)):
            with patch("dev_api._env_path", return_value=env_path):
                r = client.get("/api/settings/system/llm-backend")
        assert r.status_code == 200
        body = r.json()
        assert body["vllm_host"] == "10.1.10.9"
        assert body["vllm_port"] == 8001

    def test_get_returns_default_vllm_port_when_unset(self, tmp_path):
        yaml_path = tmp_path / "config" / "user.yaml"
        _write_user_yaml(yaml_path, {})
        env_path = tmp_path / ".env"
        with patch("dev_api._wizard_yaml_path", return_value=str(yaml_path)):
            with patch("dev_api._env_path", return_value=env_path):
                r = client.get("/api/settings/system/llm-backend")
        assert r.status_code == 200
        body = r.json()
        assert body["vllm_host"] == ""
        assert body["vllm_port"] == 8000

    def test_post_writes_vllm_host_and_port(self, tmp_path):
        yaml_path = tmp_path / "config" / "user.yaml"
        _write_user_yaml(yaml_path, {})
        env_path = tmp_path / ".env"
        with patch("dev_api._wizard_yaml_path", return_value=str(yaml_path)):
            with patch("dev_api._env_path", return_value=env_path):
                r = client.post("/api/settings/system/llm-backend", json={
                    "vllm_host": "host.docker.internal",
                    "vllm_port": 8000,
                })
        assert r.status_code == 200
        saved = _read_user_yaml(yaml_path)
        assert saved["services"]["vllm_host"] == "host.docker.internal"
        assert saved["services"]["vllm_port"] == 8000

    def test_post_with_only_vllm_host_preserves_ollama_host(self, tmp_path):
        """Same 'blank means unchanged' semantics already established for
        ollama_host/port -- adding vllm fields must not regress that."""
        yaml_path = tmp_path / "config" / "user.yaml"
        _write_user_yaml(yaml_path, {"services": {
            "ollama_host": "10.1.10.5", "ollama_port": 11500,
        }})
        env_path = tmp_path / ".env"
        with patch("dev_api._wizard_yaml_path", return_value=str(yaml_path)):
            with patch("dev_api._env_path", return_value=env_path):
                r = client.post("/api/settings/system/llm-backend", json={
                    "vllm_host": "10.1.10.9",
                })
        assert r.status_code == 200
        saved = _read_user_yaml(yaml_path)
        assert saved["services"]["ollama_host"] == "10.1.10.5"
        assert saved["services"]["ollama_port"] == 11500
        assert saved["services"]["vllm_host"] == "10.1.10.9"


class TestVllmDetect:
    def test_vllm_detect_tries_docker_candidates_first_when_dockerized(self, tmp_path):
        calls = []

        def fake_get(url, **kw):
            calls.append(url)
            resp = type("R", (), {"status_code": 200 if "host.docker.internal" in url else 599})()
            return resp

        with patch("dev_api._running_in_docker", return_value=True), \
             patch("dev_api.requests.get", side_effect=fake_get):
            r = client.post("/api/settings/system/vllm-detect", json={"port": 8000})
        assert r.status_code == 200
        body = r.json()
        assert body["found"] is True
        assert body["host"] == "host.docker.internal"
        assert calls[0].startswith("http://host.docker.internal")

    def test_vllm_detect_probes_v1_models_not_api_tags(self, tmp_path):
        """vLLM speaks the OpenAI-compatible API (/v1/models), not Ollama's
        /api/tags -- probing the wrong path would always report not-found
        even against a healthy vLLM server."""
        calls = []

        def fake_get(url, **kw):
            calls.append(url)
            resp = type("R", (), {"status_code": 200})()
            return resp

        with patch("dev_api._running_in_docker", return_value=False), \
             patch("dev_api.requests.get", side_effect=fake_get):
            r = client.post("/api/settings/system/vllm-detect", json={"port": 8000})
        assert r.status_code == 200
        assert r.json()["found"] is True
        assert "/v1/models" in calls[0]

    def test_vllm_detect_reports_not_found_when_nothing_reachable(self, tmp_path):
        with patch("dev_api._running_in_docker", return_value=True), \
             patch("dev_api.requests.get", side_effect=Exception("connection refused")):
            r = client.post("/api/settings/system/vllm-detect", json={"port": 8000})
        body = r.json()
        assert body["found"] is False
        assert len(body["tried"]) >= 2


class TestOllamaPull:
    def test_pull_kicks_off_background_request_and_returns_immediately(self, tmp_path):
        yaml_path = tmp_path / "config" / "user.yaml"
        _write_user_yaml(yaml_path, {"services": {"ollama_host": "10.1.10.5", "ollama_port": 11500}})
        fake_resp = type("R", (), {"status_code": 200, "json": lambda self: {}})()
        with patch("dev_api._wizard_yaml_path", return_value=str(yaml_path)):
            with patch("dev_api.requests.post", return_value=fake_resp) as mock_post:
                r = client.post("/api/settings/system/ollama-pull", json={"model": "llama3.2:3b"})
        assert r.status_code == 200
        assert r.json() == {"ok": True, "status": "pulling"}
        mock_post.assert_called_once()
        called_url = mock_post.call_args[0][0]
        called_json = mock_post.call_args.kwargs.get("json")
        assert "10.1.10.5:11500" in called_url
        assert called_json["name"] == "llama3.2:3b"

    def test_pull_rejects_blank_model(self, tmp_path):
        yaml_path = tmp_path / "config" / "user.yaml"
        _write_user_yaml(yaml_path, {})
        with patch("dev_api._wizard_yaml_path", return_value=str(yaml_path)):
            r = client.post("/api/settings/system/ollama-pull", json={"model": ""})
        assert r.status_code == 400
