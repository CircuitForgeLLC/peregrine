"""
LLM abstraction layer with priority fallback chain.
Config lookup order:
  1. <repo>/config/llm.yaml  — per-install local config
  2. ~/.config/circuitforge/llm.yaml  — user-level config (circuitforge-core default)
  3. env-var auto-config (ANTHROPIC_API_KEY, OPENAI_API_KEY, OLLAMA_HOST, …)
"""
from pathlib import Path

from circuitforge_core.llm import LLMRouter as _CoreLLMRouter

# Kept for backwards-compatibility — external callers that import CONFIG_PATH
# from this module continue to work.
CONFIG_PATH = Path(__file__).parent.parent / "config" / "llm.yaml"


class LLMRouter(_CoreLLMRouter):
    """Peregrine-specific LLMRouter — tri-level config path priority.

    When ``config_path`` is supplied (e.g. in tests) it is passed straight
    through to the core.  When omitted, the lookup order is:
      1. <repo>/config/llm.yaml  (per-install local config)
      2. ~/.config/circuitforge/llm.yaml  (user-level, circuitforge-core default)
      3. env-var auto-config  (ANTHROPIC_API_KEY, OPENAI_API_KEY, OLLAMA_HOST …)
    """

    def __init__(self, config_path: Path | None = None) -> None:
        if config_path is not None:
            # Explicit path supplied — use it directly (e.g. tests, CLI override).
            super().__init__(config_path)
            return

        local = Path(__file__).parent.parent / "config" / "llm.yaml"
        user_level = Path.home() / ".config" / "circuitforge" / "llm.yaml"
        if local.exists():
            super().__init__(local)
        elif user_level.exists():
            super().__init__(user_level)
        else:
            # No yaml found — let circuitforge-core's env-var auto-config run.
            # The core default CONFIG_PATH (~/.config/circuitforge/llm.yaml)
            # won't exist either, so _auto_config_from_env() will be triggered.
            super().__init__()


# Module-level singleton for convenience
_router: LLMRouter | None = None


def complete(prompt: str, system: str | None = None) -> str:
    global _router
    if _router is None:
        _router = LLMRouter()
    return _router.complete(prompt, system)
