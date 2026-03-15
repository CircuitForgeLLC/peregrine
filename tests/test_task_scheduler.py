# tests/test_task_scheduler.py
"""Tests for scripts/task_scheduler.py and related db helpers."""
import sqlite3
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
