"""Adzuna Jobs API scraper.

API docs: https://developer.adzuna.com/docs/search
Config:   config/adzuna.yaml  (gitignored — contains app_id + app_key)

Each title in the search profile is queried as an exact phrase per location.
Returns a list of dicts compatible with scripts.db.insert_job().
"""
from __future__ import annotations

import time
from pathlib import Path

import requests
import yaml

_CONFIG_PATH = Path(__file__).parent.parent.parent / "config" / "adzuna.yaml"
_BASE_URL = "https://api.adzuna.com/v1/api/jobs/us/search"


def _load_config() -> tuple[str, str]:
    if not _CONFIG_PATH.exists():
        raise FileNotFoundError(
            f"Adzuna config not found: {_CONFIG_PATH}\n"
            "Copy config/adzuna.yaml.example → config/adzuna.yaml and fill in credentials."
        )
    cfg = yaml.safe_load(_CONFIG_PATH.read_text())
    app_id = (cfg.get("app_id") or "").strip()
    app_key = (cfg.get("app_key") or "").strip()
    if not app_id or not app_key:
        raise ValueError(
            "config/adzuna.yaml requires both 'app_id' and 'app_key'.\n"
            "Find your App ID at https://developer.adzuna.com/admin/applications"
        )
    return app_id, app_key


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


def _is_remote(location_display: str) -> bool:
    return "remote" in location_display.lower()


def scrape(profile: dict, location: str, results_wanted: int = 50) -> list[dict]:
    """Fetch jobs from the Adzuna API for a single location.

    Args:
        profile: Search profile dict from search_profiles.yaml.
        location: Location string (e.g. "Remote" or "San Francisco Bay Area, CA").
        results_wanted: Maximum results to return across all titles.

    Returns:
        List of job dicts with keys: title, company, url, source, location,
        is_remote, salary, description.
    """
    try:
        app_id, app_key = _load_config()
    except (FileNotFoundError, ValueError) as exc:
        print(f"    [adzuna] Skipped — {exc}")
        return []

    titles = profile.get("titles") or profile.get("job_titles", [])
    hours_old = profile.get("hours_old", 240)
    max_days_old = max(1, hours_old // 24)
    is_remote_search = location.lower() == "remote"

    session = requests.Session()
    session.headers.update({"Accept": "application/json", "User-Agent": "Mozilla/5.0"})

    seen_ids: set[str] = set()
    results: list[dict] = []

    for title in titles:
        if len(results) >= results_wanted:
            break

        page = 1
        while len(results) < results_wanted:
            # Adzuna doesn't support where=remote — it treats it as a city name and
            # returns 0 results. For remote searches, append "remote" to the what param.
            if is_remote_search:
                params = {
                    "app_id": app_id,
                    "app_key": app_key,
                    "results_per_page": 50,
                    "what": f'"{title}" remote',
                    "sort_by": "date",
                    "max_days_old": max_days_old,
                }
            else:
                params = {
                    "app_id": app_id,
                    "app_key": app_key,
                    "results_per_page": 50,
                    "what_phrase": title,
                    "where": location,
                    "sort_by": "date",
                    "max_days_old": max_days_old,
                }
            try:
                resp = session.get(f"{_BASE_URL}/{page}", params=params, timeout=20)
            except requests.RequestException as exc:
                print(f"    [adzuna] Request error ({title}): {exc}")
                break

            if resp.status_code == 401:
                print("    [adzuna] Auth failed — check app_id and app_key in config/adzuna.yaml")
                return results
            if resp.status_code != 200:
                print(f"    [adzuna] HTTP {resp.status_code} for '{title}' page {page}")
                break

            data = resp.json()
            jobs = data.get("results", [])
            if not jobs:
                break

            for job in jobs:
                job_id = str(job.get("id", ""))
                if job_id in seen_ids:
                    continue
                seen_ids.add(job_id)

                loc_display = job.get("location", {}).get("display_name", "")
                redirect_url = job.get("redirect_url", "")
                if not redirect_url:
                    continue

                results.append({
                    "title":       job.get("title", ""),
                    "company":     job.get("company", {}).get("display_name", ""),
                    "url":         redirect_url,
                    "source":      "adzuna",
                    "location":    loc_display,
                    "is_remote":   is_remote_search or _is_remote(loc_display),
                    "salary":      _salary_str(job),
                    "description": job.get("description", ""),
                })

            total = data.get("count", 0)
            if len(results) >= total or len(jobs) < 50:
                break  # last page

            page += 1
            time.sleep(0.5)  # polite pacing between pages

        time.sleep(0.5)  # between titles

    return results[:results_wanted]
