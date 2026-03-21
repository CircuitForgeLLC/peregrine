# Survey Assistant Page — Vue SPA Design

## Goal

Port the Streamlit Survey Assistant page (`app/pages/7_Survey.py`) to a Vue 3 SPA view at `/survey/:id`, with a calm single-column layout, text paste and screenshot input, Quick/Detailed mode selection, LLM analysis, save-to-job, and response history.

## Scope

**In scope:**
- Routing at `/survey/:id` with redirect guard (job must be in `survey`, `phone_screen`, `interviewing`, or `offer`)
- `/survey` (no id) redirects to `/interviews`
- Calm single-column layout (max-width 760px, centered) with sticky job context bar
- Input: tabbed text paste / screenshot (paste Ctrl+V + drag-and-drop + file upload)
- Screenshot tab disabled (but visible) when vision service is unavailable
- Mode selection: two full-width labeled cards (Quick / Detailed)
- Synchronous LLM analysis via new backend endpoint
- Results rendered below input after analysis
- Save to job: optional survey name + reported score
- Response history: collapsible accordion, closed by default
- "Survey →" navigation link on kanban cards in `survey`, `phone_screen`, `interviewing`, `offer` stages

**Explicitly deferred:**
- Streaming LLM responses (requires SSE endpoint — deferred to future sprint)
- Mock Q&A / interview practice chat (separate feature, requires streaming chat endpoint)

---

## Architecture

### Routing

- `/survey/:id` — renders `SurveyView.vue` with the specified job
- `/survey` (no id) — redirects to `/interviews`
- On mount: if job id is missing, or job status not in `['survey', 'phone_screen', 'interviewing', 'offer']`, redirect to `/interviews`

### Backend — `dev-api.py` (4 new endpoints)

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/api/vision/health` | Proxy to vision service health check; returns `{available: bool}` |
| `POST` | `/api/jobs/{id}/survey/analyze` | Accepts `{text?, image_b64?, mode}`; runs LLM synchronously; returns `{output, source}` |
| `POST` | `/api/jobs/{id}/survey/responses` | Saves survey response to `survey_responses` table; saves image file if `image_b64` provided |
| `GET` | `/api/jobs/{id}/survey/responses` | Returns all `survey_responses` rows for job, newest first |

**Analyze endpoint details:**
- `mode`: `"quick"` or `"detailed"` (lowercase) — frontend sends lowercase; backend uses as-is to select prompt template (same as Streamlit `_build_text_prompt` / `_build_image_prompt`, which expect lowercase `mode`)
- If `image_b64` provided: routes through `vision_fallback_order`; **no system prompt** (matches Streamlit vision path); `source = "screenshot"`
- If `text` provided: routes through `research_fallback_order`; passes `system=_SURVEY_SYSTEM` (matches Streamlit text path); `source = "text_paste"`
- `_SURVEY_SYSTEM` constant: `"You are a job application advisor helping a candidate answer a culture-fit survey. The candidate values collaborative teamwork, clear communication, growth, and impact. Choose answers that present them in the best professional light."`
- Returns `{output: str, source: str}` on success; raises HTTP 500 on LLM failure

**Save endpoint details:**
- Body: `{survey_name?, mode, source, raw_input?, image_b64?, llm_output, reported_score?}`
- Backend generates `received_at = datetime.now().isoformat()` — not passed by client
- If `image_b64` present: saves PNG to `data/survey_screenshots/{job_id}/{timestamp}.png`; stores path in `image_path` column; `image_b64` is NOT stored in DB
- Calls `scripts.db.insert_survey_response(db_path, job_id, survey_name, received_at, source, raw_input, image_path, mode, llm_output, reported_score)` — note `received_at` is the second positional arg after `job_id`
- `SurveyResponse.created_at` in the store interface maps the DB `created_at` column (SQLite auto-set on insert); `received_at` is a separate column storing the analysis timestamp — both are returned by `GET /survey/responses`; store interface exposes `received_at` for display
- Returns `{id: int}` of new row

**Vision health endpoint:**
- Attempts `GET http://localhost:8002/health` with 2s timeout
- Returns `{available: true}` on 200, `{available: false}` on any error/timeout

