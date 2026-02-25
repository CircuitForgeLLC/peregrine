# Background Task Processing Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace synchronous LLM calls in Apply and Interview Prep pages with background threads so cover letter and research generation survive page navigation.

**Architecture:** A new `background_tasks` SQLite table tracks task state. `scripts/task_runner.py` spawns daemon threads that call existing generator functions and write results via existing DB helpers. The Streamlit sidebar polls active tasks every 3s via `@st.fragment(run_every=3)`; individual pages show per-job status with the same pattern.

**Tech Stack:** Python `threading` (stdlib), SQLite, Streamlit `st.fragment` (≥1.33 — already installed)

---

## Task 1: Add background_tasks table and DB helpers

**Files:**
- Modify: `scripts/db.py`
- Test: `tests/test_db.py`

### Step 1: Write the failing tests

Add to `tests/test_db.py`:

```python
# ── background_tasks tests ────────────────────────────────────────────────────

def test_init_db_creates_background_tasks_table(tmp_path):
    """init_db creates a background_tasks table."""
    from scripts.db import init_db
    db_path = tmp_path / "test.db"
    init_db(db_path)
    import sqlite3
    conn = sqlite3.connect(db_path)
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='background_tasks'"
    )
    assert cur.fetchone() is not None
    conn.close()


def test_insert_task_returns_id_and_true(tmp_path):
    """insert_task returns (task_id, True) for a new task."""
    from scripts.db import init_db, insert_job, insert_task
    db_path = tmp_path / "test.db"
    init_db(db_path)
    job_id = insert_job(db_path, {
        "title": "CSM", "company": "Acme", "url": "https://ex.com/1",
        "source": "linkedin", "location": "Remote", "is_remote": True,
        "salary": "", "description": "", "date_found": "2026-02-20",
    })
    task_id, is_new = insert_task(db_path, "cover_letter", job_id)
    assert isinstance(task_id, int) and task_id > 0
    assert is_new is True


def test_insert_task_deduplicates_active_task(tmp_path):
    """insert_task returns (existing_id, False) if a queued/running task already exists."""
    from scripts.db import init_db, insert_job, insert_task
    db_path = tmp_path / "test.db"
    init_db(db_path)
    job_id = insert_job(db_path, {
        "title": "CSM", "company": "Acme", "url": "https://ex.com/1",
        "source": "linkedin", "location": "Remote", "is_remote": True,
        "salary": "", "description": "", "date_found": "2026-02-20",
    })
    first_id, _ = insert_task(db_path, "cover_letter", job_id)
    second_id, is_new = insert_task(db_path, "cover_letter", job_id)
    assert second_id == first_id
    assert is_new is False


def test_insert_task_allows_different_types_same_job(tmp_path):
    """insert_task allows cover_letter and company_research for the same job concurrently."""
    from scripts.db import init_db, insert_job, insert_task
    db_path = tmp_path / "test.db"
    init_db(db_path)
    job_id = insert_job(db_path, {
        "title": "CSM", "company": "Acme", "url": "https://ex.com/1",
        "source": "linkedin", "location": "Remote", "is_remote": True,
        "salary": "", "description": "", "date_found": "2026-02-20",
    })
    _, cl_new = insert_task(db_path, "cover_letter", job_id)
    _, res_new = insert_task(db_path, "company_research", job_id)
    assert cl_new is True
    assert res_new is True


def test_update_task_status_running(tmp_path):
    """update_task_status('running') sets started_at."""
    from scripts.db import init_db, insert_job, insert_task, update_task_status
    import sqlite3
    db_path = tmp_path / "test.db"
    init_db(db_path)
    job_id = insert_job(db_path, {
        "title": "CSM", "company": "Acme", "url": "https://ex.com/1",
        "source": "linkedin", "location": "Remote", "is_remote": True,
        "salary": "", "description": "", "date_found": "2026-02-20",
    })
    task_id, _ = insert_task(db_path, "cover_letter", job_id)
    update_task_status(db_path, task_id, "running")
    conn = sqlite3.connect(db_path)
    row = conn.execute("SELECT status, started_at FROM background_tasks WHERE id=?", (task_id,)).fetchone()
    conn.close()
    assert row[0] == "running"
    assert row[1] is not None


def test_update_task_status_completed(tmp_path):
    """update_task_status('completed') sets finished_at."""
    from scripts.db import init_db, insert_job, insert_task, update_task_status
    import sqlite3
    db_path = tmp_path / "test.db"
    init_db(db_path)
    job_id = insert_job(db_path, {
        "title": "CSM", "company": "Acme", "url": "https://ex.com/1",
        "source": "linkedin", "location": "Remote", "is_remote": True,
        "salary": "", "description": "", "date_found": "2026-02-20",
    })
    task_id, _ = insert_task(db_path, "cover_letter", job_id)
    update_task_status(db_path, task_id, "completed")
    conn = sqlite3.connect(db_path)
    row = conn.execute("SELECT status, finished_at FROM background_tasks WHERE id=?", (task_id,)).fetchone()
    conn.close()
    assert row[0] == "completed"
    assert row[1] is not None


def test_update_task_status_failed_stores_error(tmp_path):
    """update_task_status('failed') stores error message and sets finished_at."""
    from scripts.db import init_db, insert_job, insert_task, update_task_status
    import sqlite3
    db_path = tmp_path / "test.db"
    init_db(db_path)
    job_id = insert_job(db_path, {
        "title": "CSM", "company": "Acme", "url": "https://ex.com/1",
        "source": "linkedin", "location": "Remote", "is_remote": True,
        "salary": "", "description": "", "date_found": "2026-02-20",
    })
    task_id, _ = insert_task(db_path, "cover_letter", job_id)
    update_task_status(db_path, task_id, "failed", error="LLM timeout")
    conn = sqlite3.connect(db_path)
    row = conn.execute("SELECT status, error, finished_at FROM background_tasks WHERE id=?", (task_id,)).fetchone()
    conn.close()
    assert row[0] == "failed"
    assert row[1] == "LLM timeout"
    assert row[2] is not None


def test_get_active_tasks_returns_only_active(tmp_path):
    """get_active_tasks returns only queued/running tasks with job info joined."""
    from scripts.db import init_db, insert_job, insert_task, update_task_status, get_active_tasks
    db_path = tmp_path / "test.db"
    init_db(db_path)
    job_id = insert_job(db_path, {
        "title": "CSM", "company": "Acme", "url": "https://ex.com/1",
        "source": "linkedin", "location": "Remote", "is_remote": True,
        "salary": "", "description": "", "date_found": "2026-02-20",
    })
    active_id, _ = insert_task(db_path, "cover_letter", job_id)
    done_id, _ = insert_task(db_path, "company_research", job_id)
    update_task_status(db_path, done_id, "completed")

    tasks = get_active_tasks(db_path)
    assert len(tasks) == 1
    assert tasks[0]["id"] == active_id
    assert tasks[0]["company"] == "Acme"
    assert tasks[0]["title"] == "CSM"


def test_get_task_for_job_returns_latest(tmp_path):
    """get_task_for_job returns the most recent task for the given type+job."""
    from scripts.db import init_db, insert_job, insert_task, update_task_status, get_task_for_job
    db_path = tmp_path / "test.db"
    init_db(db_path)
    job_id = insert_job(db_path, {
        "title": "CSM", "company": "Acme", "url": "https://ex.com/1",
        "source": "linkedin", "location": "Remote", "is_remote": True,
        "salary": "", "description": "", "date_found": "2026-02-20",
    })
    first_id, _ = insert_task(db_path, "cover_letter", job_id)
    update_task_status(db_path, first_id, "completed")
    second_id, _ = insert_task(db_path, "cover_letter", job_id)  # allowed since first is done

    task = get_task_for_job(db_path, "cover_letter", job_id)
    assert task is not None
    assert task["id"] == second_id


def test_get_task_for_job_returns_none_when_absent(tmp_path):
    """get_task_for_job returns None when no task exists for that job+type."""
    from scripts.db import init_db, insert_job, get_task_for_job
    db_path = tmp_path / "test.db"
    init_db(db_path)
    job_id = insert_job(db_path, {
        "title": "CSM", "company": "Acme", "url": "https://ex.com/1",
        "source": "linkedin", "location": "Remote", "is_remote": True,
        "salary": "", "description": "", "date_found": "2026-02-20",
    })
    assert get_task_for_job(db_path, "cover_letter", job_id) is None
```

