# Design: Generalizing Job Seeker for Public Use

**Date:** 2026-02-24
**Status:** Approved
**Target directory:** `/Library/Development/devl/job-seeker-app/`

---

## Overview

Fork the personal job-seeker app into a fully generalized version suitable for any job seeker.
The personal version (`/devl/job-seeker/`) is preserved as-is on `main`.
The public version is a separate local directory with a fresh git repo — no shared history.

Core goals:
- Extract every hard-coded personal reference into a `config/user.yaml` profile
- Docker Compose stack with profiles covering all GPU/inference configurations
- First-run wizard that gates the app until the user is configured
- Optional fine-tune wizard in Settings for users with a cover letter corpus and a GPU

---

## Architecture

The app runs via `docker compose` with four named profiles:

| Profile | Containers | Use case |
|---|---|---|
| `remote` | app + searxng | No GPU; all LLM calls go to external APIs |
| `cpu` | app + ollama + searxng | No GPU; local models run on CPU (slow) |
| `single-gpu` | app + ollama + searxng | One GPU shared for cover letters + research |
| `dual-gpu` | app + ollama + vllm + searxng | GPU 0 = Ollama, GPU 1 = vLLM |

**SearXNG always runs** regardless of profile — it's lightweight and useful in every mode.

**Vision Service** runs as a separate container only in `single-gpu` and `dual-gpu` profiles.
In `remote` profile, vision falls back to `claude_code` / `anthropic` backends.
In `cpu` profile, vision falls back to cloud backends (moondream2 on CPU is impractically slow).

SQLite lives in a named Docker volume mount (`./data/`). No separate DB container.

CompanyScraper (`companyScraper.py`) is bundled directly into the app image — no external
path dependency on the host.

The Claude Code Wrapper and GitHub Copilot Wrapper service entries are removed from the
Services tab entirely. Users bring their own OpenAI-compatible endpoints via `config/llm.yaml`.

---

## User Profile (`config/user.yaml`)

Single source of truth for all personal data. Checked at startup — if absent, the first-run
wizard is shown before any other page is accessible.

```yaml
# Identity — drives all LLM personas, PDF headers, UI labels
name: ""
email: ""
phone: ""
linkedin: ""
career_summary: ""        # paragraph injected into cover letter system prompt

# Sensitive employers — masked in research briefs
nda_companies: []         # e.g. ["UpGuard"] → "enterprise security vendor (NDA)"

# Local file paths
docs_dir: "~/Documents/JobSearch"       # cover letter PDFs + corpus
ollama_models_dir: "~/models/ollama"   # maps to OLLAMA_MODELS in container
vllm_models_dir: "~/models/vllm"       # mounted into vllm container

# Active hardware profile
inference_profile: "remote"  # remote | cpu | single-gpu | dual-gpu

# Service connection config
services:
  streamlit_port: 8501

  ollama_host: localhost
  ollama_port: 11434
  ollama_ssl: false
  ollama_ssl_verify: true   # set false for self-signed certs

  vllm_host: localhost
  vllm_port: 8000
  vllm_ssl: false
  vllm_ssl_verify: true

  searxng_host: localhost
  searxng_port: 8888
  searxng_ssl: false
  searxng_ssl_verify: true
```

All service base URLs in `config/llm.yaml` are **derived values** — auto-generated from the
`services` block whenever the user saves their profile. Users never hand-edit URLs.

Health checks in the Services tab switch from raw TCP socket checks to
`requests.get(url, verify=ssl_verify)` so they work against HTTPS endpoints and self-signed certs.

---

## First-Run Wizard

A dedicated Streamlit page shown instead of normal navigation when `config/user.yaml` is absent.
Five steps with a progress bar; all steps write to a staging dict, committed to disk on the
final step only.

### Step 1 — Hardware Detection
- Auto-detect CUDA GPUs via `nvidia-smi` or `torch.cuda.device_count()`
- Check NVIDIA Container Toolkit availability (`docker info | grep nvidia`)
- Suggest a profile based on findings; user can override
- Warn if suggested profile requires toolkit not installed, with link to docs

### Step 2 — Identity
- Name, email, phone, LinkedIn URL
- Career summary (multi-line text area): used as the LLM cover letter persona
- Example placeholder text drawn from the resume profile YAML if AIHawk is present

