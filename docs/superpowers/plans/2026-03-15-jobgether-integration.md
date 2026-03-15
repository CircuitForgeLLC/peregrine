# Jobgether Integration Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Filter Jobgether listings out of all other scrapers, add a dedicated Jobgether scraper and URL scraper (Playwright-based), and add recruiter-aware cover letter framing for Jobgether jobs.

**Architecture:** Blocklist config handles filtering with zero code changes. A new `_scrape_jobgether()` in `scrape_url.py` handles manual URL imports via Playwright with URL slug fallback. A new `scripts/custom_boards/jobgether.py` handles discovery. Cover letter framing is an `is_jobgether` flag threaded from `task_runner.py` → `generate()` → `build_prompt()`.

**Tech Stack:** Python, Playwright (already installed), SQLite, PyTest, YAML config

**Spec:** `/Library/Development/CircuitForge/peregrine/docs/superpowers/specs/2026-03-15-jobgether-integration-design.md`

---

## Worktree Setup

- [ ] **Create worktree for this feature**

```bash
cd /Library/Development/CircuitForge/peregrine
git worktree add .worktrees/jobgether-integration -b feature/jobgether-integration
```

All implementation work happens in `/Library/Development/CircuitForge/peregrine/.worktrees/jobgether-integration/`.

---

## Chunk 1: Blocklist filter + scrape_url.py

### Task 1: Add Jobgether to blocklist

**Files:**
- Modify: `/Library/Development/CircuitForge/peregrine/config/blocklist.yaml`

- [ ] **Step 1: Edit blocklist.yaml**

```yaml
companies:
  - jobgether
```

- [ ] **Step 2: Verify the existing `_is_blocklisted` test passes (or write one)**

Check `/Library/Development/CircuitForge/peregrine/tests/test_discover.py` for existing blocklist tests. If none cover company matching, add:

```python
def test_is_blocklisted_jobgether():
    from scripts.discover import _is_blocklisted
    blocklist = {"companies": ["jobgether"], "industries": [], "locations": []}
    assert _is_blocklisted({"company": "Jobgether", "location": "", "description": ""}, blocklist)
    assert _is_blocklisted({"company": "jobgether inc", "location": "", "description": ""}, blocklist)
    assert not _is_blocklisted({"company": "Acme Corp", "location": "", "description": ""}, blocklist)
```

Run: `conda run -n job-seeker python -m pytest tests/test_discover.py -v -k "blocklist"`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add config/blocklist.yaml tests/test_discover.py
git commit -m "feat: filter Jobgether listings via blocklist"
```

---

### Task 2: Add Jobgether detection to scrape_url.py

**Files:**
- Modify: `/Library/Development/CircuitForge/peregrine/scripts/scrape_url.py`
- Modify: `/Library/Development/CircuitForge/peregrine/tests/test_scrape_url.py`

- [ ] **Step 1: Write failing tests**

In `/Library/Development/CircuitForge/peregrine/tests/test_scrape_url.py`, add:

```python
def test_detect_board_jobgether():
    from scripts.scrape_url import _detect_board
    assert _detect_board("https://jobgether.com/offer/69b42d9d24d79271ee0618e8-csm---resware") == "jobgether"
    assert _detect_board("https://www.jobgether.com/offer/abc-role---company") == "jobgether"


def test_jobgether_slug_company_extraction():
    from scripts.scrape_url import _company_from_jobgether_url
    assert _company_from_jobgether_url(
        "https://jobgether.com/offer/69b42d9d24d79271ee0618e8-customer-success-manager---resware"
    ) == "Resware"
    assert _company_from_jobgether_url(
        "https://jobgether.com/offer/abc123-director-of-cs---acme-corp"
    ) == "Acme Corp"
    assert _company_from_jobgether_url(
        "https://jobgether.com/offer/abc123-no-separator-here"
    ) == ""


