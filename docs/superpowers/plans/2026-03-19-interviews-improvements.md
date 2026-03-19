# Interviews Page Improvements — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add three improvements to the Interviews page: (1) collapsible Applied/Survey pre-kanban section with localStorage persistence, (2) email sync status pill in the page header, (3) stage signal banners on job cards in both the pre-list and the kanban.

**Architecture:** Backend adds four new endpoints to `dev-api.py` (stage signals batched into `GET /api/interviews`, email sync trigger/status, signal dismiss). The store gets a new exported `StageSignal` type. `MoveToSheet` gains an optional `preSelectedStage` prop. `InterviewCard` gains the signal banner and an extended `move` emit. `InterviewsView` gets the collapsible section and email sync pill — both wired together.

**Tech Stack:** Python FastAPI (dev-api.py), Vue 3, TypeScript, Pinia, CSS `max-height` transition

---

## File Map

| File | Action |
|---|---|
| `dev-api.py` | Stage signals in `/api/interviews`; `POST /api/email/sync`; `GET /api/email/sync/status`; `POST /api/stage-signals/{id}/dismiss` |
| `tests/test_dev_api_interviews.py` | **NEW** — pytest tests for all four new dev-api behaviors |
| `web/src/stores/interviews.ts` | Export `StageSignal` interface; add `stage_signals: StageSignal[]` to `PipelineJob`; update `fetchAll()` identity map |
| `web/src/components/MoveToSheet.vue` | Add optional `preSelectedStage?: PipelineStage` prop; pre-select on open |
| `web/src/components/InterviewCard.vue` | Signal banner at card bottom; extend `move` emit signature |
| `web/src/views/InterviewsView.vue` | Collapsible Applied section (localStorage, `max-height` CSS, signal count in header); email sync pill + polling; wire `preSelectedStage` through `openMove` → `MoveToSheet` |

---

## Task 1: Backend — new dev-api.py endpoints

**Files:**
- Modify: `dev-api.py`
- Create: `tests/test_dev_api_interviews.py`

### Context

`list_interviews()` (line 286) currently runs one query then closes the DB. We'll refactor it to keep the connection open, run a second query for undismissed signals, group results by `job_id` in Python, then close. The three new endpoints follow the existing `_get_db()` + `db.close()` pattern. SQLite column is `finished_at` (NOT `completed_at`) in `background_tasks`. Use `job_id = 0` as sentinel for global email sync tasks.

Signal types to **exclude** from the query: `'neutral'`, `'unrelated'`, `'digest'`, `'event_rescheduled'`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_dev_api_interviews.py`:

```python
"""Tests for new dev-api.py endpoints: stage signals, email sync, signal dismiss."""
import sqlite3
import tempfile
import os
import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def tmp_db(tmp_path):
    """Create a minimal staging.db schema in a temp dir."""
    db_path = str(tmp_path / "staging.db")
    con = sqlite3.connect(db_path)
    con.executescript("""
        CREATE TABLE jobs (
            id INTEGER PRIMARY KEY,
            title TEXT, company TEXT, url TEXT, location TEXT,
            is_remote INTEGER DEFAULT 0, salary TEXT,
            match_score REAL, keyword_gaps TEXT, status TEXT,
            interview_date TEXT, rejection_stage TEXT,
            applied_at TEXT, phone_screen_at TEXT, interviewing_at TEXT,
            offer_at TEXT, hired_at TEXT, survey_at TEXT
        );
        CREATE TABLE job_contacts (
            id INTEGER PRIMARY KEY,
            job_id INTEGER,
            subject TEXT,
            received_at TEXT,
            stage_signal TEXT,
            suggestion_dismissed INTEGER DEFAULT 0
        );
        CREATE TABLE background_tasks (
            id INTEGER PRIMARY KEY,
            task_type TEXT,
            job_id INTEGER,
            status TEXT DEFAULT 'queued',
            finished_at TEXT
        );
        INSERT INTO jobs (id, title, company, status) VALUES
            (1, 'Engineer', 'Acme', 'applied'),
            (2, 'Designer', 'Beta', 'phone_screen');
        INSERT INTO job_contacts (id, job_id, subject, received_at, stage_signal, suggestion_dismissed) VALUES
            (10, 1, 'Interview confirmed', '2026-03-19T10:00:00', 'interview_scheduled', 0),
            (11, 1, 'Old neutral', '2026-03-18T09:00:00', 'neutral', 0),
            (12, 2, 'Offer letter', '2026-03-19T11:00:00', 'offer_received', 0),
            (13, 1, 'Already dismissed', '2026-03-17T08:00:00', 'positive_response', 1);
    """)
    con.close()
    return db_path


@pytest.fixture()
def client(tmp_db, monkeypatch):
    monkeypatch.setenv("STAGING_DB", tmp_db)
    # Re-import after env var is set so DB_PATH picks it up
    import importlib
    import dev_api
    importlib.reload(dev_api)
    return TestClient(dev_api.app)


# ── GET /api/interviews — stage signals batched ────────────────────────────

