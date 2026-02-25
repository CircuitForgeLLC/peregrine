# Design: Craigslist Custom Board Scraper

**Date:** 2026-02-24
**Status:** Approved

---

## Overview

Add a Craigslist scraper to `scripts/custom_boards/craigslist.py` following the existing
adzuna/theladders pattern. Craigslist is regional (one subdomain per metro), has no native
remote filter, and exposes an RSS feed that gives clean structured data without Playwright.

Discovery uses RSS for speed and reliability. Full job description is populated by the
existing `scrape_url` background task. Company name and salary — not present in Craigslist
listings as structured fields — are extracted from the description body by the existing
`enrich_descriptions` LLM pipeline after the posting is fetched.

---

## Files

| Action | File |
|---|---|
| Create | `scripts/custom_boards/craigslist.py` |
| Create | `config/craigslist.yaml` (gitignored) |
| Create | `config/craigslist.yaml.example` |
| Create | `tests/test_craigslist.py` |
| Modify | `scripts/discover.py` — add to `CUSTOM_SCRAPERS` registry |
| Modify | `scripts/enrich_descriptions.py` — add company/salary extraction for craigslist source |
| Modify | `config/search_profiles.yaml` — add `craigslist` to `custom_boards` on relevant profiles |
| Modify | `.gitignore` — add `config/craigslist.yaml` |

---

## Config (`config/craigslist.yaml`)

Gitignored. `.example` committed alongside it.

```yaml
# Craigslist metro subdomains to search.
# Full list at: https://www.craigslist.org/about/sites
metros:
  - sfbay
  - newyork
  - chicago
  - losangeles
  - seattle
  - austin

# Maps search profile location strings to a single metro subdomain.
# Locations not listed here are skipped silently.
location_map:
  "San Francisco Bay Area, CA": sfbay
  "New York, NY": newyork
  "Chicago, IL": chicago
  "Los Angeles, CA": losangeles
  "Seattle, WA": seattle
  "Austin, TX": austin

# Craigslist job category. Defaults to 'jjj' (general jobs) if omitted.
# Other useful values: csr (customer service), mar (marketing), sof (software)
# category: jjj
```

---

## Scraper Architecture

### RSS URL pattern
```
https://{metro}.craigslist.org/search/{category}?query={title}&format=rss&sort=date
```

Default category: `jjj`. Overridable via `category` key in config.

### `scrape(profile, location, results_wanted)` flow

1. Load `config/craigslist.yaml` — return `[]` with a printed warning if missing or malformed
2. Determine metros to search:
   - `location.lower() == "remote"` → all configured metros (Craigslist has no native remote filter)
   - Any other string → `location_map.get(location)` → single metro; skip silently if not mapped
3. For each metro × each title in `profile["titles"]`:
   - Fetch RSS via `requests.get` with a standard User-Agent header
   - Parse with `xml.etree.ElementTree` (stdlib — no extra deps)
   - Filter `<item>` entries by `<pubDate>` against `profile["hours_old"]`
   - Extract title, URL, and description snippet from each item
   - `time.sleep(0.5)` between fetches (polite pacing; easy to make configurable later)
4. Dedup by URL within the run via a `seen_urls` set
5. Stop when `results_wanted` is reached
6. Return list of job dicts

### Return dict shape

```python
{
    "title":       "<RSS item title, cleaned>",
    "company":     "",              # not in Craigslist — filled by LLM enrichment
    "url":         "<item link>",
    "source":      "craigslist",
    "location":    "<metro> (Craigslist)",
    "is_remote":   True,            # if remote search, else False
    "salary":      "",              # not reliably structured — filled by LLM enrichment
    "description": "",              # scrape_url background task fills this in
}
```

### Error handling

- Missing config → `[]` + printed warning, never raises
- `requests.RequestException` → skip that metro/title, print warning, continue
- Malformed RSS XML → skip that response, print warning, continue
- HTTP non-200 → skip, print status code

---

## LLM Enrichment for company/salary

Craigslist postings frequently include company name and salary in the body text, but not as
structured fields. After `scrape_url` populates `description`, the `enrich_descriptions`
task handles extraction.

**Trigger condition:** `source == "craigslist"` AND `company == ""` AND `description != ""`

**Prompt addition:** Extend the existing enrichment prompt to also extract:
- Company name (if present in the posting body)
- Salary or compensation range (if mentioned)

Results written back via `update_job_fields`. If the LLM cannot extract a company name,
the field stays blank — this is expected and acceptable for Craigslist.

---

## discover.py Integration

One-line addition to the `CUSTOM_SCRAPERS` registry:

```python
from scripts.custom_boards import craigslist as _craigslist

CUSTOM_SCRAPERS: dict[str, object] = {
    "adzuna":      _adzuna.scrape,
    "theladders":  _theladders.scrape,
    "craigslist":  _craigslist.scrape,   # new
}
```

Add `craigslist` to `custom_boards` in `config/search_profiles.yaml` for relevant profiles.

---

## Tests (`tests/test_craigslist.py`)

All tests use mocked `requests.get` with fixture RSS XML — no network calls.

| Test | Asserts |
|---|---|
| `test_scrape_returns_empty_on_missing_config` | Missing yaml → `[]`, no raise |
| `test_scrape_remote_hits_all_metros` | `location="Remote"` → one fetch per configured metro |
| `test_scrape_location_map_resolves` | `"San Francisco Bay Area, CA"` → `sfbay` only |
| `test_scrape_location_not_in_map_returns_empty` | Unknown location → `[]`, no raise |
| `test_hours_old_filter` | Items older than `hours_old` are excluded |
| `test_dedup_within_run` | Same URL appearing in two metros only returned once |
| `test_http_error_graceful` | `RequestException` → `[]`, no raise |
| `test_results_wanted_cap` | Never returns more than `results_wanted` |

---

## Out of Scope

- Playwright-based scraping (RSS is sufficient; Playwright adds a dep for no gain)
- Craigslist subcategory multi-search per profile (config `category` override is sufficient)
- Salary/company extraction directly in the scraper (LLM enrichment is the right layer)
- Windows support (deferred globally)
