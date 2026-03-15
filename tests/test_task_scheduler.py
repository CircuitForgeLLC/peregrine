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
