# Interviews Page — Improvements Design

**Date:** 2026-03-19
**Status:** Approved — ready for implementation planning

---

## Goal

Add three improvements to the Vue SPA Interviews page:
1. Collapse the Applied/Survey pre-kanban strip so the kanban board is immediately visible
2. Email sync status pill in the page header
3. Stage signal banners on job cards — in both the Applied/Survey pre-list rows and the kanban `InterviewCard` components

---

## Decisions Made

| Decision | Choice |
|---|---|
| Applied section default state | Collapsed |
| Collapse persistence | `localStorage` key `peregrine.interviews.appliedExpanded` |
| Signal visibility when collapsed | `⚡ N signals` count shown in collapsed header |
| Email sync placement | Page header status pill (right side, beside ↻ Refresh) |
| Signal banner placement | Applied/Survey pre-list rows AND InterviewCard kanban cards |
| Signal data loading | Batched with `GET /api/interviews` response (no N+1 requests) |
| Multiple signals | Show most recent; `+N more` expands rest inline; click again to collapse |
| Signal dismiss | Optimistic removal; `POST /api/stage-signals/{id}/dismiss` |
| MoveToSheet pre-selection | New optional `preSelectedStage?: PipelineStage` prop on MoveToSheet |
| Email not configured | `POST /api/email/sync` returns 503; pill shows muted `📧 Email not configured` (non-interactive) |
| Polling teardown | Stop polling on `onUnmounted`; hydrate status from `GET /api/email/sync/status` on mount |

---

## Feature 1: Applied Section Collapsible

### Behavior

The pre-kanban "Applied + Survey" strip (currently rendered above the three kanban columns) becomes a toggle section. Survey jobs remain in the same section.

**Default state:** collapsed on page load, unless `localStorage` indicates the user previously expanded it.

**Header row (always visible):**

```
▶  Applied   [12]   ·   ⚡ 2 signals          (collapsed)
▼  Applied   [12]   ·   ⚡ 2 signals          (expanded)
```

- Arrow chevron toggles on click (anywhere on the header row)
- Count badge: total applied + survey jobs
- Signal indicator: `⚡ N signals` in amber — shown only when there are undismissed signals across applied/survey jobs. Hidden when N = 0.
- CSS `max-height` transition: transition from `0` to `800px` (safe cap — enough for any real list). `prefers-reduced-motion`: instant toggle (no transition).

**Expanded state:** renders the existing applied/survey job rows with signal banners (see Feature 3).

### localStorage

```typescript
const APPLIED_EXPANDED_KEY = 'peregrine.interviews.appliedExpanded'
// default: false (collapsed). localStorage returns null on first load → defaults to false.
const appliedExpanded = ref(localStorage.getItem(APPLIED_EXPANDED_KEY) === 'true')
watch(appliedExpanded, v => localStorage.setItem(APPLIED_EXPANDED_KEY, String(v)))
```

`localStorage.getItem(...)` returns `null` on first load; `null === 'true'` is `false`, so the section starts collapsed correctly.

---

## Feature 2: Email Sync Status Pill

### Placement

Right side of the Interviews page header, alongside the existing ↻ Refresh button.

### States

| API `status` + `last_completed_at` | Pill appearance | Interaction |
|---|---|---|
| No API call yet / `idle` + `null` | `📧 Sync Emails` (outlined button) | Click → trigger sync |
| `idle` + timestamp exists | `📧 Synced 4m ago` (green pill) | Click → re-trigger sync |
| `queued` or `running` | `⏳ Syncing…` (disabled, pulse animation) | Non-interactive |
| `completed` | `📧 Synced 4m ago` (green pill) | Click → re-trigger sync |
| `failed` | `⚠ Sync failed` (amber pill) | Click → retry |
| 503 from `POST /api/email/sync` | `📧 Email not configured` (muted, non-interactive) | None |

