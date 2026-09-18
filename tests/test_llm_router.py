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
    from unittest.mock import patch

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


# Tests for complete_task() and task-model exceptions
from scripts.llm_router import LLMRouter, TaskModelNotAssignedError, TaskModelUnreachableError


def _router_with_task_models(task_models: dict, backends: dict, extra_config: dict | None = None):
    config = {
        "backends": backends,
        "fallback_order": list(backends.keys()),
        "task_models": task_models,
        **(extra_config or {}),
    }
    return LLMRouter(config)


def test_complete_task_raises_when_unassigned_and_no_fallback_chain():
    """Only a genuinely unconfigured install (no assignment AND no usable
    fallback chain) is a hard TaskModelNotAssignedError."""
    router = _router_with_task_models(
        task_models={},
        backends={"ollama": {"type": "openai_compat", "base_url": "http://x", "model": "m", "enabled": True}},
        extra_config={"fallback_order": [], "research_fallback_order": []},
    )
    try:
        router.complete_task("research", "prompt")
        assert False, "expected TaskModelNotAssignedError"
    except TaskModelNotAssignedError as e:
        assert e.task == "research"


def test_complete_task_raises_when_assigned_backend_missing_and_no_fallback_chain():
    router = _router_with_task_models(
        task_models={"research": {"backend": "does_not_exist", "model": "m"}},
        backends={"ollama": {"type": "openai_compat", "base_url": "http://x", "model": "m", "enabled": True}},
        extra_config={"fallback_order": [], "research_fallback_order": []},
    )
    try:
        router.complete_task("research", "prompt")
        assert False, "expected TaskModelNotAssignedError"
    except TaskModelNotAssignedError as e:
        assert e.task == "research"


def test_complete_task_raises_unreachable_when_backend_disabled():
    router = _router_with_task_models(
        task_models={"research": {"backend": "ollama", "model": "m"}},
        backends={"ollama": {"type": "openai_compat", "base_url": "http://x", "model": "m", "enabled": False}},
    )
    try:
        router.complete_task("research", "prompt")
        assert False, "expected TaskModelUnreachableError"
    except TaskModelUnreachableError as e:
        assert e.task == "research"
        assert e.backend_id == "ollama"


def test_complete_task_calls_complete_with_backend_and_model_pinned():
    from unittest.mock import patch, MagicMock
    router = _router_with_task_models(
        task_models={"research": {"backend": "ollama", "model": "llama3.1:8b"}},
        backends={"ollama": {"type": "openai_compat", "base_url": "http://x", "model": "meghan-cover-writer", "enabled": True}},
    )
    with patch.object(router, "complete", return_value="result") as mock_complete:
        result = router.complete_task("research", "prompt", system="sys")
    assert result == "result"
    mock_complete.assert_called_once_with(
        "prompt", system="sys", fallback_order=["ollama"], model_override="llama3.1:8b", max_tokens=None,
    )


def test_complete_task_wraps_runtime_error_as_unreachable():
    from unittest.mock import patch
    router = _router_with_task_models(
        task_models={"chat": {"backend": "ollama", "model": "llama3.1:8b"}},
        backends={"ollama": {"type": "openai_compat", "base_url": "http://x", "model": "m", "enabled": True}},
    )
    with patch.object(router, "complete", side_effect=RuntimeError("all backends exhausted")):
        try:
            router.complete_task("chat", "prompt")
            assert False, "expected TaskModelUnreachableError"
        except TaskModelUnreachableError as e:
            assert e.task == "chat"
            assert e.backend_id == "ollama"
            assert "all backends exhausted" in e.detail


# ── Graceful degradation: no task_models assigned anywhere ───────────────────
# Nothing seeds task_models on a fresh install (and cloud tenants have no UI to
# set one), so complete_task() must fall back to the existing fallback chains
# rather than hard-failing every LLM feature.


def test_complete_task_falls_back_to_research_fallback_order_when_unassigned():
    from unittest.mock import patch
    router = _router_with_task_models(
        task_models={},
        backends={
            "cf_text": {"type": "openai_compat", "base_url": "http://x", "model": "cf-text", "enabled": True},
            "ollama": {"type": "openai_compat", "base_url": "http://y", "model": "llama3.2:3b", "enabled": True},
        },
        extra_config={"fallback_order": ["ollama"], "research_fallback_order": ["cf_text"]},
    )
    with patch.object(router, "complete", return_value="result") as mock_complete:
        assert router.complete_task("research", "prompt") == "result"
    mock_complete.assert_called_once_with(
        "prompt", system=None, fallback_order=["cf_text"], model_override="cf-text", max_tokens=None,
    )


