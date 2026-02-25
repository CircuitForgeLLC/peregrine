# Job Seeker Web UI Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a Streamlit web UI with SQLite staging so Meghan can review scraped jobs, approve/batch-sync to Notion, edit settings, and complete her AIHawk profile.

**Architecture:** `discover.py` writes to a local SQLite `staging.db` instead of Notion directly. Streamlit pages read/write SQLite for job review, YAML files for settings and resume. A new `sync.py` pushes approved jobs to Notion on demand.

**Tech Stack:** Python 3.12, Streamlit (already installed), sqlite3 (stdlib), pyyaml, notion-client, conda env `job-seeker`

---

## Task 1: SQLite DB helpers (`db.py`)

**Files:**
- Create: `scripts/db.py`
- Create: `tests/test_db.py`
- Modify: `.gitignore` (add `staging.db`)

**Step 1: Add staging.db to .gitignore**

```bash
echo "staging.db" >> /devl/job-seeker/.gitignore
```

**Step 2: Write failing tests**

```python
# tests/test_db.py
import pytest
import sqlite3
from pathlib import Path
from unittest.mock import patch


def test_init_db_creates_jobs_table(tmp_path):
    """init_db creates a jobs table with correct schema."""
    from scripts.db import init_db
    db_path = tmp_path / "test.db"
    init_db(db_path)
    conn = sqlite3.connect(db_path)
    cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='jobs'")
    assert cursor.fetchone() is not None
    conn.close()


def test_insert_job_returns_id(tmp_path):
    """insert_job inserts a row and returns its id."""
    from scripts.db import init_db, insert_job
    db_path = tmp_path / "test.db"
    init_db(db_path)
    job = {
        "title": "CSM", "company": "Acme", "url": "https://example.com/1",
        "source": "linkedin", "location": "Remote", "is_remote": True,
        "salary": "$100k", "description": "Great role", "date_found": "2026-02-20",
    }
    row_id = insert_job(db_path, job)
    assert isinstance(row_id, int)
    assert row_id > 0


def test_insert_job_skips_duplicate_url(tmp_path):
    """insert_job returns None if URL already exists."""
    from scripts.db import init_db, insert_job
    db_path = tmp_path / "test.db"
    init_db(db_path)
    job = {"title": "CSM", "company": "Acme", "url": "https://example.com/1",
           "source": "linkedin", "location": "Remote", "is_remote": True,
           "salary": "", "description": "", "date_found": "2026-02-20"}
    insert_job(db_path, job)
    result = insert_job(db_path, job)
    assert result is None


def test_get_jobs_by_status(tmp_path):
    """get_jobs_by_status returns only jobs with matching status."""
    from scripts.db import init_db, insert_job, get_jobs_by_status, update_job_status
    db_path = tmp_path / "test.db"
    init_db(db_path)
    job = {"title": "CSM", "company": "Acme", "url": "https://example.com/1",
           "source": "linkedin", "location": "Remote", "is_remote": True,
           "salary": "", "description": "", "date_found": "2026-02-20"}
    row_id = insert_job(db_path, job)
    update_job_status(db_path, [row_id], "approved")
    approved = get_jobs_by_status(db_path, "approved")
    pending = get_jobs_by_status(db_path, "pending")
    assert len(approved) == 1
    assert len(pending) == 0


def test_update_job_status_batch(tmp_path):
    """update_job_status updates multiple rows at once."""
    from scripts.db import init_db, insert_job, update_job_status, get_jobs_by_status
    db_path = tmp_path / "test.db"
    init_db(db_path)
    ids = []
    for i in range(3):
        job = {"title": f"Job {i}", "company": "Co", "url": f"https://example.com/{i}",
               "source": "indeed", "location": "Remote", "is_remote": True,
               "salary": "", "description": "", "date_found": "2026-02-20"}
        ids.append(insert_job(db_path, job))
    update_job_status(db_path, ids, "rejected")
    assert len(get_jobs_by_status(db_path, "rejected")) == 3
```

**Step 3: Run tests — expect ImportError**

```bash
conda run -n job-seeker pytest tests/test_db.py -v
```

Expected: `ModuleNotFoundError: No module named 'scripts.db'`

**Step 4: Write `scripts/db.py`**

```python
# scripts/db.py
"""
SQLite staging layer for job listings.
Jobs flow: pending → approved/rejected → synced
"""
import sqlite3
from pathlib import Path
from typing import Optional

DEFAULT_DB = Path(__file__).parent.parent / "staging.db"

CREATE_JOBS = """
CREATE TABLE IF NOT EXISTS jobs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    title           TEXT,
    company         TEXT,
    url             TEXT UNIQUE,
    source          TEXT,
    location        TEXT,
    is_remote       INTEGER DEFAULT 0,
    salary          TEXT,
    description     TEXT,
    match_score     REAL,
    keyword_gaps    TEXT,
    date_found      TEXT,
    status          TEXT DEFAULT 'pending',
    notion_page_id  TEXT
);
"""


def init_db(db_path: Path = DEFAULT_DB) -> None:
    """Create tables if they don't exist."""
    conn = sqlite3.connect(db_path)
    conn.execute(CREATE_JOBS)
    conn.commit()
    conn.close()


def insert_job(db_path: Path = DEFAULT_DB, job: dict = None) -> Optional[int]:
    """
    Insert a job. Returns row id, or None if URL already exists.
    """
    if job is None:
        return None
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.execute(
            """INSERT INTO jobs
               (title, company, url, source, location, is_remote, salary, description, date_found)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                job.get("title", ""),
                job.get("company", ""),
                job.get("url", ""),
                job.get("source", ""),
                job.get("location", ""),
                int(bool(job.get("is_remote", False))),
                job.get("salary", ""),
                job.get("description", ""),
                job.get("date_found", ""),
            ),
        )
        conn.commit()
        return cursor.lastrowid
    except sqlite3.IntegrityError:
        return None  # duplicate URL
    finally:
        conn.close()


def get_jobs_by_status(db_path: Path = DEFAULT_DB, status: str = "pending") -> list[dict]:
    """Return all jobs with the given status as a list of dicts."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.execute(
        "SELECT * FROM jobs WHERE status = ? ORDER BY date_found DESC, id DESC",
        (status,),
    )
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows


def get_job_counts(db_path: Path = DEFAULT_DB) -> dict:
    """Return counts per status."""
    conn = sqlite3.connect(db_path)
    cursor = conn.execute(
        "SELECT status, COUNT(*) as n FROM jobs GROUP BY status"
    )
    counts = {row[0]: row[1] for row in cursor.fetchall()}
    conn.close()
    return counts


def update_job_status(db_path: Path = DEFAULT_DB, ids: list[int] = None, status: str = "approved") -> None:
    """Batch-update status for a list of job IDs."""
    if not ids:
        return
    conn = sqlite3.connect(db_path)
    conn.execute(
        f"UPDATE jobs SET status = ? WHERE id IN ({','.join('?' * len(ids))})",
        [status] + list(ids),
    )
    conn.commit()
    conn.close()


def get_existing_urls(db_path: Path = DEFAULT_DB) -> set[str]:
    """Return all URLs already in staging (any status)."""
    conn = sqlite3.connect(db_path)
    cursor = conn.execute("SELECT url FROM jobs")
    urls = {row[0] for row in cursor.fetchall()}
    conn.close()
    return urls


def write_match_scores(db_path: Path = DEFAULT_DB, job_id: int = None,
                       score: float = 0.0, gaps: str = "") -> None:
    """Write match score and keyword gaps back to a job row."""
    conn = sqlite3.connect(db_path)
    conn.execute(
        "UPDATE jobs SET match_score = ?, keyword_gaps = ? WHERE id = ?",
        (score, gaps, job_id),
    )
    conn.commit()
    conn.close()
```

