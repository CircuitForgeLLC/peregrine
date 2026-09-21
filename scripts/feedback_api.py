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
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError):
        # OSError covers FileNotFoundError (git not installed/not on PATH); the
        # feedback report just falls back to a generic "dev" version label.
        version = "dev"

    # Tier from user.yaml
    tier = "unknown"
    try:
        user = yaml.safe_load((_ROOT / "config" / "user.yaml").read_text()) or {}
        tier = user.get("tier", "unknown")
    except (OSError, yaml.YAMLError, UnicodeDecodeError, AttributeError):
        # config/user.yaml is legitimately absent for many installs (defaults haven't
        # been written yet) — this is an expected, common path, not a real failure, so
        # we deliberately don't log it on every feedback submission; the "unknown"
        # default is already informative in the collected context. UnicodeDecodeError
        # covers a non-UTF-8 file (read_text() isn't caught by OSError), AttributeError
        # covers a malformed non-dict YAML top-level (.get() on a list/scalar) --
        # same reasoning as the llm_backend lookup below.
        pass

    # LLM backend from llm.yaml — report first entry in fallback_order that's enabled
    llm_backend = "unknown"
    try:
        llm = yaml.safe_load((_ROOT / "config" / "llm.yaml").read_text()) or {}
        backends = llm.get("backends", {})
        for name in llm.get("fallback_order", []):
            if backends.get(name, {}).get("enabled", False):
                llm_backend = name
                break
    except (OSError, yaml.YAMLError, UnicodeDecodeError, AttributeError, TypeError):
        # Same reasoning as the tier lookup above: config/llm.yaml missing/malformed is
        # expected for many installs. UnicodeDecodeError covers a non-UTF-8 file
        # (read_text() isn't caught by OSError). AttributeError covers a non-dict
        # `backends` entry (`.get` called on something that isn't a dict). TypeError
        # covers a non-iterable `fallback_order` (e.g. malformed YAML gives an int
        # instead of a list). Not logged on every submission for the same "expected,
        # not a real failure" reason.
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
    path = log_path or (_ROOT / "data" / ".streamlit.log")
    if not path.exists():
        return "(no log file found)"
    lines = path.read_text(errors="replace").splitlines()
    return mask_pii("\n".join(lines[-n:]))


def collect_listings(db_path: Path | None = None, n: int = 5) -> list[dict]:
    """Return the n most-recent job listings — title, company, url only."""
    import sqlite3

    from scripts.db import DEFAULT_DB
    path = db_path or DEFAULT_DB
    with sqlite3.connect(path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT title, company, url FROM jobs ORDER BY id DESC LIMIT ?", (n,)
        ).fetchall()
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
    # Use the bot token when set; fall back to the main API token for dev/self-hosted.
    token = os.environ.get("FORGEJO_BOT_TOKEN") or os.environ.get("FORGEJO_API_TOKEN", "")
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
    token = os.environ.get("FORGEJO_BOT_TOKEN") or os.environ.get("FORGEJO_API_TOKEN", "")
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
    Returns PNG bytes, or None if Playwright is not installed or capture fails.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return None

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
    except Exception:  # noqa: BLE001 -- Playwright browser automation (launch,
        # navigate, wait_for_load_state, screenshot) can raise many distinct
        # playwright.sync_api errors (timeouts, target-closed, connection issues) plus
        # OSError if the Chromium binary itself is missing; per the docstring this
        # function's contract is "return None on any capture failure," never raise, so
        # a screenshot problem doesn't block the rest of the feedback submission.
        return None