def test_interviews_includes_stage_signals(client):
    resp = client.get("/api/interviews")
    assert resp.status_code == 200
    jobs = {j["id"]: j for j in resp.json()}

    # job 1 should have exactly 1 undismissed non-excluded signal
    assert "stage_signals" in jobs[1]
    signals = jobs[1]["stage_signals"]
    assert len(signals) == 1
    assert signals[0]["stage_signal"] == "interview_scheduled"
    assert signals[0]["subject"] == "Interview confirmed"
    assert signals[0]["id"] == 10

    # neutral signal excluded
    signal_types = [s["stage_signal"] for s in signals]
    assert "neutral" not in signal_types

    # dismissed signal excluded
    signal_ids = [s["id"] for s in signals]
    assert 13 not in signal_ids

    # job 2 has an offer signal
    assert len(jobs[2]["stage_signals"]) == 1
    assert jobs[2]["stage_signals"][0]["stage_signal"] == "offer_received"


def test_interviews_empty_signals_for_job_without_contacts(client, tmp_db):
    con = sqlite3.connect(tmp_db)
    con.execute("INSERT INTO jobs (id, title, company, status) VALUES (3, 'NoContact', 'Corp', 'survey')")
    con.commit(); con.close()
    resp = client.get("/api/interviews")
    jobs = {j["id"]: j for j in resp.json()}
    assert jobs[3]["stage_signals"] == []


# ── POST /api/email/sync ───────────────────────────────────────────────────

def test_email_sync_returns_202(client):
    resp = client.post("/api/email/sync")
    assert resp.status_code == 202
    assert "task_id" in resp.json()


def test_email_sync_inserts_background_task(client, tmp_db):
    client.post("/api/email/sync")
    con = sqlite3.connect(tmp_db)
    row = con.execute(
        "SELECT task_type, job_id, status FROM background_tasks WHERE task_type='email_sync'"
    ).fetchone()
    con.close()
    assert row is not None
    assert row[0] == "email_sync"
    assert row[1] == 0   # sentinel
    assert row[2] == "queued"


# ── GET /api/email/sync/status ─────────────────────────────────────────────

def test_email_sync_status_idle_when_no_tasks(client):
    resp = client.get("/api/email/sync/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "idle"
    assert body["last_completed_at"] is None


def test_email_sync_status_reflects_latest_task(client, tmp_db):
    con = sqlite3.connect(tmp_db)
    con.execute(
        "INSERT INTO background_tasks (task_type, job_id, status, finished_at) VALUES "
        "('email_sync', 0, 'completed', '2026-03-19T12:00:00')"
    )
    con.commit(); con.close()
    resp = client.get("/api/email/sync/status")
    body = resp.json()
    assert body["status"] == "completed"
    assert body["last_completed_at"] == "2026-03-19T12:00:00"


# ── POST /api/stage-signals/{id}/dismiss ──────────────────────────────────

def test_dismiss_signal_sets_flag(client, tmp_db):
    resp = client.post("/api/stage-signals/10/dismiss")
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}
    con = sqlite3.connect(tmp_db)
    row = con.execute(
        "SELECT suggestion_dismissed FROM job_contacts WHERE id = 10"
    ).fetchone()
    con.close()
    assert row[0] == 1


def test_dismiss_signal_404_for_missing_id(client):
    resp = client.post("/api/stage-signals/9999/dismiss")
    assert resp.status_code == 404
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /Library/Development/CircuitForge/peregrine/.worktrees/feature-vue-spa
/devl/miniconda3/envs/job-seeker/bin/pytest tests/test_dev_api_interviews.py -v
```

Expected: FAIL — `dev_api` module not found (tests reference `dev_api` not `dev-api`).

- [ ] **Step 3: Create a `dev_api.py` symlink (module alias)**

The test imports `dev_api` (underscore). Create a thin module alias:

```bash
cd /Library/Development/CircuitForge/peregrine/.worktrees/feature-vue-spa
ln -sf dev-api.py dev_api.py
```

Re-run — should now fail with `ImportError` or route-not-found errors (not import error), which confirms the test infrastructure works.

- [ ] **Step 4: Implement the four backend changes in `dev-api.py`**

**4a — Stage signals in `list_interviews()`:** Replace lines 286–301 with:

```python
SIGNAL_EXCLUDED = ("neutral", "unrelated", "digest", "event_rescheduled")

@app.get("/api/interviews")
def list_interviews():
    db = _get_db()
    placeholders = ",".join("?" * len(PIPELINE_STATUSES))
    rows = db.execute(
        f"SELECT id, title, company, url, location, is_remote, salary, "
        f"match_score, keyword_gaps, status, "
        f"interview_date, rejection_stage, "
        f"applied_at, phone_screen_at, interviewing_at, offer_at, hired_at, survey_at "
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
            f"SELECT id, job_id, subject, received_at, stage_signal "
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
            })

    db.close()
    return [
        {**dict(r), "is_remote": bool(r["is_remote"]), "stage_signals": signals_by_job[r["id"]]}
        for r in rows
    ]
```

**4b — Email sync endpoints:** Add after the `list_interviews` function (before the `POST /api/jobs/{id}/move` block):

```python
# ── POST /api/email/sync ──────────────────────────────────────────────────

@app.post("/api/email/sync", status_code=202)
def trigger_email_sync():
    db = _get_db()
    db.execute(
        "INSERT INTO background_tasks (task_type, job_id, status) VALUES ('email_sync', 0, 'queued')"
    )
    db.commit()
    task_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
    db.close()
    return {"task_id": task_id}


# ── GET /api/email/sync/status ────────────────────────────────────────────

