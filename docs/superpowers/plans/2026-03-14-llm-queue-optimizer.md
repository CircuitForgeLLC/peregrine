# LLM Queue Optimizer Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace Peregrine's spawn-per-task LLM threading model with a resource-aware batch scheduler that groups tasks by model type, respects VRAM budgets, and survives process restarts.

**Architecture:** A new `TaskScheduler` singleton (in `scripts/task_scheduler.py`) maintains per-type deques for LLM tasks (`cover_letter`, `company_research`, `wizard_generate`). A scheduler daemon thread picks the deepest queue that fits in available VRAM and runs it serially; multiple type batches may overlap when VRAM allows. Non-LLM tasks (`discovery`, `email_sync`, etc.) continue to spawn free threads unchanged. On restart, `queued` LLM tasks are re-loaded from SQLite; only `running` tasks (results unknown) are reset to `failed`.

**Tech Stack:** Python 3.12, SQLite (via `scripts/db.py`), `threading`, `collections.deque`, `scripts/preflight.py` (VRAM detection), pytest

**Spec:** `docs/superpowers/specs/2026-03-14-llm-queue-optimizer-design.md`

**Worktree:** `/Library/Development/CircuitForge/peregrine/.worktrees/feature-llm-queue-optimizer/`

**All commands run from worktree root.** Pytest: `/devl/miniconda3/envs/job-seeker/bin/pytest`

---

## Chunk 1: Foundation

Tasks 1–3. DB helper, config update, and skeleton module. No threading yet.

---

### Task 1: `reset_running_tasks()` in `scripts/db.py`

Adds a focused restart-safe helper that resets only `running` tasks to `failed`, leaving `queued` rows untouched for the scheduler to resume.

**Files:**
- Modify: `scripts/db.py` (after `kill_stuck_tasks()`, ~line 367)
- Create: `tests/test_task_scheduler.py` (first test)

- [ ] **Step 1: Create the test file with the first failing test**

Create `tests/test_task_scheduler.py`:

```python
# tests/test_task_scheduler.py
"""Tests for scripts/task_scheduler.py and related db helpers."""
import sqlite3
import threading
import time
from collections import deque
from pathlib import Path

import pytest

from scripts.db import init_db, reset_running_tasks


@pytest.fixture
def tmp_db(tmp_path):
    db = tmp_path / "test.db"
    init_db(db)
    return db


def test_reset_running_tasks_resets_only_running(tmp_db):
    """reset_running_tasks() marks running→failed but leaves queued untouched."""
    conn = sqlite3.connect(tmp_db)
    conn.execute(
        "INSERT INTO background_tasks (task_type, job_id, status) VALUES (?,?,?)",
        ("cover_letter", 1, "running"),
    )
    conn.execute(
        "INSERT INTO background_tasks (task_type, job_id, status) VALUES (?,?,?)",
        ("company_research", 2, "queued"),
    )
    conn.commit()
    conn.close()

    count = reset_running_tasks(tmp_db)

    conn = sqlite3.connect(tmp_db)
    rows = {r[0]: r[1] for r in conn.execute(
        "SELECT task_type, status FROM background_tasks"
    ).fetchall()}
    conn.close()

    assert count == 1
    assert rows["cover_letter"] == "failed"
    assert rows["company_research"] == "queued"


def test_reset_running_tasks_returns_zero_when_nothing_running(tmp_db):
    """Returns 0 when no running tasks exist."""
    conn = sqlite3.connect(tmp_db)
    conn.execute(
        "INSERT INTO background_tasks (task_type, job_id, status) VALUES (?,?,?)",
        ("cover_letter", 1, "queued"),
    )
    conn.commit()
    conn.close()

    assert reset_running_tasks(tmp_db) == 0
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
/devl/miniconda3/envs/job-seeker/bin/pytest tests/test_task_scheduler.py -v
```

Expected: `ImportError: cannot import name 'reset_running_tasks' from 'scripts.db'`

- [ ] **Step 3: Add `reset_running_tasks()` to `scripts/db.py`**

Insert after `kill_stuck_tasks()` (~line 367):

```python
def reset_running_tasks(db_path: Path = DEFAULT_DB) -> int:
    """On restart: mark in-flight tasks failed. Queued tasks survive for the scheduler."""
    conn = sqlite3.connect(db_path)
    count = conn.execute(
        "UPDATE background_tasks SET status='failed', error='Interrupted by restart',"
        " finished_at=datetime('now') WHERE status='running'"
    ).rowcount
    conn.commit()
    conn.close()
    return count
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
/devl/miniconda3/envs/job-seeker/bin/pytest tests/test_task_scheduler.py -v
```

Expected: `2 passed`