### Step 2: Run tests to verify they fail

```bash
/devl/miniconda3/envs/job-seeker/bin/pytest tests/test_db.py -v -k "background_tasks or insert_task or update_task_status or get_active_tasks or get_task_for_job"
```

Expected: FAIL with `ImportError: cannot import name 'insert_task'`

### Step 3: Implement in scripts/db.py

Add the DDL constant after `CREATE_COMPANY_RESEARCH`:

```python
CREATE_BACKGROUND_TASKS = """
CREATE TABLE IF NOT EXISTS background_tasks (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    task_type   TEXT NOT NULL,
    job_id      INTEGER NOT NULL,
    status      TEXT NOT NULL DEFAULT 'queued',
    error       TEXT,
    created_at  DATETIME DEFAULT (datetime('now')),
    started_at  DATETIME,
    finished_at DATETIME
)
"""
```

Add `conn.execute(CREATE_BACKGROUND_TASKS)` inside `init_db()`, after the existing three `conn.execute()` calls:

```python
def init_db(db_path: Path = DEFAULT_DB) -> None:
    """Create tables if they don't exist, then run migrations."""
    conn = sqlite3.connect(db_path)
    conn.execute(CREATE_JOBS)
    conn.execute(CREATE_JOB_CONTACTS)
    conn.execute(CREATE_COMPANY_RESEARCH)
    conn.execute(CREATE_BACKGROUND_TASKS)   # ← add this line
    conn.commit()
    conn.close()
    _migrate_db(db_path)
```

