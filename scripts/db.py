"""
SQLite staging layer for job listings.
Jobs flow: pending → approved/rejected → applied → synced
          applied → phone_screen → interviewing → offer → hired (or rejected)
"""
import os
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

from circuitforge_core.db import get_connection as _cf_get_connection

DEFAULT_DB = Path(os.environ.get("STAGING_DB", Path(__file__).parent.parent / "staging.db"))


def get_connection(db_path: Path = DEFAULT_DB, key: str = "") -> "sqlite3.Connection":
    """Thin shim — delegates to circuitforge_core.db.get_connection."""
    return _cf_get_connection(db_path, key)


CREATE_JOBS = """
CREATE TABLE IF NOT EXISTS jobs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    title           TEXT,
    company         TEXT,
    url             TEXT UNIQUE,
    source          TEXT,
    location        TEXT,
    is_remote       INTEGER DEFAULT 0,
    salary          TEXT,
    description     TEXT,
    match_score     REAL,
    keyword_gaps    TEXT,
    date_found      TEXT,
    status          TEXT DEFAULT 'pending',
    notion_page_id  TEXT,
    cover_letter    TEXT,
    applied_at      TEXT
);
"""

CREATE_JOB_CONTACTS = """
CREATE TABLE IF NOT EXISTS job_contacts (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id             INTEGER NOT NULL,
    direction          TEXT DEFAULT 'inbound',
    subject            TEXT,
    from_addr          TEXT,
    to_addr            TEXT,
    body               TEXT,
    received_at        TEXT,
    is_response_needed INTEGER DEFAULT 0,
    responded_at       TEXT,
    message_id         TEXT,
    FOREIGN KEY (job_id) REFERENCES jobs(id)
);
"""

_CONTACT_MIGRATIONS = [
    ("message_id",           "TEXT"),
    ("stage_signal",         "TEXT"),
    ("suggestion_dismissed", "INTEGER DEFAULT 0"),
]

_RESEARCH_MIGRATIONS = [
    ("tech_brief",          "TEXT"),
    ("funding_brief",       "TEXT"),
    ("competitors_brief",   "TEXT"),
    ("red_flags",           "TEXT"),
    ("scrape_used",         "INTEGER"),  # 1 = SearXNG contributed data, 0 = LLM-only
    ("accessibility_brief", "TEXT"),     # Inclusion & Accessibility section
]

CREATE_COMPANY_RESEARCH = """
CREATE TABLE IF NOT EXISTS company_research (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id           INTEGER NOT NULL UNIQUE,
    generated_at     TEXT,
    company_brief    TEXT,
    ceo_brief        TEXT,
    talking_points   TEXT,
    raw_output       TEXT,
    tech_brief       TEXT,
    funding_brief    TEXT,
    competitors_brief TEXT,
    red_flags        TEXT,
    FOREIGN KEY (job_id) REFERENCES jobs(id)
);
"""

CREATE_BACKGROUND_TASKS = """
CREATE TABLE IF NOT EXISTS background_tasks (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    task_type   TEXT NOT NULL,
    job_id      INTEGER DEFAULT 0,
    params      TEXT,
    status      TEXT NOT NULL DEFAULT 'queued',
    error       TEXT,
    created_at  DATETIME DEFAULT (datetime('now')),
    started_at  DATETIME,
    finished_at DATETIME,
    stage       TEXT,
    updated_at  DATETIME
)
"""

CREATE_SURVEY_RESPONSES = """
CREATE TABLE IF NOT EXISTS survey_responses (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id         INTEGER NOT NULL REFERENCES jobs(id),
    survey_name    TEXT,
    received_at    DATETIME,
    source         TEXT,
    raw_input      TEXT,
    image_path     TEXT,
    mode           TEXT,
    llm_output     TEXT,
    reported_score TEXT,
    created_at     DATETIME DEFAULT CURRENT_TIMESTAMP
);
"""

CREATE_DIGEST_QUEUE = """
CREATE TABLE IF NOT EXISTS digest_queue (
    id             INTEGER PRIMARY KEY,
    job_contact_id INTEGER NOT NULL REFERENCES job_contacts(id),
    created_at     TEXT DEFAULT (datetime('now')),
    UNIQUE(job_contact_id)
)
"""

CREATE_REFERENCES = """
CREATE TABLE IF NOT EXISTS references_ (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    name         TEXT NOT NULL,
    relationship TEXT,
    company      TEXT,
    email        TEXT,
    phone        TEXT,
    notes        TEXT,
    tags         TEXT DEFAULT '[]',
    created_at   TEXT DEFAULT (datetime('now')),
    updated_at   TEXT DEFAULT (datetime('now'))
);
"""