- [ ] **Step 5: Commit**

```bash
git add scripts/db.py tests/test_task_scheduler.py
git commit -m "feat(db): add reset_running_tasks() for durable scheduler restart"
```

---

### Task 2: Add `scheduler:` section to `config/llm.yaml.example`

Documents VRAM budgets so operators know what to configure.

**Files:**
- Modify: `config/llm.yaml.example` (append at end)

- [ ] **Step 1: Append scheduler config section**

Add to the end of `config/llm.yaml.example`:

```yaml

# ── Scheduler — LLM batch queue optimizer ─────────────────────────────────────
# The scheduler batches LLM tasks by model type to avoid GPU model switching.
# VRAM budgets are conservative peak estimates (GB) for each task type.
# Increase if your models are larger; decrease if tasks share GPU memory well.
scheduler:
  vram_budgets:
    cover_letter: 2.5       # alex-cover-writer:latest (~2GB GGUF + headroom)
    company_research: 5.0   # llama3.1:8b or vllm model
    wizard_generate: 2.5    # same model family as cover_letter
  max_queue_depth: 500      # max pending tasks per type before drops (with logged warning)
```

- [ ] **Step 2: Verify the file is valid YAML**

```bash
conda run -n job-seeker python -c "import yaml; yaml.safe_load(open('config/llm.yaml.example'))"
```

Expected: no output (no error)

- [ ] **Step 3: Commit**

```bash
git add config/llm.yaml.example
git commit -m "docs(config): add scheduler VRAM budget config to llm.yaml.example"
```

---

### Task 3: Create `scripts/task_scheduler.py` skeleton

Establishes the module with constants, `TaskSpec`, and an empty `TaskScheduler` class. Subsequent tasks fill in the implementation method by method under TDD.

**Files:**
- Create: `scripts/task_scheduler.py`

- [ ] **Step 1: Create the skeleton file**

Create `scripts/task_scheduler.py`:

```python
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
```

- [ ] **Step 2: Verify the module imports cleanly**

```bash
conda run -n job-seeker python -c "from scripts.task_scheduler import LLM_TASK_TYPES, TaskSpec, TaskScheduler; print('ok')"
```

Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add scripts/task_scheduler.py
git commit -m "feat(scheduler): add task_scheduler.py skeleton with constants and TaskSpec"
```

---

## Chunk 2: Scheduler Core

Tasks 4–7. Implements `TaskScheduler` method-by-method under TDD: init, enqueue, loop, workers, singleton, and durability.

---

### Task 4: `TaskScheduler.__init__()` — budget loading and VRAM detection

**Files:**
- Modify: `scripts/task_scheduler.py` (replace `pass` in class body)
- Modify: `tests/test_task_scheduler.py` (add tests)

- [ ] **Step 1: Add failing tests**

Append to `tests/test_task_scheduler.py`:

```python
from scripts.task_scheduler import (
    TaskScheduler, LLM_TASK_TYPES, DEFAULT_VRAM_BUDGETS,
    get_scheduler, reset_scheduler,
)


def _noop_run_task(*args, **kwargs):
    """Stand-in for _run_task that does nothing."""
    pass


@pytest.fixture(autouse=True)
def clean_scheduler():
    """Reset singleton between every test."""
    yield
    reset_scheduler()


def test_default_budgets_used_when_no_config(tmp_db):
    """Scheduler falls back to DEFAULT_VRAM_BUDGETS when config key absent."""
    s = TaskScheduler(tmp_db, _noop_run_task)
    assert s._budgets == DEFAULT_VRAM_BUDGETS


def test_config_budgets_override_defaults(tmp_db, tmp_path):
    """Values in llm.yaml scheduler.vram_budgets override defaults."""
    config_dir = tmp_db.parent.parent / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "llm.yaml").write_text(
        "scheduler:\n  vram_budgets:\n    cover_letter: 9.9\n"
    )
    s = TaskScheduler(tmp_db, _noop_run_task)
    assert s._budgets["cover_letter"] == 9.9
    # Non-overridden keys still use defaults
    assert s._budgets["company_research"] == DEFAULT_VRAM_BUDGETS["company_research"]


def test_missing_budget_logs_warning(tmp_db, caplog):
    """A type in LLM_TASK_TYPES with no budget entry logs a warning."""
    import logging
    # Temporarily add a type with no budget
    original = LLM_TASK_TYPES.copy() if hasattr(LLM_TASK_TYPES, 'copy') else set(LLM_TASK_TYPES)
    from scripts import task_scheduler as ts
    ts.LLM_TASK_TYPES = frozenset(LLM_TASK_TYPES | {"orphan_type"})
    try:
        with caplog.at_level(logging.WARNING, logger="scripts.task_scheduler"):
            s = TaskScheduler(tmp_db, _noop_run_task)
        assert any("orphan_type" in r.message for r in caplog.records)
    finally:
        ts.LLM_TASK_TYPES = frozenset(original)


