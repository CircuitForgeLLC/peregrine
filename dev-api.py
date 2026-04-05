"""
Minimal dev-only FastAPI server for the Vue SPA.
Reads directly from /devl/job-seeker/staging.db.
Run with:
    conda run -n job-seeker uvicorn dev-api:app --port 8600 --reload
"""
import imaplib
import json
import logging
import os
import re
import socket
import sqlite3
import ssl as ssl_mod
import subprocess
import sys
import threading
from contextvars import ContextVar
from datetime import datetime
from pathlib import Path
from typing import Optional, List
from urllib.parse import urlparse

import requests
import yaml
from bs4 import BeautifulSoup
from fastapi import FastAPI, HTTPException, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Allow importing peregrine scripts for cover letter generation
PEREGRINE_ROOT = Path("/Library/Development/CircuitForge/peregrine")
if str(PEREGRINE_ROOT) not in sys.path:
    sys.path.insert(0, str(PEREGRINE_ROOT))

from circuitforge_core.config.settings import load_env as _load_env  # noqa: E402
from scripts.credential_store import get_credential, set_credential, delete_credential  # noqa: E402
from scripts.db_migrate import migrate_db  # noqa: E402

DB_PATH = os.environ.get("STAGING_DB", "/devl/job-seeker/staging.db")

_CLOUD_MODE       = os.environ.get("CLOUD_MODE", "").lower() in ("1", "true")
_CLOUD_DATA_ROOT  = Path(os.environ.get("CLOUD_DATA_ROOT", "/devl/menagerie-data"))
_DIRECTUS_SECRET  = os.environ.get("DIRECTUS_JWT_SECRET", "")

# Per-request DB path — set by cloud_session_middleware; falls back to DB_PATH
_request_db: ContextVar[str | None] = ContextVar("_request_db", default=None)

