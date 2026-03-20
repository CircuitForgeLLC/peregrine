# Digest Scrape Queue Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a persistent digest queue so users can click the 📰 Digest chip on a signal banner, browse extracted job links from queued digest emails, and send selected URLs through the existing discovery pipeline as pending jobs.

**Architecture:** New `digest_queue` table in `staging.db` stores queued digest emails (foreign-keyed to `job_contacts`). Four new FastAPI endpoints in `dev-api.py` handle list/add/extract/queue-jobs/delete. A new Pinia store + `DigestView.vue` page provide the browse UI. The existing reclassify chip handler gets a third fire-and-forget API call for digest entries.

**Tech Stack:** Python / FastAPI / SQLite / Vue 3 / TypeScript / Pinia / Heroicons Vue

---

## File Map

| File | What changes |
|---|---|
| `scripts/db.py` | Add `CREATE_DIGEST_QUEUE` string; call it in `init_db()` |
| `dev-api.py` | `@app.on_event("startup")` for digest table; `_score_url()` + `extract_links()` helpers; 4 new endpoints; `DigestQueueBody` + `QueueJobsBody` Pydantic models |
| `tests/test_dev_api_digest.py` | New file — 11 tests with isolated tmp_db fixture |
| `web/src/stores/digest.ts` | New Pinia store — `DigestEntry`, `DigestLink` types; `fetchAll()`, `remove()` actions |
| `web/src/views/DigestView.vue` | New page — entry list, expand/extract/select/queue UI |
| `web/src/router/index.ts` | Add `/digest` route |
| `web/src/components/AppNav.vue` | Add `NewspaperIcon` import; add Digest nav item; import digest store; reactive badge in template |
| `web/src/components/InterviewCard.vue` | Third fire-and-forget call in `reclassifySignal` digest branch |
| `web/src/views/InterviewsView.vue` | Third fire-and-forget call in `reclassifyPreSignal` digest branch |

---

## Task 1: DB schema — `digest_queue` table

**Files:**
- Modify: `scripts/db.py:138,188-197`
- Modify: `dev-api.py` (add startup event after `_strip_html` definition)

- [ ] **Step 1: Add `CREATE_DIGEST_QUEUE` string to `scripts/db.py`**

After the `CREATE_SURVEY_RESPONSES` string (around line 138), insert:

```python
CREATE_DIGEST_QUEUE = """
CREATE TABLE IF NOT EXISTS digest_queue (
  id             INTEGER PRIMARY KEY,
  job_contact_id INTEGER NOT NULL REFERENCES job_contacts(id),
  created_at     TEXT DEFAULT (datetime('now')),
  UNIQUE(job_contact_id)
)
"""
```

- [ ] **Step 2: Call it in `init_db()`**

In `init_db()` (around line 195), add after the existing `CREATE_SURVEY_RESPONSES` call:

```python
    conn.execute(CREATE_DIGEST_QUEUE)
```

The full `init_db` body should now be:
```python
def init_db(db_path: Path = DEFAULT_DB) -> None:
    """Create tables if they don't exist, then run migrations."""
    conn = sqlite3.connect(db_path)
    conn.execute(CREATE_JOBS)
    conn.execute(CREATE_JOB_CONTACTS)
    conn.execute(CREATE_COMPANY_RESEARCH)
    conn.execute(CREATE_BACKGROUND_TASKS)
    conn.execute(CREATE_SURVEY_RESPONSES)
    conn.execute(CREATE_DIGEST_QUEUE)
    conn.commit()
    conn.close()
    _migrate_db(db_path)
```

- [ ] **Step 3: Add startup event to `dev-api.py`**

After the `_strip_html` function definition, add:

```python
@app.on_event("startup")
def _startup():
    """Ensure digest_queue table exists (dev-api may run against an existing DB)."""
    db = _get_db()
    db.execute("""
        CREATE TABLE IF NOT EXISTS digest_queue (
          id             INTEGER PRIMARY KEY,
          job_contact_id INTEGER NOT NULL REFERENCES job_contacts(id),
          created_at     TEXT DEFAULT (datetime('now')),
          UNIQUE(job_contact_id)
        )
    """)
    db.commit()
    db.close()
```

- [ ] **Step 4: Verify schema creation**

```bash
cd /Library/Development/CircuitForge/peregrine/.worktrees/feature-vue-spa
conda run -n job-seeker python -c "
from scripts.db import init_db
import tempfile, os
with tempfile.TemporaryDirectory() as d:
    p = os.path.join(d, 'staging.db')
    init_db(p)
    import sqlite3
    con = sqlite3.connect(p)
    tables = con.execute(\"SELECT name FROM sqlite_master WHERE type='table'\").fetchall()
    print([t[0] for t in tables])
"
```

Expected: list includes `digest_queue`

- [ ] **Step 5: Commit**

```bash
git add scripts/db.py dev-api.py
git commit -m "feat: add digest_queue table to schema and dev-api startup"
```

---

## Task 2: `GET` + `POST /api/digest-queue` endpoints + tests

