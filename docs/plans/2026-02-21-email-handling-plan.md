# Email Handling Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add stage-signal classification to inbound emails, recruiter lead capture from unmatched emails, email sync as a background task, and surface both in the UI.

**Architecture:** Extend `imap_sync.py` with a phi3-mini classifier and Nemotron lead extractor; wire `email_sync` into `task_runner.py`; add two new DB helpers and two migration columns; update three UI pages.

**Tech Stack:** Python, SQLite, imaplib, LLMRouter (Ollama phi3:mini + Nemotron 1.5B), Streamlit.

**Run tests:** `/devl/miniconda3/envs/job-seeker/bin/pytest tests/ -v`
**Conda prefix:** `conda run -n job-seeker`

---

### Task 1: DB migrations — stage_signal + suggestion_dismissed columns

**Files:**
- Modify: `scripts/db.py`
- Test: `tests/test_db.py`

**Context:** `_CONTACT_MIGRATIONS` is a list of `(col, type)` tuples applied in `_migrate_db()`. Add to that list. Also add two helper functions: `get_unread_stage_signals(db_path, job_id)` returns contacts with a non-null, non-neutral stage_signal and `suggestion_dismissed = 0`; `dismiss_stage_signal(db_path, contact_id)` sets `suggestion_dismissed = 1`. Also update `add_contact()` to accept an optional `stage_signal` kwarg.

**Step 1: Write the failing tests**

In `tests/test_db.py`, append:

```python
def test_stage_signal_columns_exist(tmp_path):
    """init_db creates stage_signal and suggestion_dismissed columns on job_contacts."""
    from scripts.db import init_db
    db_path = tmp_path / "test.db"
    init_db(db_path)
    conn = sqlite3.connect(db_path)
    cols = {row[1] for row in conn.execute("PRAGMA table_info(job_contacts)").fetchall()}
    conn.close()
    assert "stage_signal" in cols
    assert "suggestion_dismissed" in cols


def test_add_contact_with_stage_signal(tmp_path):
    """add_contact stores stage_signal when provided."""
    from scripts.db import init_db, insert_job, add_contact, get_contacts
    db_path = tmp_path / "test.db"
    init_db(db_path)
    job_id = insert_job(db_path, {
        "title": "CSM", "company": "Acme", "url": "https://ex.com/1",
        "source": "linkedin", "location": "Remote", "is_remote": True,
        "salary": "", "description": "", "date_found": "2026-02-21",
    })
    add_contact(db_path, job_id=job_id, direction="inbound",
                subject="Interview invite", stage_signal="interview_scheduled")
    contacts = get_contacts(db_path, job_id=job_id)
    assert contacts[0]["stage_signal"] == "interview_scheduled"


def test_get_unread_stage_signals(tmp_path):
    """get_unread_stage_signals returns only non-neutral, non-dismissed signals."""
    from scripts.db import (init_db, insert_job, add_contact,
                            get_unread_stage_signals, dismiss_stage_signal)
    db_path = tmp_path / "test.db"
    init_db(db_path)
    job_id = insert_job(db_path, {
        "title": "CSM", "company": "Acme", "url": "https://ex.com/1",
        "source": "linkedin", "location": "Remote", "is_remote": True,
        "salary": "", "description": "", "date_found": "2026-02-21",
    })
    c1 = add_contact(db_path, job_id=job_id, direction="inbound",
                     subject="Interview invite", stage_signal="interview_scheduled")
    add_contact(db_path, job_id=job_id, direction="inbound",
                subject="Auto-confirm", stage_signal="neutral")
    signals = get_unread_stage_signals(db_path, job_id)
    assert len(signals) == 1
    assert signals[0]["stage_signal"] == "interview_scheduled"

    dismiss_stage_signal(db_path, c1)
    assert get_unread_stage_signals(db_path, job_id) == []
```

**Step 2: Run tests to confirm they fail**

```bash
/devl/miniconda3/envs/job-seeker/bin/pytest tests/test_db.py::test_stage_signal_columns_exist tests/test_db.py::test_add_contact_with_stage_signal tests/test_db.py::test_get_unread_stage_signals -v
```

Expected: 3 failures.

**Step 3: Implement in `scripts/db.py`**

3a. In `_CONTACT_MIGRATIONS`, add:
```python
_CONTACT_MIGRATIONS = [
    ("message_id",           "TEXT"),
    ("stage_signal",         "TEXT"),
    ("suggestion_dismissed", "INTEGER DEFAULT 0"),
]
```

3b. Update `add_contact()` signature and INSERT:
```python
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
```

3c. Add the two new helpers after `get_contacts()`:
```python
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
```

