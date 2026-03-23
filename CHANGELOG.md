# Changelog

All notable changes to Peregrine are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [Unreleased]

---

## [0.7.0] — 2026-03-22

### Added
- **Vue 3 SPA — beta access for paid tier** — The new Vue 3 frontend (built with
  Vite + UnoCSS) is now merged into `main` and available to paid-tier subscribers
  as an opt-in beta. The Streamlit UI remains the default and will continue to
  receive full support.
  - `web/` — full Vue 3 SPA source (components, stores, router, composables,
    views) from `feature/vue-spa`
  - `web/src/components/ClassicUIButton.vue` — one-click switch back to the
    Classic (Streamlit) UI; sets `prgn_ui=streamlit` cookie and appends
    `?prgn_switch=streamlit` so `user.yaml` stays in sync
  - `web/src/composables/useFeatureFlag.ts` — reads `prgn_demo_tier` cookie for
    demo toolbar visual consistency (display-only, not an authoritative gate)

- **UI switcher** — Reddit-style opt-in to the Vue SPA with durable preference
  persistence and graceful fallback.
  - `app/components/ui_switcher.py` — `sync_ui_cookie()`, `switch_ui()`,
    `render_banner()`, `render_settings_toggle()`
  - `scripts/user_profile.py` — `ui_preference` field (`streamlit` | `vue`,
    default: `streamlit`) with round-trip `save()`
  - `app/wizard/tiers.py` — `vue_ui_beta: "paid"` feature key; `demo_tier`
    keyword arg on `can_use()` for thread-safe demo mode simulation
  - Banner (dismissible, paid tier only) + Settings → System → Deployment toggle
  - Caddy cookie routing: `prgn_ui=vue` → nginx Vue SPA; absent/`streamlit` →
    Streamlit. 502 fallback clears cookie and redirects with `?ui_fallback=1`

- **Demo toolbar** — slim full-width tier-simulation bar for `DEMO_MODE`
  instances. Free / Paid / Premium pills let demo visitors explore all feature
  tiers without an account. Persists via `prgn_demo_tier` cookie. Default: Paid
  (most compelling first impression). `app/components/demo_toolbar.py`

- **Docker `web` service** — multi-stage nginx container serving the Vue SPA
  `dist/` build. Added to `compose.yml` (port 8506), `compose.demo.yml`
  (port 8507), `compose.cloud.yml` (port 8508). `manage.sh build` now includes
  the `web` service alongside `app`.

### Changed
- **Caddy routing** — `menagerie.circuitforge.tech` and
  `demo.circuitforge.tech` peregrine blocks now inspect the `prgn_ui` cookie
  and fan-out to the Vue SPA service or Streamlit accordingly.

---

## [0.6.2] — 2026-03-18

### Added
- **Playwright E2E test harness** — smoke + interaction test suite covering all
  three Peregrine instances (demo / cloud / local). Navigates every page, checks
  for DOM errors on load, clicks every interactable element, diffs errors
  before/after each click, and XFAIL-marks expected demo-mode failures so
  neutering-guard regressions are surfaced as XPASSes. Screenshots on failure.
  - `tests/e2e/test_smoke.py` — page-load error detection
  - `tests/e2e/test_interactions.py` — full click-through with XFAIL/XPASS bucketing
  - `tests/e2e/conftest.py` — Streamlit-aware wait helpers, error scanner, fixtures
  - `tests/e2e/models.py` — `ErrorRecord`, `ModeConfig`, `diff_errors`
  - `tests/e2e/modes/` — per-mode configs (demo / cloud / local)
  - `tests/e2e/pages/` — page objects for all 7 pages including Settings tabs

### Fixed
- **Demo: "Discovery failed" error on Home page load** — `task_runner.py` now
  checks `DEMO_MODE` before importing `discover.py`; returns a friendly error
  immediately instead of crashing on missing `search_profiles.yaml` (#21)
- **Demo: silent `st.error()` in collapsed Practice Q&A expander** — Interview
  Prep no longer auto-triggers the LLM on page render in demo mode; shows an
  `st.info` placeholder instead, eliminating the hidden error element (#22)
- **Cloud: auth wall shown to E2E test browser** — `cloud_session.py` now falls
  back to the `Cookie` header when `X-CF-Session` is absent (direct access
  without Caddy). Playwright's `set_extra_http_headers()` does not propagate to
  WebSocket handshakes; cookies do. Test harness uses `ctx.add_cookies()`.
- **E2E error scanner returned empty text for collapsed expanders** — switched
  from `inner_text()` (respects CSS `display:none`) to `text_content()` so
  errors inside collapsed Streamlit expanders are captured with their full text.

---

## [0.6.1] — 2026-03-16

### Fixed
- **Keyword suggestions not visible on first render** — `✨ Suggest` in
  Settings → Search now calls `st.rerun()` after storing results; chips appear
  immediately without requiring a tab switch (#18)
- **Wizard identity step required manual re-entry of resume data** — step 4
  (Identity) now prefills name, email, and phone from the parsed resume when
  those fields are blank; existing saved values are not overwritten (#17)
- **"Send to Notion" hardcoded on Home dashboard** — sync section now shows the
  connected provider name, or a "Set up a sync integration" prompt with a
  Settings link when no integration is configured (#16)
- **`test_generate_calls_llm_router` flaky in full suite** — resolved by queue
  optimizer merge; mock state pollution eliminated (#12)

---

## [0.6.0] — 2026-03-16

### Added
- **Calendar integration** — push interview events to Apple Calendar (CalDAV) or
  Google Calendar directly from the Interviews kanban. Idempotent: a second push
  updates the existing event rather than creating a duplicate. Button shows
  "📅 Add to Calendar" on first push and "🔄 Update Calendar" thereafter.
  Event title: `{Stage}: {Job Title} @ {Company}`; 1hr duration at noon UTC;
  job URL and company research brief included in event description.
  - `scripts/calendar_push.py` — push/update orchestration
  - `scripts/integrations/apple_calendar.py` — `create_event()` / `update_event()`
    via `caldav` + `icalendar`
  - `scripts/integrations/google_calendar.py` — `create_event()` / `update_event()`
    via `google-api-python-client` (service account); `test()` now makes a real API call
  - `scripts/db.py` — `calendar_event_id TEXT` column (auto-migration) +
    `set_calendar_event_id()` helper
  - `environment.yml` — pin `caldav>=1.3`, `icalendar>=5.0`,
    `google-api-python-client>=2.0`, `google-auth>=2.0`

---

## [0.4.1] — 2026-03-13

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