def test_cpu_only_system_gets_unlimited_vram(tmp_db, monkeypatch):
    """_available_vram is 999.0 when _get_gpus() returns empty list."""
    # Patch the module-level _get_gpus in task_scheduler (not preflight)
    # so __init__'s _ts_mod._get_gpus() call picks up the mock.
    monkeypatch.setattr("scripts.task_scheduler._get_gpus", lambda: [])
    s = TaskScheduler(tmp_db, _noop_run_task)
    assert s._available_vram == 999.0


def test_gpu_vram_summed_across_all_gpus(tmp_db, monkeypatch):
    """_available_vram sums vram_total_gb across all detected GPUs."""
    fake_gpus = [
        {"name": "RTX 3090", "vram_total_gb": 24.0, "vram_free_gb": 20.0},
        {"name": "RTX 3090", "vram_total_gb": 24.0, "vram_free_gb": 18.0},
    ]
    monkeypatch.setattr("scripts.task_scheduler._get_gpus", lambda: fake_gpus)
    s = TaskScheduler(tmp_db, _noop_run_task)
    assert s._available_vram == 48.0
```

- [ ] **Step 2: Run to confirm failures**

```bash
/devl/miniconda3/envs/job-seeker/bin/pytest tests/test_task_scheduler.py -v -k "budget or vram or warning"
```

Expected: multiple failures — `TaskScheduler.__init__` not implemented yet

- [ ] **Step 3: Implement `__init__`**

Replace `pass` in the `TaskScheduler` class with:

```python
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
        from scripts import task_scheduler as _ts_mod
        gpus = _ts_mod._get_gpus()
        self._available_vram: float = (
            sum(g["vram_total_gb"] for g in gpus) if gpus else 999.0
        )
    except Exception:
        self._available_vram = 999.0
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
/devl/miniconda3/envs/job-seeker/bin/pytest tests/test_task_scheduler.py -v -k "budget or vram or warning"
```

Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add scripts/task_scheduler.py tests/test_task_scheduler.py
git commit -m "feat(scheduler): implement TaskScheduler.__init__ with budget loading and VRAM detection"
```

---

### Task 5: `TaskScheduler.enqueue()` — depth guard and ghost-row cleanup

**Files:**
- Modify: `scripts/task_scheduler.py` (add `enqueue` method)
- Modify: `tests/test_task_scheduler.py` (add tests)

- [ ] **Step 1: Add failing tests**

Append to `tests/test_task_scheduler.py`:

```python
def test_enqueue_adds_taskspec_to_deque(tmp_db):
    """enqueue() appends a TaskSpec to the correct per-type deque."""
    s = TaskScheduler(tmp_db, _noop_run_task)
    s.enqueue(1, "cover_letter", 10, None)
    s.enqueue(2, "cover_letter", 11, '{"key": "val"}')

    assert len(s._queues["cover_letter"]) == 2
    assert s._queues["cover_letter"][0].id == 1
    assert s._queues["cover_letter"][1].id == 2


def test_enqueue_wakes_scheduler(tmp_db):
    """enqueue() sets the _wake event so the scheduler loop re-evaluates."""
    s = TaskScheduler(tmp_db, _noop_run_task)
    assert not s._wake.is_set()
    s.enqueue(1, "cover_letter", 10, None)
    assert s._wake.is_set()


def test_max_queue_depth_marks_task_failed(tmp_db):
    """When queue is at max_queue_depth, dropped task is marked failed in DB."""
    from scripts.db import insert_task

    s = TaskScheduler(tmp_db, _noop_run_task)
    s._max_queue_depth = 2

    # Fill the queue to the limit via direct deque manipulation (no DB rows needed)
    from scripts.task_scheduler import TaskSpec
    s._queues.setdefault("cover_letter", deque())
    s._queues["cover_letter"].append(TaskSpec(99, 1, None))
    s._queues["cover_letter"].append(TaskSpec(100, 2, None))

    # Insert a real DB row for the task we're about to drop
    task_id, _ = insert_task(tmp_db, "cover_letter", 3)

    # This enqueue should be rejected and the DB row marked failed
    s.enqueue(task_id, "cover_letter", 3, None)

    conn = sqlite3.connect(tmp_db)
    row = conn.execute(
        "SELECT status, error FROM background_tasks WHERE id=?", (task_id,)
    ).fetchone()
    conn.close()

    assert row[0] == "failed"
    assert "depth" in row[1].lower()
    # Queue length unchanged
    assert len(s._queues["cover_letter"]) == 2


def test_max_queue_depth_logs_warning(tmp_db, caplog):
    """Queue depth overflow logs a WARNING."""
    import logging
    from scripts.db import insert_task
    from scripts.task_scheduler import TaskSpec

    s = TaskScheduler(tmp_db, _noop_run_task)
    s._max_queue_depth = 0  # immediately at limit

    task_id, _ = insert_task(tmp_db, "cover_letter", 1)
    with caplog.at_level(logging.WARNING, logger="scripts.task_scheduler"):
        s.enqueue(task_id, "cover_letter", 1, None)

    assert any("depth" in r.message.lower() for r in caplog.records)
```