@app.get("/api/email/sync/status")
def email_sync_status():
    db = _get_db()
    row = db.execute(
        "SELECT status, finished_at AS last_completed_at, error "
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
        "status":           row_dict["status"],
        "last_completed_at": row_dict["last_completed_at"],
        "error":            row_dict.get("error"),
    }


# ── POST /api/stage-signals/{id}/dismiss ─────────────────────────────────

@app.post("/api/stage-signals/{signal_id}/dismiss")
def dismiss_signal(signal_id: int):
    db = _get_db()
    result = db.execute(
        "UPDATE job_contacts SET suggestion_dismissed = 1 WHERE id = ?",
        (signal_id,),
    )
    db.commit()
    db.close()
    if result.rowcount == 0:
        raise HTTPException(404, "Signal not found")
    return {"ok": True}
```

- [ ] **Step 5: Run tests again — verify they pass**

```bash
/devl/miniconda3/envs/job-seeker/bin/pytest tests/test_dev_api_interviews.py -v
```

Expected: all tests PASS.

- [ ] **Step 6: Run the full test suite to check for regressions**

```bash
/devl/miniconda3/envs/job-seeker/bin/pytest tests/ -v --ignore=tests/e2e
```

Expected: existing tests still pass.

- [ ] **Step 7: Commit**

Note: `dev_api.py` is a symlink committed to the repo so that pytest can import the `dev_api` module by its Python-valid name. It points to `dev-api.py` (which uses a hyphen and is not directly importable). This is intentional.

```bash
cd /Library/Development/CircuitForge/peregrine/.worktrees/feature-vue-spa
git add dev-api.py dev_api.py tests/test_dev_api_interviews.py
git commit -m "feat(interviews): add stage signals, email sync, and dismiss endpoints to dev-api"
```

---

## Task 2: Store — StageSignal type + PipelineJob update

**Files:**
- Modify: `web/src/stores/interviews.ts`

### Context

Add and export the `StageSignal` interface before `PipelineJob`. Add `stage_signals: StageSignal[]` to `PipelineJob`. The `fetchAll()` function already maps data with `{ ...j }` — since the API now returns `stage_signals`, it will be included automatically. No other logic changes.

- [ ] **Step 1: Add the `StageSignal` export and update `PipelineJob`**

In `web/src/stores/interviews.ts`, insert the `StageSignal` interface before the `PipelineJob` interface and add `stage_signals` to `PipelineJob`:

```typescript
// ADD before PipelineJob:
export interface StageSignal {
  id: number              // job_contacts.id — used for POST /api/stage-signals/{id}/dismiss
  subject: string
  received_at: string     // ISO timestamp
  stage_signal: 'interview_scheduled' | 'positive_response' | 'offer_received' | 'survey_received' | 'rejected'
}

// MODIFY PipelineJob — add as last field:
  stage_signals: StageSignal[]  // undismissed signals, newest first
```

- [ ] **Step 2: Type-check**

```bash
cd /Library/Development/CircuitForge/peregrine/.worktrees/feature-vue-spa/web
npx vue-tsc --noEmit
```

Expected: 0 errors.

- [ ] **Step 3: Commit**

```bash
cd /Library/Development/CircuitForge/peregrine/.worktrees/feature-vue-spa
git add web/src/stores/interviews.ts
git commit -m "feat(interviews): export StageSignal interface; add stage_signals to PipelineJob"
```

---

## Task 3: MoveToSheet — preSelectedStage prop

**Files:**
- Modify: `web/src/components/MoveToSheet.vue`

### Context

`MoveToSheet` currently initializes `selectedStage` to `null`. Adding an optional `preSelectedStage` prop means: if it's provided, `selectedStage` starts with that value (the stage button appears pre-highlighted). The prop is typed `PipelineStage | undefined` and defaults to `undefined`. All existing non-signal `openMove()` calls pass no `preSelectedStage`, so the sheet defaults to null-selected as before.

- [ ] **Step 1: Add the `preSelectedStage` optional prop**

Open `web/src/components/MoveToSheet.vue`. The file currently has a bare `defineProps<{...}>()` call with no `withDefaults`. Simply add the optional field — no `withDefaults` wrapper needed since optional props default to `undefined` in Vue 3.

```typescript
// BEFORE (lines 6–9):
const props = defineProps<{
  currentStatus: string
  jobTitle:      string
}>()

// AFTER:
const props = defineProps<{
  currentStatus:     string
  jobTitle:          string
  preSelectedStage?: PipelineStage
}>()
```

`PipelineStage` is already imported on line 4 (`import type { PipelineStage } from '../stores/interviews'`) — no new import needed.

- [ ] **Step 2: Pre-select the stage on mount**

Replace the current `selectedStage` initialization (line 16):

```typescript
// BEFORE:
const selectedStage = ref<PipelineStage | null>(null)

