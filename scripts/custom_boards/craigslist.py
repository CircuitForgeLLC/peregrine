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

    titles: list[str] = profile.get("titles") or profile.get("job_titles", [])
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
