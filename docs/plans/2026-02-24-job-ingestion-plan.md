# Job Ingestion Improvements — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Auto-parse LinkedIn Job Alert digest emails into multiple pending jobs, add a `scrape_url` background task that fills in job details from a URL, and add a Home page widget for manual URL/CSV import.

**Architecture:** New `scripts/scrape_url.py` worker + `update_job_fields` DB helper → `scrape_url` task type in `task_runner.py` → consumed by both the LinkedIn alert parser in `imap_sync.py` and the new Home page URL import section.

**Tech Stack:** Python 3.12, Streamlit, SQLite, requests, BeautifulSoup4, JobSpy (internal scrapers), imap_sync existing patterns

**Reference:** Design doc at `docs/plans/2026-02-24-job-ingestion-design.md`

---

## Task 1: DB helper — `update_job_fields`

**Files:**
- Modify: `scripts/db.py`
- Test: `tests/test_db.py`

**Step 1: Write the failing test**

Add to `tests/test_db.py`:

```python
def test_update_job_fields(tmp_path):
    from scripts.db import init_db, insert_job, update_job_fields
    db = tmp_path / "test.db"
    init_db(db)
    job_id = insert_job(db, {
        "title": "Importing…", "company": "", "url": "https://example.com/job/1",
        "source": "manual", "location": "", "description": "", "date_found": "2026-02-24",
    })
    update_job_fields(db, job_id, {
        "title": "Customer Success Manager",
        "company": "Acme Corp",
        "location": "San Francisco, CA",
        "description": "Great role.",
        "salary": "$120k",
        "is_remote": 1,
    })
    import sqlite3
    conn = sqlite3.connect(db)
    row = dict(conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone())
    conn.close()
    assert row["title"] == "Customer Success Manager"
    assert row["company"] == "Acme Corp"
    assert row["description"] == "Great role."
    assert row["is_remote"] == 1


def test_update_job_fields_ignores_unknown_columns(tmp_path):
    from scripts.db import init_db, insert_job, update_job_fields
    db = tmp_path / "test.db"
    init_db(db)
    job_id = insert_job(db, {
        "title": "Importing…", "company": "", "url": "https://example.com/job/2",
        "source": "manual", "location": "", "description": "", "date_found": "2026-02-24",
    })
    # Should not raise even with an unknown column
    update_job_fields(db, job_id, {"title": "Real Title", "nonexistent_col": "ignored"})
    import sqlite3
    conn = sqlite3.connect(db)
    row = dict(conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone())
    conn.close()
    assert row["title"] == "Real Title"
```

**Step 2: Run test to verify it fails**

```bash
/devl/miniconda3/envs/job-seeker/bin/pytest tests/test_db.py::test_update_job_fields tests/test_db.py::test_update_job_fields_ignores_unknown_columns -v
```
Expected: FAIL — `ImportError: cannot import name 'update_job_fields'`

**Step 3: Implement `update_job_fields` in `scripts/db.py`**

Add after `update_cover_letter`:

```python
_UPDATABLE_JOB_COLS = {
    "title", "company", "url", "source", "location", "is_remote",
    "salary", "description", "match_score", "keyword_gaps",
}


def update_job_fields(db_path: Path = DEFAULT_DB, job_id: int = None,
                      fields: dict = None) -> None:
    """Update arbitrary job columns. Unknown keys are silently ignored."""
    if not job_id or not fields:
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
```

**Step 4: Run tests to verify they pass**

```bash
/devl/miniconda3/envs/job-seeker/bin/pytest tests/test_db.py::test_update_job_fields tests/test_db.py::test_update_job_fields_ignores_unknown_columns -v
```
Expected: PASS

**Step 5: Commit**

```bash
git add scripts/db.py tests/test_db.py
git commit -m "feat: add update_job_fields helper to db.py"
```

---

## Task 2: `scripts/scrape_url.py` + `task_runner.py` integration