// AFTER:
const selectedStage = ref<PipelineStage | null>(props.preSelectedStage ?? null)
```

- [ ] **Step 3: Type-check**

```bash
cd /Library/Development/CircuitForge/peregrine/.worktrees/feature-vue-spa/web
npx vue-tsc --noEmit
```

Expected: 0 errors.

- [ ] **Step 4: Commit**

```bash
cd /Library/Development/CircuitForge/peregrine/.worktrees/feature-vue-spa
git add web/src/components/MoveToSheet.vue
git commit -m "feat(interviews): add preSelectedStage prop to MoveToSheet"
```

---

## Task 4: InterviewCard — signal banner + move emit extension

**Files:**
- Modify: `web/src/components/InterviewCard.vue`

### Context

The card currently ends at its `</div>` close with no signal section. We add a signal banner block inside the card border (after existing content). The `move` emit is extended from `move: [jobId: number]` to `move: [jobId: number, preSelectedStage?: PipelineStage]` — the second arg is optional so existing `@move="openMove"` usages remain valid.

`StageSignal` and `PipelineStage` are imported from the store. The `job` prop already comes in as `PipelineJob` (post-Task 2 it now includes `stage_signals`).

**Signal → stage mapping (must be hardcoded; `rejected` → `'interview_rejected'`, not `'rejected'`)**:

```
interview_scheduled  → phone_screen,   amber,  "Move to Phone Screen"
positive_response    → phone_screen,   amber,  "Move to Phone Screen"
offer_received       → offer,          green,  "Move to Offer"
survey_received      → survey,         amber,  "Move to Survey"
rejected             → interview_rejected, red, "Mark Rejected"
```

**Multiple signals**: when `stage_signals.length > 1`, only the most recent banner shows. A `+N more` link below it toggles showing all signals. `sigExpanded` ref tracks this state.

**Dismiss**: optimistic — remove from local `job.stage_signals` array immediately, then `POST /api/stage-signals/{id}/dismiss`. No error recovery needed (optimistic per spec).

`overflow: hidden` on `.interview-card` must **not** clip the banner. Remove that rule — the card has a border already so there's no visual change. (The card currently has `overflow: hidden` which would hide the bottom banner border-radius.)

- [ ] **Step 1: Add signal helpers to the `<script setup>` block**

```typescript
// Update the existing vue import line to include `ref` if not already present:
import { ref, computed } from 'vue'
// (InterviewCard currently imports ref — verify it's there; add if missing)

import type { StageSignal, PipelineStage } from '../stores/interviews'
import { useApiFetch } from '../composables/useApi'

// Add to emits:
const emit = defineEmits<{
  move: [jobId: number, preSelectedStage?: PipelineStage]
  prep: [jobId: number]
}>()

// Signal state
const sigExpanded = ref(false)

interface SignalMeta {
  label: string
  stage: PipelineStage
  color: 'amber' | 'green' | 'red'
}

const SIGNAL_META: Record<StageSignal['stage_signal'], SignalMeta> = {
  interview_scheduled: { label: 'Move to Phone Screen', stage: 'phone_screen',       color: 'amber' },
  positive_response:   { label: 'Move to Phone Screen', stage: 'phone_screen',       color: 'amber' },
  offer_received:      { label: 'Move to Offer',        stage: 'offer',              color: 'green' },
  survey_received:     { label: 'Move to Survey',       stage: 'survey',             color: 'amber' },
  rejected:            { label: 'Mark Rejected',        stage: 'interview_rejected', color: 'red'   },
}

const COLOR_BG: Record<'amber' | 'green' | 'red', string> = {
  amber: 'rgba(245,158,11,0.08)',
  green: 'rgba(39,174,96,0.08)',
  red:   'rgba(192,57,43,0.08)',
}
const COLOR_BORDER: Record<'amber' | 'green' | 'red', string> = {
  amber: 'rgba(245,158,11,0.4)',
  green: 'rgba(39,174,96,0.4)',
  red:   'rgba(192,57,43,0.4)',
}

function visibleSignals(): StageSignal[] {
  const sigs = props.job.stage_signals ?? []
  return sigExpanded.value ? sigs : sigs.slice(0, 1)
}

async function dismissSignal(sig: StageSignal) {
  // Optimistic removal
  const arr = props.job.stage_signals
  const idx = arr.findIndex(s => s.id === sig.id)
  if (idx !== -1) arr.splice(idx, 1)
  await useApiFetch(`/api/stage-signals/${sig.id}/dismiss`, { method: 'POST' })
}
```

- [ ] **Step 2: Add signal banner template block**

Add the following inside the card template, after the existing card content div but still inside the `.interview-card` wrapper. The banner is gated with `v-if="job.stage_signals?.length"`.

```html
<!-- Signal banners -->
<template v-if="job.stage_signals?.length">
  <div
    v-for="sig in visibleSignals()"
    :key="sig.id"
    class="signal-banner"
    :style="{
      background: COLOR_BG[SIGNAL_META[sig.stage_signal].color],
      borderTopColor: COLOR_BORDER[SIGNAL_META[sig.stage_signal].color],
    }"
  >
    <span class="signal-label">
      📧 Email suggests: <strong>{{ SIGNAL_META[sig.stage_signal].label }}</strong>
    </span>
    <span class="signal-subject">{{ sig.subject.slice(0, 60) }}{{ sig.subject.length > 60 ? '…' : '' }}</span>
    <div class="signal-actions">
      <button
        class="btn-signal-move"
        @click.stop="emit('move', props.job.id, SIGNAL_META[sig.stage_signal].stage)"
        :aria-label="`${SIGNAL_META[sig.stage_signal].label} for ${props.job.title}`"
      >→ {{ SIGNAL_META[sig.stage_signal].label }}</button>
      <button
        class="btn-signal-dismiss"
        @click.stop="dismissSignal(sig)"
        aria-label="Dismiss signal"
      >✕</button>
    </div>
  </div>
  <button
    v-if="(job.stage_signals?.length ?? 0) > 1"
    class="btn-sig-expand"
    @click.stop="sigExpanded = !sigExpanded"
  >{{ sigExpanded ? '− less' : `+${(job.stage_signals?.length ?? 1) - 1} more` }}</button>