**Step 5: Run tests — expect 5 passing**

```bash
conda run -n job-seeker pytest tests/test_db.py -v
```

Expected: `5 passed`

**Step 6: Commit**

```bash
cd /devl/job-seeker
git add scripts/db.py tests/test_db.py .gitignore
git commit -m "feat: add SQLite staging layer (db.py)"
```

---

## Task 2: Update `discover.py` to write to SQLite

**Files:**
- Modify: `scripts/discover.py`
- Modify: `tests/test_discover.py`

**Step 1: Update the tests**

Replace the existing `tests/test_discover.py` with this version that tests SQLite writes:

```python
# tests/test_discover.py
import pytest
from unittest.mock import patch, MagicMock
import pandas as pd
from pathlib import Path

SAMPLE_JOB = {
    "title": "Customer Success Manager",
    "company": "Acme Corp",
    "location": "Remote",
    "is_remote": True,
    "job_url": "https://linkedin.com/jobs/view/123456",
    "site": "linkedin",
    "min_amount": 90000,
    "max_amount": 120000,
    "salary_source": "$90,000 - $120,000",
    "description": "Great CS role",
}

SAMPLE_FM = {
    "title_field": "Salary", "job_title": "Job Title", "company": "Company Name",
    "url": "Role Link", "source": "Job Source", "status": "Status of Application",
    "status_new": "Application Submitted", "date_found": "Date Found",
    "remote": "Remote", "match_score": "Match Score",
    "keyword_gaps": "Keyword Gaps", "notes": "Notes", "job_description": "Job Description",
}

SAMPLE_NOTION_CFG = {"token": "secret_test", "database_id": "fake-db-id", "field_map": SAMPLE_FM}
SAMPLE_PROFILES_CFG = {
    "profiles": [{"name": "cs", "titles": ["Customer Success Manager"],
                  "locations": ["Remote"], "boards": ["linkedin"],
                  "results_per_board": 5, "hours_old": 72}]
}


def make_jobs_df(jobs=None):
    return pd.DataFrame(jobs or [SAMPLE_JOB])


def test_discover_writes_to_sqlite(tmp_path):
    """run_discovery inserts new jobs into SQLite staging db."""
    from scripts.discover import run_discovery
    from scripts.db import get_jobs_by_status

    db_path = tmp_path / "test.db"
    with patch("scripts.discover.load_config", return_value=(SAMPLE_PROFILES_CFG, SAMPLE_NOTION_CFG)), \
         patch("scripts.discover.scrape_jobs", return_value=make_jobs_df()), \
         patch("scripts.discover.Client"):
        run_discovery(db_path=db_path)

    jobs = get_jobs_by_status(db_path, "pending")
    assert len(jobs) == 1
    assert jobs[0]["title"] == "Customer Success Manager"


def test_discover_skips_duplicate_urls(tmp_path):
    """run_discovery does not insert a job whose URL is already in SQLite."""
    from scripts.discover import run_discovery
    from scripts.db import init_db, insert_job, get_jobs_by_status

    db_path = tmp_path / "test.db"
    init_db(db_path)
    insert_job(db_path, {
        "title": "Old", "company": "X", "url": "https://linkedin.com/jobs/view/123456",
        "source": "linkedin", "location": "Remote", "is_remote": True,
        "salary": "", "description": "", "date_found": "2026-01-01",
    })

    with patch("scripts.discover.load_config", return_value=(SAMPLE_PROFILES_CFG, SAMPLE_NOTION_CFG)), \
         patch("scripts.discover.scrape_jobs", return_value=make_jobs_df()), \
         patch("scripts.discover.Client"):
        run_discovery(db_path=db_path)

    jobs = get_jobs_by_status(db_path, "pending")
    assert len(jobs) == 1  # only the pre-existing one, not a duplicate


def test_discover_pushes_new_jobs():
    """Legacy: discover still calls push_to_notion when notion_push=True."""
    from scripts.discover import run_discovery
    import tempfile, os
    db_path = Path(tempfile.mktemp(suffix=".db"))
    try:
        with patch("scripts.discover.load_config", return_value=(SAMPLE_PROFILES_CFG, SAMPLE_NOTION_CFG)), \
             patch("scripts.discover.scrape_jobs", return_value=make_jobs_df()), \
             patch("scripts.discover.push_to_notion") as mock_push, \
             patch("scripts.discover.Client"):
            run_discovery(db_path=db_path, notion_push=True)
        assert mock_push.call_count == 1
    finally:
        if db_path.exists():
            os.unlink(db_path)


def test_push_to_notion_sets_status_new():
    """push_to_notion always sets Status to the configured status_new value."""
    from scripts.discover import push_to_notion
    mock_notion = MagicMock()
    push_to_notion(mock_notion, "fake-db-id", SAMPLE_JOB, SAMPLE_FM)
    call_kwargs = mock_notion.pages.create.call_args[1]
    status = call_kwargs["properties"]["Status of Application"]["select"]["name"]
    assert status == "Application Submitted"
```