3d. Add `get_all_message_ids()` (needed for lead dedup in Task 3):
```python
def get_all_message_ids(db_path: Path = DEFAULT_DB) -> set[str]:
    """Return all known Message-IDs across all job contacts."""
    conn = sqlite3.connect(db_path)
    rows = conn.execute(
        "SELECT message_id FROM job_contacts WHERE message_id IS NOT NULL AND message_id != ''"
    ).fetchall()
    conn.close()
    return {r[0] for r in rows}
```

**Step 4: Run tests**

```bash
/devl/miniconda3/envs/job-seeker/bin/pytest tests/test_db.py -v
```

Expected: all pass.

**Step 5: Commit**

```bash
git add scripts/db.py tests/test_db.py
git commit -m "feat: add stage_signal/suggestion_dismissed columns and helpers to db"
```

---

### Task 2: Stage signal classifier in imap_sync.py

**Files:**
- Modify: `scripts/imap_sync.py`
- Test: `tests/test_imap_sync.py` (create)

**Context:** Add a `classify_stage_signal(subject, body)` function that calls phi3:mini via LLMRouter and returns one of the 5 label strings. It must gracefully return `None` on any failure (network, timeout, model not loaded). The label parsing must strip `<think>` tags in case a thinking-capable model is used.

**Step 1: Write the failing test**

Create `tests/test_imap_sync.py`:

```python
"""Tests for imap_sync helpers (no live IMAP connection required)."""
import pytest
from unittest.mock import patch


def test_classify_stage_signal_interview(tmp_path):
    """classify_stage_signal returns interview_scheduled for a call-scheduling email."""
    from scripts.imap_sync import classify_stage_signal
    with patch("scripts.imap_sync._CLASSIFIER_ROUTER") as mock_router:
        mock_router.complete.return_value = "interview_scheduled"
        result = classify_stage_signal(
            "Let's schedule a call",
            "Hi Alex, we'd love to book a 30-min phone screen with you.",
        )
    assert result == "interview_scheduled"


def test_classify_stage_signal_returns_none_on_error(tmp_path):
    """classify_stage_signal returns None when LLM call raises."""
    from scripts.imap_sync import classify_stage_signal
    with patch("scripts.imap_sync._CLASSIFIER_ROUTER") as mock_router:
        mock_router.complete.side_effect = RuntimeError("model not loaded")
        result = classify_stage_signal("subject", "body")
    assert result is None


def test_classify_stage_signal_strips_think_tags(tmp_path):
    """classify_stage_signal strips <think>…</think> blocks before parsing."""
    from scripts.imap_sync import classify_stage_signal
    with patch("scripts.imap_sync._CLASSIFIER_ROUTER") as mock_router:
        mock_router.complete.return_value = "<think>Let me think…</think>\nrejected"
        result = classify_stage_signal("Update on your application", "We went with another candidate.")
    assert result == "rejected"


def test_normalise_company():
    """_normalise_company strips legal suffixes."""
    from scripts.imap_sync import _normalise_company
    assert _normalise_company("DataStax, Inc.") == "DataStax"
    assert _normalise_company("Wiz Ltd") == "Wiz"
    assert _normalise_company("Crusoe Energy") == "Crusoe Energy"


def test_has_recruitment_keyword():
    """_has_recruitment_keyword matches known keywords."""
    from scripts.imap_sync import _has_recruitment_keyword
    assert _has_recruitment_keyword("Interview Invitation — Senior TAM")
    assert _has_recruitment_keyword("Your application with DataStax")
    assert not _has_recruitment_keyword("Team lunch tomorrow")
```

**Step 2: Run to confirm failures**

```bash
/devl/miniconda3/envs/job-seeker/bin/pytest tests/test_imap_sync.py -v
```

Expected: ImportError or failures on `classify_stage_signal` and `_CLASSIFIER_ROUTER`.

**Step 3: Implement in `scripts/imap_sync.py`**

After the existing imports, add:

```python
import re as _re

from scripts.llm_router import LLMRouter

_CLASSIFIER_ROUTER = LLMRouter()

_CLASSIFY_SYSTEM = (
    "You are an email classifier. Classify the recruitment email into exactly ONE of these categories:\n"
    "  interview_scheduled, offer_received, rejected, positive_response, neutral\n\n"
    "Rules:\n"
    "- interview_scheduled: recruiter wants to book a call/interview\n"
    "- offer_received: job offer is being extended\n"
    "- rejected: explicitly not moving forward\n"
    "- positive_response: interested/impressed but no interview booked yet\n"
    "- neutral: auto-confirmation, generic update, no clear signal\n\n"
    "Respond with ONLY the category name. No explanation."
)

_CLASSIFY_LABELS = [
    "interview_scheduled", "offer_received", "rejected",
    "positive_response", "neutral",
]


def classify_stage_signal(subject: str, body: str) -> Optional[str]:
    """Classify an inbound email into a pipeline stage signal.

    Returns one of the 5 label strings, or None on failure.
    Uses phi3:mini via Ollama (benchmarked 100% on 12-case test set).
    """
    try:
        prompt = f"Subject: {subject}\n\nEmail: {body[:400]}"
        raw = _CLASSIFIER_ROUTER.complete(
            prompt,
            system=_CLASSIFY_SYSTEM,
            model_override="phi3:mini",
            fallback_order=["ollama_research"],
        )
        # Strip <think> blocks (in case a reasoning model slips through)
        text = _re.sub(r"<think>.*?</think>", "", raw, flags=_re.DOTALL)
        text = text.lower().strip()
        for label in _CLASSIFY_LABELS:
            if text.startswith(label) or label in text:
                return label
        return "neutral"
    except Exception:
        return None
```