CREATE_JOB_REFERENCES = """
CREATE TABLE IF NOT EXISTS job_references (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id       INTEGER NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    reference_id INTEGER NOT NULL REFERENCES references_(id) ON DELETE CASCADE,
    prep_email   TEXT,
    rec_letter   TEXT,
    UNIQUE(job_id, reference_id)
);
"""

_MIGRATIONS = [
    ("cover_letter",       "TEXT"),
    ("applied_at",         "TEXT"),
    ("interview_date",     "TEXT"),
    ("rejection_stage",    "TEXT"),
    ("phone_screen_at",    "TEXT"),
    ("interviewing_at",    "TEXT"),
    ("offer_at",           "TEXT"),
    ("hired_at",           "TEXT"),
    ("survey_at",          "TEXT"),
    ("calendar_event_id",  "TEXT"),
    ("optimized_resume",   "TEXT"),   # ATS-rewritten resume text (paid tier)
    ("ats_gap_report",     "TEXT"),   # JSON gap report (free tier)
    ("date_posted",        "TEXT"),   # Original posting date from job board (shadow listing detection)
    ("hired_feedback",           "TEXT"),   # JSON: optional post-hire "what helped" response
    ("excluded_from_training", "INTEGER DEFAULT 0"),  # opt-out of training export
]


def _migrate_db(db_path: Path) -> None:
    """Add new columns to existing tables without breaking old data."""
    conn = sqlite3.connect(db_path)
    for col, coltype in _MIGRATIONS:
        try:
            conn.execute(f"ALTER TABLE jobs ADD COLUMN {col} {coltype}")
        except sqlite3.OperationalError:
            pass  # column already exists
    for col, coltype in _CONTACT_MIGRATIONS:
        try:
            conn.execute(f"ALTER TABLE job_contacts ADD COLUMN {col} {coltype}")
        except sqlite3.OperationalError:
            pass
    for col, coltype in _RESEARCH_MIGRATIONS:
        try:
            conn.execute(f"ALTER TABLE company_research ADD COLUMN {col} {coltype}")
        except sqlite3.OperationalError:
            pass
    try:
        conn.execute("ALTER TABLE background_tasks ADD COLUMN stage TEXT")
    except sqlite3.OperationalError:
        pass
    try:
        conn.execute("ALTER TABLE background_tasks ADD COLUMN updated_at TEXT")
    except sqlite3.OperationalError:
        pass
    try:
        conn.execute("ALTER TABLE background_tasks ADD COLUMN params TEXT")
    except sqlite3.OperationalError:
        pass  # column already exists
    # Ensure references tables exist (CREATE IF NOT EXISTS is idempotent)
    conn.execute(CREATE_REFERENCES)
    conn.execute(CREATE_JOB_REFERENCES)
    conn.commit()
    conn.close()


def init_db(db_path: Path = DEFAULT_DB) -> None:
    """Create tables if they don't exist, then run migrations."""
    conn = sqlite3.connect(db_path)
    conn.execute(CREATE_JOBS)
    conn.execute(CREATE_JOB_CONTACTS)
    conn.execute(CREATE_COMPANY_RESEARCH)
    conn.execute(CREATE_BACKGROUND_TASKS)
    conn.execute(CREATE_SURVEY_RESPONSES)
    conn.execute(CREATE_DIGEST_QUEUE)
    conn.execute(CREATE_REFERENCES)
    conn.execute(CREATE_JOB_REFERENCES)
    conn.commit()
    conn.close()
    _migrate_db(db_path)


