# Interview Prep Page — Vue SPA Design

## Goal

Port the Streamlit Interview Prep page (`app/pages/6_Interview_Prep.py`) to a Vue 3 SPA view at `/prep/:id`, with a two-column layout, research brief generation, reference tabs, and localStorage call notes.

## Scope

**In scope:**
- Job header with stage badge + interview date countdown
- Research brief display with generate / refresh / polling
- All research sections: Talking Points, Company Overview, Leadership & Culture, Tech Stack (conditional), Funding (conditional), Red Flags (conditional), Inclusion & Accessibility (conditional)
- Reference panel: Job Description tab, Email History tab, Cover Letter tab
- Call Notes (localStorage, per job)
- Navigation: `/prep` redirects to `/interviews`; Interviews kanban adds "Prep →" link on active-stage cards

**Explicitly deferred:**
- Practice Q&A (LLM mock interviewer chat — needs streaming chat endpoint, deferred to a future sprint)
- "Draft reply to last email" LLM button in Email tab (present in Streamlit, requires additional LLM endpoint, deferred to a future sprint)
- Layout B / C options (full-width tabbed, accordion) — architecture supports future layout preference stored in localStorage

---

## Architecture

### Routing

- `/prep/:id` — renders `InterviewPrepView.vue` with the specified job
- `/prep` (no id) — redirects to `/interviews`
- On mount: if job id is missing, or job is not in `phone_screen` / `interviewing` / `offer`, redirect to `/interviews`
- Router already has both routes defined (`/prep` and `/prep/:id`)

### Backend — `dev-api.py` (4 new endpoints)

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/api/jobs/{id}/research` | Returns `company_research` row for job, or 404 if none |
| `POST` | `/api/jobs/{id}/research/generate` | Submits `company_research` background task via `submit_task()`; returns `{task_id, is_new}` |
| `GET` | `/api/jobs/{id}/research/task` | Latest task status from `background_tasks`: `{status, stage, message}` — matches `cover_letter_task` response shape (`message` maps the `error` column) |
| `GET` | `/api/jobs/{id}/contacts` | Returns all `job_contacts` rows for this job, ordered by `received_at` desc |

Reuses existing patterns: `submit_task()` (same as cover letter), `background_tasks` query (same as `cover_letter_task`), `get_contacts()` (same as Streamlit). No schema changes.

### Store — `web/src/stores/prep.ts`

```ts
interface ResearchBrief {
  company_brief: string | null
  ceo_brief: string | null
  talking_points: string | null
  tech_brief: string | null        // confirmed present in company_research (used in Streamlit 6_Interview_Prep.py:178)
  funding_brief: string | null     // confirmed present in company_research (used in Streamlit 6_Interview_Prep.py:185)
  red_flags: string | null
  accessibility_brief: string | null
  generated_at: string | null
  // raw_output is returned by the API but not used in the UI — intentionally omitted from interface
}

interface Contact {
  id: number
  direction: 'inbound' | 'outbound'
  subject: string | null
  from_addr: string | null
  body: string | null
  received_at: string | null
}