**Files:**
- Create: `tests/test_dev_api_digest.py`
- Modify: `dev-api.py` (append after reclassify endpoint)

- [ ] **Step 1: Create test file with fixture + GET + POST tests**

Create `/Library/Development/CircuitForge/peregrine/.worktrees/feature-vue-spa/tests/test_dev_api_digest.py`:

```python
"""Tests for digest queue API endpoints."""
import sqlite3
import os
import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def tmp_db(tmp_path):
    """Create minimal schema in a temp dir with one job_contacts row."""
    db_path = str(tmp_path / "staging.db")
    con = sqlite3.connect(db_path)
    con.executescript("""
        CREATE TABLE jobs (
            id INTEGER PRIMARY KEY,
            title TEXT, company TEXT, url TEXT UNIQUE, location TEXT,
            is_remote INTEGER DEFAULT 0, salary TEXT,
            match_score REAL, keyword_gaps TEXT, status TEXT DEFAULT 'pending',
            date_found TEXT, description TEXT, source TEXT
        );
        CREATE TABLE job_contacts (
            id INTEGER PRIMARY KEY,
            job_id INTEGER,
            subject TEXT,
            received_at TEXT,
            stage_signal TEXT,
            suggestion_dismissed INTEGER DEFAULT 0,
            body TEXT,
            from_addr TEXT
        );
        CREATE TABLE digest_queue (
            id INTEGER PRIMARY KEY,
            job_contact_id INTEGER NOT NULL REFERENCES job_contacts(id),
            created_at TEXT DEFAULT (datetime('now')),
            UNIQUE(job_contact_id)
        );
        INSERT INTO jobs (id, title, company, url, status, source, date_found)
            VALUES (1, 'Engineer', 'Acme', 'https://acme.com/job/1', 'applied', 'test', '2026-03-19');
        INSERT INTO job_contacts (id, job_id, subject, received_at, stage_signal, body, from_addr)
            VALUES (
                10, 1, 'TechCrunch Jobs Weekly', '2026-03-19T10:00:00', 'digest',
                '<html><body>Apply at <a href="https://greenhouse.io/acme/jobs/456">Senior Engineer</a> or <a href="https://lever.co/globex/staff">Staff Designer</a>. Unsubscribe: https://unsubscribe.example.com/remove</body></html>',
                'digest@techcrunch.com'
            );
    """)
    con.close()
    return db_path


@pytest.fixture()
def client(tmp_db, monkeypatch):
    monkeypatch.setenv("STAGING_DB", tmp_db)
    import importlib
    import dev_api
    importlib.reload(dev_api)
    return TestClient(dev_api.app)


# ── GET /api/digest-queue ───────────────────────────────────────────────────

def test_digest_queue_list_empty(client):
    resp = client.get("/api/digest-queue")
    assert resp.status_code == 200
    assert resp.json() == []


def test_digest_queue_list_with_entry(client, tmp_db):
    con = sqlite3.connect(tmp_db)
    con.execute("INSERT INTO digest_queue (job_contact_id) VALUES (10)")
    con.commit()
    con.close()

    resp = client.get("/api/digest-queue")
    assert resp.status_code == 200
    entries = resp.json()
    assert len(entries) == 1
    assert entries[0]["job_contact_id"] == 10
    assert entries[0]["subject"] == "TechCrunch Jobs Weekly"
    assert entries[0]["from_addr"] == "digest@techcrunch.com"
    assert "body" in entries[0]
    assert "created_at" in entries[0]


# ── POST /api/digest-queue ──────────────────────────────────────────────────

def test_digest_queue_add(client, tmp_db):
    resp = client.post("/api/digest-queue", json={"job_contact_id": 10})
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["created"] is True

    con = sqlite3.connect(tmp_db)
    row = con.execute("SELECT * FROM digest_queue WHERE job_contact_id = 10").fetchone()
    con.close()
    assert row is not None


def test_digest_queue_add_duplicate(client):
    client.post("/api/digest-queue", json={"job_contact_id": 10})
    resp = client.post("/api/digest-queue", json={"job_contact_id": 10})
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["created"] is False


def test_digest_queue_add_missing_contact(client):
    resp = client.post("/api/digest-queue", json={"job_contact_id": 9999})
    assert resp.status_code == 404
```

- [ ] **Step 2: Run tests — expect failures**

```bash
cd /Library/Development/CircuitForge/peregrine/.worktrees/feature-vue-spa
/devl/miniconda3/envs/job-seeker/bin/pytest tests/test_dev_api_digest.py -v 2>&1 | tail -20
```

Expected: 4 FAILED, 1 PASSED. `test_digest_queue_add_missing_contact` passes immediately because a POST to a non-existent endpoint returns 404, matching the assertion — this is expected and fine.

- [ ] **Step 3: Implement `GET /api/digest-queue` + `POST /api/digest-queue` in `dev-api.py`**

After the reclassify endpoint (after line ~428), add:

```python
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
    exists = db.execute(
        "SELECT 1 FROM job_contacts WHERE id = ?", (body.job_contact_id,)
    ).fetchone()
    if not exists:
        db.close()
        raise HTTPException(404, "job_contact_id not found")
    result = db.execute(
        "INSERT OR IGNORE INTO digest_queue (job_contact_id) VALUES (?)",
        (body.job_contact_id,),
    )
    db.commit()
    created = result.rowcount > 0
    db.close()
    return {"ok": True, "created": created}
```

- [ ] **Step 4: Run tests — expect all pass**

```bash
/devl/miniconda3/envs/job-seeker/bin/pytest tests/test_dev_api_digest.py -v 2>&1 | tail -15
```

Expected: 5 PASSED

- [ ] **Step 5: Run full suite to catch regressions**

```bash
/devl/miniconda3/envs/job-seeker/bin/pytest tests/ -v 2>&1 | tail -5
```

Expected: all previously passing tests still pass

- [ ] **Step 6: Commit**

```bash
git add dev-api.py tests/test_dev_api_digest.py
git commit -m "feat: add GET/POST /api/digest-queue endpoints"
```

---

## Task 3: `POST /api/digest-queue/{id}/extract-links` + tests

**Files:**
- Modify: `tests/test_dev_api_digest.py` (append tests)
- Modify: `dev-api.py` (append helpers + endpoint)

- [ ] **Step 1: Add extract-links tests to `test_dev_api_digest.py`**

Append to `tests/test_dev_api_digest.py`:

```python
# ── POST /api/digest-queue/{id}/extract-links ───────────────────────────────

def _add_digest_entry(tmp_db, contact_id=10):
    """Helper: insert a digest_queue row and return its id."""
    con = sqlite3.connect(tmp_db)
    cur = con.execute("INSERT INTO digest_queue (job_contact_id) VALUES (?)", (contact_id,))
    entry_id = cur.lastrowid
    con.commit()
    con.close()
    return entry_id


def test_digest_extract_links(client, tmp_db):
    entry_id = _add_digest_entry(tmp_db)
    resp = client.post(f"/api/digest-queue/{entry_id}/extract-links")
    assert resp.status_code == 200
    links = resp.json()["links"]
    urls = [l["url"] for l in links]

    # greenhouse.io link should be present with score=2
    gh_links = [l for l in links if "greenhouse.io" in l["url"]]
    assert len(gh_links) == 1
    assert gh_links[0]["score"] == 2

    # lever.co link should be present with score=2
    lever_links = [l for l in links if "lever.co" in l["url"]]
    assert len(lever_links) == 1
    assert lever_links[0]["score"] == 2


def test_digest_extract_links_filters_trackers(client, tmp_db):
    entry_id = _add_digest_entry(tmp_db)
    resp = client.post(f"/api/digest-queue/{entry_id}/extract-links")
    assert resp.status_code == 200
    links = resp.json()["links"]
    urls = [l["url"] for l in links]
    # Unsubscribe URL should be excluded
    assert not any("unsubscribe" in u for u in urls)


def test_digest_extract_links_404(client):
    resp = client.post("/api/digest-queue/9999/extract-links")
    assert resp.status_code == 404
```

- [ ] **Step 2: Run new tests — expect failures**

```bash
/devl/miniconda3/envs/job-seeker/bin/pytest tests/test_dev_api_digest.py::test_digest_extract_links tests/test_dev_api_digest.py::test_digest_extract_links_filters_trackers tests/test_dev_api_digest.py::test_digest_extract_links_404 -v 2>&1 | tail -10
```

Expected: 3 FAILED

- [ ] **Step 3: Add `_score_url()` and `extract_links()` to `dev-api.py`**

First, add `urlparse` to the import block at the **top of `dev-api.py`** (around line 10, with the other stdlib imports):

```python
from urllib.parse import urlparse
```

Then, after the `_startup` event function (before the endpoint definitions), add the helpers:

```python
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
        if domain in hostname or domain in path:
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
```

- [ ] **Step 4: Add `POST /api/digest-queue/{id}/extract-links` endpoint**

After `add_to_digest_queue`, add:

```python
# ── POST /api/digest-queue/{id}/extract-links ─────────────────────────────

@app.post("/api/digest-queue/{digest_id}/extract-links")
def extract_digest_links(digest_id: int):
    db = _get_db()
    row = db.execute(
        """SELECT jc.body
           FROM digest_queue dq
           JOIN job_contacts jc ON jc.id = dq.job_contact_id
           WHERE dq.id = ?""",
        (digest_id,),
    ).fetchone()
    db.close()
    if not row:
        raise HTTPException(404, "Digest entry not found")
    return {"links": _extract_links(row["body"] or "")}
```

- [ ] **Step 5: Run tests — expect all pass**

```bash
/devl/miniconda3/envs/job-seeker/bin/pytest tests/test_dev_api_digest.py -v 2>&1 | tail -15
```

Expected: 8 PASSED

- [ ] **Step 6: Commit**

```bash
git add dev-api.py tests/test_dev_api_digest.py
git commit -m "feat: add /extract-links endpoint with URL scoring"
```

---

## Task 4: `POST /api/digest-queue/{id}/queue-jobs` + `DELETE /api/digest-queue/{id}` + tests