### Step 3 — Sensitive Employers
- Optional; skip button prominent
- Chip-based add/remove (same UI as Skills tab)
- Explanation: "Employers listed here will appear as 'previous employer (NDA)' in research briefs"

### Step 4 — Inference & API Keys
- Shows only fields relevant to the selected profile
  - `remote`: Anthropic API key, optional OpenAI-compat endpoint URL + key
  - `cpu` / `single-gpu` / `dual-gpu`: Ollama model name for cover letters, vLLM model path
- Port/host/SSL fields for each active service (collapsed under "Advanced" by default)

### Step 5 — Notion (Optional)
- Integration token + database ID
- Test connection button
- Skip button prominent; can be configured later in Settings

**On completion:** writes `config/user.yaml`, `config/notion.yaml` (if provided),
auto-generates `config/llm.yaml` base URLs from service config, redirects to Home.

---

## Settings Changes

### New: My Profile tab
Editable form for all `user.yaml` fields post-setup. Saving regenerates `config/llm.yaml`
base URLs automatically. Replaces scattered "Meghan's" references in existing tab captions.

### Updated: Services tab
- Reads port/host from `profile.services.*` instead of hard-coded values
- Start/stop commands switch to `docker compose --profile <profile> up/stop <service>`
- Health checks use `requests.get` with SSL support
- Claude Code Wrapper and Copilot Wrapper entries removed
- vLLM model dir reads from `profile.vllm_models_dir`
- SearXNG Docker cwd replaced with compose command (no host path needed)

### New: Fine-Tune Wizard tab (optional, GPU only)
Shown only when `inference_profile` is `single-gpu` or `dual-gpu`.

1. **Upload corpus** — drag-and-drop cover letters (PDF, DOCX, TXT)
2. **Preview pairs** — shows extracted (job description snippet → cover letter) training pairs;
   user can remove bad examples
3. **Configure & train** — base model selector (defaults to currently loaded Ollama model),
   epochs slider, runs `finetune_local.py` as a background task
4. **Register** — on completion, `ollama create <username>-cover-writer -f Modelfile`,
   updates `config/llm.yaml` to use the new model

Skipped entirely in `remote` and `cpu` profiles with a clear explanation.

---

## Code Changes — Hard-Coded Reference Extraction

A `UserProfile` class (thin wrapper around `config/user.yaml`) is imported wherever
personal data is currently hard-coded.

| Location | Current | Generalized |
|---|---|---|
| `company_research.py` prompts | `"Meghan McCann"` | `profile.name` |
| `company_research.py` | `_NDA_COMPANIES = {"upguard"}` | `profile.nda_companies` |
| `company_research.py` | `_SCRAPER_DIR = Path("/Library/...")` | bundled in container |
| `generate_cover_letter.py` | `SYSTEM_CONTEXT` with Meghan's bio | `profile.career_summary` |
| `generate_cover_letter.py` | `LETTERS_DIR = Path("/Library/...")` | `profile.docs_dir` |
| `generate_cover_letter.py` | `_MISSION_SIGNALS` / `_MISSION_NOTES` (hardcoded) | `profile.mission_industries` list; First-Run Wizard step |
| `4_Apply.py` | contact block with name/email/phone | `profile.*` |
| `4_Apply.py` | `DOCS_DIR = Path("/Library/...")` | `profile.docs_dir` |
| `5_Interviews.py` email assistant | `"Meghan McCann is a Customer Success..."` | `profile.name + profile.career_summary` |
| `6_Interview_Prep.py` | `"Meghan"` in interviewer prompts | `profile.name` |
| `7_Survey.py` `_SURVEY_SYSTEM` | "The candidate values collaborative teamwork, clear communication, growth, and impact." | `profile.career_summary` or user-editable survey persona field |
| `scripts/vision_service/main.py` | `model_id = "vikhyatk/moondream2"`, `revision = "2025-01-09"` | configurable in `config/llm.yaml` vision_service block |
| `match.py` | `RESUME_PATH = Path("/Library/...Meghan_McCann_Resume...")` | configurable in Settings |
| `Home.py` | `"Meghan's Job Search"` | `f"{profile.name}'s Job Search"` |
| `finetune_local.py` | all `/Library/` paths + `"meghan-cover-writer"` | `profile.*` |
| `2_Settings.py` | `PFP_DIR`, hard-coded service paths | removed / compose-driven |
| `config/llm.yaml` | hard-coded `base_url` values | auto-generated from `user.yaml` |
| `config/search_profiles.yaml` | `mission_tags` on profiles (implicit) | `profile.mission_industries` drives profile generation in wizard |
| `config/adzuna.yaml` | per-user API credentials | First-Run Wizard step → `config/adzuna.yaml` (gitignored) |

