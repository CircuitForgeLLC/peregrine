# Job Seeker Platform — Design Document
**Date:** 2026-02-20
**Status:** Approved
**Candidate:** Meghan McCann

---

## Overview

A monorepo project at `/devl/job-seeker/` that integrates three FOSS tools into a
cohesive job search pipeline: automated discovery (JobSpy), resume-to-listing keyword
matching (Resume Matcher), and automated application submission (AIHawk). Job listings
and interactive documents are tracked in Notion; source documents live in
`/Library/Documents/JobSearch/`.

---

## Project Structure

```
/devl/job-seeker/
├── config/
│   ├── search_profiles.yaml    # JobSpy queries (titles, locations, boards)
│   ├── llm.yaml                # LLM router: backends + fallback order
│   └── notion.yaml             # Notion DB IDs and field mappings
├── aihawk/                     # git clone — Auto_Jobs_Applier_AIHawk
├── resume_matcher/             # git clone — Resume-Matcher
├── scripts/
│   ├── discover.py             # JobSpy → deduplicate → push to Notion
│   ├── match.py                # Notion job URL → Resume Matcher → write score back
│   └── llm_router.py           # LLM abstraction layer with priority fallback chain
├── docs/plans/                 # Design and implementation docs (no resume files)
├── environment.yml             # conda env spec (env name: job-seeker)
└── .gitignore
```

**Document storage rule:** Resumes, cover letters, and any interactable documents live
in `/Library/Documents/JobSearch/` or Notion — never committed to this repo.

---

## Architecture

### Data Flow

```
JobSpy (LinkedIn / Indeed / Glassdoor / ZipRecruiter)
    └─▶ discover.py
            ├─ deduplicate by URL against existing Notion records
            └─▶ Notion DB  (Status: "New")

Notion DB  (daily review — decide what to pursue)
    └─▶ match.py <notion-page-url>
            ├─ fetch job description from listing URL
            ├─ run Resume Matcher vs. /Library/Documents/JobSearch/Meghan_McCann_Resume_02-19-2025.pdf
            └─▶ write Match Score + Keyword Gaps back to Notion page

AIHawk  (when ready to apply)
    ├─ reads config pointing to same resume + personal_info.yaml
    ├─ llm_router.py → best available LLM backend
    ├─ submits LinkedIn Easy Apply
    └─▶ Notion status → "Applied"
```

---

## Notion Database Schema

| Field         | Type     | Notes                                                      |
|---------------|----------|------------------------------------------------------------|
| Job Title     | Title    | Primary identifier                                         |
| Company       | Text     |                                                            |
| Location      | Text     |                                                            |
| Remote        | Checkbox |                                                            |
| URL           | URL      | Deduplication key                                          |
| Source        | Select   | LinkedIn / Indeed / Glassdoor / ZipRecruiter               |
| Status        | Select   | New → Reviewing → Applied → Interview → Offer → Rejected   |
| Match Score   | Number   | 0–100, written by match.py                                 |
| Keyword Gaps  | Text     | Comma-separated missing keywords from Resume Matcher       |
| Salary        | Text     | If listed                                                  |
| Date Found    | Date     | Set at discovery time                                      |
| Notes         | Text     | Manual field                                               |

---

## LLM Router (`scripts/llm_router.py`)

Single `complete(prompt, system=None)` interface. On each call: health-check each
backend in configured order, use the first that responds. Falls back silently on
connection error, timeout, or 5xx. Logs which backend was used.

All backends except Anthropic use the `openai` Python package (OpenAI-compatible
endpoints). Anthropic uses the `anthropic` package.

### `config/llm.yaml`

```yaml
fallback_order:
  - claude_code      # port 3009 — Claude via local pipeline (highest quality)
  - ollama           # port 11434 — local, always-on
  - vllm             # port 8000 — start when needed
  - github_copilot   # port 3010 — Copilot via gh token
  - anthropic        # cloud fallback, burns API credits

backends:
  claude_code:
    type: openai_compat
    base_url: http://localhost:3009/v1
    model: claude-code-terminal
    api_key: "any"

  ollama:
    type: openai_compat
    base_url: http://localhost:11434/v1
    model: llama3.2
    api_key: "ollama"

  vllm:
    type: openai_compat
    base_url: http://localhost:8000/v1
    model: __auto__
    api_key: ""

  github_copilot:
    type: openai_compat
    base_url: http://localhost:3010/v1
    model: gpt-4o
    api_key: "any"

  anthropic:
    type: anthropic
    model: claude-sonnet-4-6
    api_key_env: ANTHROPIC_API_KEY
```

---

## Job Search Profile

### `config/search_profiles.yaml` (initial)

```yaml
profiles:
  - name: cs_leadership
    titles:
      - "Customer Success Manager"
      - "Director of Customer Success"
      - "VP Customer Success"
      - "Head of Customer Success"
      - "Technical Account Manager"
      - "Revenue Operations Manager"
      - "Customer Experience Lead"
    locations:
      - "Remote"
      - "San Francisco Bay Area, CA"
    boards:
      - linkedin
      - indeed
      - glassdoor
      - zip_recruiter
    results_per_board: 25
    remote_only: false          # remote preferred but Bay Area in-person ok
    hours_old: 72               # listings posted in last 3 days
```

---

## Conda Environment

New dedicated env `job-seeker` (not base). Core packages:

- `python-jobspy` — job scraping
- `notion-client` — Notion API
- `openai` — OpenAI-compatible calls (Ollama, vLLM, Copilot, Claude pipeline)
- `anthropic` — Anthropic API fallback
- `pyyaml` — config parsing
- `pandas` — CSV handling and dedup
- Resume Matcher dependencies (sentence-transformers, streamlit — installed from clone)

Resume Matcher Streamlit UI runs on port **8501** (confirmed clear).

---

## Port Map

| Port  | Service                        | Status         |
|-------|--------------------------------|----------------|
| 3009  | Claude Code OpenAI wrapper     | Start via manage.sh in Post Fight Processing |
| 3010  | GitHub Copilot wrapper         | Start via manage-copilot.sh                  |
| 11434 | Ollama                         | Running        |
| 8000  | vLLM                           | Start when needed                            |
| 8501  | Resume Matcher (Streamlit)     | Start when needed                            |

---

## Out of Scope (this phase)

- Scheduled/cron automation (run discover.py manually for now)
- Email/SMS alerts for new listings
- ATS resume rebuild (separate task)
- Applications to non-LinkedIn platforms via AIHawk