**Step 4: Run tests**

```bash
/devl/miniconda3/envs/job-seeker/bin/pytest tests/test_imap_sync.py -v
```

Expected: all 5 pass.

**Step 5: Commit**

```bash
git add scripts/imap_sync.py tests/test_imap_sync.py
git commit -m "feat: add classify_stage_signal to imap_sync using phi3:mini"
```

---

### Task 3: Classify inbound contacts during per-job sync

**Files:**
- Modify: `scripts/imap_sync.py`
- Test: `tests/test_imap_sync.py`

**Context:** Inside `sync_job_emails()`, after calling `add_contact()` for an inbound email, call `classify_stage_signal()` and — if the result is non-None and non-'neutral' — update the `stage_signal` column via a direct SQLite update (no new db.py helper needed; avoid round-tripping through `add_contact`). The `contact_id` is already returned by `add_contact()`.

We need a tiny helper `_update_contact_signal(db_path, contact_id, signal)` locally in imap_sync.py. Do NOT add this to db.py — it's only used here.

**Step 1: Add test**

Append to `tests/test_imap_sync.py`:

```python
def test_sync_job_emails_classifies_inbound(tmp_path):
    """sync_job_emails classifies inbound emails and stores the stage_signal."""
    from scripts.db import init_db, insert_job, get_contacts
    from scripts.imap_sync import sync_job_emails

    db_path = tmp_path / "test.db"
    init_db(db_path)
    job_id = insert_job(db_path, {
        "title": "CSM", "company": "Acme",
        "url": "https://acme.com/jobs/1",
        "source": "linkedin", "location": "Remote",
        "is_remote": True, "salary": "", "description": "",
        "date_found": "2026-02-21",
    })
    job = {"id": job_id, "company": "Acme", "url": "https://acme.com/jobs/1"}

    # Fake IMAP connection + one inbound email
    from unittest.mock import MagicMock, patch

    fake_msg_bytes = (
        b"From: recruiter@acme.com\r\n"
        b"To: alex@example.com\r\n"
        b"Subject: Interview Invitation\r\n"
        b"Message-ID: <unique-001@acme.com>\r\n"
        b"\r\n"
        b"Hi Alex, we'd like to schedule a phone screen."
    )

    conn_mock = MagicMock()
    conn_mock.select.return_value = ("OK", [b"1"])
    conn_mock.search.return_value = ("OK", [b"1"])
    conn_mock.fetch.return_value = ("OK", [(b"1 (RFC822 {123})", fake_msg_bytes)])

    with patch("scripts.imap_sync.classify_stage_signal", return_value="interview_scheduled"):
        inb, out = sync_job_emails(job, conn_mock, {"lookback_days": 90}, db_path)

    assert inb == 1
    contacts = get_contacts(db_path, job_id=job_id)
    assert contacts[0]["stage_signal"] == "interview_scheduled"
```

**Step 2: Run to confirm failure**

```bash
/devl/miniconda3/envs/job-seeker/bin/pytest tests/test_imap_sync.py::test_sync_job_emails_classifies_inbound -v
```

Expected: FAIL (stage_signal is None).

**Step 3: Update `sync_job_emails()` in `scripts/imap_sync.py`**

Add the private helper just before `sync_job_emails`:

```python
def _update_contact_signal(db_path: Path, contact_id: int, signal: str) -> None:
    """Write a stage signal onto an existing contact row."""
    import sqlite3 as _sqlite3
    conn = _sqlite3.connect(db_path)
    conn.execute(
        "UPDATE job_contacts SET stage_signal = ? WHERE id = ?",
        (signal, contact_id),
    )
    conn.commit()
    conn.close()
```

In the INBOX loop inside `sync_job_emails()`, after the `add_contact(...)` call, add:

```python
signal = classify_stage_signal(parsed["subject"], parsed["body"])
if signal and signal != "neutral":
    _update_contact_signal(db_path, contact_id, signal)
```

Note: `add_contact()` already returns the `row_id` (the contact_id). Make sure to capture it:

```python
contact_id = add_contact(
    db_path, job_id=job["id"], direction="inbound",
    ...
)
signal = classify_stage_signal(parsed["subject"], parsed["body"])
if signal and signal != "neutral":
    _update_contact_signal(db_path, contact_id, signal)
```

**Step 4: Run tests**

```bash
/devl/miniconda3/envs/job-seeker/bin/pytest tests/test_imap_sync.py -v
```

Expected: all pass.

**Step 5: Commit**

```bash
git add scripts/imap_sync.py tests/test_imap_sync.py
git commit -m "feat: classify stage signals for inbound emails during per-job sync"
```

---

### Task 4: Recruiter lead extractor + unmatched email handling

**Files:**
- Modify: `scripts/imap_sync.py`
- Modify: `scripts/db.py`
- Test: `tests/test_imap_sync.py`

**Context:** After per-job sync, do a second pass to find inbound recruitment emails NOT matched to any existing pipeline company. For each, call Nemotron to extract company + job title. If extraction succeeds and company isn't already in the DB, insert a new job (`source='email', status='pending'`). Use a synthetic URL `email://<from_domain>/<message_id_hash>` to satisfy the UNIQUE constraint on `jobs.url`.

`sync_all()` return dict gains a `new_leads` key.

**Step 1: Add test**

Append to `tests/test_imap_sync.py`:

```python
def test_extract_lead_info_returns_company_and_title():
    """extract_lead_info parses LLM JSON response into (company, title)."""
    from scripts.imap_sync import extract_lead_info
    with patch("scripts.imap_sync._CLASSIFIER_ROUTER") as mock_router:
        mock_router.complete.return_value = '{"company": "Wiz", "title": "Senior TAM"}'
        result = extract_lead_info("Senior TAM at Wiz", "Hi Alex, we have a role…", "recruiter@wiz.com")
    assert result == ("Wiz", "Senior TAM")


def test_extract_lead_info_returns_none_on_bad_json():
    """extract_lead_info returns (None, None) when LLM returns unparseable output."""
    from scripts.imap_sync import extract_lead_info
    with patch("scripts.imap_sync._CLASSIFIER_ROUTER") as mock_router:
        mock_router.complete.return_value = "I cannot determine the company."
        result = extract_lead_info("Job opportunity", "blah", "noreply@example.com")
    assert result == (None, None)
```

**Step 2: Run to confirm failures**

```bash
/devl/miniconda3/envs/job-seeker/bin/pytest tests/test_imap_sync.py::test_extract_lead_info_returns_company_and_title tests/test_imap_sync.py::test_extract_lead_info_returns_none_on_bad_json -v
```

Expected: 2 failures.

**Step 3: Implement `extract_lead_info()` in `scripts/imap_sync.py`**

Add after `classify_stage_signal()`:

```python
_EXTRACT_SYSTEM = (
    "Extract the hiring company name and job title from this recruitment email. "
    "Respond with ONLY valid JSON in this exact format: "
    '{\"company\": \"Company Name\", \"title\": \"Job Title\"}. '
    "If you cannot determine the company, respond: "
    '{\"company\": null, \"title\": null}.'
)


def extract_lead_info(subject: str, body: str,
                      from_addr: str) -> tuple[Optional[str], Optional[str]]:
    """Use Nemotron to extract (company, title) from an unmatched recruitment email.

    Returns (company, title) or (None, None) on failure / low confidence.
    """
    import json as _json
    try:
        prompt = (
            f"From: {from_addr}\n"
            f"Subject: {subject}\n\n"
            f"Email excerpt:\n{body[:600]}"
        )
        raw = _CLASSIFIER_ROUTER.complete(
            prompt,
            system=_EXTRACT_SYSTEM,
            fallback_order=["ollama_research"],
        )
        # Strip <think> blocks
        text = _re.sub(r"<think>.*?</think>", "", raw, flags=_re.DOTALL).strip()
        # Find first JSON object in response
        m = _re.search(r'\{.*\}', text, _re.DOTALL)
        if not m:
            return None, None
        data = _json.loads(m.group())
        company = data.get("company") or None
        title   = data.get("title") or None
        return company, title
    except Exception:
        return None, None
```

**Step 4: Implement `_scan_unmatched_leads()` in `scripts/imap_sync.py`**

Add this function. It uses the existing IMAP connection after per-job sync:

```python
def _scan_unmatched_leads(conn: imaplib.IMAP4, cfg: dict,
                          db_path: Path,
                          known_message_ids: set[str]) -> int:
    """Scan INBOX for recruitment emails not matched to any pipeline job.

    Calls LLM to extract company/title; inserts qualifying emails as email leads.
    Returns the count of new leads inserted.
    """
    from scripts.db import get_existing_urls, insert_job, add_contact

    lookback = int(cfg.get("lookback_days", 90))
    since = (datetime.now() - timedelta(days=lookback)).strftime("%d-%b-%Y")

    # Broad search — subject matches common recruiter terms
    broad_terms = ["interview", "opportunity", "offer", "application", "role"]
    all_uids: set[bytes] = set()
    for term in broad_terms:
        uids = _search_folder(conn, "INBOX", f'(SUBJECT "{term}")', since)
        all_uids.update(uids)

    existing_urls = get_existing_urls(db_path)
    new_leads = 0

    for uid in all_uids:
        parsed = _parse_message(conn, uid)
        if not parsed:
            continue
        mid = parsed["message_id"]
        if mid in known_message_ids:
            continue   # already synced to some job
        if not _has_recruitment_keyword(parsed["subject"]):
            continue   # false positive from broad search

        company, title = extract_lead_info(
            parsed["subject"], parsed["body"], parsed["from_addr"]
        )
        if not company:
            continue

        # Build a synthetic URL for dedup
        from_domain = _extract_domain(parsed["from_addr"]) or "unknown"
        mid_hash = str(abs(hash(mid)))[:10]
        synthetic_url = f"email://{from_domain}/{mid_hash}"

        if synthetic_url in existing_urls:
            continue   # already captured this lead

        job_id = insert_job(db_path, {
            "title": title or "(untitled)",
            "company": company,
            "url": synthetic_url,
            "source": "email",
            "location": "",
            "is_remote": 0,
            "salary": "",
            "description": parsed["body"][:2000],
            "date_found": datetime.now().isoformat()[:10],
        })
        if job_id:
            add_contact(db_path, job_id=job_id, direction="inbound",
                        subject=parsed["subject"],
                        from_addr=parsed["from_addr"],
                        body=parsed["body"],
                        received_at=parsed["date"][:16] if parsed["date"] else "",
                        message_id=mid)
            known_message_ids.add(mid)
            existing_urls.add(synthetic_url)
            new_leads += 1

    return new_leads
```

**Step 5: Update `sync_all()` to call `_scan_unmatched_leads()`**

In `sync_all()`, after the per-job loop and before `conn.logout()`:

```python
from scripts.db import get_all_message_ids
known_mids = get_all_message_ids(db_path)
summary["new_leads"] = _scan_unmatched_leads(conn, cfg, db_path, known_mids)
```

Also add `"new_leads": 0` to the initial `summary` dict.

**Step 6: Run tests**

```bash
/devl/miniconda3/envs/job-seeker/bin/pytest tests/test_imap_sync.py -v
```

Expected: all pass.

**Step 7: Commit**

```bash
git add scripts/imap_sync.py scripts/db.py tests/test_imap_sync.py
git commit -m "feat: recruiter lead extraction from unmatched inbound emails"
```

---

### Task 5: email_sync background task type

**Files:**
- Modify: `scripts/task_runner.py`
- Test: `tests/test_task_runner.py`

**Context:** Add `email_sync` to the `if/elif` chain in `_run_task()`. `job_id` is 0 (global task). The result summary is stored in the task's `error` field as a string (same pattern as `discovery`). If IMAP config is missing (`FileNotFoundError`), mark failed with a friendly message.

**Step 1: Add test**

Append to `tests/test_task_runner.py`:

```python
def test_run_task_email_sync_success(tmp_path):
    """email_sync task calls sync_all and marks completed with summary."""
    db, _ = _make_db(tmp_path)
    from scripts.db import insert_task, get_task_for_job
    task_id, _ = insert_task(db, "email_sync", 0)

    summary = {"synced": 3, "inbound": 5, "outbound": 2, "new_leads": 1, "errors": []}
    with patch("scripts.imap_sync.sync_all", return_value=summary):
        from scripts.task_runner import _run_task
        _run_task(db, task_id, "email_sync", 0)

    task = get_task_for_job(db, "email_sync", 0)
    assert task["status"] == "completed"
    assert "3 jobs" in task["error"]


def test_run_task_email_sync_file_not_found(tmp_path):
    """email_sync marks failed with helpful message when config is missing."""
    db, _ = _make_db(tmp_path)
    from scripts.db import insert_task, get_task_for_job
    task_id, _ = insert_task(db, "email_sync", 0)

    with patch("scripts.imap_sync.sync_all", side_effect=FileNotFoundError("config/email.yaml")):
        from scripts.task_runner import _run_task
        _run_task(db, task_id, "email_sync", 0)

    task = get_task_for_job(db, "email_sync", 0)
    assert task["status"] == "failed"
    assert "email" in task["error"].lower()
```

**Step 2: Run to confirm failures**

```bash
/devl/miniconda3/envs/job-seeker/bin/pytest tests/test_task_runner.py::test_run_task_email_sync_success tests/test_task_runner.py::test_run_task_email_sync_file_not_found -v
```

Expected: 2 failures.

**Step 3: Add email_sync branch to `_run_task()` in `scripts/task_runner.py`**

