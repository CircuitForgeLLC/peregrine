# Expanded First-Run Wizard — Design

**Date:** 2026-02-24
**Status:** Approved

---

## Goal

Replace the current 5-step surface-level wizard with a comprehensive onboarding flow that covers resume upload/parsing/building, guided config walkthroughs, LLM-assisted generation for key sections, and tier-based feature gating — while enforcing a minimum viable setup before the user can access the main app.

---

## Architecture

`0_Setup.py` becomes a thin orchestrator. All step logic moves into a new `app/wizard/` package. Resume parsing moves into `scripts/resume_parser.py`.

```
app/
  app.py                          # gate: user.yaml exists AND wizard_complete: true
  wizard/
    tiers.py                      # tier definitions, feature gates, can_use() helper
    step_hardware.py              # Step 1: GPU detection → profile recommendation
    step_tier.py                  # Step 2: free/paid/premium + dev_tier_override
    step_identity.py              # Step 3: name/email/phone/linkedin/career_summary
    step_resume.py                # Step 4: upload→parse OR guided form builder
    step_inference.py             # Step 5: LLM backend config + API keys
    step_search.py                # Step 6: job titles, locations, boards, keywords
    step_integrations.py          # Step 7: optional cloud/calendar/notification services
  pages/
    0_Setup.py                    # imports steps, drives progress state
scripts/
  resume_parser.py                # PDF/DOCX text extraction → LLM structuring
  integrations/
    __init__.py                   # registry: {name: IntegrationBase subclass}
    base.py                       # IntegrationBase: connect(), test(), sync(), fields()
    notion.py
    google_drive.py
    google_sheets.py
    airtable.py
    dropbox.py
    onedrive.py
    mega.py
    nextcloud.py
    google_calendar.py
    apple_calendar.py             # CalDAV
    slack.py
    discord.py                    # webhook only
    home_assistant.py
config/
  integrations/                   # one gitignored yaml per connected service
    notion.yaml.example
    google_drive.yaml.example
    ...
```

---

## Gate Logic

`app.py` gate changes from a single existence check to:

```python
if not UserProfile.exists(_USER_YAML):
    show_wizard()
elif not _profile.wizard_complete:
    show_wizard()   # resumes at last incomplete mandatory step
```

`wizard_complete: false` is written to `user.yaml` at the start of Step 3 (identity). It is only flipped to `true` when all mandatory steps pass validation on the final Finish action.

---

## Mandatory Steps

The wizard cannot be exited until all six mandatory steps pass validation.

| Step | File | Minimum to pass |
|------|------|----------------|
| 1. Hardware | `step_hardware.py` | Profile selected (auto-detected default accepted) |
| 2. Tier | `step_tier.py` | Tier selected (free is valid) |
| 3. Identity | `step_identity.py` | name + email + career_summary non-empty |
| 4. Resume | `step_resume.py` | At least one work experience entry |
| 5. Inference | `step_inference.py` | At least one working LLM endpoint confirmed |
| 6. Search | `step_search.py` | At least one job title + one location |

Each mandatory step's module exports `validate(data: dict) -> list[str]` — an errors list; empty = pass. These are pure functions, fully testable without Streamlit.

---

## Tier System

### `app/wizard/tiers.py`

```python
TIERS = ["free", "paid", "premium"]

FEATURES = {
    # Wizard LLM generation
    "llm_career_summary":           "paid",
    "llm_expand_bullets":           "paid",
    "llm_suggest_skills":           "paid",
    "llm_voice_guidelines":         "premium",
    "llm_job_titles":               "paid",
    "llm_keywords_blocklist":       "paid",
    "llm_mission_notes":            "paid",

    # App features
    "company_research":             "paid",
    "interview_prep":               "paid",
    "email_classifier":             "paid",
    "survey_assistant":             "paid",
    "model_fine_tuning":            "premium",
    "shared_cover_writer_model":    "paid",
    "multi_user":                   "premium",
    "search_profiles_limit":        {free: 1, paid: 5, premium: None},

    # Integrations
    "notion_sync":                  "paid",
    "google_sheets_sync":           "paid",
    "airtable_sync":                "paid",
    "google_calendar_sync":         "paid",
    "apple_calendar_sync":          "paid",
    "slack_notifications":          "paid",
}
# Free-tier integrations: google_drive, dropbox, onedrive, mega,
#   nextcloud, discord, home_assistant
```

### Storage in `user.yaml`

```yaml
tier: free                    # free | paid | premium
dev_tier_override: premium    # overrides tier locally — for testing only
```

### Dev override UI

Settings → Developer tab (visible when `dev_tier_override` is set or `DEV_MODE=true` in `.env`). Single selectbox to switch tier instantly — page reruns, all gates re-evaluate, no restart needed. Also exposes a "Reset wizard" button that sets `wizard_complete: false` to re-enter the wizard without deleting existing config.

### Gated UI behaviour

Paid/premium features show a muted `tier_label()` badge (`🔒 Paid` / `⭐ Premium`) and a disabled state rather than being hidden entirely — free users see what they're missing. Clicking a locked `✨` button opens an upsell tooltip, not an error.

---

## Resume Handling (Step 4)

### Fast path — upload

1. PDF → `pdfminer.six` extracts raw text
2. DOCX → `python-docx` extracts paragraphs
3. Raw text → LLM structures into `plain_text_resume.yaml` fields via background task
4. Populated form rendered for review/correction

### Fallback — guided form builder

Walks through `plain_text_resume.yaml` section by section:
- Personal info (pre-filled from Step 3)
- Work experience (add/remove entries)
- Education
- Skills
- Achievements (optional)