- [ ] **Step 2: Run to confirm failures**

```bash
/devl/miniconda3/envs/job-seeker/bin/pytest tests/test_task_scheduler.py -v -k "enqueue or depth"
```

Expected: failures — `enqueue` not defined

- [ ] **Step 3: Implement `enqueue()`**

Add method to `TaskScheduler` (after `__init__`):

```python
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
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
/devl/miniconda3/envs/job-seeker/bin/pytest tests/test_task_scheduler.py -v -k "enqueue or depth"
```

Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add scripts/task_scheduler.py tests/test_task_scheduler.py
git commit -m "feat(scheduler): implement enqueue() with depth guard and ghost-row cleanup"
```

---

### Task 6: Scheduler loop, batch worker, `start()`, and `shutdown()`

The core execution engine. The scheduler loop picks the deepest eligible queue and starts a serial batch worker for it.

**Files:**
- Modify: `scripts/task_scheduler.py` (add `start`, `shutdown`, `_scheduler_loop`, `_batch_worker`)
- Modify: `tests/test_task_scheduler.py` (add threading tests)

- [ ] **Step 1: Add failing tests**

Append to `tests/test_task_scheduler.py`:

```python
# ── Threading helpers ─────────────────────────────────────────────────────────

def _make_recording_run_task(log: list, done_event: threading.Event, expected: int):
    """Returns a mock _run_task that records (task_id, task_type) and sets done when expected count reached."""
    def _run(db_path, task_id, task_type, job_id, params):
        log.append((task_id, task_type))
        if len(log) >= expected:
            done_event.set()
    return _run


def _start_scheduler(tmp_db, run_task_fn, available_vram=999.0):
    s = TaskScheduler(tmp_db, run_task_fn)
    s._available_vram = available_vram
    s.start()
    return s


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_deepest_queue_wins_first_slot(tmp_db):
    """Type with more queued tasks starts first when VRAM only fits one type."""
    log, done = [], threading.Event()

    # Build scheduler but DO NOT start it yet — enqueue all tasks first
    # so the scheduler sees the full picture on its very first wake.
    run_task_fn = _make_recording_run_task(log, done, 4)
    s = TaskScheduler(tmp_db, run_task_fn)
    s._available_vram = 3.0  # fits cover_letter (2.5) but not +company_research (5.0)

    # Enqueue cover_letter (3 tasks) and company_research (1 task) before start.
    # cover_letter has the deeper queue and must win the first batch slot.
    for i in range(3):
        s.enqueue(i + 1, "cover_letter", i + 1, None)
    s.enqueue(4, "company_research", 4, None)

    s.start()  # scheduler now sees all tasks atomically on its first iteration
    assert done.wait(timeout=5.0), "timed out — not all 4 tasks completed"
    s.shutdown()

    assert len(log) == 4
    cl = [i for i, (_, t) in enumerate(log) if t == "cover_letter"]
    cr = [i for i, (_, t) in enumerate(log) if t == "company_research"]
    assert len(cl) == 3 and len(cr) == 1
    assert max(cl) < min(cr), "All cover_letter tasks must finish before company_research starts"


def test_fifo_within_type(tmp_db):
    """Tasks of the same type execute in arrival (FIFO) order."""
    log, done = [], threading.Event()
    s = _start_scheduler(tmp_db, _make_recording_run_task(log, done, 3))

    for task_id in [10, 20, 30]:
        s.enqueue(task_id, "cover_letter", task_id, None)

    assert done.wait(timeout=5.0), "timed out — not all 3 tasks completed"
    s.shutdown()

    assert [task_id for task_id, _ in log] == [10, 20, 30]