The elapsed-time label ("4m ago") is computed from `lastSyncedAt` using a reactive tick. A `setInterval` updates a `now` ref every 60 seconds in `onMounted`, cleared in `onUnmounted`.

### Lifecycle

**On mount:** call `GET /api/email/sync/status` once to hydrate pill state. If status is `queued` or `running` (sync was in progress before navigation), start polling immediately.

**On sync trigger:** `POST /api/email/sync` → if 503, set pill to "Email not configured" permanently for the session. Otherwise poll `GET /api/email/sync/status` every 3 seconds.

**Polling stop conditions:** status becomes `completed` or `failed`, OR component unmounts (`onUnmounted` clears the interval). On `completed`, re-fetch the interview job list to pick up new signals.

### API

**Trigger sync:**
```
POST /api/email/sync
→ 202 { task_id: number }        (sync queued)
→ 503 { detail: "Email not configured" }   (no email integration)
```
Inserts a `background_tasks` row with `task_type = "email_sync"`, `job_id = 0` (sentinel for global/non-job tasks).

**Poll status:**
```
GET /api/email/sync/status
→ {
    status: "idle" | "queued" | "running" | "completed" | "failed",
    last_completed_at: string | null,   // ISO timestamp or null
    error: string | null
  }
```
Implementation: `SELECT status, finished_at AS last_completed_at FROM background_tasks WHERE task_type = 'email_sync' ORDER BY id DESC LIMIT 1`. If no rows: return `{ status: "idle", last_completed_at: null, error: null }`. Note: the column is `finished_at` (not `completed_at`) per the `background_tasks` schema.

### Store shape

```typescript
interface SyncStatus {
  state: 'idle' | 'queued' | 'running' | 'completed' | 'failed' | 'not_configured'
  lastCompletedAt: string | null
  error: string | null
}
// ref in stores/interviews.ts, or local ref in InterviewsView.vue
```

The sync state can live as a local ref in `InterviewsView.vue` (not in the Pinia store) since it's view-only state with no cross-component consumers.

---

## Feature 3: Stage Signal Banners

### Data Model

`GET /api/interviews` response includes `stage_signals` per job. Implementation: after the main jobs query, run a second query:

```sql
SELECT id, job_id, subject, received_at, stage_signal
FROM job_contacts
WHERE job_id IN (:job_ids)
  AND suggestion_dismissed = 0
  AND stage_signal NOT IN ('neutral', 'unrelated', 'digest', 'event_rescheduled')
  AND stage_signal IS NOT NULL
ORDER BY received_at DESC
```

Group results by `job_id` in Python and attach to each job dict. Empty list `[]` if no signals.

The `StageSignal.id` is `job_contacts.id` — the contact row id, used for the dismiss endpoint.

```typescript
// Export from stores/interviews.ts so InterviewCard.vue can import it
export interface StageSignal {
  id: number              // job_contacts.id — used for POST /api/stage-signals/{id}/dismiss
  subject: string
  received_at: string     // ISO timestamp
  stage_signal: 'interview_scheduled' | 'positive_response' | 'offer_received' | 'survey_received' | 'rejected'
  // 'event_rescheduled' is excluded server-side; other classifier labels filtered at query level
}

export interface PipelineJob {
  // ... existing fields
  stage_signals: StageSignal[]  // undismissed signals, newest first
}
```

### Signal Label + Color Map

| Signal type | Suggested action label | Banner accent | `preSelectedStage` value |
|---|---|---|---|
| `interview_scheduled` | Move to Phone Screen | Amber | `'phone_screen'` |
| `positive_response` | Move to Phone Screen | Amber | `'phone_screen'` |
| `offer_received` | Move to Offer | Green | `'offer'` |
| `survey_received` | Move to Survey | Amber | `'survey'` |
| `rejected` | Mark Rejected | Red | `'interview_rejected'` |

Note: `'rejected'` maps to the stage value `'interview_rejected'` (not `'rejected'`) — this non-obvious mapping must be hardcoded in the signal banner logic.