**Files:**
- Modify: `tests/test_dev_api_digest.py` (append tests)
- Modify: `dev-api.py` (append models + endpoints)

- [ ] **Step 1: Add queue-jobs and delete tests**

Append to `tests/test_dev_api_digest.py`:

```python
# ── POST /api/digest-queue/{id}/queue-jobs ──────────────────────────────────

def test_digest_queue_jobs(client, tmp_db):
    entry_id = _add_digest_entry(tmp_db)
    resp = client.post(
        f"/api/digest-queue/{entry_id}/queue-jobs",
        json={"urls": ["https://greenhouse.io/acme/jobs/456"]},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["queued"] == 1
    assert data["skipped"] == 0

    con = sqlite3.connect(tmp_db)
    row = con.execute(
        "SELECT source, status FROM jobs WHERE url = 'https://greenhouse.io/acme/jobs/456'"
    ).fetchone()
    con.close()
    assert row is not None
    assert row[0] == "digest"
    assert row[1] == "pending"


def test_digest_queue_jobs_skips_duplicates(client, tmp_db):
    entry_id = _add_digest_entry(tmp_db)
    resp = client.post(
        f"/api/digest-queue/{entry_id}/queue-jobs",
        json={"urls": [
            "https://greenhouse.io/acme/jobs/789",
            "https://greenhouse.io/acme/jobs/789",  # same URL twice in one call
        ]},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["queued"] == 1
    assert data["skipped"] == 1

    con = sqlite3.connect(tmp_db)
    count = con.execute(
        "SELECT COUNT(*) FROM jobs WHERE url = 'https://greenhouse.io/acme/jobs/789'"
    ).fetchone()[0]
    con.close()
    assert count == 1


def test_digest_queue_jobs_skips_invalid_urls(client, tmp_db):
    entry_id = _add_digest_entry(tmp_db)
    resp = client.post(
        f"/api/digest-queue/{entry_id}/queue-jobs",
        json={"urls": ["", "ftp://bad.example.com", "https://valid.greenhouse.io/job/1"]},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["queued"] == 1
    assert data["skipped"] == 2


def test_digest_queue_jobs_empty_urls(client, tmp_db):
    entry_id = _add_digest_entry(tmp_db)
    resp = client.post(f"/api/digest-queue/{entry_id}/queue-jobs", json={"urls": []})
    assert resp.status_code == 400


def test_digest_queue_jobs_404(client):
    resp = client.post("/api/digest-queue/9999/queue-jobs", json={"urls": ["https://example.com"]})
    assert resp.status_code == 404


# ── DELETE /api/digest-queue/{id} ───────────────────────────────────────────

def test_digest_delete(client, tmp_db):
    entry_id = _add_digest_entry(tmp_db)
    resp = client.delete(f"/api/digest-queue/{entry_id}")
    assert resp.status_code == 200
    assert resp.json()["ok"] is True

    # Second delete → 404
    resp2 = client.delete(f"/api/digest-queue/{entry_id}")
    assert resp2.status_code == 404
```

- [ ] **Step 2: Run new tests — expect failures**

```bash
/devl/miniconda3/envs/job-seeker/bin/pytest tests/test_dev_api_digest.py -k "queue_jobs or delete" -v 2>&1 | tail -15
```

Expected: 6 FAILED

- [ ] **Step 3: Add `QueueJobsBody` model + both endpoints to `dev-api.py`**

```python
class QueueJobsBody(BaseModel):
    urls: list[str]


# ── POST /api/digest-queue/{id}/queue-jobs ────────────────────────────────

@app.post("/api/digest-queue/{digest_id}/queue-jobs")
def queue_digest_jobs(digest_id: int, body: QueueJobsBody):
    if not body.urls:
        raise HTTPException(400, "urls must not be empty")
    db = _get_db()
    exists = db.execute(
        "SELECT 1 FROM digest_queue WHERE id = ?", (digest_id,)
    ).fetchone()
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
        result = insert_job(DB_PATH, {
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
    result = db.execute("DELETE FROM digest_queue WHERE id = ?", (digest_id,))
    db.commit()
    rowcount = result.rowcount
    db.close()
    if rowcount == 0:
        raise HTTPException(404, "Digest entry not found")
    return {"ok": True}
```

- [ ] **Step 4: Run full digest test suite — expect all pass**

```bash
/devl/miniconda3/envs/job-seeker/bin/pytest tests/test_dev_api_digest.py -v 2>&1 | tail -20
```

Expected: 14 PASSED

- [ ] **Step 5: Run full test suite**

```bash
/devl/miniconda3/envs/job-seeker/bin/pytest tests/ -v 2>&1 | tail -5
```

Expected: all previously passing tests still pass

- [ ] **Step 6: Commit**

```bash
git add dev-api.py tests/test_dev_api_digest.py
git commit -m "feat: add queue-jobs and delete digest endpoints"
```

---

## Task 5: Pinia store — `web/src/stores/digest.ts`

**Files:**
- Create: `web/src/stores/digest.ts`

- [ ] **Step 1: Create the store**