Add the four helper functions at the end of `scripts/db.py`:

```python
# ── Background task helpers ───────────────────────────────────────────────────

def insert_task(db_path: Path = DEFAULT_DB, task_type: str = "",
                job_id: int = None) -> tuple[int, bool]:
    """Insert a new background task.

    Returns (task_id, True) if inserted, or (existing_id, False) if a
    queued/running task for the same (task_type, job_id) already exists.
    """
    conn = sqlite3.connect(db_path)
    existing = conn.execute(
        "SELECT id FROM background_tasks WHERE task_type=? AND job_id=? AND status IN ('queued','running')",
        (task_type, job_id),
    ).fetchone()
    if existing:
        conn.close()
        return existing[0], False
    cur = conn.execute(
        "INSERT INTO background_tasks (task_type, job_id, status) VALUES (?, ?, 'queued')",
        (task_type, job_id),
    )
    task_id = cur.lastrowid
    conn.commit()
    conn.close()
    return task_id, True


def update_task_status(db_path: Path = DEFAULT_DB, task_id: int = None,
                       status: str = "", error: Optional[str] = None) -> None:
    """Update a task's status and set the appropriate timestamp."""
    now = datetime.now().isoformat()[:16]
    conn = sqlite3.connect(db_path)
    if status == "running":
        conn.execute(
            "UPDATE background_tasks SET status=?, started_at=? WHERE id=?",
            (status, now, task_id),
        )
    elif status in ("completed", "failed"):
        conn.execute(
            "UPDATE background_tasks SET status=?, finished_at=?, error=? WHERE id=?",
            (status, now, error, task_id),
        )
    else:
        conn.execute("UPDATE background_tasks SET status=? WHERE id=?", (status, task_id))
    conn.commit()
    conn.close()


def get_active_tasks(db_path: Path = DEFAULT_DB) -> list[dict]:
    """Return all queued/running tasks with job title and company joined in."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("""
        SELECT bt.*, j.title, j.company
        FROM background_tasks bt
        LEFT JOIN jobs j ON j.id = bt.job_id
        WHERE bt.status IN ('queued', 'running')
        ORDER BY bt.created_at ASC
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_task_for_job(db_path: Path = DEFAULT_DB, task_type: str = "",
                     job_id: int = None) -> Optional[dict]:
    """Return the most recent task row for a (task_type, job_id) pair, or None."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        """SELECT * FROM background_tasks
           WHERE task_type=? AND job_id=?
           ORDER BY id DESC LIMIT 1""",
        (task_type, job_id),
    ).fetchone()
    conn.close()
    return dict(row) if row else None
```