### Store — `web/src/stores/survey.ts`

```ts
interface SurveyAnalysis {
  output: string
  source: 'text_paste' | 'screenshot'
  mode: 'quick' | 'detailed'   // retained so saveResponse can include it
  rawInput: string | null       // retained so saveResponse can include raw_input
}

interface SurveyResponse {
  id: number
  survey_name: string | null
  mode: 'quick' | 'detailed'
  source: string
  raw_input: string | null
  image_path: string | null
  llm_output: string
  reported_score: string | null
  received_at: string | null    // analysis timestamp (from DB received_at column)
  created_at: string | null     // row insert timestamp (SQLite auto)
}
```

State: `analysis: SurveyAnalysis | null`, `history: SurveyResponse[]`, `loading: boolean`, `saving: boolean`, `error: string | null`, `visionAvailable: boolean`, `currentJobId: number | null`

Methods:
- `fetchFor(jobId)` — clears state if `jobId !== currentJobId`; fires two parallel requests: `GET /api/jobs/{id}/survey/responses` and `GET /api/vision/health`; stores results
- `analyze(jobId, payload: {text?: string, image_b64?: string, mode: 'quick' | 'detailed'})` — sets `loading = true`; POST to analyze endpoint; stores result in `analysis` (including `mode` and `rawInput = payload.text ?? null` for later use by `saveResponse`); sets `error` on failure
- `saveResponse(jobId, {surveyName: string, reportedScore: string, image_b64?: string})` — sets `saving = true`; constructs full save body from current `analysis` (`mode`, `source`, `rawInput`, `llm_output`) + method args; POST to save endpoint; prepends new response to `history`; clears `analysis`; sets `error` on failure
- `clear()` — resets all state to initial values

### Component — `web/src/views/SurveyView.vue`

**Mount / unmount:**
- Reads `route.params.id`; redirects to `/interviews` if missing or non-numeric
- Looks up job in `interviewsStore.jobs` (fetches if empty); redirects if job status not in valid stages
- Calls `surveyStore.fetchFor(jobId)` on mount
- Calls `surveyStore.clear()` on unmount

**Layout:** Single column, `max-width: 760px`, centered (`margin: 0 auto`), padding `var(--space-6)`.

**1. Sticky context bar**
- Sticky top, low height (~40px), soft background color
- Shows: company name + job title + stage badge
- Always visible while scrolling

**2. Input card**
- Tabs: "📝 Paste Text" (always active) / "📷 Screenshot"
  - Screenshot tab: rendered but non-interactive (`aria-disabled`) when `!surveyStore.visionAvailable`; tooltip on hover: "Vision service not running — start it with: bash scripts/manage-vision.sh start"
- **Text tab:** `<textarea>` with placeholder showing example Q&A format, min-height 200px
- **Screenshot tab:** Combined drop zone with three affordances:
  - Paste: listens for `paste` event on the zone (Ctrl+V); accepts `image/*` items from `ClipboardEvent.clipboardData`
  - Drag-and-drop: `dragover` / `drop` events; accepts image files
  - File upload: `<input type="file" accept="image/*">` button within the zone
  - Preview: shows thumbnail of loaded image with "✕ Remove" button
  - Stores image as base64 string in component state

**3. Mode selection**
- Two full-width stacked cards, one per mode:
  - ⚡ **Quick** — "Best answer + one-liner per question"
  - 📋 **Detailed** — "Option-by-option breakdown with reasoning"
- Selected card: border highlight + subtle background fill
- Reactive `selectedMode` ref, default `'quick'`

**4. Analyze button**
- Full-width primary button
- Disabled when: no text input AND no image loaded
- While `surveyStore.loading`: shows spinner + "Analyzing…" label, disabled
- On click: calls `surveyStore.analyze(jobId, {text?, image_b64?, mode: selectedMode})`

