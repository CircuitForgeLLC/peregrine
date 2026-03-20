# Signal Banner Redesign — Expandable Email + Re-classification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expand signal banners to show full email body, add inline re-classification chips, and remove single-click stage advancement (always route through MoveToSheet).

**Architecture:** Backend adds `body`/`from_addr` to the signal query and a new `POST /api/stage-signals/{id}/reclassify` endpoint. The `StageSignal` TypeScript interface gains two nullable fields. Both `InterviewCard.vue` (kanban) and `InterviewsView.vue` (pre-list) get an expand toggle, body display, and six re-classification chips. Optimistic local mutation drives reactive re-labeling; neutral triggers a two-call dismiss path to preserve Avocet training signal.

**Tech Stack:** FastAPI (Python), SQLite, Vue 3, TypeScript, Pinia, `useApiFetch` composable

**Spec:** `docs/superpowers/specs/2026-03-19-signal-banner-reclassify-design.md`

---

## File Map

| File | Action |
|---|---|
| `dev-api.py` | Add `body, from_addr` to signal SELECT; add `reclassify_signal` endpoint |
| `tests/test_dev_api_interviews.py` | Add `body`/`from_addr` columns to fixture; extend existing signal test; add 3 reclassify tests |
| `web/src/stores/interviews.ts` | Add `body: string \| null`, `from_addr: string \| null` to `StageSignal` |
| `web/src/components/InterviewCard.vue` | `bodyExpanded` ref; expand toggle button; body+from_addr display; 6 reclassify chips; `reclassifySignal()` |
| `web/src/views/InterviewsView.vue` | `bodyExpandedMap` ref; `toggleBodyExpand()`; same body display + chips for pre-list rows |

---

## Task 1: Backend — body/from_addr fields + reclassify endpoint

**Files:**
- Modify: `dev-api.py` (lines ~309–325 signal SELECT + append block; after line 388 for new endpoint)
- Modify: `tests/test_dev_api_interviews.py` (fixture schema + 4 test changes)

### Step 1.1: Write the four failing tests

Add to `tests/test_dev_api_interviews.py`:

```python
# ── Body/from_addr in signal response ─────────────────────────────────────

def test_interviews_signal_includes_body_and_from_addr(client):
    resp = client.get("/api/interviews")
    assert resp.status_code == 200
    jobs = {j["id"]: j for j in resp.json()}
    sig = jobs[1]["stage_signals"][0]
    # Fields must exist (may be None when DB column is NULL)
    assert "body" in sig
    assert "from_addr" in sig


# ── POST /api/stage-signals/{id}/reclassify ────────────────────────────────

def test_reclassify_signal_updates_label(client, tmp_db):
    resp = client.post("/api/stage-signals/10/reclassify",
                       json={"stage_signal": "positive_response"})
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}
    con = sqlite3.connect(tmp_db)
    row = con.execute(
        "SELECT stage_signal FROM job_contacts WHERE id = 10"
    ).fetchone()
    con.close()
    assert row[0] == "positive_response"


def test_reclassify_signal_invalid_label(client):
    resp = client.post("/api/stage-signals/10/reclassify",
                       json={"stage_signal": "not_a_real_label"})
    assert resp.status_code == 400


def test_reclassify_signal_404_for_missing_id(client):
    resp = client.post("/api/stage-signals/9999/reclassify",
                       json={"stage_signal": "neutral"})
    assert resp.status_code == 404
```

- [ ] Add the four test functions above to `tests/test_dev_api_interviews.py`

### Step 1.2: Also extend `test_interviews_includes_stage_signals` to assert body/from_addr

The existing test (line 64) asserts `id`, `stage_signal`, and `subject`. Add assertions for the two new fields after the existing `assert signals[0]["id"] == 10` line:

```python
    assert "body" in signals[0]
    assert "from_addr" in signals[0]
```

- [ ] Add those two lines inside `test_interviews_includes_stage_signals`, after `assert signals[0]["id"] == 10`