### Step 4: Run tests to verify they pass

```bash
/devl/miniconda3/envs/job-seeker/bin/pytest tests/test_db.py -v -k "background_tasks or insert_task or update_task_status or get_active_tasks or get_task_for_job"
```

Expected: all new tests PASS, no regressions

### Step 5: Run full test suite

```bash
/devl/miniconda3/envs/job-seeker/bin/pytest tests/ -v
```

Expected: all tests PASS

### Step 6: Commit

```bash
git add scripts/db.py tests/test_db.py
git commit -m "feat: add background_tasks table and DB helpers"
```

---

## Task 2: Create scripts/task_runner.py

**Files:**
- Create: `scripts/task_runner.py`
- Test: `tests/test_task_runner.py`

### Step 1: Write the failing tests

Create `tests/test_task_runner.py`:

```python
import threading
import time
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
import sqlite3


def _make_db(tmp_path):
    from scripts.db import init_db, insert_job
    db = tmp_path / "test.db"
    init_db(db)
    job_id = insert_job(db, {
        "title": "CSM", "company": "Acme", "url": "https://ex.com/1",
        "source": "linkedin", "location": "Remote", "is_remote": True,
        "salary": "", "description": "Great role.", "date_found": "2026-02-20",
    })
    return db, job_id


def test_submit_task_returns_id_and_true(tmp_path):
    """submit_task returns (task_id, True) and spawns a thread."""
    db, job_id = _make_db(tmp_path)
    with patch("scripts.task_runner._run_task"):  # don't actually call LLM
        from scripts.task_runner import submit_task
        task_id, is_new = submit_task(db, "cover_letter", job_id)
    assert isinstance(task_id, int) and task_id > 0
    assert is_new is True


def test_submit_task_deduplicates(tmp_path):
    """submit_task returns (existing_id, False) for a duplicate in-flight task."""
    db, job_id = _make_db(tmp_path)
    with patch("scripts.task_runner._run_task"):
        from scripts.task_runner import submit_task
        first_id, _ = submit_task(db, "cover_letter", job_id)
        second_id, is_new = submit_task(db, "cover_letter", job_id)
    assert second_id == first_id
    assert is_new is False


def test_run_task_cover_letter_success(tmp_path):
    """_run_task marks running→completed and saves cover letter to DB."""
    db, job_id = _make_db(tmp_path)
    from scripts.db import insert_task, get_task_for_job, get_jobs_by_status
    task_id, _ = insert_task(db, "cover_letter", job_id)

    with patch("scripts.generate_cover_letter.generate", return_value="Dear Hiring Manager,\nGreat fit!"):
        from scripts.task_runner import _run_task
        _run_task(db, task_id, "cover_letter", job_id)

    task = get_task_for_job(db, "cover_letter", job_id)
    assert task["status"] == "completed"
    assert task["error"] is None

    conn = sqlite3.connect(db)
    row = conn.execute("SELECT cover_letter FROM jobs WHERE id=?", (job_id,)).fetchone()
    conn.close()
    assert row[0] == "Dear Hiring Manager,\nGreat fit!"


def test_run_task_company_research_success(tmp_path):
    """_run_task marks running→completed and saves research to DB."""
    db, job_id = _make_db(tmp_path)
    from scripts.db import insert_task, get_task_for_job, get_research

    task_id, _ = insert_task(db, "company_research", job_id)
    fake_result = {
        "raw_output": "raw", "company_brief": "brief",
        "ceo_brief": "ceo", "talking_points": "points",
    }
    with patch("scripts.company_research.research_company", return_value=fake_result):
        from scripts.task_runner import _run_task
        _run_task(db, task_id, "company_research", job_id)

    task = get_task_for_job(db, "company_research", job_id)
    assert task["status"] == "completed"

    research = get_research(db, job_id=job_id)
    assert research["company_brief"] == "brief"


def test_run_task_marks_failed_on_exception(tmp_path):
    """_run_task marks status=failed and stores error when generator raises."""
    db, job_id = _make_db(tmp_path)
    from scripts.db import insert_task, get_task_for_job
    task_id, _ = insert_task(db, "cover_letter", job_id)

    with patch("scripts.generate_cover_letter.generate", side_effect=RuntimeError("LLM timeout")):
        from scripts.task_runner import _run_task
        _run_task(db, task_id, "cover_letter", job_id)

    task = get_task_for_job(db, "cover_letter", job_id)
    assert task["status"] == "failed"
    assert "LLM timeout" in task["error"]


def test_submit_task_actually_completes(tmp_path):
    """Integration: submit_task spawns a thread that completes asynchronously."""
    db, job_id = _make_db(tmp_path)
    from scripts.db import get_task_for_job

    with patch("scripts.generate_cover_letter.generate", return_value="Cover letter text"):
        from scripts.task_runner import submit_task
        task_id, _ = submit_task(db, "cover_letter", job_id)
        # Wait for thread to complete (max 5s)
        for _ in range(50):
            task = get_task_for_job(db, "cover_letter", job_id)
            if task and task["status"] in ("completed", "failed"):
                break
            time.sleep(0.1)

    task = get_task_for_job(db, "cover_letter", job_id)
    assert task["status"] == "completed"
```