**Step 2: Run tests — some will fail**

```bash
conda run -n job-seeker pytest tests/test_discover.py -v
```

Expected: `test_discover_writes_to_sqlite` and `test_discover_skips_duplicate_urls` fail.

**Step 3: Update `scripts/discover.py`**

Add `db_path` and `notion_push` parameters to `run_discovery`. Default writes to SQLite only:

```python
# scripts/discover.py
"""
JobSpy → SQLite staging pipeline (default) or Notion (notion_push=True).

Usage:
    conda run -n job-seeker python scripts/discover.py
"""
import yaml
from datetime import datetime
from pathlib import Path

import pandas as pd
from jobspy import scrape_jobs
from notion_client import Client

from scripts.db import DEFAULT_DB, init_db, insert_job, get_existing_urls as db_existing_urls

CONFIG_DIR = Path(__file__).parent.parent / "config"
NOTION_CFG = CONFIG_DIR / "notion.yaml"
PROFILES_CFG = CONFIG_DIR / "search_profiles.yaml"


def load_config() -> tuple[dict, dict]:
    profiles = yaml.safe_load(PROFILES_CFG.read_text())
    notion_cfg = yaml.safe_load(NOTION_CFG.read_text())
    return profiles, notion_cfg


def get_existing_urls(notion: Client, db_id: str, url_field: str) -> set[str]:
    """Return the set of all job URLs already tracked in Notion (for notion_push mode)."""
    existing: set[str] = set()
    has_more = True
    start_cursor = None
    while has_more:
        kwargs: dict = {"database_id": db_id, "page_size": 100}
        if start_cursor:
            kwargs["start_cursor"] = start_cursor
        resp = notion.databases.query(**kwargs)
        for page in resp["results"]:
            url = page["properties"].get(url_field, {}).get("url")
            if url:
                existing.add(url)
        has_more = resp.get("has_more", False)
        start_cursor = resp.get("next_cursor")
    return existing


def push_to_notion(notion: Client, db_id: str, job: dict, fm: dict) -> None:
    """Create a new page in the Notion jobs database for a single listing."""
    min_amt = job.get("min_amount")
    max_amt = job.get("max_amount")
    if min_amt and max_amt and not (pd.isna(min_amt) or pd.isna(max_amt)):
        title_content = f"${int(min_amt):,} – ${int(max_amt):,}"
    elif job.get("salary_source") and str(job["salary_source"]) not in ("nan", "None", ""):
        title_content = str(job["salary_source"])
    else:
        title_content = str(job.get("title", "Unknown"))

    job_url = str(job.get("job_url", "") or "")
    if job_url in ("nan", "None"):
        job_url = ""

    notion.pages.create(
        parent={"database_id": db_id},
        properties={
            fm["title_field"]: {"title": [{"text": {"content": title_content}}]},
            fm["job_title"]:   {"rich_text": [{"text": {"content": str(job.get("title", "Unknown"))}}]},
            fm["company"]:     {"rich_text": [{"text": {"content": str(job.get("company", "") or "")}}]},
            fm["url"]:         {"url": job_url or None},
            fm["source"]:      {"multi_select": [{"name": str(job.get("site", "unknown")).title()}]},
            fm["status"]:      {"select": {"name": fm["status_new"]}},
            fm["remote"]:      {"checkbox": bool(job.get("is_remote", False))},
            fm["date_found"]:  {"date": {"start": datetime.now().isoformat()[:10]}},
        },
    )


def run_discovery(db_path: Path = DEFAULT_DB, notion_push: bool = False) -> None:
    profiles_cfg, notion_cfg = load_config()
    fm = notion_cfg["field_map"]

    # SQLite dedup
    init_db(db_path)
    existing_urls = db_existing_urls(db_path)

    # Notion dedup (only in notion_push mode)
    notion = None
    if notion_push:
        notion = Client(auth=notion_cfg["token"])
        existing_urls |= get_existing_urls(notion, notion_cfg["database_id"], fm["url"])

    print(f"[discover] {len(existing_urls)} existing listings")
    new_count = 0

    for profile in profiles_cfg["profiles"]:
        print(f"\n[discover] Profile: {profile['name']}")
        for location in profile["locations"]:
            print(f"  Scraping: {location}")
            jobs: pd.DataFrame = scrape_jobs(
                site_name=profile["boards"],
                search_term=" OR ".join(f'"{t}"' for t in profile["titles"]),
                location=location,
                results_wanted=profile.get("results_per_board", 25),
                hours_old=profile.get("hours_old", 72),
                linkedin_fetch_description=True,
            )

            for _, job in jobs.iterrows():
                url = str(job.get("job_url", "") or "")
                if not url or url in ("nan", "None") or url in existing_urls:
                    continue

                job_dict = job.to_dict()

                # Always write to SQLite staging
                min_amt = job_dict.get("min_amount")
                max_amt = job_dict.get("max_amount")
                salary_str = ""
                if min_amt and max_amt and not (pd.isna(min_amt) or pd.isna(max_amt)):
                    salary_str = f"${int(min_amt):,} – ${int(max_amt):,}"
                elif job_dict.get("salary_source") and str(job_dict["salary_source"]) not in ("nan", "None", ""):
                    salary_str = str(job_dict["salary_source"])

                insert_job(db_path, {
                    "title": str(job_dict.get("title", "")),
                    "company": str(job_dict.get("company", "") or ""),
                    "url": url,
                    "source": str(job_dict.get("site", "")),
                    "location": str(job_dict.get("location", "") or ""),
                    "is_remote": bool(job_dict.get("is_remote", False)),
                    "salary": salary_str,
                    "description": str(job_dict.get("description", "") or ""),
                    "date_found": datetime.now().isoformat()[:10],
                })

                # Optionally also push straight to Notion
                if notion_push:
                    push_to_notion(notion, notion_cfg["database_id"], job_dict, fm)

                existing_urls.add(url)
                new_count += 1
                print(f"  + {job.get('title')} @ {job.get('company')}")

    print(f"\n[discover] Done — {new_count} new listings staged.")


if __name__ == "__main__":
    run_discovery()
```

**Step 4: Run tests — expect 4 passing**

```bash
conda run -n job-seeker pytest tests/test_discover.py -v
```

Expected: `4 passed`

**Step 5: Run full suite**

```bash
conda run -n job-seeker pytest tests/ -v
```

Expected: all tests pass.

