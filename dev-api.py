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
from urllib.parse import urlparse
from bs4 import BeautifulSoup
from datetime import datetime
from pathlib import Path
from fastapi import FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import requests

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


# ── Link extraction helpers ───────────────────────────────────────────────

_JOB_DOMAINS = frozenset({
    'greenhouse.io', 'lever.co', 'workday.com', 'linkedin.com',
    'ashbyhq.com', 'smartrecruiters.com', 'icims.com', 'taleo.net',
    'jobvite.com', 'breezy.hr', 'recruitee.com', 'bamboohr.com',
    'myworkdayjobs.com',
})

_JOB_PATH_SEGMENTS = frozenset({'careers', 'jobs'})

_FILTER_RE = re.compile(
    r'(unsubscribe|mailto:|/track/|pixel\.|\.gif|\.png|\.jpg'
    r'|/open\?|/click\?|list-unsubscribe)',
    re.I,
)

_URL_RE = re.compile(r'https?://[^\s<>"\')\]]+', re.I)


def _score_url(url: str) -> int:
    """Return 2 for likely job URLs, 1 for others, -1 to exclude."""
    if _FILTER_RE.search(url):
        return -1
    parsed = urlparse(url)
    hostname = (parsed.hostname or '').lower()
    path = parsed.path.lower()
    for domain in _JOB_DOMAINS:
        if domain in hostname:
            return 2
    for seg in _JOB_PATH_SEGMENTS:
        if f'/{seg}/' in path or path.startswith(f'/{seg}'):
            return 2
    return 1


def _extract_links(body: str) -> list[dict]:
    """Extract and rank URLs from raw HTML email body."""
    if not body:
        return []
    seen: set[str] = set()
    results = []
    for m in _URL_RE.finditer(body):
        url = m.group(0).rstrip('.,;)')
        if url in seen:
            continue
        seen.add(url)
        score = _score_url(url)
        if score < 0:
            continue
        start = max(0, m.start() - 60)
        hint = body[start:m.start()].strip().split('\n')[-1].strip()
        results.append({'url': url, 'score': score, 'hint': hint})
    results.sort(key=lambda x: -x['score'])
    return results


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


# ── Interview Prep endpoints ─────────────────────────────────────────────────

@app.get("/api/jobs/{job_id}/research")
def get_research_brief(job_id: int):
    db = _get_db()
    row = db.execute(
        "SELECT job_id, company_brief, ceo_brief, talking_points, tech_brief, "
        "funding_brief, red_flags, accessibility_brief, generated_at "
        "FROM company_research WHERE job_id = ? LIMIT 1",
        (job_id,),
    ).fetchone()
    db.close()
    if not row:
        raise HTTPException(404, "No research found for this job")
    return dict(row)


@app.post("/api/jobs/{job_id}/research/generate")
def generate_research(job_id: int):
    try:
        from scripts.task_runner import submit_task
        task_id, is_new = submit_task(db_path=Path(DB_PATH), task_type="company_research", job_id=job_id)
        return {"task_id": task_id, "is_new": is_new}
    except Exception as e:
        raise HTTPException(500, str(e))


@app.get("/api/jobs/{job_id}/research/task")
def research_task_status(job_id: int):
    db = _get_db()
    row = db.execute(
        "SELECT status, stage, error FROM background_tasks "
        "WHERE task_type = 'company_research' AND job_id = ? "
        "ORDER BY id DESC LIMIT 1",
        (job_id,),
    ).fetchone()
    db.close()
    if not row:
        return {"status": "none", "stage": None, "message": None}
    return {"status": row["status"], "stage": row["stage"], "message": row["error"]}


@app.get("/api/jobs/{job_id}/contacts")
def get_job_contacts(job_id: int):
    db = _get_db()
    rows = db.execute(
        "SELECT id, direction, subject, from_addr, body, received_at "
        "FROM job_contacts WHERE job_id = ? ORDER BY received_at DESC",
        (job_id,),
    ).fetchall()
    db.close()
    return [dict(r) for r in rows]


# ── Survey endpoints ─────────────────────────────────────────────────────────

# Module-level imports so tests can patch dev_api.LLMRouter etc.
from scripts.llm_router import LLMRouter
from scripts.db import insert_survey_response, get_survey_responses

_SURVEY_SYSTEM = (
    "You are a job application advisor helping a candidate answer a culture-fit survey. "
    "The candidate values collaborative teamwork, clear communication, growth, and impact. "
    "Choose answers that present them in the best professional light."
)


def _build_text_prompt(text: str, mode: str) -> str:
    if mode == "quick":
        return (
            "Answer each survey question below. For each, give ONLY the letter of the best "
            "option and a single-sentence reason. Format exactly as:\n"
            "1. B — reason here\n2. A — reason here\n\n"
            f"Survey:\n{text}"
        )
    return (
        "Analyze each survey question below. For each question:\n"
        "- Briefly evaluate each option (1 sentence each)\n"
        "- State your recommendation with reasoning\n\n"
        f"Survey:\n{text}"
    )


