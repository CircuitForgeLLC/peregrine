# Jobgether Integration Design

**Date:** 2026-03-15
**Status:** Approved
**Scope:** Peregrine — discovery pipeline + manual URL import

---

## Problem

Jobgether is a job aggregator that posts listings on LinkedIn and other boards with `company = "Jobgether"` rather than the actual employer. This causes two problems:

1. **Misleading listings** — Jobs appear to be at "Jobgether" rather than the real hiring company. Meg sees "Jobgether" as employer throughout the pipeline (Job Review, cover letters, company research).
2. **Broken manual import** — Direct `jobgether.com` URLs return HTTP 403 when scraped with plain `requests`, leaving jobs stuck as `title = "Importing…"`.

**Evidence from DB:** 29+ Jobgether-sourced LinkedIn listings with `company = "Jobgether"`. Actual employer is intentionally withheld by Jobgether's business model ("on behalf of a partner company").

---

## Decision: Option A — Filter + Dedicated Scraper

Drop Jobgether listings from other scrapers entirely and replace with a direct Jobgether scraper that retrieves accurate company names. Existing Jobgether-via-LinkedIn listings in the DB are left as-is for manual review/rejection.

**Why not Option B (follow-through):** LinkedIn→Jobgether→employer is a two-hop chain where the employer is deliberately hidden. Jobgether blocks `requests`. Not worth the complexity for unreliable data.

---

## Components

### 1. Jobgether company filter — `config/blocklist.yaml`

Add `"jobgether"` to the `companies` list in `config/blocklist.yaml`. The existing `_is_blocklisted()` function in `discover.py` already performs a partial case-insensitive match on the company field and applies to all scrapers (JobSpy boards + all custom boards). No code change required.

```yaml
companies:
  - jobgether
```

This is the correct mechanism — it is user-visible, config-driven, and applies uniformly. Log output already reports blocklisted jobs per run.

### 2. URL handling in `scrape_url.py`

Three changes required:

**a) `_detect_board()`** — add `"jobgether"` branch returning `"jobgether"` when `"jobgether.com"` is in the URL. Must be added before the `return "generic"` fallback.

**b) dispatch block in `scrape_job_url()`** — add `elif board == "jobgether": fields = _scrape_jobgether(url)` to the `if/elif` chain (lines 208–215). Without this, the new `_detect_board()` branch silently falls through to `_scrape_generic()`.

**c) `_scrape_jobgether(url)`** — Playwright-based scraper to bypass 403. Extracts:
- `title` — job title from page heading
- `company` — actual employer name (visible on Jobgether offer pages)
- `location` — remote/location info
- `description` — full job description
- `source = "jobgether"`

Playwright errors (`playwright.sync_api.Error`, `TimeoutError`) are not subclasses of `requests.RequestException` but are caught by the existing broad `except Exception` handler in `scrape_job_url()` — no changes needed to the error handling block.

**URL slug fallback for company name (manual import path only):** Jobgether offer URLs follow the pattern:
```
https://jobgether.com/offer/{24-hex-hash}-{title-slug}---{company-slug}
```
When Playwright is unavailable, parse `company-slug` using:
```python
m = re.search(r'---([^/?]+)$', parsed_path)
company = m.group(1).replace("-", " ").title() if m else ""
```
Example: `/offer/69b42d9d24d79271ee0618e8-customer-success-manager---resware` → `"Resware"`.

This fallback is scoped to `_scrape_jobgether()` in `scrape_url.py` only; the discovery scraper always gets company name from the rendered DOM. `_scrape_jobgether()` does not make any `requests` calls — there is no `raise_for_status()` — so the `requests.RequestException` handler in `scrape_job_url()` is irrelevant to this path; only the broad `except Exception` applies.

**Pre-implementation checkpoint:** Confirm that Jobgether offer URLs have no tracking query params beyond UTM (already covered by `_STRIP_PARAMS`). No `canonicalize_url()` changes are expected but verify before implementation.

### 3. `scripts/custom_boards/jobgether.py`

Playwright-based search scraper following the same interface as `theladders.py`:

```python
def scrape(profile: dict, location: str, results_wanted: int = 50) -> list[dict]
```

