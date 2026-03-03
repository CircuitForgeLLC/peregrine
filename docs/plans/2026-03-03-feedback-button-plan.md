# Feedback Button — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a floating feedback button to Peregrine that lets beta testers file Forgejo issues directly from the UI, with optional PII-masked diagnostic data and screenshot attachments.

**Architecture:** Pure Python backend in `scripts/feedback_api.py` (no Streamlit dep, wrappable in FastAPI later) + thin Streamlit shell in `app/feedback.py`. Floating button uses CSS `position: fixed` targeting via `aria-label`. Screenshots via server-side Playwright (capture) and `st.file_uploader` (upload).

**Tech Stack:** Python `requests`, `re`, `playwright` (optional), Streamlit 1.54 (`@st.dialog`), Forgejo REST API v1.

---

## Task 1: Project setup — env config + Playwright dep

**Files:**
- Modify: `.env.example`
- Modify: `requirements.txt`

**Step 1: Add env vars to `.env.example`**

Open `.env.example` and add after the existing API keys block:

```
# Feedback button — Forgejo issue filing
FORGEJO_API_TOKEN=
FORGEJO_REPO=pyr0ball/peregrine
FORGEJO_API_URL=https://git.opensourcesolarpunk.com/api/v1
# GITHUB_TOKEN=          # future — enable when public mirror is active
# GITHUB_REPO=           # future
```

**Step 2: Add playwright to requirements.txt**

Add to `requirements.txt`:

```
playwright>=1.40
```

**Step 3: Install playwright and its browsers**

```bash
conda run -n job-seeker pip install playwright
conda run -n job-seeker playwright install chromium --with-deps
```

Expected: chromium browser downloaded to playwright cache.

**Step 4: Add FORGEJO_API_TOKEN to your local `.env`**

Open `.env` and add:
```
FORGEJO_API_TOKEN=your-forgejo-api-token-here
FORGEJO_REPO=pyr0ball/peregrine
FORGEJO_API_URL=https://git.opensourcesolarpunk.com/api/v1
```

**Step 5: Commit**

```bash
git add requirements.txt .env.example
git commit -m "chore: add playwright dep and Forgejo env config for feedback button"
```

---

## Task 2: Backend — PII masking + context collection

**Files:**
- Create: `scripts/feedback_api.py`
- Create: `tests/test_feedback_api.py`

**Step 1: Write failing tests**

Create `tests/test_feedback_api.py`:

```python
"""Tests for the feedback API backend."""
import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path


# ── mask_pii ──────────────────────────────────────────────────────────────────

def test_mask_pii_email():
    from scripts.feedback_api import mask_pii
    assert mask_pii("contact foo@bar.com please") == "contact [email redacted] please"


def test_mask_pii_phone_dashes():
    from scripts.feedback_api import mask_pii
    assert mask_pii("call 555-123-4567 now") == "call [phone redacted] now"


def test_mask_pii_phone_parens():
    from scripts.feedback_api import mask_pii
    assert mask_pii("(555) 867-5309") == "[phone redacted]"


def test_mask_pii_clean_text():
    from scripts.feedback_api import mask_pii
    assert mask_pii("no sensitive data here") == "no sensitive data here"


def test_mask_pii_multiple_emails():
    from scripts.feedback_api import mask_pii
    result = mask_pii("a@b.com and c@d.com")
    assert result == "[email redacted] and [email redacted]"


# ── collect_context ───────────────────────────────────────────────────────────

def test_collect_context_required_keys():
    from scripts.feedback_api import collect_context
    ctx = collect_context("Home")
    for key in ("page", "version", "tier", "llm_backend", "os", "timestamp"):
        assert key in ctx, f"missing key: {key}"


def test_collect_context_page_value():
    from scripts.feedback_api import collect_context
    ctx = collect_context("MyPage")
    assert ctx["page"] == "MyPage"


def test_collect_context_timestamp_is_utc():
    from scripts.feedback_api import collect_context
    ctx = collect_context("X")
    assert ctx["timestamp"].endswith("Z")
```

**Step 2: Run to verify they fail**

```bash
conda run -n job-seeker pytest tests/test_feedback_api.py -v 2>&1 | head -30
```

Expected: `ModuleNotFoundError: No module named 'scripts.feedback_api'`

**Step 3: Create `scripts/feedback_api.py` with mask_pii and collect_context**

```python
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
```