def test_concurrent_batches_when_vram_allows(tmp_db):
    """Two type batches start simultaneously when VRAM fits both."""
    started = {"cover_letter": threading.Event(), "company_research": threading.Event()}
    all_done = threading.Event()
    log = []

    def run_task(db_path, task_id, task_type, job_id, params):
        started[task_type].set()
        log.append(task_type)
        if len(log) >= 2:
            all_done.set()

    # VRAM=10.0 fits both cover_letter (2.5) and company_research (5.0) simultaneously
    s = _start_scheduler(tmp_db, run_task, available_vram=10.0)
    s.enqueue(1, "cover_letter", 1, None)
    s.enqueue(2, "company_research", 2, None)

    all_done.wait(timeout=5.0)
    s.shutdown()

    # Both types should have started (possibly overlapping)
    assert started["cover_letter"].is_set()
    assert started["company_research"].is_set()


def test_new_tasks_picked_up_mid_batch(tmp_db):
    """A task enqueued while a batch is running is consumed in the same batch."""
    log, done = [], threading.Event()
    task1_started = threading.Event()   # fires when task 1 begins executing
    task2_ready = threading.Event()     # fires when task 2 has been enqueued

    def run_task(db_path, task_id, task_type, job_id, params):
        if task_id == 1:
            task1_started.set()         # signal: task 1 is now running
            task2_ready.wait(timeout=2.0)  # wait for task 2 to be in the deque
        log.append(task_id)
        if len(log) >= 2:
            done.set()

    s = _start_scheduler(tmp_db, run_task)
    s.enqueue(1, "cover_letter", 1, None)
    task1_started.wait(timeout=2.0)    # wait until task 1 is actually executing
    s.enqueue(2, "cover_letter", 2, None)
    task2_ready.set()                  # unblock task 1 so it finishes

    assert done.wait(timeout=5.0), "timed out — task 2 never picked up mid-batch"
    s.shutdown()

    assert log == [1, 2]


def test_worker_crash_releases_vram(tmp_db):
    """If _run_task raises, _reserved_vram returns to 0 and scheduler continues."""
    log, done = [], threading.Event()

    def run_task(db_path, task_id, task_type, job_id, params):
        if task_id == 1:
            raise RuntimeError("simulated failure")
        log.append(task_id)
        done.set()

    s = _start_scheduler(tmp_db, run_task, available_vram=3.0)
    s.enqueue(1, "cover_letter", 1, None)
    s.enqueue(2, "cover_letter", 2, None)

    assert done.wait(timeout=5.0), "timed out — task 2 never completed after task 1 crash"
    s.shutdown()

    # Second task still ran, VRAM was released
    assert 2 in log
    assert s._reserved_vram == 0.0
```

- [ ] **Step 2: Run to confirm failures**

```bash
/devl/miniconda3/envs/job-seeker/bin/pytest tests/test_task_scheduler.py -v -k "batch or fifo or concurrent or mid_batch or crash"
```

Expected: failures — `start`, `shutdown` not defined

- [ ] **Step 3: Implement `start()`, `shutdown()`, `_scheduler_loop()`, `_batch_worker()`**

Add these methods to `TaskScheduler`:

```python
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
                if self._reserved_vram + budget <= self._available_vram:
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
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
/devl/miniconda3/envs/job-seeker/bin/pytest tests/test_task_scheduler.py -v -k "batch or fifo or concurrent or mid_batch or crash"
```

Expected: 5 passed

- [ ] **Step 5: Run all scheduler tests so far**

```bash
/devl/miniconda3/envs/job-seeker/bin/pytest tests/test_task_scheduler.py -v
```

Expected: all passing (no regressions)

- [ ] **Step 6: Commit**

```bash
git add scripts/task_scheduler.py tests/test_task_scheduler.py
git commit -m "feat(scheduler): implement scheduler loop and batch worker with VRAM-aware scheduling"
```

---

## Chunk 3: Integration

Tasks 7–11. Singleton, durability, routing shim, app.py startup change, and full suite verification.

---

### Task 7: Singleton — `get_scheduler()` and `reset_scheduler()`

**Files:**
- Modify: `scripts/task_scheduler.py` (implement the two functions)
- Modify: `tests/test_task_scheduler.py` (add tests)

- [ ] **Step 1: Add failing tests**

Append to `tests/test_task_scheduler.py`:

```python
def test_get_scheduler_returns_singleton(tmp_db):
    """Multiple calls to get_scheduler() return the same instance."""
    s1 = get_scheduler(tmp_db, _noop_run_task)
    s2 = get_scheduler(tmp_db, _noop_run_task)
    assert s1 is s2


def test_singleton_thread_safe(tmp_db):
    """Concurrent get_scheduler() calls produce exactly one instance."""
    instances = []
    errors = []

    def _get():
        try:
            instances.append(get_scheduler(tmp_db, _noop_run_task))
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=_get) for _ in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors
    assert len(set(id(s) for s in instances)) == 1  # all the same object


