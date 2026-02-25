# Survey Assistant — Design Doc

**Date:** 2026-02-23
**Status:** Approved

---

## Goal

Add a real-time Survey Assistant to the job application pipeline that helps the user answer culture-fit and values surveys during the application process. Supports timed surveys via screenshot ingestion and text paste, with a quick ("just give me the answer") or detailed ("explain each option") mode toggle.

---

## Pipeline Stage

A new `survey` stage is inserted between `applied` and `phone_screen`:

```
pending → approved → applied → survey → phone_screen → interviewing → offer → hired
```

- Promotion to `survey` is triggered manually (banner prompt) or automatically when the email classifier detects a `survey_received` signal.
- Jobs can skip `survey` entirely — it is not required.
- `survey_at` timestamp column added to `jobs` table.

---

## Email Classifier

`classify_stage_signal` in `scripts/imap_sync.py` gains a 6th label: `survey_received`.

When detected:
- The Interviews page shows the existing stage-suggestion banner style: "Survey email received — move to Survey stage?"
- One-click promote button moves the job to `survey` and records `survey_at`.

---

## Kanban Consolidation (Interviews Page)

### Change A — Pre-kanban section
`applied` and `survey` jobs appear above the kanban columns in a pre-pipeline section, not as their own columns. Visual differentiation: `survey` jobs show a badge/chip.

### Change B — Offer + Hired merged
`offer` and `hired` are combined into one column. `hired` jobs are visually differentiated (e.g. green highlight or checkmark icon) rather than occupying a separate column.

**Result:** Kanban columns are `phone_screen | interviewing | offer/hired` (3 columns), with applied/survey as a pre-section above.

---

## Survey Assistant Page (`app/pages/7_Survey.py`)

### Layout

**Left panel — Input**
- Job selector dropdown (defaults to `survey`-stage jobs, allows any job)
- Survey name field (optional label, e.g. "Culture Fit Round 1")
- Mode toggle: **Quick** / **Detailed** (persisted in session state)
- Two input tabs:
  - **Paste Text** — textarea for pasted survey content
  - **Screenshot** — `streamlit-paste-button` (clipboard paste) + file uploader side by side; either method populates an image preview
- Analyze button

**Right panel — Output**
- **Quick mode:** numbered list, each item is bold option letter + one-line rationale
  e.g. `**B** — most aligns with a collaborative, team-first culture`
- **Detailed mode:** each question expanded — option-by-option breakdown, recommendation, brief "why"
- "Save to Job" button — persists Q&A to `survey_responses`; shows reported score field before saving

**Below both panels — History**
- Accordion: prior saved survey responses for the selected job, newest first
- Shows survey name, mode, reported score, timestamp, and LLM output summary

---

## Data Model

### `survey_responses` table (new)

```sql
CREATE TABLE survey_responses (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id         INTEGER NOT NULL REFERENCES jobs(id),
    survey_name    TEXT,           -- e.g. "Culture Fit Round 1"
    received_at    DATETIME,       -- when the survey email arrived (if known)
    source         TEXT,           -- 'text_paste' | 'screenshot'
    raw_input      TEXT,           -- pasted text content, or NULL for screenshots
    image_path     TEXT,           -- path to saved screenshot, or NULL
    mode           TEXT,           -- 'quick' | 'detailed'
    llm_output     TEXT,           -- full LLM response
    reported_score TEXT,           -- optional score shown by the survey app
    created_at     DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

Screenshots saved to `data/survey_screenshots/<job_id>/<timestamp>.png` (directory gitignored). Stored by path, not BLOB.

Multiple rows per job are allowed (multiple survey rounds).

### `jobs` table addition
- `survey_at DATETIME` — timestamp when job entered `survey` stage

---

## Vision Service (`scripts/vision_service/`)

A dedicated, optional FastAPI microservice for image-based survey analysis. Independent of thoth.

### Model
- **Primary:** `moondream2` (~1.5GB VRAM at 4-bit quantization)
- **Reserve:** `Qwen2.5-VL-3B` if moondream2 accuracy proves insufficient

### Architecture
- Separate conda env: `job-seeker-vision` (torch + transformers + FastAPI + moondream2)
- Port: **8002** (avoids conflict with vLLM on 8000 and thoth on 8001)
- Model loaded lazily on first request, stays resident (no reload between calls)
- GPU loaded on first inference request; 4-bit quantization keeps VRAM footprint ~1.5GB

### Endpoints
```
POST /analyze
  Body: { "prompt": str, "image_base64": str }
  Returns: { "text": str }

GET /health
  Returns: { "status": "ok"|"loading", "model": str, "gpu": bool }
```

### Management
`scripts/manage-vision.sh start|stop|restart|status|logs` — same pattern as `manage-ui.sh`.

### Optional install
- If the vision service is not running, the Screenshot tab on the Survey page is hidden
- A note in its place explains how to enable: "Install vision service — see docs/vision-service.md"
- Text Paste mode always available regardless of vision service status

---

## LLM Router Changes (`scripts/llm_router.py`)

`LLMRouter.complete()` gains an optional `images` parameter:

```python
def complete(self, prompt: str, images: list[str] | None = None) -> str:
    # images: list of base64-encoded PNG/JPG strings
```

- Backends that don't support images are skipped when `images` is provided
- Survey analysis fallback order: `vision_service → claude_code`
- `vision_service` backend entry added to `config/llm.yaml` (enabled: false by default — optional install)

---

## Generalized Version Notes

- Vision service is an **optional feature** in the generalized app
- `config/llm.yaml` ships with `vision_service.enabled: false`
- `scripts/manage-vision.sh` and `scripts/vision_service/` included but documented as optional
- Survey page renders in degraded (text-only) mode if vision service is absent
- Install instructions in `docs/vision-service.md` (to be written during implementation)

---

## Files Affected

| File | Change |
|------|--------|
| `app/pages/7_Survey.py` | New page |
| `app/pages/5_Interviews.py` | Kanban consolidation (A+B), survey banner |
| `scripts/imap_sync.py` | Add `survey_received` classifier label |
| `scripts/db.py` | `survey_responses` table, `survey_at` column, CRUD helpers |
| `scripts/llm_router.py` | `images=` parameter, skip non-vision backends |
| `scripts/vision_service/main.py` | New FastAPI vision service |
| `scripts/vision_service/environment.yml` | New conda env spec |
| `scripts/manage-vision.sh` | New management script |
| `config/llm.yaml` | Add `vision_service` backend entry (enabled: false) |
| `config/llm.yaml.example` | Same |