### New fields needed in `config/user.yaml` (generalization)

```yaml
# Mission-aligned industries — drives cover letter Para 3 and research accessibility section
# Options: music, animal_welfare, education (extensible)
mission_industries: []

# Accessibility priority — adds Inclusion & Accessibility section to every research brief.
# This is for the candidate's personal decision-making; never disclosed in applications.
accessibility_priority: true

# Custom board API credentials
custom_boards:
  adzuna:
    app_id: ""
    app_key: ""
  # theladders: no credentials needed (curl_cffi scraper)
```

The First-Run Wizard gains a **Step 2b — Personal Preferences** screen (between Identity and Sensitive Employers):
- Checkboxes for preferred industries (Music, Animal Welfare, Education, Other...)
- "Other" opens a free-text field to add custom industry signals
- Accessibility priority toggle (on by default, explains what it does: "Adds an accessibility assessment to every company research brief so you can evaluate companies on your own terms. This information stays private — it's never sent to employers.")
- Custom board credentials (Adzuna app ID/key) with a "Test" button

---

## Docker Compose Structure

```
compose.yml              # all services + profiles
.env                     # generated by wizard (resolved paths, ports)
Dockerfile               # app image (Streamlit + companyScraper bundled)
docker/
  searxng/
    settings.yml         # pre-configured for JSON format output
  ollama/
    entrypoint.sh        # pulls default model on first start if none present
```

GPU passthrough uses `deploy.resources.reservations.devices` (NVIDIA Container Toolkit).
Wizard warns and links to install docs if toolkit is missing when a GPU profile is selected.

The `.env` file is generated (never hand-edited) and gitignored. It contains resolved
absolute paths for volume mounts (tilde-expanded from `user.yaml`) and port numbers.

---

## Out of Scope (this version)

- conda + local install path (future track)
- Multi-user / auth (single-user app)
- PostgreSQL migration (SQLite sufficient)
- Windows support
- AIHawk LinkedIn Easy Apply generalization (too tightly coupled to personal config)

---

## Backlog — Custom Job Source Scrapers

Not supported by JobSpy; would need custom scrapers plugged into `scripts/discover.py`:

| Priority | Site | Notes |
|----------|------|-------|
| 1 | [Adzuna](https://www.adzuna.com) | Free public API (api.adzuna.com) — cleanest integration path |
| 2 | [The Ladders](https://www.theladders.com) | Focuses on $100K+ roles — good signal-to-noise for senior CS/ops positions |
| 3 | Craigslist | HTML scrape, highly inconsistent by region; likely needs its own dedicated ingestion queue separate from the main discovery run |
| — | Monster.com | Low priority — requires session/auth, likely needs Playwright; skip until others are done |

**Integration pattern:** Each custom source should return the same `pd.DataFrame` schema as JobSpy (`title`, `company`, `job_url`, `location`, `is_remote`, `description`, `site`) so `run_discovery` can consume it without changes. Cleanest as a separate `scripts/custom_boards/` module.

**LLM-guided profile setup wizard** (for generic build): First-run wizard that walks a new user through their work history and desired search terms, auto-generating `plain_text_resume.yaml` and `search_profiles.yaml`. See First-Run Wizard section above for hardware/identity/inference steps; this extends Step 2 with a career interview flow.

---

## Migration from Personal Version

No automated migration. The personal version stays on its own repo. If the user wants to
carry over their `staging.db`, `config/*.yaml`, or cover letter corpus, they copy manually.
The wizard's field defaults can be pre-populated from the personal version's config files
if detected at a well-known path — but this is a nice-to-have, not required.
