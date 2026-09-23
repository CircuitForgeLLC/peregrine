# scripts/scrape_url.py
"""
Scrape a job listing from its URL and update the job record.

Supports:
  - LinkedIn  (guest jobs API — no auth required)
  - Indeed    (HTML parse)
  - Glassdoor (JobSpy internal scraper, same as enrich_descriptions.py)
  - Generic   (JSON-LD → og:tags fallback)

Usage (background task — called by task_runner):
    from scripts.scrape_url import scrape_job_url
    scrape_job_url(db_path, job_id)
"""
import json
import re
import sqlite3
import sys
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlparse

import requests
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.db import DEFAULT_DB, update_job_fields

_STRIP_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term",
    "trk", "trkEmail", "refId", "trackingId", "lipi", "midToken", "midSig",
    "eid", "otpToken", "ssid", "fmid",
}

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


_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    )
}
_TIMEOUT = 12


def _detect_board(url: str) -> str:
    """Return 'linkedin', 'indeed', 'glassdoor', 'jobgether', 'oracle_hcm', 'theladders', or 'generic'."""
    url_lower = url.lower()
    if "linkedin.com" in url_lower:
        return "linkedin"
    if "indeed.com" in url_lower:
        return "indeed"
    if "glassdoor.com" in url_lower:
        return "glassdoor"
    if "jobgether.com" in url_lower:
        return "jobgether"
    if "oraclecloud.com" in url_lower and "hcmui" in url_lower:
        return "oracle_hcm"
    if "theladders.com" in url_lower:
        return "theladders"
    return "generic"


def _extract_linkedin_job_id(url: str) -> str | None:
    """Extract numeric job ID from a LinkedIn job URL."""
    m = re.search(r"/jobs/view/(\d+)", url)
    return m.group(1) if m else None


def canonicalize_url(url: str) -> str:
    """
    Strip tracking parameters from a job URL and return a clean canonical form.

    LinkedIn:  https://www.linkedin.com/jobs/view/<id>/?trk=...  →  https://www.linkedin.com/jobs/view/<id>/
    Others:    strips utm_source/utm_medium/utm_campaign/trk/refId/trackingId
    """
    url = url.strip()
    if "linkedin.com" in url.lower():
        job_id = _extract_linkedin_job_id(url)
        if job_id:
            return f"https://www.linkedin.com/jobs/view/{job_id}/"
    parsed = urlparse(url)
    clean_qs = urlencode([(k, v) for k, v in parse_qsl(parsed.query) if k not in _STRIP_PARAMS])
    return parsed._replace(query=clean_qs).geturl()


def _scrape_linkedin(url: str) -> dict:
    """Fetch via LinkedIn guest jobs API (no auth required)."""
    job_id = _extract_linkedin_job_id(url)
    if not job_id:
        return {}
    api_url = f"https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{job_id}"
    resp = requests.get(api_url, headers=_HEADERS, timeout=_TIMEOUT)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    def _text(selector, **kwargs):
        tag = soup.find(selector, **kwargs)
        return tag.get_text(strip=True) if tag else ""

    title = _text("h2", class_="top-card-layout__title")
    company = _text("a", class_="topcard__org-name-link") or _text("span", class_="topcard__org-name-link")
    location = _text("span", class_="topcard__flavor--bullet")
    desc_div = soup.find("div", class_="show-more-less-html__markup")
    description = desc_div.get_text(separator="\n", strip=True) if desc_div else ""

    return {k: v for k, v in {
        "title": title,
        "company": company,
        "location": location,
        "description": description,
        "source": "linkedin",
    }.items() if v}


def _scrape_indeed(url: str) -> dict:
    """Scrape an Indeed job page."""
    resp = requests.get(url, headers=_HEADERS, timeout=_TIMEOUT)
    resp.raise_for_status()
    return _parse_json_ld_or_og(resp.text) or {}


def _scrape_glassdoor(url: str) -> dict:
    """Re-use JobSpy's Glassdoor scraper for description fetch."""
    m = re.search(r"jl=(\d+)", url)
    if not m:
        return {}
    try:
        from jobspy.glassdoor import Glassdoor
        from jobspy.glassdoor.constant import fallback_token, headers
        from jobspy.model import ScraperInput, Site
        from jobspy.util import create_session

        scraper = Glassdoor()
        scraper.base_url = "https://www.glassdoor.com/"
        scraper.session = create_session(has_retry=True)
        token = scraper._get_csrf_token()
        headers["gd-csrf-token"] = token if token else fallback_token
        scraper.scraper_input = ScraperInput(site_type=[Site.GLASSDOOR])
        description = scraper._fetch_job_description(int(m.group(1)))
        return {"description": description} if description else {}
    except Exception:  # noqa: BLE001 -- this block spans importing/using JobSpy's
        # internal Glassdoor scraper (CSRF token fetch, session creation, HTTP calls,
        # HTML/JSON parsing inside a third-party library we don't control), so the
        # failure surface isn't limited to one exception family. Description fetch is
        # a best-effort enrichment step; failing must degrade to an empty result, not
        # abort the whole scrape.
        return {}


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

    except Exception as exc:  # noqa: BLE001 -- Playwright browser automation (launch,
        # navigate, wait_for_load_state, in-page JS evaluate) can raise many distinct
        # playwright.sync_api errors (timeouts, target-closed, navigation failures), and
        # this scraper's contract (see docstring) is to always fall back to the URL-slug
        # company extraction rather than propagate a scrape failure.
        print(f"[scrape_url] Jobgether Playwright error for {url}: {exc}")
        company = _company_from_jobgether_url(url)
        return {"company": company, "source": "jobgether"} if company else {}