**Files:**
- Create: `scripts/scrape_url.py`
- Modify: `scripts/task_runner.py`
- Test: `tests/test_scrape_url.py`

**Step 1: Write the failing tests**

Create `tests/test_scrape_url.py`:

```python
"""Tests for URL-based job scraping."""
from unittest.mock import patch, MagicMock


def _make_db(tmp_path, url="https://www.linkedin.com/jobs/view/99999/"):
    from scripts.db import init_db, insert_job
    db = tmp_path / "test.db"
    init_db(db)
    job_id = insert_job(db, {
        "title": "Importing…", "company": "", "url": url,
        "source": "manual", "location": "", "description": "", "date_found": "2026-02-24",
    })
    return db, job_id


def test_canonicalize_url_linkedin():
    from scripts.scrape_url import canonicalize_url
    messy = (
        "https://www.linkedin.com/jobs/view/4376518925/"
        "?trk=eml-email_job_alert&refId=abc%3D%3D&trackingId=xyz"
    )
    assert canonicalize_url(messy) == "https://www.linkedin.com/jobs/view/4376518925/"


def test_canonicalize_url_linkedin_comm():
    from scripts.scrape_url import canonicalize_url
    comm = "https://www.linkedin.com/comm/jobs/view/4376518925/?trackingId=abc"
    assert canonicalize_url(comm) == "https://www.linkedin.com/jobs/view/4376518925/"


def test_canonicalize_url_generic_strips_utm():
    from scripts.scrape_url import canonicalize_url
    url = "https://jobs.example.com/post/42?utm_source=linkedin&utm_medium=email&jk=real_param"
    result = canonicalize_url(url)
    assert "utm_source" not in result
    assert "real_param" in result


def test_detect_board_linkedin():
    from scripts.scrape_url import _detect_board
    assert _detect_board("https://www.linkedin.com/jobs/view/12345/") == "linkedin"
    assert _detect_board("https://linkedin.com/jobs/view/12345/?tracking=abc") == "linkedin"


def test_detect_board_indeed():
    from scripts.scrape_url import _detect_board
    assert _detect_board("https://www.indeed.com/viewjob?jk=abc123") == "indeed"


def test_detect_board_glassdoor():
    from scripts.scrape_url import _detect_board
    assert _detect_board("https://www.glassdoor.com/job-listing/foo-bar-123.htm") == "glassdoor"


def test_detect_board_generic():
    from scripts.scrape_url import _detect_board
    assert _detect_board("https://jobs.example.com/posting/42") == "generic"


def test_extract_linkedin_job_id():
    from scripts.scrape_url import _extract_linkedin_job_id
    assert _extract_linkedin_job_id("https://www.linkedin.com/jobs/view/4376518925/") == "4376518925"
    assert _extract_linkedin_job_id("https://www.linkedin.com/comm/jobs/view/4376518925/?tracking=x") == "4376518925"
    assert _extract_linkedin_job_id("https://example.com/no-id") is None


def test_scrape_linkedin_updates_job(tmp_path):
    db, job_id = _make_db(tmp_path)

    linkedin_html = """<html><head></head><body>
        <h2 class="top-card-layout__title">Customer Success Manager</h2>
        <a class="topcard__org-name-link">Acme Corp</a>
        <span class="topcard__flavor--bullet">San Francisco, CA</span>
        <div class="show-more-less-html__markup">Exciting CSM role with great benefits.</div>
    </body></html>"""

    mock_resp = MagicMock()
    mock_resp.text = linkedin_html
    mock_resp.raise_for_status = MagicMock()

    with patch("scripts.scrape_url.requests.get", return_value=mock_resp):
        from scripts.scrape_url import scrape_job_url
        result = scrape_job_url(db, job_id)

    assert result.get("title") == "Customer Success Manager"
    assert result.get("company") == "Acme Corp"
    assert "CSM role" in result.get("description", "")

    import sqlite3
    conn = sqlite3.connect(db)
    row = dict(conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone())
    conn.close()
    assert row["title"] == "Customer Success Manager"
    assert row["company"] == "Acme Corp"


def test_scrape_url_generic_json_ld(tmp_path):
    db, job_id = _make_db(tmp_path, url="https://jobs.example.com/post/42")

    json_ld_html = """<html><head>
        <script type="application/ld+json">
        {"@type": "JobPosting", "title": "TAM Role", "description": "Tech account mgmt.",
         "hiringOrganization": {"name": "TechCo"},
         "jobLocation": {"address": {"addressLocality": "Austin, TX"}}}
        </script>
    </head><body></body></html>"""

    mock_resp = MagicMock()
    mock_resp.text = json_ld_html
    mock_resp.raise_for_status = MagicMock()

    with patch("scripts.scrape_url.requests.get", return_value=mock_resp):
        from scripts.scrape_url import scrape_job_url
        result = scrape_job_url(db, job_id)

    assert result.get("title") == "TAM Role"
    assert result.get("company") == "TechCo"


def test_scrape_url_graceful_on_http_error(tmp_path):
    db, job_id = _make_db(tmp_path)
    import requests as req

    with patch("scripts.scrape_url.requests.get", side_effect=req.RequestException("timeout")):
        from scripts.scrape_url import scrape_job_url
        result = scrape_job_url(db, job_id)

    # Should return empty dict and not raise; job row still exists
    assert isinstance(result, dict)
    import sqlite3
    conn = sqlite3.connect(db)
    row = conn.execute("SELECT id FROM jobs WHERE id=?", (job_id,)).fetchone()
    conn.close()
    assert row is not None
```