### Step 1.3: Update the fixture to include body and from_addr columns

The `job_contacts` CREATE TABLE in the `tmp_db` fixture is missing `body TEXT` and `from_addr TEXT`. The fixture test-side schema must match the real DB.

Replace the `job_contacts` CREATE TABLE block (currently `id, job_id, subject, received_at, stage_signal, suggestion_dismissed`) with:

```sql
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
```

- [ ] Update the `tmp_db` fixture's `job_contacts` schema to add `body TEXT` and `from_addr TEXT`

### Step 1.4: Run tests to confirm they all fail as expected

```bash
cd /Library/Development/CircuitForge/peregrine/.worktrees/feature-vue-spa
/devl/miniconda3/envs/job-seeker/bin/pytest tests/test_dev_api_interviews.py -v
```

Expected: 5 new/modified tests FAIL (body/from_addr not in response; reclassify endpoint 404s); existing 8 tests still PASS.

- [ ] Run and confirm

### Step 1.5: Update `dev-api.py` — add body/from_addr to signal SELECT and append

Find the signal SELECT query (line ~309). Replace:

```python
        sig_rows = db.execute(
            f"SELECT id, job_id, subject, received_at, stage_signal "
```

With:

```python
        sig_rows = db.execute(
            f"SELECT id, job_id, subject, received_at, stage_signal, body, from_addr "
```

Then extend the `signals_by_job` append dict (line ~319). Replace:

```python
            signals_by_job[sr["job_id"]].append({
                "id":           sr["id"],
                "subject":      sr["subject"],
                "received_at":  sr["received_at"],
                "stage_signal": sr["stage_signal"],
            })
```

With:

```python
            signals_by_job[sr["job_id"]].append({
                "id":           sr["id"],
                "subject":      sr["subject"],
                "received_at":  sr["received_at"],
                "stage_signal": sr["stage_signal"],
                "body":         sr["body"],
                "from_addr":    sr["from_addr"],
            })
```

- [ ] Apply both edits to `dev-api.py`

### Step 1.6: Add the reclassify endpoint to `dev-api.py`

After the `dismiss_signal` endpoint (around line 388), add:

```python
# ── POST /api/stage-signals/{id}/reclassify ──────────────────────────────

VALID_SIGNAL_LABELS = {
    'interview_scheduled', 'offer_received', 'rejected',
    'positive_response', 'survey_received', 'neutral',
    'event_rescheduled', 'unrelated', 'digest',
}

class ReclassifyBody(BaseModel):
    stage_signal: str

@app.post("/api/stage-signals/{signal_id}/reclassify")
def reclassify_signal(signal_id: int, body: ReclassifyBody):
    if body.stage_signal not in VALID_SIGNAL_LABELS:
        raise HTTPException(400, f"Invalid label: {body.stage_signal}")
    db = _get_db()
    result = db.execute(
        "UPDATE job_contacts SET stage_signal = ? WHERE id = ?",
        (body.stage_signal, signal_id),
    )
    rowcount = result.rowcount
    db.commit()
    db.close()
    if rowcount == 0:
        raise HTTPException(404, "Signal not found")
    return {"ok": True}
```

Note: `BaseModel` is already imported via `from pydantic import BaseModel` at the top of the file — check before adding a duplicate import.

- [ ] Add the endpoint and `VALID_SIGNAL_LABELS` / `ReclassifyBody` to `dev-api.py` after the dismiss endpoint

### Step 1.7: Run the full test suite to verify all tests pass

```bash
/devl/miniconda3/envs/job-seeker/bin/pytest tests/test_dev_api_interviews.py -v
```

Expected: all tests PASS (13 total: 8 existing + 5 new/extended).

- [ ] Run and confirm

### Step 1.8: Commit

```bash
cd /Library/Development/CircuitForge/peregrine/.worktrees/feature-vue-spa
git add dev-api.py tests/test_dev_api_interviews.py
git commit -m "feat(signals): add body/from_addr to signal query; add reclassify endpoint"
```

