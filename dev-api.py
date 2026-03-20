"""
Minimal dev-only FastAPI server for the Vue SPA.
Reads directly from /devl/job-seeker/staging.db.
Run with:
    conda run -n job-seeker uvicorn dev-api:app --port 8600 --reload
"""
import sqlite3
import os
import sys
import re
import json
import threading
from bs4 import BeautifulSoup
from datetime import datetime
from pathlib import Path
from fastapi import FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional

# Allow importing peregrine scripts for cover letter generation
PEREGRINE_ROOT = Path("/Library/Development/CircuitForge/peregrine")
if str(PEREGRINE_ROOT) not in sys.path:
    sys.path.insert(0, str(PEREGRINE_ROOT))

DB_PATH = os.environ.get("STAGING_DB", "/devl/job-seeker/staging.db")

app = FastAPI(title="Peregrine Dev API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://10.1.10.71:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _get_db():
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    return db


def _strip_html(text: str | None) -> str | None:
    """Strip HTML tags and normalize whitespace in email body text."""
    if not text:
        return text
    plain = BeautifulSoup(text, 'html.parser').get_text(separator='\n')
    # Strip trailing whitespace from each line
    lines = [line.rstrip() for line in plain.split('\n')]
    # Collapse 3+ consecutive blank lines to at most 2
    cleaned = re.sub(r'\n{3,}', '\n\n', '\n'.join(lines))
    return cleaned.strip() or None


@app.on_event("startup")
def _startup():
    """Ensure digest_queue table exists (dev-api may run against an existing DB)."""
    db = _get_db()
    try:
        db.execute("""
            CREATE TABLE IF NOT EXISTS digest_queue (
              id             INTEGER PRIMARY KEY,
              job_contact_id INTEGER NOT NULL REFERENCES job_contacts(id),
              created_at     TEXT DEFAULT (datetime('now')),
              UNIQUE(job_contact_id)
            )
        """)
        db.commit()
    finally:
        db.close()


def _row_to_job(row) -> dict:
    d = dict(row)
    d["is_remote"] = bool(d.get("is_remote", 0))
    return d


# ── GET /api/jobs ─────────────────────────────────────────────────────────────

@app.get("/api/jobs")
def list_jobs(status: str = "pending", limit: int = 50, fields: str = ""):
    db = _get_db()
    rows = db.execute(
        "SELECT id, title, company, url, source, location, is_remote, salary, "
        "description, match_score, keyword_gaps, date_found, status, cover_letter "
        "FROM jobs WHERE status = ? ORDER BY match_score DESC NULLS LAST LIMIT ?",
        (status, limit),
    ).fetchall()
    db.close()
    result = []
    for r in rows:
        d = _row_to_job(r)
        d["has_cover_letter"] = bool(d.get("cover_letter"))
        # Don't send full cover_letter text in the list view
        d.pop("cover_letter", None)
        result.append(d)
    return result


# ── GET /api/jobs/counts ──────────────────────────────────────────────────────

@app.get("/api/jobs/counts")
def job_counts():
    db = _get_db()
    rows = db.execute("SELECT status, count(*) as n FROM jobs GROUP BY status").fetchall()
    db.close()
    counts = {r["status"]: r["n"] for r in rows}
    return {
        "pending":  counts.get("pending",  0),
        "approved": counts.get("approved", 0),
        "applied":  counts.get("applied",  0),
        "synced":   counts.get("synced",   0),
        "rejected": counts.get("rejected", 0),
        "total":    sum(counts.values()),
    }


# ── POST /api/jobs/{id}/approve ───────────────────────────────────────────────

@app.post("/api/jobs/{job_id}/approve")
def approve_job(job_id: int):
    db = _get_db()
    db.execute("UPDATE jobs SET status = 'approved' WHERE id = ?", (job_id,))
    db.commit()
    db.close()
    return {"ok": True}


# ── POST /api/jobs/{id}/reject ────────────────────────────────────────────────

@app.post("/api/jobs/{job_id}/reject")
def reject_job(job_id: int):
    db = _get_db()
    db.execute("UPDATE jobs SET status = 'rejected' WHERE id = ?", (job_id,))
    db.commit()
    db.close()
    return {"ok": True}


# ── POST /api/jobs/{id}/revert ────────────────────────────────────────────────

class RevertBody(BaseModel):
    status: str

@app.post("/api/jobs/{job_id}/revert")
def revert_job(job_id: int, body: RevertBody):
    allowed = {"pending", "approved", "rejected", "applied", "synced"}
    if body.status not in allowed:
        raise HTTPException(400, f"Invalid status: {body.status}")
    db = _get_db()
    db.execute("UPDATE jobs SET status = ? WHERE id = ?", (body.status, job_id))
    db.commit()
    db.close()
    return {"ok": True}


# ── GET /api/system/status ────────────────────────────────────────────────────

@app.get("/api/system/status")
def system_status():
    return {
        "enrichment_enabled":  False,
        "enrichment_last_run": None,
        "enrichment_next_run": None,
        "tasks_running":       0,
        "integration_name":    "Notion",
        "integration_unsynced": 0,
    }


# ── GET /api/jobs/:id ────────────────────────────────────────────────────────

@app.get("/api/jobs/{job_id}")
def get_job(job_id: int):
    db = _get_db()
    row = db.execute(
        "SELECT id, title, company, url, source, location, is_remote, salary, "
        "description, match_score, keyword_gaps, date_found, status, cover_letter "
        "FROM jobs WHERE id = ?",
        (job_id,),
    ).fetchone()
    db.close()
    if not row:
        raise HTTPException(404, "Job not found")
    d = _row_to_job(row)
    d["has_cover_letter"] = bool(d.get("cover_letter"))
    return d


# ── POST /api/jobs/:id/applied ────────────────────────────────────────────────

@app.post("/api/jobs/{job_id}/applied")
def mark_applied(job_id: int):
    db = _get_db()
    db.execute(
        "UPDATE jobs SET status = 'applied', applied_at = datetime('now') WHERE id = ?",
        (job_id,),
    )
    db.commit()
    db.close()
    return {"ok": True}


# ── PATCH /api/jobs/:id/cover_letter ─────────────────────────────────────────

class CoverLetterBody(BaseModel):
    text: str

@app.patch("/api/jobs/{job_id}/cover_letter")
def save_cover_letter(job_id: int, body: CoverLetterBody):
    db = _get_db()
    db.execute("UPDATE jobs SET cover_letter = ? WHERE id = ?", (body.text, job_id))
    db.commit()
    db.close()
    return {"ok": True}


# ── POST /api/jobs/:id/cover_letter/generate ─────────────────────────────────

@app.post("/api/jobs/{job_id}/cover_letter/generate")
def generate_cover_letter(job_id: int):
    try:
        from scripts.task_runner import submit_task
        task_id, is_new = submit_task(
            db_path=Path(DB_PATH),
            task_type="cover_letter",
            job_id=job_id,
        )
        return {"task_id": task_id, "is_new": is_new}
    except Exception as e:
        raise HTTPException(500, str(e))


# ── GET /api/jobs/:id/cover_letter/task ──────────────────────────────────────

@app.get("/api/jobs/{job_id}/cover_letter/task")
def cover_letter_task(job_id: int):
    db = _get_db()
    row = db.execute(
        "SELECT status, stage, error FROM background_tasks "
        "WHERE task_type = 'cover_letter' AND job_id = ? "
        "ORDER BY id DESC LIMIT 1",
        (job_id,),
    ).fetchone()
    db.close()
    if not row:
        return {"status": "none", "stage": None, "message": None}
    return {
        "status":  row["status"],
        "stage":   row["stage"],
        "message": row["error"],
    }


# ── GET /api/jobs/:id/cover_letter/pdf ───────────────────────────────────────

@app.get("/api/jobs/{job_id}/cover_letter/pdf")
def download_pdf(job_id: int):
    db = _get_db()
    row = db.execute(
        "SELECT title, company, cover_letter FROM jobs WHERE id = ?", (job_id,)
    ).fetchone()
    db.close()
    if not row or not row["cover_letter"]:
        raise HTTPException(404, "No cover letter found")

    try:
        from reportlab.lib.pagesizes import letter as letter_size
        from reportlab.lib.units import inch
        from reportlab.lib.colors import HexColor
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.lib.enums import TA_LEFT
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
        import io

        buf  = io.BytesIO()
        doc  = SimpleDocTemplate(buf, pagesize=letter_size,
                                 leftMargin=inch, rightMargin=inch,
                                 topMargin=inch, bottomMargin=inch)
        dark = HexColor("#1a2338")
        body_style = ParagraphStyle(
            "Body", fontName="Helvetica", fontSize=11,
            textColor=dark, leading=16, spaceAfter=12, alignment=TA_LEFT,
        )
        story = []
        for para in row["cover_letter"].split("\n\n"):
            para = para.strip()
            if para:
                story.append(Paragraph(para.replace("\n", "<br/>"), body_style))
                story.append(Spacer(1, 2))
        doc.build(story)

        company_safe = re.sub(r"[^a-zA-Z0-9]", "", row["company"] or "Company")
        date_str     = datetime.now().strftime("%Y-%m-%d")
        filename     = f"CoverLetter_{company_safe}_{date_str}.pdf"

        return Response(
            content=buf.getvalue(),
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except ImportError:
        raise HTTPException(501, "reportlab not installed — install it to generate PDFs")


# ── GET /api/interviews ────────────────────────────────────────────────────────

PIPELINE_STATUSES = {
    "applied", "survey",
    "phone_screen", "interviewing",
    "offer", "hired",
    "interview_rejected",
}

SIGNAL_EXCLUDED = ("neutral", "unrelated", "digest", "event_rescheduled")

@app.get("/api/interviews")
def list_interviews():
    db = _get_db()
    placeholders = ",".join("?" * len(PIPELINE_STATUSES))
    rows = db.execute(
        f"SELECT id, title, company, url, location, is_remote, salary, "
        f"match_score, keyword_gaps, status, "
        f"interview_date, rejection_stage, "
        f"applied_at, phone_screen_at, interviewing_at, offer_at, hired_at, survey_at "
        f"FROM jobs WHERE status IN ({placeholders}) "
        f"ORDER BY match_score DESC NULLS LAST",
        list(PIPELINE_STATUSES),
    ).fetchall()

    job_ids = [r["id"] for r in rows]
    signals_by_job: dict[int, list] = {r["id"]: [] for r in rows}

    if job_ids:
        sig_placeholders = ",".join("?" * len(job_ids))
        excl_placeholders = ",".join("?" * len(SIGNAL_EXCLUDED))
        sig_rows = db.execute(
            f"SELECT id, job_id, subject, received_at, stage_signal, body, from_addr "
            f"FROM job_contacts "
            f"WHERE job_id IN ({sig_placeholders}) "
            f"  AND suggestion_dismissed = 0 "
            f"  AND stage_signal NOT IN ({excl_placeholders}) "
            f"  AND stage_signal IS NOT NULL "
            f"ORDER BY received_at DESC",
            job_ids + list(SIGNAL_EXCLUDED),
        ).fetchall()
        for sr in sig_rows:
            signals_by_job[sr["job_id"]].append({
                "id":           sr["id"],
                "subject":      sr["subject"],
                "received_at":  sr["received_at"],
                "stage_signal": sr["stage_signal"],
                "body":         _strip_html(sr["body"]),
                "from_addr":    sr["from_addr"],
            })

    db.close()
    return [
        {**dict(r), "is_remote": bool(r["is_remote"]), "stage_signals": signals_by_job[r["id"]]}
        for r in rows
    ]


# ── POST /api/email/sync ──────────────────────────────────────────────────

@app.post("/api/email/sync", status_code=202)
def trigger_email_sync():
    db = _get_db()
    cursor = db.execute(
        "INSERT INTO background_tasks (task_type, job_id, status) VALUES ('email_sync', 0, 'queued')"
    )
    db.commit()
    task_id = cursor.lastrowid
    db.close()
    return {"task_id": task_id}


# ── GET /api/email/sync/status ────────────────────────────────────────────

@app.get("/api/email/sync/status")
def email_sync_status():
    db = _get_db()
    row = db.execute(
        "SELECT status, finished_at AS last_completed_at "
        "FROM background_tasks "
        "WHERE task_type = 'email_sync' "
        "ORDER BY id DESC LIMIT 1"
    ).fetchone()
    db.close()
    if row is None:
        return {"status": "idle", "last_completed_at": None, "error": None}
    # background_tasks may not have an error column in staging — guard with dict access
    row_dict = dict(row)
    return {
        "status":            row_dict["status"],
        "last_completed_at": row_dict["last_completed_at"],
        "error":             row_dict.get("error"),
    }


# ── POST /api/stage-signals/{id}/dismiss ─────────────────────────────────

@app.post("/api/stage-signals/{signal_id}/dismiss")
def dismiss_signal(signal_id: int):
    db = _get_db()
    result = db.execute(
        "UPDATE job_contacts SET suggestion_dismissed = 1 WHERE id = ?",
        (signal_id,),
    )
    db.commit()
    rowcount = result.rowcount
    db.close()
    if rowcount == 0:
        raise HTTPException(404, "Signal not found")
    return {"ok": True}


# ── POST /api/stage-signals/{id}/reclassify ──────────────────────────────

VALID_SIGNAL_LABELS = {
    'interview_scheduled', 'offer_received', 'rejected',
    'positive_response', 'survey_received', 'neutral',
    'event_rescheduled', 'unrelated', 'digest',
}

class ReclassifyBody(BaseModel):
    stage_signal: str

@app.post("/api/stage-signals/{signal_id}/reclassify")
def reclassify_signal(signal_id: int, body: ReclassifyBody):
    if body.stage_signal not in VALID_SIGNAL_LABELS:
        raise HTTPException(400, f"Invalid label: {body.stage_signal}")
    db = _get_db()
    result = db.execute(
        "UPDATE job_contacts SET stage_signal = ? WHERE id = ?",
        (body.stage_signal, signal_id),
    )
    db.commit()
    rowcount = result.rowcount
    db.close()
    if rowcount == 0:
        raise HTTPException(404, "Signal not found")
    return {"ok": True}


# ── Digest queue models ───────────────────────────────────────────────────

class DigestQueueBody(BaseModel):
    job_contact_id: int


# ── GET /api/digest-queue ─────────────────────────────────────────────────

@app.get("/api/digest-queue")
def list_digest_queue():
    db = _get_db()
    rows = db.execute(
        """SELECT dq.id, dq.job_contact_id, dq.created_at,
                  jc.subject, jc.from_addr, jc.received_at, jc.body
           FROM digest_queue dq
           JOIN job_contacts jc ON jc.id = dq.job_contact_id
           ORDER BY dq.created_at DESC"""
    ).fetchall()
    db.close()
    return [
        {
            "id":             r["id"],
            "job_contact_id": r["job_contact_id"],
            "created_at":     r["created_at"],
            "subject":        r["subject"],
            "from_addr":      r["from_addr"],
            "received_at":    r["received_at"],
            "body":           _strip_html(r["body"]),
        }
        for r in rows
    ]


# ── POST /api/digest-queue ────────────────────────────────────────────────

@app.post("/api/digest-queue")
def add_to_digest_queue(body: DigestQueueBody):
    db = _get_db()
    try:
        exists = db.execute(
            "SELECT 1 FROM job_contacts WHERE id = ?", (body.job_contact_id,)
        ).fetchone()
        if not exists:
            raise HTTPException(404, "job_contact_id not found")
        result = db.execute(
            "INSERT OR IGNORE INTO digest_queue (job_contact_id) VALUES (?)",
            (body.job_contact_id,),
        )
        db.commit()
        created = result.rowcount > 0
    finally:
        db.close()
    return {"ok": True, "created": created}


# ── POST /api/jobs/{id}/move ───────────────────────────────────────────────────

STATUS_TIMESTAMP_COL = {
    "applied":            "applied_at",
    "survey":             "survey_at",
    "phone_screen":       "phone_screen_at",
    "interviewing":       "interviewing_at",
    "offer":              "offer_at",
    "hired":              "hired_at",
    "interview_rejected": None,  # uses rejection_stage instead
}

class MoveBody(BaseModel):
    status:           str
    interview_date:   str | None = None
    rejection_stage:  str | None = None

@app.post("/api/jobs/{job_id}/move")
def move_job(job_id: int, body: MoveBody):
    if body.status not in STATUS_TIMESTAMP_COL:
        raise HTTPException(400, f"Invalid pipeline status: {body.status}")
    db = _get_db()
    ts_col = STATUS_TIMESTAMP_COL[body.status]
    if ts_col:
        db.execute(
            f"UPDATE jobs SET status = ?, {ts_col} = datetime('now') WHERE id = ?",
            (body.status, job_id),
        )
    else:
        db.execute(
            "UPDATE jobs SET status = ?, rejection_stage = ? WHERE id = ?",
            (body.status, body.rejection_stage, job_id),
        )
    if body.interview_date is not None:
        db.execute(
            "UPDATE jobs SET interview_date = ? WHERE id = ?",
            (body.interview_date, job_id),
        )
    db.commit()
    db.close()
    return {"ok": True}


# ── GET /api/config/user ──────────────────────────────────────────────────────

@app.get("/api/config/user")
def config_user():
    # Try to read name from user.yaml if present
    try:
        import yaml
        cfg_path = os.path.join(os.path.dirname(DB_PATH), "config", "user.yaml")
        if not os.path.exists(cfg_path):
            cfg_path = "/devl/job-seeker/config/user.yaml"
        with open(cfg_path) as f:
            cfg = yaml.safe_load(f)
        return {"name": cfg.get("name", "")}
    except Exception:
        return {"name": ""}