```typescript
import { defineStore } from 'pinia'
import { ref } from 'vue'
import { useApiFetch } from '@/composables/useApi'

export interface DigestEntry {
  id: number
  job_contact_id: number
  created_at: string
  subject: string
  from_addr: string | null
  received_at: string
  body: string | null
}

export interface DigestLink {
  url: string
  score: number   // 2 = job-likely, 1 = other
  hint: string
}

export const useDigestStore = defineStore('digest', () => {
  const entries = ref<DigestEntry[]>([])

  async function fetchAll() {
    const { data } = await useApiFetch<DigestEntry[]>('/api/digest-queue')
    if (data) entries.value = data
  }

  async function remove(id: number) {
    entries.value = entries.value.filter(e => e.id !== id)
    await useApiFetch(`/api/digest-queue/${id}`, { method: 'DELETE' })
  }

  return { entries, fetchAll, remove }
})
```

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd /Library/Development/CircuitForge/peregrine/.worktrees/feature-vue-spa/web
npm run type-check 2>&1 | tail -10
```

Expected: no errors

- [ ] **Step 3: Commit**

```bash
git add web/src/stores/digest.ts
git commit -m "feat: add digest Pinia store"
```

---

## Task 6: Digest chip third call — `InterviewCard.vue` + `InterviewsView.vue`

**Files:**
- Modify: `web/src/components/InterviewCard.vue:87-92`
- Modify: `web/src/views/InterviewsView.vue:105-110`

- [ ] **Step 1: Add third call in `InterviewCard.vue` digest branch**

Find the existing `await useApiFetch(…/dismiss…)` line in `reclassifySignal` (line 92). Insert the following 6 lines **immediately after** that line, inside the `if (DISMISS_LABELS.has(newLabel))` block:

```typescript
    // Digest-only: add to browsable queue (fire-and-forget; sig.id === job_contacts.id)
    if (newLabel === 'digest') {
      useApiFetch('/api/digest-queue', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ job_contact_id: sig.id }),
      }).catch(() => {})
    }
```

Do NOT modify the `else` branch or any other part of the function.

- [ ] **Step 2: Add same third call in `InterviewsView.vue` digest branch**

Find the existing `await useApiFetch(…/dismiss…)` line in `reclassifyPreSignal` (line 110). Insert the same 6 lines immediately after it:

```typescript
    // Digest-only: add to browsable queue (fire-and-forget; sig.id === job_contacts.id)
    if (newLabel === 'digest') {
      useApiFetch('/api/digest-queue', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ job_contact_id: sig.id }),
      }).catch(() => {})
    }
```

Do NOT modify anything else in the function.

- [ ] **Step 3: Type-check**

```bash
cd /Library/Development/CircuitForge/peregrine/.worktrees/feature-vue-spa/web
npm run type-check 2>&1 | tail -10
```

Expected: no new errors

- [ ] **Step 4: Commit**

```bash
git add web/src/components/InterviewCard.vue web/src/views/InterviewsView.vue
git commit -m "feat: fire digest-queue add call from digest chip handler"
```

---

## Task 7: Router + Nav — add `/digest` route and nav item

**Files:**
- Modify: `web/src/router/index.ts`
- Modify: `web/src/components/AppNav.vue`

- [ ] **Step 1: Add route to `index.ts`**

After the `/interviews` route, insert:

```typescript
{ path: '/digest', component: () => import('../views/DigestView.vue') },
```

The routes array should now include:
```typescript
{ path: '/interviews', component: () => import('../views/InterviewsView.vue') },
{ path: '/digest',     component: () => import('../views/DigestView.vue') },
{ path: '/prep',       component: () => import('../views/InterviewPrepView.vue') },
```

- [ ] **Step 2: Update `AppNav.vue` — add `NewspaperIcon` to imports**

Find the Heroicons import block (around line 74). Add `NewspaperIcon` to the import:

```typescript
import {
  HomeIcon,
  ClipboardDocumentListIcon,
  PencilSquareIcon,
  CalendarDaysIcon,
  LightBulbIcon,
  MagnifyingGlassIcon,
  NewspaperIcon,
  Cog6ToothIcon,
} from '@heroicons/vue/24/outline'
```

- [ ] **Step 3: Add Digest to `navLinks` array**

> **Note:** This intermediate form will be converted to a `computed()` in Step 4 to make the badge reactive. Do not skip Step 4.

After the `Interviews` entry:

```typescript
const navLinks = [
  { to: '/',           icon: HomeIcon,                  label: 'Home' },
  { to: '/review',     icon: ClipboardDocumentListIcon, label: 'Job Review' },
  { to: '/apply',      icon: PencilSquareIcon,          label: 'Apply' },
  { to: '/interviews', icon: CalendarDaysIcon,          label: 'Interviews' },
  { to: '/digest',     icon: NewspaperIcon,             label: 'Digest' },
  { to: '/prep',       icon: LightBulbIcon,             label: 'Interview Prep' },
  { to: '/survey',     icon: MagnifyingGlassIcon,       label: 'Survey' },
]
```

- [ ] **Step 4: Add digest store + reactive badge to `AppNav.vue`**

The template already has `<span v-if="link.badge" class="sidebar__badge">` in the nav loop (line 25) — no template change needed.

In `<script setup>`, add the digest store import after the existing imports:

```typescript
import { useDigestStore } from '@/stores/digest'
const digestStore = useDigestStore()
```

Then change `navLinks` from a static `const` array to a `computed` so the Digest entry's `badge` stays reactive. Replace the existing `const navLinks = [...]` with:

```typescript
const navLinks = computed(() => [
  { to: '/',           icon: HomeIcon,                  label: 'Home' },
  { to: '/review',     icon: ClipboardDocumentListIcon, label: 'Job Review' },
  { to: '/apply',      icon: PencilSquareIcon,          label: 'Apply' },
  { to: '/interviews', icon: CalendarDaysIcon,          label: 'Interviews' },
  { to: '/digest',     icon: NewspaperIcon,             label: 'Digest',
    badge: digestStore.entries.length || undefined },
  { to: '/prep',       icon: LightBulbIcon,             label: 'Interview Prep' },
  { to: '/survey',     icon: MagnifyingGlassIcon,       label: 'Survey' },
])
```

`computed` is already imported at the top of the script (`import { ref, computed } from 'vue'`). The `badge: undefined` case hides the badge span (falsy), so no CSS changes needed.

- [ ] **Step 5: Type-check**

```bash
cd /Library/Development/CircuitForge/peregrine/.worktrees/feature-vue-spa/web
npm run type-check 2>&1 | tail -10
```

Expected: no errors (DigestView.vue doesn't exist yet — Vue router uses lazy imports so type-check may warn; that's fine)

- [ ] **Step 6: Commit**

```bash
git add web/src/router/index.ts web/src/components/AppNav.vue
git commit -m "feat: add Digest tab to nav and router"
```

---

## Task 8: `DigestView.vue` — full page UI

**Files:**
- Create: `web/src/views/DigestView.vue`

- [ ] **Step 1: Create `DigestView.vue`**

```vue
<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useDigestStore, type DigestEntry, type DigestLink } from '@/stores/digest'
import { useApiFetch } from '@/composables/useApi'