### Step 2: Run tests to verify they fail

```bash
/devl/miniconda3/envs/job-seeker/bin/pytest tests/test_task_runner.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'scripts.task_runner'`

### Step 3: Implement scripts/task_runner.py

Create `scripts/task_runner.py`:

```python
# scripts/task_runner.py
"""
Background task runner for LLM generation tasks.

Submitting a task inserts a row in background_tasks and spawns a daemon thread.
The thread calls the appropriate generator, writes results to existing tables,
and marks the task completed or failed.

Deduplication: only one queued/running task per (task_type, job_id) is allowed.
Different task types for the same job run concurrently (e.g. cover letter + research).
"""
import sqlite3
import threading
from pathlib import Path

from scripts.db import (
    DEFAULT_DB,
    insert_task,
    update_task_status,
    update_cover_letter,
    save_research,
)


def submit_task(db_path: Path = DEFAULT_DB, task_type: str = "",
                job_id: int = None) -> tuple[int, bool]:
    """Submit a background LLM task.

    Returns (task_id, True) if a new task was queued and a thread spawned.
    Returns (existing_id, False) if an identical task is already in-flight.
    """
    task_id, is_new = insert_task(db_path, task_type, job_id)
    if is_new:
        t = threading.Thread(
            target=_run_task,
            args=(db_path, task_id, task_type, job_id),
            daemon=True,
        )
        t.start()
    return task_id, is_new


def _run_task(db_path: Path, task_id: int, task_type: str, job_id: int) -> None:
    """Thread body: run the generator and persist the result."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
    conn.close()
    if row is None:
        update_task_status(db_path, task_id, "failed", error=f"Job {job_id} not found")
        return

    job = dict(row)
    update_task_status(db_path, task_id, "running")

    try:
        if task_type == "cover_letter":
            from scripts.generate_cover_letter import generate
            result = generate(
                job.get("title", ""),
                job.get("company", ""),
                job.get("description", ""),
            )
            update_cover_letter(db_path, job_id, result)

        elif task_type == "company_research":
            from scripts.company_research import research_company
            result = research_company(job)
            save_research(db_path, job_id=job_id, **result)

        else:
            raise ValueError(f"Unknown task_type: {task_type!r}")

        update_task_status(db_path, task_id, "completed")

    except Exception as exc:
        update_task_status(db_path, task_id, "failed", error=str(exc))
```

