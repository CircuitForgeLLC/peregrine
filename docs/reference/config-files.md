# Config Files

All Peregrine configuration lives in the `config/` directory. Gitignored files contain secrets or personal data; `.example` files are committed as templates.

---

## Gitignore Status

| File | Gitignored | Notes |
|------|-----------|-------|
| `config/user.yaml` | Yes | Personal data + wizard state |
| `config/llm.yaml` | No | LLM backends (no secrets by default) |
| `config/search_profiles.yaml` | No | Search configuration (no secrets) |
| `config/resume_keywords.yaml` | No | Scoring keywords (no secrets) |
| `config/blocklist.yaml` | No | Excluded companies (no secrets) |
| `config/email.yaml` | Yes | IMAP credentials |
| `config/notion.yaml` | Yes | Notion token |
| `config/adzuna.yaml` | Yes | Adzuna API credentials |
| `config/craigslist.yaml` | Yes | Craigslist target cities |
| `config/integrations/*.yaml` | Yes | All integration credentials |
| `.env` | Yes | Docker port and path overrides |

---

## config/user.yaml

The primary personal data file. Created by the first-run wizard.

```yaml
# Identity
name: "Your Name"
email: "you@example.com"
phone: "555-000-0000"
linkedin: "linkedin.com/in/yourprofile"
career_summary: >
  Experienced professional with X years in [field].

# Privacy
nda_companies: []             # company names to redact from research briefs

# Mission alignment
mission_preferences:
  music: ""                   # personal note injected into cover letter para 3
  animal_welfare: ""
  education: ""

# Research brief options (personal decision-making only)
candidate_accessibility_focus: false    # adds ADA/WCAG/ERG section
candidate_lgbtq_focus: false            # adds LGBTQIA+ inclusion section

# Tier
tier: free                              # free | paid | premium
dev_tier_override: null                 # overrides tier locally for testing

# Wizard state
wizard_complete: false
wizard_step: 0
dismissed_banners: []

# Storage paths
docs_dir: "~/Documents/JobSearch"
ollama_models_dir: "~/models/ollama"
vllm_models_dir: "~/models/vllm"

# Inference
inference_profile: "remote"             # remote | cpu | single-gpu | dual-gpu

# Service connection settings
services:
  streamlit_port: 8501
  ollama_host: localhost
  ollama_port: 11434
  ollama_ssl: false
  ollama_ssl_verify: true
  vllm_host: localhost
  vllm_port: 8000
  vllm_ssl: false
  vllm_ssl_verify: true
  searxng_host: localhost
  searxng_port: 8888
  searxng_ssl: false
  searxng_ssl_verify: true
```

All personal data access in `scripts/` goes through `scripts/user_profile.py` (`UserProfile` class) — never read this file directly in scripts.

---

## config/llm.yaml

LLM backend definitions and fallback chains. Not gitignored (contains no secrets by default — API keys come from environment variables).

```yaml
backends:
  ollama:
    type: openai_compat
    base_url: http://localhost:11434/v1
    api_key: ollama                    # placeholder; Ollama ignores the key
    model: llama3.1:8b
    enabled: true
    supports_images: false

  ollama_research:
    type: openai_compat
    base_url: http://localhost:11434/v1
    api_key: ollama
    model: llama3.1:8b                 # can be a different model for research
    enabled: true
    supports_images: false

  vllm:
    type: openai_compat
    base_url: http://localhost:8000/v1
    api_key: ""
    model: __auto__                    # auto-detect first loaded model
    enabled: true
    supports_images: false

  claude_code:
    type: openai_compat
    base_url: http://localhost:3009/v1
    api_key: any
    model: claude-code-terminal
    enabled: false
    supports_images: true

  github_copilot:
    type: openai_compat
    base_url: http://localhost:3010/v1
    api_key: any
    model: gpt-4o
    enabled: false
    supports_images: false

  anthropic:
    type: anthropic
    api_key_env: ANTHROPIC_API_KEY     # name of environment variable
    model: claude-sonnet-4-6
    enabled: false
    supports_images: true

  vision_service:
    type: vision_service
    base_url: http://localhost:8002
    enabled: true
    supports_images: true

fallback_order:
  - ollama
  - claude_code
  - vllm
  - github_copilot
  - anthropic

research_fallback_order:
  - claude_code
  - vllm
  - ollama_research
  - github_copilot
  - anthropic

vision_fallback_order:
  - vision_service
  - claude_code
  - anthropic
```