**Step 2: Run tests to verify they fail**

```bash
/devl/miniconda3/envs/job-seeker/bin/pytest tests/test_scrape_url.py -v
```
Expected: FAIL — `ModuleNotFoundError: No module named 'scripts.scrape_url'`

**Step 3: Implement `scripts/scrape_url.py`**

```python
# scripts/scrape_url.py
"""
Scrape a job listing from its URL and update the job record.

Supports:
  - LinkedIn  (guest jobs API — no auth required)
  - Indeed    (HTML parse)
  - Glassdoor (JobSpy internal scraper, same as enrich_descriptions.py)
  - Generic   (JSON-LD → og:tags fallback)

Usage (background task — called by task_runner):
    from scripts.scrape_url import scrape_job_url
    scrape_job_url(db_path, job_id)
"""
import json
import re
import sqlite3
import sys
from pathlib import Path
from typing import Optional

import requests
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.db import DEFAULT_DB, update_job_fields

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    )
}
_TIMEOUT = 12


def _detect_board(url: str) -> str:
    """Return 'linkedin', 'indeed', 'glassdoor', or 'generic'."""
    url_lower = url.lower()
    if "linkedin.com" in url_lower:
        return "linkedin"
    if "indeed.com" in url_lower:
        return "indeed"
    if "glassdoor.com" in url_lower:
        return "glassdoor"
    return "generic"


def _extract_linkedin_job_id(url: str) -> Optional[str]:
    """Extract numeric job ID from a LinkedIn job URL."""
    m = re.search(r"/jobs/view/(\d+)", url)
    return m.group(1) if m else None


def canonicalize_url(url: str) -> str:
    """
    Strip tracking parameters from a job URL and return a clean canonical form.

    LinkedIn:  https://www.linkedin.com/jobs/view/<id>/?trk=...  →  https://www.linkedin.com/jobs/view/<id>/
    Indeed:    strips utm_* and other tracking params
    Others:    strips utm_source/utm_medium/utm_campaign/trk/refId/trackingId
    """
    url = url.strip()
    if "linkedin.com" in url.lower():
        job_id = _extract_linkedin_job_id(url)
        if job_id:
            return f"https://www.linkedin.com/jobs/view/{job_id}/"
    # For other boards: strip common tracking params
    from urllib.parse import urlparse, urlencode, parse_qsl
    _STRIP_PARAMS = {
        "utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term",
        "trk", "trkEmail", "refId", "trackingId", "lipi", "midToken", "midSig",
        "eid", "otpToken", "ssid", "fmid",
    }
    parsed = urlparse(url)
    clean_qs = urlencode([(k, v) for k, v in parse_qsl(parsed.query) if k not in _STRIP_PARAMS])
    return parsed._replace(query=clean_qs).geturl()


def _scrape_linkedin(url: str) -> dict:
    """Fetch via LinkedIn guest jobs API (no auth required)."""
    job_id = _extract_linkedin_job_id(url)
    if not job_id:
        return {}
    api_url = f"https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{job_id}"
    resp = requests.get(api_url, headers=_HEADERS, timeout=_TIMEOUT)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    def _text(selector, **kwargs):
        tag = soup.find(selector, **kwargs)
        return tag.get_text(strip=True) if tag else ""

    title = _text("h2", class_="top-card-layout__title")
    company = _text("a", class_="topcard__org-name-link") or _text("span", class_="topcard__org-name-link")
    location = _text("span", class_="topcard__flavor--bullet")
    desc_div = soup.find("div", class_="show-more-less-html__markup")
    description = desc_div.get_text(separator="\n", strip=True) if desc_div else ""

    return {k: v for k, v in {
        "title": title,
        "company": company,
        "location": location,
        "description": description,
        "source": "linkedin",
    }.items() if v}


def _scrape_indeed(url: str) -> dict:
    """Scrape an Indeed job page."""
    resp = requests.get(url, headers=_HEADERS, timeout=_TIMEOUT)
    resp.raise_for_status()
    return _parse_json_ld_or_og(resp.text) or {}


def _scrape_glassdoor(url: str) -> dict:
    """Re-use JobSpy's Glassdoor scraper for description fetch."""
    m = re.search(r"jl=(\d+)", url)
    if not m:
        return {}
    try:
        from jobspy.glassdoor import Glassdoor
        from jobspy.glassdoor.constant import fallback_token, headers
        from jobspy.model import ScraperInput, Site
        from jobspy.util import create_session

        scraper = Glassdoor()
        scraper.base_url = "https://www.glassdoor.com/"
        scraper.session = create_session(has_retry=True)
        token = scraper._get_csrf_token()
        headers["gd-csrf-token"] = token if token else fallback_token
        scraper.scraper_input = ScraperInput(site_type=[Site.GLASSDOOR])
        description = scraper._fetch_job_description(int(m.group(1)))
        return {"description": description} if description else {}
    except Exception:
        return {}


def _parse_json_ld_or_og(html: str) -> dict:
    """Extract job fields from JSON-LD structured data, then og: meta tags."""
    soup = BeautifulSoup(html, "html.parser")

    # Try JSON-LD first
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
            if isinstance(data, list):
                data = next((d for d in data if d.get("@type") == "JobPosting"), {})
            if data.get("@type") == "JobPosting":
                org = data.get("hiringOrganization") or {}
                loc = (data.get("jobLocation") or {})
                if isinstance(loc, list):
                    loc = loc[0] if loc else {}
                addr = loc.get("address") or {}
                location = (
                    addr.get("addressLocality", "") or
                    addr.get("addressRegion", "") or
                    addr.get("addressCountry", "")
                )
                return {k: v for k, v in {
                    "title": data.get("title", ""),
                    "company": org.get("name", ""),
                    "location": location,
                    "description": data.get("description", ""),
                    "salary": str(data.get("baseSalary", "")) if data.get("baseSalary") else "",
                }.items() if v}
        except Exception:
            continue

    # Fall back to og: meta tags
    def _meta(prop):
        tag = soup.find("meta", property=prop) or soup.find("meta", attrs={"name": prop})
        return (tag or {}).get("content", "") if tag else ""

    title = _meta("og:title") or (soup.find("title") or {}).get_text(strip=True)
    description = _meta("og:description")
    return {k: v for k, v in {"title": title, "description": description}.items() if v}


def _scrape_generic(url: str) -> dict:
    resp = requests.get(url, headers=_HEADERS, timeout=_TIMEOUT)
    resp.raise_for_status()
    return _parse_json_ld_or_og(resp.text) or {}


def scrape_job_url(db_path: Path = DEFAULT_DB, job_id: int = None) -> dict:
    """
    Fetch the job listing at the stored URL and update the job record.

    Returns the dict of fields that were scraped (may be empty on failure).
    Does not raise — failures are logged and the job row is left as-is.
    """
    if not job_id:
        return {}

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT url FROM jobs WHERE id=?", (job_id,)).fetchone()
    conn.close()
    if not row:
        return {}

    url = row["url"] or ""
    if not url.startswith("http"):
        return {}

    board = _detect_board(url)
    try:
        if board == "linkedin":
            fields = _scrape_linkedin(url)
        elif board == "indeed":
            fields = _scrape_indeed(url)
        elif board == "glassdoor":
            fields = _scrape_glassdoor(url)
        else:
            fields = _scrape_generic(url)
    except requests.RequestException as exc:
        print(f"[scrape_url] HTTP error for job {job_id} ({url}): {exc}")
        return {}
    except Exception as exc:
        print(f"[scrape_url] Error scraping job {job_id} ({url}): {exc}")
        return {}

    if fields:
        # Never overwrite the URL or source with empty values
        fields.pop("url", None)
        update_job_fields(db_path, job_id, fields)
        print(f"[scrape_url] job {job_id}: scraped '{fields.get('title', '?')}' @ {fields.get('company', '?')}")

    return fields
```