def _scrape_oracle_hcm(url: str) -> dict:
    """Scrape an Oracle HCM CandidateExperience job page via Playwright.

    Oracle HCM portals are React SPAs that require JS execution. The prospect
    token in the URL path grants public access — no auth needed.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("[scrape_url] Oracle HCM: Playwright not installed, falling back to generic")
        return _scrape_generic(url)

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                ctx = browser.new_context(user_agent=_HEADERS["User-Agent"])
                page = ctx.new_page()
                page.goto(url, timeout=30_000)
                page.wait_for_load_state("networkidle", timeout=20_000)

                result = page.evaluate("""() => {
                    const sel = (s) => document.querySelector(s)?.textContent?.trim() || '';
                    const selInner = (s) => document.querySelector(s)?.innerText?.trim() || '';

                    // Title: try known HCM selectors then fall back to first h1
                    const title = sel('[class*="requisition-title"]')
                        || sel('[class*="JobTitle"]')
                        || sel('.job-title')
                        || sel('h1');

                    // Company: page header logo alt text, meta, or site-name span
                    const companyMeta = document.querySelector('meta[property="og:site_name"]')
                        ?.getAttribute('content') || '';
                    const company = sel('[class*="company-name"]')
                        || sel('[class*="siteName"]')
                        || sel('[class*="site-name"]')
                        || companyMeta;

                    // Location: job detail list items
                    const location = sel('[class*="job-location"]')
                        || sel('[data-testid*="location"]')
                        || sel('[class*="location"]');

                    // Description: main content div
                    const description = selInner('[class*="job-description"]')
                        || selInner('[class*="requisition-description"]')
                        || selInner('[class*="JobDescription"]')
                        || selInner('main article')
                        || selInner('main');

                    return { title, company, location, description };
                }""")
            finally:
                browser.close()

        result["source"] = "oracle_hcm"
        return {k: v for k, v in result.items() if v}

    except Exception as exc:  # noqa: BLE001 -- same reasoning as _scrape_jobgether
        # above: Playwright browser automation over an unpredictable third-party React
        # SPA can raise many distinct playwright.sync_api errors, and this scraper must
        # degrade to an empty result rather than crash the enrichment task.
        print(f"[scrape_url] Oracle HCM Playwright error for {url}: {exc}")
        return {}


def _is_cloudflare_challenge(html: str) -> bool:
    """Detect Cloudflare's bot-challenge interstitial page.

    The Ladders is behind Cloudflare bot protection at the TLS/connection
    fingerprint level (confirmed 2026-09-23: plain Playwright automation gets
    a hard 403 even with standard stealth JS evasions applied, and waiting
    for the challenge to resolve does not help). This is a best-effort
    scraper — when challenged, we must fail clean rather than store the
    interstitial text as a job description. See peregrine#203.
    """
    return "Performing security verification" in html or "cf-error-details" in html


def _scrape_theladders(url: str) -> dict:
    """Scrape a The Ladders job detail page via Playwright.

    The Ladders is a client-side React app (no SSR content) — same reason
    the existing search-results scraper (scripts/custom_boards/theladders.py)
    uses Playwright. Job detail pages are additionally behind a Cloudflare
    bot challenge that this best-effort scraper cannot reliably bypass; when
    challenged, this returns {} rather than storing garbage.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("[scrape_url] The Ladders: Playwright not installed, skipping")
        return {}

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                ctx = browser.new_context(user_agent=_HEADERS["User-Agent"])
                page = ctx.new_page()
                page.goto(url, timeout=30_000)
                page.wait_for_load_state("networkidle", timeout=20_000)
                html = page.content()

                if _is_cloudflare_challenge(html):
                    print(f"[scrape_url] The Ladders: Cloudflare challenge for {url}, skipping")
                    return {}

                result = page.evaluate("""() => {
                    const title = document.querySelector('h1')?.textContent?.trim() || '';
                    const location = document.querySelector('.remote-location-text, .location-info')
                        ?.textContent?.trim() || '';
                    const desc = document.querySelector('[class*="description"], [class*="job-detail"], article')
                        ?.innerText?.trim() || '';
                    return { title, location, description: desc };
                }""")
            finally:
                browser.close()

        result["source"] = "theladders"
        return {k: v for k, v in result.items() if v}

    except Exception as exc:  # noqa: BLE001 -- same reasoning as _scrape_jobgether
        # above: Playwright browser automation over a Cloudflare-protected React
        # SPA can raise many distinct playwright.sync_api errors, and this
        # scraper must degrade to an empty result rather than crash the
        # enrichment task.
        print(f"[scrape_url] The Ladders Playwright error for {url}: {exc}")
        return {}


