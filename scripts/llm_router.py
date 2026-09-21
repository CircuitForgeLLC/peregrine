"""
LLM abstraction layer with priority fallback chain.
Config lookup order:
  1. <repo>/config/llm.yaml  — per-install local config
  2. ~/.config/circuitforge/llm.yaml  — user-level config (circuitforge-core default)
  3. env-var auto-config (ANTHROPIC_API_KEY, OPENAI_API_KEY, OLLAMA_HOST, …)
"""
from pathlib import Path
from typing import ClassVar

from circuitforge_core.llm import LLMRouter as _CoreLLMRouter

# Kept for backwards-compatibility — external callers that import CONFIG_PATH
# from this module continue to work.
CONFIG_PATH = Path(__file__).parent.parent / "config" / "llm.yaml"


class TaskModelNotAssignedError(Exception):
    """No usable model is assigned to this task, or the assignment points
    at a backend that no longer exists in config."""
    def __init__(self, task: str):
        self.task = task
        super().__init__(f"No model assigned for task '{task}'")


class TaskModelUnreachableError(Exception):
    """A model is assigned to this task, but the backend is disabled or
    the completion call itself failed (network, timeout, etc.)."""
    def __init__(self, task: str, backend_id: str, detail: str = ""):
        self.task = task
        self.backend_id = backend_id
        self.detail = detail
        super().__init__(f"Backend '{backend_id}' for task '{task}' is unreachable: {detail}")


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

    # Which config fallback chain a task falls back to when nothing is
    # explicitly assigned to it, most-specific chain first.
    _TASK_FALLBACK_CHAINS: ClassVar[dict[str, tuple[str, ...]]] = {
        "research": ("research_fallback_order", "fallback_order"),
        "chat": ("research_fallback_order", "fallback_order"),
        "primary": ("fallback_order",),
    }

    def _default_task_model(self, task: str) -> tuple[str, str, dict] | None:
        """Derive a sensible (backend_id, model, backend) for `task` from the
        existing fallback chains, for installs that have never assigned one.

        Deliberately picks exactly ONE candidate -- the first entry of the
        first chain that names a backend which exists and has a model -- and
        does not skip a disabled backend. That keeps behavior predictable and
        keeps the caller's "unreachable" error naming the backend a user would
        actually recognise, instead of silently re-implementing complete()'s
        whole-chain-with-skip semantics.
        """
        backends = self.config.get("backends") or {}
        for chain_key in self._TASK_FALLBACK_CHAINS.get(task, ("fallback_order",)):
            chain = self.config.get(chain_key) or []
            if not chain:
                continue
            backend_id = chain[0]
            backend = backends.get(backend_id)
            model = (backend or {}).get("model")
            if backend is not None and model:
                return backend_id, model, backend
        return None

    def complete_task(
        self,
        task: str,
        prompt: str,
        *,
        system: str | None = None,
        max_tokens: int | None = None,
    ) -> str:
        """Complete a prompt using the model assigned to `task` in
        config['task_models'] (e.g. 'primary' / 'research' / 'chat').

        Unlike complete()'s general fallback_order, a task-scoped call
        either has an assigned, working model or raises a specific,
        classified error -- it never silently falls through to an
        unrelated chain.
        """
        task_models = self.config.get("task_models") or {}
        assignment = task_models.get(task) or {}

        backend_id = assignment.get("backend")
        model = assignment.get("model")
        backends = self.config.get("backends") or {}
        backend = backends.get(backend_id) if backend_id else None

        if backend is None or not model:
            # No explicit assignment (fresh install, cloud tenant, or an
            # assignment pointing at a backend that no longer exists). Rather
            # than hard-fail every LLM feature until someone visits Settings,
            # degrade gracefully to this task's existing fallback chain --
            # which is what these call sites used before per-task assignment.
            derived = self._default_task_model(task)
            if derived is None:
                raise TaskModelNotAssignedError(task)
            backend_id, model, backend = derived

        if not backend.get("enabled", True):
            raise TaskModelUnreachableError(task, backend_id, "backend is disabled")

        try:
            return self.complete(
                prompt,
                system=system,
                fallback_order=[backend_id],
                model_override=model,
                max_tokens=max_tokens,
            )
        except RuntimeError as e:
            raise TaskModelUnreachableError(task, backend_id, str(e)) from e


def _merged_cloud_llm_config(db_path: "Path") -> dict:
    """Build the effective LLM config dict for one cloud tenant: the shared,
    centrally-managed backends/fallback_order (read-only, from CONFIG_PATH)
    with task_models replaced by this tenant's own file. Never writes
    anything. task_models lives ONLY per-tenant in cloud mode -- there is no
    shared task_models to merge in, each tenant gets their own or an empty
    dict if they've never saved one.
    """
    import yaml as _yaml
    shared_cfg: dict = {}
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH) as f:
            shared_cfg = _yaml.safe_load(f) or {}

    tenant_task_models_path = Path(db_path).parent / "config" / "task_models.yaml"
    tenant_task_models: dict = {}
    if tenant_task_models_path.exists():
        with open(tenant_task_models_path) as f:
            tenant_data = _yaml.safe_load(f) or {}
        tenant_task_models = tenant_data.get("task_models", {})

    merged = dict(shared_cfg)
    merged["task_models"] = tenant_task_models
    return merged


def router_for_tenant(db_path: "Path", cloud_mode: bool) -> "LLMRouter":
    """Build the correctly-scoped LLMRouter for a task-scoped complete_task()
    call.

    Self-hosted (cloud_mode=False): returns a bare LLMRouter() -- completely
    unchanged from today's behavior. backends and task_models live together
    in the same file (CONFIG_PATH) for a single-tenant install, so the
    no-arg default already does the right thing.

    Cloud (cloud_mode=True): the shared backends/fallback_order config is
    centrally CF-managed and must never be written to by a per-tenant save
    -- but which model handles which task IS a real per-user preference.
    Merges the two into an in-memory dict and constructs LLMRouter from
    that dict directly (LLMRouter.__init__ already supports a raw dict
    config, no changes needed in circuitforge-core).
    """
    if not cloud_mode:
        return LLMRouter()
    return LLMRouter(_merged_cloud_llm_config(db_path))


# Module-level singleton for convenience
_router: LLMRouter | None = None


def complete(prompt: str, system: str | None = None) -> str:
    global _router
    if _router is None:
        _router = LLMRouter()
    return _router.complete(prompt, system)