def test_reset_scheduler_cleans_up(tmp_db):
    """reset_scheduler() shuts down the scheduler; no threads linger."""
    s = get_scheduler(tmp_db, _noop_run_task)
    thread = s._thread
    assert thread.is_alive()

    reset_scheduler()

    thread.join(timeout=2.0)
    assert not thread.is_alive()

    # After reset, get_scheduler creates a fresh instance
    s2 = get_scheduler(tmp_db, _noop_run_task)
    assert s2 is not s
```

- [ ] **Step 2: Run to confirm failures**

```bash
/devl/miniconda3/envs/job-seeker/bin/pytest tests/test_task_scheduler.py -v -k "singleton or reset"
```

Expected: failures — `get_scheduler` / `reset_scheduler` raise `NotImplementedError`

- [ ] **Step 3: Implement `get_scheduler()` and `reset_scheduler()`**

Replace the `raise NotImplementedError` stubs at the bottom of `scripts/task_scheduler.py`:

```python
def get_scheduler(db_path: Path, run_task_fn: Callable = None) -> TaskScheduler:
    """Return the process-level TaskScheduler singleton, constructing it if needed.

    run_task_fn is required on the first call; ignored on subsequent calls.
    Safety: inner lock + double-check prevents double-construction under races.
    The outer None check is a fast-path performance optimisation only.
    """
    global _scheduler
    if _scheduler is None:                      # fast path — avoids lock on steady state
        with _scheduler_lock:
            if _scheduler is None:              # re-check under lock (double-checked locking)
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
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
/devl/miniconda3/envs/job-seeker/bin/pytest tests/test_task_scheduler.py -v -k "singleton or reset"
```

Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add scripts/task_scheduler.py tests/test_task_scheduler.py
git commit -m "feat(scheduler): implement thread-safe singleton get_scheduler/reset_scheduler"
```

---

### Task 8: Durability — re-queue surviving `queued` rows on startup

On construction, the scheduler loads pre-existing `queued` LLM tasks from SQLite into deques, so they execute after restart without user re-submission.

**Files:**
- Modify: `scripts/task_scheduler.py` (add durability query to `__init__`)
- Modify: `tests/test_task_scheduler.py` (add tests)

- [ ] **Step 1: Add failing tests**

Append to `tests/test_task_scheduler.py`:

```python
def test_durability_loads_queued_llm_tasks_on_startup(tmp_db):
    """Scheduler loads pre-existing queued LLM tasks into deques at construction."""
    from scripts.db import insert_task

    # Pre-insert queued rows simulating a prior run
    id1, _ = insert_task(tmp_db, "cover_letter", 1)
    id2, _ = insert_task(tmp_db, "company_research", 2)

    s = TaskScheduler(tmp_db, _noop_run_task)

    assert len(s._queues.get("cover_letter", [])) == 1
    assert s._queues["cover_letter"][0].id == id1
    assert len(s._queues.get("company_research", [])) == 1
    assert s._queues["company_research"][0].id == id2


def test_durability_excludes_non_llm_queued_tasks(tmp_db):
    """Non-LLM queued tasks are not loaded into the scheduler deques."""
    from scripts.db import insert_task

    insert_task(tmp_db, "discovery", 0)
    insert_task(tmp_db, "email_sync", 0)

    s = TaskScheduler(tmp_db, _noop_run_task)

    assert "discovery" not in s._queues or len(s._queues["discovery"]) == 0
    assert "email_sync" not in s._queues or len(s._queues["email_sync"]) == 0


def test_durability_preserves_fifo_order(tmp_db):
    """Queued tasks are loaded in created_at (FIFO) order."""
    conn = sqlite3.connect(tmp_db)
    # Insert with explicit timestamps to control order
    conn.execute(
        "INSERT INTO background_tasks (task_type, job_id, params, status, created_at)"
        " VALUES (?,?,?,?,?)", ("cover_letter", 1, None, "queued", "2026-01-01 10:00:00")
    )
    conn.execute(
        "INSERT INTO background_tasks (task_type, job_id, params, status, created_at)"
        " VALUES (?,?,?,?,?)", ("cover_letter", 2, None, "queued", "2026-01-01 09:00:00")
    )
    conn.commit()
    ids = [r[0] for r in conn.execute(
        "SELECT id FROM background_tasks ORDER BY created_at ASC"
    ).fetchall()]
    conn.close()

    s = TaskScheduler(tmp_db, _noop_run_task)

    loaded_ids = [t.id for t in s._queues["cover_letter"]]
    assert loaded_ids == ids
```

- [ ] **Step 2: Run to confirm failures**

```bash
/devl/miniconda3/envs/job-seeker/bin/pytest tests/test_task_scheduler.py -v -k "durability"
```

Expected: failures — deques empty on construction (durability not implemented yet)