</template>
```

- [ ] **Step 3: Add signal banner CSS**

In the `<style scoped>` block, **remove** `overflow: hidden` from `.interview-card` and add:

```css
/* Remove: overflow: hidden from .interview-card */

.signal-banner {
  border-top: 1px solid transparent; /* color set inline */
  padding: 8px 12px;
  display: flex; flex-direction: column; gap: 4px;
}
.signal-label  { font-size: 0.82em; }
.signal-subject { font-size: 0.78em; color: var(--color-text-muted); }
.signal-actions { display: flex; gap: 6px; align-items: center; }
.btn-signal-move {
  background: var(--color-primary); color: #fff;
  border: none; border-radius: 4px; padding: 2px 8px; font-size: 0.78em; cursor: pointer;
}
.btn-signal-dismiss {
  background: none; border: none; color: var(--color-text-muted); font-size: 0.85em; cursor: pointer;
  padding: 2px 4px;
}
.btn-sig-expand {
  background: none; border: none; font-size: 0.75em; color: var(--color-info); cursor: pointer;
  padding: 4px 12px; text-align: left;
}
```

- [ ] **Step 4: Type-check**

```bash
cd /Library/Development/CircuitForge/peregrine/.worktrees/feature-vue-spa/web
npx vue-tsc --noEmit
```

Expected: 0 errors.

- [ ] **Step 5: Commit**

```bash
cd /Library/Development/CircuitForge/peregrine/.worktrees/feature-vue-spa
git add web/src/components/InterviewCard.vue
git commit -m "feat(interviews): add stage signal banners and extend move emit in InterviewCard"
```

---

## Task 5: InterviewsView — collapsible Applied section + email sync pill

**Files:**
- Modify: `web/src/views/InterviewsView.vue`

### Context

This task wires everything visible together. Three sub-features in one file:

**Feature A — Collapsible Applied section:**
- `appliedExpanded` ref from `localStorage` (key `peregrine.interviews.appliedExpanded`), default `false`
- `watch` to persist changes
- `appliedSignalCount` computed across `store.applied + store.survey`
- `.pre-list` section becomes a toggle: header row is always visible; body has `max-height: 0 / 800px` CSS transition
- `prefers-reduced-motion` disables transition

**Feature B — Email sync pill:**
- Local `SyncStatus` ref (not in Pinia store — view-only)
- On mount: call `GET /api/email/sync/status` to hydrate; start polling if already running
- `POST /api/email/sync` → if 503, set `not_configured` permanently for session; else poll every 3s
- Poll stop: status `completed` or `failed`; `onUnmounted` clears interval; on `completed`, call `store.fetchAll()`
- Elapsed-time label: `setInterval` ticks `now` ref every 60s; cleared on unmount

**Feature C — preSelectedStage wiring:**
- `openMove(jobId: number, preSelectedStage?: PipelineStage)` extended with second param
- `movePreSelected` ref stores the stage when opening
- `MoveToSheet` receives `:preSelectedStage="movePreSelected"`; cleared on close

- [ ] **Step 1: Add script-block additions**

In the `<script setup>` block, after the existing imports and before `const moveTarget`:

```typescript
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
// (ref, onMounted, onUnmounted already imported — just ensure computed + watch are included)

// ── Collapsible Applied section ────────────────────────────────────────────
const APPLIED_EXPANDED_KEY = 'peregrine.interviews.appliedExpanded'
const appliedExpanded = ref(localStorage.getItem(APPLIED_EXPANDED_KEY) === 'true')
watch(appliedExpanded, v => localStorage.setItem(APPLIED_EXPANDED_KEY, String(v)))

const appliedSignalCount = computed(() =>
  [...store.applied, ...store.survey]
    .reduce((n, job) => n + (job.stage_signals?.length ?? 0), 0)
)

// ── Email sync status ──────────────────────────────────────────────────────
interface SyncStatus {
  state: 'idle' | 'queued' | 'running' | 'completed' | 'failed' | 'not_configured'
  lastCompletedAt: string | null
  error: string | null
}

const syncStatus = ref<SyncStatus>({ state: 'idle', lastCompletedAt: null, error: null })
const now        = ref(Date.now())
let   syncPollId: ReturnType<typeof setInterval> | null = null
let   nowTickId:  ReturnType<typeof setInterval> | null = null

function elapsedLabel(isoTs: string | null): string {
  if (!isoTs) return ''
  const diffMs = now.value - new Date(isoTs).getTime()
  const mins   = Math.floor(diffMs / 60000)
  if (mins < 1)   return 'just now'
  if (mins < 60)  return `${mins}m ago`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24)   return `${hrs}h ago`
  return `${Math.floor(hrs / 24)}d ago`
}

async function fetchSyncStatus() {
  const { data } = await useApiFetch<{
    status: string; last_completed_at: string | null; error: string | null
  }>('/api/email/sync/status')
  if (!data) return
  syncStatus.value = {
    state:           data.status as SyncStatus['state'],
    lastCompletedAt: data.last_completed_at,
    error:           data.error,
  }
}