- [ ] Commit

---

## Task 2: Store — add body/from_addr to StageSignal interface

**Files:**
- Modify: `web/src/stores/interviews.ts` (lines 5–10, `StageSignal` interface)

**Why this is its own task:** Both `InterviewCard.vue` and `InterviewsView.vue` import `StageSignal`. TypeScript will error on `sig.body` / `sig.from_addr` until the interface is updated. Committing the type change first keeps Tasks 3 and 4 independently compilable.

### Step 2.1: Update `StageSignal` in `web/src/stores/interviews.ts`

Replace:

```typescript
export interface StageSignal {
  id: number              // job_contacts.id — used for POST /api/stage-signals/{id}/dismiss
  subject: string
  received_at: string     // ISO timestamp
  stage_signal: 'interview_scheduled' | 'positive_response' | 'offer_received' | 'survey_received' | 'rejected'
}
```

With:

```typescript
export interface StageSignal {
  id: number              // job_contacts.id — used for POST /api/stage-signals/{id}/dismiss
  subject: string
  received_at: string     // ISO timestamp
  stage_signal: 'interview_scheduled' | 'positive_response' | 'offer_received' | 'survey_received' | 'rejected'
  body: string | null     // email body text; null if not available
  from_addr: string | null // sender address; null if not available
}
```

- [ ] Edit `web/src/stores/interviews.ts`

### Step 2.2: Verify TypeScript compiles cleanly

```bash
cd /Library/Development/CircuitForge/peregrine/.worktrees/feature-vue-spa/web
npx vue-tsc --noEmit
```

Expected: 0 errors (the new fields are nullable so no existing code should break).

- [ ] Run and confirm

### Step 2.3: Commit

```bash
cd /Library/Development/CircuitForge/peregrine/.worktrees/feature-vue-spa
git add web/src/stores/interviews.ts
git commit -m "feat(signals): add body and from_addr to StageSignal interface"
```

- [ ] Commit

---

## Task 3: InterviewCard.vue — expand toggle, body display, reclassify chips

**Files:**
- Modify: `web/src/components/InterviewCard.vue`

**Context:** This component is the kanban card. It shows one signal by default, and a `+N more` button for additional signals. The `bodyExpanded` ref is per-card (not per-signal) because at most one signal is visible in collapsed state.

### Step 3.1: Add `bodyExpanded` ref and `reclassifySignal` function

In the `<script setup>` section, after the `dismissSignal` function, add:

```typescript
const bodyExpanded = ref(false)

// Re-classify chips — neutral triggers two-call dismiss path
const RECLASSIFY_CHIPS = [
  { label: '🟡 Interview', value: 'interview_scheduled' as const },
  { label: '✅ Positive',  value: 'positive_response'   as const },
  { label: '🟢 Offer',     value: 'offer_received'      as const },
  { label: '📋 Survey',    value: 'survey_received'     as const },
  { label: '✖ Rejected',   value: 'rejected'            as const },
  { label: '— Neutral',    value: 'neutral' },
] as const

async function reclassifySignal(sig: StageSignal, newLabel: string) {
  if (newLabel === 'neutral') {
    // Optimistic removal — neutral signals are dismissed
    const arr = props.job.stage_signals
    const idx = arr.findIndex(s => s.id === sig.id)
    if (idx !== -1) arr.splice(idx, 1)
    // Two-call path: persist corrected label then dismiss (Avocet training hook)
    await useApiFetch(`/api/stage-signals/${sig.id}/reclassify`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ stage_signal: 'neutral' }),
    })
    await useApiFetch(`/api/stage-signals/${sig.id}/dismiss`, { method: 'POST' })
  } else {
    // Optimistic local re-label — Vue 3 proxy tracks the mutation
    sig.stage_signal = newLabel as StageSignal['stage_signal']
    await useApiFetch(`/api/stage-signals/${sig.id}/reclassify`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ stage_signal: newLabel }),
    })
  }
}
```

