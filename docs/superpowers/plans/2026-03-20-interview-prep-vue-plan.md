# Interview Prep Vue Page — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the Interview Prep Vue page at `/prep/:id` — research brief with background-task generation/polling, tabbed reference panel (JD/Emails/Cover Letter), and localStorage call notes.

**Architecture:** Four new FastAPI endpoints supply research and contacts data. A new `usePrepStore` handles fetching, research generation, and 3s polling. `InterviewPrepView.vue` is a two-column layout (research left, reference right) with a redirect guard if no valid active-stage job is selected. The `InterviewCard.vue` "Prep →" button and `InterviewsView.vue` `@prep` handler are already wired — no changes needed to those files.

**Tech Stack:** Python/FastAPI + SQLite (backend), Vue 3 Composition API + Pinia (frontend), `@vueuse/core` `useLocalStorage` (notes), Vitest (store tests), pytest + FastAPI TestClient (backend tests)

---

## Files

| Action | Path | Purpose |
|--------|------|---------|
| Modify | `dev-api.py` | 4 new endpoints (research GET/generate/task, contacts GET) |
| Create | `tests/test_dev_api_prep.py` | Backend endpoint tests |
| Create | `web/src/stores/prep.ts` | Pinia store (research, contacts, task status, polling) |
| Create | `web/src/stores/prep.test.ts` | Store unit tests |
| Modify | `web/src/views/InterviewPrepView.vue` | Full page implementation (replaces stub) |

**Not changed:** `InterviewCard.vue`, `InterviewsView.vue`, `router/index.ts` — navigation is already wired.

**Verification (before starting):** Confirm the "Prep →" button already exists:
- `web/src/components/InterviewCard.vue` line 183: `<button class="card-action" @click.stop="emit('prep', job.id)">Prep →</button>`
- `web/src/views/InterviewsView.vue` line 464: `@prep="router.push(\`/prep/${$event}\`)"`
- If these lines are absent, add the button and handler before proceeding to Task 1.

---

## Codebase orientation

- `dev-api.py` — FastAPI app. Use `_get_db()` for SQLite connections. Pattern for background-task endpoints: see `generate_cover_letter` (line ~280) and `cover_letter_task` (line ~296). DB path comes from `DB_PATH = os.environ.get("STAGING_DB", "staging.db")`.
- `scripts/db.py` — `get_research(db_path, job_id)` returns dict or None. `get_contacts(db_path, job_id)` returns list oldest-first. `company_research` columns: `id, job_id, generated_at, company_brief, ceo_brief, talking_points, raw_output, tech_brief, funding_brief, competitors_brief, red_flags, accessibility_brief`.
- `scripts/task_runner.py` — `submit_task(db_path: Path, task_type: str, job_id: int) → (task_id: int, is_new: bool)`.
- `web/src/composables/useApi.ts` — `useApiFetch<T>(url, opts?)` returns `{data: T|null, error: ApiError|null}`, never rejects.
- `web/src/stores/interviews.ts` — `PipelineJob` interface, `useInterviewsStore`. **Important:** `PipelineJob` does NOT include `description` or `cover_letter` (those fields are excluded from the `/api/interviews` query to keep kanban payloads small). The prep store fetches these on-demand from `GET /api/jobs/{id}` (see below).
- `GET /api/jobs/{job_id}` (`dev-api.py` line ~233) — returns full job including `description`, `cover_letter`, `match_score`, `keyword_gaps`, `url`. Already exists, no changes needed.
- `@vueuse/core` `useLocalStorage(key, default)` — reactive ref backed by localStorage; already in `package.json`.
- Test pattern: see `tests/test_dev_api_digest.py` for fixture/monkeypatch pattern. See `web/src/stores/interviews.test.ts` for Vitest pattern.

---

### Task 1: Backend — research + contacts endpoints + tests

**Files:**
- Create: `tests/test_dev_api_prep.py`
- Modify: `dev-api.py` (add 4 endpoints after `cover_letter_task`, before `download_pdf` at line ~317)

- [ ] **Step 1: Write the failing tests**

Create `tests/test_dev_api_prep.py`:

```python
"""Tests for interview prep API endpoints (research + contacts)."""
import sqlite3
import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def tmp_db(tmp_path):
    """Temp DB with the tables needed by prep endpoints."""
    db_path = str(tmp_path / "staging.db")
    con = sqlite3.connect(db_path)
    con.executescript("""
        CREATE TABLE jobs (
            id INTEGER PRIMARY KEY,
            title TEXT, company TEXT, url TEXT, location TEXT,
            is_remote INTEGER DEFAULT 0, salary TEXT, description TEXT,
            match_score REAL, keyword_gaps TEXT, status TEXT DEFAULT 'pending',
            date_found TEXT, source TEXT, cover_letter TEXT,
            applied_at TEXT, phone_screen_at TEXT, interviewing_at TEXT,
            offer_at TEXT, hired_at TEXT, survey_at TEXT,
            interview_date TEXT, rejection_stage TEXT
        );
        CREATE TABLE company_research (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id INTEGER NOT NULL UNIQUE,
            generated_at TEXT,
            company_brief TEXT, ceo_brief TEXT, talking_points TEXT,
            raw_output TEXT, tech_brief TEXT, funding_brief TEXT,
            competitors_brief TEXT, red_flags TEXT, accessibility_brief TEXT
        );
        CREATE TABLE job_contacts (
            id INTEGER PRIMARY KEY,
            job_id INTEGER,
            direction TEXT DEFAULT 'inbound',
            subject TEXT, from_addr TEXT, body TEXT, received_at TEXT,
            stage_signal TEXT, suggestion_dismissed INTEGER DEFAULT 0
        );
        CREATE TABLE background_tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_type TEXT NOT NULL,
            job_id INTEGER DEFAULT 0,
            params TEXT,
            status TEXT NOT NULL DEFAULT 'queued',
            stage TEXT, error TEXT
        );
        CREATE TABLE digest_queue (
            id INTEGER PRIMARY KEY,
            job_contact_id INTEGER, created_at TEXT
        );
        INSERT INTO jobs (id, title, company, url, status, source, date_found)
            VALUES (1, 'Sr Engineer', 'Acme', 'https://acme.com/job/1',
                    'phone_screen', 'test', '2026-03-20');
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


def _seed_research(db_path: str) -> None:
    con = sqlite3.connect(db_path)
    con.execute("""
        INSERT INTO company_research
            (job_id, generated_at, company_brief, ceo_brief, talking_points,
             tech_brief, funding_brief, red_flags, accessibility_brief)
        VALUES
            (1, '2026-03-20 12:00:00', 'Acme builds widgets.', 'CEO is Jane.',
             '- Strong mission\n- Remote culture',
             'Python, React', 'Series B $10M',
             'No significant red flags.', 'Disability ERG active.')
    """)
    con.commit()
    con.close()


def _seed_task(db_path: str, status: str = "queued",
               stage: str | None = None, error: str | None = None) -> None:
    con = sqlite3.connect(db_path)
    con.execute(
        "INSERT INTO background_tasks (task_type, job_id, status, stage, error)"
        " VALUES ('company_research', 1, ?, ?, ?)",
        (status, stage, error),
    )
    con.commit()
    con.close()


def _seed_contacts(db_path: str) -> None:
    con = sqlite3.connect(db_path)
    con.executemany(
        "INSERT INTO job_contacts (id, job_id, direction, subject, from_addr, body, received_at)"
        " VALUES (?, 1, ?, ?, ?, ?, ?)",
        [
            (1, 'inbound',  'Phone screen invite', 'hr@acme.com',
             'We would love to chat.', '2026-03-19T10:00:00'),
            (2, 'outbound', 'Re: Phone screen',    'me@email.com',
             'Sounds great, confirmed.', '2026-03-19T11:00:00'),
        ],
    )
    con.commit()
    con.close()


# ── GET /api/jobs/{id}/research ──────────────────────────────────────────────

def test_research_get_not_found(client):
    resp = client.get("/api/jobs/1/research")
    assert resp.status_code == 404


def test_research_get_found(client, tmp_db):
    _seed_research(tmp_db)
    resp = client.get("/api/jobs/1/research")
    assert resp.status_code == 200
    data = resp.json()
    assert data["company_brief"] == "Acme builds widgets."
    assert data["talking_points"] == "- Strong mission\n- Remote culture"
    assert data["generated_at"] == "2026-03-20 12:00:00"
    assert "raw_output" not in data  # stripped — not displayed in UI


def test_research_get_unknown_job(client):
    resp = client.get("/api/jobs/999/research")
    assert resp.status_code == 404


# ── POST /api/jobs/{id}/research/generate ───────────────────────────────────

def test_research_generate_queues_task(client, monkeypatch):
    monkeypatch.setattr(
        "scripts.task_runner.submit_task",
        lambda db_path, task_type, job_id: (42, True),
    )
    resp = client.post("/api/jobs/1/research/generate")
    assert resp.status_code == 200
    data = resp.json()
    assert data["task_id"] == 42
    assert data["is_new"] is True


def test_research_generate_dedup(client, monkeypatch):
    monkeypatch.setattr(
        "scripts.task_runner.submit_task",
        lambda db_path, task_type, job_id: (7, False),
    )
    resp = client.post("/api/jobs/1/research/generate")
    assert resp.status_code == 200
    assert resp.json()["is_new"] is False


# ── GET /api/jobs/{id}/research/task ────────────────────────────────────────

def test_research_task_no_task(client):
    resp = client.get("/api/jobs/1/research/task")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "none"
    assert data["stage"] is None
    assert data["message"] is None


def test_research_task_running(client, tmp_db):
    _seed_task(tmp_db, "running", stage="Scraping company site")
    resp = client.get("/api/jobs/1/research/task")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "running"
    assert data["stage"] == "Scraping company site"
    assert data["message"] is None


def test_research_task_failed(client, tmp_db):
    _seed_task(tmp_db, "failed", error="LLM timeout")
    resp = client.get("/api/jobs/1/research/task")
    assert resp.status_code == 200
    assert resp.json()["status"] == "failed"
    assert resp.json()["message"] == "LLM timeout"


# ── GET /api/jobs/{id}/contacts ──────────────────────────────────────────────

def test_contacts_empty(client):
    resp = client.get("/api/jobs/1/contacts")
    assert resp.status_code == 200
    assert resp.json() == []


def test_contacts_returns_ordered_newest_first(client, tmp_db):
    _seed_contacts(tmp_db)
    resp = client.get("/api/jobs/1/contacts")
    assert resp.status_code == 200
    contacts = resp.json()
    assert len(contacts) == 2
    # newest first (outbound reply is more recent)
    assert contacts[0]["direction"] == "outbound"
    assert contacts[0]["subject"] == "Re: Phone screen"
    assert contacts[1]["direction"] == "inbound"
    assert "body" in contacts[0]
    assert "from_addr" in contacts[0]
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
/devl/miniconda3/envs/job-seeker/bin/pytest tests/test_dev_api_prep.py -v 2>&1 | head -40
```

