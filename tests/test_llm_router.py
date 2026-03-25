import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path
import yaml

CONFIG_PATH = Path(__file__).parent.parent / "config" / "llm.yaml"


def test_config_loads():
    """Config file is valid YAML with required keys."""
    cfg = yaml.safe_load(CONFIG_PATH.read_text())
    assert "fallback_order" in cfg
    assert "backends" in cfg
    assert len(cfg["fallback_order"]) >= 1


def test_router_uses_first_reachable_backend():
    """Router skips unreachable backends and uses the first that responds."""
    from scripts.llm_router import LLMRouter

    router = LLMRouter(CONFIG_PATH)

    mock_response = MagicMock()
    mock_response.choices[0].message.content = "hello"

    with patch.object(router, "_is_reachable", side_effect=[False, True, True, True, True]), \
         patch("circuitforge_core.llm.router.OpenAI") as MockOpenAI:
        instance = MockOpenAI.return_value
        instance.chat.completions.create.return_value = mock_response
        mock_model = MagicMock()
        mock_model.id = "test-model"
        instance.models.list.return_value.data = [mock_model]

        result = router.complete("say hello")

    assert result == "hello"


def test_router_raises_when_all_backends_fail():
    """Router raises RuntimeError when every backend is unreachable or errors."""
    from scripts.llm_router import LLMRouter

    router = LLMRouter(CONFIG_PATH)

    with patch.object(router, "_is_reachable", return_value=False):
        with pytest.raises(RuntimeError, match="All LLM backends exhausted"):
            router.complete("say hello")


def test_is_reachable_returns_false_on_connection_error():
    """_is_reachable returns False when the health endpoint is unreachable."""
    from scripts.llm_router import LLMRouter
    import requests

    router = LLMRouter(CONFIG_PATH)

    with patch("circuitforge_core.llm.router.requests.get", side_effect=requests.ConnectionError):
        result = router._is_reachable("http://localhost:9999/v1")

    assert result is False


def test_complete_skips_backend_without_image_support(tmp_path):
    """When images= is passed, backends without supports_images are skipped."""
    import yaml
    from scripts.llm_router import LLMRouter

    cfg = {
        "fallback_order": ["ollama", "vision_service"],
        "backends": {
            "ollama": {
                "type": "openai_compat",
                "base_url": "http://localhost:11434/v1",
                "model": "llava",
                "api_key": "ollama",
                "enabled": True,
                "supports_images": False,
            },
            "vision_service": {
                "type": "vision_service",
                "base_url": "http://localhost:8002",
                "enabled": True,
                "supports_images": True,
            },
        },
    }
    cfg_file = tmp_path / "llm.yaml"
    cfg_file.write_text(yaml.dump(cfg))

    from unittest.mock import patch, MagicMock
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"text": "B — collaborative"}

    with patch("circuitforge_core.llm.router.requests.get") as mock_get, \
         patch("circuitforge_core.llm.router.requests.post") as mock_post:
        # health check returns ok for vision_service
        mock_get.return_value = MagicMock(status_code=200)
        mock_post.return_value = mock_resp

        router = LLMRouter(config_path=cfg_file)
        result = router.complete("Which option?", images=["base64data"])

    assert result == "B — collaborative"
    # vision_service POST /analyze should have been called
    assert mock_post.called


def test_complete_without_images_skips_vision_service(tmp_path):
    """When images=None, vision_service backend is skipped."""
    import yaml
    from scripts.llm_router import LLMRouter
    from unittest.mock import patch, MagicMock

    cfg = {
        "fallback_order": ["vision_service"],
        "backends": {
            "vision_service": {
                "type": "vision_service",
                "base_url": "http://localhost:8002",
                "enabled": True,
                "supports_images": True,
            },
        },
    }
    cfg_file = tmp_path / "llm.yaml"
    cfg_file.write_text(yaml.dump(cfg))

    router = LLMRouter(config_path=cfg_file)
    with patch("circuitforge_core.llm.router.requests.post") as mock_post:
        try:
            router.complete("text only prompt")
        except RuntimeError:
            pass  # all backends exhausted is expected
        assert not mock_post.called
