from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
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

    with (
        patch.object(router, "_is_reachable", return_value=False),
        pytest.raises(RuntimeError, match="All LLM backends exhausted"),
    ):
        router.complete("say hello")


def test_is_reachable_returns_false_on_connection_error():
    """_is_reachable returns False when the health endpoint is unreachable."""
    import requests

    from scripts.llm_router import LLMRouter

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

    from unittest.mock import MagicMock, patch
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
    from unittest.mock import patch

    import yaml

    from scripts.llm_router import LLMRouter

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
from scripts.llm_router import (
    LLMRouter,
    TaskModelNotAssignedError,
    TaskModelUnreachableError,
)


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
    from unittest.mock import patch
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


# ── New tests for router_for_tenant() and _merged_cloud_llm_config() ────────


def test_router_for_tenant_self_hosted_returns_bare_router():
    """Self-hosted (cloud_mode=False): router_for_tenant must return exactly
    what LLMRouter() with no arguments returns -- this path must be
    completely unchanged by this feature."""
    from scripts.llm_router import LLMRouter, router_for_tenant

    router = router_for_tenant(Path("/irrelevant/for/self-hosted/staging.db"), cloud_mode=False)
    assert isinstance(router, LLMRouter)
    # Self-hosted ignores db_path entirely -- confirm by checking the router's
    # config matches a bare LLMRouter()'s config exactly.
    bare = LLMRouter()
    assert router.config == bare.config


def test_merged_cloud_llm_config_combines_shared_backends_and_tenant_task_models(tmp_path):
    """Cloud mode: the merged config must contain the shared backends/
    fallback_order from CONFIG_PATH, with task_models replaced by this
    tenant's own file -- never the shared file's task_models (there isn't
    one; task_models lives per-tenant only in cloud mode)."""
    from scripts.llm_router import _merged_cloud_llm_config

    shared_cfg = {
        "backends": {"ollama": {"enabled": True, "model": "shared-model"}},
        "fallback_order": ["ollama"],
    }
    fake_shared_path = tmp_path / "shared_llm.yaml"
    fake_shared_path.write_text(yaml.dump(shared_cfg))

    tenant_cfg_dir = tmp_path / "tenant-a" / "config"
    tenant_cfg_dir.mkdir(parents=True)
    (tenant_cfg_dir / "task_models.yaml").write_text(yaml.dump({
        "task_models": {"primary": {"backend": "ollama", "model": "tenant-a-model"}}
    }))
    db_path = tmp_path / "tenant-a" / "staging.db"

    with patch("scripts.llm_router.CONFIG_PATH", fake_shared_path):
        merged = _merged_cloud_llm_config(db_path)

    assert merged["backends"] == shared_cfg["backends"]
    assert merged["fallback_order"] == shared_cfg["fallback_order"]
    assert merged["task_models"] == {"primary": {"backend": "ollama", "model": "tenant-a-model"}}


def test_merged_cloud_llm_config_empty_task_models_when_tenant_file_missing(tmp_path):
    """A tenant who has never saved any assignment gets an empty task_models
    dict, not a crash or the shared file's (nonexistent) task_models."""
    from scripts.llm_router import _merged_cloud_llm_config

    fake_shared_path = tmp_path / "shared_llm.yaml"
    fake_shared_path.write_text(yaml.dump({"backends": {}, "fallback_order": []}))
    db_path = tmp_path / "tenant-b" / "staging.db"  # tenant-b/config/task_models.yaml never created

    with patch("scripts.llm_router.CONFIG_PATH", fake_shared_path):
        merged = _merged_cloud_llm_config(db_path)

    assert merged["task_models"] == {}


def test_router_for_tenant_cloud_mode_builds_router_from_merged_dict(tmp_path):
    """Cloud mode: router_for_tenant's returned router's .config must equal
    what _merged_cloud_llm_config produces for that db_path -- proving the
    router was actually constructed from the per-tenant merge, not a bare
    LLMRouter()."""
    from scripts.llm_router import (
        _merged_cloud_llm_config,
        router_for_tenant,
    )

    fake_shared_path = tmp_path / "shared_llm.yaml"
    fake_shared_path.write_text(yaml.dump({"backends": {}, "fallback_order": []}))
    db_path = tmp_path / "tenant-c" / "staging.db"

    with patch("scripts.llm_router.CONFIG_PATH", fake_shared_path):
        router = router_for_tenant(db_path, cloud_mode=True)
        expected = _merged_cloud_llm_config(db_path)

    assert router.config == expected


def test_two_tenants_get_isolated_task_models(tmp_path):
    """The core bug this whole plan exists to fix: two different tenants'
    task_models must never leak into each other."""
    from scripts.llm_router import router_for_tenant

    fake_shared_path = tmp_path / "shared_llm.yaml"
    fake_shared_path.write_text(yaml.dump({"backends": {}, "fallback_order": []}))

    tenant_a_dir = tmp_path / "tenant-a" / "config"
    tenant_a_dir.mkdir(parents=True)
    (tenant_a_dir / "task_models.yaml").write_text(yaml.dump({
        "task_models": {"primary": {"backend": "ollama", "model": "model-a"}}
    }))
    tenant_b_dir = tmp_path / "tenant-b" / "config"
    tenant_b_dir.mkdir(parents=True)
    (tenant_b_dir / "task_models.yaml").write_text(yaml.dump({
        "task_models": {"primary": {"backend": "ollama", "model": "model-b"}}
    }))

    with patch("scripts.llm_router.CONFIG_PATH", fake_shared_path):
        router_a = router_for_tenant(tmp_path / "tenant-a" / "staging.db", cloud_mode=True)
        router_b = router_for_tenant(tmp_path / "tenant-b" / "staging.db", cloud_mode=True)

    assert router_a.config["task_models"]["primary"]["model"] == "model-a"
    assert router_b.config["task_models"]["primary"]["model"] == "model-b"
