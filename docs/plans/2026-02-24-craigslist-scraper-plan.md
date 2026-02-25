# Craigslist Scraper Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a Craigslist RSS-based job scraper to `scripts/custom_boards/craigslist.py`, wired into the existing discovery pipeline, with LLM extraction of company name and salary from the fetched posting body.

**Architecture:** RSS fetch per metro × title → `scrape_url` background task fills description → new `enrich_craigslist` task type extracts company/salary via LLM. Config-driven metro list in `config/craigslist.yaml`. Integrates via the existing `CUSTOM_SCRAPERS` registry in `discover.py`.

**Tech Stack:** Python 3.11, `requests`, `xml.etree.ElementTree` (stdlib), `PyYAML`, `email.utils.parsedate_to_datetime` (stdlib), existing `llm_router.py`

**Test runner:** `/devl/miniconda3/envs/job-seeker/bin/pytest tests/ -v`

---

## Task 1: Config files + .gitignore

**Files:**
- Create: `config/craigslist.yaml.example`
- Create: `config/craigslist.yaml`
- Modify: `.gitignore`

**Step 1: Create `config/craigslist.yaml.example`**

```yaml
# Craigslist metro subdomains to search.
# Copy to config/craigslist.yaml and adjust for your markets.
# Full subdomain list: https://www.craigslist.org/about/sites
metros:
  - sfbay
  - newyork
  - chicago
  - losangeles
  - seattle
  - austin

# Maps search profile location strings → Craigslist metro subdomain.
# Locations not listed here are silently skipped.
location_map:
  "San Francisco Bay Area, CA": sfbay
  "New York, NY": newyork
  "Chicago, IL": chicago
  "Los Angeles, CA": losangeles
  "Seattle, WA": seattle
  "Austin, TX": austin

# Craigslist job category. Defaults to 'jjj' (general jobs) if omitted.
# Other options: csr (customer service), mar (marketing), sof (software/qa/dba)
# category: jjj
```

**Step 2: Create `config/craigslist.yaml`** (personal config — gitignored)

Copy `.example` as-is (Meghan targets sfbay + remote, so this default is correct).

**Step 3: Add to `.gitignore`**

Add `config/craigslist.yaml` after the existing `config/adzuna.yaml` line:

```
config/adzuna.yaml
config/craigslist.yaml
```

**Step 4: Commit**

```bash
git add config/craigslist.yaml.example .gitignore
git commit -m "feat: add craigslist config template and gitignore entry"
```

---

## Task 2: Core scraper tests (write failing first)

**Files:**
- Create: `tests/test_craigslist.py`

**Step 1: Create `tests/test_craigslist.py` with all fixtures and tests**