def test_complete_task_chat_falls_back_to_research_fallback_order_too():
    from unittest.mock import patch
    router = _router_with_task_models(
        task_models={},
        backends={"cf_text": {"type": "openai_compat", "base_url": "http://x", "model": "cf-text", "enabled": True}},
        extra_config={"fallback_order": [], "research_fallback_order": ["cf_text"]},
    )
    with patch.object(router, "complete", return_value="hi") as mock_complete:
        assert router.complete_task("chat", "prompt") == "hi"
    assert mock_complete.call_args.kwargs["model_override"] == "cf-text"


def test_complete_task_falls_back_to_fallback_order_when_no_research_chain():
    from unittest.mock import patch
    router = _router_with_task_models(
        task_models={},
        backends={"ollama": {"type": "openai_compat", "base_url": "http://y", "model": "llama3.2:3b", "enabled": True}},
        extra_config={"fallback_order": ["ollama"]},
    )
    with patch.object(router, "complete", return_value="result") as mock_complete:
        assert router.complete_task("research", "prompt") == "result"
    assert mock_complete.call_args.kwargs["fallback_order"] == ["ollama"]
    assert mock_complete.call_args.kwargs["model_override"] == "llama3.2:3b"


def test_complete_task_primary_falls_back_to_fallback_order_not_research_chain():
    from unittest.mock import patch
    router = _router_with_task_models(
        task_models={},
        backends={
            "cf_text": {"type": "openai_compat", "base_url": "http://x", "model": "cf-text", "enabled": True},
            "ollama": {"type": "openai_compat", "base_url": "http://y", "model": "llama3.2:3b", "enabled": True},
        },
        extra_config={"fallback_order": ["ollama"], "research_fallback_order": ["cf_text"]},
    )
    with patch.object(router, "complete", return_value="letter") as mock_complete:
        assert router.complete_task("primary", "prompt") == "letter"
    assert mock_complete.call_args.kwargs["fallback_order"] == ["ollama"]


def test_complete_task_explicit_assignment_wins_over_fallback():
    from unittest.mock import patch
    router = _router_with_task_models(
        task_models={"research": {"backend": "ollama", "model": "llama3.1:8b"}},
        backends={
            "cf_text": {"type": "openai_compat", "base_url": "http://x", "model": "cf-text", "enabled": True},
            "ollama": {"type": "openai_compat", "base_url": "http://y", "model": "llama3.2:3b", "enabled": True},
        },
        extra_config={"fallback_order": ["cf_text"], "research_fallback_order": ["cf_text"]},
    )
    with patch.object(router, "complete", return_value="result") as mock_complete:
        router.complete_task("research", "prompt")
    mock_complete.assert_called_once_with(
        "prompt", system=None, fallback_order=["ollama"], model_override="llama3.1:8b", max_tokens=None,
    )


def test_complete_task_fallback_derived_disabled_backend_is_unreachable_not_skipped():
    """One candidate per task, predictably named -- a disabled derived backend
    surfaces as TaskModelUnreachableError rather than silently sliding to the
    next chain entry."""
    router = _router_with_task_models(
        task_models={},
        backends={
            "cf_text": {"type": "openai_compat", "base_url": "http://x", "model": "cf-text", "enabled": False},
            "ollama": {"type": "openai_compat", "base_url": "http://y", "model": "llama3.2:3b", "enabled": True},
        },
        extra_config={"fallback_order": ["ollama"], "research_fallback_order": ["cf_text", "ollama"]},
    )
    try:
        router.complete_task("research", "prompt")
        assert False, "expected TaskModelUnreachableError"
    except TaskModelUnreachableError as e:
        assert e.backend_id == "cf_text"


def test_complete_task_skips_chain_entry_naming_an_unknown_backend():
    from unittest.mock import patch
    router = _router_with_task_models(
        task_models={},
        backends={"ollama": {"type": "openai_compat", "base_url": "http://y", "model": "llama3.2:3b", "enabled": True}},
        extra_config={"fallback_order": ["ollama"], "research_fallback_order": ["ghost_backend"]},
    )
    with patch.object(router, "complete", return_value="result") as mock_complete:
        router.complete_task("research", "prompt")
    assert mock_complete.call_args.kwargs["fallback_order"] == ["ollama"]
