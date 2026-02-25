# Job Seeker Platform — Claude Context

## Project
Automated job discovery + resume matching + application pipeline for Alex Rivera.

Full pipeline:
```
JobSpy → discover.py → SQLite (staging.db) → match.py → Job Review UI
→ Apply Workspace (cover letter + PDF) → Interviews kanban
→ phone_screen → interviewing → offer → hired
         ↓
      Notion DB (synced via sync.py)
```

## Environment
- Python env: `conda run -n job-seeker <cmd>` — always use this, never bare python
- Run tests: `/devl/miniconda3/envs/job-seeker/bin/pytest tests/ -v`
  (use direct binary — `conda run pytest` can spawn runaway processes)
- Run discovery: `conda run -n job-seeker python scripts/discover.py`
- Recreate env: `conda env create -f environment.yml`
- pytest.ini scopes test collection to `tests/` only — never widen this

## ⚠️ AIHawk env isolation — CRITICAL
- NEVER `pip install -r aihawk/requirements.txt` into the job-seeker env
- AIHawk pulls torch + CUDA (~7GB) which causes OOM during test runs
- AIHawk must run in its own env: `conda create -n aihawk-env python=3.12`
- job-seeker env must stay lightweight (no torch, no sentence-transformers, no CUDA)

## Web UI (Streamlit)
- Run: `bash scripts/manage-ui.sh start` → http://localhost:8501
- Manage: `start | stop | restart | status | logs`
- Direct binary: `/devl/miniconda3/envs/job-seeker/bin/streamlit run app/app.py`
- Entry point: `app/app.py` (uses `st.navigation()` — do NOT run `app/Home.py` directly)
- `staging.db` is gitignored — SQLite staging layer between discovery and Notion

### Pages
| Page | File | Purpose |
|------|------|---------|
| Home | `app/Home.py` | Dashboard, discovery trigger, danger-zone purge |
| Job Review | `app/pages/1_Job_Review.py` | Batch approve/reject with sorting |
| Settings | `app/pages/2_Settings.py` | LLM backends, search profiles, Notion, services |
| Resume Profile | Settings → Resume Profile tab | Edit AIHawk YAML profile (was standalone `3_Resume_Editor.py`) |
| Apply Workspace | `app/pages/4_Apply.py` | Cover letter gen + PDF export + mark applied + reject listing |
| Interviews | `app/pages/5_Interviews.py` | Kanban: phone_screen→interviewing→offer→hired |
| Interview Prep | `app/pages/6_Interview_Prep.py` | Live reference sheet during calls + Practice Q&A |
| Survey Assistant | `app/pages/7_Survey.py` | Culture-fit survey help: text paste + screenshot (moondream2) |

## Job Status Pipeline
```
pending → approved/rejected          (Job Review)
approved → applied                   (Apply Workspace — mark applied)
approved → rejected                  (Apply Workspace — reject listing button)
applied → survey                     (Interviews — "📋 Survey" button; pre-kanban section)
applied → phone_screen               (Interviews — triggers company research)
survey → phone_screen                (Interviews — after survey completed)
phone_screen → interviewing
interviewing → offer
offer → hired
any stage → rejected (rejection_stage captured for analytics)
applied/approved → synced            (sync.py → Notion)
```

## SQLite Schema (`staging.db`)
### `jobs` table key columns
- Standard: `id, title, company, url, source, location, is_remote, salary, description`
- Scores: `match_score, keyword_gaps`
- Dates: `date_found, applied_at, survey_at, phone_screen_at, interviewing_at, offer_at, hired_at`
- Interview: `interview_date, rejection_stage`
- Content: `cover_letter, notion_page_id`

### Additional tables
- `job_contacts` — email thread log per job (direction, subject, from/to, body, received_at)
- `company_research` — LLM-generated brief per job (company_brief, ceo_brief, talking_points, raw_output, accessibility_brief)
- `background_tasks` — async LLM task queue (task_type, job_id, status: queued/running/completed/failed)
- `survey_responses` — per-job Q&A pairs (survey_name, received_at, source, raw_input, image_path, mode, llm_output, reported_score)

