"""
Feedback API — pure Python backend, no Streamlit imports.
Called directly from app/feedback.py now; wrappable in a FastAPI route later.
"""
from __future__ import annotations

import platform
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import yaml

_ROOT = Path(__file__).parent.parent
_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
_PHONE_RE = re.compile(r"(\+?1[\s\-.]?)?\(?\d{3}\)?[\s\-.]?\d{3}[\s\-.]?\d{4}")


def mask_pii(text: str) -> str:
    """Redact email addresses and phone numbers from text."""
    text = _EMAIL_RE.sub("[email redacted]", text)
    text = _PHONE_RE.sub("[phone redacted]", text)
    return text


def collect_context(page: str) -> dict:
    """Collect app context: page, version, tier, LLM backend, OS, timestamp."""
    # App version from git
    try:
        version = subprocess.check_output(
            ["git", "describe", "--tags", "--always"],
            cwd=_ROOT, text=True, timeout=5,
        ).strip()
    except Exception:
        version = "dev"

    # Tier from user.yaml
    tier = "unknown"
    try:
        user = yaml.safe_load((_ROOT / "config" / "user.yaml").read_text()) or {}
        tier = user.get("tier", "unknown")
    except Exception:
        pass

    # LLM backend from llm.yaml
    llm_backend = "unknown"
    try:
        llm = yaml.safe_load((_ROOT / "config" / "llm.yaml").read_text()) or {}
        llm_backend = llm.get("provider", "unknown")
    except Exception:
        pass

    return {
        "page": page,
        "version": version,
        "tier": tier,
        "llm_backend": llm_backend,
        "os": platform.platform(),
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }


def collect_logs(n: int = 100, log_path: Path | None = None) -> str:
    """Return last n lines of the Streamlit log, with PII masked."""
    path = log_path or (_ROOT / ".streamlit.log")
    if not path.exists():
        return "(no log file found)"
    lines = path.read_text(errors="replace").splitlines()
    return mask_pii("\n".join(lines[-n:]))


def collect_listings(db_path: Path | None = None, n: int = 5) -> list[dict]:
    """Return the n most-recent job listings — title, company, url only."""
    import sqlite3
    from scripts.db import DEFAULT_DB
    path = db_path or DEFAULT_DB
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT title, company, url FROM jobs ORDER BY id DESC LIMIT ?", (n,)
    ).fetchall()
    conn.close()
    return [{"title": r["title"], "company": r["company"], "url": r["url"]} for r in rows]
