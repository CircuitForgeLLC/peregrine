"""
Feedback API — pure Python backend, no Streamlit imports.
Called directly from app/feedback.py now; wrappable in a FastAPI route later.
"""
from __future__ import annotations

import os
import platform
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import requests
import yaml
from playwright.sync_api import sync_playwright

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


def build_issue_body(form: dict, context: dict, attachments: dict) -> str:
    """Assemble the Forgejo issue markdown body from form data, context, and attachments."""
    _TYPE_LABELS = {"bug": "🐛 Bug", "feature": "✨ Feature Request", "other": "💬 Other"}
    lines: list[str] = [
        f"## {_TYPE_LABELS.get(form.get('type', 'other'), '💬 Other')}",
        "",
        form.get("description", ""),
        "",
    ]

    if form.get("type") == "bug" and form.get("repro"):
        lines += ["### Reproduction Steps", "", form["repro"], ""]

    if context:
        lines += ["### Context", ""]
        for k, v in context.items():
            lines.append(f"- **{k}:** {v}")
        lines.append("")

    if attachments.get("logs"):
        lines += [
            "<details>",
            "<summary>App Logs (last 100 lines)</summary>",
            "",
            "```",
            attachments["logs"],
            "```",
            "</details>",
            "",
        ]

    if attachments.get("listings"):
        lines += ["### Recent Listings", ""]
        for j in attachments["listings"]:
            lines.append(f"- [{j['title']} @ {j['company']}]({j['url']})")
        lines.append("")

    if attachments.get("submitter"):
        lines += ["---", f"*Submitted by: {attachments['submitter']}*"]

    return "\n".join(lines)


def _ensure_labels(
    label_names: list[str], base_url: str, headers: dict, repo: str
) -> list[int]:
    """Look up or create Forgejo labels by name. Returns list of IDs."""
    _COLORS = {
        "beta-feedback": "#0075ca",
        "needs-triage": "#e4e669",
        "bug": "#d73a4a",
        "feature-request": "#a2eeef",
        "question": "#d876e3",
    }
    resp = requests.get(f"{base_url}/repos/{repo}/labels", headers=headers, timeout=10)
    existing = {lb["name"]: lb["id"] for lb in resp.json()} if resp.ok else {}
    ids: list[int] = []
    for name in label_names:
        if name in existing:
            ids.append(existing[name])
        else:
            r = requests.post(
                f"{base_url}/repos/{repo}/labels",
                headers=headers,
                json={"name": name, "color": _COLORS.get(name, "#ededed")},
                timeout=10,
            )
            if r.ok:
                ids.append(r.json()["id"])
    return ids


def create_forgejo_issue(title: str, body: str, labels: list[str]) -> dict:
    """Create a Forgejo issue. Returns {"number": int, "url": str}."""
    token = os.environ.get("FORGEJO_API_TOKEN", "")
    repo = os.environ.get("FORGEJO_REPO", "pyr0ball/peregrine")
    base = os.environ.get("FORGEJO_API_URL", "https://git.opensourcesolarpunk.com/api/v1")
    headers = {"Authorization": f"token {token}", "Content-Type": "application/json"}
    label_ids = _ensure_labels(labels, base, headers, repo)
    resp = requests.post(
        f"{base}/repos/{repo}/issues",
        headers=headers,
        json={"title": title, "body": body, "labels": label_ids},
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()
    return {"number": data["number"], "url": data["html_url"]}


def upload_attachment(
    issue_number: int, image_bytes: bytes, filename: str = "screenshot.png"
) -> str:
    """Upload a screenshot to an existing Forgejo issue. Returns attachment URL."""
    token = os.environ.get("FORGEJO_API_TOKEN", "")
    repo = os.environ.get("FORGEJO_REPO", "pyr0ball/peregrine")
    base = os.environ.get("FORGEJO_API_URL", "https://git.opensourcesolarpunk.com/api/v1")
    headers = {"Authorization": f"token {token}"}
    resp = requests.post(
        f"{base}/repos/{repo}/issues/{issue_number}/assets",
        headers=headers,
        files={"attachment": (filename, image_bytes, "image/png")},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json().get("browser_download_url", "")


def screenshot_page(port: int | None = None) -> bytes | None:
    """
    Capture a screenshot of the running Peregrine UI using Playwright.
    Returns PNG bytes, or None if Playwright is not installed or if capture fails.
    """
    if port is None:
        port = int(os.environ.get("STREAMLIT_PORT", os.environ.get("STREAMLIT_SERVER_PORT", "8502")))

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": 1280, "height": 800})
            page.goto(f"http://localhost:{port}", timeout=10_000)
            page.wait_for_load_state("networkidle", timeout=10_000)
            png = page.screenshot(full_page=False)
            browser.close()
            return png
    except Exception:
        return None