def insert_job(db_path: Path = DEFAULT_DB, job: dict = None) -> Optional[int]:
    """Insert a job. Returns row id, or None if URL already exists."""
    if job is None:
        return None
    conn = sqlite3.connect(db_path)
    try:
        status = job.get("status", "pending")
        cursor = conn.execute(
            """INSERT INTO jobs
               (title, company, url, source, location, is_remote, salary, description, date_found, date_posted, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                job.get("title", ""),
                job.get("company", ""),
                job.get("url", ""),
                job.get("source", ""),
                job.get("location", ""),
                int(bool(job.get("is_remote", False))),
                job.get("salary", ""),
                job.get("description", ""),
                job.get("date_found", ""),
                job.get("date_posted", "") or "",
                status,
            ),
        )
        conn.commit()
        return cursor.lastrowid
    except sqlite3.IntegrityError:
        return None  # duplicate URL
    finally:
        conn.close()


def get_job_by_id(db_path: Path = DEFAULT_DB, job_id: int = None) -> Optional[dict]:
    """Return a single job by ID, or None if not found."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_jobs_by_status(db_path: Path = DEFAULT_DB, status: str = "pending") -> list[dict]:
    """Return all jobs with the given status as a list of dicts."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.execute(
        "SELECT * FROM jobs WHERE status = ? ORDER BY date_found DESC, id DESC",
        (status,),
    )
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows


def get_email_leads(db_path: Path = DEFAULT_DB) -> list[dict]:
    """Return pending jobs with source='email', newest first."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM jobs WHERE source = 'email' AND status = 'pending' "
        "ORDER BY date_found DESC, id DESC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_job_counts(db_path: Path = DEFAULT_DB) -> dict:
    """Return counts per status."""
    conn = sqlite3.connect(db_path)
    cursor = conn.execute(
        "SELECT status, COUNT(*) as n FROM jobs GROUP BY status"
    )
    counts = {row[0]: row[1] for row in cursor.fetchall()}
    conn.close()
    return counts


def update_job_status(db_path: Path = DEFAULT_DB, ids: list[int] = None, status: str = "approved") -> None:
    """Batch-update status for a list of job IDs."""
    if not ids:
        return
    conn = sqlite3.connect(db_path)
    conn.execute(
        f"UPDATE jobs SET status = ? WHERE id IN ({','.join('?' * len(ids))})",
        [status] + list(ids),
    )
    conn.commit()
    conn.close()


def get_existing_urls(db_path: Path = DEFAULT_DB) -> set[str]:
    """Return all URLs already in staging (any status)."""
    conn = sqlite3.connect(db_path)
    cursor = conn.execute("SELECT url FROM jobs")
    urls = {row[0] for row in cursor.fetchall()}
    conn.close()
    return urls


def write_match_scores(db_path: Path = DEFAULT_DB, job_id: int = None,
                       score: float = 0.0, gaps: str = "") -> None:
    """Write match score and keyword gaps back to a job row."""
    conn = sqlite3.connect(db_path)
    conn.execute(
        "UPDATE jobs SET match_score = ?, keyword_gaps = ? WHERE id = ?",
        (score, gaps, job_id),
    )
    conn.commit()
    conn.close()


def update_cover_letter(db_path: Path = DEFAULT_DB, job_id: int = None, text: str = "") -> None:
    """Persist a generated/edited cover letter for a job."""
    if job_id is None:
        return
    conn = sqlite3.connect(db_path)
    conn.execute("UPDATE jobs SET cover_letter = ? WHERE id = ?", (text, job_id))
    conn.commit()
    conn.close()


def save_optimized_resume(db_path: Path = DEFAULT_DB, job_id: int = None,
                          text: str = "", gap_report: str = "") -> None:
    """Persist ATS-optimized resume text and/or gap report for a job."""
    if job_id is None:
        return
    conn = sqlite3.connect(db_path)
    conn.execute(
        "UPDATE jobs SET optimized_resume = ?, ats_gap_report = ? WHERE id = ?",
        (text or None, gap_report or None, job_id),
    )
    conn.commit()
    conn.close()


def get_optimized_resume(db_path: Path = DEFAULT_DB, job_id: int = None) -> dict:
    """Return optimized_resume and ats_gap_report for a job, or empty strings if absent."""
    if job_id is None:
        return {"optimized_resume": "", "ats_gap_report": ""}
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT optimized_resume, ats_gap_report FROM jobs WHERE id = ?", (job_id,)
    ).fetchone()
    conn.close()
    if not row:
        return {"optimized_resume": "", "ats_gap_report": ""}
    return {
        "optimized_resume": row["optimized_resume"] or "",
        "ats_gap_report":   row["ats_gap_report"] or "",
    }


def save_resume_draft(db_path: Path = DEFAULT_DB, job_id: int = None,
                      draft_json: str = "") -> None:
    """Persist a structured resume review draft (awaiting user approval)."""
    if job_id is None:
        return
    conn = sqlite3.connect(db_path)
    conn.execute(
        "UPDATE jobs SET resume_draft_json = ? WHERE id = ?",
        (draft_json or None, job_id),
    )
    conn.commit()
    conn.close()


def get_resume_draft(db_path: Path = DEFAULT_DB, job_id: int = None) -> dict | None:
    """Return the pending review draft, or None if no draft is waiting."""
    if job_id is None:
        return None
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT resume_draft_json FROM jobs WHERE id = ?", (job_id,)
    ).fetchone()
    conn.close()
    if not row or not row["resume_draft_json"]:
        return None
    import json
    try:
        return json.loads(row["resume_draft_json"])
    except Exception:
        return None


def finalize_resume(db_path: Path = DEFAULT_DB, job_id: int = None,
                    final_text: str = "") -> None:
    """Save approved resume text, archive the previous version, and clear draft."""
    if job_id is None:
        return
    import json
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT optimized_resume, resume_archive_json FROM jobs WHERE id = ?", (job_id,)
    ).fetchone()
    conn.row_factory = None

    # Archive current finalized version if present
    archive: list = []
    if row:
        if row["resume_archive_json"]:
            try:
                archive = json.loads(row["resume_archive_json"])
            except Exception:
                archive = []
        if row["optimized_resume"]:
            from datetime import datetime
            archive.append({
                "archived_at": datetime.now().isoformat()[:16],
                "text": row["optimized_resume"],
            })

    conn.execute(
        "UPDATE jobs SET optimized_resume = ?, resume_draft_json = NULL, "
        "resume_archive_json = ? WHERE id = ?",
        (final_text, json.dumps(archive), job_id),
    )
    conn.commit()
    conn.close()