- [ ] **Step 3: Add durability query to `__init__`**

Append to the end of `TaskScheduler.__init__()` (after VRAM detection):

```python
    # Durability: reload surviving 'queued' LLM tasks from prior run
    self._load_queued_tasks()
```

Add the private method to `TaskScheduler`:

```python
def _load_queued_tasks(self) -> None:
    """Load pre-existing queued LLM tasks from SQLite into deques (called once in __init__)."""
    llm_types = sorted(LLM_TASK_TYPES)  # sorted for deterministic SQL params in logs
    placeholders = ",".join("?" * len(llm_types))
    conn = sqlite3.connect(self._db_path)
    rows = conn.execute(
        f"SELECT id, task_type, job_id, params FROM background_tasks"
        f" WHERE status='queued' AND task_type IN ({placeholders})"
        f" ORDER BY created_at ASC",
        llm_types,
    ).fetchall()
    conn.close()

    for row_id, task_type, job_id, params in rows:
        q = self._queues.setdefault(task_type, deque())
        q.append(TaskSpec(row_id, job_id, params))

    if rows:
        logger.info("Scheduler: resumed %d queued task(s) from prior run", len(rows))
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
/devl/miniconda3/envs/job-seeker/bin/pytest tests/test_task_scheduler.py -v -k "durability"
```

Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add scripts/task_scheduler.py tests/test_task_scheduler.py
git commit -m "feat(scheduler): add durability — re-queue surviving LLM tasks on startup"
```

---

### Task 9: `submit_task()` routing shim in `task_runner.py`

Replaces the old spawn-per-task model with scheduler routing for LLM tasks while leaving non-LLM tasks unchanged.

**Files:**
- Modify: `scripts/task_runner.py` (`submit_task` function)
- Modify: `tests/test_task_scheduler.py` (add integration test)

- [ ] **Step 1: Add failing test**

Append to `tests/test_task_scheduler.py`:

```python
def test_non_llm_tasks_bypass_scheduler(tmp_db):
    """submit_task() for non-LLM types invoke _run_task directly, not enqueue()."""
    from scripts import task_runner

    # Initialize the singleton properly so submit_task routes correctly
    s = get_scheduler(tmp_db, _noop_run_task)

    run_task_calls = []
    enqueue_calls = []

    original_run_task = task_runner._run_task
    original_enqueue = s.enqueue

    def recording_run_task(*args, **kwargs):
        run_task_calls.append(args[2])  # task_type is 3rd arg

    def recording_enqueue(task_id, task_type, job_id, params):
        enqueue_calls.append(task_type)

    import unittest.mock as mock
    with mock.patch.object(task_runner, "_run_task", recording_run_task), \
         mock.patch.object(s, "enqueue", recording_enqueue):
        task_runner.submit_task(tmp_db, "discovery", 0)

    # discovery goes directly to _run_task; enqueue is never called
    assert "discovery" not in enqueue_calls
    # The scheduler deque is untouched
    assert "discovery" not in s._queues or len(s._queues["discovery"]) == 0


def test_llm_tasks_routed_to_scheduler(tmp_db):
    """submit_task() for LLM types calls enqueue(), not _run_task directly."""
    from scripts import task_runner

    s = get_scheduler(tmp_db, _noop_run_task)

    enqueue_calls = []
    original_enqueue = s.enqueue

    import unittest.mock as mock
    with mock.patch.object(s, "enqueue", side_effect=lambda *a, **kw: enqueue_calls.append(a[1]) or original_enqueue(*a, **kw)):
        task_runner.submit_task(tmp_db, "cover_letter", 1)

    assert "cover_letter" in enqueue_calls
```

- [ ] **Step 2: Run to confirm failures**

```bash
/devl/miniconda3/envs/job-seeker/bin/pytest tests/test_task_scheduler.py -v -k "bypass or routed"
```

Expected: failures — `submit_task` still spawns threads for all types

- [ ] **Step 3: Update `submit_task()` in `scripts/task_runner.py`**

Replace the existing `submit_task` function:

```python
def submit_task(db_path: Path = DEFAULT_DB, task_type: str = "",
                job_id: int = None,
                params: str | None = None) -> tuple[int, bool]:
    """Submit a background task.

    LLM task types (cover_letter, company_research, wizard_generate) are routed
    through the TaskScheduler for VRAM-aware batch scheduling.
    All other types spawn a free daemon thread as before.

    Returns (task_id, True) if a new task was queued.
    Returns (existing_id, False) if an identical task is already in-flight.
    """
    task_id, is_new = insert_task(db_path, task_type, job_id or 0, params=params)
    if is_new:
        from scripts.task_scheduler import get_scheduler, LLM_TASK_TYPES
        if task_type in LLM_TASK_TYPES:
            get_scheduler(db_path, run_task_fn=_run_task).enqueue(
                task_id, task_type, job_id or 0, params
            )
        else:
            t = threading.Thread(
                target=_run_task,
                args=(db_path, task_id, task_type, job_id or 0, params),
                daemon=True,
            )
            t.start()
    return task_id, is_new
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
/devl/miniconda3/envs/job-seeker/bin/pytest tests/test_task_scheduler.py -v -k "bypass or routed"
```

Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add scripts/task_runner.py tests/test_task_scheduler.py
git commit -m "feat(task_runner): route LLM tasks through scheduler in submit_task()"
```

