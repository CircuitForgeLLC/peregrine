# LLM Queue Optimizer — Design Spec

**Date:** 2026-03-14
**Branch:** `feature/llm-queue-optimizer`
**Closes:** [#2](https://git.opensourcesolarpunk.com/Circuit-Forge/peregrine/issues/2)
**Author:** pyr0ball

---

## Problem

On single-GPU and CPU-only systems, the background task runner spawns a daemon thread for every task immediately on submission. When a user approves N jobs at once, N threads race to load their respective LLM models simultaneously, causing repeated model swaps and significant latency overhead.

The root issue is that `submit_task()` is a spawn-per-task model with no scheduling layer. SQLite's `background_tasks` table is a status log, not a consumed work queue.

Additionally, on restart all `queued` and `running` tasks are cleared to `failed` (inline SQL in `app.py`'s `_startup()`), discarding pending work that had not yet started executing.

---

## Goals

- Eliminate unnecessary model switching by batching LLM tasks by type
- Allow concurrent model execution when VRAM permits multiple models simultaneously
- Preserve FIFO ordering within each task type
- Survive process restarts — `queued` tasks resume after restart; only `running` tasks (whose results are unknown) are reset to `failed`
- Apply to all tiers (no tier gating)
- Keep non-LLM tasks (discovery, email sync, scrape, enrich) unaffected — they continue to spawn free threads

---

## Non-Goals

- Changing the LLM router fallback chain
- Adding new task types
- Tier gating on the scheduler
- Persistent task history in memory
- Durability for non-LLM task types (discovery, email_sync, etc. — these do not survive restarts, same as current behavior)
- Dynamic VRAM tracking — `_available_vram` is read once at startup and not refreshed (see Known Limitations)

---

## Architecture

### Task Classification

```python
LLM_TASK_TYPES = {"cover_letter", "company_research", "wizard_generate"}
```

The routing rule is: if `task_type in LLM_TASK_TYPES`, route through the scheduler. Everything else spawns a free thread unchanged from the current implementation. **Future task types default to bypass mode** unless explicitly added to `LLM_TASK_TYPES` — which is the safe default (bypass = current behavior).

`LLM_TASK_TYPES` is defined in `scripts/task_scheduler.py` and imported by `scripts/task_runner.py` for routing. This import direction (task_runner imports from task_scheduler) avoids circular imports because `task_scheduler.py` does **not** import from `task_runner.py`.

Current non-LLM types (all bypass scheduler): `discovery`, `email_sync`, `scrape_url`, `enrich_descriptions`, `enrich_craigslist`, `prepare_training`.

### Routing in `submit_task()` — No Circular Import

The routing split lives entirely in `submit_task()` in `task_runner.py`:

```python
def submit_task(db_path, task_type, job_id=None, params=None):
    task_id, is_new = insert_task(db_path, task_type, job_id or 0, params=params)
    if is_new:
        from scripts.task_scheduler import get_scheduler, LLM_TASK_TYPES
        if task_type in LLM_TASK_TYPES:
            get_scheduler(db_path).enqueue(task_id, task_type, job_id or 0, params)
        else:
            t = threading.Thread(
                target=_run_task,
                args=(db_path, task_id, task_type, job_id or 0, params),
                daemon=True,
            )
            t.start()
    return task_id, is_new
```

`TaskScheduler.enqueue()` only handles LLM task types and never imports or calls `_run_task`. This eliminates any circular import between `task_runner` and `task_scheduler`.

### Component Overview

```
submit_task()
    │
    ├── task_type in LLM_TASK_TYPES?
    │       │ yes                         │ no
    │       ▼                             ▼
    │  get_scheduler().enqueue()    spawn free thread (unchanged)
    │       │
    │       ▼
    │  per-type deque
    │       │
    │       ▼
    │  Scheduler loop (daemon thread)
    │  (wakes on enqueue or batch completion)
    │       │
    │  Sort eligible types by queue depth (desc)
    │       │
    │  For each type:
    │    reserved_vram + budget[type] ≤ available_vram?
    │       │ yes                    │ no
    │       ▼                        ▼
    │  Start batch worker       skip (wait for slot)
    │  (serial: one task at a time)
    │       │
    │  Batch worker signals done → scheduler re-evaluates
```

### New File: `scripts/task_scheduler.py`

**State:**

| Attribute | Type | Purpose |
|---|---|---|
| `_queues` | `dict[str, deque[TaskSpec]]` | Per-type pending task deques |
| `_active` | `dict[str, Thread]` | Currently running batch worker per type |
| `_budgets` | `dict[str, float]` | VRAM budget per task type (GB). Loaded at construction by merging `DEFAULT_VRAM_BUDGETS` with `scheduler.vram_budgets` from `config/llm.yaml`. Config path derived from `db_path` (e.g. `db_path.parent.parent / "config/llm.yaml"`). Missing file or key → defaults used as-is. At construction, a warning is logged for any type in `LLM_TASK_TYPES` with no budget entry after the merge. |
| `_reserved_vram` | `float` | Sum of `_budgets` values for currently active type batches |
| `_available_vram` | `float` | Total VRAM from `get_gpus()` summed across all GPUs at construction; 999.0 on CPU-only systems. Static — not refreshed after startup (see Known Limitations). |
| `_max_queue_depth` | `int` | Max tasks per type queue before drops. From `scheduler.max_queue_depth` in config; default 500. |
| `_lock` | `threading.Lock` | Protects all mutable scheduler state |
| `_wake` | `threading.Event` | Pulsed on enqueue or batch completion |
| `_stop` | `threading.Event` | Set by `shutdown()` to terminate the loop |

**Default VRAM budgets (module-level constant):**

```python
DEFAULT_VRAM_BUDGETS: dict[str, float] = {
    "cover_letter":     2.5,   # alex-cover-writer:latest (~2GB GGUF + headroom)
    "company_research": 5.0,   # llama3.1:8b or vllm model
    "wizard_generate":  2.5,   # same model family as cover_letter
}
```

At construction, the scheduler validates that every type in `LLM_TASK_TYPES` has an entry
in the merged `_budgets`. If any type is missing, a warning is logged:

```
WARNING task_scheduler: No VRAM budget defined for LLM task type 'foo' — defaulting to 0.0 GB (unlimited concurrency for this type)
```

**Scheduler loop:**

```python
while not _stop.is_set():
    _wake.wait(timeout=30)
    _wake.clear()

    with _lock:
        # Defense in depth: reap dead threads not yet cleaned by their finally block.
        # In the normal path, a batch worker's finally block calls _active.pop() and
        # decrements _reserved_vram BEFORE firing _wake — so by the time we scan here,
        # the entry is already gone and there is no double-decrement risk.
        # This reap only catches threads killed externally (daemon exit on shutdown).
        for t, thread in list(_active.items()):
            if not thread.is_alive():
                _reserved_vram -= _budgets.get(t, 0)
                del _active[t]

        # Start new batches where VRAM allows
        candidates = sorted(
            [t for t in _queues if _queues[t] and t not in _active],
            key=lambda t: len(_queues[t]),
            reverse=True,
        )
        for task_type in candidates:
            budget = _budgets.get(task_type, 0)
            if _reserved_vram + budget <= _available_vram:
                thread = Thread(target=_batch_worker, args=(task_type,), daemon=True)
                _active[task_type] = thread
                _reserved_vram += budget
                thread.start()
```

**Batch worker:**

The `finally` block is the single authoritative path for releasing `_reserved_vram` and
removing the entry from `_active`. Because `_active.pop` runs in `finally` before
`_wake.set()`, the scheduler loop's dead-thread scan will never find this entry —
no double-decrement is possible in the normal execution path.

```python
def _batch_worker(task_type: str) -> None:
    try:
        while True:
            with _lock:
                if not _queues[task_type]:
                    break
                task = _queues[task_type].popleft()
            _run_task(db_path, task.id, task_type, task.job_id, task.params)
    finally:
        with _lock:
            _active.pop(task_type, None)
            _reserved_vram -= _budgets.get(task_type, 0)
        _wake.set()
```

`_run_task` here refers to `task_runner._run_task`, passed in as a callable at
construction (e.g. `self._run_task = run_task_fn`). The caller (`task_runner.py`)
passes `_run_task` when constructing the scheduler, avoiding any import of `task_runner`
from within `task_scheduler`.

**`enqueue()` method:**

`enqueue()` only accepts LLM task types. Non-LLM routing is handled in `submit_task()`
before `enqueue()` is called (see Routing section above).

```python
def enqueue(self, task_id: int, task_type: str, job_id: int, params: str | None) -> None:
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

When a task is dropped at the depth limit, `update_task_status()` marks it `failed` in
SQLite immediately — the row inserted by `insert_task()` is never left as a permanent
ghost in `queued` state.

**Singleton access — thread-safe initialization:**

```python
_scheduler: TaskScheduler | None = None
_scheduler_lock = threading.Lock()

def get_scheduler(db_path: Path) -> TaskScheduler:
    global _scheduler
    if _scheduler is None:                  # fast path — avoids lock on steady state
        with _scheduler_lock:
            if _scheduler is None:          # re-check under lock (double-checked locking)
                _scheduler = TaskScheduler(db_path)
                _scheduler.start()
    return _scheduler

def reset_scheduler() -> None:
    """Tear down and clear singleton. Test teardown only."""
    global _scheduler
    with _scheduler_lock:
        if _scheduler:
            _scheduler.shutdown()
            _scheduler = None
```

The safety guarantee comes from the **inner `with _scheduler_lock:` block and re-check**,
not from GIL atomicity. The outer `if _scheduler is None` is a performance optimization
(avoid acquiring the lock on every `submit_task()` call once the scheduler is running).
Two threads racing at startup will both pass the outer check, but only one will win the
inner lock and construct the scheduler; the other will see a non-None value on its
inner re-check and return the already-constructed instance.

---

## Required Call Ordering in `app.py`

`reset_running_tasks()` **must complete before** `get_scheduler()` is ever called.
The scheduler's durability query reads `status='queued'` rows; if `reset_running_tasks()`
has not yet run, a row stuck in `status='running'` from a prior crash would be loaded
into the deque and re-executed, producing a duplicate result.

In practice, the first call to `get_scheduler()` is triggered by the `submit_task()` call
inside `_startup()`'s SearXNG auto-recovery block — not by a user action. The ordering
holds because `reset_running_tasks()` is called on an earlier line within the same
`_startup()` function body. **Do not reorder these calls.**

```python
@st.cache_resource
def _startup() -> None:
    # Step 1: Reset interrupted tasks — MUST come first
    from scripts.db import reset_running_tasks
    reset_running_tasks(get_db_path())

    # Step 2 (later in same function): SearXNG re-queue calls submit_task(),
    # which triggers get_scheduler() for the first time. Ordering is guaranteed
    # because _startup() runs synchronously and step 1 is already complete.
    conn = sqlite3.connect(get_db_path())
    # ... existing SearXNG re-queue logic using conn ...
    conn.close()
```

---

## Changes to Existing Files

### `scripts/task_runner.py`

`submit_task()` gains routing logic; `_run_task` is passed to the scheduler at first call:

```python
def submit_task(db_path, task_type, job_id=None, params=None):
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

`get_scheduler()` accepts `run_task_fn` only on first call (when constructing); subsequent
calls ignore it (singleton already initialized). `_run_task()` and all handler branches
remain unchanged.

### `scripts/db.py`

Add `reset_running_tasks()` alongside the existing `kill_stuck_tasks()`. Like
`kill_stuck_tasks()`, it uses a plain `sqlite3.connect()` — consistent with the
existing pattern in this file, and appropriate because this call happens before the
app's connection pooling is established:

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

### `app/app.py`

Inside `_startup()`, replace the inline SQL block that wipes both `queued` and `running`
rows with a call to `reset_running_tasks()`. The replacement must be the **first operation
in `_startup()`** — before the SearXNG re-queue logic that calls `submit_task()`:

```python
# REMOVE this block:
conn.execute(
    "UPDATE background_tasks SET status='failed', error='Interrupted by server restart',"
    " finished_at=datetime('now') WHERE status IN ('queued','running')"
)

# ADD at the top of _startup(), before any submit_task() calls:
from scripts.db import reset_running_tasks
reset_running_tasks(get_db_path())
```

The existing `conn` used for subsequent SearXNG logic is unaffected — `reset_running_tasks()`
opens and closes its own connection.

### `config/llm.yaml.example`

Add `scheduler:` section:

```yaml
scheduler:
  vram_budgets:
    cover_letter: 2.5       # alex-cover-writer:latest (~2GB GGUF + headroom)
    company_research: 5.0   # llama3.1:8b or vllm model
    wizard_generate: 2.5    # same model family as cover_letter
  max_queue_depth: 500
```

---

## Data Model

No schema changes. The existing `background_tasks` table supports all scheduler needs:

| Column | Scheduler use |
|---|---|
| `task_type` | Queue routing — determines which deque receives the task |
| `status` | `queued` → in deque; `running` → batch worker executing; `completed`/`failed` → done |
| `created_at` | FIFO ordering within type (durability startup query sorts by this) |
| `params` | Passed through to `_run_task()` unchanged |

---

## Durability

Scope: **LLM task types only** (`cover_letter`, `company_research`, `wizard_generate`).
Non-LLM tasks do not survive restarts, same as current behavior.

On construction, `TaskScheduler.__init__()` queries:

```sql
SELECT id, task_type, job_id, params
FROM background_tasks
WHERE status = 'queued'
  AND task_type IN ('cover_letter', 'company_research', 'wizard_generate')
ORDER BY created_at ASC
```

Results are pushed onto their respective deques. This query runs inside `__init__` before
`start()` is called (before the scheduler loop thread exists), so there is no concurrency
concern with deque population.

`running` rows are reset to `failed` by `reset_running_tasks()` before `get_scheduler()`
is called — see Required Call Ordering above.

---

## Known Limitations

**Static `_available_vram`:** Total GPU VRAM is read from `get_gpus()` once at scheduler
construction and never refreshed. Changes after startup — another process releasing VRAM,
a GPU going offline, Ollama unloading a model — are not reflected. The scheduler's
correctness depends on per-task VRAM budgets being conservative estimates of **peak model
footprint** (not free VRAM at a given moment). On a system where Ollama and vLLM share
the GPU, budgets should account for both models potentially resident simultaneously.
Dynamic VRAM polling is a future enhancement.

---

## Memory Safety

- **`finally` block owns VRAM release** — batch worker always decrements `_reserved_vram`
  and removes its `_active` entry before firing `_wake`, even on exception. The scheduler
  loop's dead-thread scan is defense in depth for externally-killed daemons only; it cannot
  double-decrement because `_active.pop` in `finally` runs first.
- **Max queue depth with DB cleanup** — `enqueue()` rejects tasks past `max_queue_depth`,
  logs a warning, and immediately marks the dropped task `failed` in SQLite to prevent
  permanent ghost rows in `queued` state.
- **No in-memory history** — deques hold only pending `TaskSpec` namedtuples. Completed
  and failed state lives exclusively in SQLite. Memory footprint is `O(pending tasks)`.
- **Thread-safe singleton** — double-checked locking with `_scheduler_lock` prevents
  double-construction. Safety comes from the inner lock + re-check; the outer `None`
  check is a performance optimization only.
- **Missing budget warning** — any `LLM_TASK_TYPES` entry with no budget entry after
  config merge logs a warning at construction; defaults to 0.0 GB (unlimited concurrency
  for that type). This prevents silent incorrect scheduling for future task types.
- **`reset_scheduler()`** — explicit teardown for test isolation: sets `_stop`, joins
  scheduler thread with timeout, clears module-level reference under `_scheduler_lock`.

---

## Testing (`tests/test_task_scheduler.py`)

All tests mock `_run_task` to avoid real LLM calls. `reset_scheduler()` is called in
an `autouse` fixture for isolation between test cases.

| Test | What it verifies |
|---|---|
| `test_deepest_queue_wins_first_slot` | N cover_letter + M research enqueued (N > M); cover_letter batch starts first when `_available_vram` only fits one model budget, because it has the deeper queue |
| `test_fifo_within_type` | Arrival order preserved within a type batch |
| `test_concurrent_batches_when_vram_allows` | Two type batches start simultaneously when `_available_vram` fits both budgets combined |
| `test_new_tasks_picked_up_mid_batch` | Task enqueued via `enqueue()` while a batch is active is consumed by the running worker in the same batch |
| `test_worker_crash_releases_vram` | `_run_task` raises; `_reserved_vram` returns to 0; scheduler continues; no double-decrement |
| `test_non_llm_tasks_bypass_scheduler` | `discovery`, `email_sync` etc. spawn free threads via `submit_task()`; scheduler deques untouched |
| `test_durability_llm_tasks_on_startup` | DB has existing `queued` LLM-type rows; scheduler loads them into deques on construction |
| `test_durability_excludes_non_llm` | `queued` non-LLM rows in DB are not loaded into deques on startup |
| `test_running_rows_reset_before_scheduler` | `reset_running_tasks()` sets `running` → `failed`; `queued` rows untouched |
| `test_max_queue_depth_marks_failed` | Enqueue past limit logs warning, does not add to deque, and marks task `failed` in DB |
| `test_missing_budget_logs_warning` | Type in `LLM_TASK_TYPES` with no budget entry at construction logs a warning |
| `test_singleton_thread_safe` | Concurrent calls to `get_scheduler()` produce exactly one scheduler instance |
| `test_reset_scheduler_cleans_up` | `reset_scheduler()` stops loop thread; no lingering threads after call |

---

## Files Touched

| File | Change |
|---|---|
| `scripts/task_scheduler.py` | **New** — ~180 lines |
| `scripts/task_runner.py` | `submit_task()` routing shim — ~12 lines changed |
| `scripts/db.py` | `reset_running_tasks()` added — ~10 lines |
| `app/app.py` | `_startup()`: inline SQL block → `reset_running_tasks()` call, placed first |
| `config/llm.yaml.example` | Add `scheduler:` section |
| `tests/test_task_scheduler.py` | **New** — ~240 lines |
