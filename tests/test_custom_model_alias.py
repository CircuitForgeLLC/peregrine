"""GET/PUT /api/settings/system/custom-model -- lets a cloud managed user
enter their own fine-tuned model alias (matching cf-orch's UserModelRegistry
YAML alias convention). No routing to cf-orch happens yet -- cf-orch has no
user_id threading on the task_allocate path and no self-service registration
API; this just persists the setting so it's ready once that lands. See
circuitforge-plans/peregrine/superpowers/plans/2026-09-18-cloud-custom-model-cforch-followup.md.
"""
import yaml
from unittest.mock import patch
from fastapi.testclient import TestClient
import dev_api
from dev_api import app

client = TestClient(app)


def _write_user_yaml(path, data=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data or {}))


class TestCustomModelAlias:
    def test_get_returns_empty_when_unset(self, tmp_path):
        yaml_path = tmp_path / "config" / "user.yaml"
        _write_user_yaml(yaml_path, {})
        with patch("dev_api._wizard_yaml_path", return_value=str(yaml_path)):
            r = client.get("/api/settings/system/custom-model")
        assert r.status_code == 200
        assert r.json()["custom_model_alias"] == ""

    def test_get_returns_saved_alias(self, tmp_path):
        yaml_path = tmp_path / "config" / "user.yaml"
        _write_user_yaml(yaml_path, {"custom_model_alias": "meghan-letter-writer-v2"})
        with patch("dev_api._wizard_yaml_path", return_value=str(yaml_path)):
            r = client.get("/api/settings/system/custom-model")
        assert r.status_code == 200
        assert r.json()["custom_model_alias"] == "meghan-letter-writer-v2"

    def test_put_saves_alias(self, tmp_path):
        yaml_path = tmp_path / "config" / "user.yaml"
        _write_user_yaml(yaml_path, {})
        with patch("dev_api._wizard_yaml_path", return_value=str(yaml_path)), \
             patch("dev_api._get_effective_tier", return_value="premium"):
            r = client.put("/api/settings/system/custom-model", json={"custom_model_alias": "my-fine-tune"})
        assert r.status_code == 200
        assert r.json() == {"ok": True}
        saved = yaml.safe_load(yaml_path.read_text())
        assert saved["custom_model_alias"] == "my-fine-tune"

    def test_put_can_clear_alias(self, tmp_path):
        yaml_path = tmp_path / "config" / "user.yaml"
        _write_user_yaml(yaml_path, {"custom_model_alias": "old-alias"})
        with patch("dev_api._wizard_yaml_path", return_value=str(yaml_path)), \
             patch("dev_api._get_effective_tier", return_value="premium"):
            r = client.put("/api/settings/system/custom-model", json={"custom_model_alias": ""})
        assert r.status_code == 200
        saved = yaml.safe_load(yaml_path.read_text())
        assert saved["custom_model_alias"] == ""

    def test_put_preserves_unrelated_existing_keys(self, tmp_path):
        yaml_path = tmp_path / "config" / "user.yaml"
        _write_user_yaml(yaml_path, {"inference_profile": "remote", "services": {"ollama_host": "10.1.10.5"}})
        with patch("dev_api._wizard_yaml_path", return_value=str(yaml_path)), \
             patch("dev_api._get_effective_tier", return_value="premium"):
            r = client.put("/api/settings/system/custom-model", json={"custom_model_alias": "my-fine-tune"})
        assert r.status_code == 200
        saved = yaml.safe_load(yaml_path.read_text())
        assert saved["inference_profile"] == "remote"
        assert saved["services"]["ollama_host"] == "10.1.10.5"
        assert saved["custom_model_alias"] == "my-fine-tune"

    def test_put_rejects_when_not_premium(self, tmp_path):
        yaml_path = tmp_path / "config" / "user.yaml"
        _write_user_yaml(yaml_path, {})
        with patch("dev_api._wizard_yaml_path", return_value=str(yaml_path)), \
             patch("dev_api._get_effective_tier", return_value="paid"):
            r = client.put("/api/settings/system/custom-model", json={"custom_model_alias": "my-fine-tune"})
        assert r.status_code == 402
        assert r.json()["detail"] == {"error": "tier_required", "min_tier": "premium"}
        saved = yaml.safe_load(yaml_path.read_text())
        assert "custom_model_alias" not in saved

    def test_put_allows_clearing_when_not_premium(self, tmp_path):
        yaml_path = tmp_path / "config" / "user.yaml"
        _write_user_yaml(yaml_path, {"custom_model_alias": "old-alias"})
        with patch("dev_api._wizard_yaml_path", return_value=str(yaml_path)), \
             patch("dev_api._get_effective_tier", return_value="paid"):
            r = client.put("/api/settings/system/custom-model", json={"custom_model_alias": ""})
        assert r.status_code == 200
        saved = yaml.safe_load(yaml_path.read_text())
        assert saved["custom_model_alias"] == ""

    def test_put_allows_when_premium(self, tmp_path):
        yaml_path = tmp_path / "config" / "user.yaml"
        _write_user_yaml(yaml_path, {})
        with patch("dev_api._wizard_yaml_path", return_value=str(yaml_path)), \
             patch("dev_api._get_effective_tier", return_value="premium"):
            r = client.put("/api/settings/system/custom-model", json={"custom_model_alias": "my-fine-tune"})
        assert r.status_code == 200
        saved = yaml.safe_load(yaml_path.read_text())
        assert saved["custom_model_alias"] == "my-fine-tune"
