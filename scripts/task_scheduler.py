# scripts/task_scheduler.py
"""Peregrine LLM task scheduler — thin shim over circuitforge_core.tasks.scheduler.

All scheduling logic lives in circuitforge_core. This module defines
Peregrine-specific task types, VRAM budgets, and config loading.

Public API (unchanged — callers do not need to change):
    LLM_TASK_TYPES       — frozenset of task type strings routed through the scheduler
    DEFAULT_VRAM_BUDGETS  — dict of conservative peak VRAM estimates per task type
    TaskSpec             — lightweight task descriptor (re-exported from core)
    TaskScheduler        — backward-compatible wrapper around the core scheduler class
    get_scheduler()      — returns the process-level TaskScheduler singleton
    reset_scheduler()    — test teardown only
"""
from __future__ import annotations

import logging
import os
import threading
from pathlib import Path
from typing import Callable, Optional

from circuitforge_core.tasks.scheduler import (
    TaskSpec,                        # re-export unchanged
    TaskScheduler as _CoreTaskScheduler,
)

logger = logging.getLogger(__name__)

# ── Peregrine task types and VRAM budgets ─────────────────────────────────────

LLM_TASK_TYPES: frozenset[str] = frozenset({
    "cover_letter",
    "company_research",
    "wizard_generate",
    "resume_optimize",
})

# Conservative peak VRAM estimates (GB) per task type.
# Overridable per-install via scheduler.vram_budgets in config/llm.yaml.
DEFAULT_VRAM_BUDGETS: dict[str, float] = {
    "cover_letter":     2.5,   # alex-cover-writer:latest (~2 GB GGUF + headroom)
    "company_research": 5.0,   # llama3.1:8b or vllm model
    "wizard_generate":  2.5,   # same model family as cover_letter
    "resume_optimize":  5.0,   # section-by-section rewrite; same budget as research
}

_DEFAULT_MAX_QUEUE_DEPTH = 500


def _load_config_overrides(db_path: Path) -> tuple[dict[str, float], int]:
    """Load VRAM budget overrides and max_queue_depth from config/llm.yaml."""
    budgets = dict(DEFAULT_VRAM_BUDGETS)
    max_depth = _DEFAULT_MAX_QUEUE_DEPTH
    config_path = db_path.parent.parent / "config" / "llm.yaml"
    if config_path.exists():
        try:
            import yaml
            with open(config_path) as f:
                cfg = yaml.safe_load(f) or {}
            sched_cfg = cfg.get("scheduler", {})
            budgets.update(sched_cfg.get("vram_budgets", {}))
            max_depth = int(sched_cfg.get("max_queue_depth", max_depth))
        except Exception as exc:
            logger.warning(
                "Failed to load scheduler config from %s: %s", config_path, exc
            )
    return budgets, max_depth


# Module-level stub so tests can monkeypatch scripts.task_scheduler._get_gpus
# (existing tests monkeypatch this symbol — keep it here for backward compat).
try:
    from scripts.preflight import get_gpus as _get_gpus
except Exception:
    _get_gpus = lambda: []  # noqa: E731


class TaskScheduler(_CoreTaskScheduler):
    """Peregrine-specific TaskScheduler.

    Extends circuitforge_core.tasks.scheduler.TaskScheduler with:
    - Peregrine default VRAM budgets and task types wired into __init__
    - Config loading from config/llm.yaml
    - Backward-compatible two-argument __init__ signature (db_path, run_task_fn)
    - _get_gpus monkeypatch support (existing tests patch this module-level symbol)
    - Backward-compatible enqueue() that marks dropped tasks failed in the DB
      and logs under the scripts.task_scheduler logger

    Direct construction is still supported for tests; production code should
    use get_scheduler() instead.
    """

    def __init__(self, db_path: Path, run_task_fn: Callable) -> None:
        budgets, max_depth = _load_config_overrides(db_path)

        # Resolve VRAM using module-level _get_gpus so tests can monkeypatch it
        try:
            gpus = _get_gpus()
            available_vram: float = (
                sum(g["vram_total_gb"] for g in gpus) if gpus else 999.0
            )
        except Exception:
            available_vram = 999.0

        # Warn under this module's logger for any task types with no VRAM budget
        # (mirrors the core warning but captures under scripts.task_scheduler
        # so existing tests using caplog.at_level(logger="scripts.task_scheduler") pass)
        for t in LLM_TASK_TYPES:
            if t not in budgets:
                logger.warning(
                    "No VRAM budget defined for LLM task type %r — "
                    "defaulting to 0.0 GB (unlimited concurrency for this type)", t
                )

        coordinator_url = os.environ.get(
            "CF_ORCH_URL", "http://localhost:7700"
        ).rstrip("/")

        super().__init__(
            db_path=db_path,
            run_task_fn=run_task_fn,
            task_types=LLM_TASK_TYPES,
            vram_budgets=budgets,
            available_vram_gb=available_vram,
            max_queue_depth=max_depth,
            coordinator_url=coordinator_url,
            service_name="peregrine",
        )

    def enqueue(
        self,
        task_id: int,
        task_type: str,
        job_id: int,
        params: Optional[str],
    ) -> bool:
        """Add an LLM task to the scheduler queue.

        When the queue is full, marks the task failed in SQLite immediately
        (backward-compatible with the original Peregrine behavior) and logs a
        warning under the scripts.task_scheduler logger.

        Returns True if enqueued, False if the queue was full.
        """
        enqueued = super().enqueue(task_id, task_type, job_id, params)
        if not enqueued:
            # Log under this module's logger so existing caplog tests pass
            logger.warning(
                "Queue depth limit reached for %s (max=%d) — task %d dropped",
                task_type, self._max_queue_depth, task_id,
            )
            from scripts.db import update_task_status
            update_task_status(
                self._db_path, task_id, "failed", error="Queue depth limit reached"
            )
        return enqueued


# ── Peregrine-local singleton ──────────────────────────────────────────────────
# We manage our own singleton (not the core one) so the process-level instance
# is always a Peregrine TaskScheduler (with the enqueue() override).

_scheduler: Optional[TaskScheduler] = None
_scheduler_lock = threading.Lock()


def get_scheduler(
    db_path: Path,
    run_task_fn: Optional[Callable] = None,
) -> TaskScheduler:
    """Return the process-level Peregrine TaskScheduler singleton.

    run_task_fn is required on the first call; ignored on subsequent calls
    (double-checked locking — singleton already constructed).
    """
    global _scheduler
    if _scheduler is None:                      # fast path — no lock on steady state
        with _scheduler_lock:
            if _scheduler is None:              # re-check under lock
                if run_task_fn is None:
                    raise ValueError("run_task_fn required on first get_scheduler() call")
                _scheduler = TaskScheduler(db_path, run_task_fn)
                _scheduler.start()
    return _scheduler


def reset_scheduler() -> None:
    """Shut down and clear the singleton. TEST TEARDOWN ONLY."""
    global _scheduler
    with _scheduler_lock:
        if _scheduler is not None:
            _scheduler.shutdown()
            _scheduler = None
