"""Tests for Peregrine's LLMRouter shim — priority fallback logic."""
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock, call

sys.path.insert(0, str(Path(__file__).parent.parent))


def _import_fresh():
    """Import scripts.llm_router fresh (bypass module cache)."""
    import importlib
    import scripts.llm_router as mod
    importlib.reload(mod)
    return mod


# ---------------------------------------------------------------------------
# Test 1: local config/llm.yaml takes priority when it exists
# ---------------------------------------------------------------------------

def test_uses_local_yaml_when_present():
    """When config/llm.yaml exists locally, super().__init__ is called with that path."""
    import scripts.llm_router as shim_mod
    from circuitforge_core.llm import LLMRouter as _CoreLLMRouter

    local_path = Path(shim_mod.__file__).parent.parent / "config" / "llm.yaml"
    user_path = Path.home() / ".config" / "circuitforge" / "llm.yaml"

    def fake_exists(self):
        return self == local_path  # only the local path "exists"

    captured = {}

    def fake_core_init(self, config_path=None):
        captured["config_path"] = config_path
        self.config = {}

    with patch.object(Path, "exists", fake_exists), \
         patch.object(_CoreLLMRouter, "__init__", fake_core_init):
        import importlib
        import scripts.llm_router as mod
        importlib.reload(mod)
        mod.LLMRouter()

    assert captured.get("config_path") == local_path, (
        f"Expected super().__init__ to be called with local path {local_path}, "
        f"got {captured.get('config_path')}"
    )


# ---------------------------------------------------------------------------
# Test 2: falls through to env-var auto-config when neither yaml exists
# ---------------------------------------------------------------------------

def test_falls_through_to_env_when_no_yamls():
    """When no yaml files exist, super().__init__ is called with no args (env-var path)."""
    import scripts.llm_router as shim_mod
    from circuitforge_core.llm import LLMRouter as _CoreLLMRouter

    captured = {}

    def fake_exists(self):
        return False  # no yaml files exist anywhere

    def fake_core_init(self, config_path=None):
        # Record whether a path was passed
        captured["config_path"] = config_path
        captured["called"] = True
        self.config = {}

    with patch.object(Path, "exists", fake_exists), \
         patch.object(_CoreLLMRouter, "__init__", fake_core_init):
        import importlib
        import scripts.llm_router as mod
        importlib.reload(mod)
        mod.LLMRouter()

    assert captured.get("called"), "super().__init__ was never called"
    # When called with no args, config_path defaults to None in our mock,
    # meaning the shim correctly fell through to env-var auto-config
    assert captured.get("config_path") is None, (
        f"Expected super().__init__ to be called with no explicit path (None), "
        f"got {captured.get('config_path')}"
    )


# ---------------------------------------------------------------------------
# Test 3: module-level complete() singleton is only instantiated once
# ---------------------------------------------------------------------------

def test_complete_singleton_is_reused():
    """complete() reuses the same LLMRouter instance across multiple calls."""
    import importlib
    import scripts.llm_router as mod
    importlib.reload(mod)

    # Reset singleton
    mod._router = None

    instantiation_count = [0]
    original_init = mod.LLMRouter.__init__

    mock_router = MagicMock()
    mock_router.complete.return_value = "OK"

    original_class = mod.LLMRouter

    class CountingRouter(original_class):
        def __init__(self):
            instantiation_count[0] += 1
            # Bypass real __init__ to avoid needing config files
            self.config = {}

        def complete(self, prompt, system=None):
            return "OK"

    # Patch the class in the module
    mod.LLMRouter = CountingRouter
    mod._router = None

    result1 = mod.complete("first call")
    result2 = mod.complete("second call")

    assert result1 == "OK"
    assert result2 == "OK"
    assert instantiation_count[0] == 1, (
        f"Expected LLMRouter to be instantiated exactly once, "
        f"got {instantiation_count[0]} instantiation(s)"
    )

    # Restore
    mod.LLMRouter = original_class
