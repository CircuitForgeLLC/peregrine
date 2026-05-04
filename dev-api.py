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
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List
from urllib.parse import urlparse

import requests
import yaml
from bs4 import BeautifulSoup
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Allow importing peregrine scripts for cover letter generation.
# Resolved from __file__ so it works both in Docker (/app) and on the dev
# machine (/Library/Development/CircuitForge/peregrine) without hardcoding.
PEREGRINE_ROOT = Path(__file__).resolve().parent
if str(PEREGRINE_ROOT) not in sys.path:
    sys.path.insert(0, str(PEREGRINE_ROOT))

from circuitforge_core.api import make_feedback_router as _make_feedback_router  # noqa: E402
from circuitforge_core.config.settings import load_env as _load_env  # noqa: E402
from scripts.credential_store import get_credential, set_credential, delete_credential  # noqa: E402

DB_PATH = os.environ.get("STAGING_DB", "/devl/job-seeker/staging.db")

_CLOUD_MODE       = os.environ.get("CLOUD_MODE", "").lower() in ("1", "true")
_CLOUD_DATA_ROOT  = Path(os.environ.get("CLOUD_DATA_ROOT", "/devl/menagerie-data"))
_DIRECTUS_SECRET  = os.environ.get("DIRECTUS_JWT_SECRET", "")
IS_DEMO: bool = os.environ.get("DEMO_MODE", "").lower() in ("1", "true", "yes")

# Per-request DB path — set by cloud_session_middleware; falls back to DB_PATH
_request_db: ContextVar[str | None] = ContextVar("_request_db", default=None)