## Scripts
| Script | Purpose |
|--------|---------|
| `scripts/discover.py` | JobSpy + custom board scrape → SQLite insert |
| `scripts/custom_boards/adzuna.py` | Adzuna Jobs API (app_id + app_key in config/adzuna.yaml) |
| `scripts/custom_boards/theladders.py` | The Ladders scraper via curl_cffi + __NEXT_DATA__ SSR parse |
| `scripts/match.py` | Resume keyword matching → match_score |
| `scripts/sync.py` | Push approved/applied jobs to Notion |
| `scripts/llm_router.py` | LLM fallback chain (reads config/llm.yaml) |
| `scripts/generate_cover_letter.py` | Cover letter via LLM; detects mission-aligned companies (music/animal welfare/education) and injects Para 3 hint |
| `scripts/company_research.py` | Pre-interview brief via LLM + optional SearXNG scrape; includes Inclusion & Accessibility section |
| `scripts/prepare_training_data.py` | Extract cover letter JSONL for fine-tuning |
| `scripts/finetune_local.py` | Unsloth QLoRA fine-tune on local GPU |
| `scripts/db.py` | All SQLite helpers (single source of truth) |
| `scripts/task_runner.py` | Background thread executor — `submit_task(db, type, job_id)` dispatches daemon threads for LLM jobs |
| `scripts/vision_service/main.py` | FastAPI moondream2 inference on port 8002; `manage-vision.sh` lifecycle |

## LLM Router
- Config: `config/llm.yaml`
- Cover letter fallback order: `claude_code → ollama (alex-cover-writer:latest) → vllm → copilot → anthropic`
- Research fallback order: `claude_code → vllm (__auto__, ouroboros) → ollama_research (llama3.1:8b) → ...`
- `alex-cover-writer:latest` is cover-letter only — it doesn't follow structured markdown prompts for research
- `LLMRouter.complete()` accepts `fallback_order=` override for per-task routing
- `LLMRouter.complete()` accepts `images: list[str]` (base64) — vision backends only; non-vision backends skipped when images present
- Vision fallback order config key: `vision_fallback_order: [vision_service, claude_code, anthropic]`
- `vision_service` backend type: POST to `/analyze`; skipped automatically when no images provided
- Claude Code wrapper: `/Library/Documents/Post Fight Processing/server-openai-wrapper-v2.js`
- Copilot wrapper: `/Library/Documents/Post Fight Processing/manage-copilot.sh start`

## Fine-Tuned Model
- Model: `alex-cover-writer:latest` registered in Ollama
- Base: `unsloth/Llama-3.2-3B-Instruct` (QLoRA, rank 16, 10 epochs)
- Training data: 62 cover letters from `/Library/Documents/JobSearch/`
- JSONL: `/Library/Documents/JobSearch/training_data/cover_letters.jsonl`
- Adapter: `/Library/Documents/JobSearch/training_data/finetune_output/adapter/`
- Merged: `/Library/Documents/JobSearch/training_data/gguf/alex-cover-writer/`
- Re-train: `conda run -n ogma python scripts/finetune_local.py`
  (uses `ogma` env with unsloth + trl; pin to GPU 0 with `CUDA_VISIBLE_DEVICES=0`)

## Background Tasks
- Cover letter gen and company research run as daemon threads via `scripts/task_runner.py`
- Tasks survive page navigation; results written to existing tables when done
- On server restart, `app.py` startup clears any stuck `running`/`queued` rows to `failed`
- Dedup: only one queued/running task per `(task_type, job_id)` at a time
- Sidebar indicator (`app/app.py`) polls every 3s via `@st.fragment(run_every=3)`
- ⚠️ Streamlit fragment + sidebar: use `with st.sidebar: _fragment()` — sidebar context must WRAP the call, not be inside the fragment body

## Vision Service
- Script: `scripts/vision_service/main.py` (FastAPI, port 8002)
- Model: `vikhyatk/moondream2` revision `2025-01-09` — lazy-loaded on first `/analyze` (~1.8GB download)
- GPU: 4-bit quantization when CUDA available (~1.5GB VRAM); CPU fallback
- Conda env: `job-seeker-vision` — separate from job-seeker (torch + transformers live here)
- Create env: `conda env create -f scripts/vision_service/environment.yml`
- Manage: `bash scripts/manage-vision.sh start|stop|restart|status|logs`
- Survey page degrades gracefully to text-only when vision service is down
- ⚠️ Never install vision deps (torch, bitsandbytes, transformers) into the job-seeker env

## Company Research
- Script: `scripts/company_research.py`
- Auto-triggered when a job moves to `phone_screen` in the Interviews kanban
- Three-phase: (1) SearXNG company scrape → (1b) SearXNG news snippets → (2) LLM synthesis
- SearXNG scraper: `/Library/Development/scrapers/companyScraper.py`
- SearXNG Docker: run `docker compose up -d` from `/Library/Development/scrapers/SearXNG/` (port 8888)
- `beautifulsoup4` and `fake-useragent` are installed in job-seeker env (required for scraper)
- News search hits `/search?format=json` — JSON format must be enabled in `searxng-config/settings.yml`
- ⚠️ `settings.yml` owned by UID 977 (container user) — use `docker cp` to update, not direct writes
- ⚠️ `settings.yml` requires `use_default_settings: true` at the top or SearXNG fails schema validation
- `companyScraper` calls `sys.exit()` on missing deps — use `except BaseException` not `except Exception`