**Step 4: Add `scrape_url` task type to `scripts/task_runner.py`**

In `_run_task`, add a new `elif` branch after `enrich_descriptions` and before the final `else`:

```python
        elif task_type == "scrape_url":
            from scripts.scrape_url import scrape_job_url
            fields = scrape_job_url(db_path, job_id)
            title = fields.get("title") or job.get("url", "?")
            company = fields.get("company", "")
            msg = f"{title}" + (f" @ {company}" if company else "")
            update_task_status(db_path, task_id, "completed", error=msg)
            return
```

**Step 5: Run all tests**

```bash
/devl/miniconda3/envs/job-seeker/bin/pytest tests/test_scrape_url.py -v
```
Expected: all PASS

**Step 6: Commit**

```bash
git add scripts/scrape_url.py scripts/task_runner.py tests/test_scrape_url.py
git commit -m "feat: add scrape_url background task for URL-based job import"
```

---

## Task 3: LinkedIn Job Alert email parser

**Files:**
- Modify: `scripts/imap_sync.py`
- Test: `tests/test_imap_sync.py`

**Step 1: Write the failing tests**

Add to `tests/test_imap_sync.py`:

```python
def test_parse_linkedin_alert_extracts_jobs():
    from scripts.imap_sync import parse_linkedin_alert
    body = """\
Your job alert for customer success manager in United States
New jobs match your preferences.
Manage alerts: https://www.linkedin.com/comm/jobs/alerts?...

Customer Success Manager
Reflow
California, United States
View job: https://www.linkedin.com/comm/jobs/view/4376518925/?trackingId=abc%3D%3D&refId=xyz

---------------------------------------------------------

Customer Engagement Manager
Bitwarden
United States

2 school alumni
Apply with resume & profile
View job: https://www.linkedin.com/comm/jobs/view/4359824983/?trackingId=def%3D%3D

---------------------------------------------------------

"""
    jobs = parse_linkedin_alert(body)
    assert len(jobs) == 2
    assert jobs[0]["title"] == "Customer Success Manager"
    assert jobs[0]["company"] == "Reflow"
    assert jobs[0]["location"] == "California, United States"
    assert jobs[0]["url"] == "https://www.linkedin.com/jobs/view/4376518925/"
    assert jobs[1]["title"] == "Customer Engagement Manager"
    assert jobs[1]["company"] == "Bitwarden"
    assert jobs[1]["url"] == "https://www.linkedin.com/jobs/view/4359824983/"


def test_parse_linkedin_alert_skips_blocks_without_view_job():
    from scripts.imap_sync import parse_linkedin_alert
    body = """\
Customer Success Manager
Some Company
United States

---------------------------------------------------------

Valid Job Title
Valid Company
Remote
View job: https://www.linkedin.com/comm/jobs/view/1111111/?x=y

---------------------------------------------------------
"""
    jobs = parse_linkedin_alert(body)
    assert len(jobs) == 1
    assert jobs[0]["title"] == "Valid Job Title"


def test_parse_linkedin_alert_empty_body():
    from scripts.imap_sync import parse_linkedin_alert
    assert parse_linkedin_alert("") == []
    assert parse_linkedin_alert("No jobs here.") == []
```