def _load_demo_seed(db_path: str, seed_file: str) -> None:
    """Load seed SQL into the demo DB if it is empty (no jobs rows yet)."""
    import sqlite3 as _sqlite3
    seed_path = Path(seed_file)
    if not seed_path.exists():
        return
    con = _sqlite3.connect(db_path)
    try:
        count = con.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
        if count == 0:
            con.executescript(seed_path.read_text())
            con.commit()
    finally:
        con.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load .env, run migrations, and (in demo mode) seed the demo DB."""
    # Load .env before any runtime env reads — safe because lifespan doesn't run
    # when dev_api is imported by tests (only when uvicorn actually starts).
    _load_env(PEREGRINE_ROOT / ".env")
    from scripts.db_migrate import migrate_db
    migrate_db(Path(DB_PATH))

    # Cloud mode: sweep all known user DBs at startup so schema changes land
    # for every user on deploy, not only on their next request.
    if _CLOUD_MODE and _CLOUD_DATA_ROOT.is_dir():
        import logging as _log
        _sweep_log = _log.getLogger("peregrine.startup")
        for user_db in _CLOUD_DATA_ROOT.glob("*/peregrine/staging.db"):
            try:
                migrate_db(user_db)
                _migrated_db_paths.add(str(user_db))
                _sweep_log.info("Migrated user DB: %s", user_db)
            except Exception as exc:
                _sweep_log.warning("Migration failed for %s: %s", user_db, exc)

    if IS_DEMO and (seed_file := os.environ.get("DEMO_SEED_FILE")):
        _load_demo_seed(DB_PATH, seed_file)
    yield


app = FastAPI(title="Peregrine Dev API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://10.1.10.71:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_feedback_router = _make_feedback_router(
    repo="Circuit-Forge/peregrine",
    product="peregrine",
    demo_mode_fn=lambda: (
        _CLOUD_MODE or os.environ.get("DEMO_MODE", "").lower() in ("1", "true", "yes")
    ),
)
app.include_router(_feedback_router, prefix="/api/feedback")

_log = logging.getLogger("peregrine.session")


def _demo_guard() -> None:
    """Raise 403 if running in demo mode. Call at the top of any write endpoint."""
    if IS_DEMO:
        raise HTTPException(status_code=403, detail="demo-write-blocked")

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
            if user_db not in _migrated_db_paths:
                from scripts.db_migrate import migrate_db
                migrate_db(Path(user_db))
                _migrated_db_paths.add(user_db)
            token = _request_db.set(user_db)
            try:
                return await call_next(request)
            finally:
                _request_db.reset(token)
    return await call_next(request)


_migrated_db_paths: set[str] = set()


def _get_db():
    path = _request_db.get() or DB_PATH
    if path not in _migrated_db_paths:
        from scripts.db_migrate import migrate_db
        migrate_db(Path(path))
        _migrated_db_paths.add(path)
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


def _shadow_score(date_posted: str | None, date_found: str | None) -> str | None:
    """Return 'shadow', 'stale', or None based on posting age when discovered.

    A job posted >30 days before discovery is a shadow candidate (posted to
    satisfy legal/HR requirements, likely already filled). 14-30 days is stale.
    Returns None when dates are unavailable.
    """
    if not date_posted or not date_found:
        return None
    try:
        posted = datetime.fromisoformat(date_posted.replace("Z", "+00:00")).replace(tzinfo=timezone.utc)
        found  = datetime.fromisoformat(date_found.replace("Z", "+00:00")).replace(tzinfo=timezone.utc)
        days = (found - posted).days
        if days >= 30:
            return "shadow"
        if days >= 14:
            return "stale"
    except (ValueError, TypeError):
        pass
    return None


# ── GET /api/jobs ─────────────────────────────────────────────────────────────

@app.get("/api/jobs")
def list_jobs(status: str = "pending", limit: int = 50, fields: str = ""):
    db = _get_db()
    rows = db.execute(
        "SELECT id, title, company, url, source, location, is_remote, salary, "
        "description, match_score, keyword_gaps, date_found, date_posted, status, cover_letter "
        "FROM jobs WHERE status = ? ORDER BY match_score DESC NULLS LAST LIMIT ?",
        (status, limit),
    ).fetchall()
    db.close()
    result = []
    for r in rows:
        d = _row_to_job(r)
        d["has_cover_letter"] = bool(d.get("cover_letter"))
        d["shadow_score"] = _shadow_score(d.get("date_posted"), d.get("date_found"))
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
    _demo_guard()
    db = _get_db()
    db.execute("UPDATE jobs SET status = 'approved' WHERE id = ?", (job_id,))
    db.commit()
    db.close()
    return {"ok": True}


# ── POST /api/jobs/{id}/reject ────────────────────────────────────────────────

@app.post("/api/jobs/{job_id}/reject")
def reject_job(job_id: int):
    _demo_guard()
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
    _demo_guard()
    try:
        from scripts.task_runner import submit_task
        task_id, is_new = submit_task(
            db_path=Path(_request_db.get() or DB_PATH),
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
        task_id, is_new = submit_task(db_path=Path(_request_db.get() or DB_PATH), task_type="company_research", job_id=job_id)
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
    result = _get(db_path=Path(_request_db.get() or DB_PATH), job_id=job_id)
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
            db_path=Path(_request_db.get() or DB_PATH),
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


@app.get("/api/jobs/{job_id}/resume_optimizer/review")
def get_resume_review(job_id: int):
    """Return the pending review draft for this job (populated when task is awaiting_review)."""
    from scripts.db import get_resume_draft as _get_draft
    draft = _get_draft(db_path=Path(_request_db.get() or DB_PATH), job_id=job_id)
    if not draft:
        return {"draft": None}
    return {"draft": draft}


class GapFramingDecision(BaseModel):
    skill: str
    # "adjacent" — has related experience, inject bridging sentence into bullets
    # "learning" — actively developing the skill, add structured note to skills list
    # "skip"     — no connection, omit entirely
    mode: str = "skip"
    context: str = ""  # candidate's own words; required for adjacent/learning


class ResumeReviewBody(BaseModel):
    # Per-section decisions.  Keys are section names; values are section-type-specific.
    # skills:     {"approved_additions": [...]}
    # summary:    {"accepted": bool}
    # experience: {"accepted_entries": [{"title": str, "company": str, "accepted": bool}]}
    decisions: dict
    # One entry per rejected skill, describing how to frame the gap honestly.
    gap_framings: list[GapFramingDecision] = []


@app.post("/api/jobs/{job_id}/resume_optimizer/review")
def preview_resume_review(job_id: int, body: ResumeReviewBody):
    """Apply review decisions + gap framings and return the assembled resume for preview.

    Does NOT save yet — the user sees the full assembled resume and confirms
    via POST /approve before anything is persisted.

    Flow:
      1. apply_review_decisions() — merges approved skills, summary, experience choices
      2. frame_skill_gaps()       — injects adjacent/learning framing for rejected skills
      3. render_resume_text()     — renders to plain text for the preview panel
      Returns: {preview_text, preview_struct} — struct preserved for the approve step.
    """
    import json as _json
    from scripts.db import get_resume_draft as _get_draft
    from scripts.resume_optimizer import (
        apply_review_decisions, frame_skill_gaps, render_resume_text,
    )

    db_path = Path(_request_db.get() or DB_PATH)
    draft = _get_draft(db_path=db_path, job_id=job_id)
    if not draft:
        raise HTTPException(404, "No pending review draft for this job")

    # Step 1: apply section-level decisions
    struct = apply_review_decisions(draft, body.decisions)

    # Step 2: inject gap framing for rejected skills (adjacent / learning)
    framings = [f.model_dump() for f in body.gap_framings if f.mode in ("adjacent", "learning")]
    if framings:
        db_path_obj = Path(_request_db.get() or DB_PATH)
        job_row = _get_db().execute(
            "SELECT title, company FROM jobs WHERE id=?", (job_id,)
        ).fetchone()
        _get_db().close()
        job = {"title": job_row[0], "company": job_row[1]} if job_row else {}

        from scripts.user_profile import UserProfile
        from app.cloud_session import get_config_dir
        _user_yaml = get_config_dir() / "user.yaml"
        candidate_voice = UserProfile(_user_yaml).candidate_voice if UserProfile.exists(_user_yaml) else ""

        struct = frame_skill_gaps(struct, framings, job, candidate_voice)

    preview_text = render_resume_text(struct)
    return {"preview_text": preview_text, "preview_struct": struct}


@app.post("/api/jobs/{job_id}/resume_optimizer/approve")
def approve_resume(job_id: int, body: dict):
    """Save the user-approved assembled resume struct and mark the task complete.

    Expects body: {"preview_struct": {...}}  — the struct returned by /review.
    Saves both the rendered plain text and the struct (for YAML export).
    """
    import json as _json
    from scripts.db import finalize_resume as _finalize

    db_path = Path(_request_db.get() or DB_PATH)
    struct = body.get("preview_struct")
    if not struct:
        raise HTTPException(400, "preview_struct is required")

    from scripts.resume_optimizer import render_resume_text
    final_text = render_resume_text(struct)

    # Persist plain text + struct (struct enables YAML export later)
    _finalize(db_path=db_path, job_id=job_id, final_text=final_text)

    # Store struct alongside the text so YAML round-trip is possible
    db = _get_db()
    db.execute(
        "UPDATE jobs SET resume_final_struct=? WHERE id=?",
        (_json.dumps(struct), job_id),
    )
    db.execute(
        "UPDATE background_tasks SET status='completed', updated_at=datetime('now') "
        "WHERE task_type='resume_optimize' AND job_id=? AND status='awaiting_review'",
        (job_id,),
    )
    db.commit()
    db.close()

    saved_resume_id: int | None = None
    if body.get("save_to_library"):
        from scripts.db import create_resume as _create_r
        import json as _json2
        resume_name = (body.get("resume_name") or "").strip() or f"Optimized for job {job_id}"
        saved = _create_r(
            db_path,
            name=resume_name,
            text=final_text,
            source="optimizer",
            job_id=job_id,
            struct_json=_json.dumps(struct) if struct else None,
        )
        saved_resume_id = saved["id"]

    return {"optimized_resume": final_text, "saved_resume_id": saved_resume_id}


def _get_final_struct(job_id: int) -> dict:
    """Return the approved resume struct for a job, or raise 404."""
    import json as _json
    db = _get_db()
    row = db.execute(
        "SELECT resume_final_struct FROM jobs WHERE id=?", (job_id,)
    ).fetchone()
    db.close()
    if not row or not row[0]:
        raise HTTPException(404, "No approved resume struct for this job — approve first")
    return _json.loads(row[0])


@app.get("/api/jobs/{job_id}/resume_optimizer/export-pdf")
def export_resume_pdf(job_id: int):
    """Generate a PDF from the approved resume struct and return it as a download."""
    import tempfile
    from scripts.resume_optimizer import export_pdf
    from fastapi.responses import FileResponse

    struct = _get_final_struct(job_id)
    tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
    tmp.close()
    export_pdf(struct, tmp.name)

    return FileResponse(
        tmp.name,
        media_type="application/pdf",
        filename=f"resume-optimized-job-{job_id}.pdf",
    )


@app.get("/api/jobs/{job_id}/resume_optimizer/export-yaml")
def export_resume_yaml(job_id: int):
    """Return the approved resume struct as a downloadable YAML file."""
    import yaml
    from fastapi.responses import Response

    struct = _get_final_struct(job_id)
    yaml_text = yaml.dump(struct, default_flow_style=False, allow_unicode=True)

    return Response(
        content=yaml_text,
        media_type="application/x-yaml",
        headers={"Content-Disposition": f"attachment; filename=resume-optimized-job-{job_id}.yaml"},
    )


@app.get("/api/jobs/{job_id}/resume_optimizer/history")
def get_resume_history(job_id: int):
    """Return the archive of past finalized resume versions (newest first)."""
    from scripts.db import get_resume_archive as _get_archive
    archive = _get_archive(db_path=Path(_request_db.get() or DB_PATH), job_id=job_id)
    return {"history": archive}


# ── Resume library endpoints ───────────────────────────────────────────────────

@app.get("/api/resumes")
def list_resumes_endpoint():
    from scripts.db import list_resumes as _list
    return {"resumes": _list(Path(_request_db.get() or DB_PATH))}


@app.post("/api/resumes")
def create_resume_endpoint(body: dict):
    from scripts.db import create_resume as _create
    name = (body.get("name") or "").strip()
    text = (body.get("text") or "").strip()
    if not name or not text:
        raise HTTPException(400, "name and text are required")
    return _create(
        Path(_request_db.get() or DB_PATH),
        name=name, text=text,
        source=body.get("source", "manual"),
        job_id=body.get("job_id"),
        struct_json=body.get("struct_json"),
    )


@app.post("/api/resumes/import")
async def import_resume_endpoint(file: UploadFile, name: str = ""):
    import os, tempfile, json as _json
    from scripts.db import create_resume as _create
    db_path = Path(_request_db.get() or DB_PATH)
    content = await file.read()
    MAX_IMPORT_BYTES = 5 * 1024 * 1024  # 5 MB
    if len(content) > MAX_IMPORT_BYTES:
        raise HTTPException(413, "File too large — 5 MB maximum")
    filename = file.filename or ""
    ext = Path(filename).suffix.lower()
    struct_json: str | None = None

    if ext in (".txt", ".md"):
        text = content.decode("utf-8", errors="replace")

    elif ext in (".pdf", ".docx", ".odt"):
        from scripts.resume_parser import (
            extract_text_from_pdf as _extract_pdf,
            extract_text_from_docx as _extract_docx,
            extract_text_from_odt as _extract_odt,
        )
        if ext == ".pdf":
            text = _extract_pdf(content)
        elif ext == ".docx":
            text = _extract_docx(content)
        else:
            text = _extract_odt(content)

    elif ext in (".yaml", ".yml"):
        import yaml as _yaml
        from scripts.task_runner import _normalize_aihawk_resume
        raw = _yaml.safe_load(content.decode("utf-8", errors="replace")) or {}
        struct = _normalize_aihawk_resume(raw)
        struct_json = _json.dumps(struct)
        lines = [struct.get("career_summary", "")]
        for exp in struct.get("experience", []):
            lines.append(f"{exp.get('title', '')} at {exp.get('company', '')}")
            lines.extend(f"• {b}" for b in exp.get("bullets", []))
        text = "\n".join(lines)
        if not text.strip():
            raise HTTPException(400, "YAML file contains no readable content")

    else:
        raise HTTPException(
            400,
            f"Unsupported file type: {ext}. Accepted: .txt .md .pdf .docx .odt .yaml .yml",
        )

    resume_name = name.strip() or Path(filename).stem or "Imported Resume"
    return _create(db_path, name=resume_name, text=text.strip(), source="import", struct_json=struct_json)


@app.get("/api/resumes/{resume_id}")
def get_resume_endpoint(resume_id: int):
    from scripts.db import get_resume as _get
    r = _get(Path(_request_db.get() or DB_PATH), resume_id)
    if not r:
        raise HTTPException(404, "Resume not found")
    return r


@app.patch("/api/resumes/{resume_id}")
def update_resume_endpoint(resume_id: int, body: dict):
    from scripts.db import get_resume as _get, update_resume as _update
    db_path = Path(_request_db.get() or DB_PATH)
    if not _get(db_path, resume_id):
        raise HTTPException(404, "Resume not found")
    return _update(db_path, resume_id, name=body.get("name"), text=body.get("text"))


@app.delete("/api/resumes/{resume_id}")
def delete_resume_endpoint(resume_id: int):
    from scripts.db import get_resume as _get, list_resumes as _list, delete_resume as _delete
    db_path = Path(_request_db.get() or DB_PATH)
    r = _get(db_path, resume_id)
    if not r:
        raise HTTPException(404, "Resume not found")
    if len(_list(db_path)) == 1:
        raise HTTPException(409, "Cannot delete the only resume")
    if r["is_default"]:
        raise HTTPException(409, "Cannot delete the default resume — set a new default first")
    _delete(db_path, resume_id)
    return {"ok": True}


@app.post("/api/resumes/{resume_id}/set-default")
def set_default_resume_endpoint(resume_id: int):
    import yaml as _yaml
    from scripts.db import get_resume as _get, set_default_resume as _set_default
    db_path = Path(_request_db.get() or DB_PATH)
    if not _get(db_path, resume_id):
        raise HTTPException(404, "Resume not found")
    _set_default(db_path, resume_id)
    _user_yaml = db_path.parent / "config" / "user.yaml"
    if _user_yaml.exists():
        profile = _yaml.safe_load(_user_yaml.read_text(encoding="utf-8")) or {}
        profile["default_resume_id"] = resume_id
        _user_yaml.write_text(_yaml.dump(profile, default_flow_style=False, allow_unicode=True))
    return {"ok": True}


@app.post("/api/resumes/{resume_id}/apply-to-profile")
def apply_resume_to_profile(resume_id: int):
    """Sync a library resume entry to the active profile (library→profile direction).

    Workflow:
      1. Load the library entry (must have struct_json).
      2. Load current profile to preserve metadata fields.
      3. Backup current profile content as a new auto-named library entry.
      4. Merge content fields from the library entry into the profile.
      5. Write updated plain_text_resume.yaml.
      6. Mark the library entry synced_at.
      7. Return backup details for the frontend notification.
    """
    import json as _json
    from scripts.resume_sync import (
        library_to_profile_content,
        profile_to_library,
        make_auto_backup_name,
    )
    from scripts.db import get_resume as _get, create_resume as _create

    db_path = Path(_request_db.get() or DB_PATH)
    entry = _get(db_path, resume_id)
    if not entry:
        raise HTTPException(404, "Resume not found")

    struct_json: dict = {}
    if entry.get("struct_json"):
        try:
            struct_json = _json.loads(entry["struct_json"])
        except Exception:
            raise HTTPException(422, "Library entry has malformed struct_json — re-import the resume to repair it.")

    resume_path = _resume_path()
    current_profile: dict = {}
    if resume_path.exists():
        with open(resume_path, encoding="utf-8") as f:
            current_profile = yaml.safe_load(f) or {}

    # Backup current content to library before overwriting
    backup_text, backup_struct = profile_to_library(current_profile)
    backup_name = make_auto_backup_name(entry["name"])
    backup = _create(
        db_path,
        name=backup_name,
        text=backup_text,
        source="auto_backup",
        struct_json=_json.dumps(backup_struct),
    )

    # Merge: overwrite content fields, preserve metadata
    content = library_to_profile_content(struct_json)
    CONTENT_FIELDS = {
        "name", "surname", "email", "phone", "career_summary",
        "experience", "skills", "education", "achievements",
    }
    for field in CONTENT_FIELDS:
        current_profile[field] = content[field]

    resume_path.parent.mkdir(parents=True, exist_ok=True)
    with open(resume_path, "w", encoding="utf-8") as f:
        yaml.dump(current_profile, f, allow_unicode=True, default_flow_style=False)

    from scripts.db import update_resume_synced_at as _mark_synced
    _mark_synced(db_path, resume_id)

    return {
        "ok":             True,
        "backup_id":      backup["id"],
        "backup_name":    backup_name,
        "fields_updated": sorted(CONTENT_FIELDS),
    }


# ── Per-job resume endpoints ───────────────────────────────────────────────────

@app.get("/api/jobs/{job_id}/resume")
def get_job_resume_endpoint(job_id: int):
    from scripts.db import get_job_resume as _get
    r = _get(Path(_request_db.get() or DB_PATH), job_id)
    if not r:
        raise HTTPException(404, "No resume configured — add one in Resume Manager")
    return r


@app.patch("/api/jobs/{job_id}/resume")
def set_job_resume_endpoint(job_id: int, body: dict):
    from scripts.db import get_resume as _get_r, set_job_resume as _set, get_job_resume as _get_job
    db_path = Path(_request_db.get() or DB_PATH)
    resume_id = body.get("resume_id")
    if not resume_id or not _get_r(db_path, resume_id):
        raise HTTPException(404, "Resume not found")
    _set(db_path, job_id=job_id, resume_id=resume_id)
    return _get_job(db_path, job_id)


# ── GET /api/imitate/samples ──────────────────────────────────────────────────
# Avocet "Imitate" tab uses this to build the EXACT prompt Peregrine sends to
# its LLM — including user voice, mission context, style examples, and full job
# context. Avocet then routes these prompts through different local models to
# compare generation quality against the real Peregrine pipeline.

def _imitate_load_profile():
    """Load UserProfile from config/user.yaml, or None if missing."""
    try:
        from scripts.user_profile import UserProfile
        _yaml = PEREGRINE_ROOT / "config" / "user.yaml"
        return UserProfile(_yaml) if UserProfile.exists(_yaml) else None
    except Exception:
        return None


def _imitate_cover_letter(db, profile, limit: int) -> dict:
    from scripts.generate_cover_letter import (
        build_prompt, _build_system_context,
        load_corpus, find_similar_letters, detect_mission_alignment,
    )
    rows = db.execute(
        "SELECT id, title, company, description, cover_letter, status FROM jobs "
        "WHERE description IS NOT NULL AND description != '' "
        "  AND status IN ('applied','phone_screen','interviewing','offer','hired') "
        "ORDER BY applied_at DESC NULLS LAST LIMIT ?",
        (limit,),
    ).fetchall()

    system_ctx = _build_system_context(profile)
    try:
        corpus = load_corpus()
    except Exception:
        corpus = []

    samples = []
    for r in rows:
        desc = r["description"] or ""
        examples = find_similar_letters(desc, corpus) if corpus else []
        mission_hint = detect_mission_alignment(r["company"], desc)
        prompt = build_prompt(
            title=r["title"],
            company=r["company"],
            description=desc,
            examples=examples,
            mission_hint=mission_hint,
            system_context=system_ctx,
            candidate_name=profile.name if profile else None,
        )
        samples.append({
            "id": r["id"],
            "job_title": r["title"],
            "company": r["company"],
            "status": r["status"],
            "system_prompt": system_ctx,
            "input_text": prompt,
            "output_text": r["cover_letter"] or "",
        })
    return {"samples": samples, "total": len(samples), "type": "cover_letter"}


def _imitate_company_research(db, profile, limit: int) -> dict:
    rows = db.execute(
        "SELECT j.id, j.title, j.company, j.description, j.status, "
        "       cr.raw_output, cr.company_brief "
        "FROM jobs j LEFT JOIN company_research cr ON cr.job_id = j.id "
        "WHERE j.description IS NOT NULL AND j.description != '' "
        "  AND j.status IN ('phone_screen','interviewing','offer','hired') "
        "ORDER BY j.phone_screen_at DESC NULLS LAST LIMIT ?",
        (limit,),
    ).fetchall()

    name = profile.name if profile else "the candidate"
    career_summary = profile.career_summary if profile else ""

    # Load plain-text resume for context
    resume_ctx = ""
    try:
        import yaml as _yaml
        _rpath = PEREGRINE_ROOT / "config" / "plain_text_resume.yaml"
        if _rpath.exists():
            _rd = _yaml.safe_load(_rpath.read_text(encoding="utf-8")) or {}
            parts = []
            for section in ("experience", "skills", "education", "summary"):
                val = _rd.get(section)
                if val:
                    parts.append(f"### {section.title()}\n{val if isinstance(val, str) else str(val)}")
            resume_ctx = "\n\n".join(parts)[:2000]
    except Exception:
        pass

    samples = []
    for r in rows:
        jd = (r["description"] or "")[:1500].strip()
        resume_block = f"\n## Candidate Background\n{resume_ctx}" if resume_ctx else ""
        career_block = f"Candidate background: {career_summary}\n\n" if career_summary else ""
        prompt = (
            f"You are preparing {name} for a job interview.\n"
            f"{career_block}"
            f"Role: **{r['title']}** at **{r['company']}**\n\n"
            f"## Job Description\n{jd}"
            f"{resume_block}\n\n"
            f"---\n\n"
            f"Produce a structured research brief with exactly these markdown section headers:\n\n"
            f"## Company Overview\n"
            f"What {r['company']} does, core product/service, business model, size/stage, market positioning.\n\n"
            f"## Leadership & Culture\n"
            f"CEO background and leadership style, mission/values statements, Glassdoor themes.\n\n"
            f"## Tech Stack & Product\n"
            f"Technologies, platforms, and product direction relevant to the {r['title']} role.\n\n"
            f"## Funding & Market Position\n"
            f"Funding stage, key investors, recent rounds, competitor landscape.\n\n"
            f"## Recent Developments\n"
            f"News, launches, acquisitions, or press from the past 12-18 months.\n\n"
            f"## Red Flags & Watch-outs\n"
            f"Culture issues, layoffs, financial stress, or Glassdoor concerns worth knowing. "
            f"If nothing notable, write 'No significant red flags identified.'\n\n"
            f"## Talking Points for {name}\n"
            f"Five specific talking points for the phone screen. Each must reference a concrete "
            f"experience and connect to a specific JD signal. 1-2 sentences, ready to speak aloud. "
            f"Never give generic advice.\n\n"
            f"---\n"
            f"⚠️ This brief uses LLM training knowledge only (no live web data). "
            f"Verify key facts before the call."
        )
        samples.append({
            "id": r["id"],
            "job_title": r["title"],
            "company": r["company"],
            "status": r["status"],
            "system_prompt": "",
            "input_text": prompt,
            "output_text": r["raw_output"] or r["company_brief"] or "",
        })
    return {"samples": samples, "total": len(samples), "type": "company_research"}


def _imitate_interview_prep(db, profile, limit: int) -> dict:
    rows = db.execute(
        "SELECT j.id, j.title, j.company, j.status, "
        "       cr.talking_points, cr.company_brief "
        "FROM jobs j LEFT JOIN company_research cr ON cr.job_id = j.id "
        "WHERE j.status IN ('phone_screen','interviewing','offer','hired') "
        "ORDER BY j.phone_screen_at DESC NULLS LAST LIMIT ?",
        (limit,),
    ).fetchall()

    name = profile.name if profile else "the candidate"
    samples = []
    for r in rows:
        system_prompt = (
            f"You are a recruiter at {r['company']} conducting a phone screen for the "
            f"{r['title']} role. Ask one question at a time. After {name} answers, give "
            f"brief feedback (1-2 sentences), then ask your next question. Be professional but warm."
        )
        ctx_parts = []
        if r["talking_points"]:
            ctx_parts.append(f"[Candidate talking points]\n{r['talking_points']}")
        if r["company_brief"]:
            ctx_parts.append(f"[Company context]\n{r['company_brief'][:500]}")
        ctx_block = ("\n\n".join(ctx_parts) + "\n\n") if ctx_parts else ""
        input_text = (
            f"{ctx_block}"
            f"Start the mock phone screen for the {r['title']} role at {r['company']}. "
            f"Ask your first question. Keep it realistic and concise."
        )
        samples.append({
            "id": r["id"],
            "job_title": r["title"],
            "company": r["company"],
            "status": r["status"],
            "system_prompt": system_prompt,
            "input_text": input_text,
            "output_text": "",
        })
    return {"samples": samples, "total": len(samples), "type": "interview_prep"}


def _imitate_ats_resume(db, profile, limit: int) -> dict:
    rows = db.execute(
        "SELECT id, title, company, description, ats_gap_report, status FROM jobs "
        "WHERE description IS NOT NULL AND description != '' "
        "  AND status IN ('applied','phone_screen','interviewing','offer','hired') "
        "ORDER BY applied_at DESC NULLS LAST LIMIT ?",
        (limit,),
    ).fetchall()

    candidate_voice = profile.candidate_voice if profile else ""
    voice_block = (
        f"\nCandidate voice/style: {candidate_voice}\n"
        "Preserve this tone in any phrasing suggestions."
    ) if candidate_voice else ""

    resume_text = ""
    try:
        _rpath = PEREGRINE_ROOT / "config" / "plain_text_resume.yaml"
        if _rpath.exists():
            resume_text = _rpath.read_text(encoding="utf-8")[:3000]
    except Exception:
        pass
    resume_block = f"\n## Current Resume\n{resume_text}" if resume_text else ""

    samples = []
    for r in rows:
        desc = (r["description"] or "")[:1500].strip()
        prompt = (
            f"You are an ATS (applicant tracking system) keyword optimization expert.\n\n"
            f"Analyze the resume below against this job description. Identify keyword gaps "
            f"(terms in the JD missing or underrepresented in the resume) and for each gap "
            f"specify which section it belongs in (summary, skills, or experience).\n\n"
            f"Job: {r['title']} at {r['company']}\n\n"
            f"## Job Description\n{desc}"
            f"{resume_block}"
            f"{voice_block}\n\n"
            f"Return a JSON array of gap objects, each with keys:\n"
            f'  "term": the missing keyword\n'
            f'  "section": summary | skills | experience\n'
            f'  "priority": high | medium | low\n'
            f'  "rationale": one sentence explaining the gap\n\n'
            f"Order by priority descending. Return ONLY the JSON array."
        )
        samples.append({
            "id": r["id"],
            "job_title": r["title"],
            "company": r["company"],
            "status": r["status"],
            "system_prompt": "",
            "input_text": prompt,
            "output_text": r["ats_gap_report"] or "",
        })
    return {"samples": samples, "total": len(samples), "type": "ats_resume"}


@app.get("/api/imitate/samples")
def imitate_samples(type: str = "cover_letter", limit: int = 5):
    """Return the assembled generation prompt Peregrine would send to its LLM.

    Each sample has:
      system_prompt  the system context (candidate voice, career summary)
      input_text     the full assembled user prompt (JD + resume + mission + style examples)
      output_text    existing generated output for comparison (may be empty)

    Avocet sends system_prompt + input_text through different local models to
    compare which best replicates Peregrine's generation quality.

    type: cover_letter | company_research | interview_prep | ats_resume
    """
    limit = max(1, min(limit, 20))
    db = _get_db()
    profile = _imitate_load_profile()

    try:
        if type == "cover_letter":
            result = _imitate_cover_letter(db, profile, limit)
        elif type == "company_research":
            result = _imitate_company_research(db, profile, limit)
        elif type == "interview_prep":
            result = _imitate_interview_prep(db, profile, limit)
        elif type == "ats_resume":
            result = _imitate_ats_resume(db, profile, limit)
        else:
            raise HTTPException(
                400,
                f"Unknown type '{type}'. Use: cover_letter, company_research, interview_prep, ats_resume",
            )
    finally:
        db.close()

    return result


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


class LogContactBody(BaseModel):
    direction:   str
    subject:     str
    from_addr:   Optional[str] = None
    body:        Optional[str] = None
    received_at: Optional[str] = None


@app.post("/api/jobs/{job_id}/contacts")
def log_contact(job_id: int, payload: LogContactBody):
    """Log a manually entered inbound or outbound email contact for a job."""
    db = _get_db()
    received_at = payload.received_at or datetime.utcnow().isoformat()
    db.execute(
        "INSERT INTO job_contacts (job_id, direction, subject, from_addr, body, received_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (job_id, payload.direction, payload.subject, payload.from_addr, payload.body, received_at),
    )
    db.commit()
    db.close()
    return {"ok": True}


class InterviewDateBody(BaseModel):
    interview_date: Optional[str] = None


@app.patch("/api/jobs/{job_id}/interview_date")
def set_interview_date(job_id: int, payload: InterviewDateBody):
    """Set or clear the interview date for a job without changing its pipeline status."""
    interview_date = payload.interview_date  # ISO string or null
    db = _get_db()
    db.execute("UPDATE jobs SET interview_date = ? WHERE id = ?", (interview_date, job_id))
    db.commit()
    db.close()
    return {"ok": True}


@app.post("/api/jobs/{job_id}/calendar_push")
def calendar_push(job_id: int):
    """Push the job's interview event to the first configured calendar integration."""
    from scripts.calendar_push import push_interview_event
    db_path = Path(_request_db.get() or DB_PATH)
    cfg_dir = db_path.parent / "config"
    result = push_interview_event(
        db_path=db_path,
        job_id=job_id,
        config_dir=cfg_dir,
    )
    if not result.get("ok"):
        raise HTTPException(400, result.get("error", "Calendar push failed"))
    return result