Add after the `company_research` elif, before the `else`:

```python
elif task_type == "email_sync":
    try:
        from scripts.imap_sync import sync_all
        result = sync_all(db_path)
        leads = result.get("new_leads", 0)
        errs  = len(result.get("errors", []))
        msg = (
            f"{result['synced']} jobs updated, "
            f"+{result['inbound']} in, +{result['outbound']} out"
            f"{f', {leads} new lead(s)' if leads else ''}"
            f"{f', {errs} error(s)' if errs else ''}"
        )
        update_task_status(db_path, task_id, "completed", error=msg)
        return
    except FileNotFoundError:
        update_task_status(db_path, task_id, "failed",
                           error="Email not configured — go to Settings → Email")
        return
```

**Step 4: Run tests**

```bash
/devl/miniconda3/envs/job-seeker/bin/pytest tests/test_task_runner.py -v
```

Expected: all pass.

**Step 5: Commit**

```bash
git add scripts/task_runner.py tests/test_task_runner.py
git commit -m "feat: add email_sync background task type to task_runner"
```

---

### Task 6: Sync Emails button on Home page

**Files:**
- Modify: `app/Home.py`

**Context:** Home.py has three sections in `left / mid / right` columns (Find Jobs, Score Listings, Send to Notion). Add a fourth section. Since we can't easily add a 4th column to the same row without crowding, add it as a new row below the divider, before the Danger Zone expander. Use the same background task pattern as discovery: check for an in-flight `email_sync` task, disable button if running, poll with `@st.fragment(run_every=4)`.

Also update the imports to include `get_all_message_ids` — no, actually we don't need that. We need `submit_task` (already imported) and `get_task_for_job` (already imported).

Also update the success message to show new_leads if any.