const store = useDigestStore()

// Per-entry state keyed by DigestEntry.id
const expandedIds  = ref<Record<number, boolean>>({})
const linkResults  = ref<Record<number, DigestLink[]>>({})
const selectedUrls = ref<Record<number, Set<string>>>({})
const queueResult  = ref<Record<number, { queued: number; skipped: number } | null>>({})
const extracting   = ref<Record<number, boolean>>({})
const queuing      = ref<Record<number, boolean>>({})

onMounted(() => store.fetchAll())

function toggleExpand(id: number) {
  expandedIds.value = { ...expandedIds.value, [id]: !expandedIds.value[id] }
}

// Spread-copy pattern — same as expandedSignalIds in InterviewCard, safe for Vue 3 reactivity
function toggleUrl(entryId: number, url: string) {
  const prev = selectedUrls.value[entryId] ?? new Set<string>()
  const next = new Set(prev)
  next.has(url) ? next.delete(url) : next.add(url)
  selectedUrls.value = { ...selectedUrls.value, [entryId]: next }
}

function selectedCount(id: number) {
  return selectedUrls.value[id]?.size ?? 0
}

function jobLinks(id: number): DigestLink[] {
  return (linkResults.value[id] ?? []).filter(l => l.score >= 2)
}

function otherLinks(id: number): DigestLink[] {
  return (linkResults.value[id] ?? []).filter(l => l.score < 2)
}

async function extractLinks(entry: DigestEntry) {
  extracting.value = { ...extracting.value, [entry.id]: true }
  const { data } = await useApiFetch<{ links: DigestLink[] }>(
    `/api/digest-queue/${entry.id}/extract-links`,
    { method: 'POST' },
  )
  extracting.value = { ...extracting.value, [entry.id]: false }
  if (!data) return
  linkResults.value = { ...linkResults.value, [entry.id]: data.links }
  expandedIds.value = { ...expandedIds.value, [entry.id]: true }
  // Pre-check job-likely links
  const preChecked = new Set(data.links.filter(l => l.score >= 2).map(l => l.url))
  selectedUrls.value = { ...selectedUrls.value, [entry.id]: preChecked }
  queueResult.value = { ...queueResult.value, [entry.id]: null }
}

async function queueJobs(entry: DigestEntry) {
  const urls = [...(selectedUrls.value[entry.id] ?? [])]
  if (!urls.length) return
  queuing.value = { ...queuing.value, [entry.id]: true }
  const { data } = await useApiFetch<{ queued: number; skipped: number }>(
    `/api/digest-queue/${entry.id}/queue-jobs`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ urls }),
    },
  )
  queuing.value = { ...queuing.value, [entry.id]: false }
  if (!data) return
  queueResult.value = { ...queueResult.value, [entry.id]: data }
  linkResults.value  = { ...linkResults.value,  [entry.id]: [] }
  expandedIds.value  = { ...expandedIds.value,  [entry.id]: false }
}