**Step 2: Run tests to verify they fail**

```bash
/devl/miniconda3/envs/job-seeker/bin/pytest tests/test_imap_sync.py::test_parse_linkedin_alert_extracts_jobs tests/test_imap_sync.py::test_parse_linkedin_alert_skips_blocks_without_view_job tests/test_imap_sync.py::test_parse_linkedin_alert_empty_body -v
```
Expected: FAIL — `ImportError: cannot import name 'parse_linkedin_alert'`

**Step 3: Implement `parse_linkedin_alert` in `scripts/imap_sync.py`**

Add after the existing `_has_todo_keyword` function (around line 391):

```python
_LINKEDIN_ALERT_SENDER = "jobalerts-noreply@linkedin.com"

# Social-proof / nav lines to skip when parsing alert blocks
_ALERT_SKIP_PHRASES = {
    "alumni", "apply with", "actively hiring", "manage alerts",
    "view all jobs", "your job alert", "new jobs match",
    "unsubscribe", "linkedin corporation",
}


def parse_linkedin_alert(body: str) -> list[dict]:
    """
    Parse the plain-text body of a LinkedIn Job Alert digest email.

    Returns a list of dicts: {title, company, location, url}.
    URL is canonicalized to https://www.linkedin.com/jobs/view/<id>/
    (tracking parameters stripped).
    """
    jobs = []
    # Split on separator lines (10+ dashes)
    blocks = re.split(r"\n\s*-{10,}\s*\n", body)
    for block in blocks:
        lines = [ln.strip() for ln in block.strip().splitlines() if ln.strip()]

        # Find "View job:" URL
        url = None
        for line in lines:
            m = re.search(r"View job:\s*(https?://\S+)", line, re.IGNORECASE)
            if m:
                raw_url = m.group(1)
                job_id_m = re.search(r"/jobs/view/(\d+)", raw_url)
                if job_id_m:
                    url = f"https://www.linkedin.com/jobs/view/{job_id_m.group(1)}/"
                break
        if not url:
            continue

        # Filter noise lines
        content = [
            ln for ln in lines
            if not any(p in ln.lower() for p in _ALERT_SKIP_PHRASES)
            and not ln.lower().startswith("view job:")
            and not ln.startswith("http")
        ]
        if len(content) < 2:
            continue

        jobs.append({
            "title": content[0],
            "company": content[1],
            "location": content[2] if len(content) > 2 else "",
            "url": url,
        })
    return jobs
```

