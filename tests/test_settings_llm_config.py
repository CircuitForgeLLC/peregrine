from unittest.mock import patch

import yaml
from fastapi.testclient import TestClient

from dev_api import app

client = TestClient(app)


class TestGetLlmConfig:
    def test_returns_a_list_derived_from_the_dict_shaped_backends(self, tmp_path):
        """config/llm.yaml stores backends as a dict keyed by id, but the
        frontend's drag-reorder UI needs a list of {id, enabled, priority}.
        Returning the raw dict here made the frontend's `.filter()` call
        crash on every page load, since a dict has no .filter()."""
        llm_yaml = tmp_path / "llm.yaml"
        llm_yaml.write_text(yaml.safe_dump({
            "backends": {
                "cf_text": {"type": "openai_compat", "model": "cf-text", "enabled": True},
                "ollama": {"type": "openai_compat", "model": "llama3.1:8b", "enabled": True},
                "anthropic": {"type": "anthropic", "model": "claude-sonnet-4-6", "enabled": False},
            },
            "fallback_order": ["cf_text", "ollama", "anthropic"],
        }))
        with patch("dev_api.LLM_CONFIG_PATH", llm_yaml):
            r = client.get("/api/settings/system/llm")
        assert r.status_code == 200
        backends = r.json()["backends"]
        assert isinstance(backends, list)
        ids = [b["id"] for b in backends]
        assert ids == ["cf_text", "ollama", "anthropic"]
        assert backends[0]["priority"] == 1
        assert backends[1]["priority"] == 2
        assert backends[2]["priority"] == 3
        assert backends[0]["enabled"] is True
        assert backends[2]["enabled"] is False

    def test_returns_empty_list_when_llm_yaml_missing(self, tmp_path):
        llm_yaml = tmp_path / "llm.yaml"
        with patch("dev_api.LLM_CONFIG_PATH", llm_yaml):
            r = client.get("/api/settings/system/llm")
        assert r.status_code == 200
        assert r.json()["backends"] == []

    def test_includes_backends_missing_from_fallback_order_at_the_end(self, tmp_path):
        """A backend defined but never added to fallback_order (e.g. one the
        user has never enabled) must still be visible in the reorder list,
        not silently dropped."""
        llm_yaml = tmp_path / "llm.yaml"
        llm_yaml.write_text(yaml.safe_dump({
            "backends": {
                "ollama": {"type": "openai_compat", "model": "llama3.1:8b", "enabled": True},
                "github_copilot": {"type": "openai_compat", "model": "gpt-4o", "enabled": False},
            },
            "fallback_order": ["ollama"],
        }))
        with patch("dev_api.LLM_CONFIG_PATH", llm_yaml):
            r = client.get("/api/settings/system/llm")
        assert r.status_code == 200
        ids = [b["id"] for b in r.json()["backends"]]
        assert ids == ["ollama", "github_copilot"]


class TestSaveLlmConfig:
    def test_preserves_backend_config_fields_updates_only_enabled(self, tmp_path):
        """The old handler replaced the entire backends dict with the
        frontend's flat {id, enabled, priority} list, destroying base_url,
        model, type, and every other field for every backend on every save."""
        llm_yaml = tmp_path / "llm.yaml"
        llm_yaml.write_text(yaml.safe_dump({
            "backends": {
                "ollama": {
                    "type": "openai_compat",
                    "base_url": "http://host.docker.internal:11434/v1",
                    "model": "llama3.1:8b",
                    "api_key": "ollama",
                    "enabled": True,
                },
            },
            "fallback_order": ["ollama"],
        }))
        with patch("dev_api.LLM_CONFIG_PATH", llm_yaml):
            r = client.put("/api/settings/system/llm", json={
                "backends": [{"id": "ollama", "enabled": False, "priority": 1}],
            })
        assert r.status_code == 200
        saved = yaml.safe_load(llm_yaml.read_text())
        assert saved["backends"]["ollama"]["base_url"] == "http://host.docker.internal:11434/v1"
        assert saved["backends"]["ollama"]["model"] == "llama3.1:8b"
        assert saved["backends"]["ollama"]["api_key"] == "ollama"
        assert saved["backends"]["ollama"]["enabled"] is False

    def test_reorders_fallback_order_to_match_payload_priority(self, tmp_path):
        llm_yaml = tmp_path / "llm.yaml"
        llm_yaml.write_text(yaml.safe_dump({
            "backends": {
                "cf_text": {"type": "openai_compat", "model": "cf-text", "enabled": True},
                "ollama": {"type": "openai_compat", "model": "llama3.1:8b", "enabled": True},
            },
            "fallback_order": ["cf_text", "ollama"],
        }))
        with patch("dev_api.LLM_CONFIG_PATH", llm_yaml):
            r = client.put("/api/settings/system/llm", json={
                "backends": [
                    {"id": "ollama", "enabled": True, "priority": 1},
                    {"id": "cf_text", "enabled": True, "priority": 2},
                ],
            })
        assert r.status_code == 200
        saved = yaml.safe_load(llm_yaml.read_text())
        assert saved["fallback_order"] == ["ollama", "cf_text"]

    def test_ignores_a_payload_id_not_present_in_backends(self, tmp_path):
        """A stale/unknown id in the payload must not crash or create a
        bogus backend entry."""
        llm_yaml = tmp_path / "llm.yaml"
        llm_yaml.write_text(yaml.safe_dump({
            "backends": {"ollama": {"type": "openai_compat", "model": "llama3.1:8b", "enabled": True}},
            "fallback_order": ["ollama"],
        }))
        with patch("dev_api.LLM_CONFIG_PATH", llm_yaml):
            r = client.put("/api/settings/system/llm", json={
                "backends": [
                    {"id": "ollama", "enabled": True, "priority": 1},
                    {"id": "totally_unknown", "enabled": True, "priority": 2},
                ],
            })
        assert r.status_code == 200
        saved = yaml.safe_load(llm_yaml.read_text())
        assert "totally_unknown" not in saved["backends"]
        assert saved["fallback_order"] == ["ollama"]