interface TaskStatus {
  status: 'queued' | 'running' | 'completed' | 'failed' | 'none' | null
  stage: string | null
  message: string | null  // maps the background_tasks.error column; matches cover_letter_task shape
}
```

State: `research: ResearchBrief | null`, `contacts: Contact[]`, `taskStatus: TaskStatus`, `loading: boolean`, `error: string | null`, `currentJobId: number | null`.

Methods:
- `fetchFor(jobId)` — clears state if `jobId !== currentJobId`, fires three parallel requests: `GET /research`, `GET /contacts`, `GET /research/task`. Stores results. If task status from the task fetch is `queued` or `running`, calls `pollTask(jobId)` to start the polling interval.
- `generateResearch(jobId)` — `POST /research/generate`, then calls `pollTask(jobId)`
- `pollTask(jobId)` — `setInterval` at 3s; stops when status is `completed` or `failed`; on `completed` re-calls `fetchFor(jobId)` to pull in fresh research
- `clear()` — cancels any active poll interval, resets all state

### Component — `web/src/views/InterviewPrepView.vue`

**Mount / unmount:**
- Reads `route.params.id`; redirects to `/interviews` if missing
- Looks up job in `interviewsStore.jobs`; redirects to `/interviews` if job status not in active stages
- Calls `prepStore.fetchFor(jobId)` on mount
- Calls `prepStore.clear()` on unmount (`onUnmounted`)

**Layout (desktop ≥1024px): two-column**

Left column (40%):
1. Job header
   - Company + title (`h1`)
   - Stage badge (pill)
   - Interview date + countdown (🔴 TODAY / 🟡 TOMORROW / 🟢 in N days / grey "was N days ago")
   - "Open job listing ↗" link button (if `job.url`)
2. Research controls
   - State: `no research + no task` → "Generate research brief" primary button
   - State: `task queued/running` → spinner + stage label (e.g. "Scraping company site…"), polling active
   - State: `research loaded` → "Generated: {timestamp}" caption + "Refresh" button (disabled while task running)
   - State: `task failed` → inline error + "Retry" button
3. Research sections (render only if non-empty string):
   - 🎯 Talking Points
   - 🏢 Company Overview
   - 👤 Leadership & Culture
   - ⚙️ Tech Stack & Product *(conditional)*
   - 💰 Funding & Market Position *(conditional)*
   - ⚠️ Red Flags & Watch-outs *(conditional; styled as warning block; skip if text contains "no significant red flags")*
   - ♿ Inclusion & Accessibility *(conditional; privacy caption: "For your personal evaluation — not disclosed in any application.")*

Right column (60%):
1. Tabs: Job Description | Email History | Cover Letter
   - **JD tab**: match score badge (🟢 ≥70% / 🟡 ≥40% / 🔴 <40%), keyword gaps, description rendered as markdown
   - **Email tab**: list of contacts — icon (📥/📤) + subject + date + from_addr + first 500 chars of body; empty state if none
   - **Letter tab**: cover letter markdown; empty state if none
2. Call Notes
   - Textarea below tabs
   - `v-model` bound to computed getter/setter reading `localStorage.getItem('cf-prep-notes-{jobId}')`
   - Auto-saved via debounced `watch` (300ms)
   - Caption: "Notes are saved locally — they won't sync between devices."
   - **Intentional upgrade from Streamlit**: Streamlit stored notes in `session_state` only (lost on navigation). localStorage persists across page refreshes and sessions.

**Mobile (≤1023px):** single column — left panel content first (scrollable), then tabs panel below.

### Navigation addition — `InterviewsView.vue`

Add a "Prep →" `RouterLink` to `/prep/:id` on each job card in `phone_screen`, `interviewing`, and `offer` columns. Not shown in `applied`, `survey`, `hired`, or `interview_rejected`.

---

## Data Flow

```
User navigates to /prep/:id
  → InterviewPrepView mounts
  → redirect check (job in active stage?)
  → prepStore.fetchFor(id)
      ├─ GET /api/jobs/{id}/research       (parallel)
      ├─ GET /api/jobs/{id}/contacts       (parallel)
      └─ GET /api/jobs/{id}/research/task  (parallel — to check if a task is already running)
  → if task running: pollTask(id) starts interval
  → user clicks "Generate" / "Refresh"
      → POST /api/jobs/{id}/research/generate
      → pollTask(id) starts
          → GET /api/jobs/{id}/research/task every 3s
          → on completed: fetchFor(id) re-fetches research
User navigates away
  → prepStore.clear() cancels interval
```

---

## Error Handling

- Research fetch 404 → `research` stays null, show generate button
- Research fetch network/5xx → show inline error in left column
- Contacts fetch error → show "Could not load email history" in Email tab
- Generate task failure → `taskStatus.message` shown with "Retry" button
- Job not found / wrong stage → redirect to `/interviews` (no error flash)

---

## Testing

New test files:
- `tests/test_dev_api_prep.py` — covers all 4 endpoints: research GET (found/not-found), generate (new/duplicate), task status, contacts GET
- `web/src/stores/prep.test.ts` — unit tests for `fetchFor`, `generateResearch`, `pollTask` (mock `useApiFetch`), `clear` cancels interval

No new DB migrations. All DB access uses existing `scripts/db.py` helpers.

---

## Files Changed

| Action | Path |
|--------|------|
| Modify | `dev-api.py` — 4 new endpoints |
| Create | `tests/test_dev_api_prep.py` |
| Create | `web/src/stores/prep.ts` |
| Modify | `web/src/views/InterviewPrepView.vue` — full implementation |
| Modify | `web/src/views/InterviewsView.vue` — add "Prep →" links |
| Create | `web/src/stores/prep.test.ts` |