Expected: all 11 tests fail with 404/422 errors (endpoints don't exist yet).

- [ ] **Step 3: Add the 4 endpoints to `dev-api.py`**

Insert after `cover_letter_task` (after line ~312, before `download_pdf`):

```python
# ── GET /api/jobs/:id/research ────────────────────────────────────────────────

@app.get("/api/jobs/{job_id}/research")
def get_research_brief(job_id: int):
    from scripts.db import get_research as _get_research
    row = _get_research(DEFAULT_DB, job_id=job_id)
    if not row:
        raise HTTPException(404, "No research found for this job")
    row.pop("raw_output", None)  # not displayed in UI
    return row


# ── POST /api/jobs/:id/research/generate ─────────────────────────────────────

@app.post("/api/jobs/{job_id}/research/generate")
def generate_research(job_id: int):
    try:
        from scripts.task_runner import submit_task
        task_id, is_new = submit_task(
            db_path=Path(DB_PATH),
            task_type="company_research",
            job_id=job_id,
        )
        return {"task_id": task_id, "is_new": is_new}
    except Exception as e:
        raise HTTPException(500, str(e))


# ── GET /api/jobs/:id/research/task ──────────────────────────────────────────

@app.get("/api/jobs/{job_id}/research/task")
def research_task(job_id: int):
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
    return {
        "status":  row["status"],
        "stage":   row["stage"],
        "message": row["error"],
    }


# ── GET /api/jobs/:id/contacts ────────────────────────────────────────────────

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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
/devl/miniconda3/envs/job-seeker/bin/pytest tests/test_dev_api_prep.py -v
```

Expected: all 11 pass.

- [ ] **Step 5: Run the full test suite to check for regressions**

```bash
/devl/miniconda3/envs/job-seeker/bin/pytest tests/ -q --tb=short 2>&1 | tail -5
```

Expected: 539 passed, 0 failed.

- [ ] **Step 6: Commit**

```bash
git add dev-api.py tests/test_dev_api_prep.py
git commit -m "feat: add research and contacts endpoints for interview prep"
```

---

### Task 2: Prep Pinia store + store tests

**Files:**
- Create: `web/src/stores/prep.ts`
- Create: `web/src/stores/prep.test.ts`

- [ ] **Step 1: Write the failing store tests**

Create `web/src/stores/prep.test.ts`:

```typescript
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { usePrepStore } from './prep'

vi.mock('../composables/useApi', () => ({
  useApiFetch: vi.fn(),
}))

import { useApiFetch } from '../composables/useApi'
const mockFetch = vi.mocked(useApiFetch)

const SAMPLE_RESEARCH = {
  job_id: 1,
  company_brief: 'Acme builds widgets.',
  ceo_brief: 'CEO is Jane.',
  talking_points: '- Strong mission',
  tech_brief: null,
  funding_brief: null,
  red_flags: null,
  accessibility_brief: null,
  generated_at: '2026-03-20 12:00:00',
}

const SAMPLE_CONTACTS = [
  { id: 2, direction: 'outbound', subject: 'Re: invite', from_addr: 'me@x.com',
    body: 'Confirmed.', received_at: '2026-03-19T11:00:00' },
]

const SAMPLE_FULL_JOB = {
  id: 1, title: 'Sr Engineer', company: 'Acme', url: 'https://acme.com/job/1',
  description: 'We build widgets.', cover_letter: 'Dear Acme…',
  match_score: 85, keyword_gaps: 'Rust',
}

const TASK_NONE    = { status: 'none',    stage: null, message: null }
const TASK_RUNNING = { status: 'running', stage: 'Scraping…', message: null }
const TASK_DONE    = { status: 'completed', stage: null, message: null }
const TASK_FAILED  = { status: 'failed',    stage: null, message: 'LLM timeout' }

describe('usePrepStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.clearAllMocks()
  })

  // fetchFor fires 4 parallel requests: research, contacts, task, full-job
  // Order in Promise.all: research, contacts, task, fullJob
  it('fetchFor loads research, contacts, task status, and full job in parallel', async () => {
    mockFetch
      .mockResolvedValueOnce({ data: SAMPLE_RESEARCH,  error: null })  // research
      .mockResolvedValueOnce({ data: SAMPLE_CONTACTS,  error: null })  // contacts
      .mockResolvedValueOnce({ data: TASK_NONE,        error: null })  // task
      .mockResolvedValueOnce({ data: SAMPLE_FULL_JOB,  error: null })  // fullJob
    const store = usePrepStore()
    await store.fetchFor(1)
    expect(store.research?.company_brief).toBe('Acme builds widgets.')
    expect(store.contacts).toHaveLength(1)
    expect(store.taskStatus.status).toBe('none')
    expect(store.fullJob?.description).toBe('We build widgets.')
    expect(store.fullJob?.cover_letter).toBe('Dear Acme…')
    expect(store.currentJobId).toBe(1)
  })

  it('fetchFor clears state when called with a different jobId', async () => {
    const store = usePrepStore()
    // First load
    mockFetch
      .mockResolvedValueOnce({ data: SAMPLE_RESEARCH, error: null })
      .mockResolvedValueOnce({ data: SAMPLE_CONTACTS, error: null })
      .mockResolvedValueOnce({ data: TASK_NONE,       error: null })
      .mockResolvedValueOnce({ data: SAMPLE_FULL_JOB, error: null })
    await store.fetchFor(1)
    expect(store.research).not.toBeNull()

    // Load different job — state clears first
    mockFetch
      .mockResolvedValueOnce({ data: null, error: { kind: 'http', status: 404, detail: '' } })
      .mockResolvedValueOnce({ data: [], error: null })
      .mockResolvedValueOnce({ data: TASK_NONE, error: null })
      .mockResolvedValueOnce({ data: { ...SAMPLE_FULL_JOB, id: 2 }, error: null })
    await store.fetchFor(2)
    expect(store.research).toBeNull()
    expect(store.currentJobId).toBe(2)
  })

  it('fetchFor starts polling when task is already running', async () => {
    mockFetch
      .mockResolvedValueOnce({ data: null,           error: { kind: 'http', status: 404, detail: '' } })
      .mockResolvedValueOnce({ data: [],             error: null })
      .mockResolvedValueOnce({ data: TASK_RUNNING,   error: null })  // task running on mount
      .mockResolvedValueOnce({ data: SAMPLE_FULL_JOB, error: null })
      .mockResolvedValueOnce({ data: TASK_DONE,      error: null })  // poll tick → done
      // fetchFor re-runs after completion (4 fetches again):
      .mockResolvedValueOnce({ data: SAMPLE_RESEARCH, error: null })
      .mockResolvedValueOnce({ data: SAMPLE_CONTACTS, error: null })
      .mockResolvedValueOnce({ data: TASK_NONE,       error: null })
      .mockResolvedValueOnce({ data: SAMPLE_FULL_JOB, error: null })
    const store = usePrepStore()
    await store.fetchFor(1)
    expect(store.taskStatus.status).toBe('running')

    // Advance timer by 3s — poll fires, task is done, fetchFor re-runs
    await vi.advanceTimersByTimeAsync(3000)
    expect(store.research?.company_brief).toBe('Acme builds widgets.')
  })

  it('generateResearch posts and starts polling', async () => {
    mockFetch
      .mockResolvedValueOnce({ data: { task_id: 42, is_new: true }, error: null })  // generate POST
      .mockResolvedValueOnce({ data: TASK_RUNNING, error: null })   // first poll tick
      .mockResolvedValueOnce({ data: TASK_DONE,    error: null })   // second poll tick → done
      // fetchFor re-runs (4 fetches):
      .mockResolvedValueOnce({ data: SAMPLE_RESEARCH, error: null })
      .mockResolvedValueOnce({ data: SAMPLE_CONTACTS, error: null })
      .mockResolvedValueOnce({ data: TASK_NONE,       error: null })
      .mockResolvedValueOnce({ data: SAMPLE_FULL_JOB, error: null })
    const store = usePrepStore()
    store.currentJobId = 1  // simulate already loaded for job 1
    await store.generateResearch(1)

    await vi.advanceTimersByTimeAsync(3000)  // first tick → running
    await vi.advanceTimersByTimeAsync(3000)  // second tick → done, re-fetch
    expect(store.research?.company_brief).toBe('Acme builds widgets.')
  })

  it('clear cancels polling interval and resets state', async () => {
    mockFetch
      .mockResolvedValueOnce({ data: null,           error: { kind: 'http', status: 404, detail: '' } })
      .mockResolvedValueOnce({ data: [],             error: null })
      .mockResolvedValueOnce({ data: TASK_RUNNING,   error: null })
      .mockResolvedValueOnce({ data: SAMPLE_FULL_JOB, error: null })
    const store = usePrepStore()
    await store.fetchFor(1)
    store.clear()
    expect(store.research).toBeNull()
    expect(store.contacts).toHaveLength(0)
    expect(store.fullJob).toBeNull()
    expect(store.currentJobId).toBeNull()
    // Advance timer — no more fetch calls should happen
    const callsBefore = mockFetch.mock.calls.length
    await vi.advanceTimersByTimeAsync(3000)
    expect(mockFetch.mock.calls.length).toBe(callsBefore)  // no new calls
  })
})
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /Library/Development/CircuitForge/peregrine/.worktrees/feature-vue-spa/web && npm test -- --reporter=verbose 2>&1 | grep -A 3 "prep.test"
```

Expected: import error or test failures (store doesn't exist yet).

- [ ] **Step 3: Implement the store**

Create `web/src/stores/prep.ts`:

```typescript
import { defineStore } from 'pinia'
import { ref } from 'vue'
import { useApiFetch } from '../composables/useApi'

export interface ResearchBrief {
  job_id: number
  company_brief: string | null
  ceo_brief: string | null
  talking_points: string | null
  tech_brief: string | null
  funding_brief: string | null
  red_flags: string | null
  accessibility_brief: string | null
  generated_at: string | null
  // raw_output intentionally omitted — not displayed in UI
}

export interface Contact {
  id: number
  direction: 'inbound' | 'outbound'
  subject: string | null
  from_addr: string | null
  body: string | null
  received_at: string | null
}

export interface TaskStatus {
  status: 'queued' | 'running' | 'completed' | 'failed' | 'none' | null
  stage: string | null
  message: string | null  // maps background_tasks.error; matches cover_letter_task shape
}

export interface FullJobDetail {
  id: number
  title: string
  company: string
  url: string | null
  description: string | null
  cover_letter: string | null
  match_score: number | null
  keyword_gaps: string | null
}

export const usePrepStore = defineStore('prep', () => {
  const research      = ref<ResearchBrief | null>(null)
  const contacts      = ref<Contact[]>([])
  const taskStatus    = ref<TaskStatus>({ status: null, stage: null, message: null })
  const fullJob       = ref<FullJobDetail | null>(null)
  const loading       = ref(false)
  const error         = ref<string | null>(null)
  const currentJobId  = ref<number | null>(null)

  let pollId: ReturnType<typeof setInterval> | null = null

  function _stopPoll() {
    if (pollId !== null) { clearInterval(pollId); pollId = null }
  }

  async function pollTask(jobId: number) {
    _stopPoll()
    pollId = setInterval(async () => {
      const { data } = await useApiFetch<TaskStatus>(`/api/jobs/${jobId}/research/task`)
      if (!data) return
      taskStatus.value = data
      if (data.status === 'completed' || data.status === 'failed') {
        _stopPoll()
        if (data.status === 'completed') await fetchFor(jobId)
      }
    }, 3000)
  }

  async function fetchFor(jobId: number) {
    if (jobId !== currentJobId.value) {
      _stopPoll()
      research.value    = null
      contacts.value    = []
      taskStatus.value  = { status: null, stage: null, message: null }
      fullJob.value     = null
      error.value       = null
      currentJobId.value = jobId
    }
    loading.value = true

    // 4 parallel fetches: research (may 404), contacts, task status, full job detail
    // Full job needed for description + cover_letter (not on PipelineJob in interviews store)
    const [resRes, conRes, taskRes, jobRes] = await Promise.all([
      useApiFetch<ResearchBrief>(`/api/jobs/${jobId}/research`),
      useApiFetch<Contact[]>(`/api/jobs/${jobId}/contacts`),
      useApiFetch<TaskStatus>(`/api/jobs/${jobId}/research/task`),
      useApiFetch<FullJobDetail>(`/api/jobs/${jobId}`),
    ])

    loading.value = false

    // 404 = no research yet — not an error, show generate button
    if (resRes.error && resRes.error.kind === 'http' && resRes.error.status !== 404) {
      error.value = `Could not load research: ${resRes.error.status}`
    } else {
      research.value = resRes.data
    }

    contacts.value   = conRes.data ?? []
    taskStatus.value = taskRes.data ?? { status: null, stage: null, message: null }
    fullJob.value    = jobRes.data

    if (taskStatus.value.status === 'queued' || taskStatus.value.status === 'running') {
      pollTask(jobId)
    }
  }

  async function generateResearch(jobId: number) {
    const { error: err } = await useApiFetch(`/api/jobs/${jobId}/research/generate`, {
      method: 'POST',
    })
    if (err) {
      error.value = 'Could not start research generation'
      return
    }
    taskStatus.value = { status: 'queued', stage: null, message: null }
    pollTask(jobId)
  }

  function clear() {
    _stopPoll()
    research.value     = null
    contacts.value     = []
    taskStatus.value   = { status: null, stage: null, message: null }
    fullJob.value      = null
    loading.value      = false
    error.value        = null
    currentJobId.value = null
  }

  return { research, contacts, taskStatus, fullJob, loading, error, currentJobId,
           fetchFor, generateResearch, pollTask, clear }
})
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /Library/Development/CircuitForge/peregrine/.worktrees/feature-vue-spa/web && npm test -- --reporter=verbose 2>&1 | grep -A 5 "prep"
```

Expected: 5/5 prep store tests pass.

- [ ] **Step 5: Run full frontend test suite**

```bash
cd /Library/Development/CircuitForge/peregrine/.worktrees/feature-vue-spa/web && npm test
```

Expected: all tests pass (no regressions).

- [ ] **Step 6: Commit**

```bash
git add web/src/stores/prep.ts web/src/stores/prep.test.ts
git commit -m "feat: add prep Pinia store with research polling"
```

---

### Task 3: InterviewPrepView.vue

**Files:**
- Modify: `web/src/views/InterviewPrepView.vue` (replace stub)

No automated tests for the component itself — verified manually against the dev server.

**Key patterns from the codebase:**
- `useInterviewsStore()` — already has all PipelineJob data (title, company, url, description, cover_letter, match_score, keyword_gaps, interview_date, status)
- `usePrepStore()` from Task 2
- `useLocalStorage(key, default)` from `@vueuse/core` — reactive ref backed by localStorage
- `useRouter()` / `useRoute()` from `vue-router` for redirect + params
- Active stages for prep: `phone_screen`, `interviewing`, `offer`
- All CSS uses `var(--color-*)`, `var(--space-*)`, `var(--app-primary)` etc. (see `AppNav.vue` for reference)
- Mobile breakpoint: `@media (max-width: 1023px)` matches the rest of the app

- [ ] **Step 1: Implement `InterviewPrepView.vue`**

Replace the stub with the full implementation:

```vue
<template>
  <div v-if="job" class="prep-root">

    <!-- ── Left column: research brief ─────────────────────────── -->
    <section class="prep-left" aria-label="Interview preparation">

      <!-- Job header -->
      <header class="prep-header">
        <h1 class="prep-title">{{ job.company }} — {{ job.title }}</h1>
        <div class="prep-meta">
          <span class="stage-badge" :class="`stage-badge--${job.status}`">
            {{ STAGE_LABELS[job.status as PipelineStage] ?? job.status }}
          </span>
          <span v-if="countdownLabel" class="countdown">{{ countdownLabel }}</span>
        </div>
        <a v-if="job.url" :href="job.url" target="_blank" rel="noopener"
           class="listing-link">Open job listing ↗</a>
      </header>

      <!-- Research controls -->
      <div class="research-controls">
        <!-- No research, no task running -->
        <template v-if="!prepStore.research && !isTaskActive">
          <p v-if="prepStore.error" class="research-error">{{ prepStore.error }}</p>
          <button class="btn btn--primary" @click="prepStore.generateResearch(jobId)">
            🔬 Generate research brief
          </button>
        </template>

        <!-- Task running / queued -->
        <template v-else-if="isTaskActive">
          <div class="task-spinner" role="status">
            <span class="spinner" aria-hidden="true"></span>
            <span>{{ prepStore.taskStatus.stage || 'Generating… this may take 30–60 seconds' }}</span>
          </div>
        </template>

        <!-- Research loaded header -->
        <template v-else-if="prepStore.research">
          <div class="research-meta">
            <span class="research-ts">Generated: {{ prepStore.research.generated_at?.slice(0, 16) ?? '—' }}</span>
            <button class="btn btn--ghost btn--sm"
                    :disabled="isTaskActive"
                    @click="prepStore.generateResearch(jobId)">
              🔄 Refresh
            </button>
          </div>
          <!-- Task failed while research exists -->
          <p v-if="prepStore.taskStatus.status === 'failed'" class="research-error">
            Refresh failed: {{ prepStore.taskStatus.message }}
            <button class="btn btn--ghost btn--sm" @click="prepStore.generateResearch(jobId)">Retry</button>
          </p>
        </template>

        <!-- Task failed, no research -->
        <template v-else-if="prepStore.taskStatus.status === 'failed'">
          <p class="research-error">Generation failed: {{ prepStore.taskStatus.message }}</p>
          <button class="btn btn--primary" @click="prepStore.generateResearch(jobId)">Retry</button>
        </template>
      </div>

      <!-- Research sections — only when loaded -->
      <template v-if="prepStore.research">
        <div class="research-divider"></div>

        <section v-if="prepStore.research.talking_points?.trim()" class="research-section">
          <h2 class="research-section__title">🎯 Talking Points</h2>
          <pre class="research-text">{{ prepStore.research.talking_points }}</pre>
        </section>

        <section v-if="prepStore.research.company_brief?.trim()" class="research-section">
          <h2 class="research-section__title">🏢 Company Overview</h2>
          <pre class="research-text">{{ prepStore.research.company_brief }}</pre>
        </section>

        <section v-if="prepStore.research.ceo_brief?.trim()" class="research-section">
          <h2 class="research-section__title">👤 Leadership &amp; Culture</h2>
          <pre class="research-text">{{ prepStore.research.ceo_brief }}</pre>
        </section>

        <section v-if="prepStore.research.tech_brief?.trim()" class="research-section">
          <h2 class="research-section__title">⚙️ Tech Stack &amp; Product</h2>
          <pre class="research-text">{{ prepStore.research.tech_brief }}</pre>
        </section>

        <section v-if="prepStore.research.funding_brief?.trim()" class="research-section">
          <h2 class="research-section__title">💰 Funding &amp; Market Position</h2>
          <pre class="research-text">{{ prepStore.research.funding_brief }}</pre>
        </section>

        <section v-if="showRedFlags" class="research-section research-section--warning">
          <h2 class="research-section__title">⚠️ Red Flags &amp; Watch-outs</h2>
          <pre class="research-text">{{ prepStore.research.red_flags }}</pre>
        </section>

        <section v-if="prepStore.research.accessibility_brief?.trim()" class="research-section">
          <h2 class="research-section__title">♿ Inclusion &amp; Accessibility</h2>
          <p class="research-privacy">For your personal evaluation — not disclosed in any application.</p>
          <pre class="research-text">{{ prepStore.research.accessibility_brief }}</pre>
        </section>
      </template>

    </section>

    <!-- ── Right column: reference panel ───────────────────────── -->
    <section class="prep-right" aria-label="Reference materials">

      <!-- Tabs -->
      <div class="ref-tabs" role="tablist">
        <button
          v-for="tab in TABS" :key="tab.id"
          class="ref-tab"
          :class="{ 'ref-tab--active': activeTab === tab.id }"
          role="tab"
          :aria-selected="activeTab === tab.id"
          @click="activeTab = tab.id"
        >{{ tab.label }}</button>
      </div>

      <div class="ref-panel">

        <!-- Job Description -->
        <div v-show="activeTab === 'jd'" role="tabpanel">
          <!-- match_score + keyword_gaps come from prepStore.fullJob (not PipelineJob) -->
          <div v-if="prepStore.fullJob?.match_score != null" class="score-row">
            <span class="score-badge" :class="scoreBadgeClass">
              {{ scoreBadgeLabel }}
            </span>
            <span v-if="prepStore.fullJob?.keyword_gaps" class="keyword-gaps">
              Gaps: {{ prepStore.fullJob.keyword_gaps }}
            </span>
          </div>
          <pre v-if="prepStore.fullJob?.description" class="research-text jd-text">{{ prepStore.fullJob.description }}</pre>
          <p v-else class="empty-state">No description saved for this listing.</p>
        </div>

        <!-- Email History -->
        <div v-show="activeTab === 'email'" role="tabpanel">
          <p v-if="prepStore.contacts.length === 0" class="empty-state">
            No emails logged yet.
          </p>
          <template v-else>
            <article v-for="c in prepStore.contacts" :key="c.id" class="contact-item">
              <div class="contact-header">
                <span>{{ c.direction === 'inbound' ? '📥' : '📤' }}</span>
                <strong class="contact-subject">{{ c.subject || '(no subject)' }}</strong>
                <span class="contact-date">{{ c.received_at?.slice(0, 10) ?? '' }}</span>
              </div>
              <p v-if="c.from_addr" class="contact-from">From: {{ c.from_addr }}</p>
              <pre v-if="c.body" class="contact-body">{{ c.body.slice(0, 500) }}{{ c.body.length > 500 ? '…' : '' }}</pre>
            </article>
          </template>
        </div>

        <!-- Cover Letter -->
        <div v-show="activeTab === 'letter'" role="tabpanel">
          <!-- cover_letter comes from prepStore.fullJob (not PipelineJob) -->
          <pre v-if="prepStore.fullJob?.cover_letter?.trim()" class="research-text">{{ prepStore.fullJob.cover_letter }}</pre>
          <p v-else class="empty-state">No cover letter saved for this job.</p>
        </div>

      </div>

      <!-- Call Notes -->
      <div class="notes-section">
        <h2 class="notes-title">📝 Call Notes</h2>
        <p class="notes-caption">Notes are saved locally — they won't sync between devices.</p>
        <textarea
          v-model="notes"
          class="notes-textarea"
          placeholder="Type notes during or after the call…"
          rows="8"
        ></textarea>
      </div>

    </section>
  </div>

  <!-- Loading state — interviewsStore not yet populated -->
  <div v-else class="prep-loading">
    <span class="spinner" aria-hidden="true"></span>
    <span>Loading…</span>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useLocalStorage } from '@vueuse/core'
import { useInterviewsStore } from '../stores/interviews'
import { usePrepStore } from '../stores/prep'
import type { PipelineStage } from '../stores/interviews'
import { STAGE_LABELS } from '../stores/interviews'

const route  = useRoute()
const router = useRouter()
const interviewsStore = useInterviewsStore()
const prepStore       = usePrepStore()

const ACTIVE_STAGES = new Set<string>(['phone_screen', 'interviewing', 'offer'])

const TABS = [
  { id: 'jd'     as const, label: '📄 Job Description' },
  { id: 'email'  as const, label: '📧 Email History'   },
  { id: 'letter' as const, label: '📝 Cover Letter'    },
] as const

type TabId = typeof TABS[number]['id']
const activeTab = ref<TabId>('jd')

// ── Job resolution ────────────────────────────────────────────────────────────
const jobId = computed(() => {
  const raw = route.params.id
  return Array.isArray(raw) ? parseInt(raw[0]) : parseInt(raw as string)
})

const job = computed(() =>
  isNaN(jobId.value)
    ? null
    : interviewsStore.jobs.find(j => j.id === jobId.value && ACTIVE_STAGES.has(j.status)) ?? null
)

// ── Interview date countdown ──────────────────────────────────────────────────
const countdownLabel = computed(() => {
  const idate = job.value?.interview_date
  if (!idate) return ''
  const today  = new Date(); today.setHours(0, 0, 0, 0)
  const target = new Date(idate); target.setHours(0, 0, 0, 0)
  const delta  = Math.round((target.getTime() - today.getTime()) / 86_400_000)
  if (delta === 0) return '🔴 TODAY'
  if (delta === 1) return '🟡 TOMORROW'
  if (delta > 0)   return `🟢 in ${delta} days`
  return `(was ${Math.abs(delta)}d ago)`
})

// ── Research task status helpers ──────────────────────────────────────────────
const isTaskActive = computed(() =>
  prepStore.taskStatus.status === 'queued' || prepStore.taskStatus.status === 'running'
)

const showRedFlags = computed(() => {
  const rf = prepStore.research?.red_flags?.trim()
  return rf && !rf.toLowerCase().includes('no significant red flags')
})

// ── Match score badge — uses prepStore.fullJob (has description/cover_letter/match_score) ──
const scoreBadgeClass = computed(() => {
  const s = prepStore.fullJob?.match_score
  if (s == null) return ''
  return s >= 70 ? 'score--green' : s >= 40 ? 'score--yellow' : 'score--red'
})

const scoreBadgeLabel = computed(() => {
  const s = prepStore.fullJob?.match_score
  if (s == null) return ''
  const emoji = s >= 70 ? '🟢' : s >= 40 ? '🟡' : '🔴'
  return `${emoji} ${s.toFixed(0)}% match`
})

// ── Call Notes — localStorage per job ────────────────────────────────────────
const notes = useLocalStorage(
  computed(() => `cf-prep-notes-${jobId.value}`),
  '',
)

// ── Lifecycle ─────────────────────────────────────────────────────────────────
onMounted(async () => {
  // /prep with no id or non-numeric id → redirect
  if (isNaN(jobId.value)) { router.replace('/interviews'); return }

  // If interviews store is empty (direct navigation), fetch first
  if (interviewsStore.jobs.length === 0) await interviewsStore.fetchAll()

  // Job not found or wrong stage → redirect
  if (!job.value) { router.replace('/interviews'); return }

  await prepStore.fetchFor(jobId.value)
})

onUnmounted(() => {
  prepStore.clear()
})
</script>

<style scoped>
/* ── Layout ──────────────────────────────────────────────────── */
.prep-root {
  display: flex;
  gap: var(--space-6);
  padding: var(--space-6);
  min-height: 100dvh;
  align-items: flex-start;
}

.prep-left  { flex: 0 0 40%; min-width: 0; }
.prep-right { flex: 1; min-width: 0; }

/* ── Job header ──────────────────────────────────────────────── */
.prep-title {
  font-family: var(--font-display);
  font-size: var(--text-xl);
  font-weight: 700;
  color: var(--color-text);
  margin-bottom: var(--space-2);
}

.prep-meta {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  flex-wrap: wrap;
  margin-bottom: var(--space-3);
}

.stage-badge {
  font-size: var(--text-xs);
  font-weight: 600;
  padding: 2px var(--space-2);
  border-radius: var(--radius-full);
  background: var(--app-primary-light);
  color: var(--app-primary);
}

.countdown {
  font-size: var(--text-sm);
  color: var(--color-text-muted);
}

.listing-link {
  display: inline-block;
  font-size: var(--text-sm);
  color: var(--app-primary);
  text-decoration: none;
  margin-bottom: var(--space-4);
}
.listing-link:hover { text-decoration: underline; }

/* ── Research controls ───────────────────────────────────────── */
.research-controls {
  margin-bottom: var(--space-4);
}

.task-spinner {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  font-size: var(--text-sm);
  color: var(--color-text-muted);
}

.spinner {
  display: inline-block;
  width: 1rem;
  height: 1rem;
  border: 2px solid var(--color-border);
  border-top-color: var(--app-primary);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
  flex-shrink: 0;
}

@keyframes spin { to { transform: rotate(360deg); } }

.research-meta {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  flex-wrap: wrap;
}

.research-ts {
  font-size: var(--text-xs);
  color: var(--color-text-muted);
}

.research-error {
  color: var(--color-error, #c0392b);
  font-size: var(--text-sm);
  margin-bottom: var(--space-2);
}

.research-divider {
  border-top: 1px solid var(--color-border-light);
  margin: var(--space-4) 0;
}

/* ── Research sections ───────────────────────────────────────── */
.research-section {
  margin-bottom: var(--space-5);
}

.research-section__title {
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--color-text);
  margin-bottom: var(--space-2);
}

.research-section--warning {
  background: var(--color-warning-bg, #fff8e1);
  border-left: 3px solid var(--color-warning, #f39c12);
  padding: var(--space-3);
  border-radius: 0 var(--radius-md) var(--radius-md) 0;
}

.research-privacy {
  font-size: var(--text-xs);
  color: var(--color-text-muted);
  font-style: italic;
  margin-bottom: var(--space-2);
}

.research-text {
  white-space: pre-wrap;
  word-break: break-word;
  font-family: var(--font-body, sans-serif);
  font-size: var(--text-sm);
  line-height: 1.6;
  color: var(--color-text);
  margin: 0;
}

/* ── Tabs ────────────────────────────────────────────────────── */
.ref-tabs {
  display: flex;
  gap: var(--space-1);
  border-bottom: 2px solid var(--color-border);
  margin-bottom: var(--space-4);
}

.ref-tab {
  padding: var(--space-2) var(--space-3);
  font-size: var(--text-sm);
  font-weight: 500;
  border: none;
  background: none;
  color: var(--color-text-muted);
  cursor: pointer;
  border-bottom: 2px solid transparent;
  margin-bottom: -2px;
  transition: color 150ms ease, border-color 150ms ease;
}

.ref-tab:hover { color: var(--app-primary); }

.ref-tab--active {
  color: var(--app-primary);
  border-bottom-color: var(--app-primary);
  font-weight: 600;
}

.ref-panel {
  min-height: 200px;
}

/* ── JD panel ────────────────────────────────────────────────── */
.score-row {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  flex-wrap: wrap;
  margin-bottom: var(--space-3);
  font-size: var(--text-sm);
}

.score-badge { font-weight: 600; }
.score--green  { color: var(--color-success, #27ae60); }
.score--yellow { color: var(--color-warning, #f39c12); }
.score--red    { color: var(--color-error, #c0392b); }

.keyword-gaps { color: var(--color-text-muted); }

.jd-text {
  max-height: 60vh;
  overflow-y: auto;
}

/* ── Email tab ───────────────────────────────────────────────── */
.contact-item {
  padding: var(--space-3) 0;
  border-bottom: 1px solid var(--color-border-light);
}
.contact-item:last-child { border-bottom: none; }

.contact-header {
  display: flex;
  align-items: baseline;
  gap: var(--space-2);
  flex-wrap: wrap;
  margin-bottom: var(--space-1);
}

.contact-subject {
  font-size: var(--text-sm);
  font-weight: 600;
}

.contact-date {
  font-size: var(--text-xs);
  color: var(--color-text-muted);
}

.contact-from {
  font-size: var(--text-xs);
  color: var(--color-text-muted);
  margin-bottom: var(--space-1);
}

.contact-body {
  white-space: pre-wrap;
  word-break: break-word;
  font-family: var(--font-body, sans-serif);
  font-size: var(--text-xs);
  color: var(--color-text-muted);
  margin: 0;
  max-height: 120px;
  overflow: hidden;
}

/* ── Notes ───────────────────────────────────────────────────── */
.notes-section {
  margin-top: var(--space-6);
  border-top: 1px solid var(--color-border-light);
  padding-top: var(--space-4);
}

.notes-title {
  font-size: var(--text-sm);
  font-weight: 600;
  margin-bottom: var(--space-1);
}

.notes-caption {
  font-size: var(--text-xs);
  color: var(--color-text-muted);
  margin-bottom: var(--space-2);
}

.notes-textarea {
  width: 100%;
  resize: vertical;
  padding: var(--space-3);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  background: var(--color-surface);
  color: var(--color-text);
  font-family: var(--font-body, sans-serif);
  font-size: var(--text-sm);
  line-height: 1.5;
  transition: border-color 150ms ease;
}
.notes-textarea:focus {
  outline: none;
  border-color: var(--app-primary);
}

/* ── Buttons ─────────────────────────────────────────────────── */
.btn {
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
  padding: var(--space-2) var(--space-4);
  border-radius: var(--radius-md);
  font-size: var(--text-sm);
  font-weight: 500;
  cursor: pointer;
  border: 1px solid transparent;
  transition: background 150ms ease, color 150ms ease;
}
.btn--primary {
  background: var(--app-primary);
  color: white;
  border-color: var(--app-primary);
}
.btn--primary:hover { filter: brightness(1.1); }
.btn--ghost {
  background: transparent;
  color: var(--app-primary);
  border-color: var(--app-primary);
}
.btn--ghost:hover { background: var(--app-primary-light); }
.btn--sm { padding: var(--space-1) var(--space-2); font-size: var(--text-xs); }
.btn:disabled { opacity: 0.5; cursor: not-allowed; }

/* ── Empty / loading states ──────────────────────────────────── */
.empty-state {
  color: var(--color-text-muted);
  font-size: var(--text-sm);
  padding: var(--space-4) 0;
}

.prep-loading {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-3);
  min-height: 40vh;
  color: var(--color-text-muted);
}

/* ── Mobile: single column ───────────────────────────────────── */
@media (max-width: 1023px) {
  .prep-root {
    flex-direction: column;
    padding: var(--space-4);
    gap: var(--space-4);
  }
  .prep-left  { flex: none; width: 100%; }
  .prep-right { flex: none; width: 100%; }
}
</style>
```

- [ ] **Step 2: Open the dev server and verify the page loads**

```bash
# From the worktree web directory — dev server should already be running at :5173
# Navigate to http://10.1.10.71:5173/prep/<a job id in phone_screen/interviewing/offer>
# Verify:
# - Job header, stage badge, countdown show correctly
# - Left panel shows "Generate research brief" button (if no research)
# - Right panel shows JD / Email / Letter tabs
# - Switching tabs works
# - Notes textarea persists after page refresh (localStorage)
# - Navigating to /prep (no id) redirects to /interviews
```

- [ ] **Step 3: Run full test suite (Python)**

```bash
/devl/miniconda3/envs/job-seeker/bin/pytest tests/ -q --tb=short 2>&1 | tail -5
```

Expected: 539 passed, 0 failed.

- [ ] **Step 4: Run full frontend tests**

```bash
cd /Library/Development/CircuitForge/peregrine/.worktrees/feature-vue-spa/web && npm test
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add web/src/views/InterviewPrepView.vue
git commit -m "feat: implement InterviewPrepView with research polling and reference tabs"
```