### Step 4: Run tests to verify they pass

```bash
/devl/miniconda3/envs/job-seeker/bin/pytest tests/test_task_runner.py -v
```

Expected: all tests PASS

### Step 5: Run full test suite

```bash
/devl/miniconda3/envs/job-seeker/bin/pytest tests/ -v
```

Expected: all tests PASS

### Step 6: Commit

```bash
git add scripts/task_runner.py tests/test_task_runner.py
git commit -m "feat: add task_runner — background thread executor for LLM tasks"
```

---

## Task 3: Add sidebar task indicator to app/app.py

**Files:**
- Modify: `app/app.py`

No new tests needed — this is pure UI wiring.

### Step 1: Replace the contents of app/app.py

Current file is 33 lines. Replace entirely with:

```python
# app/app.py
"""
Streamlit entry point — uses st.navigation() to control the sidebar.
Main workflow pages are listed at the top; Settings is separated into
a "System" section so it doesn't crowd the navigation.

Run: streamlit run app/app.py
     bash scripts/manage-ui.sh start
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st
from scripts.db import DEFAULT_DB, init_db, get_active_tasks

st.set_page_config(
    page_title="Job Seeker",
    page_icon="💼",
    layout="wide",
)

init_db(DEFAULT_DB)

# ── Background task sidebar indicator ─────────────────────────────────────────
@st.fragment(run_every=3)
def _task_sidebar() -> None:
    tasks = get_active_tasks(DEFAULT_DB)
    if not tasks:
        return
    with st.sidebar:
        st.divider()
        st.markdown(f"**⏳ {len(tasks)} task(s) running**")
        for t in tasks:
            icon = "⏳" if t["status"] == "running" else "🕐"
            label = "Cover letter" if t["task_type"] == "cover_letter" else "Research"
            st.caption(f"{icon} {label} — {t.get('company') or 'unknown'}")

_task_sidebar()

# ── Navigation ─────────────────────────────────────────────────────────────────
pages = {
    "": [
        st.Page("Home.py",                   title="Home",            icon="🏠"),
        st.Page("pages/1_Job_Review.py",     title="Job Review",      icon="📋"),
        st.Page("pages/4_Apply.py",          title="Apply Workspace", icon="🚀"),
        st.Page("pages/5_Interviews.py",     title="Interviews",      icon="🎯"),
        st.Page("pages/6_Interview_Prep.py", title="Interview Prep",  icon="📞"),
    ],
    "System": [
        st.Page("pages/2_Settings.py",       title="Settings",        icon="⚙️"),
    ],
}

pg = st.navigation(pages)
pg.run()
```

### Step 2: Smoke-test by running the UI

```bash
bash /devl/job-seeker/scripts/manage-ui.sh restart
```

Navigate to http://localhost:8501 and confirm the app loads without error. The sidebar task indicator does not appear when no tasks are running (correct).

### Step 3: Commit

```bash
git add app/app.py
git commit -m "feat: sidebar background task indicator with 3s auto-refresh"
```

---

## Task 4: Update 4_Apply.py to use background generation

**Files:**
- Modify: `app/pages/4_Apply.py`

No new unit tests — covered by existing test suite for DB layer. Smoke-test in browser.