def test_scrape_jobgether_no_playwright(tmp_path):
    """When Playwright is unavailable, _scrape_jobgether falls back to URL slug for company."""
    # Patch playwright.sync_api to None in sys.modules so the local import inside
    # _scrape_jobgether raises ImportError at call time (local imports run at call time,
    # not at module load time — so no reload needed).
    import sys
    import unittest.mock as mock

    url = "https://jobgether.com/offer/69b42d9d24d79271ee0618e8-customer-success-manager---resware"
    with mock.patch.dict(sys.modules, {"playwright": None, "playwright.sync_api": None}):
        from scripts.scrape_url import _scrape_jobgether
        result = _scrape_jobgether(url)

    assert result.get("company") == "Resware"
    assert result.get("source") == "jobgether"
```

Run: `conda run -n job-seeker python -m pytest tests/test_scrape_url.py::test_detect_board_jobgether tests/test_scrape_url.py::test_jobgether_slug_company_extraction tests/test_scrape_url.py::test_scrape_jobgether_no_playwright -v`
Expected: FAIL (functions not yet defined)

- [ ] **Step 2: Add `_company_from_jobgether_url()` to scrape_url.py**

Add after the `_STRIP_PARAMS` block (around line 34):

```python
def _company_from_jobgether_url(url: str) -> str:
    """Extract company name from Jobgether offer URL slug.

    Slug format: /offer/{24-hex-hash}-{title-slug}---{company-slug}
    Triple-dash separator delimits title from company.
    Returns title-cased company name, or "" if pattern not found.
    """
    m = re.search(r"---([^/?]+)$", urlparse(url).path)
    if not m:
        print(f"[scrape_url] Jobgether URL slug: no company separator found in {url}")
        return ""
    return m.group(1).replace("-", " ").title()
```

- [ ] **Step 3: Add `"jobgether"` branch to `_detect_board()`**

In `/Library/Development/CircuitForge/peregrine/scripts/scrape_url.py`, modify `_detect_board()` (add before `return "generic"`):

```python
    if "jobgether.com" in url_lower:
        return "jobgether"