- [ ] Add `bodyExpanded`, `RECLASSIFY_CHIPS`, and `reclassifySignal` to the script section

### Step 3.2: Update the signal banner template

Find the signal banner `<template v-if="job.stage_signals?.length">` block (lines ~131–163). Replace the entire block with:

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
        <div class="signal-header">
          <span class="signal-label">
            📧 <strong>{{ SIGNAL_META[sig.stage_signal].label.replace('Move to ', '') }}</strong>
          </span>
          <span class="signal-subject">{{ sig.subject.slice(0, 60) }}{{ sig.subject.length > 60 ? '…' : '' }}</span>
          <div class="signal-header-actions">
            <button class="btn-signal-read" @click.stop="bodyExpanded = !bodyExpanded">
              {{ bodyExpanded ? '▾ Hide' : '▸ Read' }}
            </button>
            <button
              class="btn-signal-move"
              @click.stop="emit('move', props.job.id, SIGNAL_META[sig.stage_signal].stage)"
              :aria-label="`${SIGNAL_META[sig.stage_signal].label} for ${props.job.title}`"
            >→ Move</button>
            <button
              class="btn-signal-dismiss"
              @click.stop="dismissSignal(sig)"
              aria-label="Dismiss signal"
            >✕</button>
          </div>
        </div>
        <!-- Expanded body + reclassify chips -->
        <div v-if="bodyExpanded" class="signal-body-expanded">
          <div v-if="sig.from_addr" class="signal-from">From: {{ sig.from_addr }}</div>
          <div v-if="sig.body" class="signal-body-text">{{ sig.body }}</div>
          <div v-else class="signal-body-empty">No email body available.</div>
          <div class="signal-reclassify">
            <span class="signal-reclassify-label">Re-classify:</span>
            <button
              v-for="chip in RECLASSIFY_CHIPS"
              :key="chip.value"
              class="btn-chip"
              :class="{ 'btn-chip-active': sig.stage_signal === chip.value }"
              @click.stop="reclassifySignal(sig, chip.value)"
            >{{ chip.label }}</button>
          </div>
        </div>
      </div>
      <button
        v-if="(job.stage_signals?.length ?? 0) > 1"
        class="btn-sig-expand"
        @click.stop="sigExpanded = !sigExpanded"
      >{{ sigExpanded ? '− less' : `+${(job.stage_signals?.length ?? 1) - 1} more` }}</button>
    </template>