- Base URL: `https://jobgether.com/remote-jobs`
- Search strategy: iterate over `profile["titles"]`, apply search/filter params
- **Pre-condition — do not begin implementation of this file until live URL inspection is complete.** Use browser dev tools or a Playwright `page.on("request")` capture to determine the actual query parameter format for title/location filtering. Jobgether may use URL query params, path segments, or JS-driven state — this cannot be assumed from the URL alone.
- Extraction: job cards from rendered DOM (Playwright `page.evaluate()`)
- Returns standard job dicts: `title, company, url, source, location, is_remote, salary, description`
- `source = "jobgether"`
- Graceful `ImportError` handling if Playwright not installed (same pattern as `theladders.py`)
- Polite pacing: 1s sleep between title iterations
- Company name comes from DOM; URL slug parse is not needed in this path

### 4. Registration + config

**`discover.py` — import block (lines 20–22):**
```python
from scripts.custom_boards import jobgether as _jobgether
```

**`discover.py` — `CUSTOM_SCRAPERS` dict literal (lines 30–34):**
```python
CUSTOM_SCRAPERS: dict[str, object] = {
    "adzuna":     _adzuna.scrape,
    "theladders": _theladders.scrape,
    "craigslist": _craigslist.scrape,
    "jobgether":  _jobgether.scrape,   # ← add this line
}
```

**`config/search_profiles.yaml` (and `.example`):**
Add `jobgether` to `custom_boards` for any profile that includes `Remote` in its `locations` list. Jobgether is a remote-work-focused aggregator; adding it to location-specific non-remote profiles is not useful. Do not add a `custom_boards` key to profiles that don't already have one unless they are remote-eligible.
```yaml
custom_boards:
  - jobgether
```

---

## Data Flow

```
discover.py
  ├── JobSpy boards       → _is_blocklisted(company="jobgether") → drop → DB insert
  ├── custom: adzuna      → _is_blocklisted(company="jobgether") → drop → DB insert
  ├── custom: theladders  → _is_blocklisted(company="jobgether") → drop → DB insert
  ├── custom: craigslist  → _is_blocklisted(company="jobgether") → drop → DB insert
  └── custom: jobgether   → (company = real employer, never "jobgether") → DB insert

scrape_url.py
  └── jobgether.com URL → _detect_board() = "jobgether"
                        → _scrape_jobgether()
                          ├── Playwright available → full job fields from page
                          └── Playwright unavailable → company from URL slug only
```

---

## Implementation Notes

- **Slug fallback None-guard:** The regex `r'---([^/?]+)$'` returns a wrong value (not `None`) if the URL slug doesn't follow the expected format. Add a logged warning and return `""` rather than title-casing garbage.
- **Import guard in `discover.py`:** Wrap the `jobgether` import with `try/except ImportError`, setting `_jobgether = None`, and gate the `CUSTOM_SCRAPERS` registration with `if _jobgether is not None`. This ensures the graceful ImportError in `jobgether.py` (for missing Playwright) propagates cleanly to the caller rather than crashing discovery.

### 5. Cover letter recruiter framing — `scripts/generate_cover_letter.py`

When `source = "jobgether"`, inject a system hint that shifts the cover letter addressee from the employer to the Jobgether recruiter. Use Policy A: recruiter framing applies for all Jobgether-sourced jobs regardless of whether the real company name was resolved.

- If company is known (e.g. "Resware"): *"Your client at Resware will appreciate..."*
- If company is unknown: *"Your client will appreciate..."*

The real company name is always stored in the DB as resolved by the scraper — this is internal knowledge only. The framing shift is purely in the generated letter text, not in how the job is stored or displayed.

Implementation: add an `is_jobgether` flag to the cover letter prompt context (same pattern as `mission_hint` injection). Add a conditional block in the system prompt / Para 1 instructions when the flag is true.

---

## Out of Scope

- Retroactively fixing existing `company = "Jobgether"` rows in the DB (left for manual review/rejection)
- Jobgether authentication / logged-in scraping
- Pagination beyond `results_wanted` cap
- Dedup between Jobgether scraper and other boards (existing URL dedup in `discover.py` handles this)

---

## Files Changed

| File | Change |
|------|--------|
| `config/blocklist.yaml` | Add `"jobgether"` to `companies` list |
| `scripts/discover.py` | Add import + entry in `CUSTOM_SCRAPERS` dict literal |
| `scripts/scrape_url.py` | Add `_detect_board` branch, dispatch branch, `_scrape_jobgether()` |
| `scripts/custom_boards/jobgether.py` | New file — Playwright search scraper |
| `config/search_profiles.yaml` | Add `jobgether` to `custom_boards` |
| `config/search_profiles.yaml.example` | Same |