function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}
</script>

<template>
  <div class="digest-view">
    <h1 class="digest-heading">📰 Digest Queue</h1>

    <div v-if="store.entries.length === 0" class="digest-empty">
      <span class="empty-bird">🦅</span>
      <p>No digest emails queued.</p>
      <p class="empty-hint">When you mark an email as 📰 Digest, it appears here.</p>
    </div>

    <div v-else class="digest-list">
      <div v-for="entry in store.entries" :key="entry.id" class="digest-entry">

        <!-- Entry header row -->
        <div class="entry-header" @click="toggleExpand(entry.id)">
          <span class="entry-toggle" aria-hidden="true">{{ expandedIds[entry.id] ? '▾' : '▸' }}</span>
          <div class="entry-meta">
            <span class="entry-subject">{{ entry.subject }}</span>
            <span class="entry-from">
              <template v-if="entry.from_addr">From: {{ entry.from_addr }} · </template>
              {{ formatDate(entry.received_at) }}
            </span>
          </div>
          <div class="entry-actions" @click.stop>
            <button
              class="btn-extract"
              :disabled="extracting[entry.id]"
              :aria-label="linkResults[entry.id]?.length ? 'Re-extract links' : 'Extract job links'"
              @click="extractLinks(entry)"
            >
              {{ linkResults[entry.id]?.length ? 'Re-extract' : 'Extract' }}
            </button>
            <button
              class="btn-dismiss"
              aria-label="Remove from digest queue"
              @click="store.remove(entry.id)"
            >✕</button>
          </div>
        </div>

        <!-- Post-queue confirmation -->
        <div v-if="queueResult[entry.id]" class="queue-result">
          ✅ {{ queueResult[entry.id]!.queued }}
          job{{ queueResult[entry.id]!.queued !== 1 ? 's' : '' }} queued for review<template
            v-if="queueResult[entry.id]!.skipped > 0"
          >, {{ queueResult[entry.id]!.skipped }} skipped (already in pipeline)</template>
        </div>

        <!-- Expanded: link list -->
        <template v-if="expandedIds[entry.id]">
          <div v-if="extracting[entry.id]" class="entry-status">Extracting links…</div>

          <div v-else-if="linkResults[entry.id] !== undefined && !linkResults[entry.id]!.length" class="entry-status">
            No job links found in this email.
          </div>

          <div v-else-if="linkResults[entry.id]?.length" class="entry-links">
            <!-- Job-likely links (score ≥ 2), pre-checked -->
            <div class="link-group">
              <label
                v-for="link in jobLinks(entry.id)"
                :key="link.url"
                class="link-row"
              >
                <input
                  type="checkbox"
                  class="link-check"
                  :checked="selectedUrls[entry.id]?.has(link.url)"
                  @change="toggleUrl(entry.id, link.url)"
                />
                <div class="link-text">
                  <span v-if="link.hint" class="link-hint">{{ link.hint }}</span>
                  <span class="link-url">{{ link.url }}</span>
                </div>
              </label>
            </div>

            <!-- Other links (score = 1), unchecked -->
            <template v-if="otherLinks(entry.id).length">
              <div class="link-divider">Other links</div>
              <div class="link-group">
                <label
                  v-for="link in otherLinks(entry.id)"
                  :key="link.url"
                  class="link-row link-row--other"
                >
                  <input
                    type="checkbox"
                    class="link-check"
                    :checked="selectedUrls[entry.id]?.has(link.url)"
                    @change="toggleUrl(entry.id, link.url)"
                  />
                  <div class="link-text">
                    <span v-if="link.hint" class="link-hint">{{ link.hint }}</span>
                    <span class="link-url">{{ link.url }}</span>
                  </div>
                </label>
              </div>
            </template>

            <button
              class="btn-queue"
              :disabled="selectedCount(entry.id) === 0 || queuing[entry.id]"
              @click="queueJobs(entry)"
            >
              Queue {{ selectedCount(entry.id) > 0 ? selectedCount(entry.id) + ' ' : '' }}selected →
            </button>
          </div>
        </template>

      </div>
    </div>
  </div>
</template>

<style scoped>
.digest-view {
  padding: var(--space-6);
  max-width: 720px;
  margin: 0 auto;
}

.digest-heading {
  font-size: 1.25rem;
  font-weight: 700;
  color: var(--color-text);
  margin-bottom: var(--space-6);
}

/* Empty state */
.digest-empty {
  text-align: center;
  padding: var(--space-16) var(--space-8);
  color: var(--color-text-muted);
}
.empty-bird  { font-size: 2.5rem; display: block; margin-bottom: var(--space-4); }
.empty-hint  { font-size: 0.875rem; margin-top: var(--space-2); }

/* Entry list */
.digest-list { display: flex; flex-direction: column; gap: var(--space-3); }

.digest-entry {
  background: var(--color-surface-raised);
  border: 1px solid var(--color-border-light);
  border-radius: 10px;
  overflow: hidden;
}

