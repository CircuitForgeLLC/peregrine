# Changelog

All notable changes to Peregrine are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [Unreleased]

### Added
- Expanded first-run wizard: 7-step onboarding with GPU detection, tier selection,
  resume upload/parsing, LLM inference test, search profile builder, integration cards
- Tier system: free / paid / premium feature gates (`app/wizard/tiers.py`)
- 13 integration drivers: Notion, Google Sheets, Airtable, Google Drive, Dropbox,
  OneDrive, MEGA, Nextcloud, Google Calendar, Apple Calendar, Slack, Discord,
  Home Assistant — with auto-discovery registry
- Resume parser: PDF (pdfplumber) and DOCX (python-docx) + LLM structuring
- `wizard_generate` background task type with iterative refinement (feedback loop)
- Dismissible setup banners on Home page (13 contextual prompts)
- Developer tab in Settings: tier override selectbox and wizard reset button
- Integrations tab in Settings: connect / test / disconnect all 12 non-Notion drivers
- HuggingFace token moved to Developer tab
- `params` column in `background_tasks` for wizard task payloads
- `wizard_complete`, `wizard_step`, `tier`, `dev_tier_override`, `dismissed_banners`,
  `effective_tier` added to UserProfile
- MkDocs documentation site (Material theme, 20 pages)
- `LICENSE-MIT` and `LICENSE-BSL`, `CONTRIBUTING.md`, `CHANGELOG.md`

### Changed
- `app.py` wizard gate now checks `wizard_complete` flag in addition to file existence
- Settings tabs reorganised: Integrations tab added, Developer tab conditionally shown
- HF token removed from Services tab (now Developer-only)

### Removed
- Dead `app/pages/3_Resume_Editor.py` (functionality lives in Settings → Resume Profile)

---

## [0.1.0] — 2026-02-01

### Added
- Initial release: JobSpy discovery pipeline, SQLite staging, Streamlit UI
- Job Review, Apply Workspace, Interviews kanban, Interview Prep, Survey Assistant
- LLM router with fallback chain (Ollama, vLLM, Claude Code wrapper, Anthropic)
- Notion sync, email sync with IMAP classifier, company research with SearXNG
- Background task runner with daemon threads
- Vision service (moondream2) for survey screenshot analysis
- Adzuna, The Ladders, and Craigslist custom board scrapers
- Docker Compose profiles: remote, cpu, single-gpu, dual-gpu
- `setup.sh` cross-platform dependency installer
- `scripts/preflight.py` and `scripts/migrate.py`