function startSyncPoll() {
  if (syncPollId) return
  syncPollId = setInterval(async () => {
    await fetchSyncStatus()
    if (syncStatus.value.state === 'completed' || syncStatus.value.state === 'failed') {
      clearInterval(syncPollId!); syncPollId = null
      if (syncStatus.value.state === 'completed') store.fetchAll()
    }
  }, 3000)
}

async function triggerSync() {
  if (syncStatus.value.state === 'queued' || syncStatus.value.state === 'running') return
  const { data, error } = await useApiFetch<{ task_id: number }>('/api/email/sync', { method: 'POST' })
  if (error) {
    if (error.kind === 'http' && error.status === 503) {
      // Email integration not configured — set permanently for this session
      syncStatus.value = { state: 'not_configured', lastCompletedAt: null, error: null }
    } else {
      // Transient error (network, server 5xx etc.) — show failed but allow retry
      syncStatus.value = { ...syncStatus.value, state: 'failed', error: error.kind === 'http' ? error.detail : error.message }
    }
    return
  }
  if (data) {
    syncStatus.value = { ...syncStatus.value, state: 'queued' }
    startSyncPoll()
  }
}
```

- [ ] **Step 2: Update `openMove` and add `movePreSelected` ref**

```typescript
// REPLACE existing:
const moveTarget = ref<PipelineJob | null>(null)
function openMove(jobId: number) {
  moveTarget.value = store.jobs.find(j => j.id === jobId) ?? null
}

// WITH:
const moveTarget      = ref<PipelineJob | null>(null)
const movePreSelected = ref<PipelineStage | undefined>(undefined)

function openMove(jobId: number, preSelectedStage?: PipelineStage) {
  moveTarget.value      = store.jobs.find(j => j.id === jobId) ?? null
  movePreSelected.value = preSelectedStage
}
```

- [ ] **Step 3: Update `onMounted` and `onUnmounted`**

```typescript
// REPLACE:
onMounted(async () => { await store.fetchAll(); document.addEventListener('keydown', onKeydown) })
onUnmounted(() => document.removeEventListener('keydown', onKeydown))

// WITH:
onMounted(async () => {
  await store.fetchAll()
  document.addEventListener('keydown', onKeydown)
  await fetchSyncStatus()
  if (syncStatus.value.state === 'queued' || syncStatus.value.state === 'running') {
    startSyncPoll()
  }
  nowTickId = setInterval(() => { now.value = Date.now() }, 60000)
})

onUnmounted(() => {
  document.removeEventListener('keydown', onKeydown)
  if (syncPollId) { clearInterval(syncPollId); syncPollId = null }
  if (nowTickId)  { clearInterval(nowTickId);  nowTickId  = null }
})
```

- [ ] **Step 4: Update the template — page header (email sync pill)**

Replace the existing `<header class="view-header">` block:

```html
<header class="view-header">
  <h1 class="view-title">Interviews</h1>
  <div class="header-actions">
    <!-- Email sync pill -->
    <button
      v-if="syncStatus.state === 'not_configured'"
      class="sync-pill sync-pill--muted"
      disabled
      aria-label="Email not configured"
    >📧 Email not configured</button>
    <button
      v-else-if="syncStatus.state === 'queued' || syncStatus.state === 'running'"
      class="sync-pill sync-pill--syncing"
      disabled
      aria-label="Syncing emails"
    >⏳ Syncing…</button>
    <button
      v-else-if="syncStatus.state === 'completed' || (syncStatus.state === 'idle' && syncStatus.lastCompletedAt)"
      class="sync-pill sync-pill--synced"
      @click="triggerSync"
      :aria-label="`Email synced ${elapsedLabel(syncStatus.lastCompletedAt)} — click to re-sync`"
    >📧 Synced {{ elapsedLabel(syncStatus.lastCompletedAt) }}</button>
    <button
      v-else-if="syncStatus.state === 'failed'"
      class="sync-pill sync-pill--failed"
      @click="triggerSync"
      aria-label="Sync failed — click to retry"
    >⚠ Sync failed</button>
    <button
      v-else
      class="sync-pill sync-pill--idle"
      @click="triggerSync"
      aria-label="Sync emails"
    >📧 Sync Emails</button>

    <button class="btn-refresh" @click="store.fetchAll()" :disabled="store.loading" aria-label="Refresh">
      {{ store.loading ? '⟳' : '↺' }}
    </button>
  </div>