See [LLM Router](llm-router.md) for full documentation.

---

## config/search_profiles.yaml

Defines what jobs to search for. Multiple profiles can coexist.

```yaml
profiles:
  - name: cs_leadership                # unique profile identifier
    titles:
      - Customer Success Manager
      - Director of Customer Success
    locations:
      - Remote
      - San Francisco Bay Area, CA
    boards:
      - linkedin
      - indeed
      - glassdoor
      - zip_recruiter
      - google
    custom_boards:
      - adzuna
      - theladders
      - craigslist
    exclude_keywords:                   # job titles containing these are dropped
      - sales
      - account executive
      - SDR
    results_per_board: 75
    hours_old: 240                      # only fetch jobs posted in last N hours
    mission_tags:                       # optional: links to mission_preferences
      - music
```

---

## config/resume_keywords.yaml

Keywords extracted from your resume, used for match scoring. Managed via **Settings → Skills**.

```yaml
keywords:
  - Customer Success
  - Churn reduction
  - Salesforce
  - SQL
  - Stakeholder management
  - QBR
  - onboarding
```

---

## config/blocklist.yaml

Companies or domains to exclude from discovery results entirely.

```yaml
blocked_companies:
  - "Pyramid Scheme Inc"
  - "Sketchy Startup"

blocked_domains:
  - "mlm-company.com"
```

---

## config/email.yaml

IMAP email sync credentials. Gitignored. See [Email Sync](../user-guide/email-sync.md) for setup.

```yaml
host: imap.gmail.com
port: 993
use_ssl: true
username: your.email@gmail.com
password: xxxx-xxxx-xxxx-xxxx     # Gmail App Password (16 chars, no spaces)
sent_folder: ""                    # leave blank to auto-detect
lookback_days: 90
todo_label: ""                     # optional: Gmail label to monitor
```

---

## config/notion.yaml

Notion integration credentials. Gitignored.

```yaml
token: "secret_..."               # Notion integration token
database_id: "1bd75cff-..."       # database ID from the URL

# Notion property names → Peregrine field names
field_map:
  title: "Salary"                 # Notion title property (unusual — it's the page title)
  status: "Status of Application"
  company: "Company"
  url: "Role Link"
  source: "Job Source"            # multi_select type
  location: "Location"
  applied_at: "Date Applied"
```

Field names in Notion are non-obvious. Always read them from `field_map` rather than guessing.

---

## config/adzuna.yaml

Adzuna Jobs API credentials. Gitignored.

```yaml
app_id: "12345678"
app_key: "abcdefgh1234567890abcdefgh123456"
country: "us"                      # two-letter country code
```

Get credentials at [developer.adzuna.com](https://developer.adzuna.com/).

---

## config/craigslist.yaml

Target city slugs for the Craigslist scraper. Gitignored.

```yaml
cities:
  - sfbay
  - nyc
  - seattle
  - chicago
```

Find slugs at `https://www.craigslist.org/about/sites`.

---

## config/integrations/

One YAML file per integration, created when you test and save credentials in the wizard or Settings. All files in this directory are gitignored.

```
config/integrations/
  notion.yaml
  airtable.yaml
  google_sheets.yaml
  google_drive.yaml
  dropbox.yaml
  onedrive.yaml
  mega.yaml
  nextcloud.yaml
  google_calendar.yaml
  apple_calendar.yaml
  slack.yaml
  discord.yaml
  home_assistant.yaml
```

Each file contains only the fields defined by that integration's `fields()` method. Example for Discord:

```yaml
webhook_url: "https://discord.com/api/webhooks/..."
```

---

## .env

Docker port and path overrides. Created from `.env.example` by `install.sh`. Gitignored.

```bash
# Ports (change if defaults conflict with existing services)
STREAMLIT_PORT=8501
OLLAMA_PORT=11434
VLLM_PORT=8000
SEARXNG_PORT=8888
VISION_PORT=8002

# GPU settings (written by preflight.py)
RECOMMENDED_PROFILE=single-gpu
CPU_OFFLOAD_GB=0                   # KV cache RAM offload for low-VRAM GPUs
```
