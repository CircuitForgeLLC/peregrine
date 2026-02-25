# Adding a Custom Job Board Scraper

Peregrine supports pluggable custom job board scrapers. Standard boards use the JobSpy library. Custom scrapers handle boards with non-standard APIs, paywalls, or SSR-rendered pages.

This guide walks through adding a new scraper from scratch.

---

## Step 1 — Create the scraper module

Create `scripts/custom_boards/myboard.py`. Every custom scraper must implement one function:

```python
# scripts/custom_boards/myboard.py

def scrape(profile: dict, db_path: str) -> list[dict]:
    """
    Scrape job listings from MyBoard for the given search profile.

    Args:
        profile: The active search profile dict from search_profiles.yaml.
                 Keys include: titles (list), locations (list),
                 hours_old (int), results_per_board (int).
        db_path: Absolute path to staging.db. Use this if you need to
                 check for existing URLs before returning.

    Returns:
        List of job dicts. Each dict must contain at minimum:
            title       (str)   — job title
            company     (str)   — company name
            url         (str)   — canonical job URL (used as unique key)
            source      (str)   — board identifier, e.g. "myboard"
            location    (str)   — "Remote" or "City, State"
            is_remote   (bool)  — True if remote
            salary      (str)   — salary string or "" if unknown
            description (str)   — full job description text or "" if unavailable
            date_found  (str)   — ISO 8601 datetime string, e.g. "2026-02-25T12:00:00"
    """
    jobs = []

    for title in profile.get("titles", []):
        for location in profile.get("locations", []):
            results = _fetch_from_myboard(title, location, profile)
            jobs.extend(results)

    return jobs


def _fetch_from_myboard(title: str, location: str, profile: dict) -> list[dict]:
    """Internal helper — call the board's API and transform results."""
    import requests
    from datetime import datetime

    params = {
        "q": title,
        "l": location,
        "limit": profile.get("results_per_board", 50),
    }

    try:
        resp = requests.get(
            "https://api.myboard.com/jobs",
            params=params,
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"[myboard] fetch error: {e}")
        return []

    jobs = []
    for item in data.get("results", []):
        jobs.append({
            "title":       item.get("title", ""),
            "company":     item.get("company", ""),
            "url":         item.get("url", ""),
            "source":      "myboard",
            "location":    item.get("location", ""),
            "is_remote":   "remote" in item.get("location", "").lower(),
            "salary":      item.get("salary", ""),
            "description": item.get("description", ""),
            "date_found":  datetime.utcnow().isoformat(),
        })

    return jobs
```

### Required fields

| Field | Type | Notes |
|-------|------|-------|
| `title` | str | Job title |
| `company` | str | Company name |
| `url` | str | **Unique key** — must be stable and canonical |
| `source` | str | Short board identifier, e.g. `"myboard"` |
| `location` | str | `"Remote"` or `"City, ST"` |
| `is_remote` | bool | `True` if remote |
| `salary` | str | Salary string or `""` |
| `description` | str | Full description text or `""` |
| `date_found` | str | ISO 8601 UTC datetime |

### Deduplication

`discover.py` deduplicates by `url` before inserting into the database. If a job with the same URL already exists, it is silently skipped. You do not need to handle deduplication inside your scraper.

### Rate limiting

Be a good citizen:
- Add a `time.sleep(0.5)` between paginated requests
- Respect `Retry-After` headers
- Do not scrape faster than a human browsing the site
- If the site provides an official API, prefer that over scraping HTML

### Credentials

If your scraper requires API keys or credentials:
- Create `config/myboard.yaml.example` as a template
- Create `config/myboard.yaml` (gitignored) for live credentials
- Read it in your scraper with `yaml.safe_load(open("config/myboard.yaml"))`
- Document the credential setup in comments at the top of your module

---

## Step 2 — Register the scraper

Open `scripts/discover.py` and add your scraper to the `CUSTOM_SCRAPERS` dict:

```python
from scripts.custom_boards import adzuna, theladders, craigslist, myboard

CUSTOM_SCRAPERS = {
    "adzuna":     adzuna.scrape,
    "theladders": theladders.scrape,
    "craigslist": craigslist.scrape,
    "myboard":    myboard.scrape,   # add this line
}
```

---

## Step 3 — Activate in a search profile

Open `config/search_profiles.yaml` and add `myboard` to `custom_boards` in any profile:

```yaml
profiles:
  - name: cs_leadership
    boards:
      - linkedin
      - indeed
    custom_boards:
      - adzuna
      - myboard          # add this line
    titles:
      - Customer Success Manager
    locations:
      - Remote
```

---

## Step 4 — Write a test

Create `tests/test_myboard.py`. Mock the HTTP call to avoid hitting the live API during tests:

```python
# tests/test_myboard.py

from unittest.mock import patch
from scripts.custom_boards.myboard import scrape

MOCK_RESPONSE = {
    "results": [
        {
            "title": "Customer Success Manager",
            "company": "Acme Corp",
            "url": "https://myboard.com/jobs/12345",
            "location": "Remote",
            "salary": "$80,000 - $100,000",
            "description": "We are looking for a CSM...",
        }
    ]
}

def test_scrape_returns_correct_shape():
    profile = {
        "titles": ["Customer Success Manager"],
        "locations": ["Remote"],
        "results_per_board": 10,
        "hours_old": 240,
    }

    with patch("scripts.custom_boards.myboard.requests.get") as mock_get:
        mock_get.return_value.ok = True
        mock_get.return_value.raise_for_status = lambda: None
        mock_get.return_value.json.return_value = MOCK_RESPONSE

        jobs = scrape(profile, db_path="nonexistent.db")

    assert len(jobs) == 1
    job = jobs[0]

    # Required fields
    assert "title" in job
    assert "company" in job
    assert "url" in job
    assert "source" in job
    assert "location" in job
    assert "is_remote" in job
    assert "salary" in job
    assert "description" in job
    assert "date_found" in job

    assert job["source"] == "myboard"
    assert job["title"] == "Customer Success Manager"
    assert job["url"] == "https://myboard.com/jobs/12345"


def test_scrape_handles_http_error_gracefully():
    profile = {
        "titles": ["Customer Success Manager"],
        "locations": ["Remote"],
        "results_per_board": 10,
        "hours_old": 240,
    }

    with patch("scripts.custom_boards.myboard.requests.get") as mock_get:
        mock_get.side_effect = Exception("Connection refused")

        jobs = scrape(profile, db_path="nonexistent.db")

    assert jobs == []
```

---

## Existing Scrapers as Reference

| Scraper | Notes |
|---------|-------|
| `scripts/custom_boards/adzuna.py` | REST API with `app_id` + `app_key` authentication |
| `scripts/custom_boards/theladders.py` | SSR scraper using `curl_cffi` to parse `__NEXT_DATA__` JSON embedded in the page |
| `scripts/custom_boards/craigslist.py` | RSS feed scraper |
