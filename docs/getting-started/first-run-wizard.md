# First-Run Wizard

When you open Peregrine for the first time, the setup wizard launches automatically. It walks through seven steps and saves your progress after each one — if your browser closes or the server restarts, it resumes where you left off.

---

## Step 1 — Hardware

Peregrine detects NVIDIA GPUs using `nvidia-smi` and reports:

- Number of GPUs found
- VRAM per GPU
- Available system RAM

Based on this, it recommends a Docker Compose profile:

| Recommendation | Condition |
|---------------|-----------|
| `remote` | No GPU detected |
| `cpu` | GPU detected but VRAM < 4 GB |
| `single-gpu` | One GPU with VRAM >= 4 GB |
| `dual-gpu` | Two or more GPUs |

You can override the recommendation and select any profile manually. The selection is written to `config/user.yaml` as `inference_profile`.

---

## Step 2 — Tier

Select your Peregrine tier:

| Tier | Description |
|------|-------------|
| **Free** | Job discovery, matching, and basic pipeline — no LLM features |
| **Paid** | Adds cover letters, company research, email sync, integrations, and all AI features |
| **Premium** | Adds fine-tuning and multi-user support |

Your tier is written to `config/user.yaml` as `tier`.

**Dev tier override** — for local testing without a paid licence, set `dev_tier_override: premium` in `config/user.yaml`. This is for development use only and has no effect on production deployments.

See [Tier System](../reference/tier-system.md) for the full feature gate table.

---

## Step 3 — Identity

Enter your personal details. These are stored locally in `config/user.yaml` and used to personalise cover letters and research briefs.

| Field | Description |
|-------|-------------|
| Name | Your full name |
| Email | Primary contact email |
| Phone | Contact phone number |
| LinkedIn | LinkedIn profile URL |
| Career summary | 2–4 sentence professional summary — used in cover letters and interview prep |

**LLM-assisted writing (Paid):** If you have a paid tier, the wizard offers to generate your career summary from a few bullet points using your configured LLM backend.

---

## Step 4 — Resume

Two paths are available:

### Upload PDF or DOCX

Upload your existing resume. The LLM parses it and extracts:
- Work experience (employer, title, dates, bullets)
- Education
- Skills
- Certifications

The extracted data is stored in `config/user.yaml` and used when generating cover letters.

### Guided form builder

Fill in each section manually using structured form fields. Useful if you do not have a digital resume file ready, or if the parser misses something important.

Both paths produce the same data structure. You can mix them — upload first, then edit the result in the form.

---

## Step 5 — Inference

Configure which LLM backends Peregrine uses. Backends are tried in priority order; if the first fails, Peregrine falls back to the next.

Available backend types:

| Type | Examples | Notes |
|------|---------|-------|
| `openai_compat` | Ollama, vLLM, Claude Code wrapper, Copilot wrapper | Any OpenAI-compatible API |
| `anthropic` | Claude via Anthropic API | Requires `ANTHROPIC_API_KEY` env var |
| `vision_service` | Moondream2 local service | Used for survey screenshot analysis only |

For each backend you want to enable:

1. Enter the base URL (e.g. `http://localhost:11434/v1` for Ollama)
2. Enter an API key if required (Anthropic, OpenAI)
3. Click **Test** — Peregrine pings the `/health` endpoint and attempts a short completion

The full backend configuration is written to `config/llm.yaml`. You can edit it directly later via **Settings → LLM Backends**.

!!! tip "Recommended minimum"
    Enable at least Ollama with a general-purpose model (e.g. `llama3.1:8b`) for research tasks, and either Ollama or Anthropic for cover letter generation. The wizard will not block you if no backend is configured, but most features will not work.

---

## Step 6 — Search

Define what jobs to look for. Search configuration is written to `config/search_profiles.yaml`.

| Field | Description |
|-------|-------------|
| Profile name | A label for this search profile (e.g. `cs_leadership`) |
| Job titles | List of titles to search for (e.g. `Customer Success Manager`, `TAM`) |
| Locations | City/region strings or `Remote` |
| Boards | Standard boards: `linkedin`, `indeed`, `glassdoor`, `zip_recruiter`, `google` |
| Custom boards | Additional scrapers: `adzuna`, `theladders`, `craigslist` |
| Exclude keywords | Jobs containing these words in the title are dropped |
| Results per board | Max jobs to fetch per board per run |
| Hours old | Only fetch jobs posted within this many hours |

You can create multiple profiles (e.g. one for remote roles, one for a target industry). Run them all from the Home page or run a specific one.

---

## Step 7 — Integrations

Connect optional external services. All integrations are optional — skip this step if you want to use Peregrine without external accounts.

Available integrations:

**Job tracking (Paid):** Notion, Airtable, Google Sheets

**Document storage (Free):** Google Drive, Dropbox, OneDrive, MEGA, Nextcloud

**Calendar (Paid):** Google Calendar, Apple Calendar (CalDAV)

**Notifications (Paid for Slack; Free for Discord and Home Assistant):** Slack, Discord, Home Assistant

Each integration has a connection card with the required credentials. Click **Test** to verify the connection before saving. Credentials are written to `config/integrations/<name>.yaml` (gitignored).

See [Integrations](../user-guide/integrations.md) for per-service details.

---

## Crash Recovery

The wizard saves your progress to `config/user.yaml` after each step is completed (`wizard_step` field). If anything goes wrong:

- Restart Peregrine and navigate to http://localhost:8501
- The wizard resumes at the last completed step

---

## Re-entering the Wizard

To go through the wizard again (e.g. to change your search profile or swap LLM backends):

1. Open **Settings**
2. Go to the **Developer** tab
3. Click **Reset wizard**

This sets `wizard_complete: false` and `wizard_step: 0` in `config/user.yaml`. Your previously entered data is preserved as defaults.
