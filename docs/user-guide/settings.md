# Settings

The Settings page is accessible from the sidebar. It contains all configuration for Peregrine, organised into tabs.

---

## My Profile

Personal information used in cover letters, research briefs, and interview prep.

| Field | Description |
|-------|-------------|
| Name | Your full name |
| Email | Contact email address |
| Phone | Contact phone number |
| LinkedIn | LinkedIn profile URL |
| Career summary | 2–4 sentence professional summary |
| NDA companies | Companies you cannot mention in research briefs (previous employers under NDA) |
| Docs directory | Where PDFs and exported documents are saved (default: `~/Documents/JobSearch`) |

### Mission Preferences

Optional notes about industries you genuinely care about. When the cover letter generator detects alignment with one of these industries, it injects your note into paragraph 3 of the cover letter.

| Field | Tag | Example |
|-------|-----|---------|
| Music industry note | `music` | "I've played in bands for 15 years and care deeply about how artists get paid" |
| Animal welfare note | `animal_welfare` | "I volunteer at my local shelter every weekend" |
| Education note | `education` | "I tutored underserved kids and care deeply about literacy" |

Leave a field blank to use a generic default when alignment is detected.

### Research Brief Preferences

Controls optional sections in company research briefs. Both are for personal decision-making only and are never included in applications.

| Setting | Section added |
|---------|--------------|
| Candidate accessibility focus | Disability inclusion and accessibility signals (ADA, ERGs, WCAG) |
| Candidate LGBTQIA+ focus | LGBTQIA+ inclusion signals (ERGs, non-discrimination policies, culture) |

---

## Search

Manage search profiles. Equivalent to editing `config/search_profiles.yaml` directly, but with a form UI.

- Add, edit, and delete profiles
- Configure titles, locations, boards, custom boards, exclude keywords, and mission tags
- Changes are saved to `config/search_profiles.yaml`

---

## LLM Backends

Configure which LLM backends Peregrine uses and in what order.

| Setting | Description |
|---------|-------------|
| Enabled toggle | Whether a backend is considered in the fallback chain |
| Base URL | API endpoint (for `openai_compat` backends) |
| Model | Model name or `__auto__` (vLLM auto-detects the loaded model) |
| API key | API key if required |
| Test button | Sends a short ping to verify the backend is reachable |

### Fallback chains

Three independent fallback chains are configured:

| Chain | Used for |
|-------|---------|
| `fallback_order` | Cover letter generation and general tasks |
| `research_fallback_order` | Company research briefs |
| `vision_fallback_order` | Survey screenshot analysis |

---

## Notion

Configure Notion integration credentials. Requires:
- Notion integration token (from [notion.so/my-integrations](https://www.notion.so/my-integrations))
- Database ID (from the Notion database URL)

The field map controls which Notion properties correspond to which Peregrine fields. Edit `config/notion.yaml` directly for advanced field mapping.

---

## Services

Connection settings for local services:

| Service | Default host:port |
|---------|-----------------|
| Ollama | localhost:11434 |
| vLLM | localhost:8000 |
| SearXNG | localhost:8888 |

Each service has SSL and SSL-verify toggles for reverse-proxy setups.

---

## Resume Profile

Edit your parsed resume data (work experience, education, skills, certifications). This is the same data extracted during the first-run wizard Resume step.

Changes here affect all future cover letter generations.

---

## Email

Configure IMAP email sync. See [Email Sync](email-sync.md) for full setup instructions.

---

## Skills

Manage your `config/resume_keywords.yaml` — the list of skills and keywords used for match scoring.

Add or remove keywords. Higher-weighted keywords count more toward the match score.

---

## Integrations

Connection cards for all 13 integrations. See [Integrations](integrations.md) for per-service details.

---

## Fine-Tune

**Tier: Premium**

Tools for fine-tuning a cover letter model on your personal writing style.

- Export cover letter training data as JSONL
- Configure training parameters (rank, epochs, learning rate)
- Start a fine-tuning run (requires `ogma` conda environment with Unsloth)
- Register the output model with Ollama

---

## Developer

Developer and debugging tools.

| Option | Description |
|--------|-------------|
| Reset wizard | Sets `wizard_complete: false` and `wizard_step: 0`; resumes at step 1 on next page load |
| Dev tier override | Set `dev_tier_override` to `paid` or `premium` to test tier-gated features locally |
| Clear stuck tasks | Manually sets any `running` or `queued` background tasks to `failed` (also runs on app startup) |
| View raw config | Shows the current `config/user.yaml` contents |