```

- [ ] Replace the signal banner template block

### Step 3.3: Add CSS for new elements

After the existing `.btn-signal-dismiss` rule, add:

```css
.btn-signal-read {
  background: none; border: none; color: var(--color-text-muted); font-size: 0.82em;
  cursor: pointer; padding: 2px 6px; white-space: nowrap;
}
.signal-header {
  display: flex; align-items: center; gap: 8px; flex-wrap: wrap;
}
.signal-header-actions {
  margin-left: auto; display: flex; gap: 6px; align-items: center;
}
.signal-body-expanded {
  margin-top: 8px; font-size: 0.8em; border-top: 1px dashed var(--color-border);
  padding-top: 8px;
}
.signal-from {
  color: var(--color-text-muted); margin-bottom: 4px;
}
.signal-body-text {
  white-space: pre-wrap; color: var(--color-text); line-height: 1.5;
  max-height: 200px; overflow-y: auto;
}
.signal-body-empty {
  color: var(--color-text-muted); font-style: italic;
}
.signal-reclassify {
  display: flex; gap: 6px; flex-wrap: wrap; align-items: center; margin-top: 8px;
}
.signal-reclassify-label {
  font-size: 0.75em; color: var(--color-text-muted);
}
.btn-chip {
  background: var(--color-surface); color: var(--color-text-muted);
  border: 1px solid var(--color-border); border-radius: 4px;
  padding: 2px 7px; font-size: 0.75em; cursor: pointer;
}
.btn-chip:hover {
  background: var(--color-hover);
}
.btn-chip-active {
  background: var(--color-primary-muted, #e8f0ff);
  color: var(--color-primary); border-color: var(--color-primary);
  font-weight: 600;
}
```

- [ ] Add the CSS rules to the `<style>` section of `InterviewCard.vue`

### Step 3.4: Verify TypeScript compiles cleanly

```bash
cd /Library/Development/CircuitForge/peregrine/.worktrees/feature-vue-spa/web
npx vue-tsc --noEmit
```

Expected: 0 errors.

- [ ] Run and confirm

### Step 3.5: Commit

```bash
cd /Library/Development/CircuitForge/peregrine/.worktrees/feature-vue-spa
git add web/src/components/InterviewCard.vue
git commit -m "feat(signals): expandable body + reclassify chips in InterviewCard"
```

- [ ] Commit

---

## Task 4: InterviewsView.vue — expand toggle, body display, reclassify chips (pre-list)

**Files:**
- Modify: `web/src/views/InterviewsView.vue`

**Context:** This view shows signal banners in the "Applied" pre-list rows. Unlike InterviewCard (one `bodyExpanded` per card), here each signal row can be independently expanded. Use `ref<Record<number, boolean>>` keyed by `sig.id` with spread-copy for guaranteed Vue 3 reactivity (same pattern as `sigExpandedIds` but for body expansion).

### Step 4.1: Add `bodyExpandedMap`, `toggleBodyExpand`, and `reclassifyPreSignal`

In the script section, after the `dismissPreSignal` function (line ~59–63), add:

```typescript
const bodyExpandedMap = ref<Record<number, boolean>>({})

function toggleBodyExpand(sigId: number) {
  bodyExpandedMap.value = { ...bodyExpandedMap.value, [sigId]: !bodyExpandedMap.value[sigId] }
}

const PRE_RECLASSIFY_CHIPS = [
  { label: '🟡 Interview', value: 'interview_scheduled' as const },
  { label: '✅ Positive',  value: 'positive_response'   as const },
  { label: '🟢 Offer',     value: 'offer_received'      as const },
  { label: '📋 Survey',    value: 'survey_received'     as const },
  { label: '✖ Rejected',   value: 'rejected'            as const },
  { label: '— Neutral',    value: 'neutral' },
] as const

async function reclassifyPreSignal(job: PipelineJob, sig: StageSignal, newLabel: string) {
  if (newLabel === 'neutral') {
    // Optimistic removal
    const idx = job.stage_signals.findIndex(s => s.id === sig.id)
    if (idx !== -1) job.stage_signals.splice(idx, 1)
    await useApiFetch(`/api/stage-signals/${sig.id}/reclassify`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ stage_signal: 'neutral' }),
    })
    await useApiFetch(`/api/stage-signals/${sig.id}/dismiss`, { method: 'POST' })
  } else {
    sig.stage_signal = newLabel as StageSignal['stage_signal']
    await useApiFetch(`/api/stage-signals/${sig.id}/reclassify`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ stage_signal: newLabel }),
    })
  }
}
```

- [ ] Add `bodyExpandedMap`, `toggleBodyExpand`, `PRE_RECLASSIFY_CHIPS`, and `reclassifyPreSignal` to the script section

### Step 4.2: Update the pre-list signal banner template

Find the `<!-- Signal banners for pre-list rows -->` block (lines ~319–342). Replace it with:

```html
          <!-- Signal banners for pre-list rows -->
          <template v-if="job.stage_signals?.length">
            <div
              v-for="sig in (job.stage_signals ?? []).slice(0, sigExpandedIds.has(job.id) ? undefined : 1)"
              :key="sig.id"
              class="pre-signal-banner"
              :data-color="SIGNAL_META_PRE[sig.stage_signal]?.color"
            >
              <div class="signal-header">
                <span class="signal-label">📧 <strong>{{ SIGNAL_META_PRE[sig.stage_signal]?.label?.replace('Move to ', '') ?? sig.stage_signal }}</strong></span>
                <span class="signal-subject">{{ sig.subject.slice(0, 60) }}{{ sig.subject.length > 60 ? '…' : '' }}</span>
                <div class="signal-header-actions">
                  <button class="btn-signal-read" @click="toggleBodyExpand(sig.id)">
                    {{ bodyExpandedMap[sig.id] ? '▾ Hide' : '▸ Read' }}
                  </button>
                  <button
                    class="btn-signal-move"
                    @click="openMove(job.id, SIGNAL_META_PRE[sig.stage_signal]?.stage)"
                  >→ Move</button>
                  <button class="btn-signal-dismiss" @click="dismissPreSignal(job, sig)">✕</button>
                </div>
              </div>
              <!-- Expanded body + reclassify chips -->
              <div v-if="bodyExpandedMap[sig.id]" class="signal-body-expanded">
                <div v-if="sig.from_addr" class="signal-from">From: {{ sig.from_addr }}</div>
                <div v-if="sig.body" class="signal-body-text">{{ sig.body }}</div>
                <div v-else class="signal-body-empty">No email body available.</div>
                <div class="signal-reclassify">
                  <span class="signal-reclassify-label">Re-classify:</span>
                  <button
                    v-for="chip in PRE_RECLASSIFY_CHIPS"
                    :key="chip.value"
                    class="btn-chip"
                    :class="{ 'btn-chip-active': sig.stage_signal === chip.value }"
                    @click="reclassifyPreSignal(job, sig, chip.value)"
                  >{{ chip.label }}</button>
                </div>
              </div>
            </div>
            <button
              v-if="(job.stage_signals?.length ?? 0) > 1"
              class="btn-sig-expand"
              @click="togglePreSigExpand(job.id)"
            >{{ sigExpandedIds.has(job.id) ? '− less' : `+${(job.stage_signals?.length ?? 1) - 1} more` }}</button>
          </template>