**Step 6: Commit**

```bash
cd /devl/job-seeker
git add scripts/discover.py tests/test_discover.py
git commit -m "feat: route discover.py through SQLite staging layer"
```

---

## Task 3: `sync.py` — approved → Notion push

**Files:**
- Create: `scripts/sync.py`
- Create: `tests/test_sync.py`

**Step 1: Write failing tests**

```python
# tests/test_sync.py
import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path


SAMPLE_FM = {
    "title_field": "Salary", "job_title": "Job Title", "company": "Company Name",
    "url": "Role Link", "source": "Job Source", "status": "Status of Application",
    "status_new": "Application Submitted", "date_found": "Date Found",
    "remote": "Remote", "match_score": "Match Score",
    "keyword_gaps": "Keyword Gaps", "notes": "Notes", "job_description": "Job Description",
}

SAMPLE_NOTION_CFG = {"token": "secret_test", "database_id": "fake-db-id", "field_map": SAMPLE_FM}

SAMPLE_JOB = {
    "id": 1, "title": "CSM", "company": "Acme", "url": "https://example.com/1",
    "source": "linkedin", "location": "Remote", "is_remote": 1,
    "salary": "$100k", "description": "Good role", "match_score": 80.0,
    "keyword_gaps": "Gainsight, Churnzero", "date_found": "2026-02-20",
    "status": "approved", "notion_page_id": None,
}


def test_sync_pushes_approved_jobs(tmp_path):
    """sync_to_notion pushes approved jobs and marks them synced."""
    from scripts.sync import sync_to_notion
    from scripts.db import init_db, insert_job, get_jobs_by_status, update_job_status

    db_path = tmp_path / "test.db"
    init_db(db_path)
    row_id = insert_job(db_path, {
        "title": "CSM", "company": "Acme", "url": "https://example.com/1",
        "source": "linkedin", "location": "Remote", "is_remote": True,
        "salary": "$100k", "description": "Good role", "date_found": "2026-02-20",
    })
    update_job_status(db_path, [row_id], "approved")

    mock_notion = MagicMock()
    mock_notion.pages.create.return_value = {"id": "notion-page-abc"}

    with patch("scripts.sync.load_notion_config", return_value=SAMPLE_NOTION_CFG), \
         patch("scripts.sync.Client", return_value=mock_notion):
        count = sync_to_notion(db_path=db_path)

    assert count == 1
    mock_notion.pages.create.assert_called_once()
    synced = get_jobs_by_status(db_path, "synced")
    assert len(synced) == 1


def test_sync_returns_zero_when_nothing_approved(tmp_path):
    """sync_to_notion returns 0 when there are no approved jobs."""
    from scripts.sync import sync_to_notion
    from scripts.db import init_db

    db_path = tmp_path / "test.db"
    init_db(db_path)

    with patch("scripts.sync.load_notion_config", return_value=SAMPLE_NOTION_CFG), \
         patch("scripts.sync.Client"):
        count = sync_to_notion(db_path=db_path)

    assert count == 0
```

**Step 2: Run tests — expect ImportError**

```bash
conda run -n job-seeker pytest tests/test_sync.py -v
```

Expected: `ModuleNotFoundError: No module named 'scripts.sync'`

**Step 3: Write `scripts/sync.py`**

```python
# scripts/sync.py
"""
Push approved jobs from SQLite staging to Notion.

Usage:
    conda run -n job-seeker python scripts/sync.py
"""
import yaml
from pathlib import Path
from datetime import datetime

from notion_client import Client

from scripts.db import DEFAULT_DB, get_jobs_by_status, update_job_status

CONFIG_DIR = Path(__file__).parent.parent / "config"


def load_notion_config() -> dict:
    return yaml.safe_load((CONFIG_DIR / "notion.yaml").read_text())


def sync_to_notion(db_path: Path = DEFAULT_DB) -> int:
    """Push all approved jobs to Notion. Returns count synced."""
    cfg = load_notion_config()
    notion = Client(auth=cfg["token"])
    db_id = cfg["database_id"]
    fm = cfg["field_map"]

    approved = get_jobs_by_status(db_path, "approved")
    if not approved:
        print("[sync] No approved jobs to sync.")
        return 0

    synced_ids = []
    for job in approved:
        try:
            page = notion.pages.create(
                parent={"database_id": db_id},
                properties={
                    fm["title_field"]: {"title": [{"text": {"content": job.get("salary") or job.get("title", "")}}]},
                    fm["job_title"]:   {"rich_text": [{"text": {"content": job.get("title", "")}}]},
                    fm["company"]:     {"rich_text": [{"text": {"content": job.get("company", "")}}]},
                    fm["url"]:         {"url": job.get("url") or None},
                    fm["source"]:      {"multi_select": [{"name": job.get("source", "unknown").title()}]},
                    fm["status"]:      {"select": {"name": fm["status_new"]}},
                    fm["remote"]:      {"checkbox": bool(job.get("is_remote", 0))},
                    fm["date_found"]:  {"date": {"start": job.get("date_found", datetime.now().isoformat()[:10])}},
                    fm["match_score"]: {"number": job.get("match_score")},
                    fm["keyword_gaps"]: {"rich_text": [{"text": {"content": job.get("keyword_gaps") or ""}}]},
                },
            )
            synced_ids.append(job["id"])
            print(f"[sync] + {job.get('title')} @ {job.get('company')}")
        except Exception as e:
            print(f"[sync] Error syncing {job.get('url')}: {e}")

    update_job_status(db_path, synced_ids, "synced")
    print(f"[sync] Done — {len(synced_ids)} jobs synced to Notion.")
    return len(synced_ids)


if __name__ == "__main__":
    sync_to_notion()
```

**Step 4: Run tests — expect 2 passing**

```bash
conda run -n job-seeker pytest tests/test_sync.py -v
```

Expected: `2 passed`

**Step 5: Full suite**

```bash
conda run -n job-seeker pytest tests/ -v
```

Expected: all pass.

**Step 6: Commit**

```bash
cd /devl/job-seeker
git add scripts/sync.py tests/test_sync.py
git commit -m "feat: add sync.py to push approved jobs from SQLite to Notion"
```

---

## Task 4: Streamlit theme + app scaffold

**Files:**
- Create: `app/.streamlit/config.toml`
- Create: `app/Home.py`
- Create: `app/pages/1_Job_Review.py` (stub)
- Create: `app/pages/2_Settings.py` (stub)
- Create: `app/pages/3_Resume_Editor.py` (stub)