```

- [ ] **Step 4: Add `_scrape_jobgether()` function**

Add after `_scrape_glassdoor()` (around line 137):

```python
def _scrape_jobgether(url: str) -> dict:
    """Scrape a Jobgether offer page using Playwright to bypass 403.

    Falls back to URL slug for company name when Playwright is unavailable.
    Does not use requests — no raise_for_status().
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        company = _company_from_jobgether_url(url)
        if company:
            print(f"[scrape_url] Jobgether: Playwright not installed, using slug fallback → {company}")
        return {"company": company, "source": "jobgether"} if company else {}

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                ctx = browser.new_context(user_agent=_HEADERS["User-Agent"])
                page = ctx.new_page()
                page.goto(url, timeout=30_000)
                page.wait_for_load_state("networkidle", timeout=20_000)

                result = page.evaluate("""() => {
                    const title = document.querySelector('h1')?.textContent?.trim() || '';
                    const company = document.querySelector('[class*="company"], [class*="employer"], [data-testid*="company"]')
                        ?.textContent?.trim() || '';
                    const location = document.querySelector('[class*="location"], [data-testid*="location"]')
                        ?.textContent?.trim() || '';
                    const desc = document.querySelector('[class*="description"], [class*="job-desc"], article')
                        ?.innerText?.trim() || '';
                    return { title, company, location, description: desc };
                }""")
            finally:
                browser.close()

        # Fall back to slug for company if DOM extraction missed it
        if not result.get("company"):
            result["company"] = _company_from_jobgether_url(url)

        result["source"] = "jobgether"
        return {k: v for k, v in result.items() if v}

    except Exception as exc:
        print(f"[scrape_url] Jobgether Playwright error for {url}: {exc}")
        # Last resort: slug fallback
        company = _company_from_jobgether_url(url)
        return {"company": company, "source": "jobgether"} if company else {}
```

> ⚠️ **The CSS selectors in the `page.evaluate()` call are placeholders.** Before committing, inspect `https://jobgether.com/offer/` in a browser to find the actual class names for title, company, location, and description. Update the selectors accordingly.

- [ ] **Step 5: Add dispatch branch in `scrape_job_url()`**

In the `if board == "linkedin":` dispatch chain (around line 208), add before the `else`:

```python
        elif board == "jobgether":
            fields = _scrape_jobgether(url)
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `conda run -n job-seeker python -m pytest tests/test_scrape_url.py -v`
Expected: All PASS (including pre-existing tests)

- [ ] **Step 7: Commit**

```bash
git add scripts/scrape_url.py tests/test_scrape_url.py
git commit -m "feat: add Jobgether URL detection and scraper to scrape_url.py"
```

---

## Chunk 2: Jobgether custom board scraper

> ⚠️ **Pre-condition:** Before writing the scraper, inspect `https://jobgether.com/remote-jobs` live to determine the actual URL/filter param format and DOM card selectors. Use the Playwright MCP browser tool or Chrome devtools. Record: (1) the query param for job title search, (2) the job card CSS selectors for title, company, URL, location, salary.

### Task 3: Inspect Jobgether search live

**Files:** None (research step)

- [ ] **Step 1: Navigate to Jobgether remote jobs and inspect search params**

Using browser devtools or Playwright network capture, navigate to `https://jobgether.com/remote-jobs`, search for "Customer Success Manager", and capture:
- The resulting URL (query params)
- Network requests (XHR/fetch) if the page uses API calls
- CSS selectors for job card elements

Record findings here before proceeding.

- [ ] **Step 2: Test a Playwright page.evaluate() extraction manually**

```python
# Run interactively to validate selectors
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)  # headless=False to see the page
    page = browser.new_page()
    page.goto("https://jobgether.com/remote-jobs")
    page.wait_for_load_state("networkidle")
    # Test your selectors here
    cards = page.query_selector_all("[YOUR_CARD_SELECTOR]")
    print(len(cards))
    browser.close()
```

---

### Task 4: Write jobgether.py scraper

**Files:**
- Create: `/Library/Development/CircuitForge/peregrine/scripts/custom_boards/jobgether.py`
- Modify: `/Library/Development/CircuitForge/peregrine/tests/test_discover.py` (or create `tests/test_jobgether.py`)

- [ ] **Step 1: Write failing test**

In `/Library/Development/CircuitForge/peregrine/tests/test_discover.py` (or a new `tests/test_jobgether.py`):

```python
def test_jobgether_scraper_returns_empty_on_missing_playwright(monkeypatch):
    """Graceful fallback when Playwright is unavailable."""
    import scripts.custom_boards.jobgether as jg
    monkeypatch.setattr("scripts.custom_boards.jobgether.sync_playwright", None)
    result = jg.scrape({"titles": ["Customer Success Manager"]}, "Remote", results_wanted=5)
    assert result == []


def test_jobgether_scraper_respects_results_wanted(monkeypatch):
    """Scraper caps results at results_wanted."""
    import scripts.custom_boards.jobgether as jg

    fake_jobs = [
        {"title": f"CSM {i}", "href": f"/offer/abc{i}-csm---acme", "company": f"Acme {i}",
         "location": "Remote", "is_remote": True, "salary": ""}
        for i in range(20)
    ]

    class FakePage:
        def goto(self, *a, **kw): pass
        def wait_for_load_state(self, *a, **kw): pass
        def evaluate(self, _): return fake_jobs

    class FakeCtx:
        def new_page(self): return FakePage()

    class FakeBrowser:
        def new_context(self, **kw): return FakeCtx()
        def close(self): pass

    class FakeChromium:
        def launch(self, **kw): return FakeBrowser()

    class FakeP:
        chromium = FakeChromium()
        def __enter__(self): return self
        def __exit__(self, *a): pass

    monkeypatch.setattr("scripts.custom_boards.jobgether.sync_playwright", lambda: FakeP())
    result = jg.scrape({"titles": ["CSM"]}, "Remote", results_wanted=5)
    assert len(result) <= 5
```

Run: `conda run -n job-seeker python -m pytest tests/ -v -k "jobgether"`
Expected: FAIL (module not found)

- [ ] **Step 2: Create `scripts/custom_boards/jobgether.py`**

```python
"""Jobgether scraper — Playwright-based (requires chromium installed).