No tests needed for UI pages (Streamlit pages aren't unit-testable without an e2e framework).

**Step 1: Add Email Sync section to `app/Home.py`**

After the `with right:` block and before `st.divider()` (the one before Danger Zone), add:

```python
st.divider()

# ── Email Sync ────────────────────────────────────────────────────────────────
email_left, email_right = st.columns([3, 1])

with email_left:
    st.subheader("Sync Emails")
    st.caption("Pull inbound recruiter emails and match them to active applications. "
               "New recruiter outreach is added to your Job Review queue.")

with email_right:
    _email_task = get_task_for_job(DEFAULT_DB, "email_sync", 0)
    _email_running = _email_task and _email_task["status"] in ("queued", "running")

    if st.button("📧 Sync Emails", use_container_width=True, type="primary",
                 disabled=bool(_email_running)):
        submit_task(DEFAULT_DB, "email_sync", 0)
        st.rerun()

    if _email_running:
        @st.fragment(run_every=4)
        def _email_status():
            t = get_task_for_job(DEFAULT_DB, "email_sync", 0)
            if t and t["status"] in ("queued", "running"):
                st.info("⏳ Syncing emails…")
            else:
                st.rerun()
        _email_status()
    elif _email_task and _email_task["status"] == "completed":
        st.success(f"✅ {_email_task.get('error', 'Done')}")
    elif _email_task and _email_task["status"] == "failed":
        st.error(f"Sync failed: {_email_task.get('error', '')}")
```

**Step 2: Manual smoke test**

```bash
bash /devl/job-seeker/scripts/manage-ui.sh restart
```

Open http://localhost:8501, confirm "Sync Emails" section appears with button.

**Step 3: Commit**

```bash
git add app/Home.py
git commit -m "feat: add Sync Emails background task button to Home page"
```

---

### Task 7: Convert Interviews sync to background task + add stage suggestion banner

**Files:**
- Modify: `app/pages/5_Interviews.py`

**Context:** The sidebar sync button in 5_Interviews.py currently calls `sync_all()` synchronously inside a `with st.spinner(...)` block (lines 38–61). Replace it with `submit_task(DEFAULT_DB, "email_sync", 0)` + fragment polling, matching the pattern in Home.py.

Then add the stage suggestion banner in `_render_card()`. After the interview date form (or at the top of the "if not compact:" block), call `get_unread_stage_signals()`. If any exist, show the most recent one with → Move and Dismiss buttons.

The banner should only show for stages where a stage advancement makes sense: `applied`, `phone_screen`, `interviewing`. Not `offer` or `hired`.

**Step 1: Update imports in `5_Interviews.py`**

Add to the existing `from scripts.db import (...)` block:
- `get_unread_stage_signals`
- `dismiss_stage_signal`

Add to the `from scripts.task_runner import submit_task` line (already present).

**Step 2: Replace synchronous sync button**

Replace the entire `with st.sidebar:` block (lines 38–61) with:

```python
with st.sidebar:
    st.markdown("### 📧 Email Sync")
    _email_task = get_task_for_job(DEFAULT_DB, "email_sync", 0)
    _email_running = _email_task and _email_task["status"] in ("queued", "running")

    if st.button("🔄 Sync Emails", use_container_width=True, type="primary",
                 disabled=bool(_email_running)):
        submit_task(DEFAULT_DB, "email_sync", 0)
        st.rerun()

    if _email_running:
        @st.fragment(run_every=4)
        def _email_sidebar_status():
            t = get_task_for_job(DEFAULT_DB, "email_sync", 0)
            if t and t["status"] in ("queued", "running"):
                st.info("⏳ Syncing…")
            else:
                st.rerun()
        _email_sidebar_status()
    elif _email_task and _email_task["status"] == "completed":
        st.success(_email_task.get("error", "Done"))
    elif _email_task and _email_task["status"] == "failed":
        msg = _email_task.get("error", "")
        if "not configured" in msg.lower():
            st.error("Email not configured. Go to **Settings → Email**.")
        else:
            st.error(f"Sync failed: {msg}")
```

**Step 3: Add stage suggestion banner in `_render_card()`**

Inside `_render_card()`, at the start of the `if not compact:` block (just before `# Advance / Reject buttons`), add:

```python
if stage in ("applied", "phone_screen", "interviewing"):
    signals = get_unread_stage_signals(DEFAULT_DB, job_id=job_id)
    if signals:
        sig = signals[-1]  # most recent
        _SIGNAL_LABELS = {
            "interview_scheduled": ("📞 Phone Screen", "phone_screen"),
            "positive_response":   ("📞 Phone Screen", "phone_screen"),
            "offer_received":      ("📜 Offer",        "offer"),
            "rejected":            ("✗ Reject",        None),
        }
        label_text, target_stage = _SIGNAL_LABELS.get(sig["stage_signal"], (None, None))
        with st.container(border=True):
            st.caption(
                f"💡 Email suggests: **{sig['stage_signal'].replace('_', ' ')}**  \n"
                f"_{sig.get('subject', '')}_ · {(sig.get('received_at') or '')[:10]}"
            )
            b1, b2 = st.columns(2)
            if target_stage and b1.button(
                f"→ {label_text}", key=f"sig_adv_{sig['id']}",
                use_container_width=True, type="primary",
            ):
                if target_stage == "phone_screen" and stage == "applied":
                    advance_to_stage(DEFAULT_DB, job_id=job_id, stage="phone_screen")
                    submit_task(DEFAULT_DB, "company_research", job_id)
                elif target_stage:
                    advance_to_stage(DEFAULT_DB, job_id=job_id, stage=target_stage)
                dismiss_stage_signal(DEFAULT_DB, sig["id"])
                st.rerun()
            elif label_text == "✗ Reject" and b1.button(
                "✗ Reject", key=f"sig_rej_{sig['id']}",
                use_container_width=True,
            ):
                reject_at_stage(DEFAULT_DB, job_id=job_id, rejection_stage=stage)
                dismiss_stage_signal(DEFAULT_DB, sig["id"])
                st.rerun()
            if b2.button("Dismiss", key=f"sig_dis_{sig['id']}",
                         use_container_width=True):
                dismiss_stage_signal(DEFAULT_DB, sig["id"])
                st.rerun()
```

**Step 4: Manual smoke test**

```bash
bash /devl/job-seeker/scripts/manage-ui.sh restart
```

Open Interviews page, confirm sidebar sync button is present and non-blocking.

**Step 5: Commit**

```bash
git add app/pages/5_Interviews.py
git commit -m "feat: non-blocking email sync + stage suggestion banner on Interviews kanban"
```

---

### Task 8: Email leads section in Job Review

**Files:**
- Modify: `app/pages/1_Job_Review.py`
- Modify: `scripts/db.py`

**Context:** Email leads are jobs with `source = 'email'` and `status = 'pending'`. They already appear in the `pending` list returned by `get_jobs_by_status()`. We want to visually separate them at the top when `show_status == 'pending'`.

Add a `get_email_leads(db_path)` helper in `scripts/db.py` that returns pending email-source jobs ordered by `date_found DESC`. In the Job Review page, before the main job list loop, if `show_status == 'pending'`, pull email leads and render them in a distinct section with an `📧 Email Lead` badge. Then render the remaining (non-email) pending jobs below.

**Step 1: Add test for new DB helper**

Append to `tests/test_db.py`:

```python
def test_get_email_leads(tmp_path):
    """get_email_leads returns only source='email' pending jobs."""
    from scripts.db import init_db, insert_job, get_email_leads
    db_path = tmp_path / "test.db"
    init_db(db_path)
    insert_job(db_path, {
        "title": "CSM", "company": "Acme", "url": "https://ex.com/1",
        "source": "linkedin", "location": "Remote", "is_remote": True,
        "salary": "", "description": "", "date_found": "2026-02-21",
    })
    insert_job(db_path, {
        "title": "TAM", "company": "Wiz", "url": "email://wiz.com/abc123",
        "source": "email", "location": "", "is_remote": 0,
        "salary": "", "description": "Hi Alex…", "date_found": "2026-02-21",
    })
    leads = get_email_leads(db_path)
    assert len(leads) == 1
    assert leads[0]["company"] == "Wiz"
    assert leads[0]["source"] == "email"
```

**Step 2: Run to confirm failure**

```bash
/devl/miniconda3/envs/job-seeker/bin/pytest tests/test_db.py::test_get_email_leads -v
```

Expected: FAIL (ImportError or function missing).

**Step 3: Add `get_email_leads()` to `scripts/db.py`**

After `get_jobs_by_status()`:

```python
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
```

**Step 4: Run test**

```bash
/devl/miniconda3/envs/job-seeker/bin/pytest tests/test_db.py::test_get_email_leads -v
```

Expected: PASS.

**Step 5: Update `1_Job_Review.py`**

Add to the top-level import from `scripts.db`:
- `get_email_leads`

After `init_db(DEFAULT_DB)` and before the sidebar filters block, add:

```python
# ── Email leads (shown only when browsing pending) ────────────────────────────
_email_leads = get_email_leads(DEFAULT_DB) if True else []
```

(We always fetch them; the section only renders when `show_status == 'pending'`.)

After `st.divider()` (after the caption line) and before the main `for job in jobs:` loop, add:

```python
if show_status == "pending" and _email_leads:
    st.subheader(f"📧 Email Leads ({len(_email_leads)})")
    st.caption(
        "Inbound recruiter emails not yet matched to a scraped listing. "
        "Approve to move to Job Review; Reject to dismiss."
    )
    for lead in _email_leads:
        lead_id = lead["id"]
        with st.container(border=True):
            left_l, right_l = st.columns([7, 3])
            with left_l:
                st.markdown(f"**{lead['title']}** — {lead['company']}")
                badge_cols = st.columns(4)
                badge_cols[0].caption("📧 Email Lead")
                badge_cols[1].caption(f"📅 {lead.get('date_found', '')}")
                if lead.get("description"):
                    with st.expander("📄 Email excerpt", expanded=False):
                        st.text(lead["description"][:500])
            with right_l:
                if st.button("✅ Approve", key=f"el_approve_{lead_id}",
                             type="primary", use_container_width=True):
                    update_job_status(DEFAULT_DB, [lead_id], "approved")
                    st.rerun()
                if st.button("❌ Reject", key=f"el_reject_{lead_id}",
                             use_container_width=True):
                    update_job_status(DEFAULT_DB, [lead_id], "rejected")
                    st.rerun()
    st.divider()

# Filter out email leads from the main pending list (already shown above)
if show_status == "pending":
    jobs = [j for j in jobs if j.get("source") != "email"]
```

**Step 6: Manual smoke test**

```bash
bash /devl/job-seeker/scripts/manage-ui.sh restart
```

Confirm Job Review shows "Email Leads" section when filtering for pending.

**Step 7: Commit**

```bash
git add scripts/db.py tests/test_db.py app/pages/1_Job_Review.py
git commit -m "feat: show email lead jobs at top of Job Review pending queue"
```

---

### Task 9: Full test run + final polish

**Files:**
- No new files

**Step 1: Run full test suite**

```bash
/devl/miniconda3/envs/job-seeker/bin/pytest tests/ -v
```

Expected: all pass. Fix any regressions before proceeding.

**Step 2: Verify DB exports in `scripts/db.py`**

Confirm that `get_unread_stage_signals`, `dismiss_stage_signal`, `get_all_message_ids`, and `get_email_leads` are imported correctly wherever used:
- `5_Interviews.py` imports `get_unread_stage_signals`, `dismiss_stage_signal`
- `imap_sync.py` imports `get_all_message_ids`
- `1_Job_Review.py` imports `get_email_leads`

Run:
```bash
conda run -n job-seeker python -c "from scripts.db import get_unread_stage_signals, dismiss_stage_signal, get_all_message_ids, get_email_leads; print('OK')"
```

**Step 3: Smoke-test the classifier with real Ollama**

```bash
conda run -n job-seeker python -c "
from scripts.imap_sync import classify_stage_signal
print(classify_stage_signal('Interview Invitation', 'We would love to schedule a 30-min phone screen with you.'))
print(classify_stage_signal('Your application with DataStax', 'We have decided to move forward with other candidates.'))
print(classify_stage_signal('Application received', 'We have received your application and will be in touch.'))
"
```

Expected output:
```
interview_scheduled
rejected
neutral
```

**Step 4: Commit**

```bash
git add -A
git commit -m "chore: verify all email handling imports and run full test suite"
```
