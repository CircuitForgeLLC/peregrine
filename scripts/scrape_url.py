# scripts/scrape_url.py
"""
Scrape a job listing from its URL and update the job record.

Supports:
  - LinkedIn   (guest jobs API — no auth required)
  - Indeed     (HTML parse)
  - Glassdoor  (JobSpy internal scraper, same as enrich_descriptions.py)
  - Greenhouse (public boards JSON API — the board pages are client-rendered)
  - Generic    (JSON-LD → og:tags fallback)

Usage (background task — called by task_runner):
    from scripts.scrape_url import scrape_job_url
    scrape_job_url(db_path, job_id)
"""
import html as html_lib
import json
import re
import sqlite3
import sys
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts import safe_net
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
    """Return 'linkedin', 'indeed', 'glassdoor', 'jobgether', 'oracle_hcm', 'theladders', 'greenhouse', or 'generic'."""
    # Match on the host only. Looking for a board's name anywhere in the URL let any other host be
    # routed to a board scraper (some of them drive a browser to the URL) just by putting that name
    # in its path or query (peregrine#250).
    host = (urlparse(url).hostname or "").lower()

    def on(domain: str) -> bool:
        return host == domain or host.endswith("." + domain)

    if on("linkedin.com"):
        return "linkedin"
    if on("indeed.com"):
        return "indeed"
    if on("glassdoor.com"):
        return "glassdoor"
    if on("jobgether.com"):
        return "jobgether"
    # Oracle HCM career sites live on <tenant>.fa.<region>.oraclecloud.com and serve under /hcmUI/.
    # Both are required: the "fa" label keeps other oraclecloud.com hosts (object storage, say) out
    # of the browser scraper, and the path must START with /hcmUI/, not merely contain it somewhere.
    if (
        on("oraclecloud.com")
        and "fa" in host.split(".")[1:-2]
        and (urlparse(url).path or "").lower().startswith("/hcmui/")
    ):
        return "oracle_hcm"
    if on("theladders.com"):
        return "theladders"
    if _parse_greenhouse_url(url):
        return "greenhouse"
    if _is_ultipro_job_url(url):
        return "ultipro"
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


def _parse_linkedin_posting(html: str) -> dict:
    """Parse the HTML of a LinkedIn guest jobs API posting. Empty fields are left out.

    Shared by the scraper below and the description backfill (scripts/linkedin_backfill.py)."""
    soup = BeautifulSoup(html, "html.parser")

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


def _scrape_linkedin(url: str) -> dict:
    """Fetch via LinkedIn guest jobs API (no auth required)."""
    job_id = _extract_linkedin_job_id(url)
    if not job_id:
        return {}
    api_url = f"https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{job_id}"
    resp = _fetch(api_url, headers=_HEADERS, timeout=_TIMEOUT)
    resp.raise_for_status()
    return _parse_linkedin_posting(resp.text)


