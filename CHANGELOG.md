# Changelog

All notable changes to Peregrine are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [Unreleased]

---

## [0.4.0] — 2026-03-13

### Added
- **LinkedIn profile import** — one-click import from a public LinkedIn profile URL
  (Playwright headless Chrome, no login required) or from a LinkedIn data export zip.
  Staged to `linkedin_stage.json` so the profile is parsed once and reused across
  sessions without repeated network requests. Available on all tiers including Free.
  - `scripts/linkedin_utils.py` — HTML parser with ordered CSS selector fallbacks;
    extracts name, experience, education, skills, certifications, summary
  - `scripts/linkedin_scraper.py` — Playwright URL scraper + export zip CSV parser;
    atomic staging file write; URL validation; robust error handling
  - `scripts/linkedin_parser.py` — staging file reader; re-runs HTML parser on stored
    raw HTML so selector improvements apply without re-scraping
  - `app/components/linkedin_import.py` — shared Streamlit widget (status bar, preview,
    URL import, advanced zip upload) used by both wizard and Settings
  - Wizard step 3: new "🔗 LinkedIn" tab alongside Upload and Build Manually
  - Settings → Resume Profile: collapsible "Import from LinkedIn" expander
  - Dockerfile: Playwright Chromium install added to Docker image

### Fixed
- **Cloud mode perpetual onboarding loop** — wizard gate in `app.py` now reads
  `get_config_dir()/user.yaml` (per-user in cloud, repo-level locally) instead of a
  hardcoded repo path; completing the wizard now correctly exits it in cloud mode
- **Cloud resume YAML path** — wizard step 3 writes resume to per-user `CONFIG_DIR`
  instead of the shared repo `config/` (would have merged all cloud users' data)
- **Cloud session redirect** — missing/invalid session token now JS-redirects to
  `circuitforge.tech/login` instead of showing a raw error message
- Removed remaining AIHawk UI references (`Home.py`, `4_Apply.py`, `migrate.py`)

---

## [0.3.0] — 2026-03-06

### Added
- **Feedback button** — in-app issue reporting with screenshot paste support; posts
  directly to Forgejo as structured issues; available from sidebar on all pages
  (`app/feedback.py`, `scripts/feedback_api.py`, `app/components/paste_image.py`)
- **BYOK cloud backend detection** — `scripts/byok_guard.py`: pure Python detection
  engine with full unit test coverage (18 tests); classifies backends as cloud or local
  based on type, `base_url` heuristic, and opt-out `local: true` flag
- **BYOK activation warning** — one-time acknowledgment required in Settings when a
  new cloud LLM backend is enabled; shows data inventory (what leaves your machine,
  what stays local), provider policy links; ack state persisted to `config/user.yaml`
  under `byok_acknowledged_backends`
- **Sidebar cloud LLM indicator** — amber badge on every page when any cloud backend
  is active; links to Settings; disappears when reverted to local-only config
- **LLM suggest: search terms** — three-angle analysis from resume (job titles,
  skills keywords, and exclude terms to filter irrelevant listings)
- **LLM suggest: resume keywords** — skills gap analysis against job descriptions
- **LLM Suggest button** in Settings → Search → Skills & Keywords section
- **Backup/restore script** (`scripts/backup.py`) — multi-instance and legacy support
- `PRIVACY.md` — short-form privacy notice linked from Settings

### Changed
- Settings save button for LLM Backends now gates on cloud acknowledgment before
  writing `config/llm.yaml`

### Fixed
- Settings widget crash on certain rerun paths
- Docker service controls in Settings → System tab
- `DEFAULT_DB` now respects `STAGING_DB` environment variable (was silently ignoring it)
- `generate()` in cover letter refinement now correctly passes `max_tokens` kwarg

### Security / Privacy
- Full test suite anonymized — fictional "Alex Rivera" replaces all real personal data
  in test fixtures (`tests/test_cover_letter.py`, `test_imap_sync.py`,
  `test_classifier_adapters.py`, `test_db.py`)
- Complete PII scrub from git history: real name, email address, and phone number
  removed from all 161 commits across both branches via `git filter-repo`

---

## [0.2.0] — 2026-02-26

### Added
- Cover letter iterative refinement: "Refine with Feedback" expander in Apply Workspace;
  `generate()` accepts `previous_result`/`feedback`; task params passed through `submit_task`
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