</header>
```

- [ ] **Step 5: Update the template — collapsible pre-list section**

Replace the existing `<section class="pre-list" ...>` block (lines 132–152):

```html
<!-- Pre-list: Applied + Survey (collapsible) -->
<section class="pre-list" aria-label="Applied jobs">
  <button
    class="pre-list-toggle"
    @click="appliedExpanded = !appliedExpanded"
    :aria-expanded="appliedExpanded"
    aria-controls="pre-list-body"
  >
    <span class="pre-list-chevron" :class="{ 'is-expanded': appliedExpanded }">▶</span>
    <span class="pre-list-toggle-title">
      Applied
      <span class="pre-list-count">{{ store.applied.length + store.survey.length }}</span>
    </span>
    <span v-if="appliedSignalCount > 0" class="pre-list-signal-count">⚡ {{ appliedSignalCount }} signal{{ appliedSignalCount !== 1 ? 's' : '' }}</span>
  </button>

  <div
    id="pre-list-body"
    class="pre-list-body"
    :class="{ 'is-expanded': appliedExpanded }"
  >
    <div v-if="store.applied.length === 0 && store.survey.length === 0" class="pre-list-empty">
      <span class="empty-bird">🦅</span>
      <span>No applied jobs yet. <RouterLink to="/apply">Go to Apply</RouterLink> to submit applications.</span>
    </div>
    <template v-for="job in [...store.applied, ...store.survey]" :key="job.id">
      <div class="pre-list-row">
        <div class="pre-row-info">
          <span class="pre-row-title">{{ job.title }}</span>
          <span class="pre-row-company">{{ job.company }}</span>
          <span v-if="job.status === 'survey'" class="survey-badge">Survey</span>
        </div>
        <div class="pre-row-meta">
          <span v-if="daysSince(job.applied_at) !== null" class="pre-row-days">{{ daysSince(job.applied_at) }}d ago</span>
          <button class="btn-move-pre" @click="openMove(job.id)" :aria-label="`Move ${job.title}`">Move to… ›</button>
        </div>
      </div>
      <!-- Signal banners for pre-list rows -->
      <template v-if="job.stage_signals?.length">
        <div
          v-for="sig in (job.stage_signals ?? []).slice(0, sigExpandedIds.has(job.id) ? undefined : 1)"
      <!-- Note: inside <template>, Vue auto-unwraps refs — sigExpandedIds.has() is correct here (no .value needed) -->
          :key="sig.id"
          class="pre-signal-banner"
          :data-color="SIGNAL_META_PRE[sig.stage_signal]?.color"
        >
          <span class="signal-label">📧 Email suggests: <strong>{{ SIGNAL_META_PRE[sig.stage_signal]?.label }}</strong></span>
          <span class="signal-subject">{{ sig.subject.slice(0, 60) }}{{ sig.subject.length > 60 ? '…' : '' }}</span>
          <div class="signal-actions">
            <button
              class="btn-signal-move"
              @click="openMove(job.id, SIGNAL_META_PRE[sig.stage_signal]?.stage)"
            >→ {{ SIGNAL_META_PRE[sig.stage_signal]?.label }}</button>
            <button class="btn-signal-dismiss" @click="dismissPreSignal(job, sig)">✕</button>
          </div>
        </div>
        <button
          v-if="(job.stage_signals?.length ?? 0) > 1"
          class="btn-sig-expand"
          @click="togglePreSigExpand(job.id)"
        >{{ sigExpandedIds.has(job.id) ? '− less' : `+${(job.stage_signals?.length ?? 1) - 1} more` }}
        <!-- sigExpandedIds.has() is correct in <template> — Vue auto-unwraps the ref -->
        </button>
      </template>
    </template>
  </div>
</section>
```

Add the required script helpers for pre-list signals. Add in `<script setup>`:

```typescript
import type { StageSignal } from '../stores/interviews'
import { useApiFetch } from '../composables/useApi'

// Signal metadata (same map as InterviewCard — defined here for pre-list rows)
const SIGNAL_META_PRE = {
  interview_scheduled: { label: 'Move to Phone Screen', stage: 'phone_screen'       as PipelineStage, color: 'amber' },
  positive_response:   { label: 'Move to Phone Screen', stage: 'phone_screen'       as PipelineStage, color: 'amber' },
  offer_received:      { label: 'Move to Offer',        stage: 'offer'              as PipelineStage, color: 'green' },
  survey_received:     { label: 'Move to Survey',       stage: 'survey'             as PipelineStage, color: 'amber' },
  rejected:            { label: 'Mark Rejected',        stage: 'interview_rejected' as PipelineStage, color: 'red'   },
} as const

const sigExpandedIds = ref(new Set<number>())
// IMPORTANT: must reassign .value (not mutate in place) to trigger Vue reactivity
function togglePreSigExpand(jobId: number) {
  const next = new Set(sigExpandedIds.value)
  if (next.has(jobId)) next.delete(jobId)
  else next.add(jobId)
  sigExpandedIds.value = next
}

async function dismissPreSignal(job: PipelineJob, sig: StageSignal) {
  const idx = job.stage_signals.findIndex(s => s.id === sig.id)
  if (idx !== -1) job.stage_signals.splice(idx, 1)
  await useApiFetch(`/api/stage-signals/${sig.id}/dismiss`, { method: 'POST' })
}
```

- [ ] **Step 6: Update MoveToSheet binding in template**

```html
<!-- REPLACE: -->
<MoveToSheet
  v-if="moveTarget"
  :currentStatus="moveTarget.status"
  :jobTitle="`${moveTarget.title} at ${moveTarget.company}`"
  @move="onMove"
  @close="moveTarget = null"
/>

<!-- WITH: -->
<MoveToSheet
  v-if="moveTarget"
  :currentStatus="moveTarget.status"
  :jobTitle="`${moveTarget.title} at ${moveTarget.company}`"
  :preSelectedStage="movePreSelected"
  @move="onMove"
  @close="moveTarget = null; movePreSelected = undefined"
/>
```

- [ ] **Step 7: Add CSS for new elements**

Add to the `<style scoped>` block:

```css
/* Header actions */
.header-actions { display: flex; align-items: center; gap: var(--space-2); margin-left: auto; }