Jobgether (jobgether.com) is a remote-work job aggregator. It blocks plain
requests with 403, so we use Playwright to render the page and extract cards.

Install Playwright: conda run -n job-seeker pip install playwright &&
                   conda run -n job-seeker python -m playwright install chromium

Returns a list of dicts compatible with scripts.db.insert_job().
"""
from __future__ import annotations

import re
import time
from typing import Any

_BASE = "https://jobgether.com"
_SEARCH_PATH = "/remote-jobs"

# TODO: Replace with confirmed query param key after live inspection (Task 3)
_QUERY_PARAM = "search"

# Module-level import so tests can monkeypatch scripts.custom_boards.jobgether.sync_playwright
try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sync_playwright = None


def scrape(profile: dict, location: str, results_wanted: int = 50) -> list[dict]:
    """
    Scrape job listings from Jobgether using Playwright.

    Args:
        profile: Search profile dict (uses 'titles').
        location: Location string — Jobgether is remote-focused; location used
                  only if the site exposes a location filter.
        results_wanted: Maximum results to return across all titles.

    Returns:
        List of job dicts with keys: title, company, url, source, location,
        is_remote, salary, description.
    """
    if sync_playwright is None:
        print(
            "    [jobgether] playwright not installed.\n"
            "    Install: conda run -n job-seeker pip install playwright && "
            "conda run -n job-seeker python -m playwright install chromium"
        )
        return []

    results: list[dict] = []
    seen_urls: set[str] = set()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            )
        )
        page = ctx.new_page()

        for title in profile.get("titles", []):
            if len(results) >= results_wanted:
                break

            # TODO: Confirm URL param format from live inspection (Task 3)
            url = f"{_BASE}{_SEARCH_PATH}?{_QUERY_PARAM}={title.replace(' ', '+')}"

            try:
                page.goto(url, timeout=30_000)
                page.wait_for_load_state("networkidle", timeout=20_000)
            except Exception as exc:
                print(f"    [jobgether] Page load error for '{title}': {exc}")
                continue

            # TODO: Replace JS selector with confirmed card selector from Task 3
            try:
                raw_jobs: list[dict[str, Any]] = page.evaluate(_extract_jobs_js())
            except Exception as exc:
                print(f"    [jobgether] JS extract error for '{title}': {exc}")
                continue

            if not raw_jobs:
                print(f"    [jobgether] No cards found for '{title}' — selector may need updating")
                continue

            for job in raw_jobs:
                href = job.get("href", "")
                if not href:
                    continue
                full_url = _BASE + href if href.startswith("/") else href
                if full_url in seen_urls:
                    continue
                seen_urls.add(full_url)

                results.append({
                    "title":       job.get("title", ""),
                    "company":     job.get("company", ""),
                    "url":         full_url,
                    "source":      "jobgether",
                    "location":    job.get("location") or "Remote",
                    "is_remote":   True,  # Jobgether is remote-focused
                    "salary":      job.get("salary") or "",
                    "description": "",  # not in card view; scrape_url fills in
                })

                if len(results) >= results_wanted:
                    break

            time.sleep(1)  # polite pacing between titles

        browser.close()

    return results[:results_wanted]


def _extract_jobs_js() -> str:
    """JS to run in page context — extracts job data from rendered card elements.

    TODO: Replace selectors with confirmed values from Task 3 live inspection.
    """
    return """() => {
        // TODO: replace '[class*=job-card]' with confirmed card selector
        const cards = document.querySelectorAll('[class*="job-card"], [data-testid*="job"]');
        return Array.from(cards).map(card => {
            // TODO: replace these selectors with confirmed values
            const titleEl = card.querySelector('h2, h3, [class*="title"]');
            const companyEl = card.querySelector('[class*="company"], [class*="employer"]');
            const linkEl = card.querySelector('a');
            const salaryEl = card.querySelector('[class*="salary"]');
            const locationEl = card.querySelector('[class*="location"]');
            return {
                title: titleEl ? titleEl.textContent.trim() : null,
                company: companyEl ? companyEl.textContent.trim() : null,
                href: linkEl ? linkEl.getAttribute('href') : null,
                salary: salaryEl ? salaryEl.textContent.trim() : null,
                location: locationEl ? locationEl.textContent.trim() : null,
                is_remote: true,
            };
        }).filter(j => j.title && j.href);
    }"""
```

- [ ] **Step 3: Run tests**

Run: `conda run -n job-seeker python -m pytest tests/ -v -k "jobgether"`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add scripts/custom_boards/jobgether.py tests/test_discover.py
git commit -m "feat: add Jobgether custom board scraper (selectors pending live inspection)"
```

---

## Chunk 3: Registration, config, cover letter framing

### Task 5: Register scraper in discover.py + update search_profiles.yaml

**Files:**
- Modify: `/Library/Development/CircuitForge/peregrine/scripts/discover.py`
- Modify: `/Library/Development/CircuitForge/peregrine/config/search_profiles.yaml`
- Modify: `/Library/Development/CircuitForge/peregrine/config/search_profiles.yaml.example` (if it exists)

- [ ] **Step 1: Add import to discover.py import block (lines 20–22)**

`jobgether.py` absorbs the Playwright `ImportError` internally (module-level `try/except`), so it always imports successfully. Match the existing pattern exactly:

```python
from scripts.custom_boards import jobgether as _jobgether
```

- [ ] **Step 2: Add to CUSTOM_SCRAPERS dict literal (lines 30–34)**

```python
CUSTOM_SCRAPERS: dict[str, object] = {
    "adzuna":     _adzuna.scrape,
    "theladders": _theladders.scrape,
    "craigslist": _craigslist.scrape,
    "jobgether":  _jobgether.scrape,
}
```

When Playwright is absent, `_jobgether.scrape()` returns `[]` gracefully — no special guard needed in `discover.py`.

- [ ] **Step 3: Add `jobgether` to remote-eligible profiles in search_profiles.yaml**

Add `- jobgether` to the `custom_boards` list for every profile that has `Remote` in its `locations`. Based on the current file, that means: `cs_leadership`, `music_industry`, `animal_welfare`, `education`. Do NOT add it to `default` (locations: San Francisco CA only).

- [ ] **Step 4: Run discover tests**

Run: `conda run -n job-seeker python -m pytest tests/test_discover.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/discover.py config/search_profiles.yaml
git commit -m "feat: register Jobgether scraper and add to remote search profiles"
```

---

### Task 6: Cover letter recruiter framing

**Files:**
- Modify: `/Library/Development/CircuitForge/peregrine/scripts/generate_cover_letter.py`
- Modify: `/Library/Development/CircuitForge/peregrine/scripts/task_runner.py`
- Modify: `/Library/Development/CircuitForge/peregrine/tests/test_match.py` or add `tests/test_cover_letter.py`

- [ ] **Step 1: Write failing test**

Create or add to `/Library/Development/CircuitForge/peregrine/tests/test_cover_letter.py`:

```python
def test_build_prompt_jobgether_framing_unknown_company():
    from scripts.generate_cover_letter import build_prompt
    prompt = build_prompt(
        title="Customer Success Manager",
        company="Jobgether",
        description="CSM role at an undisclosed company.",
        examples=[],
        is_jobgether=True,
    )
    assert "Your client" in prompt
    assert "recruiter" in prompt.lower() or "jobgether" in prompt.lower()


def test_build_prompt_jobgether_framing_known_company():
    from scripts.generate_cover_letter import build_prompt
    prompt = build_prompt(
        title="Customer Success Manager",
        company="Resware",
        description="CSM role at Resware.",
        examples=[],
        is_jobgether=True,
    )
    assert "Your client at Resware" in prompt


def test_build_prompt_no_jobgether_framing_by_default():
    from scripts.generate_cover_letter import build_prompt
    prompt = build_prompt(
        title="Customer Success Manager",
        company="Acme Corp",
        description="CSM role.",
        examples=[],
    )
    assert "Your client" not in prompt
```

Run: `conda run -n job-seeker python -m pytest tests/test_cover_letter.py -v`
Expected: FAIL

- [ ] **Step 2: Add `is_jobgether` to `build_prompt()` in generate_cover_letter.py**

Modify the `build_prompt()` signature (line 186):

```python
def build_prompt(
    title: str,
    company: str,
    description: str,
    examples: list[dict],
    mission_hint: str | None = None,
    is_jobgether: bool = False,
) -> str:
```

Add the recruiter hint block after the `mission_hint` block (after line 203):

```python
    if is_jobgether:
        if company and company.lower() != "jobgether":
            recruiter_note = (
                f"🤝 Recruiter context: This listing is posted by Jobgether on behalf of "
                f"{company}. Address the cover letter to the Jobgether recruiter, not directly "
                f"to the hiring company. Use framing like 'Your client at {company} will "
                f"appreciate...' rather than addressing {company} directly. The role "
                f"requirements are those of the actual employer."
            )
        else:
            recruiter_note = (
                "🤝 Recruiter context: This listing is posted by Jobgether on behalf of an "
                "undisclosed employer. Address the cover letter to the Jobgether recruiter. "
                "Use framing like 'Your client will appreciate...' rather than addressing "
                "the company directly."
            )
        parts.append(f"{recruiter_note}\n")
```

- [ ] **Step 3: Add `is_jobgether` to `generate()` signature**

Modify `generate()` (line 233):

```python
def generate(
    title: str,
    company: str,
    description: str = "",
    previous_result: str = "",
    feedback: str = "",
    is_jobgether: bool = False,
    _router=None,
) -> str:
```

Pass it through to `build_prompt()` (line 254):

```python
    prompt = build_prompt(title, company, description, examples,
                          mission_hint=mission_hint, is_jobgether=is_jobgether)
```

- [ ] **Step 4: Pass `is_jobgether` from task_runner.py**

In `/Library/Development/CircuitForge/peregrine/scripts/task_runner.py`, modify the `generate()` call inside the `cover_letter` task block (`elif task_type == "cover_letter":` starts at line 152; the `generate()` call is at ~line 156):

```python
        elif task_type == "cover_letter":
            import json as _json
            p = _json.loads(params or "{}")
            from scripts.generate_cover_letter import generate
            result = generate(
                job.get("title", ""),
                job.get("company", ""),
                job.get("description", ""),
                previous_result=p.get("previous_result", ""),
                feedback=p.get("feedback", ""),
                is_jobgether=job.get("source") == "jobgether",
            )
            update_cover_letter(db_path, job_id, result)
```

- [ ] **Step 5: Run tests**

Run: `conda run -n job-seeker python -m pytest tests/test_cover_letter.py -v`
Expected: All PASS

- [ ] **Step 6: Run full test suite**

Run: `conda run -n job-seeker python -m pytest tests/ -v`
Expected: All PASS

- [ ] **Step 7: Commit**

```bash
git add scripts/generate_cover_letter.py scripts/task_runner.py tests/test_cover_letter.py
git commit -m "feat: add Jobgether recruiter framing to cover letter generation"
```

---

## Final: Merge

- [ ] **Merge worktree branch to main**

```bash
cd /Library/Development/CircuitForge/peregrine
git merge feature/jobgether-integration
git worktree remove .worktrees/jobgether-integration
```

- [ ] **Push to remote**

```bash
git push origin main
```

---

## Manual verification after merge

1. Add the stuck Jobgether manual import (job 2286) — delete the old stuck row and re-add the URL via "Add Jobs by URL" in the Home page. Verify the scraper resolves company = "Resware".
2. Run a short discovery (`discover.py` with `results_per_board: 5`) and confirm no `company="Jobgether"` rows appear in `staging.db`.
3. Generate a cover letter for a Jobgether-sourced job and confirm recruiter framing appears.
