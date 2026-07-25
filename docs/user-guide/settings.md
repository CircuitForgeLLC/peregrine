# Settings

Access Settings from the sidebar. The page has a navigation panel on the left (desktop) or a chip bar at the top (mobile). Each section is described below.

For an overview of how settings fit into your daily use, see [Daily Workflow](daily-workflow.md).

---

## My Profile

Personal information used in cover letters, research briefs, and interview prep.

| Field | Description |
|-------|-------------|
| Full name | Your name as it appears in generated documents |
| Email | Contact email |
| Phone | Contact phone number |
| LinkedIn URL | Used in cover letter headers |
| Career summary | 2–4 sentences that anchor all LLM-generated content |

### Mission Preferences

Optional notes about industries you genuinely care about. When the cover letter generator detects alignment with one of these industries, it injects your note into the generated letter.

| Field | Tag |
|-------|-----|
| Music industry note | `music` |
| Animal welfare note | `animal_welfare` |
| Education note | `education` |

Leave a field blank to use a generic default when alignment is detected.

### Research Brief Preferences

Controls optional sections in company research briefs. Both are for personal decision-making only and never appear in applications.

| Setting | Section added to brief |
|---------|----------------------|
| Accessibility focus | Disability inclusion signals (ADA, ERGs, WCAG) |
| LGBTQIA+ focus | Inclusion signals (ERGs, non-discrimination policies) |

---

## Resume Profile

A structured editor for your work experience, education, skills, and personal details. This is the primary data source for cover letter generation.

### Resume vs. Library

The Resume Profile is backed by a structured YAML file (`plain_text_resume.yaml`). The **Resume Library** (`/resumes`, accessible from the sidebar) is a versioned archive of full resume texts. They stay in sync automatically when you use the "Apply to profile" flow — see [Daily Workflow — Managing Your Resume](daily-workflow.md#managing-your-resume).

### Uploading a resume

If no profile exists yet, you can:

- **Upload & Parse** — upload a PDF, DOCX, or ODT. Peregrine extracts structured data automatically.
- **Fill in Manually** — start from a blank form.
- **Run Setup Wizard** — re-enter the first-run wizard (self-hosted only).

### Editing the profile

When a resume exists, the full form is shown. Sections:

- **Career Summary** — used in every cover letter and research brief
- **Personal Information** — name, email, phone, LinkedIn; synced from My Profile
- **Work Experience** — title, company, period, location, industry, responsibilities, skills
- **Education** — institution, degree, field, dates
- **Skills, Domains, Keywords** — tags used for keyword matching; click **Suggest** for AI recommendations
- **Certifications and Achievements** — optional; included in cover letter context

Click **Save** to write changes. If a default library entry is linked, it updates automatically.

---

## Search Prefs

Manage what Peregrine searches for across all job boards. Changes take effect on the next discovery run — no restart needed.

| Field | Description |
|-------|-------------|
| Remote preference | Remote only, on-site only, or both |
| Job Titles | Roles searched on every board |
| Locations | Geographic scope; leave blank for unrestricted |
| Exclude Keywords | Drop any job title containing these words before it enters the database |
| Job Boards | Enable or disable specific sources; boards marked "coming soon" are tracked in the backlog |
| Custom Board URLs | Additional job board URLs to include |
| Blocklists | Companies, industries, or locations to always skip |

Click **Suggest** next to Job Titles, Locations, or Exclude Keywords to get AI-generated suggestions based on your resume.

---

## Connections

API credentials and authentication for external services.

| Service | What it enables |
|---------|----------------|
| Notion | Sync approved/applied jobs to a Notion database |
| Airtable | Alternative sync target |
| Google Drive | Document export |
| Slack / Discord | Status notifications |
| Google Calendar / Apple Calendar | Interview scheduling (Paid) |

See [Integrations](integrations.md) for per-service setup instructions.

---

## System

*Not available in cloud mode.*

LLM backend configuration and service connection settings.

### LLM Backends

| Setting | Description |
|---------|-------------|
| Enabled toggle | Whether a backend is considered in the fallback chain |
| Base URL | API endpoint for OpenAI-compatible backends |
| Model | Model name or `__auto__` (vLLM auto-detects the loaded model) |
| API key | Required for hosted APIs |
| Test button | Sends a ping to verify the backend is reachable |

Three independent fallback chains:

| Chain | Used for |
|-------|---------|
| Cover letter chain | Cover letter generation and general tasks |
| Research chain | Company research briefs |
| Vision chain | Survey screenshot analysis |

### Service Hosts and Ports

Connection settings for Ollama, vLLM, and SearXNG. Each service has an SSL toggle and SSL-verify toggle for reverse-proxy setups.

---

## Fine-Tune

*Tier: Premium only.*

Tools for fine-tuning a cover letter model on your personal writing style.

1. **Export Training Data** — produces a JSONL file from your saved cover letters
2. **Configure training** — rank, epochs, learning rate
3. **Start fine-tune** — runs via the `ogma` conda environment with Unsloth
4. **Register model** — adds the output to Ollama as `alex-cover-writer:latest`

---

## License

View your current license key, tier, and entitlements. Paste a new key here if you are upgrading or replacing a key.

---

## Data

*Not available in cloud mode.*

Export or delete your local data.

| Action | What it does |
|--------|-------------|
| Export | Downloads `staging.db` and config files as a zip |
| Purge pending jobs | Deletes all jobs with status `pending` |
| Purge rejected jobs | Deletes all jobs with status `rejected` |
| Factory reset | Removes all data and config; returns to first-run wizard |

---

## Privacy

Controls for data collection and diagnostic logging. All collection is opt-in.

---

## Developer

Developer and debugging tools. Only visible when dev mode is enabled or a `dev_tier_override` is set.

| Option | Description |
|--------|-------------|
| Reset wizard | Sets `wizard_complete: false`; wizard restarts on next page load |
| Dev tier override | Set tier to `paid` or `premium` to test tier-gated features locally |
| Clear stuck tasks | Manually fails any `running` or `queued` background tasks |
| View raw config | Shows current `user.yaml` contents |
