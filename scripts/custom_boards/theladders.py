"""The Ladders scraper — Playwright-based (requires chromium installed).

The Ladders is a client-side React app (no SSR __NEXT_DATA__). We use Playwright
to execute JS, wait for job cards to render, then extract from the DOM.

Company names are hidden from guest (non-logged-in) users, but are encoded in
the job URL slug: /job/{title-slug}-{company-slug}-{location-slug}_{id}

curl_cffi is no longer needed for this scraper; plain Playwright is sufficient.
playwright must be installed: `conda run -n job-seeker python -m playwright install chromium`

Returns a list of dicts compatible with scripts.db.insert_job().
"""
from __future__ import annotations

import re
import time
from typing import Any

_BASE = "https://www.theladders.com"
_SEARCH_PATH = "/jobs/searchjobs/{slug}"

# Location slug in URLs for remote jobs
_REMOTE_SLUG = "virtual-travel"


def _company_from_url(href: str, title_slug: str) -> str:
    """
    Extract company name from The Ladders job URL slug.

    URL format: /job/{title-slug}-{company-slug}-{location-slug}_{id}?ir=1
    Example: /job/customer-success-manager-gainsight-virtual-travel_85434789
             → "Gainsight"
    """
    # Strip path prefix and query
    slug = href.split("/job/", 1)[-1].split("?")[0]
    # Strip numeric ID suffix (e.g. _85434789)
    slug = re.sub(r"_\d+$", "", slug)
    # Strip known title prefix
    if slug.startswith(title_slug + "-"):
        slug = slug[len(title_slug) + 1:]
    # Strip common location suffixes
    for loc_suffix in [f"-{_REMOTE_SLUG}", "-new-york", "-los-angeles",
                       "-san-francisco", "-chicago", "-austin", "-seattle",
                       "-boston", "-atlanta", "-remote"]:
        if slug.endswith(loc_suffix):
            slug = slug[: -len(loc_suffix)]
            break
    # Convert kebab-case → title case
    return slug.replace("-", " ").title() if slug else ""


def _extract_jobs_js() -> str:
    """JS to run in page context — extracts job data from rendered card elements."""
    return """() => {
        const cards = document.querySelectorAll('[class*=job-card-container]');
        return Array.from(cards).map(card => {
            const link = card.querySelector('p.job-link-wrapper a, a.clipped-text');
            const salary = card.querySelector('p.salary, .salary-info p');
            const locEl = card.querySelector('.remote-location-text, .location-info');
            const remoteEl = card.querySelector('.remote-flag-badge-remote');
            return {
                title: link ? link.textContent.trim() : null,
                href: link ? link.getAttribute('href') : null,
                salary: salary ? salary.textContent.replace('*','').trim() : null,
                location: locEl ? locEl.textContent.trim() : null,
                is_remote: !!remoteEl,
            };
        }).filter(j => j.title && j.href);
    }"""


def scrape(profile: dict, location: str, results_wanted: int = 50) -> list[dict]:
    """
    Scrape job listings from The Ladders using Playwright.

    Args:
        profile: Search profile dict (uses 'titles').
        location: Location string (e.g. "Remote" or "San Francisco Bay Area, CA").
        results_wanted: Maximum results to return across all titles.

    Returns:
        List of job dicts with keys: title, company, url, source, location,
        is_remote, salary, description.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print(
            "    [theladders] playwright not installed.\n"
            "    Install: conda run -n job-seeker pip install playwright && "
            "conda run -n job-seeker python -m playwright install chromium"
        )
        return []

    is_remote_search = location.lower() == "remote"
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

            slug = title.lower().replace(" ", "-").replace("/", "-")
            title_slug = slug  # used for company extraction from URL

            params: dict[str, str] = {}
            if is_remote_search:
                params["remote"] = "true"
            elif location:
                params["location"] = location

            url = _BASE + _SEARCH_PATH.format(slug=slug)
            if params:
                query = "&".join(f"{k}={v}" for k, v in params.items())
                url = f"{url}?{query}"

            try:
                page.goto(url, timeout=30_000)
                page.wait_for_load_state("networkidle", timeout=20_000)
            except Exception as exc:
                print(f"    [theladders] Page load error for '{title}': {exc}")
                continue

            try:
                raw_jobs: list[dict[str, Any]] = page.evaluate(_extract_jobs_js())
            except Exception as exc:
                print(f"    [theladders] JS extract error for '{title}': {exc}")
                continue

            if not raw_jobs:
                print(f"    [theladders] No cards found for '{title}' — selector may need updating")
                continue

            for job in raw_jobs:
                href = job.get("href", "")
                if not href:
                    continue
                full_url = _BASE + href if href.startswith("/") else href
                if full_url in seen_urls:
                    continue
                seen_urls.add(full_url)

                company = _company_from_url(href, title_slug)
                loc_text = (job.get("location") or "").replace("Remote", "").strip(", ")
                if is_remote_search or job.get("is_remote"):
                    loc_display = "Remote" + (f" — {loc_text}" if loc_text and loc_text != "US-Anywhere" else "")
                else:
                    loc_display = loc_text or location

                results.append({
                    "title":       job.get("title", ""),
                    "company":     company,
                    "url":         full_url,
                    "source":      "theladders",
                    "location":    loc_display,
                    "is_remote":   bool(job.get("is_remote") or is_remote_search),
                    "salary":      job.get("salary") or "",
                    "description": "",  # not available in card view; scrape_url will fill in
                })

                if len(results) >= results_wanted:
                    break

            time.sleep(1)  # polite pacing between titles

        browser.close()

    return results[:results_wanted]