**Step 4: Run tests to verify they pass**

```bash
conda run -n job-seeker pytest tests/test_feedback_api.py::test_mask_pii_email \
  tests/test_feedback_api.py::test_mask_pii_phone_dashes \
  tests/test_feedback_api.py::test_mask_pii_phone_parens \
  tests/test_feedback_api.py::test_mask_pii_clean_text \
  tests/test_feedback_api.py::test_mask_pii_multiple_emails \
  tests/test_feedback_api.py::test_collect_context_required_keys \
  tests/test_feedback_api.py::test_collect_context_page_value \
  tests/test_feedback_api.py::test_collect_context_timestamp_is_utc -v
```

Expected: 8 PASSED.

**Step 5: Commit**

```bash
git add scripts/feedback_api.py tests/test_feedback_api.py
git commit -m "feat: feedback_api — mask_pii + collect_context"
```

---

## Task 3: Backend — log + listing collection

**Files:**
- Modify: `scripts/feedback_api.py`
- Modify: `tests/test_feedback_api.py`

**Step 1: Write failing tests**

Append to `tests/test_feedback_api.py`:

```python
# ── collect_logs ──────────────────────────────────────────────────────────────

def test_collect_logs_returns_string(tmp_path):
    from scripts.feedback_api import collect_logs
    log = tmp_path / ".streamlit.log"
    log.write_text("line1\nline2\nline3\n")
    result = collect_logs(log_path=log, n=10)
    assert isinstance(result, str)
    assert "line3" in result


def test_collect_logs_tails_n_lines(tmp_path):
    from scripts.feedback_api import collect_logs
    log = tmp_path / ".streamlit.log"
    log.write_text("\n".join(f"line{i}" for i in range(200)))
    result = collect_logs(log_path=log, n=10)
    assert "line199" in result
    assert "line0" not in result


def test_collect_logs_masks_pii(tmp_path):
    from scripts.feedback_api import collect_logs
    log = tmp_path / "test.log"
    log.write_text("user foo@bar.com connected\n")
    result = collect_logs(log_path=log)
    assert "foo@bar.com" not in result
    assert "[email redacted]" in result


def test_collect_logs_missing_file(tmp_path):
    from scripts.feedback_api import collect_logs
    result = collect_logs(log_path=tmp_path / "nonexistent.log")
    assert "no log file" in result.lower()


# ── collect_listings ──────────────────────────────────────────────────────────

def test_collect_listings_safe_fields_only(tmp_path):
    """Only title, company, url — no cover letters, notes, or emails."""
    from scripts.db import init_db, insert_job
    from scripts.feedback_api import collect_listings
    db = tmp_path / "test.db"
    init_db(db)
    insert_job(db, {
        "title": "CSM", "company": "Acme", "url": "https://example.com/1",
        "source": "linkedin", "location": "Remote", "is_remote": True,
        "salary": "", "description": "great role", "date_found": "2026-03-01",
    })
    results = collect_listings(db_path=db, n=5)
    assert len(results) == 1
    assert set(results[0].keys()) == {"title", "company", "url"}
    assert results[0]["title"] == "CSM"


def test_collect_listings_respects_n(tmp_path):
    from scripts.db import init_db, insert_job
    from scripts.feedback_api import collect_listings
    db = tmp_path / "test.db"
    init_db(db)
    for i in range(10):
        insert_job(db, {
            "title": f"Job {i}", "company": "Acme", "url": f"https://example.com/{i}",
            "source": "linkedin", "location": "Remote", "is_remote": False,
            "salary": "", "description": "", "date_found": "2026-03-01",
        })
    assert len(collect_listings(db_path=db, n=3)) == 3
```

**Step 2: Run to verify they fail**

```bash
conda run -n job-seeker pytest tests/test_feedback_api.py -k "collect_logs or collect_listings" -v 2>&1 | head -20
```

Expected: all FAIL with `ImportError` or similar.

**Step 3: Add functions to `scripts/feedback_api.py`**

Append after `collect_context`:

```python
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
```

**Step 4: Run tests to verify they pass**

```bash
conda run -n job-seeker pytest tests/test_feedback_api.py -k "collect_logs or collect_listings" -v
```

Expected: 6 PASSED.

**Step 5: Commit**

```bash
git add scripts/feedback_api.py tests/test_feedback_api.py
git commit -m "feat: feedback_api — collect_logs + collect_listings"
```

---