No tests for Streamlit page rendering — test helper functions instead.

**Step 1: Create theme**

```toml
# app/.streamlit/config.toml
[theme]
base = "dark"
primaryColor = "#2DD4BF"          # teal
backgroundColor = "#0F172A"       # slate-900
secondaryBackgroundColor = "#1E293B"  # slate-800
textColor = "#F1F5F9"             # slate-100
font = "sans serif"
```

**Step 2: Create `app/Home.py`**

```python
# app/Home.py
"""
Job Seeker Dashboard — Home page.
Shows counts, Run Discovery button, and Sync to Notion button.
"""
import subprocess
import sys
from pathlib import Path

import streamlit as st

# Make scripts importable
sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.db import DEFAULT_DB, init_db, get_job_counts

st.set_page_config(
    page_title="Meghan's Job Search",
    page_icon="🔍",
    layout="wide",
)

init_db(DEFAULT_DB)
counts = get_job_counts(DEFAULT_DB)

st.title("🔍 Meghan's Job Search")
st.caption("Discover → Review → Sync to Notion")

st.divider()

# Stat cards
col1, col2, col3, col4 = st.columns(4)
col1.metric("Pending Review", counts.get("pending", 0))
col2.metric("Approved", counts.get("approved", 0))
col3.metric("Synced to Notion", counts.get("synced", 0))
col4.metric("Rejected", counts.get("rejected", 0))

st.divider()

# Actions
left, right = st.columns(2)

with left:
    st.subheader("Find New Jobs")
    st.caption("Scrapes all configured boards and adds new listings to your review queue.")
    if st.button("🚀 Run Discovery", use_container_width=True, type="primary"):
        with st.spinner("Scraping job boards…"):
            result = subprocess.run(
                ["conda", "run", "-n", "job-seeker", "python", "scripts/discover.py"],
                capture_output=True, text=True,
                cwd=str(Path(__file__).parent.parent),
            )
        if result.returncode == 0:
            st.success("Discovery complete! Head to Job Review to see new listings.")
            st.code(result.stdout)
        else:
            st.error("Discovery failed.")
            st.code(result.stderr)

with right:
    approved_count = counts.get("approved", 0)
    st.subheader("Send to Notion")
    st.caption("Push all approved jobs to your Notion tracking database.")
    if approved_count == 0:
        st.info("No approved jobs yet. Review and approve some listings first.")
    else:
        if st.button(f"📤 Sync {approved_count} approved job{'s' if approved_count != 1 else ''} → Notion",
                     use_container_width=True, type="primary"):
            with st.spinner("Syncing to Notion…"):
                from scripts.sync import sync_to_notion
                count = sync_to_notion(DEFAULT_DB)
            st.success(f"Synced {count} job{'s' if count != 1 else ''} to Notion!")
            st.rerun()
```

**Step 3: Create page stubs**

```python
# app/pages/1_Job_Review.py
import streamlit as st
st.set_page_config(page_title="Job Review", page_icon="📋", layout="wide")
st.title("📋 Job Review")
st.info("Coming soon — Task 5")
```

```python
# app/pages/2_Settings.py
import streamlit as st
st.set_page_config(page_title="Settings", page_icon="⚙️", layout="wide")
st.title("⚙️ Settings")
st.info("Coming soon — Task 6")
```

```python
# app/pages/3_Resume_Editor.py
import streamlit as st
st.set_page_config(page_title="Resume Editor", page_icon="📝", layout="wide")
st.title("📝 Resume Editor")
st.info("Coming soon — Task 7")
```

**Step 4: Smoke test**

```bash
conda run -n job-seeker streamlit run /devl/job-seeker/app/Home.py --server.headless true &
sleep 4
curl -s http://localhost:8501 | grep -q "Meghan" && echo "OK" || echo "FAIL"
kill %1
```

Expected: `OK`

**Step 5: Commit**

```bash
cd /devl/job-seeker
git add app/
git commit -m "feat: add Streamlit app scaffold with dark theme and dashboard"
```

---

## Task 5: Job Review page

**Files:**
- Modify: `app/pages/1_Job_Review.py`

No separate unit tests — logic is inline Streamlit. Test manually after implement.

**Step 1: Replace stub with full implementation**

```python
# app/pages/1_Job_Review.py
"""
Job Review — browse pending listings, batch approve or reject.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import streamlit as st
from scripts.db import DEFAULT_DB, init_db, get_jobs_by_status, update_job_status

st.set_page_config(page_title="Job Review", page_icon="📋", layout="wide")
st.title("📋 Job Review")

init_db(DEFAULT_DB)

# Filters sidebar
with st.sidebar:
    st.header("Filters")
    show_status = st.selectbox("Show", ["pending", "approved", "rejected", "synced"], index=0)
    remote_only = st.checkbox("Remote only", value=False)
    min_score = st.slider("Min match score", 0, 100, 0)
    st.divider()
    st.caption("Use checkboxes to select jobs, then approve or reject in bulk.")

jobs = get_jobs_by_status(DEFAULT_DB, show_status)

# Apply filters
if remote_only:
    jobs = [j for j in jobs if j.get("is_remote")]
if min_score > 0:
    jobs = [j for j in jobs if (j.get("match_score") or 0) >= min_score]

if not jobs:
    st.info(f"No {show_status} jobs matching your filters.")
    st.stop()

st.caption(f"Showing {len(jobs)} {show_status} job{'s' if len(jobs) != 1 else ''}")

# Batch action buttons (only relevant for pending)
if show_status == "pending":
    col_a, col_b, col_c = st.columns([2, 2, 6])
    select_all = col_a.button("Select all", use_container_width=True)
    clear_all = col_b.button("Clear all", use_container_width=True)

    if "selected_ids" not in st.session_state:
        st.session_state.selected_ids = set()
    if select_all:
        st.session_state.selected_ids = {j["id"] for j in jobs}
    if clear_all:
        st.session_state.selected_ids = set()

    col_approve, col_reject, _ = st.columns([2, 2, 6])
    if col_approve.button("✅ Approve selected", use_container_width=True, type="primary",
                          disabled=not st.session_state.selected_ids):
        update_job_status(DEFAULT_DB, list(st.session_state.selected_ids), "approved")
        st.session_state.selected_ids = set()
        st.success("Approved!")
        st.rerun()
    if col_reject.button("❌ Reject selected", use_container_width=True,
                         disabled=not st.session_state.selected_ids):
        update_job_status(DEFAULT_DB, list(st.session_state.selected_ids), "rejected")
        st.session_state.selected_ids = set()
        st.success("Rejected.")
        st.rerun()

st.divider()

# Job cards
for job in jobs:
    score = job.get("match_score")
    if score is None:
        score_badge = "⬜ No score"
    elif score >= 70:
        score_badge = f"🟢 {score:.0f}%"
    elif score >= 40:
        score_badge = f"🟡 {score:.0f}%"
    else:
        score_badge = f"🔴 {score:.0f}%"

    remote_badge = "🌐 Remote" if job.get("is_remote") else "🏢 On-site"
    source_badge = job.get("source", "").title()

    with st.container(border=True):
        left, right = st.columns([8, 2])
        with left:
            checked = st.checkbox(
                f"**{job['title']}** — {job['company']}",
                key=f"chk_{job['id']}",
                value=job["id"] in st.session_state.get("selected_ids", set()),
            )
            if checked:
                st.session_state.setdefault("selected_ids", set()).add(job["id"])
            else:
                st.session_state.setdefault("selected_ids", set()).discard(job["id"])

            cols = st.columns(4)
            cols[0].caption(remote_badge)
            cols[1].caption(f"📌 {source_badge}")
            cols[2].caption(score_badge)
            cols[3].caption(f"📅 {job.get('date_found', '')}")

            if job.get("keyword_gaps"):
                st.caption(f"**Keyword gaps:** {job['keyword_gaps']}")

        with right:
            if job.get("url"):
                st.link_button("View listing →", job["url"], use_container_width=True)
            if job.get("salary"):
                st.caption(f"💰 {job['salary']}")
```

