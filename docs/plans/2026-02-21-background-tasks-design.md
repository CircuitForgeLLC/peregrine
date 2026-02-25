# Background Task Processing — Design

**Date:** 2026-02-21
**Status:** Approved

## Problem

Cover letter generation (`4_Apply.py`) and company research (`6_Interview_Prep.py`) call LLM scripts synchronously inside `st.spinner()`. If the user navigates away during generation, Streamlit abandons the in-progress call and the result is lost. Both results are already persisted to SQLite on completion, so if the task kept running in the background the result would be available on return.

## Solution Overview

Python threading + SQLite task table. When a user clicks Generate, a daemon thread is spawned immediately and the task is recorded in a new `background_tasks` table. The thread writes results to the existing tables (`jobs.cover_letter`, `company_research`) and marks itself complete/failed. All pages share a sidebar indicator that auto-refreshes while tasks are active. Individual pages show task-level status inline.

## SQLite Schema

New table `background_tasks` added in `scripts/db.py`:

```sql
CREATE TABLE IF NOT EXISTS background_tasks (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    task_type   TEXT NOT NULL,   -- "cover_letter" | "company_research"
    job_id      INTEGER NOT NULL,
    status      TEXT NOT NULL DEFAULT 'queued',  -- queued | running | completed | failed
    error       TEXT,
    created_at  DATETIME DEFAULT (datetime('now')),
    started_at  DATETIME,
    finished_at DATETIME
)
```

## Deduplication Rule

Before inserting a new task, check for an existing `queued` or `running` row with the same `(task_type, job_id)`. If one exists, reject the submission (return the existing task's id). Different task types for the same job (e.g. cover letter + research) are allowed to run concurrently. Different jobs of the same type are allowed concurrently.

## Components

### `scripts/task_runner.py` (new)

- `submit_task(db, task_type, job_id) -> int` — dedup check, insert row, spawn daemon thread, return task id
- `_run_task(db, task_id, task_type, job_id)` — thread body: mark running, call generator, save result, mark completed/failed
- `get_active_tasks(db) -> list[dict]` — all queued/running rows with job title+company joined
- `get_task_for_job(db, task_type, job_id) -> dict | None` — latest task row for a specific job+type

### `scripts/db.py` (modified)

- Add `init_background_tasks(conn)` called inside `init_db()`
- Add `insert_task`, `update_task_status`, `get_active_tasks`, `get_task_for_job` helpers

### `app/app.py` (modified)

- After `st.navigation()`, call `get_active_tasks()` and render sidebar indicator
- Use `st.fragment` with `time.sleep(3)` + `st.rerun(scope="fragment")` to poll while tasks are active
- Sidebar shows: `⏳ N task(s) running` count + per-task line (type + company name)
- Fragment polling stops when active task count reaches zero

### `app/pages/4_Apply.py` (modified)

- Generate button calls `submit_task(db, "cover_letter", job_id)` instead of running inline
- If a task is `queued`/`running` for the selected job, disable button and show inline status fragment (polls every 3s)
- On `completed`, load cover letter from `jobs` row (already saved by thread)
- On `failed`, show error message and re-enable button

### `app/pages/6_Interview_Prep.py` (modified)

- Generate/Refresh buttons call `submit_task(db, "company_research", job_id)` instead of running inline
- Same inline status fragment pattern as Apply page

## Data Flow

```
User clicks Generate
    → submit_task(db, type, job_id)
        → dedup check (reject if already queued/running for same type+job)
        → INSERT background_tasks row (status=queued)
        → spawn daemon thread
        → return task_id
    → page shows inline "⏳ Queued…" fragment

Thread runs
    → UPDATE status=running, started_at=now
    → call generate_cover_letter.generate() OR research_company()
    → write result to jobs.cover_letter OR company_research table
    → UPDATE status=completed, finished_at=now
    (on exception: UPDATE status=failed, error=str(e))

Sidebar fragment (every 3s while active tasks > 0)
    → get_active_tasks() → render count + list
    → st.rerun(scope="fragment")

Page fragment (every 3s while task for this job is running)
    → get_task_for_job() → render status
    → on completed: st.rerun() (full rerun to reload cover letter / research)
```

## What Is Not Changed

- `generate_cover_letter.generate()` and `research_company()` are called unchanged from the thread
- `update_cover_letter()` and `save_research()` DB helpers are reused unchanged
- No new Python packages required
- No separate worker process — daemon threads die with the Streamlit server, but results already written to SQLite survive