## Task 4: Backend — issue body builder

**Files:**
- Modify: `scripts/feedback_api.py`
- Modify: `tests/test_feedback_api.py`

**Step 1: Write failing tests**

Append to `tests/test_feedback_api.py`:

```python
# ── build_issue_body ──────────────────────────────────────────────────────────

def test_build_issue_body_contains_description():
    from scripts.feedback_api import build_issue_body
    form = {"type": "bug", "title": "Test", "description": "it broke", "repro": ""}
    ctx = {"page": "Home", "version": "v1.0", "tier": "free",
           "llm_backend": "ollama", "os": "Linux", "timestamp": "2026-03-03T00:00:00Z"}
    body = build_issue_body(form, ctx, {})
    assert "it broke" in body
    assert "Home" in body
    assert "v1.0" in body


def test_build_issue_body_bug_includes_repro():
    from scripts.feedback_api import build_issue_body
    form = {"type": "bug", "title": "X", "description": "desc", "repro": "step 1\nstep 2"}
    body = build_issue_body(form, {}, {})
    assert "step 1" in body
    assert "Reproduction" in body


def test_build_issue_body_no_repro_for_feature():
    from scripts.feedback_api import build_issue_body
    form = {"type": "feature", "title": "X", "description": "add dark mode", "repro": "ignored"}
    body = build_issue_body(form, {}, {})
    assert "Reproduction" not in body


def test_build_issue_body_logs_in_collapsible():
    from scripts.feedback_api import build_issue_body
    form = {"type": "other", "title": "X", "description": "Y", "repro": ""}
    body = build_issue_body(form, {}, {"logs": "log line 1\nlog line 2"})
    assert "<details>" in body
    assert "log line 1" in body


def test_build_issue_body_omits_logs_when_not_provided():
    from scripts.feedback_api import build_issue_body
    form = {"type": "bug", "title": "X", "description": "Y", "repro": ""}
    body = build_issue_body(form, {}, {})
    assert "<details>" not in body


def test_build_issue_body_submitter_attribution():
    from scripts.feedback_api import build_issue_body
    form = {"type": "bug", "title": "X", "description": "Y", "repro": ""}
    body = build_issue_body(form, {}, {"submitter": "Jane Doe <jane@example.com>"})
    assert "Jane Doe" in body


def test_build_issue_body_listings_shown():
    from scripts.feedback_api import build_issue_body
    form = {"type": "bug", "title": "X", "description": "Y", "repro": ""}
    listings = [{"title": "CSM", "company": "Acme", "url": "https://example.com/1"}]
    body = build_issue_body(form, {}, {"listings": listings})
    assert "CSM" in body
    assert "Acme" in body
```

**Step 2: Run to verify they fail**

```bash
conda run -n job-seeker pytest tests/test_feedback_api.py -k "build_issue_body" -v 2>&1 | head -20
```

**Step 3: Add `build_issue_body` to `scripts/feedback_api.py`**

Append after `collect_listings`:

```python
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
```

**Step 4: Run tests to verify they pass**

```bash
conda run -n job-seeker pytest tests/test_feedback_api.py -k "build_issue_body" -v
```

Expected: 7 PASSED.

**Step 5: Commit**

```bash
git add scripts/feedback_api.py tests/test_feedback_api.py
git commit -m "feat: feedback_api — build_issue_body"
```

---

## Task 5: Backend — Forgejo API client

**Files:**
- Modify: `scripts/feedback_api.py`
- Modify: `tests/test_feedback_api.py`

**Step 1: Write failing tests**

Append to `tests/test_feedback_api.py`:

```python
# ── Forgejo API ───────────────────────────────────────────────────────────────

@patch("scripts.feedback_api.requests.get")
@patch("scripts.feedback_api.requests.post")
def test_ensure_labels_uses_existing(mock_post, mock_get):
    from scripts.feedback_api import _ensure_labels
    mock_get.return_value.ok = True
    mock_get.return_value.json.return_value = [
        {"name": "beta-feedback", "id": 1},
        {"name": "bug", "id": 2},
    ]
    ids = _ensure_labels(
        ["beta-feedback", "bug"],
        "https://example.com/api/v1", {"Authorization": "token x"}, "owner/repo"
    )
    assert ids == [1, 2]
    mock_post.assert_not_called()


@patch("scripts.feedback_api.requests.get")
@patch("scripts.feedback_api.requests.post")
def test_ensure_labels_creates_missing(mock_post, mock_get):
    from scripts.feedback_api import _ensure_labels
    mock_get.return_value.ok = True
    mock_get.return_value.json.return_value = []
    mock_post.return_value.ok = True
    mock_post.return_value.json.return_value = {"id": 99}
    ids = _ensure_labels(
        ["needs-triage"],
        "https://example.com/api/v1", {"Authorization": "token x"}, "owner/repo"
    )
    assert 99 in ids


@patch("scripts.feedback_api._ensure_labels", return_value=[1, 2])
@patch("scripts.feedback_api.requests.post")
def test_create_forgejo_issue_success(mock_post, mock_labels, monkeypatch):
    from scripts.feedback_api import create_forgejo_issue
    monkeypatch.setenv("FORGEJO_API_TOKEN", "testtoken")
    monkeypatch.setenv("FORGEJO_REPO", "owner/repo")
    monkeypatch.setenv("FORGEJO_API_URL", "https://example.com/api/v1")
    mock_post.return_value.status_code = 201
    mock_post.return_value.raise_for_status = lambda: None
    mock_post.return_value.json.return_value = {"number": 42, "html_url": "https://example.com/issues/42"}
    result = create_forgejo_issue("Test issue", "body text", ["beta-feedback", "bug"])
    assert result["number"] == 42
    assert "42" in result["url"]


@patch("scripts.feedback_api.requests.post")
def test_upload_attachment_returns_url(mock_post, monkeypatch):
    from scripts.feedback_api import upload_attachment
    monkeypatch.setenv("FORGEJO_API_TOKEN", "testtoken")
    monkeypatch.setenv("FORGEJO_REPO", "owner/repo")
    monkeypatch.setenv("FORGEJO_API_URL", "https://example.com/api/v1")
    mock_post.return_value.status_code = 201
    mock_post.return_value.raise_for_status = lambda: None
    mock_post.return_value.json.return_value = {
        "uuid": "abc", "browser_download_url": "https://example.com/assets/abc"
    }
    url = upload_attachment(42, b"\x89PNG", "screenshot.png")
    assert url == "https://example.com/assets/abc"
```

**Step 2: Run to verify they fail**

```bash
conda run -n job-seeker pytest tests/test_feedback_api.py -k "label or issue or attach" -v 2>&1 | head -20
```

**Step 3: Add Forgejo API functions to `scripts/feedback_api.py`**

Append after `build_issue_body`:

```python
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
```

**Step 4: Run tests to verify they pass**

```bash
conda run -n job-seeker pytest tests/test_feedback_api.py -k "label or issue or attach" -v
```

Expected: 4 PASSED.

**Step 5: Run full test suite to check for regressions**

```bash
conda run -n job-seeker pytest tests/test_feedback_api.py -v
```

Expected: all PASSED.

**Step 6: Commit**

```bash
git add scripts/feedback_api.py tests/test_feedback_api.py
git commit -m "feat: feedback_api — Forgejo label management + issue filing + attachment upload"
```

---

## Task 6: Backend — server-side screenshot capture

**Files:**
- Modify: `scripts/feedback_api.py`
- Modify: `tests/test_feedback_api.py`

**Step 1: Write failing tests**

Append to `tests/test_feedback_api.py`:

```python
# ── screenshot_page ───────────────────────────────────────────────────────────

def test_screenshot_page_returns_none_without_playwright(monkeypatch):
    """If playwright is not installed, screenshot_page returns None gracefully."""
    import builtins
    real_import = builtins.__import__
    def mock_import(name, *args, **kwargs):
        if name == "playwright.sync_api":
            raise ImportError("no playwright")
        return real_import(name, *args, **kwargs)
    monkeypatch.setattr(builtins, "__import__", mock_import)
    from scripts.feedback_api import screenshot_page
    result = screenshot_page(port=9999)
    assert result is None


@patch("scripts.feedback_api.sync_playwright")
def test_screenshot_page_returns_bytes(mock_pw):
    """screenshot_page returns PNG bytes when playwright is available."""
    from scripts.feedback_api import screenshot_page
    fake_png = b"\x89PNG\r\n\x1a\n"
    mock_context = MagicMock()
    mock_pw.return_value.__enter__ = lambda s: mock_context
    mock_pw.return_value.__exit__ = MagicMock(return_value=False)
    mock_browser = mock_context.chromium.launch.return_value
    mock_page = mock_browser.new_page.return_value
    mock_page.screenshot.return_value = fake_png
    result = screenshot_page(port=8502)
    assert result == fake_png
```