def _scrape_indeed(url: str) -> dict:
    """Scrape an Indeed job page."""
    resp = _fetch(url, headers=_HEADERS, timeout=_TIMEOUT)
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
                _guard_browser_context(ctx)
                page = ctx.new_page()
                page.goto(url, timeout=30_000)
                page.wait_for_load_state("networkidle", timeout=20_000)

                if _page_left_public_web(page):
                    return {}
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
                _guard_browser_context(ctx)
                page = ctx.new_page()
                page.goto(url, timeout=30_000)
                page.wait_for_load_state("networkidle", timeout=20_000)

                if _page_left_public_web(page):
                    return {}
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

    The Ladders sits behind Cloudflare bot protection, but a masked,
    non-headless-looking User-Agent (see _HEADERS above) reliably gets
    through it — the earlier "hard TLS-fingerprint block" finding
    (peregrine#204) turned out to be an artifact of testing with a browser
    that sent a literal "HeadlessChrome" User-Agent, not a real block of
    this scraper's own request shape (confirmed 2026-09-23 against the real
    cf conda env's Playwright install, matching what this function uses).
    Kept as defensive best-effort handling in case Cloudflare's posture
    changes or challenges intermittently — never store interstitial text as
    a job description.
    """
    return "Performing security verification" in html or "cf-error-details" in html


def _scrape_theladders(url: str) -> dict:
    """Scrape a The Ladders job detail page via Playwright.

    The Ladders is a client-side React app (no SSR content) — same reason
    the existing search-results scraper (scripts/custom_boards/theladders.py)
    uses Playwright.
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
                _guard_browser_context(ctx)
                page = ctx.new_page()
                page.goto(url, timeout=30_000)
                # The Ladders keeps background network activity (analytics,
                # polling) alive indefinitely, so wait_for_load_state("networkidle")
                # never resolves even once the job content has fully rendered
                # (confirmed 2026-09-23: content is present well before any
                # networkidle timeout fires). Wait for the actual content
                # instead; a timeout here just means proceeding with whatever
                # has rendered so far, not a fatal error.
                try:
                    # Wait on the description selector specifically, not a broad
                    # OR including "article"/"h1" -- those bare tags exist in the
                    # page's layout shell before React populates them, so an OR
                    # wait can resolve on an empty shell and race ahead of the
                    # title actually being filled in (confirmed 2026-09-23: by
                    # the time the description-ish selector has real content,
                    # the title is reliably populated too).
                    page.wait_for_selector(
                        '[class*="description"], [class*="job-detail"]',
                        timeout=15_000,
                    )
                except Exception:  # noqa: BLE001, S110 -- a selector-wait timeout
                    # means proceeding to extraction with whatever rendered so far;
                    # the extraction JS below already degrades to empty strings per
                    # field when nothing matched, so this is not a fatal error.
                    pass
                # The title (<h1>) renders on a separate timeline from the
                # description and is not reliably present yet even once the
                # description selector resolves (confirmed 2026-09-23: h1 count
                # was 0 on some runs at that point) -- give it its own short,
                # non-fatal wait.
                try:
                    page.wait_for_selector("h1", timeout=5_000)
                except Exception:  # noqa: BLE001, S110 -- same reasoning as above:
                    # a missing title after this wait just means title comes back
                    # empty, not a fatal error for the whole scrape.
                    pass
                if _page_left_public_web(page):
                    return {}
                html = page.content()

                if _is_cloudflare_challenge(html):
                    print(f"[scrape_url] The Ladders: Cloudflare challenge for {url}, skipping")
                    return {}

                if _page_left_public_web(page):
                    return {}
                result = page.evaluate("""() => {
                    // The Ladders renders contraction apostrophes through a custom
                    // web font that maps a control/PUA codepoint (observed as the
                    // literal two-character sequence U+0003 U+0039) to an apostrophe
                    // glyph -- innerText/textContent extraction gets the raw
                    // codepoints, not the rendered glyph, so undo the substitution.
                    const fixApostrophes = (s) => s.replace(/\\u0003\\u0039/g, "'");
                    const title = fixApostrophes(document.querySelector('h1')?.textContent?.trim() || '');
                    const location = document.querySelector('.remote-location-text, .location-info')
                        ?.textContent?.trim() || '';
                    const desc = fixApostrophes(document.querySelector('[class*="description"], [class*="job-detail"], article')
                        ?.innerText?.trim() || '');
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


_GREENHOUSE_API = "https://boards-api.greenhouse.io/v1/boards/{board}/jobs/{job_id}"
_GREENHOUSE_PATH_RE = re.compile(r"^/(?P<board>[^/?#]+)/jobs/(?P<job_id>\d+)")


def _parse_greenhouse_url(url: str) -> tuple[str, str] | None:
    """Return (board, job_id) for a Greenhouse job URL, or None.

    Handles job-boards.greenhouse.io/<board>/jobs/<id>, boards.greenhouse.io/<board>/jobs/<id>
    (EU boards included) and the embed form boards.greenhouse.io/embed/job_app?for=<board>&token=<id>.
    A company page that only carries ?gh_jid=<id> has no board in the URL, so it is not matched.
    """
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    if host != "greenhouse.io" and not host.endswith(".greenhouse.io"):
        return None
    if parsed.path.startswith("/embed/job_app"):
        query = dict(parse_qsl(parsed.query))
        board, job_id = query.get("for", ""), query.get("token", "")
        return (board, job_id) if board and job_id.isdigit() else None
    match = _GREENHOUSE_PATH_RE.match(parsed.path)
    return (match["board"], match["job_id"]) if match else None


def _greenhouse_html_to_text(escaped_html: str) -> str:
    """The API's content field is HTML that has been HTML-escaped. Unescape it once, break lines at
    block elements, bullet the list items, and let the parser decode the entities left inside."""
    markup = html_lib.unescape(escaped_html)
    markup = re.sub(r"<li[^>]*>", "- ", markup, flags=re.IGNORECASE)
    markup = re.sub(r"</(p|div|h[1-6]|ul|ol|li|tr|table|section)>|<br\s*/?>", "\n", markup, flags=re.IGNORECASE)
    text = BeautifulSoup(markup, "html.parser").get_text()
    lines = [re.sub(r"[ \t ]+", " ", line).strip() for line in text.splitlines()]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def _format_greenhouse_pay(ranges: list | None) -> str:
    """Format published pay ranges, e.g. '$95,000 - $110,000 USD' or 'EUR 60,000 - 70,000'."""
    formatted = []
    for pay in ranges or []:
        low, high = pay.get("min_cents"), pay.get("max_cents")
        if low is None and high is None:
            continue
        currency = (pay.get("currency_type") or "").upper()
        low_amount = None if low is None else low / 100
        high_amount = None if high is None else high / 100
        amounts = [a for a in (low_amount, high_amount) if a is not None]
        if currency == "USD":
            span = " - ".join(f"${a:,.0f}" for a in dict.fromkeys(amounts))
            formatted.append(f"{span} USD")
        else:
            span = " - ".join(f"{a:,.0f}" for a in dict.fromkeys(amounts))
            formatted.append(f"{currency} {span}".strip())
    return " | ".join(formatted)


_ULTIPRO_PAYLOAD_RE = re.compile(r"CandidateOpportunityDetail\(\s*(\{.*?\})\s*\)\s*;", re.DOTALL)


def _is_ultipro_job_url(url: str) -> bool:
    """True for an UltiPro (UKG) job page: <host>.ultipro.com/<tenant>/JobBoard/<board>/OpportunityDetail.
    The host is matched as a suffix of the parsed hostname, so a lookalike such as
    ultipro.com.evil.example or the name in a query string does not count."""
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if host != "ultipro.com" and not host.endswith(".ultipro.com"):
        return False
    return bool(re.search(r"/JobBoard/[^/]+/OpportunityDetail/?$", parsed.path, re.IGNORECASE))


def _ultipro_html_to_text(markup: str) -> str:
    """Posting descriptions are plain HTML. Break lines at block elements and <br>, bullet list items."""
    markup = re.sub(r"<li[^>]*>", "- ", markup or "", flags=re.IGNORECASE)
    markup = re.sub(r"</(p|div|h[1-6]|ul|ol|li|tr|table|section)>|<br\s*/?>", "\n", markup, flags=re.IGNORECASE)
    text = BeautifulSoup(markup, "html.parser").get_text()
    lines = [re.sub(r"[ \t ]+", " ", line).strip() for line in text.splitlines()]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def _format_ultipro_pay(data: dict) -> str:
    """'$18.50 - $22.00 USD', only when the posting marks its pay range visible and fills it in."""
    pay = data.get("PayRange") or {}
    low, high = pay.get("PayRangeMinimum"), pay.get("PayRangeMaximum")
    if not data.get("PayRangeVisible") or (low is None and high is None):
        return ""
    currency = (data.get("PayRangeCurrencyCode") or "").upper()
    amounts = [a for a in (low, high) if a is not None]
    if currency == "USD":
        return " - ".join(f"${a:,.2f}" for a in dict.fromkeys(amounts)) + " USD"
    return f"{currency} " + " - ".join(f"{a:,.2f}" for a in dict.fromkeys(amounts))


def _scrape_ultipro(url: str) -> dict:
    """Read a posting from an UltiPro (UKG) job page (peregrine#253).

    The page has no JSON-LD, so the generic scraper only got a placeholder title. The whole posting is
    embedded in the HTML as JSON in a CandidateOpportunityDetail({...}) call, so no browser is needed.
    The employer's name is not in that payload: the company is the branch or location name the
    posting gives, which is what the page itself shows. A closed posting (404) or a page without a
    readable payload falls back to the generic scraper.
    """
    # _fetch, not requests.get: on the hosted version it goes through the guarded session
    # (peregrine#228), so a redirect or changed DNS answer cannot aim this at an internal address.
    resp = _fetch(url, headers=_HEADERS, timeout=_TIMEOUT)
    if resp.status_code == 404:
        return _scrape_generic(url)
    resp.raise_for_status()
    match = _ULTIPRO_PAYLOAD_RE.search(resp.text or "")
    try:
        data = json.loads(match.group(1)) if match else None
    except ValueError:
        data = None
    if not isinstance(data, dict) or not data.get("Title"):
        return _scrape_generic(url)

    location = (data.get("Locations") or [{}])[0] or {}
    address = location.get("Address") or {}
    state = (address.get("State") or {}).get("Code") or ""
    description = _ultipro_html_to_text(data.get("Description") or "")
    equal_opportunity = _ultipro_html_to_text(data.get("EqualOpportunityEmployerDescription") or "")
    if equal_opportunity:
        description = f"{description}\n\n{equal_opportunity}".strip()

    fields = {
        "title": data["Title"].strip(),
        "company": (location.get("LocalizedName") or "").strip(),
        "location": ", ".join(part for part in (address.get("City"), state) if part),
        "description": description,
        "salary": _format_ultipro_pay(data),
        "source": "ultipro",
    }
    return {key: value for key, value in fields.items() if value}


def _scrape_greenhouse(url: str) -> dict:
    """Fetch a posting from Greenhouse's public boards API.

    The board pages are client-rendered (no JobPosting JSON-LD, a placeholder <title>), so the
    generic scraper only ever got the title. The API returns everything. A 404 means the job is
    closed or unpublished, so fall back to whatever the page itself still shows.
    """
    parsed = _parse_greenhouse_url(url)
    if parsed is None:
        return _scrape_generic(url)
    board, job_id = parsed
    resp = _fetch(
        _GREENHOUSE_API.format(board=board, job_id=job_id),
        params={"pay_transparency": "true"},
        headers=_HEADERS,
        timeout=_TIMEOUT,
    )
    if resp.status_code == 404:
        return _scrape_generic(url)
    resp.raise_for_status()
    data = resp.json()

    location = ((data.get("location") or {}).get("name") or "").strip()
    fields = {
        "title": (data.get("title") or "").strip(),
        "company": (data.get("company_name") or "").strip(),
        "location": location,
        "description": _greenhouse_html_to_text(data.get("content") or ""),
        "salary": _format_greenhouse_pay(data.get("pay_input_ranges")),
        "source": "greenhouse",
    }
    fields = {key: value for key, value in fields.items() if value}
    if location:
        fields["is_remote"] = "remote" in location.lower()
    return fields


def _guard_browser_context(context) -> None:
    """On the hosted version, make the browser abort any request to a non-public address.

    The browser-driven scrapers (Jobgether, Oracle HCM, TheLadders) load a page that runs scripts,
    follows redirects and loads sub-resources on its own, so checking the first address is not
    enough: every request the page makes is vetted here before it leaves. Anything that is not
    http(s) is refused as well (file://, ftp://), except inline data:/blob: content, which makes no
    network request. The browser resolves names itself, so a name that changes its answer between
    this check and the browser's own lookup is a residual gap. It is narrowed by detecting these
    scrapers on the board's own host only, never on a host that merely mentions it.
    """
    if not safe_net.cloud_mode():
        return
    verdicts: dict = {}

    def allowed(url: str) -> bool:
        parsed = urlparse(url)
        key = (parsed.scheme, parsed.netloc.lower())
        if key not in verdicts:
            verdicts[key] = safe_net.public_url_error(url, ("http", "https")) is None
        return verdicts[key]

    def handle(route):
        request = route.request
        url = request.url
        if urlparse(url).scheme in ("data", "blob", "about"):
            route.continue_()
            return
        if not allowed(url):
            route.abort()
            return
        if request.is_navigation_request():
            # Chromium follows a redirect on its own and does not ask again for the next hop, so a
            # page on an allowed host could be redirected into an internal service. Fetch the
            # navigation without following redirects, vet where it points, and hand the browser
            # the response, which makes it request the next hop through this handler again.
            try:
                response = route.fetch(max_redirects=0)
            except Exception:  # noqa: BLE001 - any failure to fetch means the navigation is refused
                route.abort()
                return
            if 300 <= response.status < 400:
                location = response.headers.get("location")
                if not location or not allowed(urljoin(url, location)):
                    route.abort()
                    return
            route.fulfill(response=response)
            return
        route.continue_()

    context.route("**/*", handle)

    # WebSockets never reach the request handler above, so a script on the page could open one to
    # an internal address. Route them too, and close any that is not public before it connects.
    route_web_socket = getattr(context, "route_web_socket", None)
    if route_web_socket is None:
        raise RuntimeError("This Playwright version cannot restrict WebSockets, refusing to run the browser.")

    def handle_web_socket(web_socket):
        # wss:// -> https://, ws:// -> http://, so the same address check applies.
        as_http = re.sub(r"^ws(s?)://", r"http\1://", web_socket.url, count=1, flags=re.IGNORECASE)
        if allowed(as_http):
            web_socket.connect_to_server()
        # Otherwise do nothing. A routed WebSocket that never calls connect_to_server() is mocked:
        # the page sees a socket but nothing leaves the machine. Calling close() here would be
        # clearer but deadlocks Playwright's sync API inside a handler.

    route_web_socket("**/*", handle_web_socket)


def _page_left_public_web(page) -> bool:
    """True on the hosted version when the page the browser ended up on is not a public http(s) page.

    Checked before anything is read from the page, as a last line behind the request guard: if a
    redirect or a script managed to land the browser somewhere internal, nothing from that page
    is returned or stored."""
    return safe_net.cloud_mode() and safe_net.public_url_error(page.url, ("http", "https")) is not None


def _fetch(url: str, **kwargs):
    """GET an address a user supplied. On the hosted version it goes through the safe session, which
    cannot be aimed at the internal network (peregrine#250). Self-hosted installs fetch directly, so
    a job board on the local network keeps working."""
    if safe_net.cloud_mode():
        return safe_net.SafeSession().get(url, **kwargs)
    return requests.get(url, **kwargs)


def _scrape_generic(url: str) -> dict:
    resp = _fetch(url, headers=_HEADERS, timeout=_TIMEOUT)
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

    # Checked again here, not only when the link was added: a name can resolve somewhere else later,
    # and this is before any fetch or browser launch. The address is deliberately not logged.
    if safe_net.cloud_mode() and safe_net.public_url_error(url, ("http", "https")):
        print(f"[scrape_url] job {job_id}: refusing to fetch a non-public address")
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
        elif board == "greenhouse":
            fields = _scrape_greenhouse(url)
        elif board == "ultipro":
            fields = _scrape_ultipro(url)
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

    if not fields.get("description"):
        # One line per empty scrape: job id and board only, never the address or any page content.
        print(f"[scrape_url] job {job_id}: board '{board}' returned no description")

    if fields:
        fields.pop("url", None)
        update_job_fields(db_path, job_id, fields)
        print(f"[scrape_url] job {job_id}: scraped '{fields.get('title', '?')}' @ {fields.get('company', '?')}")

    return fields
