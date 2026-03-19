# Interviews Page — Improvements Design

**Date:** 2026-03-19
**Status:** Approved — ready for implementation planning

---

## Goal

Add three improvements to the Vue SPA Interviews page:
1. Collapse the Applied/Survey pre-kanban strip so the kanban board is immediately visible
2. Email sync status pill in the page header
3. Stage signal banners on job cards (email-detected flags with actionable move/dismiss buttons)

---

## Decisions Made

| Decision | Choice |
|---|---|
| Applied section default state | Collapsed |
| Collapse persistence | `localStorage` key `peregrine.interviews.appliedExpanded` |
| Signal visibility when collapsed | `⚡ N signals` count shown in collapsed header |
| Email sync placement | Page header status pill (right side, beside ↻ Refresh) |
| Signal banner placement | Inline at bottom of InterviewCard |
| Signal data loading | Batched with `GET /api/interviews` response (no N+1 requests) |
| Multiple signals | Show most recent; `+N more` link expands the rest |
| Signal dismiss | Optimistic removal; `POST /api/stage-signals/{id}/dismiss` |

---

## Feature 1: Applied Section Collapsible

### Behavior

The pre-kanban "Applied + Survey" strip (currently rendered above the three kanban columns) becomes a toggle section. Survey jobs remain in the same section as now.

**Default state:** collapsed on page load. `localStorage` is checked first — if the user has previously expanded it, it opens expanded.

**Header row (always visible):**

```
▶  Applied   [12]   ·   ⚡ 2 signals          (collapsed)
▼  Applied   [12]   ·   ⚡ 2 signals          (expanded)
```

- Arrow chevron toggles on click (anywhere on the header row)
- Count badge: total applied + survey jobs
- Signal indicator: `⚡ N signals` in amber — only shown when there are undismissed stage signals among the applied/survey jobs. Hidden when zero.
- Smooth CSS `max-height` transition (200ms ease-out). `prefers-reduced-motion`: instant toggle.

**Expanded state:** renders the existing applied/survey job rows, unchanged from current behavior.

### localStorage

```typescript
const APPLIED_EXPANDED_KEY = 'peregrine.interviews.appliedExpanded'
// default: false (collapsed)
const appliedExpanded = ref(localStorage.getItem(APPLIED_EXPANDED_KEY) === 'true')
watch(appliedExpanded, v => localStorage.setItem(APPLIED_EXPANDED_KEY, String(v)))
```

---

## Feature 2: Email Sync Status Pill

### Placement

Right side of the Interviews page header, alongside the existing ↻ Refresh button.

### States

| State | Appearance | Interaction |
|---|---|---|
| Never synced | `📧 Sync Emails` (outlined button) | Click → trigger sync |
| Queued / Running | `⏳ Syncing…` (disabled, pulse animation) | Non-interactive |
| Completed | `📧 Synced 4m ago` (green pill) | Click → re-trigger sync |
| Failed | `⚠ Sync failed` (amber pill) | Click → retry |

The elapsed-time label ("4m ago") is computed from `lastSyncedAt` timestamp. Updates every 60 seconds via a `setInterval` in `onMounted`, cleared in `onUnmounted`.

### API

**Trigger sync:**
```
POST /api/email/sync
→ 202 { task_id: number }
```
Inserts a `background_tasks` row with `task_type = "email_sync"`, `job_id = 0`. Returns immediately.

**Poll status:**
```
GET /api/email/sync/status
→ { status: "idle" | "queued" | "running" | "completed" | "failed",
    last_completed_at: string | null,
    error: string | null }
```
Polls every 3 seconds while status is `queued` or `running`. Stops polling on `completed` or `failed`. On `completed`, re-fetches the interview job list (to pick up new signals).

### Store action

```typescript
// stores/interviews.ts
async function syncEmails() { ... }  // sets syncStatus ref, polls, re-fetches on complete
```

`syncStatus` ref shape:
```typescript
interface SyncStatus {
  state: 'idle' | 'queued' | 'running' | 'completed' | 'failed'
  lastCompletedAt: string | null
  error: string | null
}
```

---

## Feature 3: Stage Signal Banners

### Data Model

`GET /api/interviews` response now includes `stage_signals` per job:

```typescript
interface StageSignal {
  id: number
  subject: string
  received_at: string
  stage_signal: 'interview_scheduled' | 'positive_response' | 'offer_received' | 'survey_received' | 'rejected'
}

interface PipelineJob {
  // ... existing fields
  stage_signals: StageSignal[]  // undismissed signals only, newest first
}
```

Signals are filtered server-side: `suggestion_dismissed = 0` and `stage_signal NOT IN ('neutral', 'unrelated', 'digest', null)`.

### Signal Label Map

| Signal type | Label | Banner color |
|---|---|---|
| `interview_scheduled` | Move to Phone Screen | Amber |
| `positive_response` | Move to Phone Screen | Amber |
| `offer_received` | Move to Offer | Green |
| `survey_received` | Move to Survey | Amber |
| `rejected` | Mark Rejected | Red |

### Banner Layout

Rendered at the bottom of `InterviewCard`, inside the card border:

```
┌──────────────────────────────────────────────┐
│  [card content]                               │
│──────────────────────────────────────────────│
│ 📧 Email suggests: Move to Phone Screen       │
│ "Interview confirmed for Tuesday…"     [→ Move] [✕] │
└──────────────────────────────────────────────┘
```

- Background: `rgba(245,158,11,0.08)` amber / `rgba(39,174,96,0.08)` green / `rgba(192,57,43,0.08)` red
- Top border matching color (1px, 40% opacity)
- Subject line truncated to ~60 chars
- **[→ Move]** button: opens `MoveToSheet` pre-selected to the suggested stage
- **[✕]** button: dismisses signal (optimistic — removes from local array immediately, then `POST /api/stage-signals/{id}/dismiss`)

**Multiple signals:** only the most recent signal banner is shown by default. If `stage_signals.length > 1`, a `+N more` link at the bottom of the banner expands to show all signals stacked. Each has its own dismiss button.

### Dismiss API

```
POST /api/stage-signals/{id}/dismiss
→ 200 { ok: true }
```
Sets `suggestion_dismissed = 1` in `job_contacts` table.

### Applied section signal count

The collapsed Applied section header shows `⚡ N signals` where N = total undismissed signals across all applied/survey jobs. Computed from `store.applied` + `store.survey` → sum of `stage_signals.length`.

---

## Files

| File | Action |
|---|---|
| `web/src/views/InterviewsView.vue` | Collapsible Applied section + email sync pill |
| `web/src/components/InterviewCard.vue` | Stage signal banner |
| `web/src/stores/interviews.ts` | `stage_signals` on `PipelineJob`; `syncEmails()` action; `SyncStatus` ref |
| `dev-api.py` | `stage_signals` in `/api/interviews`; `POST /api/email/sync`; `GET /api/email/sync/status`; `POST /api/stage-signals/{id}/dismiss` |

---

## What Stays the Same

- Kanban columns (Phone Screen → Interviewing → Offer/Hired) — unchanged
- MoveToSheet modal — unchanged (reused by signal "→ Move" action)
- Rejected section — unchanged
- InterviewCard content above the signal banner — unchanged
- Keyboard navigation — unchanged