```python
"""Tests for Craigslist RSS scraper."""
from datetime import datetime, timezone, timedelta
from email.utils import format_datetime
from unittest.mock import patch, MagicMock
import xml.etree.ElementTree as ET

import pytest
import requests


# ── RSS fixture helpers ────────────────────────────────────────────────────────

def _make_rss(items: list[dict]) -> bytes:
    """Build minimal Craigslist-style RSS XML from a list of item dicts."""
    channel = ET.Element("channel")
    for item_data in items:
        item = ET.SubElement(channel, "item")
        for tag, value in item_data.items():
            el = ET.SubElement(item, tag)
            el.text = value
    rss = ET.Element("rss")
    rss.append(channel)
    return ET.tostring(rss, encoding="utf-8", xml_declaration=True)


def _pubdate(hours_ago: float = 1.0) -> str:
    """Return an RFC 2822 pubDate string for N hours ago."""
    dt = datetime.now(tz=timezone.utc) - timedelta(hours=hours_ago)
    return format_datetime(dt)


def _mock_resp(content: bytes, status_code: int = 200) -> MagicMock:
    mock = MagicMock()
    mock.status_code = status_code
    mock.content = content
    mock.raise_for_status = MagicMock()
    if status_code >= 400:
        mock.raise_for_status.side_effect = requests.HTTPError(f"HTTP {status_code}")
    return mock


# ── Fixtures ──────────────────────────────────────────────────────────────────

_SAMPLE_RSS = _make_rss([{
    "title": "Customer Success Manager",
    "link": "https://sfbay.craigslist.org/jjj/d/csm-role/1234567890.html",
    "description": "Great CSM role at Acme Corp. Salary $120k.",
    "pubDate": _pubdate(1),
}])

_TWO_ITEM_RSS = _make_rss([
    {
        "title": "Customer Success Manager",
        "link": "https://sfbay.craigslist.org/jjj/d/csm-role/1111111111.html",
        "description": "CSM role 1.",
        "pubDate": _pubdate(1),
    },
    {
        "title": "Account Manager",
        "link": "https://sfbay.craigslist.org/jjj/d/am-role/2222222222.html",
        "description": "AM role.",
        "pubDate": _pubdate(2),
    },
])

_OLD_ITEM_RSS = _make_rss([{
    "title": "Old Job",
    "link": "https://sfbay.craigslist.org/jjj/d/old-job/9999999999.html",
    "description": "Very old posting.",
    "pubDate": _pubdate(hours_ago=500),
}])

_TWO_METRO_CONFIG = {
    "metros": ["sfbay", "newyork"],
    "location_map": {
        "San Francisco Bay Area, CA": "sfbay",
        "New York, NY": "newyork",
    },
    "category": "jjj",
}

_SINGLE_METRO_CONFIG = {
    "metros": ["sfbay"],
    "location_map": {"San Francisco Bay Area, CA": "sfbay"},
}

_PROFILE = {"titles": ["Customer Success Manager"], "hours_old": 240}


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_scrape_returns_empty_on_missing_config(tmp_path):
    """Missing craigslist.yaml → returns [] without raising."""
    with patch("scripts.custom_boards.craigslist._CONFIG_PATH",
               tmp_path / "craigslist.yaml"):
        import importlib
        import scripts.custom_boards.craigslist as cl
        importlib.reload(cl)
        result = cl.scrape(_PROFILE, "San Francisco Bay Area, CA")
    assert result == []


def test_scrape_remote_hits_all_metros():
    """location='Remote' triggers one RSS fetch per configured metro."""
    with patch("scripts.custom_boards.craigslist._load_config",
               return_value=_TWO_METRO_CONFIG):
        with patch("scripts.custom_boards.craigslist.requests.get",
                   return_value=_mock_resp(_SAMPLE_RSS)) as mock_get:
            from scripts.custom_boards import craigslist
            result = craigslist.scrape(_PROFILE, "Remote")

    assert mock_get.call_count == 2
    fetched_urls = [call.args[0] for call in mock_get.call_args_list]
    assert any("sfbay" in u for u in fetched_urls)
    assert any("newyork" in u for u in fetched_urls)
    assert all(r["is_remote"] for r in result)


def test_scrape_location_map_resolves():
    """Known location string maps to exactly one metro."""
    with patch("scripts.custom_boards.craigslist._load_config",
               return_value=_TWO_METRO_CONFIG):
        with patch("scripts.custom_boards.craigslist.requests.get",
                   return_value=_mock_resp(_SAMPLE_RSS)) as mock_get:
            from scripts.custom_boards import craigslist
            result = craigslist.scrape(_PROFILE, "San Francisco Bay Area, CA")

    assert mock_get.call_count == 1
    assert "sfbay" in mock_get.call_args.args[0]
    assert len(result) == 1
    assert result[0]["is_remote"] is False


def test_scrape_location_not_in_map_returns_empty():
    """Location not in location_map → [] without raising."""
    with patch("scripts.custom_boards.craigslist._load_config",
               return_value=_SINGLE_METRO_CONFIG):
        with patch("scripts.custom_boards.craigslist.requests.get") as mock_get:
            from scripts.custom_boards import craigslist
            result = craigslist.scrape(_PROFILE, "Portland, OR")

    assert result == []
    mock_get.assert_not_called()


def test_hours_old_filter():
    """Items older than hours_old are excluded."""
    profile = {"titles": ["Customer Success Manager"], "hours_old": 48}
    with patch("scripts.custom_boards.craigslist._load_config",
               return_value=_SINGLE_METRO_CONFIG):
        with patch("scripts.custom_boards.craigslist.requests.get",
                   return_value=_mock_resp(_OLD_ITEM_RSS)):
            from scripts.custom_boards import craigslist
            result = craigslist.scrape(profile, "San Francisco Bay Area, CA")

    assert result == []


def test_dedup_within_run():
    """Same URL from two different metros is only returned once."""
    same_url_rss = _make_rss([{
        "title": "CSM Role",
        "link": "https://sfbay.craigslist.org/jjj/d/csm/1234.html",
        "description": "Same job.",
        "pubDate": _pubdate(1),
    }])
    with patch("scripts.custom_boards.craigslist._load_config",
               return_value=_TWO_METRO_CONFIG):
        with patch("scripts.custom_boards.craigslist.requests.get",
                   return_value=_mock_resp(same_url_rss)):
            from scripts.custom_boards import craigslist
            result = craigslist.scrape(_PROFILE, "Remote")

    urls = [r["url"] for r in result]
    assert len(urls) == len(set(urls))


def test_http_error_graceful():
    """HTTP error → [] without raising."""
    with patch("scripts.custom_boards.craigslist._load_config",
               return_value=_SINGLE_METRO_CONFIG):
        with patch("scripts.custom_boards.craigslist.requests.get",
                   side_effect=requests.RequestException("timeout")):
            from scripts.custom_boards import craigslist
            result = craigslist.scrape(_PROFILE, "San Francisco Bay Area, CA")

    assert result == []


def test_results_wanted_cap():
    """Never returns more than results_wanted items."""
    with patch("scripts.custom_boards.craigslist._load_config",
               return_value=_TWO_METRO_CONFIG):
        with patch("scripts.custom_boards.craigslist.requests.get",
                   return_value=_mock_resp(_TWO_ITEM_RSS)):
            from scripts.custom_boards import craigslist
            result = craigslist.scrape(_PROFILE, "Remote", results_wanted=1)

    assert len(result) <= 1
```

