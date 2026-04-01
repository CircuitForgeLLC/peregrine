"""
LLM abstraction layer with priority fallback chain.
Reads config/llm.yaml. Tries backends in order; falls back on any error.
"""
from pathlib import Path

from circuitforge_core.llm import LLMRouter as _CoreLLMRouter

CONFIG_PATH = Path(__file__).parent.parent / "config" / "llm.yaml"


class LLMRouter(_CoreLLMRouter):
    """Peregrine-specific LLMRouter — defaults to Peregrine's config/llm.yaml."""

    def __init__(self, config_path: Path = CONFIG_PATH):
        super().__init__(config_path)


# Module-level singleton for convenience
_router: LLMRouter | None = None


def complete(prompt: str, system: str | None = None) -> str:
    global _router
    if _router is None:
        _router = LLMRouter()
    return _router.complete(prompt, system)
