"""RemoteOK job board scraper — public JSON API, no auth required.

API docs: https://remoteok.com/api  (undocumented but stable; widely used)
Response is a JSON array; element 0 is feed metadata (`legal`, `last_updated`),
the rest are job postings.

Remote-only board — the `location` parameter is accepted for interface
compatibility but ignored (matches the pattern noted for WeWorkRemotely).

Returns a list of dicts compatible with scripts.db.insert_job().
"""
from __future__ import annotations

import time

import requests

_API_URL = "https://remoteok.com/api"
_HEADERS = {
    "Accept": "application/json",
    # RemoteOK rejects requests with no/blank User-Agent.
    "User-Agent": "Mozilla/5.0 (compatible; PeregrineBot/1.0; +https://circuitforge.tech)",
}
_TIMEOUT = 15


def _salary_str(job: dict) -> str:
    lo = job.get("salary_min")
    hi = job.get("salary_max")
    try:
        if lo and hi:
            return f"${int(lo):,} – ${int(hi):,}"
        if lo:
            return f"${int(lo):,}+"
    except (TypeError, ValueError):
        pass
    return ""


def _matches_title(job_position: str, titles: list[str]) -> bool:
    if not titles:
        return True
    position_lower = job_position.lower()
    return any(t.lower() in position_lower for t in titles)


def scrape(profile: dict, location: str, results_wanted: int = 50) -> list[dict]:
    """Fetch jobs from the RemoteOK API, filtered by the profile's titles.

    RemoteOK has no search endpoint — it returns its full current listing
    feed, so filtering by title and recency happens client-side.

    Args:
        profile: Search profile dict from search_profiles.yaml.
        location: Ignored — RemoteOK is remote-only.
        results_wanted: Maximum results to return.

    Returns:
        List of job dicts with keys: title, company, url, source, location,
        is_remote, salary, description.
    """
    titles: list[str] = profile.get("titles") or profile.get("job_titles", [])
    hours_old: int = profile.get("hours_old", 240)
    cutoff_epoch = time.time() - (hours_old * 3600)

    try:
        resp = requests.get(_API_URL, headers=_HEADERS, timeout=_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
    except (requests.RequestException, ValueError) as exc:
        print(f"    [remoteok] Request error: {exc}")
        return []

    if not isinstance(data, list) or len(data) < 2:
        print("    [remoteok] Unexpected response shape — skipping")
        return []

    results: list[dict] = []
    # data[0] is feed metadata (legal/last_updated), not a job.
    for job in data[1:]:
        if len(results) >= results_wanted:
            break
        if not isinstance(job, dict):
            continue

        position = job.get("position", "")
        if not position or not _matches_title(position, titles):
            continue

        epoch = job.get("epoch")
        if epoch is not None and epoch < cutoff_epoch:
            continue

        url = job.get("url") or job.get("apply_url") or ""
        if not url:
            continue

        results.append({
            "title":       position,
            "company":     job.get("company", ""),
            "url":         url,
            "source":      "remoteok",
            "location":    job.get("location") or "Remote",
            "is_remote":   True,
            "salary":      _salary_str(job),
            "description": job.get("description", ""),
        })

    return results[:results_wanted]