**Step 2: Run tests to verify they all fail**

```bash
/devl/miniconda3/envs/job-seeker/bin/pytest tests/test_craigslist.py -v
```

Expected: `ModuleNotFoundError: No module named 'scripts.custom_boards.craigslist'`

---

## Task 3: Implement `scripts/custom_boards/craigslist.py`

**Files:**
- Create: `scripts/custom_boards/craigslist.py`

**Step 1: Create the scraper**

```python
"""Craigslist job scraper — RSS-based.

Uses Craigslist's native RSS feed endpoint for discovery.
Full job description is populated by the scrape_url background task.
Company name and salary (not structured in Craigslist listings) are
extracted from the description body by the enrich_craigslist task.

Config: config/craigslist.yaml  (gitignored — metro list + location map)
        config/craigslist.yaml.example  (committed template)

Returns a list of dicts compatible with scripts.db.insert_job().
"""
from __future__ import annotations

import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import quote_plus

import requests
import yaml

_CONFIG_PATH = Path(__file__).parent.parent.parent / "config" / "craigslist.yaml"
_DEFAULT_CATEGORY = "jjj"
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    )
}
_TIMEOUT = 15
_SLEEP = 0.5  # seconds between requests — easy to make configurable later


def _load_config() -> dict:
    if not _CONFIG_PATH.exists():
        raise FileNotFoundError(
            f"Craigslist config not found: {_CONFIG_PATH}\n"
            "Copy config/craigslist.yaml.example → config/craigslist.yaml "
            "and configure your target metros."
        )
    cfg = yaml.safe_load(_CONFIG_PATH.read_text()) or {}
    if not cfg.get("metros"):
        raise ValueError(
            "config/craigslist.yaml must contain at least one entry under 'metros'."
        )
    return cfg


def _rss_url(metro: str, category: str, query: str) -> str:
    return (
        f"https://{metro}.craigslist.org/search/{category}"
        f"?query={quote_plus(query)}&format=rss&sort=date"
    )


def _parse_pubdate(pubdate_str: str) -> datetime | None:
    """Parse an RSS pubDate string to a timezone-aware datetime."""
    try:
        return parsedate_to_datetime(pubdate_str)
    except Exception:
        return None


def _fetch_rss(url: str) -> list[dict]:
    """Fetch and parse a Craigslist RSS feed. Returns list of raw item dicts."""
    resp = requests.get(url, headers=_HEADERS, timeout=_TIMEOUT)
    resp.raise_for_status()
    try:
        root = ET.fromstring(resp.content)
    except ET.ParseError as exc:
        raise ValueError(f"Malformed RSS XML: {exc}") from exc

    items = []
    for item in root.findall(".//item"):
        def _text(tag: str, _item=item) -> str:
            el = _item.find(tag)
            return (el.text or "").strip() if el is not None else ""

        items.append({
            "title":       _text("title"),
            "link":        _text("link"),
            "description": _text("description"),
            "pubDate":     _text("pubDate"),
        })
    return items


def scrape(profile: dict, location: str, results_wanted: int = 50) -> list[dict]:
    """Fetch jobs from Craigslist RSS for a single location.

    Args:
        profile: Search profile dict from search_profiles.yaml.
        location: Location string (e.g. "Remote" or "San Francisco Bay Area, CA").
        results_wanted: Maximum results to return across all metros and titles.

    Returns:
        List of job dicts with keys: title, company, url, source, location,
        is_remote, salary, description.
        company/salary are empty — filled later by enrich_craigslist task.
    """
    try:
        cfg = _load_config()
    except (FileNotFoundError, ValueError) as exc:
        print(f"    [craigslist] Skipped — {exc}")
        return []

    metros_all: list[str] = cfg.get("metros", [])
    location_map: dict[str, str] = cfg.get("location_map", {})
    category: str = cfg.get("category") or _DEFAULT_CATEGORY

    is_remote_search = location.lower() == "remote"
    if is_remote_search:
        metros = metros_all
    else:
        metro = location_map.get(location)
        if not metro:
            print(f"    [craigslist] No metro mapping for '{location}' — skipping")
            return []
        metros = [metro]

    titles: list[str] = profile.get("titles", [])
    hours_old: int = profile.get("hours_old", 240)
    cutoff = datetime.now(tz=timezone.utc).timestamp() - (hours_old * 3600)

    seen_urls: set[str] = set()
    results: list[dict] = []

    for metro in metros:
        if len(results) >= results_wanted:
            break

        for title in titles:
            if len(results) >= results_wanted:
                break

            url = _rss_url(metro, category, title)
            try:
                items = _fetch_rss(url)
            except requests.RequestException as exc:
                print(f"    [craigslist] HTTP error ({metro}/{title}): {exc}")
                time.sleep(_SLEEP)
                continue
            except ValueError as exc:
                print(f"    [craigslist] Parse error ({metro}/{title}): {exc}")
                time.sleep(_SLEEP)
                continue

            for item in items:
                if len(results) >= results_wanted:
                    break

                item_url = item.get("link", "")
                if not item_url or item_url in seen_urls:
                    continue

                pub = _parse_pubdate(item.get("pubDate", ""))
                if pub and pub.timestamp() < cutoff:
                    continue

                seen_urls.add(item_url)
                results.append({
                    "title":       item.get("title", ""),
                    "company":     "",
                    "url":         item_url,
                    "source":      "craigslist",
                    "location":    f"{metro} (Craigslist)",
                    "is_remote":   is_remote_search,
                    "salary":      "",
                    "description": "",
                })

            time.sleep(_SLEEP)

    return results[:results_wanted]
```

