import os
import yaml
from unittest.mock import patch
from fastapi.testclient import TestClient
import dev_api
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
