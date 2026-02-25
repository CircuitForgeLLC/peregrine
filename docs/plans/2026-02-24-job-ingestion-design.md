# Design: Job Ingestion Improvements

**Date:** 2026-02-24
**Status:** Approved

---

## Overview

Three improvements to how jobs enter the pipeline:

1. **Auto-parse LinkedIn Job Alert emails** — digest emails from `jobalerts-noreply@linkedin.com`
   contain multiple structured job cards in plain text. Currently ingested as a single confusing
   email lead. Instead, parse each card into a separate pending job and scrape it via a background
   task.

2. **`scrape_url` background task** — new task type that takes a job record's URL, fetches
   the full listing (title, company, description, salary, location), and updates the job row.
   Shared by both the LinkedIn alert parser and the manual URL import feature.

3. **Add Job(s) by URL on Home page** — paste one URL per line, or upload a CSV with a URL
   column. Each URL is inserted as a pending job and queued for background scraping.

---

## `scrape_url` Worker (`scripts/scrape_url.py`)

Single public function: `scrape_job_url(db_path, job_id) -> dict`

Board detection from URL hostname:

| URL pattern | Board | Scrape method |
|---|---|---|
| `linkedin.com/jobs/view/<id>/` | LinkedIn | LinkedIn guest jobs API (`/jobs-guest/jobs/api/jobPosting/<id>`) |
| `indeed.com/viewjob?jk=<key>` | Indeed | requests + BeautifulSoup HTML parse |
| `glassdoor.com/...` | Glassdoor | JobSpy internal scraper (same as `enrich_descriptions.py`) |
| anything else | generic | requests + JSON-LD → og:tags fallback |

On success: `UPDATE jobs SET title, company, description, salary, location, is_remote WHERE id=?`
On failure: job remains pending with its URL intact — user can still approve/reject it.

Requires a new `update_job_fields(db_path, job_id, fields: dict)` helper in `db.py`.

---

## LinkedIn Alert Parser (`imap_sync.py`)

New function `parse_linkedin_alert(body: str) -> list[dict]`

The plain-text body has a reliable block structure:
```
<Title>
<Company>
<Location>
[optional social proof lines like "2 school alumni"]
View job: https://www.linkedin.com/comm/jobs/view/<ID>/?<tracking>

---------------------------------------------------------

<next job block...>
```

Parser:
1. Split on lines of 10+ dashes
2. For each block: filter out social-proof lines (alumni, "Apply with", "actively hiring", etc.)
3. Extract: title (line 1), company (line 2), location (line 3), URL (line starting "View job:")
4. Canonicalize URL: strip tracking params → `https://www.linkedin.com/jobs/view/<id>/`

Detection in `_scan_unmatched_leads`: if `from_addr` contains
`jobalerts-noreply@linkedin.com`, skip the LLM path and call `parse_linkedin_alert` instead.
Each parsed card → `insert_job()` + `submit_task(db, "scrape_url", job_id)`.
The email itself is not stored as an email lead — it's a batch import trigger.

---

## Home Page URL Import

New section on `app/Home.py` between Email Sync and Danger Zone.

Two tabs:
- **Paste URLs** — `st.text_area`, one URL per line
- **Upload CSV** — `st.file_uploader`, auto-detects first column value starting with `http`

Both routes call a shared `_queue_url_imports(db_path, urls)` helper that:
1. Filters URLs already in the DB (dedup by URL)
2. Calls `insert_job({title="Importing…", source="manual", url=url, ...})`
3. Calls `submit_task(db, "scrape_url", job_id)` per new job
4. Shows `st.success(f"Queued N job(s)")`

A `@st.fragment(run_every=3)` status block below the form polls active `scrape_url` tasks
and shows per-job status (⏳ / ✅ / ❌ title - company).

---

## Search Settings (already applied)

`config/search_profiles.yaml`:
- `hours_old: 120 → 240` (cover LinkedIn's algo-sorted alerts)
- `results_per_board: 50 → 75`
- Added title: `Customer Engagement Manager`

---

## Out of Scope

- Scraping all 551 historical LinkedIn alert emails (run email sync going forward)
- Deduplication against Notion (URL dedup in SQLite is sufficient)
- Authentication-required boards (Indeed Easy Apply, etc.)