def _build_image_prompt(mode: str) -> str:
    if mode == "quick":
        return (
            "This is a screenshot of a culture-fit survey. Read all questions and answer each "
            "with the letter of the best option for a collaborative, growth-oriented candidate. "
            "Format: '1. B — brief reason' on separate lines."
        )
    return (
        "This is a screenshot of a culture-fit survey. For each question, evaluate each option "
        "and recommend the best choice for a collaborative, growth-oriented candidate. "
        "Include a brief breakdown per option and a clear recommendation."
    )


@app.get("/api/vision/health")
def vision_health():
    try:
        r = requests.get("http://localhost:8002/health", timeout=2)
        return {"available": r.status_code == 200}
    except Exception:
        return {"available": False}


class SurveyAnalyzeBody(BaseModel):
    text: Optional[str] = None
    image_b64: Optional[str] = None
    mode: str  # "quick" or "detailed"


@app.post("/api/jobs/{job_id}/survey/analyze")
def survey_analyze(job_id: int, body: SurveyAnalyzeBody):
    try:
        router = LLMRouter()
        if body.image_b64:
            prompt = _build_image_prompt(body.mode)
            output = router.complete(
                prompt,
                images=[body.image_b64],
                fallback_order=router.config.get("vision_fallback_order"),
            )
            source = "screenshot"
        else:
            prompt = _build_text_prompt(body.text or "", body.mode)
            output = router.complete(
                prompt,
                system=_SURVEY_SYSTEM,
                fallback_order=router.config.get("research_fallback_order"),
            )
            source = "text_paste"
        return {"output": output, "source": source}
    except Exception as e:
        raise HTTPException(500, str(e))


class SurveySaveBody(BaseModel):
    survey_name: Optional[str] = None
    mode: str
    source: str
    raw_input: Optional[str] = None
    image_b64: Optional[str] = None
    llm_output: str
    reported_score: Optional[str] = None


@app.post("/api/jobs/{job_id}/survey/responses")
def save_survey_response(job_id: int, body: SurveySaveBody):
    received_at = datetime.now().isoformat()
    image_path = None
    if body.image_b64:
        import base64
        screenshots_dir = Path(DB_PATH).parent / "survey_screenshots" / str(job_id)
        screenshots_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        img_path = screenshots_dir / f"{timestamp}.png"
        img_path.write_bytes(base64.b64decode(body.image_b64))
        image_path = str(img_path)
    row_id = insert_survey_response(
        db_path=Path(DB_PATH),
        job_id=job_id,
        survey_name=body.survey_name,
        received_at=received_at,
        source=body.source,
        raw_input=body.raw_input,
        image_path=image_path,
        mode=body.mode,
        llm_output=body.llm_output,
        reported_score=body.reported_score,
    )
    return {"id": row_id}


@app.get("/api/jobs/{job_id}/survey/responses")
def get_survey_history(job_id: int):
    return get_survey_responses(db_path=Path(DB_PATH), job_id=job_id)


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


# ── POST /api/digest-queue/{id}/extract-links ─────────────────────────────

@app.post("/api/digest-queue/{digest_id}/extract-links")
def extract_digest_links(digest_id: int):
    db = _get_db()
    try:
        row = db.execute(
            """SELECT jc.body
               FROM digest_queue dq
               JOIN job_contacts jc ON jc.id = dq.job_contact_id
               WHERE dq.id = ?""",
            (digest_id,),
        ).fetchone()
    finally:
        db.close()
    if not row:
        raise HTTPException(404, "Digest entry not found")
    return {"links": _extract_links(row["body"] or "")}


# ── POST /api/digest-queue/{id}/queue-jobs ────────────────────────────────

class QueueJobsBody(BaseModel):
    urls: list[str]


@app.post("/api/digest-queue/{digest_id}/queue-jobs")
def queue_digest_jobs(digest_id: int, body: QueueJobsBody):
    if not body.urls:
        raise HTTPException(400, "urls must not be empty")
    db = _get_db()
    try:
        exists = db.execute(
            "SELECT 1 FROM digest_queue WHERE id = ?", (digest_id,)
        ).fetchone()
    finally:
        db.close()
    if not exists:
        raise HTTPException(404, "Digest entry not found")

    try:
        from scripts.db import insert_job
    except ImportError:
        raise HTTPException(500, "scripts.db not available")
    queued = 0
    skipped = 0
    for url in body.urls:
        if not url or not url.startswith(('http://', 'https://')):
            skipped += 1
            continue
        result = insert_job(Path(DB_PATH), {
            'url': url,
            'title': '',
            'company': '',
            'source': 'digest',
            'date_found': datetime.utcnow().isoformat(),
        })
        if result:
            queued += 1
        else:
            skipped += 1
    return {"ok": True, "queued": queued, "skipped": skipped}


# ── DELETE /api/digest-queue/{id} ────────────────────────────────────────

@app.delete("/api/digest-queue/{digest_id}")
def delete_digest_entry(digest_id: int):
    db = _get_db()
    try:
        result = db.execute("DELETE FROM digest_queue WHERE id = ?", (digest_id,))
        db.commit()
        rowcount = result.rowcount
    finally:
        db.close()
    if rowcount == 0:
        raise HTTPException(404, "Digest entry not found")
    return {"ok": True}


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
