# scripts/task_scheduler.py
"""Resource-aware batch scheduler for LLM background tasks.

Routes LLM task types through per-type deques with VRAM-aware scheduling.
Non-LLM tasks bypass this module — routing lives in scripts/task_runner.py.

Public API:
    LLM_TASK_TYPES  — set of task type strings routed through the scheduler
    get_scheduler() — lazy singleton accessor
    reset_scheduler() — test teardown only
"""
import logging
import sqlite3
import threading
from collections import deque, namedtuple
from pathlib import Path
from typing import Callable, Optional

# Module-level import so tests can monkeypatch scripts.task_scheduler._get_gpus
try:
    from scripts.preflight import get_gpus as _get_gpus
except Exception:  # graceful degradation if preflight unavailable
    _get_gpus = lambda: []

logger = logging.getLogger(__name__)

# Task types that go through the scheduler (all others spawn free threads)
LLM_TASK_TYPES: frozenset[str] = frozenset({
    "cover_letter",
    "company_research",
    "wizard_generate",
})

# Conservative peak VRAM estimates (GB) per task type.
# Overridable per-install via scheduler.vram_budgets in config/llm.yaml.
DEFAULT_VRAM_BUDGETS: dict[str, float] = {
    "cover_letter":     2.5,   # alex-cover-writer:latest (~2GB GGUF + headroom)
    "company_research": 5.0,   # llama3.1:8b or vllm model
    "wizard_generate":  2.5,   # same model family as cover_letter
}

# Lightweight task descriptor stored in per-type deques
TaskSpec = namedtuple("TaskSpec", ["id", "job_id", "params"])


class TaskScheduler:
    """Resource-aware LLM task batch scheduler. Use get_scheduler() — not direct construction."""
    pass


# ── Singleton ─────────────────────────────────────────────────────────────────

_scheduler: Optional[TaskScheduler] = None
_scheduler_lock = threading.Lock()


def get_scheduler(db_path: Path, run_task_fn: Callable = None) -> TaskScheduler:
    """Return the process-level TaskScheduler singleton, constructing it if needed.

    run_task_fn is required on the first call (when the singleton is constructed);
    ignored on subsequent calls. Pass scripts.task_runner._run_task.
    """
    raise NotImplementedError


def reset_scheduler() -> None:
    """Shut down and clear the singleton. TEST TEARDOWN ONLY — not for production use."""
    raise NotImplementedError
