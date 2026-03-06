"""Tests for BYOK cloud backend detection."""
import pytest
from scripts.byok_guard import is_cloud_backend, cloud_backends


class TestIsCloudBackend:
    def test_anthropic_type_is_always_cloud(self):
        assert is_cloud_backend("anthropic", {"type": "anthropic", "enabled": True}) is True

    def test_claude_code_type_is_cloud(self):
        assert is_cloud_backend("claude_code", {"type": "claude_code", "enabled": True}) is True

    def test_vision_service_is_always_local(self):
        assert is_cloud_backend("vision", {"type": "vision_service"}) is False

    def test_openai_compat_localhost_is_local(self):
        cfg = {"type": "openai_compat", "base_url": "http://localhost:11434/v1"}
        assert is_cloud_backend("ollama", cfg) is False

    def test_openai_compat_127_is_local(self):
        cfg = {"type": "openai_compat", "base_url": "http://127.0.0.1:8000/v1"}
        assert is_cloud_backend("vllm", cfg) is False

    def test_openai_compat_0000_is_local(self):
        cfg = {"type": "openai_compat", "base_url": "http://0.0.0.0:8000/v1"}
        assert is_cloud_backend("vllm", cfg) is False

    def test_openai_compat_remote_url_is_cloud(self):
        cfg = {"type": "openai_compat", "base_url": "https://api.openai.com/v1"}
        assert is_cloud_backend("openai", cfg) is True

    def test_openai_compat_together_is_cloud(self):
        cfg = {"type": "openai_compat", "base_url": "https://api.together.xyz/v1"}
        assert is_cloud_backend("together", cfg) is True

    def test_local_override_suppresses_cloud_detection(self):
        cfg = {"type": "openai_compat", "base_url": "http://192.168.1.100:11434/v1", "local": True}
        assert is_cloud_backend("nas_ollama", cfg) is False

    def test_local_override_on_anthropic_suppresses_detection(self):
        cfg = {"type": "anthropic", "local": True}
        assert is_cloud_backend("anthropic", cfg) is False

    def test_unknown_type_without_url_is_local(self):
        assert is_cloud_backend("mystery", {"type": "unknown_type"}) is False


class TestCloudBackends:
    def test_empty_config_returns_empty(self):
        assert cloud_backends({}) == []

    def test_fully_local_config_returns_empty(self):
        cfg = {
            "backends": {
                "ollama": {"type": "openai_compat", "base_url": "http://localhost:11434/v1", "enabled": True},
                "vision": {"type": "vision_service", "enabled": True},
            }
        }
        assert cloud_backends(cfg) == []

    def test_cloud_backend_returned(self):
        cfg = {
            "backends": {
                "anthropic": {"type": "anthropic", "enabled": True},
            }
        }
        assert cloud_backends(cfg) == ["anthropic"]

    def test_disabled_cloud_backend_excluded(self):
        cfg = {
            "backends": {
                "anthropic": {"type": "anthropic", "enabled": False},
            }
        }
        assert cloud_backends(cfg) == []

    def test_mix_returns_only_enabled_cloud(self):
        cfg = {
            "backends": {
                "ollama":    {"type": "openai_compat", "base_url": "http://localhost:11434/v1", "enabled": True},
                "anthropic": {"type": "anthropic", "enabled": True},
                "openai":    {"type": "openai_compat", "base_url": "https://api.openai.com/v1", "enabled": False},
            }
        }
        result = cloud_backends(cfg)
        assert result == ["anthropic"]

    def test_multiple_cloud_backends_all_returned(self):
        cfg = {
            "backends": {
                "anthropic": {"type": "anthropic", "enabled": True},
                "openai":    {"type": "openai_compat", "base_url": "https://api.openai.com/v1", "enabled": True},
            }
        }
        result = cloud_backends(cfg)
        assert set(result) == {"anthropic", "openai"}