app = FastAPI(title="Peregrine Dev API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://10.1.10.71:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


_log = logging.getLogger("peregrine.session")

def _resolve_cf_user_id(cookie_str: str) -> str | None:
    """Extract cf_session JWT from Cookie string and return Directus user_id.

    Directus signs with the raw bytes of its JWT_SECRET (which is base64-encoded
    in env). Try the raw string first, then fall back to base64-decoded bytes.
    """
    if not cookie_str:
        _log.debug("_resolve_cf_user_id: empty cookie string")
        return None
    m = re.search(r'(?:^|;)\s*cf_session=([^;]+)', cookie_str)
    if not m:
        _log.debug("_resolve_cf_user_id: no cf_session in cookie: %s…", cookie_str[:80])
        return None
    token = m.group(1).strip()
    import base64
    import jwt  # PyJWT
    secrets_to_try: list[str | bytes] = [_DIRECTUS_SECRET]
    try:
        secrets_to_try.append(base64.b64decode(_DIRECTUS_SECRET))
    except Exception:
        pass
    # Skip exp verification — we use the token for routing only, not auth.
    # Directus manages actual auth; Caddy gates on cookie presence.
    decode_opts = {"verify_exp": False}
    for secret in secrets_to_try:
        try:
            payload = jwt.decode(token, secret, algorithms=["HS256"], options=decode_opts)
            user_id = payload.get("id") or payload.get("sub")
            if user_id:
                _log.debug("_resolve_cf_user_id: resolved user_id=%s", user_id)
                return user_id
        except Exception as exc:
            _log.debug("_resolve_cf_user_id: decode failed (%s): %s", type(exc).__name__, exc)
            continue
    _log.warning("_resolve_cf_user_id: all secrets failed for token prefix %s…", token[:20])
    return None


@app.middleware("http")
async def cloud_session_middleware(request: Request, call_next):
    """In cloud mode, resolve per-user staging.db from the X-CF-Session header."""
    if _CLOUD_MODE and _DIRECTUS_SECRET:
        cookie_header = request.headers.get("X-CF-Session", "")
        user_id = _resolve_cf_user_id(cookie_header)
        if user_id:
            user_db = str(_CLOUD_DATA_ROOT / user_id / "peregrine" / "staging.db")
            token = _request_db.set(user_db)
            try:
                return await call_next(request)
            finally:
                _request_db.reset(token)
    return await call_next(request)


def _get_db():
    path = _request_db.get() or DB_PATH
    db = sqlite3.connect(path)
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
    """Load .env then run pending SQLite migrations."""
    # Load .env before any runtime env reads — safe because startup doesn't run
    # when dev_api is imported by tests (only when uvicorn actually starts).
    _load_env(PEREGRINE_ROOT / ".env")
    migrate_db(Path(DB_PATH))


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


# ── ATS Resume Optimizer endpoints ───────────────────────────────────────────

@app.get("/api/jobs/{job_id}/resume_optimizer")
def get_optimized_resume(job_id: int):
    """Return the current optimized resume and ATS gap report for a job."""
    from scripts.db import get_optimized_resume as _get
    import json
    result = _get(db_path=Path(DB_PATH), job_id=job_id)
    gap_report = result.get("ats_gap_report", "")
    try:
        gap_report_parsed = json.loads(gap_report) if gap_report else []
    except Exception:
        gap_report_parsed = []
    return {
        "optimized_resume": result.get("optimized_resume", ""),
        "ats_gap_report":   gap_report_parsed,
    }


class ResumeOptimizeBody(BaseModel):
    full_rewrite: bool = False


@app.post("/api/jobs/{job_id}/resume_optimizer/generate")
def generate_optimized_resume(job_id: int, body: ResumeOptimizeBody):
    """Queue an ATS resume optimization task for this job.

    full_rewrite=False (default) → free tier: gap report only, no LLM rewrite.
    full_rewrite=True → paid tier: per-section LLM rewrite + hallucination check.
    """
    import json
    try:
        from scripts.task_runner import submit_task
        params = json.dumps({"full_rewrite": body.full_rewrite})
        task_id, is_new = submit_task(
            db_path=Path(DB_PATH),
            task_type="resume_optimize",
            job_id=job_id,
            params=params,
        )
        return {"task_id": task_id, "is_new": is_new}
    except Exception as e:
        raise HTTPException(500, str(e))


@app.get("/api/jobs/{job_id}/resume_optimizer/task")
def resume_optimizer_task_status(job_id: int):
    """Poll the latest resume_optimize task status for this job."""
    db = _get_db()
    row = db.execute(
        "SELECT status, stage, error FROM background_tasks "
        "WHERE task_type = 'resume_optimize' AND job_id = ? "
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
    if body.mode not in ("quick", "detailed"):
        raise HTTPException(400, f"Invalid mode: {body.mode!r}")
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
    if body.mode not in ("quick", "detailed"):
        raise HTTPException(400, f"Invalid mode: {body.mode!r}")
    received_at = datetime.now().isoformat()
    image_path = None
    if body.image_b64:
        try:
            import base64
            screenshots_dir = Path(DB_PATH).parent / "survey_screenshots" / str(job_id)
            screenshots_dir.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            img_path = screenshots_dir / f"{timestamp}.png"
            img_path.write_bytes(base64.b64decode(body.image_b64))
            image_path = str(img_path)
        except Exception:
            raise HTTPException(400, "Invalid image data")
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


# ── Application Q&A endpoints ─────────────────────────────────────────────────

def _ensure_qa_column(db) -> None:
    """Add application_qa TEXT column to jobs if not present (idempotent)."""
    try:
        db.execute("ALTER TABLE jobs ADD COLUMN application_qa TEXT")
        db.commit()
    except Exception:
        pass  # Column already exists


class QAItem(BaseModel):
    id: str
    question: str
    answer: str


class QAPayload(BaseModel):
    items: List[QAItem]


class QASuggestPayload(BaseModel):
    question: str


@app.get("/api/jobs/{job_id}/qa")
def get_qa(job_id: int):
    db = _get_db()
    _ensure_qa_column(db)
    row = db.execute("SELECT application_qa FROM jobs WHERE id = ?", (job_id,)).fetchone()
    db.close()
    if not row:
        raise HTTPException(404, "Job not found")
    try:
        items = json.loads(row["application_qa"] or "[]")
    except Exception:
        items = []
    return {"items": items}


@app.patch("/api/jobs/{job_id}/qa")
def save_qa(job_id: int, payload: QAPayload):
    db = _get_db()
    _ensure_qa_column(db)
    row = db.execute("SELECT id FROM jobs WHERE id = ?", (job_id,)).fetchone()
    if not row:
        db.close()
        raise HTTPException(404, "Job not found")
    db.execute(
        "UPDATE jobs SET application_qa = ? WHERE id = ?",
        (json.dumps([item.model_dump() for item in payload.items]), job_id),
    )
    db.commit()
    db.close()
    return {"ok": True}


@app.post("/api/jobs/{job_id}/qa/suggest")
def suggest_qa_answer(job_id: int, payload: QASuggestPayload):
    """Synchronously generate an LLM answer for an application Q&A question."""
    db = _get_db()
    job_row = db.execute(
        "SELECT title, company, description FROM jobs WHERE id = ?", (job_id,)
    ).fetchone()
    db.close()
    if not job_row:
        raise HTTPException(404, "Job not found")

    # Load resume summary for context
    resume_context = ""
    try:
        resume_path = _resume_path()
        if resume_path.exists():
            with open(resume_path) as f:
                resume_data = yaml.safe_load(f) or {}
            parts = []
            if resume_data.get("name"):
                parts.append(f"Candidate: {resume_data['name']}")
            if resume_data.get("skills"):
                parts.append(f"Skills: {', '.join(resume_data['skills'][:20])}")
            if resume_data.get("experience"):
                exp = resume_data["experience"]
                if isinstance(exp, list) and exp:
                    titles = [e.get("title", "") for e in exp[:3] if e.get("title")]
                    if titles:
                        parts.append(f"Recent roles: {', '.join(titles)}")
            if resume_data.get("career_summary"):
                parts.append(f"Summary: {resume_data['career_summary'][:400]}")
            resume_context = "\n".join(parts)
    except Exception:
        pass

    prompt = (
        f"You are helping a job applicant answer an application question.\n\n"
        f"Job: {job_row['title']} at {job_row['company']}\n"
        f"Job description excerpt:\n{(job_row['description'] or '')[:800]}\n\n"
        f"Candidate background:\n{resume_context or 'Not provided'}\n\n"
        f"Application question: {payload.question}\n\n"
        "Write a concise, professional answer (2–4 sentences) in first person. "
        "Be specific and genuine. Do not use hollow filler phrases."
    )

    try:
        from scripts.llm_router import LLMRouter
        router = LLMRouter()
        answer = router.complete(prompt)
        return {"answer": answer.strip()}
    except Exception as e:
        raise HTTPException(500, f"LLM generation failed: {e}")


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


# ── Task management routes ─────────────────────────────────────────────────────

def _db_path() -> Path:
    """Return the effective staging.db path (cloud-aware)."""
    return Path(_request_db.get() or DB_PATH)


@app.get("/api/tasks")
def list_active_tasks():
    from scripts.db import get_active_tasks
    return get_active_tasks(_db_path())


@app.delete("/api/tasks/{task_id}")
def cancel_task_by_id(task_id: int):
    from scripts.db import cancel_task
    ok = cancel_task(_db_path(), task_id)
    return {"ok": ok}


@app.post("/api/tasks/kill")
def kill_stuck():
    from scripts.db import kill_stuck_tasks
    killed = kill_stuck_tasks(_db_path())
    return {"killed": killed}


@app.post("/api/tasks/discovery", status_code=202)
def trigger_discovery():
    from scripts.task_runner import submit_task
    task_id, is_new = submit_task(_db_path(), "discovery", 0)
    return {"task_id": task_id, "is_new": is_new}


@app.post("/api/tasks/email-sync", status_code=202)
def trigger_email_sync_task():
    from scripts.task_runner import submit_task
    task_id, is_new = submit_task(_db_path(), "email_sync", 0)
    return {"task_id": task_id, "is_new": is_new}


@app.post("/api/tasks/enrich", status_code=202)
def trigger_enrich_task():
    from scripts.task_runner import submit_task
    task_id, is_new = submit_task(_db_path(), "enrich_descriptions", 0)
    return {"task_id": task_id, "is_new": is_new}


@app.post("/api/tasks/score")
def trigger_score():
    try:
        result = subprocess.run(
            [sys.executable, "scripts/match.py"],
            capture_output=True, text=True, cwd=str(PEREGRINE_ROOT),
        )
        if result.returncode == 0:
            return {"ok": True, "output": result.stdout}
        raise HTTPException(status_code=500, detail=result.stderr)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/tasks/sync")
def trigger_notion_sync():
    try:
        from scripts.sync import sync_to_notion
        count = sync_to_notion(_db_path())
        return {"ok": True, "count": count}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Bulk job actions ───────────────────────────────────────────────────────────

class BulkArchiveBody(BaseModel):
    statuses: List[str]


@app.post("/api/jobs/archive")
def bulk_archive_jobs(body: BulkArchiveBody):
    from scripts.db import archive_jobs
    n = archive_jobs(_db_path(), statuses=body.statuses)
    return {"archived": n}


class BulkPurgeBody(BaseModel):
    statuses: Optional[List[str]] = None
    target: Optional[str] = None  # "email", "non_remote", "rescrape"


@app.post("/api/jobs/purge")
def bulk_purge_jobs(body: BulkPurgeBody):
    from scripts.db import purge_jobs, purge_email_data, purge_non_remote
    if body.target == "email":
        contacts, jobs = purge_email_data(_db_path())
        return {"ok": True, "contacts": contacts, "jobs": jobs}
    if body.target == "non_remote":
        n = purge_non_remote(_db_path())
        return {"ok": True, "deleted": n}
    if body.target == "rescrape":
        purge_jobs(_db_path(), statuses=["pending", "approved", "rejected"])
        from scripts.task_runner import submit_task
        submit_task(_db_path(), "discovery", 0)
        return {"ok": True}
    statuses = body.statuses or ["pending", "rejected"]
    n = purge_jobs(_db_path(), statuses=statuses)
    return {"ok": True, "deleted": n}


class AddJobsBody(BaseModel):
    urls: List[str]


@app.post("/api/jobs/add", status_code=202)
def add_jobs_by_url(body: AddJobsBody):
    try:
        from datetime import datetime as _dt
        from scripts.scrape_url import canonicalize_url
        from scripts.db import get_existing_urls, insert_job
        from scripts.task_runner import submit_task
        db_path = _db_path()
        existing = get_existing_urls(db_path)
        queued = 0
        for raw_url in body.urls:
            url = canonicalize_url(raw_url.strip())
            if not url.startswith("http") or url in existing:
                continue
            job_id = insert_job(db_path, {
                "title": "Importing...", "company": "", "url": url,
                "source": "manual", "location": "", "description": "",
                "date_found": _dt.now().isoformat()[:10],
            })
            if job_id:
                submit_task(db_path, "scrape_url", job_id)
                queued += 1
        return {"queued": queued}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/jobs/upload-csv", status_code=202)
async def upload_jobs_csv(file: UploadFile):
    try:
        import csv as _csv
        import io as _io
        from datetime import datetime as _dt
        from scripts.scrape_url import canonicalize_url
        from scripts.db import get_existing_urls, insert_job
        from scripts.task_runner import submit_task
        content = await file.read()
        reader = _csv.DictReader(_io.StringIO(content.decode("utf-8", errors="replace")))
        urls: list[str] = []
        for row in reader:
            for val in row.values():
                if val and val.strip().startswith("http"):
                    urls.append(val.strip())
                    break
        db_path = _db_path()
        existing = get_existing_urls(db_path)
        queued = 0
        for raw_url in urls:
            url = canonicalize_url(raw_url)
            if not url.startswith("http") or url in existing:
                continue
            job_id = insert_job(db_path, {
                "title": "Importing...", "company": "", "url": url,
                "source": "manual", "location": "", "description": "",
                "date_found": _dt.now().isoformat()[:10],
            })
            if job_id:
                submit_task(db_path, "scrape_url", job_id)
                queued += 1
        return {"queued": queued, "total": len(urls)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Setup banners ──────────────────────────────────────────────────────────────

_SETUP_BANNERS = [
    {"key": "connect_cloud",       "text": "Connect a cloud service for resume/cover letter storage",  "link": "/settings?tab=integrations"},
    {"key": "setup_email",         "text": "Set up email sync to catch recruiter outreach",             "link": "/settings?tab=email"},
    {"key": "setup_email_labels",  "text": "Set up email label filters for auto-classification",        "link": "/settings?tab=email"},
    {"key": "tune_mission",        "text": "Tune your mission preferences for better cover letters",     "link": "/settings?tab=profile"},
    {"key": "configure_keywords",  "text": "Configure keywords and blocklist for smarter search",       "link": "/settings?tab=search"},
    {"key": "upload_corpus",       "text": "Upload your cover letter corpus for voice fine-tuning",     "link": "/settings?tab=fine-tune"},
    {"key": "configure_linkedin",  "text": "Configure LinkedIn Easy Apply automation",                  "link": "/settings?tab=integrations"},
    {"key": "setup_searxng",       "text": "Set up company research with SearXNG",                     "link": "/settings?tab=system"},
    {"key": "target_companies",    "text": "Build a target company list for focused outreach",          "link": "/settings?tab=search"},
    {"key": "setup_notifications", "text": "Set up notifications for stage changes",                   "link": "/settings?tab=integrations"},
    {"key": "tune_model",          "text": "Tune a custom cover letter model on your writing",          "link": "/settings?tab=fine-tune"},
    {"key": "review_training",     "text": "Review and curate training data for model tuning",         "link": "/settings?tab=fine-tune"},
    {"key": "setup_calendar",      "text": "Set up calendar sync to track interview dates",            "link": "/settings?tab=integrations"},
]


@app.get("/api/config/setup-banners")
def get_setup_banners():
    try:
        cfg = _load_user_config()
        if not cfg.get("wizard_complete"):
            return []
        dismissed = set(cfg.get("dismissed_banners", []))
        return [b for b in _SETUP_BANNERS if b["key"] not in dismissed]
    except Exception:
        return []


@app.post("/api/config/setup-banners/{key}/dismiss")
def dismiss_setup_banner(key: str):
    try:
        cfg = _load_user_config()
        dismissed = cfg.get("dismissed_banners", [])
        if key not in dismissed:
            dismissed.append(key)
            cfg["dismissed_banners"] = dismissed
            _save_user_config(cfg)
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


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


# ── GET /api/config/app ───────────────────────────────────────────────────────

@app.get("/api/config/app")
def get_app_config():
    import os
    profile = os.environ.get("INFERENCE_PROFILE", "cpu")
    valid_profiles = {"remote", "cpu", "single-gpu", "dual-gpu"}
    valid_tiers = {"free", "paid", "premium", "ultra"}
    raw_tier = os.environ.get("APP_TIER", "free")

    # Cloud users always bypass the wizard — they configure through Settings
    is_cloud = os.environ.get("CLOUD_MODE", "").lower() in ("1", "true")
    if is_cloud:
        wizard_complete = True
    else:
        try:
            cfg = load_user_profile(_user_yaml_path())
            wizard_complete = bool(cfg.get("wizard_complete", False))
        except Exception:
            wizard_complete = False

    return {
        "isCloud": os.environ.get("CLOUD_MODE", "").lower() in ("1", "true"),
        "isDemo": os.environ.get("DEMO_MODE", "").lower() in ("1", "true", "yes"),
        "isDevMode": os.environ.get("DEV_MODE", "").lower() in ("1", "true"),
        "tier": raw_tier if raw_tier in valid_tiers else "free",
        "contractedClient": os.environ.get("CONTRACTED_CLIENT", "").lower() in ("1", "true"),
        "inferenceProfile": profile if profile in valid_profiles else "cpu",
        "wizardComplete": wizard_complete,
    }


# ── GET /api/config/user ──────────────────────────────────────────────────────

@app.get("/api/config/user")
def config_user():
    # Try to read name from user.yaml if present
    try:
        import yaml
        cfg_path = _user_yaml_path()
        with open(cfg_path) as f:
            cfg = yaml.safe_load(f)
        return {"name": cfg.get("name", "")}
    except Exception:
        return {"name": ""}


# ── Settings: My Profile endpoints ───────────────────────────────────────────

from scripts.user_profile import load_user_profile, save_user_profile


def _user_yaml_path() -> str:
    """Resolve user.yaml path relative to the active staging.db.

    In cloud mode the ContextVar holds the per-user db path; elsewhere
    falls back to STAGING_DB env var.  Never crosses user boundaries.
    """
    db = _request_db.get() or os.environ.get("STAGING_DB", "/devl/peregrine/staging.db")
    return os.path.join(os.path.dirname(db), "config", "user.yaml")


def _mission_dict_to_list(prefs: object) -> list:
    """Convert {industry: note} dict to [{industry, note}] list for the SPA."""
    if isinstance(prefs, list):
        return prefs
    if isinstance(prefs, dict):
        return [{"industry": k, "note": v or ""} for k, v in prefs.items()]
    return []


def _mission_list_to_dict(prefs: list) -> dict:
    """Convert [{industry, note}] list from the SPA back to {industry: note} dict."""
    result = {}
    for item in prefs:
        if isinstance(item, dict):
            result[item.get("industry", "")] = item.get("note", "")
    return result


@app.get("/api/settings/profile")
def get_profile():
    try:
        cfg = load_user_profile(_user_yaml_path())
        return {
            "name":               cfg.get("name", ""),
            "email":              cfg.get("email", ""),
            "phone":              cfg.get("phone", ""),
            "linkedin_url":       cfg.get("linkedin", ""),
            "career_summary":     cfg.get("career_summary", ""),
            "candidate_voice":    cfg.get("candidate_voice", ""),
            "inference_profile":  cfg.get("inference_profile", "cpu"),
            "mission_preferences": _mission_dict_to_list(cfg.get("mission_preferences", {})),
            "nda_companies":      cfg.get("nda_companies", []),
            "accessibility_focus": cfg.get("candidate_accessibility_focus", False),
            "lgbtq_focus":        cfg.get("candidate_lgbtq_focus", False),
        }
    except Exception as e:
        raise HTTPException(500, f"Could not read profile: {e}")


class MissionPrefModel(BaseModel):
    industry: str
    note: str = ""


class UserProfilePayload(BaseModel):
    name: str = ""
    email: str = ""
    phone: str = ""
    linkedin_url: str = ""
    career_summary: str = ""
    candidate_voice: str = ""
    inference_profile: str = "cpu"
    mission_preferences: List[MissionPrefModel] = []
    nda_companies: List[str] = []
    accessibility_focus: bool = False
    lgbtq_focus: bool = False


class IdentitySyncPayload(BaseModel):
    name: str = ""
    email: str = ""
    phone: str = ""
    linkedin_url: str = ""

_VALID_THEMES = frozenset({"auto", "light", "dark", "solarized-dark", "solarized-light", "colorblind"})

class ThemePayload(BaseModel):
    theme: str

@app.post("/api/settings/theme")
def set_theme(payload: ThemePayload):
    """Persist the user's chosen theme to user.yaml."""
    if payload.theme not in _VALID_THEMES:
        raise HTTPException(status_code=400, detail=f"Invalid theme: {payload.theme}")
    try:
        data = load_user_profile(_user_yaml_path())
        data["theme"] = payload.theme
        save_user_profile(_user_yaml_path(), data)
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class UIPrefPayload(BaseModel):
    preference: str  # "streamlit" | "vue"

@app.post("/api/settings/ui-preference")
def set_ui_preference(payload: UIPrefPayload):
    """Persist UI preference to user.yaml so Streamlit doesn't re-set the cookie."""
    if payload.preference not in ("streamlit", "vue"):
        raise HTTPException(status_code=400, detail="preference must be 'streamlit' or 'vue'")
    try:
        data = load_user_profile(_user_yaml_path())
        data["ui_preference"] = payload.preference
        save_user_profile(_user_yaml_path(), data)
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/settings/resume/sync-identity")
def sync_identity(payload: IdentitySyncPayload):
    """Sync identity fields from profile store back to user.yaml."""
    try:
        data = load_user_profile(_user_yaml_path())
        data["name"] = payload.name
        data["email"] = payload.email
        data["phone"] = payload.phone
        data["linkedin"] = payload.linkedin_url  # yaml key is 'linkedin', not 'linkedin_url'
        save_user_profile(_user_yaml_path(), data)
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/api/settings/profile")
def save_profile(payload: UserProfilePayload):
    try:
        yaml_path = _user_yaml_path()
        cfg = load_user_profile(yaml_path)
        cfg["name"] = payload.name
        cfg["email"] = payload.email
        cfg["phone"] = payload.phone
        cfg["linkedin"] = payload.linkedin_url
        cfg["career_summary"] = payload.career_summary
        cfg["candidate_voice"] = payload.candidate_voice
        cfg["inference_profile"] = payload.inference_profile
        cfg["mission_preferences"] = _mission_list_to_dict(
            [m.model_dump() for m in payload.mission_preferences]
        )
        cfg["nda_companies"] = payload.nda_companies
        cfg["candidate_accessibility_focus"] = payload.accessibility_focus
        cfg["candidate_lgbtq_focus"] = payload.lgbtq_focus
        save_user_profile(yaml_path, cfg)
        return {"ok": True}
    except Exception as e:
        raise HTTPException(500, f"Could not save profile: {e}")


# ── Settings: My Profile — LLM generation endpoints ─────────────────────────

def _resume_context_snippet() -> str:
    """Load a concise resume snippet for use as LLM generation context."""
    try:
        rp = _resume_path()
        if not rp.exists():
            return ""
        with open(rp) as f:
            resume_data = yaml.safe_load(f) or {}
        parts: list[str] = []
        if resume_data.get("name"):
            parts.append(f"Candidate: {resume_data['name']}")
        if resume_data.get("skills"):
            parts.append(f"Skills: {', '.join(resume_data['skills'][:20])}")
        if resume_data.get("experience"):
            exp = resume_data["experience"]
            if isinstance(exp, list) and exp:
                titles = [e.get("title", "") for e in exp[:3] if e.get("title")]
                if titles:
                    parts.append(f"Recent roles: {', '.join(titles)}")
        return "\n".join(parts)
    except Exception:
        return ""


@app.post("/api/settings/profile/generate-summary")
def generate_career_summary():
    """LLM-generate a career summary from the candidate's resume profile."""
    context = _resume_context_snippet()
    if not context:
        raise HTTPException(400, "Resume profile is empty — add experience and skills first")
    prompt = (
        "You are a professional resume writer.\n\n"
        f"Candidate background:\n{context}\n\n"
        "Write a 2–3 sentence professional career summary in first person. "
        "Be specific, highlight key strengths, and avoid hollow filler phrases like "
        "'results-driven' or 'passionate self-starter'."
    )
    try:
        from scripts.llm_router import LLMRouter
        summary = LLMRouter().complete(prompt)
        return {"summary": summary.strip()}
    except Exception as e:
        raise HTTPException(500, f"LLM generation failed: {e}")


@app.post("/api/settings/profile/generate-missions")
def generate_mission_preferences():
    """LLM-generate 3 mission/industry preferences from the candidate's resume."""
    context = _resume_context_snippet()
    prompt = (
        "You are helping a job seeker identify mission-aligned industries they would enjoy working in.\n\n"
        + (f"Candidate background:\n{context}\n\n" if context else "")
        + "Suggest 3 mission-aligned industries or causes the candidate might care about "
        "(e.g. animal welfare, education, accessibility, climate tech, healthcare). "
        "Return a JSON array with exactly 3 objects, each with 'tag' (slug, no spaces), "
        "'label' (human-readable name), and 'note' (one sentence on why it fits). "
        "Only output the JSON array, no other text."
    )
    try:
        from scripts.llm_router import LLMRouter
        import json as _json
        raw = LLMRouter().complete(prompt)
        # Extract JSON array from the response
        start = raw.find("[")
        end = raw.rfind("]") + 1
        if start == -1 or end == 0:
            raise ValueError("LLM did not return a JSON array")
        items = _json.loads(raw[start:end])
        # Normalise to {industry, note} — LLM may return {tag, label, note}
        missions = [
            {"industry": m.get("label") or m.get("tag") or str(m), "note": m.get("note", "")}
            for m in items if isinstance(m, dict)
        ]
        return {"mission_preferences": missions}
    except Exception as e:
        raise HTTPException(500, f"LLM generation failed: {e}")


@app.post("/api/settings/profile/generate-voice")
def generate_candidate_voice():
    """LLM-generate a candidate voice/writing-style note from the resume profile."""
    context = _resume_context_snippet()
    if not context:
        raise HTTPException(400, "Resume profile is empty — add experience and skills first")
    prompt = (
        "You are a professional writing coach helping a job seeker articulate their communication style.\n\n"
        f"Candidate background:\n{context}\n\n"
        "Write a 1–2 sentence note describing the candidate's professional voice and writing style "
        "for use in cover letter generation. This should capture tone (e.g. direct, warm, precise), "
        "values that come through in their writing, and any standout personality. "
        "Write it in third person as a style directive (e.g. 'Writes in a clear, direct tone...')."
    )
    try:
        from scripts.llm_router import LLMRouter
        voice = LLMRouter().complete(prompt)
        return {"voice": voice.strip()}
    except Exception as e:
        raise HTTPException(500, f"LLM generation failed: {e}")


# ── Settings: Resume Profile endpoints ───────────────────────────────────────

class WorkEntry(BaseModel):
    title: str = ""; company: str = ""; period: str = ""; location: str = ""
    industry: str = ""; responsibilities: str = ""; skills: List[str] = []

class ResumePayload(BaseModel):
    name: str = ""; email: str = ""; phone: str = ""; linkedin_url: str = ""
    surname: str = ""; address: str = ""; city: str = ""; zip_code: str = ""; date_of_birth: str = ""
    experience: List[WorkEntry] = []
    salary_min: int = 0; salary_max: int = 0; notice_period: str = ""
    remote: bool = False; relocation: bool = False
    assessment: bool = False; background_check: bool = False
    gender: str = ""; pronouns: str = ""; ethnicity: str = ""
    veteran_status: str = ""; disability: str = ""
    skills: List[str] = []; domains: List[str] = []; keywords: List[str] = []

def _config_dir() -> Path:
    """Resolve per-user config directory. Always co-located with user.yaml."""
    return Path(_user_yaml_path()).parent

def _resume_path() -> Path:
    """Resolve plain_text_resume.yaml co-located with user.yaml (user-isolated)."""
    return _config_dir() / "plain_text_resume.yaml"

def _search_prefs_path() -> Path:
    return _config_dir() / "search_profiles.yaml"

def _license_path() -> Path:
    return _config_dir() / "license.yaml"

def _tokens_path() -> Path:
    return _config_dir() / "tokens.yaml"

def _normalize_experience(raw: list) -> list:
    """Normalize AIHawk-style experience entries to the Vue WorkEntry schema.

    Parser / AIHawk stores: bullets (list[str]), start_date, end_date
    Vue WorkEntry expects:   responsibilities (str), period (str)
    """
    out = []
    for e in raw:
        if not isinstance(e, dict):
            continue
        entry = dict(e)
        # bullets → responsibilities
        if "responsibilities" not in entry or not entry["responsibilities"]:
            bullets = entry.pop("bullets", None) or []
            if isinstance(bullets, list):
                entry["responsibilities"] = "\n".join(b for b in bullets if b)
            elif isinstance(bullets, str):
                entry["responsibilities"] = bullets
        else:
            entry.pop("bullets", None)
        # start_date + end_date → period
        if "period" not in entry or not entry["period"]:
            start = entry.pop("start_date", "") or ""
            end = entry.pop("end_date", "") or ""
            entry["period"] = f"{start} – {end}".strip(" –") if (start or end) else ""
        else:
            entry.pop("start_date", None)
            entry.pop("end_date", None)
        out.append(entry)
    return out


@app.get("/api/settings/resume")
def get_resume():
    try:
        resume_path = _resume_path()
        if not resume_path.exists():
            return {"exists": False}
        with open(resume_path) as f:
            data = yaml.safe_load(f) or {}
        data["exists"] = True
        if "experience" in data and isinstance(data["experience"], list):
            data["experience"] = _normalize_experience(data["experience"])
        return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/api/settings/resume")
def save_resume(payload: ResumePayload):
    try:
        resume_path = _resume_path()
        resume_path.parent.mkdir(parents=True, exist_ok=True)
        with open(resume_path, "w") as f:
            yaml.dump(payload.model_dump(), f, allow_unicode=True, default_flow_style=False)
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/settings/resume/blank")
def create_blank_resume():
    try:
        resume_path = _resume_path()
        resume_path.parent.mkdir(parents=True, exist_ok=True)
        if not resume_path.exists():
            with open(resume_path, "w") as f:
                yaml.dump({}, f)
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/settings/resume/upload")
async def upload_resume(file: UploadFile):
    try:
        from scripts.resume_parser import (
            extract_text_from_pdf,
            extract_text_from_docx,
            extract_text_from_odt,
            structure_resume,
        )
        suffix = Path(file.filename).suffix.lower()
        file_bytes = await file.read()

        if suffix == ".pdf":
            raw_text = extract_text_from_pdf(file_bytes)
        elif suffix == ".odt":
            raw_text = extract_text_from_odt(file_bytes)
        else:
            raw_text = extract_text_from_docx(file_bytes)

        result, err = structure_resume(raw_text)
        if err and not result:
            return {"ok": False, "error": err}
        # Persist parsed data so store.load() reads the updated file
        resume_path = _resume_path()
        resume_path.parent.mkdir(parents=True, exist_ok=True)
        with open(resume_path, "w") as f:
            yaml.dump(result, f, allow_unicode=True, default_flow_style=False)
        result["exists"] = True
        return {"ok": True, "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Settings: Search Preferences endpoints ────────────────────────────────────

class SearchPrefsPayload(BaseModel):
    remote_preference: str = "both"
    job_titles: List[str] = []
    locations: List[str] = []
    exclude_keywords: List[str] = []
    job_boards: List[dict] = []
    custom_board_urls: List[str] = []
    blocklist_companies: List[str] = []
    blocklist_industries: List[str] = []
    blocklist_locations: List[str] = []

@app.get("/api/settings/search")
def get_search_prefs():
    try:
        p = _search_prefs_path()
        if not p.exists():
            return {}
        with open(p) as f:
            data = yaml.safe_load(f) or {}
        return data.get("default", {})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/api/settings/search")
def save_search_prefs(payload: SearchPrefsPayload):
    try:
        p = _search_prefs_path()
        data = {}
        if p.exists():
            with open(p) as f:
                data = yaml.safe_load(f) or {}
        data["default"] = payload.model_dump()
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w") as f:
            yaml.dump(data, f, allow_unicode=True, default_flow_style=False)
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class SearchSuggestPayload(BaseModel):
    type: str          # "titles" | "locations" | "exclude_keywords"
    current: List[str] = []

@app.post("/api/settings/search/suggest")
def suggest_search(payload: SearchSuggestPayload):
    """LLM-generate suggestions for job titles, locations, or exclude keywords."""
    context = _resume_context_snippet()
    current_str = ", ".join(payload.current) if payload.current else "none"

    if payload.type == "titles":
        prompt = (
            "You are a career advisor helping a job seeker identify relevant job titles.\n\n"
            + (f"Candidate background:\n{context}\n\n" if context else "")
            + f"Current job titles they're searching for: {current_str}\n\n"
            "Suggest 5 additional relevant job titles they may have missed. "
            "Return only a JSON array of strings, no other text. "
            "Example: [\"Senior Software Engineer\", \"Staff Engineer\"]"
        )
    elif payload.type == "locations":
        prompt = (
            "You are a career advisor helping a job seeker identify relevant job markets.\n\n"
            + (f"Candidate background:\n{context}\n\n" if context else "")
            + f"Current locations they're searching in: {current_str}\n\n"
            "Suggest 5 relevant locations or remote options they may have missed. "
            "Include 'Remote' if not already listed. "
            "Return only a JSON array of strings, no other text."
        )
    elif payload.type == "exclude_keywords":
        prompt = (
            "You are a job search assistant helping a job seeker filter out irrelevant listings.\n\n"
            + (f"Candidate background:\n{context}\n\n" if context else "")
            + f"Keywords they already exclude: {current_str}\n\n"
            "Suggest 5–8 keywords or phrases they should add to their exclude list to avoid "
            "irrelevant postings (e.g. management roles they don't want, clearance requirements, "
            "technologies they don't work with). "
            "Return only a JSON array of strings, no other text."
        )
    else:
        raise HTTPException(400, f"Unknown suggestion type: {payload.type}")

    try:
        import json as _json
        from scripts.llm_router import LLMRouter
        raw = LLMRouter().complete(prompt)
        start = raw.find("[")
        end   = raw.rfind("]") + 1
        if start == -1 or end == 0:
            return {"suggestions": []}
        suggestions = _json.loads(raw[start:end])
        return {"suggestions": [str(s) for s in suggestions if s]}
    except Exception as e:
        raise HTTPException(500, f"LLM generation failed: {e}")


# ── Settings: System — LLM Backends + BYOK endpoints ─────────────────────────

class ByokAckPayload(BaseModel):
    backends: List[str] = []

class LlmConfigPayload(BaseModel):
    backends: List[dict] = []

LLM_CONFIG_PATH = Path("config/llm.yaml")

@app.get("/api/settings/system/llm")
def get_llm_config():
    try:
        user = load_user_profile(_user_yaml_path())
        backends = []
        if LLM_CONFIG_PATH.exists():
            with open(LLM_CONFIG_PATH) as f:
                data = yaml.safe_load(f) or {}
            backends = data.get("backends", [])
        return {"backends": backends, "byok_acknowledged": user.get("byok_acknowledged_backends", [])}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/api/settings/system/llm")
def save_llm_config(payload: LlmConfigPayload):
    try:
        data = {}
        if LLM_CONFIG_PATH.exists():
            with open(LLM_CONFIG_PATH) as f:
                data = yaml.safe_load(f) or {}
        data["backends"] = payload.backends
        LLM_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(LLM_CONFIG_PATH, "w") as f:
            yaml.dump(data, f, allow_unicode=True, default_flow_style=False)
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/settings/system/llm/byok-ack")
def byok_ack(payload: ByokAckPayload):
    try:
        user = load_user_profile(_user_yaml_path())
        existing = user.get("byok_acknowledged_backends", [])
        user["byok_acknowledged_backends"] = list(set(existing + payload.backends))
        save_user_profile(_user_yaml_path(), user)
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Settings: System — Services ───────────────────────────────────────────────

SERVICES_REGISTRY = [
    {"name": "ollama", "port": 11434, "compose_service": "ollama", "note": "LLM inference", "profiles": ["cpu","single-gpu","dual-gpu"]},
    {"name": "vllm", "port": 8000, "compose_service": "vllm", "note": "vLLM server", "profiles": ["single-gpu","dual-gpu"]},
    {"name": "vision", "port": 8002, "compose_service": "vision", "note": "Moondream2 vision", "profiles": ["single-gpu","dual-gpu"]},
    {"name": "searxng", "port": 8888, "compose_service": "searxng", "note": "Search engine", "profiles": ["cpu","remote","single-gpu","dual-gpu"]},
]


def _port_open(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


@app.get("/api/settings/system/services")
def get_services():
    try:
        profile = os.environ.get("INFERENCE_PROFILE", "cpu")
        result = []
        for svc in SERVICES_REGISTRY:
            if profile not in svc["profiles"]:
                continue
            result.append({"name": svc["name"], "port": svc["port"],
                           "running": _port_open(svc["port"]), "note": svc["note"]})
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/settings/system/services/{name}/start")
def start_service(name: str):
    try:
        svc = next((s for s in SERVICES_REGISTRY if s["name"] == name), None)
        if not svc:
            raise HTTPException(404, "Unknown service")
        r = subprocess.run(["docker", "compose", "up", "-d", svc["compose_service"]],
                          capture_output=True, text=True)
        return {"ok": r.returncode == 0, "output": r.stdout + r.stderr}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/settings/system/services/{name}/stop")
def stop_service(name: str):
    try:
        svc = next((s for s in SERVICES_REGISTRY if s["name"] == name), None)
        if not svc:
            raise HTTPException(404, "Unknown service")
        r = subprocess.run(["docker", "compose", "stop", svc["compose_service"]],
                          capture_output=True, text=True)
        return {"ok": r.returncode == 0, "output": r.stdout + r.stderr}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Settings: System — Email ──────────────────────────────────────────────────

# EMAIL_PATH is resolved per-request via _config_dir()
EMAIL_CRED_SERVICE = "peregrine"
EMAIL_CRED_KEY = "imap_password"

# Non-secret fields stored in yaml
EMAIL_YAML_FIELDS = ("host", "port", "ssl", "username", "sent_folder", "lookback_days")


@app.get("/api/settings/system/email")
def get_email_config():
    try:
        config = {}
        ep = _config_dir() / "email.yaml"
        if ep.exists():
            with open(ep) as f:
                config = yaml.safe_load(f) or {}
        # Never return the password — only indicate whether it's set
        password = get_credential(EMAIL_CRED_SERVICE, EMAIL_CRED_KEY)
        config["password_set"] = bool(password)
        config.pop("password", None)  # strip if somehow in yaml
        return config
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/api/settings/system/email")
def save_email_config(payload: dict):
    try:
        ep = _config_dir() / "email.yaml"
        ep.parent.mkdir(parents=True, exist_ok=True)
        # Extract password before writing yaml; discard the sentinel boolean regardless
        password = payload.pop("password", None)
        payload.pop("password_set", None)  # always discard — boolean sentinel, not a secret
        if password and isinstance(password, str):
            set_credential(EMAIL_CRED_SERVICE, EMAIL_CRED_KEY, password)
        # Write non-secret fields to yaml (chmod 600 still, contains username)
        safe_config = {k: v for k, v in payload.items() if k in EMAIL_YAML_FIELDS}
        fd = os.open(str(ep), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            yaml.dump(safe_config, f, allow_unicode=True, default_flow_style=False)
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/settings/system/email/test")
def test_email(payload: dict):
    try:
        # Always use the stored credential — never accept a password in the test request body
        password = get_credential(EMAIL_CRED_SERVICE, EMAIL_CRED_KEY)
        host = payload.get("host", "")
        port = int(payload.get("port", 993))
        use_ssl = payload.get("ssl", True)
        username = payload.get("username", "")
        if not all([host, username, password]):
            return {"ok": False, "error": "Missing host, username, or password"}
        if use_ssl:
            ctx = ssl_mod.create_default_context()
            conn = imaplib.IMAP4_SSL(host, port, ssl_context=ctx)
        else:
            conn = imaplib.IMAP4(host, port)
        conn.login(username, password)
        conn.logout()
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ── Settings: System — Integrations ──────────────────────────────────────────

@app.get("/api/settings/system/integrations")
def get_integrations():
    try:
        from scripts.integrations import REGISTRY
        result = []
        for integration in REGISTRY:
            result.append({
                "id": integration.id,
                "name": integration.name,
                "connected": integration.is_connected(),
                "tier_required": getattr(integration, "tier_required", "free"),
                "fields": [{"key": f["key"], "label": f["label"], "type": f.get("type", "text")}
                           for f in integration.fields()],
            })
        return result
    except ImportError:
        return []  # integrations module not yet implemented
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/settings/system/integrations/{integration_id}/test")
def test_integration(integration_id: str, payload: dict):
    try:
        from scripts.integrations import REGISTRY
        integration = next((i for i in REGISTRY if i.id == integration_id), None)
        if not integration:
            raise HTTPException(404, "Unknown integration")
        ok, error = integration.test(payload)
        return {"ok": ok, "error": error}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/settings/system/integrations/{integration_id}/connect")
def connect_integration(integration_id: str, payload: dict):
    try:
        from scripts.integrations import REGISTRY
        integration = next((i for i in REGISTRY if i.id == integration_id), None)
        if not integration:
            raise HTTPException(404, "Unknown integration")
        ok, error = integration.test(payload)
        if not ok:
            return {"ok": False, "error": error}
        integration.save_credentials(payload)
        return {"ok": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/settings/system/integrations/{integration_id}/disconnect")
def disconnect_integration(integration_id: str):
    try:
        from scripts.integrations import REGISTRY
        integration = next((i for i in REGISTRY if i.id == integration_id), None)
        if not integration:
            raise HTTPException(404, "Unknown integration")
        integration.remove_credentials()
        return {"ok": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Settings: System — File Paths ─────────────────────────────────────────────

@app.get("/api/settings/system/paths")
def get_file_paths():
    try:
        user = load_user_profile(_user_yaml_path())
        return {
            "docs_dir": user.get("docs_dir", ""),
            "data_dir": user.get("data_dir", ""),
            "model_dir": user.get("model_dir", ""),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/api/settings/system/paths")
def save_file_paths(payload: dict):
    try:
        user = load_user_profile(_user_yaml_path())
        for key in ("docs_dir", "data_dir", "model_dir"):
            if key in payload:
                user[key] = payload[key]
        save_user_profile(_user_yaml_path(), user)
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Settings: System — Deployment Config ─────────────────────────────────────

@app.get("/api/settings/system/deploy")
def get_deploy_config():
    try:
        return {
            "base_url_path": os.environ.get("STREAMLIT_SERVER_BASE_URL_PATH", ""),
            "server_host": os.environ.get("STREAMLIT_SERVER_ADDRESS", "0.0.0.0"),
            "server_port": int(os.environ.get("STREAMLIT_SERVER_PORT", "8502")),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/api/settings/system/deploy")
def save_deploy_config(payload: dict):
    # Deployment config changes require restart; just acknowledge
    return {"ok": True, "note": "Restart required to apply changes"}


# ── Settings: Fine-Tune ───────────────────────────────────────────────────────

_TRAINING_JSONL = Path("/Library/Documents/JobSearch/training_data/cover_letters.jsonl")


def _load_training_pairs() -> list[dict]:
    """Load training pairs from the JSONL file. Returns empty list if missing."""
    if not _TRAINING_JSONL.exists():
        return []
    pairs = []
    with open(_TRAINING_JSONL, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    pairs.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return pairs


def _save_training_pairs(pairs: list[dict]) -> None:
    _TRAINING_JSONL.parent.mkdir(parents=True, exist_ok=True)
    with open(_TRAINING_JSONL, "w", encoding="utf-8") as f:
        for p in pairs:
            f.write(json.dumps(p, ensure_ascii=False) + "\n")


@app.get("/api/settings/fine-tune/status")
def finetune_status():
    try:
        pairs_count = len(_load_training_pairs())
        from scripts.task_runner import get_task_status
        task = get_task_status("finetune_extract")
        if task:
            # Prefer the DB task count if available and larger (recent extraction)
            db_count = task.get("result_count", 0) or 0
            pairs_count = max(pairs_count, db_count)
        status = task.get("status", "idle") if task else "idle"
        # Stub quota for self-hosted; cloud overrides via its own middleware
        return {"status": status, "pairs_count": pairs_count, "quota_remaining": None}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/settings/fine-tune/pairs")
def list_training_pairs():
    """Return training pairs with index for display and removal."""
    pairs = _load_training_pairs()
    return {
        "pairs": [
            {"index": i, "instruction": p.get("instruction", ""), "source_file": p.get("source_file", "")}
            for i, p in enumerate(pairs)
        ],
        "total": len(pairs),
    }


@app.delete("/api/settings/fine-tune/pairs/{index}")
def delete_training_pair(index: int):
    """Remove a training pair by index."""
    pairs = _load_training_pairs()
    if index < 0 or index >= len(pairs):
        raise HTTPException(404, "Pair index out of range")
    pairs.pop(index)
    _save_training_pairs(pairs)
    return {"ok": True, "remaining": len(pairs)}


@app.post("/api/settings/fine-tune/extract")
def finetune_extract():
    try:
        from scripts.task_runner import submit_task
        task_id = submit_task(DB_PATH, "finetune_extract", None)
        return {"task_id": str(task_id)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/settings/fine-tune/upload")
async def finetune_upload(files: list[UploadFile]):
    try:
        upload_dir = Path("data/finetune_uploads")
        upload_dir.mkdir(parents=True, exist_ok=True)
        saved = []
        for f in files:
            dest = upload_dir / (f.filename or "upload.bin")
            content = await f.read()
            fd = os.open(str(dest), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "wb") as out:
                out.write(content)
            saved.append(str(dest))
        return {"file_count": len(saved), "paths": saved}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/settings/fine-tune/submit")
def finetune_submit():
    """Trigger prepare_training_data extraction and queue fine-tune background task."""
    try:
        from scripts.task_runner import submit_task
        task_id, is_new = submit_task(Path(DB_PATH), "prepare_training", None)
        return {"job_id": str(task_id), "is_new": is_new}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/settings/fine-tune/local-status")
def finetune_local_status():
    try:
        import subprocess
        result = subprocess.run(
            ["ollama", "list"], capture_output=True, text=True, timeout=5
        )
        model_ready = "alex-cover-writer" in (result.stdout or "")
        return {"model_ready": model_ready}
    except Exception:
        return {"model_ready": False}


# ── Settings: License ─────────────────────────────────────────────────────────

# _config_dir() / _license_path() / _tokens_path() are per-request (see helpers above)


def _load_user_config() -> dict:
    """Load user.yaml using the same path logic as _user_yaml_path()."""
    return load_user_profile(_user_yaml_path())


def _save_user_config(cfg: dict) -> None:
    """Save user.yaml using the same path logic as _user_yaml_path()."""
    save_user_profile(_user_yaml_path(), cfg)


@app.get("/api/settings/license")
def get_license():
    try:
        lp = _license_path()
        if lp.exists():
            with open(lp) as f:
                data = yaml.safe_load(f) or {}
        else:
            data = {}
        return {
            "tier": data.get("tier", "free"),
            "key": data.get("key"),
            "active": bool(data.get("active", False)),
            "grace_period_ends": data.get("grace_period_ends"),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class LicenseActivatePayload(BaseModel):
    key: str

@app.post("/api/settings/license/activate")
def activate_license(payload: LicenseActivatePayload):
    try:
        # In dev: accept any key matching our format, grant paid tier
        key = payload.key.strip()
        if not re.match(r'^CFG-[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}$', key):
            return {"ok": False, "error": "Invalid key format"}
        lp = _license_path()
        data = {"tier": "paid", "key": key, "active": True}
        lp.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(str(lp), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            yaml.dump(data, f, allow_unicode=True, default_flow_style=False)
        return {"ok": True, "tier": "paid"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/settings/license/deactivate")
def deactivate_license():
    try:
        lp = _license_path()
        if lp.exists():
            with open(lp) as f:
                data = yaml.safe_load(f) or {}
            data["active"] = False
            fd = os.open(str(lp), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w") as f:
                yaml.dump(data, f, allow_unicode=True, default_flow_style=False)
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Settings: Data ────────────────────────────────────────────────────────────

class BackupCreatePayload(BaseModel):
    include_db: bool = False

@app.post("/api/settings/data/backup/create")
def create_backup(payload: BackupCreatePayload):
    try:
        import zipfile
        import datetime
        cfg_dir = _config_dir()
        backup_dir = cfg_dir.parent / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        dest = backup_dir / f"peregrine_backup_{ts}.zip"
        file_count = 0
        with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as zf:
            for cfg_file in cfg_dir.glob("*.yaml"):
                if cfg_file.name not in ("tokens.yaml",):
                    zf.write(cfg_file, f"config/{cfg_file.name}")
                    file_count += 1
            if payload.include_db:
                db_path = Path(_request_db.get() or DB_PATH)
                if db_path.exists():
                    zf.write(db_path, "data/staging.db")
                    file_count += 1
        size_bytes = dest.stat().st_size
        return {"path": str(dest), "file_count": file_count, "size_bytes": size_bytes}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Settings: Privacy ─────────────────────────────────────────────────────────

PRIVACY_YAML_FIELDS = {"telemetry_opt_in", "byok_info_dismissed", "master_off", "usage_events", "content_sharing"}

@app.get("/api/settings/privacy")
def get_privacy():
    try:
        cfg = _load_user_config()
        return {
            "telemetry_opt_in": bool(cfg.get("telemetry_opt_in", False)),
            "byok_info_dismissed": bool(cfg.get("byok_info_dismissed", False)),
            "master_off": bool(cfg.get("master_off", False)),
            "usage_events": cfg.get("usage_events", True),
            "content_sharing": bool(cfg.get("content_sharing", False)),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/api/settings/privacy")
def save_privacy(payload: dict):
    try:
        cfg = _load_user_config()
        for k, v in payload.items():
            if k in PRIVACY_YAML_FIELDS:
                cfg[k] = v
        _save_user_config(cfg)
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Settings: Developer ───────────────────────────────────────────────────────

@app.get("/api/settings/developer")
def get_developer():
    try:
        cfg = _load_user_config()
        tokens = {}
        tp = _tokens_path()
        if tp.exists():
            with open(tp) as f:
                tokens = yaml.safe_load(f) or {}
        return {
            "dev_tier_override": cfg.get("dev_tier_override"),
            "hf_token_set": bool(tokens.get("huggingface_token")),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class DevTierPayload(BaseModel):
    tier: Optional[str]

@app.put("/api/settings/developer/tier")
def set_dev_tier(payload: DevTierPayload):
    try:
        cfg = _load_user_config()
        cfg["dev_tier_override"] = payload.tier
        _save_user_config(cfg)
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class HfTokenPayload(BaseModel):
    token: str

@app.put("/api/settings/developer/hf-token")
def save_hf_token(payload: HfTokenPayload):
    try:
        set_credential("peregrine_tokens", "huggingface_token", payload.token)
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/settings/developer/hf-token/test")
def test_hf_token():
    try:
        token = get_credential("peregrine_tokens", "huggingface_token")
        if not token:
            return {"ok": False, "error": "No token stored"}
        from huggingface_hub import whoami
        info = whoami(token=token)
        return {"ok": True, "username": info.get("name")}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.post("/api/settings/developer/wizard-reset")
def wizard_reset():
    try:
        cfg = _load_user_config()
        cfg["wizard_complete"] = False
        _save_user_config(cfg)
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/settings/developer/export-classifier")
def export_classifier():
    try:
        import json as _json
        from scripts.db import get_labeled_emails
        emails = get_labeled_emails(DB_PATH)
        export_path = Path("data/email_score.jsonl")
        export_path.parent.mkdir(parents=True, exist_ok=True)
        with open(export_path, "w") as f:
            for e in emails:
                f.write(_json.dumps(e) + "\n")
        return {"ok": True, "count": len(emails), "path": str(export_path)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Wizard API ────────────────────────────────────────────────────────────────
#
# These endpoints back the Vue SPA first-run onboarding wizard.
# State is persisted to user.yaml on every step so the wizard can resume
# after a browser refresh or crash (mirrors the Streamlit wizard behaviour).

_WIZARD_PROFILES = ("remote", "cpu", "single-gpu", "dual-gpu")
_WIZARD_TIERS = ("free", "paid", "premium")


def _wizard_yaml_path() -> str:
    """Same resolution logic as _user_yaml_path() — single source of truth."""
    return _user_yaml_path()


def _load_wizard_yaml() -> dict:
    try:
        return load_user_profile(_wizard_yaml_path()) or {}
    except Exception:
        return {}


def _save_wizard_yaml(updates: dict) -> None:
    path = _wizard_yaml_path()
    existing = _load_wizard_yaml()
    existing.update(updates)
    save_user_profile(path, existing)


def _detect_gpus() -> list[str]:
    """Detect GPUs. Prefers PEREGRINE_GPU_NAMES env var (set by preflight)."""
    env_names = os.environ.get("PEREGRINE_GPU_NAMES", "").strip()
    if env_names:
        return [n.strip() for n in env_names.split(",") if n.strip()]
    try:
        out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
            text=True, timeout=5,
        )
        return [line.strip() for line in out.strip().splitlines() if line.strip()]
    except Exception:
        return []


def _suggest_profile(gpus: list[str]) -> str:
    recommended = os.environ.get("RECOMMENDED_PROFILE", "").strip()
    if recommended and recommended in _WIZARD_PROFILES:
        return recommended
    if len(gpus) >= 2:
        return "dual-gpu"
    if len(gpus) == 1:
        return "single-gpu"
    return "remote"


@app.get("/api/wizard/status")
def wizard_status():
    """Return current wizard state for resume-after-refresh.

    wizard_complete=True means the wizard has been finished and the app
    should not redirect to /setup.  wizard_step is the last completed step
    (0 = not started); the SPA advances to step+1 on load.
    """
    cfg = _load_wizard_yaml()
    return {
        "wizard_complete": bool(cfg.get("wizard_complete", False)),
        "wizard_step": int(cfg.get("wizard_step", 0)),
        "saved_data": {
            "inference_profile": cfg.get("inference_profile", ""),
            "tier": cfg.get("tier", "free"),
            "name": cfg.get("name", ""),
            "email": cfg.get("email", ""),
            "phone": cfg.get("phone", ""),
            "linkedin": cfg.get("linkedin", ""),
            "career_summary": cfg.get("career_summary", ""),
            "services": cfg.get("services", {}),
        },
    }


class WizardStepPayload(BaseModel):
    step: int
    data: dict = {}


@app.post("/api/wizard/step")
def wizard_save_step(payload: WizardStepPayload):
    """Persist a single wizard step and advance the step counter.

    Side effects by step number:
    - Step 3 (Resume): writes config/plain_text_resume.yaml
    - Step 5 (Inference): writes API keys into .env
    - Step 6 (Search): writes config/search_profiles.yaml
    """
    step = payload.step
    data = payload.data

    if step < 1 or step > 7:
        raise HTTPException(status_code=400, detail="step must be 1–7")

    updates: dict = {"wizard_step": step}

    # ── Step-specific field extraction ────────────────────────────────────────
    if step == 1:
        profile = data.get("inference_profile", "remote")
        if profile not in _WIZARD_PROFILES:
            raise HTTPException(status_code=400, detail=f"Unknown profile: {profile}")
        updates["inference_profile"] = profile

    elif step == 2:
        tier = data.get("tier", "free")
        if tier not in _WIZARD_TIERS:
            raise HTTPException(status_code=400, detail=f"Unknown tier: {tier}")
        updates["tier"] = tier

    elif step == 3:
        # Resume data: persist to plain_text_resume.yaml
        resume = data.get("resume", {})
        if resume:
            resume_path = Path(_wizard_yaml_path()).parent / "plain_text_resume.yaml"
            resume_path.parent.mkdir(parents=True, exist_ok=True)
            with open(resume_path, "w") as f:
                yaml.dump(resume, f, allow_unicode=True, default_flow_style=False)

    elif step == 4:
        for field in ("name", "email", "phone", "linkedin", "career_summary"):
            if field in data:
                updates[field] = data[field]

    elif step == 5:
        # Write API keys to .env (never store in user.yaml)
        env_path = Path(_wizard_yaml_path()).parent.parent / ".env"
        env_lines = env_path.read_text().splitlines() if env_path.exists() else []

        def _set_env_key(lines: list[str], key: str, val: str) -> list[str]:
            for i, line in enumerate(lines):
                if line.startswith(f"{key}="):
                    lines[i] = f"{key}={val}"
                    return lines
            lines.append(f"{key}={val}")
            return lines

        if data.get("anthropic_key"):
            env_lines = _set_env_key(env_lines, "ANTHROPIC_API_KEY", data["anthropic_key"])
        if data.get("openai_url"):
            env_lines = _set_env_key(env_lines, "OPENAI_COMPAT_URL", data["openai_url"])
        if data.get("openai_key"):
            env_lines = _set_env_key(env_lines, "OPENAI_COMPAT_KEY", data["openai_key"])
        if any(data.get(k) for k in ("anthropic_key", "openai_url", "openai_key")):
            env_path.parent.mkdir(parents=True, exist_ok=True)
            env_path.write_text("\n".join(env_lines) + "\n")

        if "services" in data:
            updates["services"] = data["services"]

    elif step == 6:
        # Persist search preferences to search_profiles.yaml
        titles = data.get("titles", [])
        locations = data.get("locations", [])
        search_path = _search_prefs_path()
        existing_search: dict = {}
        if search_path.exists():
            with open(search_path) as f:
                existing_search = yaml.safe_load(f) or {}
        default_profile = existing_search.get("default", {})
        default_profile["job_titles"] = titles
        default_profile["location"] = locations
        existing_search["default"] = default_profile
        search_path.parent.mkdir(parents=True, exist_ok=True)
        with open(search_path, "w") as f:
            yaml.dump(existing_search, f, allow_unicode=True, default_flow_style=False)

    # Step 7 (integrations) has no extra side effects here — connections are
    # handled by the existing /api/settings/system/integrations/{id}/connect.

    try:
        _save_wizard_yaml(updates)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return {"ok": True, "step": step}


@app.get("/api/wizard/hardware")
def wizard_hardware():
    """Detect GPUs and suggest an inference profile."""
    gpus = _detect_gpus()
    suggested = _suggest_profile(gpus)
    return {
        "gpus": gpus,
        "suggested_profile": suggested,
        "profiles": list(_WIZARD_PROFILES),
    }


class WizardInferenceTestPayload(BaseModel):
    profile: str = "remote"
    anthropic_key: str = ""
    openai_url: str = ""
    openai_key: str = ""
    ollama_host: str = "localhost"
    ollama_port: int = 11434


@app.post("/api/wizard/inference/test")
def wizard_test_inference(payload: WizardInferenceTestPayload):
    """Test LLM or Ollama connectivity.

    Always returns {ok, message} — a connection failure is reported as a
    soft warning (message), not an HTTP error, so the wizard can let the
    user continue past a temporarily-down Ollama instance.
    """
    if payload.profile == "remote":
        try:
            # Temporarily inject key if provided (don't persist yet)
            env_override = {}
            if payload.anthropic_key:
                env_override["ANTHROPIC_API_KEY"] = payload.anthropic_key
            if payload.openai_url:
                env_override["OPENAI_COMPAT_URL"] = payload.openai_url
            if payload.openai_key:
                env_override["OPENAI_COMPAT_KEY"] = payload.openai_key

            old_env = {k: os.environ.get(k) for k in env_override}
            os.environ.update(env_override)
            try:
                from scripts.llm_router import LLMRouter
                result = LLMRouter().complete("Reply with only the word: OK")
                ok = bool(result and result.strip())
                message = "LLM responding." if ok else "LLM returned an empty response."
            finally:
                for k, v in old_env.items():
                    if v is None:
                        os.environ.pop(k, None)
                    else:
                        os.environ[k] = v
        except Exception as exc:
            return {"ok": False, "message": f"LLM test failed: {exc}"}
    else:
        # Local profile — ping Ollama
        ollama_url = f"http://{payload.ollama_host}:{payload.ollama_port}"
        try:
            resp = requests.get(f"{ollama_url}/api/tags", timeout=5)
            ok = resp.status_code == 200
            message = "Ollama is running." if ok else f"Ollama returned HTTP {resp.status_code}."
        except Exception:
            # Soft-fail: user can skip and configure later
            return {
                "ok": False,
                "message": (
                    "Ollama not responding — you can continue and configure it later "
                    "in Settings → System."
                ),
            }

    return {"ok": ok, "message": message}


@app.post("/api/wizard/complete")
def wizard_complete():
    """Finalise the wizard: set wizard_complete=true, apply service URLs."""
    try:
        from scripts.user_profile import UserProfile
        from scripts.generate_llm_config import apply_service_urls

        yaml_path = _wizard_yaml_path()
        llm_yaml = Path(yaml_path).parent / "llm.yaml"

        try:
            profile_obj = UserProfile(yaml_path)
            if llm_yaml.exists():
                apply_service_urls(profile_obj, llm_yaml)
        except Exception:
            pass  # don't block completion on llm.yaml errors

        cfg = _load_wizard_yaml()
        cfg["wizard_complete"] = True
        cfg.pop("wizard_step", None)
        save_user_profile(yaml_path, cfg)

        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
