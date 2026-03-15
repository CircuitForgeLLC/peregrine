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

    def __init__(self, db_path: Path, run_task_fn: Callable) -> None:
        self._db_path = db_path
        self._run_task = run_task_fn

        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._queues: dict[str, deque] = {}
        self._active: dict[str, threading.Thread] = {}
        self._reserved_vram: float = 0.0
        self._thread: Optional[threading.Thread] = None

        # Load VRAM budgets: defaults + optional config overrides
        self._budgets: dict[str, float] = dict(DEFAULT_VRAM_BUDGETS)
        config_path = db_path.parent.parent / "config" / "llm.yaml"
        self._max_queue_depth: int = 500
        if config_path.exists():
            try:
                import yaml
                with open(config_path) as f:
                    cfg = yaml.safe_load(f) or {}
                sched_cfg = cfg.get("scheduler", {})
                self._budgets.update(sched_cfg.get("vram_budgets", {}))
                self._max_queue_depth = sched_cfg.get("max_queue_depth", 500)
            except Exception as exc:
                logger.warning("Failed to load scheduler config from %s: %s", config_path, exc)

        # Warn on LLM types with no budget entry after merge
        for t in LLM_TASK_TYPES:
            if t not in self._budgets:
                logger.warning(
                    "No VRAM budget defined for LLM task type %r — "
                    "defaulting to 0.0 GB (unlimited concurrency for this type)", t
                )

        # Detect total GPU VRAM; fall back to unlimited (999) on CPU-only systems.
        # Uses module-level _get_gpus so tests can monkeypatch scripts.task_scheduler._get_gpus.
        try:
            gpus = _get_gpus()
            self._available_vram: float = (
                sum(g["vram_total_gb"] for g in gpus) if gpus else 999.0
            )
        except Exception:
            self._available_vram = 999.0

    def enqueue(self, task_id: int, task_type: str, job_id: int,
                params: Optional[str]) -> None:
        """Add an LLM task to the scheduler queue.

        If the queue for this type is at max_queue_depth, the task is marked
        failed in SQLite immediately (no ghost queued rows) and a warning is logged.
        """
        from scripts.db import update_task_status

        with self._lock:
            q = self._queues.setdefault(task_type, deque())
            if len(q) >= self._max_queue_depth:
                logger.warning(
                    "Queue depth limit reached for %s (max=%d) — task %d dropped",
                    task_type, self._max_queue_depth, task_id,
                )
                update_task_status(self._db_path, task_id, "failed",
                                   error="Queue depth limit reached")
                return
            q.append(TaskSpec(task_id, job_id, params))

        self._wake.set()

    def start(self) -> None:
        """Start the background scheduler loop thread. Call once after construction."""
        self._thread = threading.Thread(
            target=self._scheduler_loop, name="task-scheduler", daemon=True
        )
        self._thread.start()

    def shutdown(self, timeout: float = 5.0) -> None:
        """Signal the scheduler to stop and wait for it to exit."""
        self._stop.set()
        self._wake.set()  # unblock any wait()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)

    def _scheduler_loop(self) -> None:
        """Main scheduler daemon — wakes on enqueue or batch completion."""
        while not self._stop.is_set():
            self._wake.wait(timeout=30)
            self._wake.clear()

            with self._lock:
                # Defense in depth: reap externally-killed batch threads.
                # In normal operation _active.pop() runs in finally before _wake fires,
                # so this reap finds nothing — no double-decrement risk.
                for t, thread in list(self._active.items()):
                    if not thread.is_alive():
                        self._reserved_vram -= self._budgets.get(t, 0.0)
                        del self._active[t]

                # Start new type batches while VRAM allows
                candidates = sorted(
                    [t for t in self._queues if self._queues[t] and t not in self._active],
                    key=lambda t: len(self._queues[t]),
                    reverse=True,
                )
                for task_type in candidates:
                    budget = self._budgets.get(task_type, 0.0)
                    # Always allow at least one batch to run even if its budget
                    # exceeds _available_vram (prevents permanent starvation when
                    # a single type's budget is larger than the VRAM ceiling).
                    if self._reserved_vram == 0.0 or self._reserved_vram + budget <= self._available_vram:
                        thread = threading.Thread(
                            target=self._batch_worker,
                            args=(task_type,),
                            name=f"batch-{task_type}",
                            daemon=True,
                        )
                        self._active[task_type] = thread
                        self._reserved_vram += budget
                        thread.start()

    def _batch_worker(self, task_type: str) -> None:
        """Serial consumer for one task type. Runs until the type's deque is empty."""
        try:
            while True:
                with self._lock:
                    q = self._queues.get(task_type)
                    if not q:
                        break
                    task = q.popleft()
                # _run_task is scripts.task_runner._run_task (passed at construction)
                self._run_task(
                    self._db_path, task.id, task_type, task.job_id, task.params
                )
        finally:
            # Always release — even if _run_task raises.
            # _active.pop here prevents the scheduler loop reap from double-decrementing.
            with self._lock:
                self._active.pop(task_type, None)
                self._reserved_vram -= self._budgets.get(task_type, 0.0)
            self._wake.set()


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