### Step 1: Add imports at the top of 4_Apply.py

After the existing imports block (after `from scripts.db import ...`), add:

```python
from scripts.db import get_task_for_job
from scripts.task_runner import submit_task
```

So the full import block becomes:

```python
from scripts.db import (
    DEFAULT_DB, init_db, get_jobs_by_status,
    update_cover_letter, mark_applied,
    get_task_for_job,
)
from scripts.task_runner import submit_task
```

### Step 2: Replace the Generate button section

Find this block (around line 174–185):

```python
    if st.button("✨ Generate / Regenerate", use_container_width=True):
        with st.spinner("Generating via LLM…"):
            try:
                from scripts.generate_cover_letter import generate as _gen
                st.session_state[_cl_key] = _gen(
                    job.get("title", ""),
                    job.get("company", ""),
                    job.get("description", ""),
                )
                st.rerun()
            except Exception as e:
                st.error(f"Generation failed: {e}")
```

Replace with:

```python
    _cl_task = get_task_for_job(DEFAULT_DB, "cover_letter", selected_id)
    _cl_running = _cl_task and _cl_task["status"] in ("queued", "running")

    if st.button("✨ Generate / Regenerate", use_container_width=True, disabled=bool(_cl_running)):
        submit_task(DEFAULT_DB, "cover_letter", selected_id)
        st.rerun()

    if _cl_running:
        @st.fragment(run_every=3)
        def _cl_status_fragment():
            t = get_task_for_job(DEFAULT_DB, "cover_letter", selected_id)
            if t and t["status"] in ("queued", "running"):
                lbl = "Queued…" if t["status"] == "queued" else "Generating via LLM…"
                st.info(f"⏳ {lbl}")
            else:
                st.rerun()  # full page rerun — reloads cover letter from DB
        _cl_status_fragment()
    elif _cl_task and _cl_task["status"] == "failed":
        st.error(f"Generation failed: {_cl_task.get('error', 'unknown error')}")
```

Also update the session-state initialiser just below (line 171–172) so it loads from DB after background completion. The existing code already does this correctly:

```python
    if _cl_key not in st.session_state:
        st.session_state[_cl_key] = job.get("cover_letter") or ""
```

This is fine — `job` is fetched fresh on each full-page rerun, so when the background thread writes to `jobs.cover_letter`, the next full rerun picks it up.

### Step 3: Smoke-test in browser

1. Navigate to Apply Workspace
2. Select an approved job
3. Click "Generate / Regenerate"
4. Navigate away to Home
5. Navigate back to Apply Workspace for the same job
6. Observe: button is disabled and "⏳ Generating via LLM…" shows while running; cover letter appears when done

### Step 4: Commit

```bash
git add app/pages/4_Apply.py
git commit -m "feat: cover letter generation runs in background, survives navigation"
```

---

## Task 5: Update 6_Interview_Prep.py to use background research

**Files:**
- Modify: `app/pages/6_Interview_Prep.py`

### Step 1: Add imports at the top of 6_Interview_Prep.py

After the existing `from scripts.db import (...)` block, add:

```python
from scripts.db import get_task_for_job
from scripts.task_runner import submit_task
```

So the full import block becomes:

```python
from scripts.db import (
    DEFAULT_DB, init_db,
    get_interview_jobs, get_contacts, get_research,
    save_research, get_task_for_job,
)
from scripts.task_runner import submit_task
```

### Step 2: Replace the "no research yet" generate button block

Find this block (around line 99–111):

```python
    if not research:
        st.warning("No research brief yet for this job.")
        if st.button("🔬 Generate research brief", type="primary", use_container_width=True):
            with st.spinner("Generating… this may take 30–60 seconds"):
                try:
                    from scripts.company_research import research_company
                    result = research_company(job)
                    save_research(DEFAULT_DB, job_id=selected_id, **result)
                    st.success("Done!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error: {e}")
        st.stop()
    else:
```

