"""We Work Remotely job board scraper — public RSS feed, no auth required.

Feed: https://weworkremotely.com/remote-jobs.rss
Item titles are formatted "Company: Job Title" — split on the first ": ".

Remote-only board — the `location` parameter is accepted for interface
compatibility but ignored (WWR has no location-scoped feed).

Returns a list of dicts compatible with scripts.db.insert_job().
"""
from __future__ import annotations

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import defusedxml.ElementTree as ET
import requests

_RSS_URL = "https://weworkremotely.com/remote-jobs.rss"
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; PeregrineBot/1.0; +https://circuitforge.tech)",
}
_TIMEOUT = 15


def _parse_pubdate(pubdate_str: str) -> datetime | None:
    """Parse an RSS pubDate string to a timezone-aware datetime."""
    try:
        return parsedate_to_datetime(pubdate_str)
    except Exception:
        return None


def _split_title(raw_title: str) -> tuple[str, str]:
    """Split WWR's "Company: Job Title" format into (company, title)."""
    if ": " in raw_title:
        company, title = raw_title.split(": ", 1)
        return company.strip(), title.strip()
    return "", raw_title.strip()


def _matches_title(job_title: str, titles: list[str]) -> bool:
    if not titles:
        return True
    title_lower = job_title.lower()
    return any(t.lower() in title_lower for t in titles)


def _fetch_rss() -> list[dict]:
    """Fetch and parse the WWR RSS feed. Returns list of raw item dicts."""
    resp = requests.get(_RSS_URL, headers=_HEADERS, timeout=_TIMEOUT)
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
            "region":      _text("region"),
        })
    return items


def scrape(profile: dict, location: str, results_wanted: int = 50) -> list[dict]:
    """Fetch jobs from the WeWorkRemotely RSS feed, filtered by the profile's titles.

    WWR has no search endpoint — it publishes its full current listing feed,
    so filtering by title and recency happens client-side.

    Args:
        profile: Search profile dict from search_profiles.yaml.
        location: Ignored — WeWorkRemotely is remote-only.
        results_wanted: Maximum results to return.

    Returns:
        List of job dicts with keys: title, company, url, source, location,
        is_remote, salary, description.
        salary is empty — not present in the RSS feed.
    """
    titles: list[str] = profile.get("titles") or profile.get("job_titles", [])
    hours_old: int = profile.get("hours_old", 240)
    cutoff = datetime.now(tz=timezone.utc).timestamp() - (hours_old * 3600)

    try:
        items = _fetch_rss()
    except (requests.RequestException, ValueError) as exc:
        print(f"    [weworkremotely] Request error: {exc}")
        return []

    seen_urls: set[str] = set()
    results: list[dict] = []

    for item in items:
        if len(results) >= results_wanted:
            break

        raw_title = item.get("title", "")
        link = item.get("link", "")
        if not raw_title or not link or link in seen_urls:
            continue

        company, title = _split_title(raw_title)
        if not _matches_title(title, titles):
            continue

        pubdate = _parse_pubdate(item.get("pubDate", ""))
        if pubdate is not None and pubdate.timestamp() < cutoff:
            continue

        seen_urls.add(link)
        results.append({
            "title":       title,
            "company":     company,
            "url":         link,
            "source":      "weworkremotely",
            "location":    item.get("region") or "Remote",
            "is_remote":   True,
            "salary":      "",
            "description": item.get("description", ""),
        })

    return results[:results_wanted]