**Step 2: Run to verify they fail**

```bash
conda run -n job-seeker pytest tests/test_feedback_api.py -k "screenshot" -v 2>&1 | head -20
```

**Step 3: Add `screenshot_page` to `scripts/feedback_api.py`**

Append after `upload_attachment`. Note the `try/except ImportError` for graceful degradation:

```python
def screenshot_page(port: int | None = None) -> bytes | None:
    """
    Capture a screenshot of the running Peregrine UI using Playwright.
    Returns PNG bytes, or None if Playwright is not installed.
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
    except Exception:
        return None
```

Also add the import at the top of the try block to satisfy the mock test. The import at the function level is correct — do NOT add it to the module level, because we want the graceful degradation path to work.

**Step 4: Run tests to verify they pass**

```bash
conda run -n job-seeker pytest tests/test_feedback_api.py -k "screenshot" -v
```

Expected: 2 PASSED.

**Step 5: Run full backend test suite**

```bash
conda run -n job-seeker pytest tests/test_feedback_api.py -v
```

Expected: all PASSED.

**Step 6: Commit**

```bash
git add scripts/feedback_api.py tests/test_feedback_api.py
git commit -m "feat: feedback_api — screenshot_page with Playwright (graceful fallback)"
```

---

## Task 7: UI — floating button + feedback dialog

**Files:**
- Create: `app/feedback.py`

No pytest tests for Streamlit UI (too brittle for dialogs). Manual verification in Task 8.

**Step 1: Create `app/feedback.py`**