# ── Survey endpoints ─────────────────────────────────────────────────────────

# Module-level imports so tests can patch dev_api.LLMRouter etc.
from scripts.llm_router import LLMRouter
from scripts.db import insert_survey_response, get_survey_responses

from scripts.survey_assistant import (
    SURVEY_SYSTEM as _SURVEY_SYSTEM,
    build_text_prompt as _build_text_prompt,
    build_image_prompt as _build_image_prompt,
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
    import json as _json
    from scripts.task_runner import submit_task
    params = _json.dumps({
        "text":      body.text,
        "image_b64": body.image_b64,
        "mode":      body.mode,
    })
    try:
        task_id, is_new = submit_task(
            db_path=Path(_request_db.get() or DB_PATH),
            task_type="survey_analyze",
            job_id=job_id,
            params=params,
        )
        return {"task_id": task_id, "is_new": is_new}
    except Exception as e:
        raise HTTPException(500, str(e))


# ── GET /api/jobs/:id/survey/analyze/task ────────────────────────────────────

@app.get("/api/jobs/{job_id}/survey/analyze/task")
def survey_analyze_task(job_id: int, task_id: Optional[int] = None):
    import json as _json
    db = _get_db()
    if task_id is not None:
        row = db.execute(
            "SELECT status, stage, error FROM background_tasks WHERE id = ? AND job_id = ?",
            (task_id, job_id),
        ).fetchone()
    else:
        row = db.execute(
            "SELECT status, stage, error FROM background_tasks "
            "WHERE task_type = 'survey_analyze' AND job_id = ? "
            "ORDER BY id DESC LIMIT 1",
            (job_id,),
        ).fetchone()
    db.close()
    if not row:
        return {"status": "none", "stage": None, "result": None, "message": None}
    result = None
    message = row["error"]
    if row["status"] == "completed" and row["error"]:
        try:
            result = _json.loads(row["error"])
            message = None
        except (ValueError, TypeError):
            pass
    return {
        "status":  row["status"],
        "stage":   row["stage"],
        "result":  result,
        "message": message,
    }


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
        db_path=Path(_request_db.get() or DB_PATH),
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
    return get_survey_responses(db_path=Path(_request_db.get() or DB_PATH), job_id=job_id)


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


# ── POST /api/jobs/:id/hired-feedback ─────────────────────────────────────────

class HiredFeedbackPayload(BaseModel):
    what_helped: str = ""
    factors: list[str] = []

@app.post("/api/jobs/{job_id}/hired-feedback")
def save_hired_feedback(job_id: int, payload: HiredFeedbackPayload):
    _demo_guard()
    db = _get_db()
    row = db.execute("SELECT status FROM jobs WHERE id = ?", (job_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Job not found")
    if row["status"] != "hired":
        raise HTTPException(400, "Feedback only accepted for hired jobs")
    db.execute(
        "UPDATE jobs SET hired_feedback = ? WHERE id = ?",
        (json.dumps({"what_helped": payload.what_helped, "factors": payload.factors}), job_id),
    )
    db.commit()
    db.close()
    return {"ok": True}


# ── GET /api/contacts ──────────────────────────────────────────────────────────

@app.get("/api/contacts")
def list_contacts(job_id: Optional[int] = None, direction: Optional[str] = None,
                  search: Optional[str] = None, limit: int = 100, offset: int = 0):
    db = _get_db()
    query = """
        SELECT jc.id, jc.job_id, jc.direction, jc.subject, jc.from_addr, jc.to_addr,
               jc.received_at, jc.stage_signal,
               j.title AS job_title, j.company AS job_company
        FROM job_contacts jc
        LEFT JOIN jobs j ON j.id = jc.job_id
        WHERE 1=1
    """
    params: list = []
    if job_id is not None:
        query += " AND jc.job_id = ?"
        params.append(job_id)
    if direction:
        query += " AND jc.direction = ?"
        params.append(direction)
    if search:
        query += " AND (jc.from_addr LIKE ? OR jc.to_addr LIKE ? OR jc.subject LIKE ?)"
        like = f"%{search}%"
        params += [like, like, like]
    query += " ORDER BY jc.received_at DESC LIMIT ? OFFSET ?"
    params += [limit, offset]
    rows = db.execute(query, params).fetchall()
    total = db.execute(
        "SELECT COUNT(*) FROM job_contacts" + (" WHERE job_id = ?" if job_id else ""),
        ([job_id] if job_id else []),
    ).fetchone()[0]
    db.close()
    return {"total": total, "contacts": [dict(r) for r in rows]}


# ── References ─────────────────────────────────────────────────────────────────

class ReferencePayload(BaseModel):
    name:         str
    relationship: str = ""
    company:      str = ""
    email:        str = ""
    phone:        str = ""
    notes:        str = ""
    tags:         list[str] = []

class PrepEmailPayload(BaseModel):
    job_id: int

class RecLetterPayload(BaseModel):
    job_id:       int
    talking_points: str = ""


@app.get("/api/references")
def list_references():
    db = _get_db()
    rows = db.execute(
        "SELECT * FROM references_ ORDER BY name ASC"
    ).fetchall()
    db.close()
    return [dict(r) for r in rows]


@app.post("/api/references")
def create_reference(payload: ReferencePayload):
    db = _get_db()
    cur = db.execute(
        """INSERT INTO references_ (name, relationship, company, email, phone, notes, tags)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (payload.name, payload.relationship, payload.company,
         payload.email, payload.phone, payload.notes,
         json.dumps(payload.tags)),
    )
    db.commit()
    row = db.execute("SELECT * FROM references_ WHERE id = ?", (cur.lastrowid,)).fetchone()
    db.close()
    return dict(row)


@app.patch("/api/references/{ref_id}")
def update_reference(ref_id: int, payload: ReferencePayload):
    db = _get_db()
    row = db.execute("SELECT id FROM references_ WHERE id = ?", (ref_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Reference not found")
    db.execute(
        """UPDATE references_ SET name=?, relationship=?, company=?, email=?, phone=?,
           notes=?, tags=?, updated_at=datetime('now') WHERE id=?""",
        (payload.name, payload.relationship, payload.company,
         payload.email, payload.phone, payload.notes,
         json.dumps(payload.tags), ref_id),
    )
    db.commit()
    updated = db.execute("SELECT * FROM references_ WHERE id = ?", (ref_id,)).fetchone()
    db.close()
    return dict(updated)


@app.delete("/api/references/{ref_id}")
def delete_reference(ref_id: int):
    db = _get_db()
    db.execute("DELETE FROM references_ WHERE id = ?", (ref_id,))
    db.commit()
    db.close()
    return {"ok": True}


@app.get("/api/references/for-job/{job_id}")
def references_for_job(job_id: int):
    db = _get_db()
    rows = db.execute(
        """SELECT r.*, jr.prep_email, jr.rec_letter, jr.id AS jr_id
           FROM references_ r
           JOIN job_references jr ON jr.reference_id = r.id
           WHERE jr.job_id = ?
           ORDER BY r.name ASC""",
        (job_id,),
    ).fetchall()
    db.close()
    return [dict(r) for r in rows]


@app.post("/api/references/{ref_id}/link-job")
def link_reference_to_job(ref_id: int, body: PrepEmailPayload):
    db = _get_db()
    try:
        db.execute(
            "INSERT INTO job_references (job_id, reference_id) VALUES (?, ?)",
            (body.job_id, ref_id),
        )
        db.commit()
    except Exception:
        pass  # already linked
    db.close()
    return {"ok": True}


@app.delete("/api/references/{ref_id}/unlink-job/{job_id}")
def unlink_reference_from_job(ref_id: int, job_id: int):
    db = _get_db()
    db.execute(
        "DELETE FROM job_references WHERE reference_id = ? AND job_id = ?",
        (ref_id, job_id),
    )
    db.commit()
    db.close()
    return {"ok": True}


@app.post("/api/references/{ref_id}/prep-email")
def generate_prep_email(ref_id: int, payload: PrepEmailPayload):
    """Draft a short 'heads up' email to send a reference before they hear from the hiring team."""
    db = _get_db()
    ref_row = db.execute("SELECT * FROM references_ WHERE id = ?", (ref_id,)).fetchone()
    if not ref_row:
        db.close()
        raise HTTPException(404, "Reference not found")
    job_row = db.execute(
        "SELECT title, company, description FROM jobs WHERE id = ?", (payload.job_id,)
    ).fetchone()
    if not job_row:
        db.close()
        raise HTTPException(404, "Job not found")
    ref = dict(ref_row)
    job = dict(job_row)
    db.close()

    prompt = f"""Draft a short, warm email to send to a professional reference before a job interview.

Reference: {ref['name']} ({ref['relationship']} at {ref['company']})
Role applying for: {job['title']} at {job['company']}
Job description excerpt: {(job['description'] or '')[:500]}

The email should:
- Be 3-4 short paragraphs max
- Thank them for being a reference
- Briefly describe the role and why it's a good fit
- Mention 1-2 specific accomplishments they could speak to
- Give them a heads-up they may be contacted soon
- Be warm and professional, not overly formal

Return only the email body (no subject line)."""

    try:
        from scripts.llm_router import LLMRouter
        router = LLMRouter()
        email_text = router.complete(prompt)
    except Exception as e:
        raise HTTPException(500, f"LLM generation failed: {e}")

    # Persist to job_references
    db = _get_db()
    db.execute(
        """INSERT INTO job_references (job_id, reference_id, prep_email)
           VALUES (?, ?, ?)
           ON CONFLICT(job_id, reference_id) DO UPDATE SET prep_email = excluded.prep_email""",
        (payload.job_id, ref_id, email_text),
    )
    db.commit()
    db.close()
    return {"prep_email": email_text}


@app.post("/api/references/{ref_id}/rec-letter")
def generate_rec_letter(ref_id: int, payload: RecLetterPayload):
    """Draft a recommendation letter the reference can edit and send on their letterhead."""
    db = _get_db()
    ref_row = db.execute("SELECT * FROM references_ WHERE id = ?", (ref_id,)).fetchone()
    if not ref_row:
        db.close()
        raise HTTPException(404, "Reference not found")
    job_row = db.execute(
        "SELECT title, company, description FROM jobs WHERE id = ?", (payload.job_id,)
    ).fetchone()
    if not job_row:
        db.close()
        raise HTTPException(404, "Job not found")
    ref = dict(ref_row)
    job = dict(job_row)
    db.close()

    prompt = f"""Draft a professional recommendation letter that {ref['name']} ({ref['relationship']}) could send on their letterhead for a candidate applying to {job['title']} at {job['company']}.

Key talking points to highlight: {payload.talking_points or 'general professional excellence, collaboration, initiative'}

The letter should:
- Be addressed generically (Dear Hiring Manager)
- Be 3-4 paragraphs
- Sound natural — written from the recommender's voice, not the candidate's
- Highlight specific, credible observations a {ref['relationship']} would have
- Close with strong endorsement and contact offer

Return only the letter body."""

    try:
        from scripts.llm_router import LLMRouter
        router = LLMRouter()
        letter_text = router.complete(prompt)
    except Exception as e:
        raise HTTPException(500, f"LLM generation failed: {e}")

    db = _get_db()
    db.execute(
        """INSERT INTO job_references (job_id, reference_id, rec_letter)
           VALUES (?, ?, ?)
           ON CONFLICT(job_id, reference_id) DO UPDATE SET rec_letter = excluded.rec_letter""",
        (payload.job_id, ref_id, letter_text),
    )
    db.commit()
    db.close()
    return {"rec_letter": letter_text}


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
        f"applied_at, phone_screen_at, interviewing_at, offer_at, hired_at, survey_at, hired_feedback "
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


@app.get("/api/tasks/active")
def list_active_tasks_envelope():
    """Envelope wrapper for the Vue task indicator poll — returns {count, tasks}."""
    from scripts.db import get_active_tasks
    tasks = get_active_tasks(_db_path())
    return {"count": len(tasks), "tasks": tasks}


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


_HEIMDALL_URL         = os.environ.get("HEIMDALL_URL", "https://license.circuitforge.tech")
_HEIMDALL_ADMIN_TOKEN = os.environ.get("HEIMDALL_ADMIN_TOKEN", "")


def _resolve_cloud_tier() -> str:
    """Resolve the current user's tier from Heimdall for cloud API responses.

    Extracts the user_id from the per-request DB path set by cloud_session_middleware
    (format: <CLOUD_DATA_ROOT>/<user_id>/peregrine/staging.db), then calls Heimdall
    /admin/cloud/resolve.  Returns "free" on any error so the app degrades gracefully.
    """
    if not _HEIMDALL_ADMIN_TOKEN:
        _log.warning("HEIMDALL_ADMIN_TOKEN not set — defaulting API tier to free")
        return "free"
    db_path = _request_db.get()
    if not db_path:
        return "free"
    # Extract user_id: .../menagerie-data/<user_id>/peregrine/staging.db
    try:
        user_id = Path(db_path).parts[-3]
    except IndexError:
        _log.warning("_resolve_cloud_tier: unexpected db_path format: %s", db_path)
        return "free"
    try:
        resp = requests.post(
            f"{_HEIMDALL_URL}/admin/cloud/resolve",
            json={"user_id": user_id, "product": "peregrine"},
            headers={"Authorization": f"Bearer {_HEIMDALL_ADMIN_TOKEN}"},
            timeout=5,
        )
        if resp.status_code == 200:
            return resp.json().get("tier", "free")
        if resp.status_code == 404:
            return "free"
        _log.warning("Heimdall resolve returned %s for user %s", resp.status_code, user_id)
    except Exception as exc:
        _log.warning("Heimdall tier resolve failed for user %s: %s", user_id, exc)
    return "free"


# ── GET /api/config/app ───────────────────────────────────────────────────────

@app.get("/api/config/app")
def get_app_config():
    import os
    profile = os.environ.get("INFERENCE_PROFILE", "cpu")
    valid_profiles = {"remote", "cpu", "single-gpu", "dual-gpu"}
    valid_tiers = {"free", "paid", "premium", "ultra"}

    # Cloud: resolve tier from Heimdall (APP_TIER env is single-tenant only).
    is_cloud = os.environ.get("CLOUD_MODE", "").lower() in ("1", "true")
    if is_cloud:
        raw_tier = _resolve_cloud_tier()
    else:
        raw_tier = os.environ.get("APP_TIER", "free")
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

class EducationEntry(BaseModel):
    institution: str = ""; degree: str = ""; field: str = ""
    start_date: str = ""; end_date: str = ""

class ResumePayload(BaseModel):
    name: str = ""; email: str = ""; phone: str = ""; linkedin_url: str = ""
    surname: str = ""; address: str = ""; city: str = ""; zip_code: str = ""; date_of_birth: str = ""
    career_summary: str = ""
    experience: List[WorkEntry] = []
    education: List[EducationEntry] = []
    achievements: List[str] = []
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

    AIHawk stores:  key_responsibilities (numbered dicts), employment_period, skills_acquired
    Vue WorkEntry:  responsibilities (str), period (str), skills (list)
    If already in Vue format (has 'period' key or 'responsibilities' key), pass through unchanged.
    """
    out = []
    for e in raw:
        if not isinstance(e, dict):
            continue
        # Already in Vue WorkEntry format — pass through
        if "period" in e or "responsibilities" in e:
            out.append({
                "title":            e.get("title", ""),
                "company":          e.get("company", ""),
                "period":           e.get("period", ""),
                "location":         e.get("location", ""),
                "industry":         e.get("industry", ""),
                "responsibilities": e.get("responsibilities", ""),
                "skills":           e.get("skills") or [],
            })
            continue
        # AIHawk format
        resps = e.get("key_responsibilities", {})
        if isinstance(resps, dict):
            resp_text = "\n".join(v for v in resps.values() if isinstance(v, str))
        elif isinstance(resps, list):
            resp_text = "\n".join(str(r) for r in resps)
        else:
            resp_text = str(resps)
        period = e.get("employment_period", "")
        skills_raw = e.get("skills_acquired", [])
        skills = skills_raw if isinstance(skills_raw, list) else []
        out.append({
            "title":            e.get("position", ""),
            "company":          e.get("company", ""),
            "period":           period,
            "location":         e.get("location", ""),
            "industry":         e.get("industry", ""),
            "responsibilities": resp_text,
            "skills":           skills,
        })
    return out


@app.get("/api/settings/resume")
def get_resume():
    try:
        resume_path = _resume_path()
        if not resume_path.exists():
            # Backward compat: check user.yaml for career_summary
            _uy = Path(_user_yaml_path())
            if _uy.exists():
                uy = yaml.safe_load(_uy.read_text(encoding="utf-8")) or {}
                if uy.get("career_summary"):
                    return {"exists": False, "legacy_career_summary": uy["career_summary"]}
            return {"exists": False}
        with open(resume_path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        data["exists"] = True
        if "experience" in data and isinstance(data["experience"], list):
            data["experience"] = _normalize_experience(data["experience"])
        # Backward compat: if career_summary missing from YAML, try user.yaml
        if not data.get("career_summary"):
            _uy = Path(_user_yaml_path())
            if _uy.exists():
                uy = yaml.safe_load(_uy.read_text(encoding="utf-8")) or {}
                data["career_summary"] = uy.get("career_summary", "")
        return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/api/settings/resume")
def save_resume(payload: ResumePayload):
    """Save resume profile. If a default library entry exists, sync content back to it."""
    import json as _json
    from scripts.db import (
        get_resume as _get_resume,
        update_resume_content as _update_content,
    )
    from scripts.resume_sync import profile_to_library
    try:
        resume_path = _resume_path()
        resume_path.parent.mkdir(parents=True, exist_ok=True)
        with open(resume_path, "w", encoding="utf-8") as f:
            yaml.dump(payload.model_dump(), f, allow_unicode=True, default_flow_style=False)

        # Profile→library sync: if a default resume exists, update it
        synced_id: int | None = None
        db_path = Path(_request_db.get() or DB_PATH)
        _uy = Path(_user_yaml_path())
        if _uy.exists():
            profile_meta = yaml.safe_load(_uy.read_text(encoding="utf-8")) or {}
            default_id = profile_meta.get("default_resume_id")
            if default_id:
                entry = _get_resume(db_path, int(default_id))
                if entry:
                    text, struct = profile_to_library(payload.model_dump())
                    _update_content(db_path, int(default_id), text=text, struct_json=_json.dumps(struct))
                    synced_id = int(default_id)

        return {"ok": True, "synced_library_entry_id": synced_id}
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

def _get_valid_jobspy_boards() -> set[str]:
    """Return the set of board names supported by the installed JobSpy version."""
    try:
        from jobspy import Site
        return {s.value for s in Site}
    except Exception:
        return {"linkedin", "indeed", "zip_recruiter", "glassdoor", "google"}


@app.get("/api/settings/search")
def get_search_prefs():
    try:
        p = _search_prefs_path()
        if not p.exists():
            return {}
        with open(p) as f:
            data = yaml.safe_load(f) or {}

        # Handle both old `default: {...}` format and new `profiles: [...]` format.
        from scripts.discover import _normalize_profiles
        normalized = _normalize_profiles(data)
        profiles = normalized.get("profiles", [])
        profile = next((pr for pr in profiles if pr.get("name") == "default"), None)
        if profile is None:
            # Fall back to reading the raw default key (covers edge cases)
            profile = data.get("default", {})

        # Annotate job_boards with a `supported` flag so the UI can distinguish
        # boards that produce real results from ones that are not yet implemented.
        valid = _get_valid_jobspy_boards()
        job_boards = profile.get("job_boards", [])
        if job_boards:
            profile["job_boards"] = [
                {**b, "supported": b.get("name", "") in valid}
                for b in job_boards
            ]
        # Also expose boards list (canonical format) with the same annotation
        boards = profile.get("boards", [])
        if boards and not job_boards:
            profile["job_boards"] = [
                {"name": b, "enabled": True, "supported": b in valid}
                for b in boards
            ]

        return profile
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


class ResumeTagSuggestPayload(BaseModel):
    type: str          # "skills" | "domains" | "keywords"
    current: List[str] = []


@app.post("/api/settings/resume/suggest-tags")
def suggest_resume_tags(payload: ResumeTagSuggestPayload):
    """LLM-generate suggestions for skills, domains, or keywords based on the resume profile."""
    context = _resume_context_snippet()
    current_str = ", ".join(payload.current) if payload.current else "none"

    if payload.type == "skills":
        prompt = (
            "You are a career advisor helping a job seeker build their skills list.\n\n"
            + (f"Candidate background:\n{context}\n\n" if context else "")
            + f"Skills they already have listed: {current_str}\n\n"
            "Suggest 8 additional skills, tools, or technologies they likely have based on their "
            "background but haven't listed yet. Focus on concrete, ATS-friendly terms. "
            "Return only a JSON array of strings, no other text. "
            "Example: [\"HubSpot\", \"Tableau\", \"SQL\"]"
        )
    elif payload.type == "domains":
        prompt = (
            "You are a career advisor helping a job seeker define the industry domains they work in.\n\n"
            + (f"Candidate background:\n{context}\n\n" if context else "")
            + f"Domains they already have listed: {current_str}\n\n"
            "Suggest 6 additional industry domains, verticals, or market segments relevant to their "
            "background that they haven't listed. Think: 'B2B SaaS', 'enterprise software', "
            "'financial services', etc. "
            "Return only a JSON array of strings, no other text."
        )
    elif payload.type == "keywords":
        prompt = (
            "You are a resume ATS (applicant tracking system) specialist helping a job seeker "
            "identify important keywords recruiters search for.\n\n"
            + (f"Candidate background:\n{context}\n\n" if context else "")
            + f"Keywords they already have listed: {current_str}\n\n"
            "Suggest 10 additional ATS keywords, phrases, or buzzwords that recruiters in their "
            "field commonly search for — metrics, methodologies, frameworks, or role-specific "
            "terminology they may have missed. "
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


# ── Settings: per-user cover-letter model ────────────────────────────────────

@app.get("/api/settings/llm/cover-letter-model")
def get_cover_letter_model():
    """Return the user's custom cover letter model (from per-user llm.yaml if set)."""
    cfg_path = _config_dir() / "llm.yaml"
    if cfg_path.exists():
        with open(cfg_path) as f:
            data = yaml.safe_load(f) or {}
        # Convention: the first backend in fallback_order that targets cover letters
        # is stored under backends.cover_letter.model
        model = (data.get("backends", {}).get("cover_letter") or {}).get("model", "")
        return {"model": model}
    return {"model": ""}


class CoverLetterModelPayload(BaseModel):
    model: str


@app.put("/api/settings/llm/cover-letter-model")
def set_cover_letter_model(payload: CoverLetterModelPayload):
    """Write the custom cover letter model into the per-user llm.yaml."""
    cfg_path = _config_dir() / "llm.yaml"
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    data: dict = {}
    if cfg_path.exists():
        with open(cfg_path) as f:
            data = yaml.safe_load(f) or {}
    backends = data.setdefault("backends", {})
    if payload.model:
        backends["cover_letter"] = {
            "type": "openai_compat",
            "enabled": True,
            "base_url": "http://localhost:11434/v1",
            "model": payload.model,
            "api_key": "any",
            "supports_images": False,
        }
        order = data.setdefault("fallback_order", [])
        if "cover_letter" not in order:
            order.insert(0, "cover_letter")
    else:
        # Clear custom model — remove the backend and drop from fallback order
        backends.pop("cover_letter", None)
        data["fallback_order"] = [b for b in data.get("fallback_order", []) if b != "cover_letter"]
    with open(cfg_path, "w") as f:
        yaml.dump(data, f, allow_unicode=True, default_flow_style=False)
    return {"ok": True}


@app.get("/api/settings/llm/ollama-models")
def get_ollama_models():
    """Return available Ollama models by querying the local Ollama API."""
    try:
        ollama_host = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
        if not ollama_host.startswith("http"):
            ollama_host = f"http://{ollama_host}"
        resp = requests.get(f"{ollama_host.rstrip('/')}/api/tags", timeout=3)
        if resp.status_code == 200:
            models = [m["name"] for m in resp.json().get("models", [])]
            return {"models": models}
    except Exception:
        pass
    return {"models": []}


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
        try:
            from scripts.user_profile import UserProfile
            _opted_in = UserProfile(Path(_user_yaml_path())).training_export_opt_in
        except Exception:
            _opted_in = False
        # Stub quota for self-hosted; cloud overrides via its own middleware
        return {"status": status, "pairs_count": pairs_count, "quota_remaining": None, "opted_in": _opted_in}
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


# ── Settings: Fine-Tune — Training Export ─────────────────────────────────────

class TrainingOptInBody(BaseModel):
    enabled: bool


def _training_opt_in_required() -> None:
    """Raise 403 if training_export_opt_in is not enabled in user profile."""
    try:
        from scripts.user_profile import UserProfile
        profile = UserProfile(Path(_user_yaml_path()))
        if not profile.training_export_opt_in:
            raise HTTPException(
                status_code=403,
                detail="Training export is not enabled. Enable it in Settings → Fine-Tune.",
            )
    except FileNotFoundError:
        raise HTTPException(
            status_code=403,
            detail="Training export is not enabled. Enable it in Settings → Fine-Tune.",
        )


@app.patch("/api/settings/fine-tune/opt-in")
def set_training_opt_in(body: TrainingOptInBody):
    try:
        from scripts.user_profile import UserProfile
        profile = UserProfile(Path(_user_yaml_path()))
        profile.training_export_opt_in = body.enabled
        profile.save()
        return {"ok": True, "enabled": profile.training_export_opt_in}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/settings/fine-tune/db-pairs")
def list_db_pairs():
    _training_opt_in_required()
    try:
        from scripts.db import get_db_pairs
        db_path = Path(_request_db.get() or DB_PATH)
        pairs = get_db_pairs(db_path)
        excluded_count = sum(1 for p in pairs if p["excluded"])
        return {
            "pairs": pairs,
            "total": len(pairs),
            "excluded_count": excluded_count,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.patch("/api/settings/fine-tune/db-pairs/{job_id}/exclude")
def exclude_db_pair(job_id: int):
    _training_opt_in_required()
    try:
        from scripts.db import set_training_exclusion
        set_training_exclusion(Path(_request_db.get() or DB_PATH), job_id, excluded=True)
        return {"ok": True, "job_id": job_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.patch("/api/settings/fine-tune/db-pairs/{job_id}/include")
def include_db_pair(job_id: int):
    _training_opt_in_required()
    try:
        from scripts.db import set_training_exclusion
        set_training_exclusion(Path(_request_db.get() or DB_PATH), job_id, excluded=False)
        return {"ok": True, "job_id": job_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/settings/fine-tune/export")
def export_training_jsonl():
    _training_opt_in_required()
    import json as _json
    from fastapi.responses import StreamingResponse
    from scripts.db import get_training_pairs

    db_path = Path(_request_db.get() or DB_PATH)
    db_pairs = get_training_pairs(db_path)
    file_pairs = _load_training_pairs()

    def _generate():
        for pair in db_pairs:
            yield _json.dumps(pair, ensure_ascii=False) + "\n"
        for pair in file_pairs:
            record = dict(pair)
            record.setdefault("source", "file")
            yield _json.dumps(record, ensure_ascii=False) + "\n"

    return StreamingResponse(
        _generate(),
        media_type="application/x-ndjson",
        headers={"Content-Disposition": 'attachment; filename="peregrine_training_pairs.jsonl"'},
    )


# Phase 2 stubs — reserved, not yet implemented
@app.post("/api/settings/fine-tune/cloud-request")
def cloud_finetune_request():
    raise HTTPException(status_code=501, detail="Cloud fine-tune is not yet available.")


@app.get("/api/settings/fine-tune/cloud-status")
def cloud_finetune_status():
    raise HTTPException(status_code=501, detail="Cloud fine-tune is not yet available.")


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

_WIZARD_PROFILES = ("remote", "cpu", "single-gpu", "dual-gpu", "cf-orch")
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
        # Persist search preferences to search_profiles.yaml in canonical format:
        #   profiles: [{name, titles, locations, boards, ...}]
        titles = data.get("titles", [])
        locations = data.get("locations", [])
        search_path = _search_prefs_path()
        existing_search: dict = {}
        if search_path.exists():
            with open(search_path) as f:
                existing_search = yaml.safe_load(f) or {}

        # Normalize legacy wizard format on read so we can update in place
        from scripts.discover import _normalize_profiles as _norm
        existing_search = _norm(existing_search)

        # Find or create the "default" profile entry
        profiles_list = existing_search.get("profiles", [])
        default_profile = next((p for p in profiles_list if p.get("name") == "default"), None)
        if default_profile is None:
            default_profile = {"name": "default"}
            profiles_list.append(default_profile)
        default_profile["titles"] = titles
        default_profile["locations"] = locations
        existing_search["profiles"] = profiles_list
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


def _fetch_cforch_nodes() -> list[dict]:
    """Query cf-orch coordinator for live node + GPU data. Returns [] on any error."""
    url = os.environ.get("CF_ORCH_URL", "").rstrip("/")
    if not url:
        return []
    try:
        import urllib.request, json as _json
        req = urllib.request.Request(f"{url}/api/nodes", headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = _json.loads(resp.read())
            return data.get("nodes", [])
    except Exception:
        return []


@app.get("/api/wizard/hardware")
def wizard_hardware():
    """Detect local GPUs, suggest an inference profile, and report cf-orch nodes."""
    gpus = _detect_gpus()
    suggested = _suggest_profile(gpus)

    # Enrich with cf-orch cluster data when coordinator URL is configured
    orch_nodes = _fetch_cforch_nodes()
    orch_summary = []
    for node in orch_nodes:
        for gpu in node.get("gpus", []):
            orch_summary.append({
                "node": node["node_id"],
                "name": gpu["name"],
                "vram_total_mb": gpu["vram_total_mb"],
                "vram_free_mb": gpu["vram_free_mb"],
            })

    return {
        "gpus": gpus,
        "suggested_profile": suggested,
        "profiles": list(_WIZARD_PROFILES),
        "cf_orch_available": len(orch_nodes) > 0,
        "cf_orch_gpus": orch_summary,
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


# ── Messaging models ──────────────────────────────────────────────────────────

class MessageCreateBody(BaseModel):
    job_id: Optional[int] = None
    job_contact_id: Optional[int] = None
    type: str = "email"
    direction: Optional[str] = None
    subject: Optional[str] = None
    body: Optional[str] = None
    from_addr: Optional[str] = None
    to_addr: Optional[str] = None
    template_id: Optional[int] = None
    logged_at: Optional[str] = None


class MessageUpdateBody(BaseModel):
    body: str


class TemplateCreateBody(BaseModel):
    title: str
    category: str = "custom"
    subject_template: Optional[str] = None
    body_template: str


class TemplateUpdateBody(BaseModel):
    title: Optional[str] = None
    category: Optional[str] = None
    subject_template: Optional[str] = None
    body_template: Optional[str] = None


# ── Messaging (MIT) ───────────────────────────────────────────────────────────

@app.get("/api/messages")
def get_messages(
    job_id: Optional[int] = None,
    type: Optional[str] = None,
    direction: Optional[str] = None,
    limit: int = Query(default=100, ge=1, le=1000),
):
    from scripts.messaging import list_messages
    return list_messages(
        Path(_request_db.get() or DB_PATH),
        job_id=job_id, type=type, direction=direction, limit=limit,
    )


@app.post("/api/messages")
def post_message(body: MessageCreateBody):
    from scripts.messaging import create_message
    return create_message(Path(_request_db.get() or DB_PATH), **body.model_dump())


@app.delete("/api/messages/{message_id}")
def del_message(message_id: int):
    from scripts.messaging import delete_message
    try:
        delete_message(Path(_request_db.get() or DB_PATH), message_id)
        return {"ok": True}
    except KeyError:
        raise HTTPException(404, "message not found")


@app.put("/api/messages/{message_id}")
def put_message(message_id: int, body: MessageUpdateBody):
    from scripts.messaging import update_message_body
    try:
        return update_message_body(Path(_request_db.get() or DB_PATH), message_id, body.body)
    except KeyError:
        raise HTTPException(404, "message not found")


@app.get("/api/message-templates")
def get_templates():
    from scripts.messaging import list_templates
    return list_templates(Path(_request_db.get() or DB_PATH))


@app.post("/api/message-templates")
def post_template(body: TemplateCreateBody):
    from scripts.messaging import create_template
    return create_template(Path(_request_db.get() or DB_PATH), **body.model_dump())


@app.put("/api/message-templates/{template_id}")
def put_template(template_id: int, body: TemplateUpdateBody):
    from scripts.messaging import update_template
    try:
        return update_template(
            Path(_request_db.get() or DB_PATH),
            template_id,
            **body.model_dump(exclude_none=True),
        )
    except PermissionError:
        raise HTTPException(403, "cannot modify built-in templates")
    except KeyError:
        raise HTTPException(404, "template not found")


@app.delete("/api/message-templates/{template_id}")
def del_template(template_id: int):
    from scripts.messaging import delete_template
    try:
        delete_template(Path(_request_db.get() or DB_PATH), template_id)
        return {"ok": True}
    except PermissionError:
        raise HTTPException(403, "cannot delete built-in templates")
    except KeyError:
        raise HTTPException(404, "template not found")


# ── LLM Reply Draft (BSL 1.1) ─────────────────────────────────────────────────

def _get_effective_tier() -> str:
    """Resolve effective tier: Heimdall in cloud mode, APP_TIER env var in single-tenant."""
    if _CLOUD_MODE:
        return _resolve_cloud_tier()
    from app.wizard.tiers import effective_tier
    return effective_tier()


@app.post("/api/contacts/{contact_id}/draft-reply")
def draft_reply(contact_id: int):
    """Generate an LLM draft reply for an inbound job_contacts row. Tier-gated."""
    from app.wizard.tiers import can_use, has_configured_llm
    from scripts.messaging import create_message
    from scripts.llm_reply_draft import generate_draft_reply

    db_path = Path(_request_db.get() or DB_PATH)
    tier = _get_effective_tier()
    if not can_use(tier, "llm_reply_draft", has_byok=has_configured_llm()):
        raise HTTPException(402, detail={"error": "tier_required", "min_tier": "free+byok"})

    con = _get_db()
    row = con.execute("SELECT * FROM job_contacts WHERE id=?", (contact_id,)).fetchone()
    con.close()
    if not row:
        raise HTTPException(404, "contact not found")

    profile = _imitate_load_profile()
    user_name = getattr(profile, "name", "") or ""
    target_role = getattr(profile, "target_role", "") or ""

    cfg_path = db_path.parent / "config" / "llm.yaml"
    draft_body = generate_draft_reply(
        subject=row["subject"] or "",
        from_addr=row["from_addr"] or "",
        body=row["body"] or "",
        user_name=user_name,
        target_role=target_role,
        config_path=cfg_path if cfg_path.exists() else None,
    )
    msg = create_message(
        db_path,
        job_id=row["job_id"],
        job_contact_id=contact_id,
        type="draft",
        direction="outbound",
        subject=f"Re: {row['subject'] or ''}".strip(),
        body=draft_body,
        to_addr=row["from_addr"],
        template_id=None,
        from_addr=None,
    )
    return {"message_id": msg["id"]}


@app.post("/api/messages/{message_id}/approve")
def approve_message_endpoint(message_id: int):
    """Set approved_at=now(). Returns approved body for copy-to-clipboard."""
    from scripts.messaging import approve_message
    try:
        msg = approve_message(Path(_request_db.get() or DB_PATH), message_id)
        return {"body": msg["body"], "approved_at": msg["approved_at"]}
    except KeyError:
        raise HTTPException(404, "message not found")