def get_resume_archive(db_path: Path = DEFAULT_DB, job_id: int = None) -> list:
    """Return list of past finalized resume versions (newest archived first)."""
    if job_id is None:
        return []
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT resume_archive_json FROM jobs WHERE id = ?", (job_id,)
    ).fetchone()
    conn.close()
    if not row or not row["resume_archive_json"]:
        return []
    import json
    try:
        entries = json.loads(row["resume_archive_json"])
        return list(reversed(entries))  # newest first
    except Exception:
        return []


_UPDATABLE_JOB_COLS = {
    "title", "company", "url", "source", "location", "is_remote",
    "salary", "description", "match_score", "keyword_gaps",
}


def update_job_fields(db_path: Path = DEFAULT_DB, job_id: int = None,
                      fields: dict = None) -> None:
    """Update arbitrary job columns. Unknown keys are silently ignored."""
    if job_id is None or not fields:
        return
    safe = {k: v for k, v in fields.items() if k in _UPDATABLE_JOB_COLS}
    if not safe:
        return
    conn = sqlite3.connect(db_path)
    sets = ", ".join(f"{col} = ?" for col in safe)
    conn.execute(
        f"UPDATE jobs SET {sets} WHERE id = ?",
        (*safe.values(), job_id),
    )
    conn.commit()
    conn.close()


def mark_applied(db_path: Path = DEFAULT_DB, ids: list[int] = None) -> None:
    """Set status='applied' and record today's date for a list of job IDs."""
    if not ids:
        return
    today = datetime.now().isoformat()[:10]
    conn = sqlite3.connect(db_path)
    conn.execute(
        f"UPDATE jobs SET status = 'applied', applied_at = ? WHERE id IN ({','.join('?' * len(ids))})",
        [today] + list(ids),
    )
    conn.commit()
    conn.close()


def cancel_task(db_path: Path = DEFAULT_DB, task_id: int = 0) -> bool:
    """Cancel a single queued/running task by id. Returns True if a row was updated."""
    conn = sqlite3.connect(db_path)
    count = conn.execute(
        "UPDATE background_tasks SET status='failed', error='Cancelled by user',"
        " finished_at=datetime('now') WHERE id=? AND status IN ('queued','running')",
        (task_id,),
    ).rowcount
    conn.commit()
    conn.close()
    return count > 0


def kill_stuck_tasks(db_path: Path = DEFAULT_DB) -> int:
    """Mark all queued/running background tasks as failed. Returns count killed."""
    conn = sqlite3.connect(db_path)
    count = conn.execute(
        "UPDATE background_tasks SET status='failed', error='Killed by user',"
        " finished_at=datetime('now') WHERE status IN ('queued','running')"
    ).rowcount
    conn.commit()
    conn.close()
    return count


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


def purge_email_data(db_path: Path = DEFAULT_DB) -> tuple[int, int]:
    """Delete all job_contacts rows and email-sourced pending jobs.
    Returns (contacts_deleted, jobs_deleted).
    """
    conn = sqlite3.connect(db_path)
    c1 = conn.execute("DELETE FROM job_contacts").rowcount
    c2 = conn.execute("DELETE FROM jobs WHERE source='email'").rowcount
    conn.commit()
    conn.close()
    return c1, c2


def purge_jobs(db_path: Path = DEFAULT_DB, statuses: list[str] = None) -> int:
    """Delete jobs matching given statuses. Returns number of rows deleted.
    If statuses is None or empty, deletes ALL jobs (full reset).
    """
    conn = sqlite3.connect(db_path)
    if statuses:
        placeholders = ",".join("?" * len(statuses))
        cur = conn.execute(f"DELETE FROM jobs WHERE status IN ({placeholders})", statuses)
    else:
        cur = conn.execute("DELETE FROM jobs")
    count = cur.rowcount
    conn.commit()
    conn.close()
    return count


def purge_non_remote(db_path: Path = DEFAULT_DB) -> int:
    """Delete non-remote jobs that are not yet in the active pipeline.
    Preserves applied, phone_screen, interviewing, offer, hired, and synced records.
    Returns number of rows deleted.
    """
    _safe = ("applied", "phone_screen", "interviewing", "offer", "hired", "synced")
    placeholders = ",".join("?" * len(_safe))
    conn = sqlite3.connect(db_path)
    count = conn.execute(
        f"DELETE FROM jobs WHERE (is_remote = 0 OR is_remote IS NULL)"
        f" AND status NOT IN ({placeholders})",
        _safe,
    ).rowcount
    conn.commit()
    conn.close()
    return count