**5. Results card** (rendered when `surveyStore.analysis` is set)
- Appears below the Analyze button (pushes history further down)
- LLM output rendered with `whitespace-pre-wrap`
- Inline save form below output:
  - Optional "Survey name" text input (placeholder: "e.g. Culture Fit Round 1")
  - Optional "Reported score" text input (placeholder: "e.g. 82% or 4.2/5")
  - "💾 Save to job" button — calls `surveyStore.saveResponse()`; shows spinner while `surveyStore.saving`
  - Inline success message on save; clears results card

**6. History accordion**
- Header: "Survey history (N responses)" — closed by default
- Low visual weight (muted header style)
- Each entry: survey name (fallback "Survey response") + date + score if present
- Expandable per entry: shows full LLM output + mode + source + `received_at` timestamp
- `raw_input` and `image_path` are intentionally not shown in history — raw input can be long and images are not served by the API
- Empty state if no history

**Error display:**
- Analyze error: inline below Analyze button
- Save error: inline below save form (analysis output preserved)
- Store-level load error (history/vision fetch): subtle banner below context bar

**Mobile:** identical — already single column.

### Navigation addition — `InterviewsView.vue` / `InterviewCard.vue`

Follow the existing `InterviewCard.vue` emit pattern (same as "Prep →"):
- Add `emit('survey', job.id)` button to `InterviewCard.vue` with `v-if="['survey', 'phone_screen', 'interviewing', 'offer'].includes(job.status)"`
- Add `@survey="router.push('/survey/' + $event)"` handler in `InterviewsView.vue` on the relevant column card instances

Do NOT use a `RouterLink` directly on the card — the established pattern is event emission to the parent view for navigation.

---

## Data Flow

```
User navigates to /survey/:id (from kanban "Survey →" link)
  → SurveyView mounts
  → redirect check (job in valid stage?)
  → surveyStore.fetchFor(id)
      ├─ GET /api/jobs/{id}/survey/responses  (parallel)
      └─ GET /api/vision/health               (parallel)
  → user pastes text OR uploads/pastes/drags screenshot
  → user selects mode (Quick / Detailed)
  → user clicks Analyze
      → POST /api/jobs/{id}/survey/analyze
      → surveyStore.analysis set with output
  → user reviews output
  → user optionally fills survey name + reported score
  → user clicks Save
      → POST /api/jobs/{id}/survey/responses
      → new entry prepended to surveyStore.history
      → results card cleared
User navigates away
  → surveyStore.clear() resets state
```

---

## Error Handling

- Vision health check fails → `visionAvailable = false`; screenshot tab disabled; text input unaffected
- Analyze POST fails → `error` set; inline error below button; input preserved for retry
- Save POST fails → `saving` error set; inline error on save form; analysis output preserved
- Job not found / wrong stage → redirect to `/interviews`
- History fetch fails → empty history, inline error banner; does not block analyze flow

---

## Testing

New test files:
- `tests/test_dev_api_survey.py` — covers all 4 endpoints: vision health (up/down), analyze text (quick/detailed), analyze image, analyze LLM failure, save response (with/without image), get history (empty/populated)
- `web/src/stores/survey.test.ts` — unit tests: `fetchFor` parallel loads, job change clears state, `analyze` stores result, `analyze` sets error on failure, `saveResponse` prepends to history and clears analysis, `clear` resets all state

No new DB migrations. All DB access uses existing `scripts/db.py` helpers (`insert_survey_response`, `get_survey_responses`).

---

## Files Changed

| Action | Path |
|--------|------|
| Modify | `dev-api.py` — 4 new endpoints |
| Create | `tests/test_dev_api_survey.py` |
| Create | `web/src/stores/survey.ts` |
| Create | `web/src/stores/survey.test.ts` |
| Create | `web/src/views/SurveyView.vue` — full implementation (replaces placeholder stub) |
| Modify | `web/src/components/InterviewCard.vue` — add "Survey →" link |