**Step 2: Manual smoke test**

```bash
conda run -n job-seeker streamlit run /devl/job-seeker/app/Home.py
```

Open http://localhost:8501, navigate to Job Review. Confirm filters and empty state work.

**Step 3: Commit**

```bash
cd /devl/job-seeker
git add app/pages/1_Job_Review.py
git commit -m "feat: add Job Review page with batch approve/reject"
```

---

## Task 6: Settings page

**Files:**
- Modify: `app/pages/2_Settings.py`

**Step 1: Replace stub**

```python
# app/pages/2_Settings.py
"""
Settings — edit search profiles, LLM backends, and Notion connection.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import streamlit as st
import yaml

st.set_page_config(page_title="Settings", page_icon="⚙️", layout="wide")
st.title("⚙️ Settings")

CONFIG_DIR = Path(__file__).parent.parent.parent / "config"
SEARCH_CFG = CONFIG_DIR / "search_profiles.yaml"
LLM_CFG = CONFIG_DIR / "llm.yaml"
NOTION_CFG = CONFIG_DIR / "notion.yaml"


def load_yaml(path: Path) -> dict:
    if path.exists():
        return yaml.safe_load(path.read_text()) or {}
    return {}


def save_yaml(path: Path, data: dict) -> None:
    path.write_text(yaml.dump(data, default_flow_style=False, allow_unicode=True))


tab_search, tab_llm, tab_notion = st.tabs(["🔎 Search", "🤖 LLM Backends", "📚 Notion"])

# ── Search tab ──────────────────────────────────────────────────────────────
with tab_search:
    cfg = load_yaml(SEARCH_CFG)
    profiles = cfg.get("profiles", [{}])
    p = profiles[0]  # edit first profile for now

    st.subheader("Job Titles to Search")
    titles_text = st.text_area(
        "One title per line",
        value="\n".join(p.get("titles", [])),
        height=150,
        help="JobSpy will search for any of these titles across all configured boards.",
    )

    st.subheader("Locations")
    locations_text = st.text_area(
        "One location per line",
        value="\n".join(p.get("locations", [])),
        height=100,
    )

    st.subheader("Job Boards")
    board_options = ["linkedin", "indeed", "glassdoor", "zip_recruiter"]
    selected_boards = st.multiselect(
        "Active boards", board_options,
        default=p.get("boards", board_options),
    )

    col1, col2 = st.columns(2)
    results_per = col1.slider("Results per board", 5, 100, p.get("results_per_board", 25))
    hours_old = col2.slider("How far back to look (hours)", 24, 720, p.get("hours_old", 72))

    if st.button("💾 Save search settings", type="primary"):
        profiles[0] = {
            **p,
            "titles": [t.strip() for t in titles_text.splitlines() if t.strip()],
            "locations": [l.strip() for l in locations_text.splitlines() if l.strip()],
            "boards": selected_boards,
            "results_per_board": results_per,
            "hours_old": hours_old,
        }
        save_yaml(SEARCH_CFG, {"profiles": profiles})
        st.success("Search settings saved!")

# ── LLM Backends tab ────────────────────────────────────────────────────────
with tab_llm:
    cfg = load_yaml(LLM_CFG)
    backends = cfg.get("backends", {})
    fallback_order = cfg.get("fallback_order", list(backends.keys()))

    st.subheader("Fallback Order")
    st.caption("Backends are tried top-to-bottom. First reachable one wins.")
    st.write(" → ".join(fallback_order))

    st.subheader("Backend Configuration")
    updated_backends = {}
    for name in fallback_order:
        b = backends.get(name, {})
        with st.expander(f"**{name.replace('_', ' ').title()}**", expanded=False):
            if b.get("type") == "openai_compat":
                url = st.text_input("URL", value=b.get("base_url", ""), key=f"{name}_url")
                model = st.text_input("Model", value=b.get("model", ""), key=f"{name}_model")
                updated_backends[name] = {**b, "base_url": url, "model": model}
            elif b.get("type") == "anthropic":
                model = st.text_input("Model", value=b.get("model", ""), key=f"{name}_model")
                updated_backends[name] = {**b, "model": model}
            else:
                updated_backends[name] = b

            if st.button(f"Test {name}", key=f"test_{name}"):
                with st.spinner("Testing…"):
                    try:
                        import sys
                        sys.path.insert(0, str(Path(__file__).parent.parent.parent))
                        from scripts.llm_router import LLMRouter
                        r = LLMRouter()
                        reachable = r._is_reachable(b.get("base_url", ""))
                        st.success("Reachable ✓") if reachable else st.warning("Not reachable")
                    except Exception as e:
                        st.error(f"Error: {e}")

    if st.button("💾 Save LLM settings", type="primary"):
        save_yaml(LLM_CFG, {**cfg, "backends": updated_backends})
        st.success("LLM settings saved!")

# ── Notion tab ───────────────────────────────────────────────────────────────
with tab_notion:
    cfg = load_yaml(NOTION_CFG) if NOTION_CFG.exists() else {}

    st.subheader("Notion Connection")
    token = st.text_input(
        "Integration Token",
        value=cfg.get("token", ""),
        type="password",
        help="Find this at notion.so/my-integrations → your integration → Internal Integration Token",
    )
    db_id = st.text_input(
        "Database ID",
        value=cfg.get("database_id", ""),
        help="The 32-character ID from your Notion database URL",
    )

    col_save, col_test = st.columns(2)
    if col_save.button("💾 Save Notion settings", type="primary"):
        save_yaml(NOTION_CFG, {**cfg, "token": token, "database_id": db_id})
        st.success("Notion settings saved!")

    if col_test.button("🔌 Test connection"):
        with st.spinner("Connecting…"):
            try:
                from notion_client import Client
                n = Client(auth=token)
                db = n.databases.retrieve(db_id)
                st.success(f"Connected to: **{db['title'][0]['plain_text']}**")
            except Exception as e:
                st.error(f"Connection failed: {e}")
```