def archive_jobs(db_path: Path = DEFAULT_DB, statuses: list[str] = None) -> int:
    """Set status='archived' for jobs matching given statuses.

    Archived jobs stay in the DB (preserving dedup by URL) but are invisible
    to Job Review and other pipeline views.
    Returns number of rows updated.
    """
    if not statuses:
        return 0
    placeholders = ",".join("?" * len(statuses))
    conn = sqlite3.connect(db_path)
    count = conn.execute(
        f"UPDATE jobs SET status = 'archived' WHERE status IN ({placeholders})",
        statuses,
    ).rowcount
    conn.commit()
    conn.close()
    return count


# ── Interview pipeline helpers ────────────────────────────────────────────────

_STAGE_TS_COL = {
    "phone_screen": "phone_screen_at",
    "interviewing":  "interviewing_at",
    "offer":         "offer_at",
    "hired":         "hired_at",
    "survey":        "survey_at",
}


def get_interview_jobs(db_path: Path = DEFAULT_DB) -> dict[str, list[dict]]:
    """Return jobs grouped by interview/post-apply stage."""
    stages = ["applied", "survey", "phone_screen", "interviewing", "offer", "hired", "rejected"]
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    result: dict[str, list[dict]] = {}
    for stage in stages:
        cursor = conn.execute(
            "SELECT * FROM jobs WHERE status = ? ORDER BY applied_at DESC, id DESC",
            (stage,),
        )
        result[stage] = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return result


def advance_to_stage(db_path: Path = DEFAULT_DB, job_id: int = None, stage: str = "") -> None:
    """Move a job to the next interview stage and record a timestamp."""
    now = datetime.now().isoformat()[:16]
    ts_col = _STAGE_TS_COL.get(stage)
    conn = sqlite3.connect(db_path)
    if ts_col:
        conn.execute(
            f"UPDATE jobs SET status = ?, {ts_col} = ? WHERE id = ?",
            (stage, now, job_id),
        )
    else:
        conn.execute("UPDATE jobs SET status = ? WHERE id = ?", (stage, job_id))
    conn.commit()
    conn.close()


def reject_at_stage(db_path: Path = DEFAULT_DB, job_id: int = None,
                    rejection_stage: str = "") -> None:
    """Mark a job as rejected and record at which stage it was rejected."""
    conn = sqlite3.connect(db_path)
    conn.execute(
        "UPDATE jobs SET status = 'rejected', rejection_stage = ? WHERE id = ?",
        (rejection_stage, job_id),
    )
    conn.commit()
    conn.close()


def set_interview_date(db_path: Path = DEFAULT_DB, job_id: int = None,
                       date_str: str = "") -> None:
    """Persist an interview date for a job."""
    conn = sqlite3.connect(db_path)
    conn.execute("UPDATE jobs SET interview_date = ? WHERE id = ?", (date_str, job_id))
    conn.commit()
    conn.close()


def set_calendar_event_id(db_path: Path = DEFAULT_DB, job_id: int = None,
                          event_id: str = "") -> None:
    """Persist the calendar event ID returned after a successful push."""
    conn = sqlite3.connect(db_path)
    conn.execute("UPDATE jobs SET calendar_event_id = ? WHERE id = ?", (event_id, job_id))
    conn.commit()
    conn.close()


# ── Contact log helpers ───────────────────────────────────────────────────────

def add_contact(db_path: Path = DEFAULT_DB, job_id: int = None,
                direction: str = "inbound", subject: str = "",
                from_addr: str = "", to_addr: str = "",
                body: str = "", received_at: str = "",
                message_id: str = "",
                stage_signal: str = "") -> int:
    """Log an email contact. Returns the new row id."""
    ts = received_at or datetime.now().isoformat()[:16]
    conn = sqlite3.connect(db_path)
    cur = conn.execute(
        """INSERT INTO job_contacts
           (job_id, direction, subject, from_addr, to_addr, body,
            received_at, message_id, stage_signal)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (job_id, direction, subject, from_addr, to_addr, body,
         ts, message_id, stage_signal or None),
    )
    conn.commit()
    row_id = cur.lastrowid
    conn.close()
    return row_id


def get_contacts(db_path: Path = DEFAULT_DB, job_id: int = None) -> list[dict]:
    """Return all contact log entries for a job, oldest first."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.execute(
        "SELECT * FROM job_contacts WHERE job_id = ? ORDER BY received_at ASC",
        (job_id,),
    )
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows


def get_unread_stage_signals(db_path: Path = DEFAULT_DB,
                             job_id: int = None) -> list[dict]:
    """Return inbound contacts with a non-neutral, non-dismissed stage signal."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """SELECT * FROM job_contacts
           WHERE job_id = ?
             AND direction = 'inbound'
             AND stage_signal IS NOT NULL
             AND stage_signal != 'neutral'
             AND (suggestion_dismissed IS NULL OR suggestion_dismissed = 0)
           ORDER BY received_at ASC""",
        (job_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def dismiss_stage_signal(db_path: Path = DEFAULT_DB,
                         contact_id: int = None) -> None:
    """Mark a stage signal suggestion as dismissed."""
    conn = sqlite3.connect(db_path)
    conn.execute(
        "UPDATE job_contacts SET suggestion_dismissed = 1 WHERE id = ?",
        (contact_id,),
    )
    conn.commit()
    conn.close()


def get_all_message_ids(db_path: Path = DEFAULT_DB) -> set[str]:
    """Return all known Message-IDs across all job contacts."""
    conn = sqlite3.connect(db_path)
    rows = conn.execute(
        "SELECT message_id FROM job_contacts WHERE message_id IS NOT NULL AND message_id != ''"
    ).fetchall()
    conn.close()
    return {r[0] for r in rows}


# ── Company research helpers ──────────────────────────────────────────────────

def save_research(db_path: Path = DEFAULT_DB, job_id: int = None,
                  company_brief: str = "", ceo_brief: str = "",
                  talking_points: str = "", raw_output: str = "",
                  tech_brief: str = "", funding_brief: str = "",
                  competitors_brief: str = "", red_flags: str = "",
                  accessibility_brief: str = "",
                  scrape_used: int = 0) -> None:
    """Insert or replace a company research record for a job."""
    now = datetime.now().isoformat()[:16]
    conn = sqlite3.connect(db_path)
    conn.execute(
        """INSERT INTO company_research
               (job_id, generated_at, company_brief, ceo_brief, talking_points,
                raw_output, tech_brief, funding_brief, competitors_brief, red_flags,
                accessibility_brief, scrape_used)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(job_id) DO UPDATE SET
               generated_at        = excluded.generated_at,
               company_brief       = excluded.company_brief,
               ceo_brief           = excluded.ceo_brief,
               talking_points      = excluded.talking_points,
               raw_output          = excluded.raw_output,
               tech_brief          = excluded.tech_brief,
               funding_brief       = excluded.funding_brief,
               competitors_brief   = excluded.competitors_brief,
               red_flags           = excluded.red_flags,
               accessibility_brief = excluded.accessibility_brief,
               scrape_used         = excluded.scrape_used""",
        (job_id, now, company_brief, ceo_brief, talking_points, raw_output,
         tech_brief, funding_brief, competitors_brief, red_flags,
         accessibility_brief, scrape_used),
    )
    conn.commit()
    conn.close()


def get_research(db_path: Path = DEFAULT_DB, job_id: int = None) -> Optional[dict]:
    """Return the company research record for a job, or None if absent."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.execute(
        "SELECT * FROM company_research WHERE job_id = ?", (job_id,)
    )
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


# ── Survey response helpers ───────────────────────────────────────────────────