**Step 2: Run tests**

```bash
/devl/miniconda3/envs/job-seeker/bin/pytest tests/test_craigslist.py -v
```

Expected: all 8 PASS

**Step 3: Run full test suite to check for regressions**

```bash
/devl/miniconda3/envs/job-seeker/bin/pytest tests/ -v
```

Expected: all existing tests still PASS

**Step 4: Commit**

```bash
git add scripts/custom_boards/craigslist.py tests/test_craigslist.py
git commit -m "feat: add Craigslist RSS scraper to custom_boards"
```

---

## Task 4: Wire into discover.py + search_profiles.yaml

**Files:**
- Modify: `scripts/discover.py:20-32`
- Modify: `config/search_profiles.yaml`

**Step 1: Add to `CUSTOM_SCRAPERS` registry in `discover.py`**

Find this block (around line 20):

```python
from scripts.custom_boards import adzuna as _adzuna
from scripts.custom_boards import theladders as _theladders
```

Replace with:

```python
from scripts.custom_boards import adzuna as _adzuna
from scripts.custom_boards import theladders as _theladders
from scripts.custom_boards import craigslist as _craigslist
```

Find:

```python
CUSTOM_SCRAPERS: dict[str, object] = {
    "adzuna": _adzuna.scrape,
    "theladders": _theladders.scrape,
}
```

Replace with:

```python
CUSTOM_SCRAPERS: dict[str, object] = {
    "adzuna": _adzuna.scrape,
    "theladders": _theladders.scrape,
    "craigslist": _craigslist.scrape,
}
```

**Step 2: Add `craigslist` to relevant profiles in `config/search_profiles.yaml`**

For each profile that has `custom_boards:`, add `- craigslist`. Example — the `cs_leadership` profile currently has:

```yaml
  custom_boards:
  - adzuna
  - theladders
```

Change to:

```yaml
  custom_boards:
  - adzuna
  - theladders
  - craigslist
```

Repeat for all profiles where Craigslist makes sense (all of them — remote + SF Bay Area are both mapped).

**Step 3: Verify discover.py imports cleanly**

```bash
conda run -n job-seeker python -c "from scripts.discover import CUSTOM_SCRAPERS; print(list(CUSTOM_SCRAPERS.keys()))"
```

Expected: `['adzuna', 'theladders', 'craigslist']`

**Step 4: Commit**

```bash
git add scripts/discover.py config/search_profiles.yaml
git commit -m "feat: register craigslist scraper in discover.py and search profiles"
```

---

## Task 5: LLM enrichment — extract company + salary for Craigslist jobs