## Email Classifier Labels
Six labels: `interview_request`, `rejection`, `offer`, `follow_up`, `survey_received`, `other`
- `survey_received` — links or requests to complete a culture-fit survey/assessment

## Services (managed via Settings → Services tab)
| Service | Port | Notes |
|---------|------|-------|
| Streamlit UI | 8501 | `bash scripts/manage-ui.sh start` |
| Ollama | 11434 | `sudo systemctl start ollama` |
| Claude Code Wrapper | 3009 | `manage-services.sh start` in Post Fight Processing |
| GitHub Copilot Wrapper | 3010 | `manage-copilot.sh start` in Post Fight Processing |
| vLLM Server | 8000 | Manual start only |
| SearXNG | 8888 | `docker compose up -d` in scrapers/SearXNG/ |
| Vision Service | 8002 | `bash scripts/manage-vision.sh start` — moondream2 survey screenshot analysis |

## Notion
- DB: "Tracking Job Applications" (ID: `1bd75cff-7708-8007-8c00-f1de36620a0a`)
- `config/notion.yaml` is gitignored (live token); `.example` is committed
- Field names are non-obvious — always read from `field_map` in `config/notion.yaml`
- "Salary" = Notion title property (unusual — it's the page title field)
- "Job Source" = `multi_select` type
- "Role Link" = URL field
- "Status of Application" = status field; new listings use "Application Submitted"
- Sync pushes `approved` + `applied` jobs; marks them `synced` after

## Key Config Files
- `config/notion.yaml` — gitignored, has token + field_map
- `config/notion.yaml.example` — committed template
- `config/search_profiles.yaml` — titles, locations, boards, custom_boards, exclude_keywords, mission_tags (per profile)
- `config/llm.yaml` — LLM backend priority chain + enabled flags
- `config/tokens.yaml` — gitignored, stores HF token (chmod 600)
- `config/adzuna.yaml` — gitignored, Adzuna API app_id + app_key
- `config/adzuna.yaml.example` — committed template

## Custom Job Board Scrapers
- `scripts/custom_boards/adzuna.py` — Adzuna Jobs API; credentials in `config/adzuna.yaml`
- `scripts/custom_boards/theladders.py` — The Ladders SSR scraper; needs `curl_cffi` installed
- Scrapers registered in `CUSTOM_SCRAPERS` dict in `discover.py`
- Activated per-profile via `custom_boards: [adzuna, theladders]` in `search_profiles.yaml`
- `enrich_all_descriptions()` in `enrich_descriptions.py` covers all sources (not just Glassdoor)
- Home page "Fill Missing Descriptions" button dispatches `enrich_descriptions` task

## Mission Alignment & Accessibility
- Preferred industries: music, animal welfare, children's education (hardcoded in `generate_cover_letter.py`)
- `detect_mission_alignment(company, description)` injects a Para 3 hint into cover letters for aligned companies
- Company research includes an "Inclusion & Accessibility" section (8th section of the brief) in every brief
- Accessibility search query in `_SEARCH_QUERIES` hits SearXNG for ADA/ERG/disability signals
- `accessibility_brief` column in `company_research` table; shown in Interview Prep under ♿ section
- This info is for personal decision-making ONLY — never disclosed in applications
- In generalization: these become `profile.mission_industries` + `profile.accessibility_priority` in `user.yaml`

## Document Rule
Resumes and cover letters live in `/Library/Documents/JobSearch/` or Notion — never committed to this repo.

## AIHawk (LinkedIn Easy Apply)
- Cloned to `aihawk/` (gitignored)
- Config: `aihawk/data_folder/plain_text_resume.yaml` — search FILL_IN for gaps
- Self-ID: non-binary, pronouns any, no disability/drug-test disclosure
- Run: `conda run -n job-seeker python aihawk/main.py`
- Playwright: `conda run -n job-seeker python -m playwright install chromium`

## Git Remote
- Forgejo self-hosted at https://git.opensourcesolarpunk.com (username: pyr0ball)
- `git remote add origin https://git.opensourcesolarpunk.com/pyr0ball/job-seeker.git`

## Subagents
Use `general-purpose` subagent type (not `Bash`) when tasks require file writes.