def insert_survey_response(
    db_path: Path = DEFAULT_DB,
    job_id: int = None,
    survey_name: str = "",
    received_at: str = "",
    source: str = "text_paste",
    raw_input: str = "",
    image_path: str = "",
    mode: str = "quick",
    llm_output: str = "",
    reported_score: str = "",
) -> int:
    """Insert a survey response row. Returns the new row id."""
    conn = sqlite3.connect(db_path)
    cur = conn.execute(
        """INSERT INTO survey_responses
           (job_id, survey_name, received_at, source, raw_input,
            image_path, mode, llm_output, reported_score)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (job_id, survey_name or None, received_at or None,
         source, raw_input or None, image_path or None,
         mode, llm_output, reported_score or None),
    )
    conn.commit()
    row_id = cur.lastrowid
    conn.close()
    return row_id


def get_survey_responses(db_path: Path = DEFAULT_DB, job_id: int = None) -> list[dict]:
    """Return all survey responses for a job, newest first."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM survey_responses WHERE job_id = ? ORDER BY created_at DESC",
        (job_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── Background task helpers ───────────────────────────────────────────────────

def insert_task(db_path: Path = DEFAULT_DB, task_type: str = "",
                job_id: int = None,
                params: Optional[str] = None) -> tuple[int, bool]:
    """Insert a new background task.

    Returns (task_id, True) if inserted, or (existing_id, False) if a
    queued/running task for the same (task_type, job_id) already exists.

    Dedup key: (task_type, job_id) when params is None;
               (task_type, job_id, params) when params is provided.
    """
    conn = sqlite3.connect(db_path)
    try:
        if params is not None:
            existing = conn.execute(
                "SELECT id FROM background_tasks WHERE task_type=? AND job_id=? "
                "AND params=? AND status IN ('queued','running')",
                (task_type, job_id, params),
            ).fetchone()
        else:
            existing = conn.execute(
                "SELECT id FROM background_tasks WHERE task_type=? AND job_id=? "
                "AND status IN ('queued','running')",
                (task_type, job_id),
            ).fetchone()
        if existing:
            return existing[0], False
        cur = conn.execute(
            "INSERT INTO background_tasks (task_type, job_id, params) VALUES (?,?,?)",
            (task_type, job_id, params),
        )
        conn.commit()
        return cur.lastrowid, True
    finally:
        conn.close()


def update_task_status(db_path: Path = DEFAULT_DB, task_id: int = None,
                       status: str = "", error: Optional[str] = None) -> None:
    """Update a task's status and set the appropriate timestamp."""
    now = datetime.now().isoformat()[:16]
    conn = sqlite3.connect(db_path)
    if status == "running":
        conn.execute(
            "UPDATE background_tasks SET status=?, started_at=?, updated_at=? WHERE id=?",
            (status, now, now, task_id),
        )
    elif status in ("completed", "failed"):
        conn.execute(
            "UPDATE background_tasks SET status=?, finished_at=?, updated_at=?, error=? WHERE id=?",
            (status, now, now, error, task_id),
        )
    else:
        conn.execute(
            "UPDATE background_tasks SET status=?, updated_at=? WHERE id=?",
            (status, now, task_id),
        )
    conn.commit()
    conn.close()


def update_task_stage(db_path: Path = DEFAULT_DB, task_id: int = None,
                      stage: str = "") -> None:
    """Update the stage label on a running task (for progress display)."""
    conn = sqlite3.connect(db_path)
    conn.execute("UPDATE background_tasks SET stage=? WHERE id=?", (stage, task_id))
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


# ── Resume library helpers ────────────────────────────────────────────────────


def _resume_as_dict(row) -> dict:
    """Convert a sqlite3.Row from the resumes table to a plain dict."""
    return {
        "id":          row["id"],
        "name":        row["name"],
        "source":      row["source"],
        "job_id":      row["job_id"],
        "text":        row["text"],
        "struct_json": row["struct_json"],
        "word_count":  row["word_count"],
        "is_default":  row["is_default"],
        "created_at":  row["created_at"],
        "updated_at":  row["updated_at"],
        "synced_at":   row["synced_at"] if "synced_at" in row.keys() else None,
    }


def create_resume(
    db_path: Path = DEFAULT_DB,
    name: str = "",
    text: str = "",
    source: str = "manual",
    job_id: int | None = None,
    struct_json: str | None = None,
) -> dict:
    """Insert a new resume into the library. Returns the created row as a dict."""
    word_count = len(text.split()) if text else 0
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.execute(
            """INSERT INTO resumes (name, source, job_id, text, struct_json, word_count)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (name, source, job_id, text, struct_json, word_count),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM resumes WHERE id=?", (cur.lastrowid,)).fetchone()
        return _resume_as_dict(row)
    finally:
        conn.close()


def list_resumes(db_path: Path = DEFAULT_DB) -> list[dict]:
    """Return all resumes ordered by default-first then newest-first."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT * FROM resumes ORDER BY is_default DESC, created_at DESC"
        ).fetchall()
        return [_resume_as_dict(r) for r in rows]
    finally:
        conn.close()


def get_resume(db_path: Path = DEFAULT_DB, resume_id: int = 0) -> dict | None:
    """Return a single resume by id, or None if not found."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute("SELECT * FROM resumes WHERE id=?", (resume_id,)).fetchone()
        return _resume_as_dict(row) if row else None
    finally:
        conn.close()


def update_resume(
    db_path: Path = DEFAULT_DB,
    resume_id: int = 0,
    name: str | None = None,
    text: str | None = None,
) -> dict | None:
    """Update name and/or text of a resume. Returns updated row or None."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        if name is not None:
            conn.execute(
                "UPDATE resumes SET name=?, updated_at=datetime('now') WHERE id=?",
                (name, resume_id),
            )
        if text is not None:
            word_count = len(text.split())
            conn.execute(
                "UPDATE resumes SET text=?, word_count=?, updated_at=datetime('now') WHERE id=?",
                (text, word_count, resume_id),
            )
        conn.commit()
        row = conn.execute("SELECT * FROM resumes WHERE id=?", (resume_id,)).fetchone()
        return _resume_as_dict(row) if row else None
    finally:
        conn.close()


def delete_resume(db_path: Path = DEFAULT_DB, resume_id: int = 0) -> None:
    """Delete a resume by id."""
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("DELETE FROM resumes WHERE id=?", (resume_id,))
        conn.commit()
    finally:
        conn.close()


def set_default_resume(db_path: Path = DEFAULT_DB, resume_id: int = 0) -> None:
    """Set one resume as default, clearing the flag on all others."""
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("UPDATE resumes SET is_default=0")
        conn.execute("UPDATE resumes SET is_default=1 WHERE id=?", (resume_id,))
        conn.commit()
    finally:
        conn.close()


def update_resume_synced_at(db_path: Path = DEFAULT_DB, resume_id: int = 0) -> None:
    """Mark a library entry as synced to the profile (library→profile direction)."""
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "UPDATE resumes SET synced_at=datetime('now') WHERE id=?",
            (resume_id,),
        )
        conn.commit()
    finally:
        conn.close()


def update_resume_content(
    db_path: Path = DEFAULT_DB,
    resume_id: int = 0,
    text: str = "",
    struct_json: str | None = None,
) -> None:
    """Update text, struct_json, and synced_at for a library entry.

    Called by the profile→library sync path (PUT /api/settings/resume).
    """
    word_count = len(text.split()) if text else 0
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """UPDATE resumes
               SET text=?, struct_json=?, word_count=?,
                   synced_at=datetime('now'), updated_at=datetime('now')
               WHERE id=?""",
            (text, struct_json, word_count, resume_id),
        )
        conn.commit()
    finally:
        conn.close()