**Step 4: Wire the parser into `_scan_unmatched_leads`**

In `_scan_unmatched_leads`, inside the `for uid in all_uids:` loop, add a detection block immediately after the `if mid in known_message_ids: continue` check (before the existing `_has_recruitment_keyword` check):

```python
        # ── LinkedIn Job Alert digest — parse each card individually ──────
        if _LINKEDIN_ALERT_SENDER in parsed["from_addr"].lower():
            cards = parse_linkedin_alert(parsed["body"])
            for card in cards:
                if card["url"] in existing_urls:
                    continue
                job_id = insert_job(db_path, {
                    "title": card["title"],
                    "company": card["company"],
                    "url": card["url"],
                    "source": "linkedin",
                    "location": card["location"],
                    "is_remote": 0,
                    "salary": "",
                    "description": "",
                    "date_found": datetime.now().isoformat()[:10],
                })
                if job_id:
                    from scripts.task_runner import submit_task
                    submit_task(db_path, "scrape_url", job_id)
                    existing_urls.add(card["url"])
                    new_leads += 1
                    print(f"[imap] LinkedIn alert → {card['company']} — {card['title']}")
            known_message_ids.add(mid)
            continue  # skip normal LLM extraction path
```

**Step 5: Run all imap_sync tests**

```bash
/devl/miniconda3/envs/job-seeker/bin/pytest tests/test_imap_sync.py -v
```
Expected: all PASS (including the 3 new tests)