```python
"""
Floating feedback button + dialog — thin Streamlit shell.
All business logic lives in scripts/feedback_api.py.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st

# ── CSS: float the button to the bottom-right corner ─────────────────────────
# Targets the button by its aria-label (set via `help=` parameter).
_FLOAT_CSS = """
<style>
button[aria-label="Send feedback or report a bug"] {
    position: fixed !important;
    bottom: 2rem !important;
    right: 2rem !important;
    z-index: 9999 !important;
    border-radius: 25px !important;
    padding: 0.5rem 1.25rem !important;
    box-shadow: 0 4px 16px rgba(0,0,0,0.25) !important;
    font-size: 0.9rem !important;
}
</style>
"""


@st.dialog("Send Feedback", width="large")
def _feedback_dialog(page: str) -> None:
    """Two-step feedback dialog: form → consent/attachments → submit."""
    from scripts.feedback_api import (
        collect_context, collect_logs, collect_listings,
        build_issue_body, create_forgejo_issue,
        upload_attachment, screenshot_page,
    )
    from scripts.db import DEFAULT_DB

    # ── Initialise step counter ───────────────────────────────────────────────
    if "fb_step" not in st.session_state:
        st.session_state.fb_step = 1

    # ═════════════════════════════════════════════════════════════════════════
    # STEP 1 — Form
    # ═════════════════════════════════════════════════════════════════════════
    if st.session_state.fb_step == 1:
        st.subheader("What's on your mind?")

        fb_type = st.selectbox(
            "Type", ["Bug", "Feature Request", "Other"], key="fb_type"
        )
        fb_title = st.text_input(
            "Title", placeholder="Short summary of the issue or idea", key="fb_title"
        )
        fb_desc = st.text_area(
            "Description",
            placeholder="Describe what happened or what you'd like to see...",
            key="fb_desc",
        )
        if fb_type == "Bug":
            st.text_area(
                "Reproduction steps",
                placeholder="1. Go to...\n2. Click...\n3. See error",
                key="fb_repro",
            )

        col_cancel, _, col_next = st.columns([1, 3, 1])
        with col_cancel:
            if st.button("Cancel"):
                _clear_feedback_state()
                st.rerun()
        with col_next:
            if st.button(
                "Next →",
                type="primary",
                disabled=not st.session_state.get("fb_title", "").strip()
                or not st.session_state.get("fb_desc", "").strip(),
            ):
                st.session_state.fb_step = 2
                st.rerun()

    # ═════════════════════════════════════════════════════════════════════════
    # STEP 2 — Consent + attachments
    # ═════════════════════════════════════════════════════════════════════════
    elif st.session_state.fb_step == 2:
        st.subheader("Optional: attach diagnostic data")

        # ── Diagnostic data toggle + preview ─────────────────────────────────
        include_diag = st.toggle(
            "Include diagnostic data (logs + recent listings)", key="fb_diag"
        )
        if include_diag:
            with st.expander("Preview what will be sent", expanded=True):
                st.caption("**App logs (last 100 lines, PII masked):**")
                st.code(collect_logs(100), language=None)
                st.caption("**Recent listings (title / company / URL only):**")
                for j in collect_listings(DEFAULT_DB, 5):
                    st.write(f"- {j['title']} @ {j['company']} — {j['url']}")

        # ── Screenshot ────────────────────────────────────────────────────────
        st.divider()
        st.caption("**Screenshot** (optional)")
        col_cap, col_up = st.columns(2)

        with col_cap:
            if st.button("📸 Capture current view"):
                with st.spinner("Capturing page…"):
                    png = screenshot_page()
                if png:
                    st.session_state.fb_screenshot = png
                else:
                    st.warning(
                        "Playwright not available — install it with "
                        "`playwright install chromium`, or upload a screenshot instead."
                    )

        with col_up:
            uploaded = st.file_uploader(
                "Upload screenshot",
                type=["png", "jpg", "jpeg"],
                label_visibility="collapsed",
                key="fb_upload",
            )
            if uploaded:
                st.session_state.fb_screenshot = uploaded.read()

        if st.session_state.get("fb_screenshot"):
            st.image(
                st.session_state["fb_screenshot"],
                caption="Screenshot preview — this will be attached to the issue",
                use_container_width=True,
            )
            if st.button("🗑 Remove screenshot"):
                st.session_state.pop("fb_screenshot", None)
                st.rerun()

        # ── Attribution consent ───────────────────────────────────────────────
        st.divider()
        submitter: str | None = None
        try:
            import yaml
            _ROOT = Path(__file__).parent.parent
            user = yaml.safe_load((_ROOT / "config" / "user.yaml").read_text()) or {}
            name = (user.get("name") or "").strip()
            email = (user.get("email") or "").strip()
            if name or email:
                label = f"Include my name & email in the report: **{name}** ({email})"
                if st.checkbox(label, key="fb_attr"):
                    submitter = f"{name} <{email}>"
        except Exception:
            pass

        # ── Navigation ────────────────────────────────────────────────────────
        col_back, _, col_submit = st.columns([1, 3, 2])
        with col_back:
            if st.button("← Back"):
                st.session_state.fb_step = 1
                st.rerun()

        with col_submit:
            if st.button("Submit Feedback", type="primary"):
                _submit(page, include_diag, submitter, collect_context,
                        collect_logs, collect_listings, build_issue_body,
                        create_forgejo_issue, upload_attachment, DEFAULT_DB)


def _submit(page, include_diag, submitter, collect_context, collect_logs,
            collect_listings, build_issue_body, create_forgejo_issue,
            upload_attachment, db_path) -> None:
    """Handle form submission: build body, file issue, upload screenshot."""
    with st.spinner("Filing issue…"):
        context = collect_context(page)
        attachments: dict = {}
        if include_diag:
            attachments["logs"] = collect_logs(100)
            attachments["listings"] = collect_listings(db_path, 5)
        if submitter:
            attachments["submitter"] = submitter

        fb_type = st.session_state.get("fb_type", "Other")
        type_key = {"Bug": "bug", "Feature Request": "feature", "Other": "other"}.get(
            fb_type, "other"
        )
        labels = ["beta-feedback", "needs-triage"]
        labels.append(
            {"bug": "bug", "feature": "feature-request"}.get(type_key, "question")
        )

        form = {
            "type": type_key,
            "description": st.session_state.get("fb_desc", ""),
            "repro": st.session_state.get("fb_repro", "") if type_key == "bug" else "",
        }

        body = build_issue_body(form, context, attachments)

        try:
            result = create_forgejo_issue(
                st.session_state.get("fb_title", "Feedback"), body, labels
            )
            screenshot = st.session_state.get("fb_screenshot")
            if screenshot:
                upload_attachment(result["number"], screenshot)

            _clear_feedback_state()
            st.success(f"Issue filed! [View on Forgejo]({result['url']})")
            st.balloons()

        except Exception as exc:
            st.error(f"Failed to file issue: {exc}")


def _clear_feedback_state() -> None:
    for key in [
        "fb_step", "fb_type", "fb_title", "fb_desc", "fb_repro",
        "fb_diag", "fb_upload", "fb_attr", "fb_screenshot",
    ]:
        st.session_state.pop(key, None)


def inject_feedback_button(page: str = "Unknown") -> None:
    """
    Inject the floating feedback button. Call once per page render in app.py.
    Hidden automatically in DEMO_MODE.
    """
    if os.environ.get("DEMO_MODE", "").lower() in ("1", "true", "yes"):
        return
    if not os.environ.get("FORGEJO_API_TOKEN"):
        return  # silently skip if not configured

    st.markdown(_FLOAT_CSS, unsafe_allow_html=True)
    if st.button(
        "💬 Feedback",
        key="__feedback_floating_btn__",
        help="Send feedback or report a bug",
    ):
        _feedback_dialog(page)
```