### Where Banners Appear

Signal banners appear in **both** locations:

1. **Applied/Survey pre-list rows** (in `InterviewsView.vue`) — inline below the existing row content
2. **Kanban `InterviewCard` components** (phone_screen / interviewing / offer columns) — at the bottom of the card, inside the card border

This ensures the `⚡ N signals` count in the Applied section header points to visible, actionable banners in that section.

### Banner Layout

```
┌──────────────────────────────────────────────────┐
│  [existing card / row content]                    │
│──────────────────────────────────────────────────│  ← colored top border (40% opacity)
│ 📧 Email suggests: Move to Phone Screen           │
│ "Interview confirmed for Tuesday…"   [→ Move] [✕] │
└──────────────────────────────────────────────────┘
```

- Background tint: `rgba(245,158,11,0.08)` amber / `rgba(39,174,96,0.08)` green / `rgba(192,57,43,0.08)` red
- Top border: 1px solid matching accent at 40% opacity
- Subject line: truncated to ~60 chars with ellipsis
- **[→ Move]** button: emits `move: [jobId: number, preSelectedStage: PipelineStage]` up to `InterviewsView.vue`, which passes `preSelectedStage` to `MoveToSheet` when opening it. The `InterviewCard` `move` emit signature is extended from `move: [jobId: number]` to `move: [jobId: number, preSelectedStage?: PipelineStage]` — the second argument is optional so existing non-signal `move` calls remain unchanged.
- **[✕]** dismiss button: optimistic removal from local `stage_signals` array, then `POST /api/stage-signals/{id}/dismiss`

**Multiple signals:** when `stage_signals.length > 1`, only the most recent banner shows. A `+N more` link below it expands to show all signals stacked; clicking `− less` (same element, toggled) collapses back to one. Each expanded signal has its own `[✕]` button.

**Empty signals:** `v-if="job.stage_signals?.length"` gates the entire banner — nothing renders when the array is empty or undefined.

### Dismiss API

```
POST /api/stage-signals/{id}/dismiss     (id = job_contacts.id)
→ 200 { ok: true }
```

Sets `suggestion_dismissed = 1` in `job_contacts` for that row. Optimistic update: remove from local `stage_signals` array immediately on click, before API response.

### Applied section signal count

```typescript
// Computed in InterviewsView.vue
const appliedSignalCount = computed(() =>
  [...store.applied, ...store.survey]
    .reduce((n, job) => n + (job.stage_signals?.length ?? 0), 0)
)
```

---

## Files

| File | Action |
|---|---|
| `web/src/views/InterviewsView.vue` | Collapsible Applied section (toggle, localStorage, `max-height` CSS, signal count in header); email sync pill + polling in header |
| `web/src/components/InterviewCard.vue` | Stage signal banner at card bottom; import `StageSignal` from store |
| `web/src/components/MoveToSheet.vue` | Add optional `preSelectedStage?: PipelineStage` prop; pre-select stage button on open |
| `web/src/components/InterviewCard.vue` (emit) | Extend `move` emit: `move: [jobId: number, preSelectedStage?: PipelineStage]` — second arg passed from signal banner `[→ Move]` button; existing card move button continues passing `undefined` |
| `web/src/stores/interviews.ts` | Export `StageSignal` interface; add `stage_signals: StageSignal[]` to `PipelineJob`; update `_row_to_job()` equivalent |
| `dev-api.py` | `stage_signals` nested in `/api/interviews` (second query + Python grouping); `POST /api/email/sync`; `GET /api/email/sync/status`; `POST /api/stage-signals/{id}/dismiss` |

---

## What Stays the Same

- Kanban columns (Phone Screen → Interviewing → Offer/Hired) — layout unchanged
- MoveToSheet modal — existing behavior unchanged; only a new optional prop added
- Rejected section — unchanged
- InterviewCard content above the signal banner — unchanged
- Keyboard navigation — unchanged