**Step 6: Commit**

```bash
git add scripts/imap_sync.py tests/test_imap_sync.py
git commit -m "feat: auto-parse LinkedIn Job Alert digest emails into pending jobs"
```

---

## Task 4: Home page — Add Job(s) by URL

**Files:**
- Modify: `app/Home.py`

No unit tests — this is pure Streamlit UI. Verify manually by pasting a URL and checking the DB.

**Step 1: Add `_queue_url_imports` helper and the new section to `app/Home.py`**

Add to the imports at the top (after the existing `from scripts.db import ...` line):

```python
from scripts.db import DEFAULT_DB, init_db, get_job_counts, purge_jobs, purge_email_data, \
    kill_stuck_tasks, get_task_for_job, get_active_tasks, insert_job, get_existing_urls
```

Add this helper function before the Streamlit layout code (after the `init_db` call at the top):

```python
def _queue_url_imports(db_path: Path, urls: list[str]) -> int:
    """Insert each URL as a pending manual job and queue a scrape_url task.
    Returns count of newly queued jobs."""
    from datetime import datetime
    from scripts.scrape_url import canonicalize_url
    existing = get_existing_urls(db_path)
    queued = 0
    for url in urls:
        url = canonicalize_url(url.strip())
        if not url.startswith("http"):
            continue
        if url in existing:
            continue
        job_id = insert_job(db_path, {
            "title": "Importing…",
            "company": "",
            "url": url,
            "source": "manual",
            "location": "",
            "description": "",
            "date_found": datetime.now().isoformat()[:10],
        })
        if job_id:
            submit_task(db_path, "scrape_url", job_id)
            queued += 1
    return queued
```

Add a new section between the Email Sync divider and the Danger Zone expander. Replace:

```python
st.divider()

# ── Danger zone: purge + re-scrape ────────────────────────────────────────────
```

with:

```python
st.divider()

# ── Add Jobs by URL ───────────────────────────────────────────────────────────
add_left, add_right = st.columns([3, 1])
with add_left:
    st.subheader("Add Jobs by URL")
    st.caption("Paste job listing URLs to import and scrape in the background. "
               "Supports LinkedIn, Indeed, Glassdoor, and most job boards.")

url_tab, csv_tab = st.tabs(["Paste URLs", "Upload CSV"])

with url_tab:
    url_text = st.text_area(
        "urls",
        placeholder="https://www.linkedin.com/jobs/view/1234567/\nhttps://www.indeed.com/viewjob?jk=abc",
        height=100,
        label_visibility="collapsed",
    )
    if st.button("📥 Add Jobs", key="add_urls_btn", use_container_width=True,
                 disabled=not (url_text or "").strip()):
        _urls = [u.strip() for u in url_text.strip().splitlines() if u.strip().startswith("http")]
        if _urls:
            _n = _queue_url_imports(DEFAULT_DB, _urls)
            if _n:
                st.success(f"Queued {_n} job{'s' if _n != 1 else ''} for import. Check Job Review shortly.")
            else:
                st.info("All URLs already in the database.")
            st.rerun()

with csv_tab:
    csv_file = st.file_uploader("CSV with a URL column", type=["csv"],
                                label_visibility="collapsed")
    if csv_file:
        import csv as _csv
        import io as _io
        reader = _csv.DictReader(_io.StringIO(csv_file.read().decode("utf-8", errors="replace")))
        _csv_urls = []
        for row in reader:
            for val in row.values():
                if val and val.strip().startswith("http"):
                    _csv_urls.append(val.strip())
                    break
        if _csv_urls:
            st.caption(f"Found {len(_csv_urls)} URL(s) in CSV.")
            if st.button("📥 Import CSV Jobs", key="add_csv_btn", use_container_width=True):
                _n = _queue_url_imports(DEFAULT_DB, _csv_urls)
                st.success(f"Queued {_n} job{'s' if _n != 1 else ''} for import.")
                st.rerun()
        else:
            st.warning("No URLs found — CSV must have a column whose values start with http.")

# Active scrape_url tasks status
@st.fragment(run_every=3)
def _scrape_status():
    import sqlite3 as _sq
    conn = _sq.connect(DEFAULT_DB)
    conn.row_factory = _sq.Row
    rows = conn.execute(
        """SELECT bt.status, bt.error, j.title, j.company, j.url
           FROM background_tasks bt
           JOIN jobs j ON j.id = bt.job_id
           WHERE bt.task_type = 'scrape_url'
             AND bt.updated_at >= datetime('now', '-5 minutes')
           ORDER BY bt.updated_at DESC LIMIT 20"""
    ).fetchall()
    conn.close()
    if not rows:
        return
    st.caption("Recent URL imports:")
    for r in rows:
        if r["status"] == "running":
            st.info(f"⏳ Scraping {r['url']}")
        elif r["status"] == "completed":
            label = f"{r['title']}" + (f" @ {r['company']}" if r['company'] else "")
            st.success(f"✅ {label}")
        elif r["status"] == "failed":
            st.error(f"❌ {r['url']} — {r['error'] or 'scrape failed'}")

_scrape_status()

st.divider()

# ── Danger zone: purge + re-scrape ────────────────────────────────────────────
```

**Step 2: Check `background_tasks` schema has an `updated_at` column**

The status fragment queries `bt.updated_at`. Verify it exists:

```bash
conda run -n job-seeker python -c "
import sqlite3
from scripts.db import DEFAULT_DB, init_db
init_db(DEFAULT_DB)
conn = sqlite3.connect(DEFAULT_DB)
print(conn.execute('PRAGMA table_info(background_tasks)').fetchall())
"
```

If `updated_at` is missing, add a migration in `scripts/db.py`'s `_migrate_db` function:

```python
    try:
        conn.execute("ALTER TABLE background_tasks ADD COLUMN updated_at TEXT DEFAULT (datetime('now'))")
    except sqlite3.OperationalError:
        pass
```

And update `update_task_status` in `db.py` to set `updated_at = datetime('now')` on every status change:

```python
def update_task_status(db_path, task_id, status, error=None):
    conn = sqlite3.connect(db_path)
    conn.execute(
        "UPDATE background_tasks SET status=?, error=?, updated_at=datetime('now') WHERE id=?",
        (status, error, task_id),
    )
    conn.commit()
    conn.close()
```

**Step 3: Restart the UI and manually verify**

```bash
bash /devl/job-seeker/scripts/manage-ui.sh restart
```

Test:
1. Paste `https://www.linkedin.com/jobs/view/4376518925/` into the text area
2. Click "📥 Add Jobs" — should show "Queued 1 job for import"
3. Go to Job Review → should see a pending job (Reflow - Customer Success Manager once scraped)

**Step 4: Commit**

```bash
git add app/Home.py
git commit -m "feat: add 'Add Jobs by URL' section to Home page with background scraping"
```

---

## Final: push to remote

```bash
git push origin main
```