def get_job_resume(db_path: Path = DEFAULT_DB, job_id: int = 0) -> dict | None:
    """Return the resume for a job: job-specific first, then default, then None."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            """SELECT r.* FROM resumes r
               JOIN jobs j ON j.resume_id = r.id
               WHERE j.id=?""",
            (job_id,),
        ).fetchone()
        if row:
            return _resume_as_dict(row)
        row = conn.execute(
            "SELECT * FROM resumes WHERE is_default=1 LIMIT 1"
        ).fetchone()
        return _resume_as_dict(row) if row else None
    finally:
        conn.close()


def set_job_resume(db_path: Path = DEFAULT_DB, job_id: int = 0, resume_id: int = 0) -> None:
    """Attach a specific resume to a job (overrides default for that job)."""
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("UPDATE jobs SET resume_id=? WHERE id=?", (resume_id, job_id))
        conn.commit()
    finally:
        conn.close()

# ── Training export helpers ───────────────────────────────────────────────────

def _strip_greeting(text: str) -> str:
    """Remove 'Dear X,' greeting line from cover letter text."""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        stripped_line = line.strip()
        if stripped_line.lower().startswith("dear ") and stripped_line.endswith((",", ":")):
            rest = lines[i + 1:]
            while rest and not rest[0].strip():
                rest = rest[1:]
            result = "\n".join(rest).strip()
            return result if result else text.strip()
    return text.strip()


def get_db_pairs(db_path: Path) -> list[dict]:
    """Return curation metadata for ALL qualifying jobs (included and excluded).

    Used by the curation UI. Includes excluded=True rows so users can restore them.
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT id, title, company, description, status, "
            "  excluded_from_training "
            "FROM jobs "
            "WHERE status IN ('applied','phone_screen','interviewing','offer','hired') "
            "  AND cover_letter IS NOT NULL AND cover_letter != '' "
            "ORDER BY applied_at DESC",
        ).fetchall()
    finally:
        conn.close()
    return [
        {
            "job_id":        row["id"],
            "title":         row["title"] or "",
            "company":       row["company"] or "",
            "status":        row["status"],
            "instruction":   (
                f"Write a cover letter for the {row['title'] or 'unknown'} "
                f"position at {row['company'] or 'unknown'}."
            ),
            "input_preview": (row["description"] or "")[:200],
            "excluded":      bool(row["excluded_from_training"]),
        }
        for row in rows
    ]


def get_training_pairs(db_path: Path) -> list[dict]:
    """Return Alpaca-format training pairs for non-excluded qualifying jobs.

    Used by the JSONL export endpoint.
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT id, title, company, description, cover_letter "
            "FROM jobs "
            "WHERE status IN ('applied','phone_screen','interviewing','offer','hired') "
            "  AND cover_letter IS NOT NULL AND cover_letter != '' "
            "  AND excluded_from_training = 0 "
            "ORDER BY applied_at DESC",
        ).fetchall()
    finally:
        conn.close()
    return [
        {
            "instruction": (
                f"Write a cover letter for the {row['title'] or 'unknown'} "
                f"position at {row['company'] or 'unknown'}."
            ),
            "input":   row["description"] or "",
            "output":  _strip_greeting(row["cover_letter"]),
            "source":  "db",
            "job_id":  row["id"],
        }
        for row in rows
    ]


def set_training_exclusion(db_path: Path, job_id: int, excluded: bool) -> None:
    """Set excluded_from_training flag on a job."""
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "UPDATE jobs SET excluded_from_training = ? WHERE id = ?",
            (1 if excluded else 0, job_id),
        )
        conn.commit()
    finally:
        conn.close()
