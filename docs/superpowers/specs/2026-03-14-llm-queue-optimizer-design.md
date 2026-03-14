# LLM Queue Optimizer — Design Spec

**Date:** 2026-03-14
**Branch:** `feature/llm-queue-optimizer`
**Closes:** [#2](https://git.opensourcesolarpunk.com/Circuit-Forge/peregrine/issues/2)
**Author:** pyr0ball

---

## Problem

On single-GPU and CPU-only systems, the background task runner spawns a daemon thread for every task immediately on submission. When a user approves N jobs at once, N threads race to load their respective LLM models simultaneously, causing repeated model swaps and significant latency overhead.

The root issue is that `submit_task()` is a spawn-per-task model with no scheduling layer. SQLite's `background_tasks` table is a status log, not a consumed work queue.

Additionally, on restart all `queued` tasks are cleared to `failed`, discarding pending work.

---

## Goals

- Eliminate unnecessary model switching by batching LLM tasks by type
- Allow concurrent model execution when VRAM permits multiple models simultaneously
- Preserve FIFO ordering within each task type
- Survive process restarts — `queued` tasks resume after restart
- Apply to all tiers (no tier gating)
- Keep non-LLM tasks (discovery, email sync, scrape, enrich) unaffected — they continue to spawn free threads

---

## Non-Goals

- Changing the LLM router fallback chain
- Adding new task types
- Tier gating on the scheduler
- Persistent task history in memory

---

## Architecture

### Task Classification

```
LLM_TASK_TYPES = {"cover_letter", "company_research", "wizard_generate"}
```

All other task types (`discovery`, `email_sync`, `scrape_url`, `enrich_descriptions`,
`enrich_craigslist`, `prepare_training`) bypass the scheduler and spawn free threads,
unchanged from the current implementation.

### Component Overview

```
submit_task()  ──→  TaskScheduler.enqueue(task_id, task_type, job_id, params)
                         │
                         ├── LLM task? ──→  per-type deque  ──→  Scheduler loop
                         │                                              │
                         └── Non-LLM task? ──→  spawn thread (unchanged)
                                                                        │
                                          ┌─────────────────────────────┘
                                          ▼
                                   Scheduling cycle
                                   (wakes on enqueue or batch completion)
                                          │
                                   Clean up finished batches, release VRAM
                                          │
                                   Sort eligible types by queue depth (desc)
                                          │
                                   For each type:
                                     reserved_vram + budget[type] ≤ available_vram?
                                          │ yes                    │ no
                                          ▼                        ▼
                                   Start batch worker         skip (wait for slot)
                                   (serial: one task at a time)
                                          │
                                   Batch worker signals done → scheduler re-evaluates
```

### New File: `scripts/task_scheduler.py`

**State:**

| Attribute | Type | Purpose |
|---|---|---|
| `_queues` | `dict[str, deque[TaskSpec]]` | Per-type pending task deques |
| `_active` | `dict[str, Thread]` | Currently running batch worker per type |
| `_reserved_vram` | `float` | Sum of VRAM budgets for active batches |
| `_available_vram` | `float` | Total VRAM from `get_gpus()`; 999.0 on CPU-only |
| `_lock` | `threading.Lock` | Protects all mutable scheduler state |
| `_wake` | `threading.Event` | Pulsed on enqueue or batch completion |
| `_stop` | `threading.Event` | Set by `shutdown()` to terminate the loop |

**Scheduler loop:**

```python
while not _stop.is_set():
    _wake.wait(timeout=30)
    _wake.clear()

    with _lock:
        # Release finished batches
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
            budget = _budgets.get(task_type, DEFAULT_VRAM_BUDGETS.get(task_type, 0))
            if _reserved_vram + budget <= _available_vram:
                thread = Thread(target=_batch_worker, args=(task_type,), daemon=True)
                _active[task_type] = thread
                _reserved_vram += budget
                thread.start()
```

**Batch worker:**

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

Tasks arriving mid-batch for an already-active type are appended to the deque and
picked up naturally by the running batch worker — no re-scheduling needed.

**Singleton access:**

```python
_scheduler: TaskScheduler | None = None

def get_scheduler(db_path: Path) -> TaskScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = TaskScheduler(db_path)
        _scheduler.start()
    return _scheduler

def reset_scheduler() -> None:
    """Tear down and clear singleton. Test teardown only."""
    global _scheduler
    if _scheduler:
        _scheduler.shutdown()
        _scheduler = None
```

### VRAM Budget Configuration

Declared in `config/llm.yaml` under a `scheduler:` key:

```yaml
scheduler:
  vram_budgets:
    cover_letter: 2.5       # alex-cover-writer:latest (~2GB GGUF + headroom)
    company_research: 5.0   # llama3.1:8b or vllm model
    wizard_generate: 2.5    # same model family as cover_letter
  max_queue_depth: 500
```

Defaults (used when key absent — backwards compatible with existing installs):

```python
DEFAULT_VRAM_BUDGETS = {
    "cover_letter":     2.5,
    "company_research": 5.0,
    "wizard_generate":  2.5,
}
```

`_available_vram` is read from `preflight.get_gpus()` at scheduler startup (sum across
all GPUs). CPU-only systems get `_available_vram = 999.0`, allowing all type batches to
run concurrently — preserving existing behavior on CPU installs.

### Memory Safety

- **Batch worker `finally` block** — always releases `_reserved_vram` and fires `_wake`,
  even if `_run_task()` raises. Prevents permanently wedged VRAM reservations.
- **Scheduler loop reaps dead threads** — `thread.is_alive()` check catches any worker
  that exits without firing `_wake` (defense in depth).
- **Max queue depth** — `enqueue()` rejects tasks past `max_queue_depth` with a logged
  warning. Prevents unbounded memory growth under pathological conditions.
- **No in-memory history** — completed/failed state lives exclusively in SQLite. Deques
  hold only pending `TaskSpec` namedtuples. Memory footprint is `O(pending tasks)`.
- **`reset_scheduler()`** — explicit teardown for test isolation. Sets `_stop` event,
  joins the scheduler thread (with timeout), clears the module-level reference.

---

## Changes to Existing Files

### `scripts/task_runner.py`

`submit_task()` becomes a thin shim:

```python
def submit_task(db_path, task_type, job_id=None, params=None):
    task_id, is_new = insert_task(db_path, task_type, job_id or 0, params=params)
    if is_new:
        from scripts.task_scheduler import get_scheduler
        get_scheduler(db_path).enqueue(task_id, task_type, job_id or 0, params)
    return task_id, is_new
```

`_run_task()` and all task handler branches remain unchanged.

### `scripts/db.py`

Add `reset_running_tasks()` helper (alongside existing `kill_stuck_tasks()`):

```python
def reset_running_tasks(db_path: Path = DEFAULT_DB) -> int:
    """On restart: mark in-flight tasks failed. Queued tasks are left for scheduler."""
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

Replace `kill_stuck_tasks()` call with `reset_running_tasks()` on startup:

```python
# Before
kill_stuck_tasks(db_path)

# After — queued tasks survive for the scheduler to resume
reset_running_tasks(db_path)
# Scheduler reads surviving 'queued' rows during get_scheduler() startup
```

### `config/llm.yaml.example`

Add `scheduler:` section documenting VRAM budget keys.

---

## Data Model

No schema changes. The existing `background_tasks` table supports all scheduler needs:

| Column | Scheduler use |
|---|---|
| `task_type` | Queue routing |
| `status` | `queued` → pending; `running` → active; `completed`/`failed` → done |
| `created_at` | FIFO ordering within type |
| `params` | Passed through to `_run_task()` unchanged |

---

## Durability

On startup, `TaskScheduler.__init__()` queries:

```sql
SELECT id, task_type, job_id, params
FROM background_tasks
WHERE status = 'queued'
ORDER BY created_at ASC
```

LLM tasks are pushed onto their respective deques. Non-LLM tasks (which don't survive
restarts under the current model) are re-spawned as free threads.

`running` rows are reset to `failed` by `reset_running_tasks()` before the scheduler
starts — their results are unknown and must be re-submitted by the user.

---

## Testing (`tests/test_task_scheduler.py`)

| Test | What it verifies |
|---|---|
| `test_llm_tasks_batch_by_type` | N cover_letter + M research enqueued; all cover_letters execute before any research when VRAM only fits one model |
| `test_fifo_within_type` | Arrival order preserved within a type batch |
| `test_concurrent_batches_when_vram_allows` | Two type batches start simultaneously when `available_vram` fits both budgets |
| `test_new_tasks_picked_up_mid_batch` | Task enqueued while batch is active is consumed by the running worker |
| `test_worker_crash_releases_vram` | `_run_task` raises; `_reserved_vram` returns to 0; scheduler continues |
| `test_non_llm_tasks_bypass_scheduler` | `discovery`, `email_sync` etc. spawn free threads; scheduler deques untouched |
| `test_durability_on_startup` | DB has existing `queued` rows; scheduler re-enqueues them on init |
| `test_running_rows_reset_on_startup` | `running` rows → `failed` via `reset_running_tasks()`; `queued` rows untouched |
| `test_max_queue_depth` | Enqueue past limit logs warning and does not crash |
| `test_reset_scheduler_cleans_up` | `reset_scheduler()` stops loop thread; no lingering threads |

All tests mock `_run_task` to avoid real LLM calls. `reset_scheduler()` called in
teardown for isolation.

---

## Files Touched

| File | Change |
|---|---|
| `scripts/task_scheduler.py` | **New** — ~160 lines |
| `scripts/task_runner.py` | `submit_task()` shim — ~8 lines changed |
| `scripts/db.py` | `reset_running_tasks()` — ~10 lines added |
| `app/app.py` | Startup: `kill_stuck_tasks` → `reset_running_tasks` |
| `config/llm.yaml.example` | Add `scheduler:` section |
| `tests/test_task_scheduler.py` | **New** — ~200 lines |