/* Email sync pill */
.sync-pill {
  border-radius: 999px; padding: 3px 10px; font-size: 0.78em; font-weight: 600; cursor: pointer;
  border: 1px solid transparent; transition: opacity 150ms;
}
.sync-pill:disabled { cursor: default; opacity: 0.8; }
.sync-pill--idle   { border-color: var(--color-border); background: none; color: var(--color-text-muted); }
.sync-pill--syncing { background: color-mix(in srgb, var(--color-info) 10%, var(--color-surface)); color: var(--color-info); border-color: color-mix(in srgb, var(--color-info) 30%, transparent); animation: pulse 1.5s ease-in-out infinite; }
.sync-pill--synced  { background: color-mix(in srgb, var(--color-success) 12%, var(--color-surface)); color: var(--color-success); border-color: color-mix(in srgb, var(--color-success) 30%, transparent); }
.sync-pill--failed  { background: color-mix(in srgb, var(--color-error) 10%, var(--color-surface)); color: var(--color-error); border-color: color-mix(in srgb, var(--color-error) 30%, transparent); }
.sync-pill--muted   { background: var(--color-surface-alt); color: var(--color-text-muted); border-color: var(--color-border-light); }
@keyframes pulse { 0%,100%{opacity:1} 50%{opacity:0.55} }

/* Collapsible pre-list toggle header */
.pre-list-toggle {
  display: flex; align-items: center; gap: var(--space-2); width: 100%;
  background: none; border: none; cursor: pointer; padding: var(--space-1) 0;
  font-size: 0.9rem; font-weight: 700; color: var(--color-text);
  text-align: left;
}
.pre-list-chevron { font-size: 0.7em; color: var(--color-text-muted); transition: transform 200ms; display: inline-block; }
.pre-list-chevron.is-expanded { transform: rotate(90deg); }
.pre-list-count {
  display: inline-block; background: var(--color-surface-raised); border-radius: 999px;
  padding: 1px 8px; font-size: 0.75em; font-weight: 700; margin-left: var(--space-1);
  color: var(--color-text-muted);
}
.pre-list-signal-count { margin-left: auto; font-size: 0.75em; font-weight: 700; color: #e67e22; }

/* Collapsible pre-list body */
.pre-list-body {
  max-height: 0;
  overflow: hidden;
  transition: max-height 300ms ease;
}
.pre-list-body.is-expanded { max-height: 800px; }
@media (prefers-reduced-motion: reduce) {
  .pre-list-body, .pre-list-chevron { transition: none; }
}

/* Pre-list signal banners */
.pre-signal-banner {
  padding: 8px 12px; border-radius: 6px; margin: 4px 0;
  border-top: 1px solid transparent;
  display: flex; flex-direction: column; gap: 4px;
}
.pre-signal-banner[data-color="amber"] { background: rgba(245,158,11,0.08); border-top-color: rgba(245,158,11,0.4); }
.pre-signal-banner[data-color="green"] { background: rgba(39,174,96,0.08);  border-top-color: rgba(39,174,96,0.4);  }
.pre-signal-banner[data-color="red"]   { background: rgba(192,57,43,0.08);  border-top-color: rgba(192,57,43,0.4);  }
```

- [ ] **Step 8: Type-check**

```bash
cd /Library/Development/CircuitForge/peregrine/.worktrees/feature-vue-spa/web
npx vue-tsc --noEmit
```

Expected: 0 errors.

- [ ] **Step 9: Commit**

```bash
cd /Library/Development/CircuitForge/peregrine/.worktrees/feature-vue-spa
git add web/src/views/InterviewsView.vue
git commit -m "feat(interviews): collapsible Applied section, email sync pill, pre-list signal banners"
```

---

## Task 6: Final verification

**Files:** none changed

- [ ] **Step 1: Run Python test suite**

```bash
cd /Library/Development/CircuitForge/peregrine/.worktrees/feature-vue-spa
/devl/miniconda3/envs/job-seeker/bin/pytest tests/ -v --ignore=tests/e2e
```

Expected: all tests pass.

- [ ] **Step 2: Full TypeScript type-check**

```bash
cd /Library/Development/CircuitForge/peregrine/.worktrees/feature-vue-spa/web
npx vue-tsc --noEmit
```

Expected: 0 errors.

- [ ] **Step 3: Build check**

```bash
cd /Library/Development/CircuitForge/peregrine/.worktrees/feature-vue-spa/web
npm run build
```

Expected: build succeeds with 0 errors.

- [ ] **Step 4: Manual smoke-test checklist** (run dev server: `npm run dev`)

- [ ] Interviews page loads; Applied section is collapsed by default
- [ ] Clicking the header row expands/collapses with animation
- [ ] Collapse state persists on page reload (`localStorage` key `peregrine.interviews.appliedExpanded`)
- [ ] `⚡ N signals` count shown in collapsed header when signals exist
- [ ] Email sync pill shows "📧 Sync Emails" on first load
- [ ] Clicking the pill triggers a POST; pill shows "⏳ Syncing…" while polling
- [ ] Stage signal banners appear at the bottom of InterviewCard in kanban columns
- [ ] `[→ Move]` button on a signal banner opens MoveToSheet with the correct stage pre-selected
- [ ] `[✕]` on a banner optimistically removes it (no page reload needed)
- [ ] `+N more` / `− less` toggle works for jobs with multiple signals