/* Entry header */
.entry-header {
  display: flex;
  align-items: flex-start;
  gap: var(--space-3);
  padding: var(--space-4);
  cursor: pointer;
  user-select: none;
}
.entry-toggle { color: var(--color-text-muted); font-size: 0.9rem; flex-shrink: 0; padding-top: 2px; }

.entry-meta  { flex: 1; min-width: 0; }
.entry-subject {
  display: block;
  font-weight: 600;
  font-size: 0.9rem;
  color: var(--color-text);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.entry-from { display: block; font-size: 0.75rem; color: var(--color-text-muted); margin-top: 2px; }

.entry-actions { display: flex; gap: var(--space-2); flex-shrink: 0; }

.btn-extract {
  font-size: 0.75rem;
  padding: 3px 10px;
  border-radius: 5px;
  border: 1px solid var(--color-border);
  background: var(--color-surface-alt);
  color: var(--color-text);
  cursor: pointer;
  transition: border-color 0.1s, color 0.1s;
}
.btn-extract:hover:not(:disabled) { border-color: var(--color-primary); color: var(--color-primary); }
.btn-extract:disabled { opacity: 0.5; cursor: default; }

.btn-dismiss {
  font-size: 0.75rem;
  padding: 3px 8px;
  border-radius: 5px;
  border: 1px solid var(--color-border-light);
  background: transparent;
  color: var(--color-text-muted);
  cursor: pointer;
  transition: border-color 0.1s, color 0.1s;
}
.btn-dismiss:hover { border-color: var(--color-error); color: var(--color-error); }

/* Queue result */
.queue-result {
  margin: 0 var(--space-4) var(--space-3);
  font-size: 0.8rem;
  color: var(--color-success);
  background: color-mix(in srgb, var(--color-success) 10%, var(--color-surface-raised));
  border-radius: 6px;
  padding: var(--space-2) var(--space-3);
}

/* Status messages */
.entry-status {
  padding: var(--space-3) var(--space-4) var(--space-4);
  font-size: 0.8rem;
  color: var(--color-text-muted);
  font-style: italic;
}

/* Link list */
.entry-links { padding: 0 var(--space-4) var(--space-4); }
.link-group  { display: flex; flex-direction: column; gap: 2px; }

.link-row {
  display: flex;
  align-items: flex-start;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-3);
  border-radius: 6px;
  cursor: pointer;
  background: var(--color-surface);
  transition: background 0.1s;
}
.link-row:hover   { background: var(--color-surface-alt); }
.link-row--other  { opacity: 0.8; }

.link-check { flex-shrink: 0; margin-top: 3px; accent-color: var(--color-primary); cursor: pointer; }

.link-text  { min-width: 0; flex: 1; }
.link-hint  {
  display: block;
  font-size: 0.8rem;
  font-weight: 500;
  color: var(--color-text);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.link-url {
  display: block;
  font-size: 0.7rem;
  color: var(--color-text-muted);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.link-divider {
  font-size: 0.7rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--color-text-muted);
  padding: var(--space-3) 0 var(--space-2);
  border-top: 1px solid var(--color-border-light);
  margin-top: var(--space-2);
}

.btn-queue {
  margin-top: var(--space-3);
  width: 100%;
  padding: var(--space-2) var(--space-4);
  border-radius: 6px;
  border: none;
  background: var(--color-primary);
  color: var(--color-text-inverse);
  font-size: 0.875rem;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.1s;
}
.btn-queue:hover:not(:disabled) { background: var(--color-primary-hover); }
.btn-queue:disabled { opacity: 0.4; cursor: default; }

@media (max-width: 600px) {
  .digest-view { padding: var(--space-4); }
  .entry-subject { font-size: 0.85rem; }
}
</style>
```

- [ ] **Step 2: Type-check**

```bash
cd /Library/Development/CircuitForge/peregrine/.worktrees/feature-vue-spa/web
npm run type-check 2>&1 | tail -10
```

Expected: no errors

- [ ] **Step 3: Smoke-test in browser**

Start the dev API and Vue dev server:

```bash
# Terminal 1 — dev API
cd /Library/Development/CircuitForge/peregrine/.worktrees/feature-vue-spa
conda run -n job-seeker uvicorn dev-api:app --port 8600 --reload

# Terminal 2 — Vue dev server
cd /Library/Development/CircuitForge/peregrine/.worktrees/feature-vue-spa/web
npm run dev
```

Open http://localhost:5173/digest — should see empty state with 🦅 bird.

- [ ] **Step 4: Commit**

```bash
git add web/src/views/DigestView.vue
git commit -m "feat: add DigestView with expand/extract/queue UI"
```

---

## Final check

- [ ] **Run full test suite one last time**

```bash
cd /Library/Development/CircuitForge/peregrine/.worktrees/feature-vue-spa
/devl/miniconda3/envs/job-seeker/bin/pytest tests/ -v 2>&1 | tail -10
```

Expected: all tests passing

- [ ] **Type-check**

```bash
cd /Library/Development/CircuitForge/peregrine/.worktrees/feature-vue-spa/web
npm run type-check 2>&1 | tail -5
```

Expected: no errors
