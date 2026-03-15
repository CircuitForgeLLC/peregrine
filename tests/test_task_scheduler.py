# tests/test_task_scheduler.py
"""Tests for scripts/task_scheduler.py and related db helpers."""
import sqlite3
import threading
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
    try:
        reset_scheduler()
    except NotImplementedError:
        pass


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