def _parse_json_ld_or_og(html: str) -> dict:
    """Extract job fields from JSON-LD structured data, then og: meta tags."""
    soup = BeautifulSoup(html, "html.parser")

    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
            if isinstance(data, list):
                data = next((d for d in data if d.get("@type") == "JobPosting"), {})
            if data.get("@type") == "JobPosting":
                org = data.get("hiringOrganization") or {}
                loc = data.get("jobLocation") or {}
                if isinstance(loc, list):
                    loc = loc[0] if loc else {}
                addr = loc.get("address") or {}
                location = (
                    addr.get("addressLocality", "") or
                    addr.get("addressRegion", "") or
                    addr.get("addressCountry", "")
                )
                return {k: v for k, v in {
                    "title": data.get("title", ""),
                    "company": org.get("name", ""),
                    "location": location,
                    "description": data.get("description", ""),
                    "salary": str(data.get("baseSalary", "")) if data.get("baseSalary") else "",
                }.items() if v}
        except Exception:  # noqa: BLE001, S112 -- iterating arbitrary third-party
            # JSON-LD `<script>` tags: `json.loads` can raise JSONDecodeError on
            # malformed JSON, and if the parsed value isn't a dict-shaped JobPosting
            # (a bare string/number/bool at the top level, or an unexpected nested
            # shape for hiringOrganization/jobLocation/address) the chained `.get()`
            # calls can raise AttributeError/TypeError — the exact shape of a random
            # site's JSON-LD isn't something we control. Skipping to the next script
            # tag (rather than logging every malformed tag) is the intended behavior;
            # a genuine JobPosting match still gets returned normally above.
            continue

    def _meta(prop):
        tag = soup.find("meta", property=prop) or soup.find("meta", attrs={"name": prop})
        return tag.get("content", "") if tag else ""

    title_tag = soup.find("title")
    title = _meta("og:title") or (title_tag.get_text(strip=True) if title_tag else "")
    description = _meta("og:description")
    return {k: v for k, v in {"title": title, "description": description}.items() if v}


def _scrape_generic(url: str) -> dict:
    resp = requests.get(url, headers=_HEADERS, timeout=_TIMEOUT)
    resp.raise_for_status()
    return _parse_json_ld_or_og(resp.text) or {}


def scrape_job_url(db_path: Path = DEFAULT_DB, job_id: int | None = None) -> dict:
    """
    Fetch the job listing at the stored URL and update the job record.

    Returns the dict of fields scraped (may be empty on failure).
    Does not raise — failures are logged and the job row is left as-is.
    """
    if job_id is None:
        return {}

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT url FROM jobs WHERE id=?", (job_id,)).fetchone()
    conn.close()
    if not row:
        return {}

    url = row["url"] or ""
    if not url.startswith("http"):
        return {}

    board = _detect_board(url)
    try:
        if board == "linkedin":
            fields = _scrape_linkedin(url)
        elif board == "indeed":
            fields = _scrape_indeed(url)
        elif board == "glassdoor":
            fields = _scrape_glassdoor(url)
        elif board == "jobgether":
            fields = _scrape_jobgether(url)
        elif board == "oracle_hcm":
            fields = _scrape_oracle_hcm(url)
        elif board == "theladders":
            fields = _scrape_theladders(url)
        else:
            fields = _scrape_generic(url)
    except requests.RequestException as exc:
        print(f"[scrape_url] HTTP error for job {job_id} ({url}): {exc}")
        return {}
    except Exception as exc:  # noqa: BLE001 -- this dispatches to one of five
        # board-specific scrapers (LinkedIn guest API, Indeed/generic JSON-LD+bs4
        # parsing, JobSpy's internal Glassdoor scraper, Playwright automation for
        # Jobgether/Oracle HCM), each with its own non-request failure surface
        # (parsing, DOM extraction, third-party library internals); per this
        # function's own docstring contract ("does not raise — failures are logged
        # and the job row is left as-is"), any of those must degrade to an empty
        # result rather than crash the background task.
        print(f"[scrape_url] Error scraping job {job_id} ({url}): {exc}")
        return {}

    if fields:
        fields.pop("url", None)
        update_job_fields(db_path, job_id, fields)
        print(f"[scrape_url] job {job_id}: scraped '{fields.get('title', '?')}' @ {fields.get('company', '?')}")

    return fields