---

### Task 10: `app.py` startup — replace inline SQL with `reset_running_tasks()`

Enables durability by leaving `queued` rows intact on restart.

**Files:**
- Modify: `app/app.py` (`_startup` function)

- [ ] **Step 1: Locate the exact lines to change in `app/app.py`**

The block to replace is inside `_startup()`. It looks like:

```python
conn.execute(
    "UPDATE background_tasks SET status='failed', error='Interrupted by server restart',"
    " finished_at=datetime('now') WHERE status IN ('queued','running')"
)
conn.commit()
```

- [ ] **Step 2: Replace the inline SQL block**

In `app/app.py`, find `_startup()`. At the start of the function body, **before** the existing `conn = sqlite3.connect(get_db_path())` block, add:

```python
    # Reset only in-flight tasks — queued tasks survive for the scheduler to resume.
    # MUST run before any submit_task() call in this function.
    from scripts.db import reset_running_tasks
    reset_running_tasks(get_db_path())
```

Then delete the inline SQL block and its `conn.commit()` call. Leave the `conn = sqlite3.connect(...)` that follows (used by the SearXNG re-queue logic) untouched.

The result should look like:

```python
@st.cache_resource
def _startup() -> None:
    """Runs exactly once per server lifetime (st.cache_resource).
    1. Marks zombie tasks as failed.
    2. Auto-queues re-runs for any research generated without SearXNG data,
       if SearXNG is now reachable.
    """
    # Reset only in-flight tasks — queued tasks survive for the scheduler to resume.
    # MUST run before any submit_task() call in this function.
    from scripts.db import reset_running_tasks
    reset_running_tasks(get_db_path())

    conn = sqlite3.connect(get_db_path())
    # ... remainder of function unchanged ...
```

- [ ] **Step 3: Verify the app module has valid syntax**

```bash
conda run -n job-seeker python -m py_compile app/app.py && echo "syntax ok"
```

Expected: `syntax ok` (avoids executing Streamlit module-level code which would fail outside a server context)

- [ ] **Step 4: Commit**

```bash
git add app/app.py
git commit -m "feat(app): use reset_running_tasks() on startup to preserve queued tasks"
```

---

### Task 11: Full suite verification

Run the complete test suite against the baseline (pre-existing failure already documented in issue #12).

**Files:** none — verification only

- [ ] **Step 1: Run the full test suite excluding the known pre-existing failure**

```bash
/devl/miniconda3/envs/job-seeker/bin/pytest tests/ -v -k "not test_generate_calls_llm_router" 2>&1 | tail -10
```

Expected: `N passed` with zero failures. Any failure here is a regression introduced by this feature.

- [ ] **Step 1b: Confirm the pre-existing failure still exists (and only that one)**

```bash
/devl/miniconda3/envs/job-seeker/bin/pytest tests/ -v 2>&1 | grep -E "FAILED|passed|failed" | tail -5
```

Expected: exactly `1 failed` (the pre-existing `test_generate_calls_llm_router`, tracked in issue #12)

- [ ] **Step 2: Verify no regressions in task runner tests**

```bash
/devl/miniconda3/envs/job-seeker/bin/pytest tests/ -v -k "task_runner or task_scheduler" 2>&1 | tail -20
```

Expected: all passing

- [ ] **Step 3: Final commit — update branch with feature complete marker**

```bash
git commit --allow-empty -m "feat: LLM queue optimizer complete — closes #2

Resource-aware batch scheduler for LLM tasks:
- scripts/task_scheduler.py (new): TaskScheduler singleton with VRAM-aware
  batch scheduling, durability, thread-safe singleton, memory safety
- scripts/task_runner.py: submit_task() routes LLM types through scheduler
- scripts/db.py: reset_running_tasks() for durable restart behavior
- app/app.py: _startup() preserves queued tasks on restart
- config/llm.yaml.example: scheduler VRAM budget config documented
- tests/test_task_scheduler.py (new): 13 tests covering all behaviors

Pre-existing failure: test_generate_calls_llm_router (issue #12, unrelated)"
```