**Step 2: Verify the file has no syntax errors**

```bash
conda run -n job-seeker python -c "import app.feedback; print('OK')"
```

Expected: `OK`

**Step 3: Commit**

```bash
git add app/feedback.py
git commit -m "feat: floating feedback button + two-step dialog (Streamlit shell)"
```

---

## Task 8: Wire into app.py + manual verification

**Files:**
- Modify: `app/app.py`

**Step 1: Add import and call to `app/app.py`**

Find the `with st.sidebar:` block near the bottom of `app/app.py` (currently ends with `st.caption(f"Peregrine {_get_version()}")`).

Add two lines — the import near the top of the file (after the existing imports), and the call in the sidebar block:

At the top of `app/app.py`, after `from scripts.db import ...`:
```python
from app.feedback import inject_feedback_button
```

At the end of the `with st.sidebar:` block, after `st.caption(...)`:
```python
    inject_feedback_button(page=st.session_state.get("__current_page__", "Unknown"))
```

To capture the current page name, also add this anywhere early in the sidebar block (before the caption):
```python
    # Track current page for feedback context
    try:
        _page_name = pg.pages[st.session_state.get("page_index", 0)].title
    except Exception:
        _page_name = "Unknown"
    inject_feedback_button(page=_page_name)
```

> **Note on page detection:** Streamlit's `st.navigation` doesn't expose the current page via a simple API. If `pg.pages[...]` doesn't resolve cleanly, simplify to `inject_feedback_button()` with no argument — the page context is a nice-to-have, not critical.

**Step 2: Verify app starts without errors**

```bash
bash /Library/Development/CircuitForge/peregrine/manage.sh restart
bash /Library/Development/CircuitForge/peregrine/manage.sh logs
```

Expected: no Python tracebacks in logs.

**Step 3: Manual end-to-end verification checklist**

Open http://localhost:8502 and verify:

- [ ] A "💬 Feedback" pill button appears fixed in the bottom-right corner
- [ ] Button is visible on Home, Setup, and all other pages
- [ ] Button is NOT visible in DEMO_MODE (set `DEMO_MODE=1` in `.env`, restart, check)
- [ ] Clicking the button opens the two-step dialog
- [ ] Step 1: selecting "Bug" reveals the reproduction steps field; "Feature Request" hides it
- [ ] "Next →" is disabled until title + description are filled
- [ ] Step 2: toggling diagnostic data shows the masked preview (no real emails/phones)
- [ ] "📸 Capture current view" either shows a thumbnail or a warning about Playwright
- [ ] Uploading a PNG via file picker shows a thumbnail
- [ ] "🗑 Remove screenshot" clears the thumbnail
- [ ] Attribution checkbox shows the name/email from user.yaml
- [ ] Submitting files a real issue at https://git.opensourcesolarpunk.com/pyr0ball/peregrine/issues
- [ ] Issue has correct labels (beta-feedback, needs-triage, + type label)
- [ ] If screenshot provided, it appears as an attachment on the Forgejo issue
- [ ] Success message contains a clickable link to the issue

**Step 4: Commit**

```bash
git add app/app.py
git commit -m "feat: wire feedback button into app.py sidebar"
```

---

## Done

All tasks complete. The feedback button is live. When moving to Vue/Nuxt, `scripts/feedback_api.py` is wrapped in a FastAPI route — no changes to the backend needed.

**Future tasks (not in scope now):**
- GitHub mirroring (add `GITHUB_TOKEN` + `GITHUB_REPO` env vars, add `create_github_issue()`)
- Rate limiting (if beta users abuse it)
- In-app issue status tracking