Both paths converge on the same review form before saving. `career_summary` from the resume is fed back to populate Step 3 if not already set.

### Outputs

- `aihawk/data_folder/plain_text_resume.yaml`
- `career_summary` written back to `user.yaml`

---

## LLM Generation Map

All `✨` actions submit a background task via `task_runner.py` using task type `wizard_generate` with a `section` parameter. The wizard step polls via `@st.fragment(run_every=3)` and shows inline status stages. Results land in `session_state` keyed by section and auto-populate the field on completion.

**Status stages for all wizard generation tasks:**
`Queued → Analyzing → Generating → Done`

| Step | Action | Tier | Input | Output |
|------|--------|------|-------|--------|
| Identity | ✨ Generate career summary | Paid | Resume text | `career_summary` in user.yaml |
| Resume | ✨ Expand bullet points | Paid | Rough responsibility notes | Polished STAR-format bullets |
| Resume | ✨ Suggest skills | Paid | Experience descriptions | Skills list additions |
| Resume | ✨ Infer voice guidelines | Premium | Resume + uploaded cover letters | Voice/tone hints in user.yaml |
| Search | ✨ Suggest job titles | Paid | Resume + current titles | Additional title suggestions |
| Search | ✨ Suggest keywords | Paid | Resume + titles | `resume_keywords.yaml` additions |
| Search | ✨ Suggest blocklist | Paid | Resume + titles | `blocklist.yaml` additions |
| My Profile (post-wizard) | ✨ Suggest mission notes | Paid | Resume + LinkedIn URL | `mission_preferences` notes |

---

## Optional Steps — Home Banners

After wizard completion, dismissible banners on the Home page surface remaining setup. Dismissed state stored as `dismissed_banners: [...]` in `user.yaml`.

| Banner | Links to |
|--------|---------|
| Connect a cloud service | Settings → Integrations |
| Set up email sync | Settings → Email |
| Set up email labels | Settings → Email (label guide) |
| Tune your mission preferences | Settings → My Profile |
| Configure keywords & blocklist | Settings → Search |
| Upload cover letter corpus | Settings → Fine-Tune |
| Configure LinkedIn Easy Apply | Settings → AIHawk |
| Set up company research | Settings → Services (SearXNG) |
| Build a target company list | Settings → Search |
| Set up notifications | Settings → Integrations |
| Tune a model | Settings → Fine-Tune |
| Review training data | Settings → Fine-Tune |
| Set up calendar sync | Settings → Integrations |

---

## Integrations Architecture

The registry pattern means adding a new integration requires one file in `scripts/integrations/` and one `.yaml.example` in `config/integrations/` — the wizard and Settings tab auto-discover it.

```python
class IntegrationBase:
    name: str
    label: str
    tier: str
    def connect(self, config: dict) -> bool: ...
    def test(self) -> bool: ...
    def sync(self, jobs: list[dict]) -> int: ...
    def fields(self) -> list[dict]: ...   # form field definitions for wizard card
```

Integration configs written to `config/integrations/<name>.yaml` only after a successful `test()` — never on partial input.

### v1 Integration List

| Integration | Purpose | Tier |
|-------------|---------|------|
| Notion | Job tracking DB sync | Paid |
| Notion Calendar | Covered by Notion integration | Paid |
| Google Sheets | Simpler tracker alternative | Paid |
| Airtable | Alternative tracker | Paid |
| Google Drive | Resume/cover letter storage | Free |
| Dropbox | Document storage | Free |
| OneDrive | Document storage | Free |
| MEGA | Document storage (privacy-first, cross-platform) | Free |
| Nextcloud | Self-hosted document storage | Free |
| Google Calendar | Write interview dates | Paid |
| Apple Calendar | Write interview dates (CalDAV) | Paid |
| Slack | Stage change notifications | Paid |
| Discord | Stage change notifications (webhook) | Free |
| Home Assistant | Notifications + automations (self-hosted) | Free |

---

## Data Flow

```
Wizard step        →  Written to
──────────────────────────────────────────────────────────────
Hardware           →  user.yaml (inference_profile)
Tier               →  user.yaml (tier, dev_tier_override)
Identity           →  user.yaml (name, email, phone, linkedin,
                                 career_summary, wizard_complete: false)
Resume (upload)    →  aihawk/data_folder/plain_text_resume.yaml
Resume (builder)   →  aihawk/data_folder/plain_text_resume.yaml
Inference          →  user.yaml (services block)
                       .env (ANTHROPIC_API_KEY, OPENAI_COMPAT_URL/KEY)
Search             →  config/search_profiles.yaml
                       config/resume_keywords.yaml
                       config/blocklist.yaml
Finish             →  user.yaml (wizard_complete: true)
                       config/llm.yaml (via apply_service_urls())
Integrations       →  config/integrations/<name>.yaml (per service,
                       only after successful test())
Background tasks   →  staging.db background_tasks table
LLM results        →  session_state[section] → field → user saves step
```

**Key rules:**
- Each mandatory step writes immediately on "Next" — partial progress survives crash or browser close
- `apply_service_urls()` called once at Finish, not per-step
- Integration configs never written on partial input — only after `test()` passes

---

## Testing

- **Tier switching:** Settings → Developer tab selectbox — instant rerun, no restart
- **Wizard re-entry:** Settings → Developer "Reset wizard" button sets `wizard_complete: false`
- **Unit tests:** `validate(data) -> list[str]` on each step module — pure functions, no Streamlit
- **Integration tests:** `tests/test_wizard_flow.py` — full step sequence with mock LLM router and mock file writes
- **`DEV_MODE=true`** in `.env` makes Developer tab always visible regardless of `dev_tier_override`