**Files:**
- Modify: `scripts/enrich_descriptions.py`
- Modify: `scripts/task_runner.py`

**Step 1: Read `scripts/task_runner.py`** to understand the `scrape_url` completion handler before editing.

**Step 2: Add `enrich_craigslist_fields()` to `enrich_descriptions.py`**

Add this function after `enrich_all_descriptions` (before `if __name__ == "__main__"`):

```python
def enrich_craigslist_fields(
    db_path: Path = DEFAULT_DB,
    job_id: int = None,
) -> dict:
    """
    Use LLM to extract company name and salary from a Craigslist job description.

    Called after scrape_url populates the description for a craigslist job.
    Only runs when: source='craigslist', company='', description non-empty.

    Returns dict with keys 'company' and/or 'salary' (may be empty strings).
    """
    import sqlite3 as _sq
    conn = _sq.connect(db_path)
    conn.row_factory = _sq.Row
    row = conn.execute(
        "SELECT id, description, company, source FROM jobs WHERE id=?", (job_id,)
    ).fetchone()
    conn.close()

    if not row:
        return {}
    if row["source"] != "craigslist":
        return {}
    if row["company"]:  # already populated
        return {}
    if not (row["description"] or "").strip():
        return {}

    sys.path.insert(0, str(Path(__file__).parent.parent))
    from scripts.llm_router import LLMRouter

    prompt = (
        "Extract the following from this job posting. "
        "Return JSON only, no commentary.\n\n"
        '{"company": "<company name or empty string>", '
        '"salary": "<salary/compensation or empty string>"}\n\n'
        f"Posting:\n{row['description'][:3000]}"
    )

    try:
        router = LLMRouter()
        raw = router.complete(prompt)
    except Exception as exc:
        print(f"[enrich_craigslist] LLM error for job {job_id}: {exc}")
        return {}

    import json, re
    try:
        # Strip markdown code fences if present
        clean = re.sub(r"```(?:json)?|```", "", raw).strip()
        fields = json.loads(clean)
    except (json.JSONDecodeError, ValueError):
        print(f"[enrich_craigslist] Could not parse LLM response for job {job_id}: {raw!r}")
        return {}

    extracted = {
        k: (fields.get(k) or "").strip()
        for k in ("company", "salary")
        if (fields.get(k) or "").strip()
    }

    if extracted:
        from scripts.db import update_job_fields
        update_job_fields(db_path, job_id, extracted)
        print(f"[enrich_craigslist] job {job_id}: "
              f"company={extracted.get('company', '—')} "
              f"salary={extracted.get('salary', '—')}")

    return extracted
```

Also add `import sys` to the top of `enrich_descriptions.py` if not already present.

**Step 3: Add `enrich_craigslist` task type to `task_runner.py`**

In `_run_task`, add a new `elif` branch. Find the block that handles `scrape_url` and add after it:

```python
        elif task_type == "enrich_craigslist":
            from scripts.enrich_descriptions import enrich_craigslist_fields
            extracted = enrich_craigslist_fields(db_path, job_id)
            company = extracted.get("company", "")
            msg = f"company={company}" if company else "no company found"
            update_task_status(db_path, task_id, "completed", error=msg)
            return
```

**Step 4: Auto-submit `enrich_craigslist` after `scrape_url` for Craigslist jobs**

Still in `task_runner.py`, find the `scrape_url` completion handler. After the `update_task_status` call for `scrape_url`, add:

```python
            # Auto-enrich company/salary for Craigslist jobs
            import sqlite3 as _sq
            _conn = _sq.connect(db_path)
            _conn.row_factory = _sq.Row
            _job = _conn.execute(
                "SELECT source, company FROM jobs WHERE id=?", (job_id,)
            ).fetchone()
            _conn.close()
            if _job and _job["source"] == "craigslist" and not _job["company"]:
                submit_task(db_path, "enrich_craigslist", job_id)
```

**Step 5: Smoke test — run a discovery cycle and check a craigslist job**

```bash
conda run -n job-seeker python -c "
from scripts.custom_boards.craigslist import scrape
jobs = scrape({'titles': ['Customer Success Manager'], 'hours_old': 48}, 'San Francisco Bay Area, CA', results_wanted=3)
for j in jobs:
    print(j['title'], '|', j['url'])
"
```

Expected: 0–3 job dicts printed (may be 0 if no recent postings — that's fine).

**Step 6: Commit**

```bash
git add scripts/enrich_descriptions.py scripts/task_runner.py
git commit -m "feat: add enrich_craigslist task for LLM company/salary extraction"
```

---

## Final: push to remote

```bash
git push origin main
```
