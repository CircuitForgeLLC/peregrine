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
    update_task_stage,
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
    # job_id == 0 means a global task (e.g. discovery) with no associated job row.
    job: dict = {}
    if job_id:
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
        if task_type == "discovery":
            from scripts.discover import run_discovery
            new_count = run_discovery(db_path)
            n = new_count or 0
            update_task_status(
                db_path, task_id, "completed",
                error=f"{n} new listing{'s' if n != 1 else ''} added",
            )
            return

        elif task_type == "cover_letter":
            from scripts.generate_cover_letter import generate
            result = generate(
                job.get("title", ""),
                job.get("company", ""),
                job.get("description", ""),
            )
            update_cover_letter(db_path, job_id, result)

        elif task_type == "company_research":
            from scripts.company_research import research_company
            result = research_company(
                job,
                on_stage=lambda s: update_task_stage(db_path, task_id, s),
            )
            save_research(db_path, job_id=job_id, **result)

        elif task_type == "enrich_descriptions":
            from scripts.enrich_descriptions import enrich_all_descriptions
            r = enrich_all_descriptions(db_path)
            errs = len(r.get("errors", []))
            msg = (
                f"{r['succeeded']} description(s) fetched, {r['failed']} failed"
                + (f", {errs} error(s)" if errs else "")
            )
            update_task_status(db_path, task_id, "completed", error=msg)
            return

        elif task_type == "scrape_url":
            from scripts.scrape_url import scrape_job_url
            fields = scrape_job_url(db_path, job_id)
            title = fields.get("title") or job.get("url", "?")
            company = fields.get("company", "")
            msg = f"{title}" + (f" @ {company}" if company else "")
            update_task_status(db_path, task_id, "completed", error=msg)
            # Auto-enrich company/salary for Craigslist jobs
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            job_row = conn.execute(
                "SELECT source, company FROM jobs WHERE id=?", (job_id,)
            ).fetchone()
            conn.close()
            if job_row and job_row["source"] == "craigslist" and not job_row["company"]:
                submit_task(db_path, "enrich_craigslist", job_id)
            return

        elif task_type == "enrich_craigslist":
            from scripts.enrich_descriptions import enrich_craigslist_fields
            extracted = enrich_craigslist_fields(db_path, job_id)
            company = extracted.get("company", "")
            msg = f"company={company}" if company else "no company found"
            update_task_status(db_path, task_id, "completed", error=msg)
            return

        elif task_type == "email_sync":
            try:
                from scripts.imap_sync import sync_all
                result = sync_all(db_path,
                                  on_stage=lambda s: update_task_stage(db_path, task_id, s))
                leads = result.get("new_leads", 0)
                todo  = result.get("todo_attached", 0)
                errs  = len(result.get("errors", []))
                msg = (
                    f"{result['synced']} jobs updated, "
                    f"+{result['inbound']} in, +{result['outbound']} out"
                    + (f", {leads} new lead(s)" if leads else "")
                    + (f", {todo} todo attached" if todo else "")
                    + (f", {errs} error(s)" if errs else "")
                )
                update_task_status(db_path, task_id, "completed", error=msg)
                return
            except FileNotFoundError:
                update_task_status(db_path, task_id, "failed",
                                   error="Email not configured — go to Settings → Email")
                return

        else:
            raise ValueError(f"Unknown task_type: {task_type!r}")

        update_task_status(db_path, task_id, "completed")

    except BaseException as exc:
        # BaseException catches SystemExit (from companyScraper sys.exit calls)
        # in addition to regular exceptions.
        update_task_status(db_path, task_id, "failed", error=str(exc))
