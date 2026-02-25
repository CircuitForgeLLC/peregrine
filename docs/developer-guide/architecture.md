# Architecture

This page describes Peregrine's system structure, layer boundaries, and key design decisions.

---

## System Overview

```
┌─────────────────────────────────────────────────────────────┐
│                     Docker Compose                           │
│                                                             │
│  ┌──────────┐  ┌──────────┐  ┌───────┐  ┌───────────────┐ │
│  │  app     │  │  ollama  │  │ vllm  │  │ vision        │ │
│  │ :8501    │  │ :11434   │  │ :8000 │  │ :8002         │ │
│  │Streamlit │  │ Local LLM│  │ vLLM  │  │ Moondream2    │ │
│  └────┬─────┘  └──────────┘  └───────┘  └───────────────┘ │
│       │                                                      │
│  ┌────┴───────┐  ┌─────────────┐                           │
│  │ searxng    │  │  staging.db │                           │
│  │ :8888      │  │  (SQLite)   │                           │
│  └────────────┘  └─────────────┘                           │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                   Streamlit App Layer                        │
│                                                             │
│  app/app.py (entry point, navigation, sidebar task badge)  │
│                                                             │
│  app/pages/                                                 │
│    0_Setup.py       First-run wizard (gates everything)    │
│    1_Job_Review.py  Approve / reject queue                 │
│    2_Settings.py    All user configuration                 │
│    4_Apply.py       Cover letter gen + PDF export          │
│    5_Interviews.py  Kanban: phone_screen → hired           │
│    6_Interview_Prep.py  Research brief + practice Q&A     │
│    7_Survey.py      Culture-fit survey assistant           │
│                                                             │
│  app/wizard/                                                │
│    step_hardware.py ... step_integrations.py               │
│    tiers.py         Feature gate definitions               │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                     Scripts Layer                            │
│   (framework-independent — could be called by FastAPI)      │
│                                                             │
│  discover.py          JobSpy + custom board orchestration   │
│  match.py             Resume keyword scoring                │
│  db.py                All SQLite helpers (single source)    │
│  llm_router.py        LLM fallback chain                   │
│  generate_cover_letter.py  Cover letter generation         │
│  company_research.py  Pre-interview research brief         │
│  task_runner.py       Background daemon thread executor    │
│  imap_sync.py         IMAP email fetch + classify          │
│  sync.py              Push to external integrations        │
│  user_profile.py      UserProfile wrapper for user.yaml   │
│  preflight.py         Port + resource check                │
│                                                             │
│  custom_boards/       Per-board scrapers                   │
│  integrations/        Per-service integration drivers      │
│  vision_service/      FastAPI Moondream2 inference server  │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                      Config Layer                            │
│                                                             │
│  config/user.yaml          Personal data + wizard state    │
│  config/llm.yaml           LLM backends + fallback chains  │
│  config/search_profiles.yaml   Job search configuration    │
│  config/resume_keywords.yaml   Scoring keywords            │
│  config/blocklist.yaml         Excluded companies/domains  │
│  config/email.yaml             IMAP credentials            │
│  config/integrations/          Per-integration credentials │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                      Database Layer                          │
│                                                             │
│  staging.db (SQLite, local, gitignored)                     │
│                                                             │
│  jobs              Core pipeline — all job data            │
│  job_contacts      Email thread log per job                │
│  company_research  LLM-generated research briefs           │
│  background_tasks  Async task queue state                  │
│  survey_responses  Culture-fit survey Q&A pairs            │
└─────────────────────────────────────────────────────────────┘
```

---

## Layer Boundaries

### App layer (app/)

The Streamlit UI layer. Its only responsibilities are:

- Reading from `scripts/db.py` helpers
- Calling `scripts/` functions directly or via `task_runner.submit_task()`
- Rendering results to the browser

The app layer does not contain business logic. Database queries, LLM calls, and integrations all live in `scripts/`.

### Scripts layer (scripts/)

This is the stable public API of Peregrine. Scripts are designed to be framework-independent — they do not import Streamlit and can be called from a CLI, FastAPI endpoint, or background thread without modification.

All personal data access goes through `scripts/user_profile.py` (`UserProfile` class). Scripts never read `config/user.yaml` directly.

All database access goes through `scripts/db.py`. No script does raw SQLite outside of `db.py`.

### Config layer (config/)

Plain YAML files. Gitignored files contain secrets; `.example` files are committed as templates.

---

## Background Tasks

`scripts/task_runner.py` provides a simple background thread executor for long-running LLM tasks.

```python
from scripts.task_runner import submit_task

# Queue a cover letter generation task
submit_task(db_path, task_type="cover_letter", job_id=42)

# Queue a company research task
submit_task(db_path, task_type="company_research", job_id=42)
```

Tasks are recorded in the `background_tasks` table with statuses: `queued → running → completed / failed`.

**Dedup rule:** Only one `queued` or `running` task per `(task_type, job_id)` pair is allowed at a time. Submitting a duplicate is a silent no-op.

**On startup:** `app/app.py` resets any `running` or `queued` rows to `failed` to clear tasks that were interrupted by a server restart.

**Sidebar indicator:** `app/app.py` polls the `background_tasks` table every 3 seconds via a Streamlit fragment and displays a badge in the sidebar.

---

## LLM Router

`scripts/llm_router.py` provides a single `complete()` call that tries backends in priority order and falls back transparently. See [LLM Router](../reference/llm-router.md) for full documentation.

---

## Key Design Decisions

### scripts/ is framework-independent

The scripts layer was deliberately kept free of Streamlit imports. This means the full pipeline can be migrated to a FastAPI or Celery backend without rewriting business logic.

### All personal data via UserProfile

`scripts/user_profile.py` is the single source of truth for all user data. This makes it easy to swap the storage backend (e.g. from YAML to a database) without touching every script.

### SQLite as staging layer

`staging.db` acts as the staging layer between discovery and external integrations. This lets discovery, matching, and the UI all run independently without network dependencies. External integrations (Notion, Airtable, etc.) are push-only and optional.

### Tier system in app/wizard/tiers.py

`FEATURES` is a single dict that maps feature key → minimum tier. `can_use(tier, feature)` is the single gating function. New features are added to `FEATURES` in one place.

### Vision service is a separate process

Moondream2 requires `torch` and `transformers`, which are incompatible with the lightweight main conda environment. The vision service runs as a separate FastAPI process in a separate conda environment (`job-seeker-vision`), keeping the main env free of GPU dependencies.