Replace with:

```python
    _res_task = get_task_for_job(DEFAULT_DB, "company_research", selected_id)
    _res_running = _res_task and _res_task["status"] in ("queued", "running")

    if not research:
        if not _res_running:
            st.warning("No research brief yet for this job.")
            if _res_task and _res_task["status"] == "failed":
                st.error(f"Last attempt failed: {_res_task.get('error', '')}")
            if st.button("🔬 Generate research brief", type="primary", use_container_width=True):
                submit_task(DEFAULT_DB, "company_research", selected_id)
                st.rerun()

        if _res_running:
            @st.fragment(run_every=3)
            def _res_status_initial():
                t = get_task_for_job(DEFAULT_DB, "company_research", selected_id)
                if t and t["status"] in ("queued", "running"):
                    lbl = "Queued…" if t["status"] == "queued" else "Generating… this may take 30–60 seconds"
                    st.info(f"⏳ {lbl}")
                else:
                    st.rerun()
            _res_status_initial()

        st.stop()
    else:
```

### Step 3: Replace the "refresh" button block

Find this block (around line 113–124):

```python
        generated_at = research.get("generated_at", "")
        col_ts, col_btn = st.columns([3, 1])
        col_ts.caption(f"Research generated: {generated_at}")
        if col_btn.button("🔄 Refresh", use_container_width=True):
            with st.spinner("Refreshing…"):
                try:
                    from scripts.company_research import research_company
                    result = research_company(job)
                    save_research(DEFAULT_DB, job_id=selected_id, **result)
                    st.rerun()
                except Exception as e:
                    st.error(f"Error: {e}")
```

Replace with:

```python
        generated_at = research.get("generated_at", "")
        col_ts, col_btn = st.columns([3, 1])
        col_ts.caption(f"Research generated: {generated_at}")
        if col_btn.button("🔄 Refresh", use_container_width=True, disabled=bool(_res_running)):
            submit_task(DEFAULT_DB, "company_research", selected_id)
            st.rerun()

        if _res_running:
            @st.fragment(run_every=3)
            def _res_status_refresh():
                t = get_task_for_job(DEFAULT_DB, "company_research", selected_id)
                if t and t["status"] in ("queued", "running"):
                    lbl = "Queued…" if t["status"] == "queued" else "Refreshing research…"
                    st.info(f"⏳ {lbl}")
                else:
                    st.rerun()
            _res_status_refresh()
        elif _res_task and _res_task["status"] == "failed":
            st.error(f"Refresh failed: {_res_task.get('error', '')}")
```

### Step 4: Smoke-test in browser

1. Move a job to Phone Screen on the Interviews page
2. Navigate to Interview Prep, select that job
3. Click "Generate research brief"
4. Navigate away to Home
5. Navigate back — observe "⏳ Generating…" inline indicator
6. Wait for completion — research sections populate automatically

### Step 5: Run full test suite one final time

```bash
/devl/miniconda3/envs/job-seeker/bin/pytest tests/ -v
```

Expected: all tests PASS

### Step 6: Commit

```bash
git add app/pages/6_Interview_Prep.py
git commit -m "feat: company research generation runs in background, survives navigation"
```

---

## Summary of Changes

| File | Change |
|------|--------|
| `scripts/db.py` | Add `CREATE_BACKGROUND_TASKS`, `init_db` call, 4 new helpers |
| `scripts/task_runner.py` | New file — `submit_task` + `_run_task` thread body |
| `app/app.py` | Add `_task_sidebar` fragment with 3s auto-refresh |
| `app/pages/4_Apply.py` | Generate button → `submit_task`; inline status fragment |
| `app/pages/6_Interview_Prep.py` | Generate/Refresh buttons → `submit_task`; inline status fragments |
| `tests/test_db.py` | 9 new tests for background_tasks helpers |
| `tests/test_task_runner.py` | New file — 6 tests for task_runner |