**Step 2: Manual smoke test**

Navigate to Settings in the running Streamlit app. Confirm all three tabs render, save/load works.

**Step 3: Commit**

```bash
cd /devl/job-seeker
git add app/pages/2_Settings.py
git commit -m "feat: add Settings page with search, LLM, and Notion tabs"
```

---

## Task 7: Resume Editor page

**Files:**
- Modify: `app/pages/3_Resume_Editor.py`

**Step 1: Replace stub**

```python
# app/pages/3_Resume_Editor.py
"""
Resume Editor — form-based editor for Meghan's AIHawk profile YAML.
FILL_IN fields highlighted in amber.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import streamlit as st
import yaml

st.set_page_config(page_title="Resume Editor", page_icon="📝", layout="wide")
st.title("📝 Resume Editor")
st.caption("Edit Meghan's application profile used by AIHawk for LinkedIn Easy Apply.")

RESUME_PATH = Path(__file__).parent.parent.parent / "aihawk" / "data_folder" / "plain_text_resume.yaml"

if not RESUME_PATH.exists():
    st.error(f"Resume file not found at `{RESUME_PATH}`. Is AIHawk cloned?")
    st.stop()

data = yaml.safe_load(RESUME_PATH.read_text()) or {}


def field(label: str, value: str, key: str, help: str = "", password: bool = False) -> str:
    """Render a text input, highlighted amber if value is FILL_IN."""
    needs_attention = str(value).startswith("FILL_IN") or value == ""
    if needs_attention:
        st.markdown(
            f'<p style="color:#F59E0B;font-size:0.8em;margin-bottom:2px">⚠️ Needs your attention</p>',
            unsafe_allow_html=True,
        )
    return st.text_input(label, value=value or "", key=key, help=help,
                         type="password" if password else "default")


st.divider()

# ── Personal Info ──────────────────────────────────────────────────────────
with st.expander("👤 Personal Information", expanded=True):
    info = data.get("personal_information", {})
    col1, col2 = st.columns(2)
    with col1:
        name = field("First Name", info.get("name", ""), "pi_name")
        email = field("Email", info.get("email", ""), "pi_email")
        phone = field("Phone", info.get("phone", ""), "pi_phone")
        city = field("City", info.get("city", ""), "pi_city")
    with col2:
        surname = field("Last Name", info.get("surname", ""), "pi_surname")
        linkedin = field("LinkedIn URL", info.get("linkedin", ""), "pi_linkedin")
        zip_code = field("Zip Code", info.get("zip_code", ""), "pi_zip")
        dob = field("Date of Birth", info.get("date_of_birth", ""), "pi_dob",
                    help="Format: MM/DD/YYYY")

# ── Education ─────────────────────────────────────────────────────────────
with st.expander("🎓 Education"):
    edu_list = data.get("education_details", [{}])
    updated_edu = []
    for i, edu in enumerate(edu_list):
        st.markdown(f"**Entry {i+1}**")
        col1, col2 = st.columns(2)
        with col1:
            inst = field("Institution", edu.get("institution", ""), f"edu_inst_{i}")
            field_study = st.text_input("Field of Study", edu.get("field_of_study", ""), key=f"edu_field_{i}")
            start = st.text_input("Start Year", edu.get("start_date", ""), key=f"edu_start_{i}")
        with col2:
            level = st.selectbox("Degree Level",
                ["Bachelor's Degree", "Master's Degree", "Some College", "Associate's Degree", "High School", "Other"],
                index=["Bachelor's Degree", "Master's Degree", "Some College", "Associate's Degree", "High School", "Other"].index(
                    edu.get("education_level", "Some College")
                ) if edu.get("education_level") in ["Bachelor's Degree", "Master's Degree", "Some College", "Associate's Degree", "High School", "Other"] else 2,
                key=f"edu_level_{i}")
            end = st.text_input("Completion Year", edu.get("year_of_completion", ""), key=f"edu_end_{i}")
        updated_edu.append({
            "education_level": level, "institution": inst, "field_of_study": field_study,
            "start_date": start, "year_of_completion": end, "final_evaluation_grade": "", "exam": {},
        })
        st.divider()

# ── Experience ─────────────────────────────────────────────────────────────
with st.expander("💼 Work Experience"):
    exp_list = data.get("experience_details", [{}])
    if "exp_count" not in st.session_state:
        st.session_state.exp_count = len(exp_list)
    if st.button("+ Add Experience Entry"):
        st.session_state.exp_count += 1
        exp_list.append({})

    updated_exp = []
    for i in range(st.session_state.exp_count):
        exp = exp_list[i] if i < len(exp_list) else {}
        st.markdown(f"**Position {i+1}**")
        col1, col2 = st.columns(2)
        with col1:
            pos = field("Job Title", exp.get("position", ""), f"exp_pos_{i}")
            company = field("Company", exp.get("company", ""), f"exp_co_{i}")
            period = field("Employment Period", exp.get("employment_period", ""), f"exp_period_{i}",
                           help="e.g. 01/2022 - Present")
        with col2:
            location = st.text_input("Location", exp.get("location", ""), key=f"exp_loc_{i}")
            industry = st.text_input("Industry", exp.get("industry", ""), key=f"exp_ind_{i}")

        responsibilities = st.text_area(
            "Key Responsibilities (one per line)",
            value="\n".join(
                r.get(f"responsibility_{j+1}", "") if isinstance(r, dict) else str(r)
                for j, r in enumerate(exp.get("key_responsibilities", []))
            ),
            key=f"exp_resp_{i}", height=100,
        )
        skills = st.text_input(
            "Skills (comma-separated)",
            value=", ".join(exp.get("skills_acquired", [])),
            key=f"exp_skills_{i}",
        )
        resp_list = [{"responsibility_1": r.strip()} for r in responsibilities.splitlines() if r.strip()]
        skill_list = [s.strip() for s in skills.split(",") if s.strip()]
        updated_exp.append({
            "position": pos, "company": company, "employment_period": period,
            "location": location, "industry": industry,
            "key_responsibilities": resp_list, "skills_acquired": skill_list,
        })
        st.divider()

# ── Preferences ────────────────────────────────────────────────────────────
with st.expander("⚙️ Preferences & Availability"):
    wp = data.get("work_preferences", {})
    sal = data.get("salary_expectations", {})
    avail = data.get("availability", {})
    col1, col2 = st.columns(2)
    with col1:
        salary_range = st.text_input("Salary Range (USD)", sal.get("salary_range_usd", ""), key="pref_salary",
                                     help="e.g. 120000 - 180000")
        notice = st.text_input("Notice Period", avail.get("notice_period", "2 weeks"), key="pref_notice")
    with col2:
        remote_work = st.checkbox("Open to Remote", value=wp.get("remote_work", "Yes") == "Yes", key="pref_remote")
        relocation = st.checkbox("Open to Relocation", value=wp.get("open_to_relocation", "No") == "Yes", key="pref_reloc")
        assessments = st.checkbox("Willing to complete assessments",
                                  value=wp.get("willing_to_complete_assessments", "Yes") == "Yes", key="pref_assess")
        bg_checks = st.checkbox("Willing to undergo background checks",
                                value=wp.get("willing_to_undergo_background_checks", "Yes") == "Yes", key="pref_bg")

# ── Self-ID ────────────────────────────────────────────────────────────────
with st.expander("🏳️‍🌈 Self-Identification (optional)"):
    sid = data.get("self_identification", {})
    col1, col2 = st.columns(2)
    with col1:
        gender = st.text_input("Gender identity", sid.get("gender", "Non-binary"), key="sid_gender",
                               help="Select 'Non-binary' or 'Prefer not to say' when options allow")
        pronouns = st.text_input("Pronouns", sid.get("pronouns", "Any"), key="sid_pronouns")
        ethnicity = field("Ethnicity", sid.get("ethnicity", ""), "sid_ethnicity",
                          help="'Prefer not to say' is always an option")
    with col2:
        veteran = st.selectbox("Veteran status", ["No", "Yes", "Prefer not to say"],
                               index=["No", "Yes", "Prefer not to say"].index(sid.get("veteran", "No")), key="sid_vet")
        disability = st.selectbox("Disability disclosure", ["Prefer not to say", "No", "Yes"],
                                  index=["Prefer not to say", "No", "Yes"].index(
                                      sid.get("disability", "Prefer not to say")), key="sid_dis")
    st.caption("⚠️ Drug testing: set to No (medicinal cannabis for EDS). AIHawk will skip employers who require drug tests.")

st.divider()

# ── Save ───────────────────────────────────────────────────────────────────
if st.button("💾 Save Resume Profile", type="primary", use_container_width=True):
    data["personal_information"] = {
        **data.get("personal_information", {}),
        "name": name, "surname": surname, "email": email, "phone": phone,
        "city": city, "zip_code": zip_code, "linkedin": linkedin, "date_of_birth": dob,
    }
    data["education_details"] = updated_edu
    data["experience_details"] = updated_exp
    data["salary_expectations"] = {"salary_range_usd": salary_range}
    data["availability"] = {"notice_period": notice}
    data["work_preferences"] = {
        **data.get("work_preferences", {}),
        "remote_work": "Yes" if remote_work else "No",
        "open_to_relocation": "Yes" if relocation else "No",
        "willing_to_complete_assessments": "Yes" if assessments else "No",
        "willing_to_undergo_background_checks": "Yes" if bg_checks else "No",
        "willing_to_undergo_drug_tests": "No",
    }
    data["self_identification"] = {
        "gender": gender, "pronouns": pronouns, "veteran": veteran,
        "disability": disability, "ethnicity": ethnicity,
    }
    RESUME_PATH.write_text(yaml.dump(data, default_flow_style=False, allow_unicode=True))
    st.success("✅ Profile saved!")
    st.balloons()
```