```

- [ ] Replace the pre-list signal banner template block

### Step 4.3: Add CSS for new elements

The `InterviewsView.vue` `<style>` section already has `.btn-signal-dismiss`, `.btn-signal-move`, and `.signal-actions`. Add new rules that do NOT conflict with existing ones — use `.signal-header-actions` (not `.signal-actions`) for the right-aligned button group:

```css
.btn-signal-read {
  background: none; border: none; color: var(--color-text-muted); font-size: 0.82em;
  cursor: pointer; padding: 2px 6px; white-space: nowrap;
}
.signal-header {
  display: flex; align-items: center; gap: 8px; flex-wrap: wrap;
}
.signal-header-actions {
  margin-left: auto; display: flex; gap: 6px; align-items: center;
}
.signal-body-expanded {
  margin-top: 8px; font-size: 0.8em; border-top: 1px dashed var(--color-border);
  padding-top: 8px;
}
.signal-from {
  color: var(--color-text-muted); margin-bottom: 4px;
}
.signal-body-text {
  white-space: pre-wrap; color: var(--color-text); line-height: 1.5;
  max-height: 200px; overflow-y: auto;
}
.signal-body-empty {
  color: var(--color-text-muted); font-style: italic;
}
.signal-reclassify {
  display: flex; gap: 6px; flex-wrap: wrap; align-items: center; margin-top: 8px;
}
.signal-reclassify-label {
  font-size: 0.75em; color: var(--color-text-muted);
}
.btn-chip {
  background: var(--color-surface); color: var(--color-text-muted);
  border: 1px solid var(--color-border); border-radius: 4px;
  padding: 2px 7px; font-size: 0.75em; cursor: pointer;
}
.btn-chip:hover {
  background: var(--color-hover);
}
.btn-chip-active {
  background: var(--color-primary-muted, #e8f0ff);
  color: var(--color-primary); border-color: var(--color-primary);
  font-weight: 600;
}
```

- [ ] Add CSS to the `<style>` section of `InterviewsView.vue`

### Step 4.4: Verify TypeScript compiles cleanly

```bash
cd /Library/Development/CircuitForge/peregrine/.worktrees/feature-vue-spa/web
npx vue-tsc --noEmit
```

Expected: 0 errors.

- [ ] Run and confirm

### Step 4.5: Commit

```bash
cd /Library/Development/CircuitForge/peregrine/.worktrees/feature-vue-spa
git add web/src/views/InterviewsView.vue
git commit -m "feat(signals): expandable body + reclassify chips in InterviewsView pre-list"
```

- [ ] Commit

---

## Task 5: Final verification

### Step 5.1: Run full Python test suite

```bash
/devl/miniconda3/envs/job-seeker/bin/pytest tests/ -v
```

Expected: all tests pass (509 existing + 5 new = 514 total, or whatever the total becomes).

- [ ] Run and confirm

### Step 5.2: Run TypeScript type check

```bash
cd /Library/Development/CircuitForge/peregrine/.worktrees/feature-vue-spa/web
npx vue-tsc --noEmit
```

Expected: 0 errors.

- [ ] Run and confirm

### Step 5.3: Run production build

```bash
cd /Library/Development/CircuitForge/peregrine/.worktrees/feature-vue-spa/web
npm run build
```

Expected: build completes with 0 errors and 0 type errors.

- [ ] Run and confirm

---

## Implementation Notes

### `[→ Move]` button label

The spec says keep `[→ Move]` (no rename). The template above uses `→ Move` for both InterviewCard and InterviewsView pre-list rows. The old text was `→ {{ SIGNAL_META[sig.stage_signal].label }}` which was verbose and confusing. The spec says "pre-selection hint is still useful; MoveToSheet confirm is the safeguard" — so `→ Move` is correct: it still opens MoveToSheet with the pre-selected stage.

### `signal-header` and `signal-header-actions` layout note

The existing `.signal-banner` in both files has `display: flex; align-items: center`. The `.signal-header` inner div creates a horizontal flex row for label + subject + action buttons. The action button group uses `.signal-header-actions` (NOT `.signal-actions`) to avoid conflicting with the existing `.signal-actions` rule already present in both Vue files. The existing `.signal-actions` rule does not include `margin-left: auto`, which is what pushes the buttons to the right — `.signal-header-actions` adds that. Do not merge or rename `.signal-actions`; leave it in place for any existing usages.

### Neutral chip type safety

`RECLASSIFY_CHIPS` includes `'neutral'` which is not in `StageSignal['stage_signal']` union. The `reclassifySignal` function handles neutral as a special case before attempting the `as StageSignal['stage_signal']` cast, so TypeScript is satisfied. The `chip.value` in the template is typed as the union of all chip values; the `btn-chip-active` binding uses `sig.stage_signal === chip.value` which TypeScript allows since it's a `===` comparison.

### Reactive re-labeling (spec §"Reactive re-labeling")

`sig.stage_signal = newLabel as StageSignal['stage_signal']` mutates the Pinia reactive proxy directly. This works because `sig` is accessed through the Pinia store's reactive object chain — Vue 3 wraps nested objects on access. This would silently fail only if `job` or `stage_signals` were marked `toRaw()` or `markRaw()`, which they are not. The `SIGNAL_META[sig.stage_signal]` lookups in the template will reactively re-evaluate when `sig.stage_signal` changes.

### `bodyExpandedMap` in InterviewsView

Uses `ref<Record<number, boolean>>({})` (not `Map`) because Vue 3 can track property mutations on plain objects held in a `ref` deeply. The spread-copy pattern `{ ...bodyExpandedMap.value, [sigId]: !bodyExpandedMap.value[sigId] }` is the guaranteed-safe approach (same principle as the `sigExpandedIds` Set copy-on-write pattern already in the file).