**Step 2: Smoke test**

Navigate to Resume Editor in the Streamlit app. Confirm all sections render and `FILL_IN` fields show amber warnings.

**Step 3: Commit**

```bash
cd /devl/job-seeker
git add app/pages/3_Resume_Editor.py
git commit -m "feat: add Resume Editor page with form-based AIHawk YAML editor"
```

---

## Task 8: Wire up environment.yml and CLAUDE.md

**Step 1: Export updated environment.yml**

```bash
conda run -n job-seeker conda env export > /devl/job-seeker/environment.yml
```

**Step 2: Update CLAUDE.md with UI section**

Add to `CLAUDE.md`:

```markdown
## Web UI
- Run: `conda run -n job-seeker streamlit run app/Home.py`
- Opens at http://localhost:8501
- staging.db is gitignored — SQLite staging layer between discovery and Notion
- Pages: Home (dashboard), Job Review, Settings, Resume Editor
```

**Step 3: Commit**

```bash
cd /devl/job-seeker
git add environment.yml CLAUDE.md
git commit -m "chore: update environment.yml and CLAUDE.md for Streamlit UI"
```

---

## Quick Reference

| Command | What it does |
|---|---|
| `conda run -n job-seeker streamlit run app/Home.py` | Launch the web UI at localhost:8501 |
| `conda run -n job-seeker python scripts/discover.py` | Scrape boards → SQLite staging |
| `conda run -n job-seeker python scripts/sync.py` | Push approved jobs → Notion |
| `conda run -n job-seeker pytest tests/ -v` | Run all tests |
