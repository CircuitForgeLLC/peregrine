# scripts/discover.py
"""
JobSpy → SQLite staging pipeline (default) or Notion (notion_push=True).

Usage:
    conda run -n job-seeker python scripts/discover.py
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import yaml
from datetime import datetime

import pandas as pd
from jobspy import scrape_jobs
from notion_client import Client

from scripts.db import DEFAULT_DB, init_db, insert_job, get_existing_urls as db_existing_urls
from scripts.custom_boards import adzuna as _adzuna
from scripts.custom_boards import theladders as _theladders
from scripts.custom_boards import craigslist as _craigslist

CONFIG_DIR = Path(__file__).parent.parent / "config"
NOTION_CFG = CONFIG_DIR / "notion.yaml"
PROFILES_CFG = CONFIG_DIR / "search_profiles.yaml"
BLOCKLIST_CFG = CONFIG_DIR / "blocklist.yaml"

# Registry of custom board scrapers keyed by name used in search_profiles.yaml
CUSTOM_SCRAPERS: dict[str, object] = {
    "adzuna": _adzuna.scrape,
    "theladders": _theladders.scrape,
    "craigslist": _craigslist.scrape,
}


def load_config() -> tuple[dict, dict]:
    profiles = yaml.safe_load(PROFILES_CFG.read_text())
    notion_cfg = yaml.safe_load(NOTION_CFG.read_text())
    return profiles, notion_cfg


def load_blocklist() -> dict:
    """Load global blocklist config. Returns dict with companies, industries, locations lists."""
    if not BLOCKLIST_CFG.exists():
        return {"companies": [], "industries": [], "locations": []}
    raw = yaml.safe_load(BLOCKLIST_CFG.read_text()) or {}
    return {
        "companies":  [c.lower() for c in raw.get("companies", []) if c],
        "industries": [i.lower() for i in raw.get("industries", []) if i],
        "locations":  [loc.lower() for loc in raw.get("locations", []) if loc],
    }


def _is_blocklisted(job_row: dict, blocklist: dict) -> bool:
    """Return True if this job matches any global blocklist rule."""
    company_lower = (job_row.get("company") or "").lower()
    location_lower = (job_row.get("location") or "").lower()
    desc_lower = (job_row.get("description") or "").lower()
    content_lower = f"{company_lower} {desc_lower}"

    if any(bl in company_lower for bl in blocklist["companies"]):
        return True
    if any(bl in content_lower for bl in blocklist["industries"]):
        return True
    if any(bl in location_lower for bl in blocklist["locations"]):
        return True
    return False


def get_existing_urls(notion: Client, db_id: str, url_field: str) -> set[str]:
    """Return the set of all job URLs already tracked in Notion (for notion_push mode)."""
    existing: set[str] = set()
    has_more = True
    start_cursor = None
    while has_more:
        kwargs: dict = {"database_id": db_id, "page_size": 100}
        if start_cursor:
            kwargs["start_cursor"] = start_cursor
        resp = notion.databases.query(**kwargs)
        for page in resp["results"]:
            url = page["properties"].get(url_field, {}).get("url")
            if url:
                existing.add(url)
        has_more = resp.get("has_more", False)
        start_cursor = resp.get("next_cursor")
    return existing


def push_to_notion(notion: Client, db_id: str, job: dict, fm: dict) -> None:
    """Create a new page in the Notion jobs database for a single listing."""
    min_amt = job.get("min_amount")
    max_amt = job.get("max_amount")
    if min_amt and max_amt and not (pd.isna(min_amt) or pd.isna(max_amt)):
        title_content = f"${int(min_amt):,} – ${int(max_amt):,}"
    elif job.get("salary_source") and str(job["salary_source"]) not in ("nan", "None", ""):
        title_content = str(job["salary_source"])
    else:
        title_content = str(job.get("title", "Unknown"))

    job_url = str(job.get("job_url", "") or "")
    if job_url in ("nan", "None"):
        job_url = ""

    notion.pages.create(
        parent={"database_id": db_id},
        properties={
            fm["title_field"]: {"title": [{"text": {"content": title_content}}]},
            fm["job_title"]:   {"rich_text": [{"text": {"content": str(job.get("title", "Unknown"))}}]},
            fm["company"]:     {"rich_text": [{"text": {"content": str(job.get("company", "") or "")}}]},
            fm["url"]:         {"url": job_url or None},
            fm["source"]:      {"multi_select": [{"name": str(job.get("site", "unknown")).title()}]},
            fm["status"]:      {"select": {"name": fm["status_new"]}},
            fm["remote"]:      {"checkbox": bool(job.get("is_remote", False))},
            fm["date_found"]:  {"date": {"start": datetime.now().isoformat()[:10]}},
        },
    )


def run_discovery(db_path: Path = DEFAULT_DB, notion_push: bool = False) -> None:
    profiles_cfg, notion_cfg = load_config()
    fm = notion_cfg["field_map"]
    blocklist = load_blocklist()

    _bl_summary = {k: len(v) for k, v in blocklist.items() if v}
    if _bl_summary:
        print(f"[discover] Blocklist active: {_bl_summary}")

    # SQLite dedup — by URL and by (title, company) to catch cross-board reposts
    init_db(db_path)
    existing_urls = db_existing_urls(db_path)

    import sqlite3 as _sqlite3
    _conn = _sqlite3.connect(db_path)
    existing_tc = {
        (r[0].lower().strip()[:80], r[1].lower().strip())
        for r in _conn.execute("SELECT title, company FROM jobs").fetchall()
    }
    _conn.close()

    # Notion dedup (only in notion_push mode)
    notion = None
    if notion_push:
        notion = Client(auth=notion_cfg["token"])
        existing_urls |= get_existing_urls(notion, notion_cfg["database_id"], fm["url"])

    print(f"[discover] {len(existing_urls)} existing listings in DB")
    new_count = 0

    def _s(val, default="") -> str:
        """Convert a value to str, treating pandas NaN/None as default."""
        if val is None:
            return default
        s = str(val)
        return default if s in ("nan", "None", "NaN") else s

    def _insert_if_new(job_row: dict, source_label: str) -> bool:
        """Dedup-check, blocklist-check, and insert a job dict. Returns True if inserted."""
        url = job_row.get("url", "")
        if not url or url in existing_urls:
            return False

        # Global blocklist — checked before anything else
        if _is_blocklisted(job_row, blocklist):
            return False

        title_lower = job_row.get("title", "").lower()
        desc_lower  = job_row.get("description", "").lower()
        exclude_kw  = job_row.get("_exclude_kw", [])
        if any(kw in title_lower or kw in desc_lower for kw in exclude_kw):
            return False

        tc_key = (title_lower[:80], job_row.get("company", "").lower().strip())
        if tc_key in existing_tc:
            return False
        existing_tc.add(tc_key)

        insert_job(db_path, {
            "title":       job_row.get("title", ""),
            "company":     job_row.get("company", ""),
            "url":         url,
            "source":      job_row.get("source", source_label),
            "location":    job_row.get("location", ""),
            "is_remote":   bool(job_row.get("is_remote", False)),
            "salary":      job_row.get("salary", ""),
            "description": job_row.get("description", ""),
            "date_found":  datetime.now().isoformat()[:10],
        })
        existing_urls.add(url)
        return True

    for profile in profiles_cfg["profiles"]:
        print(f"\n[discover] ── Profile: {profile['name']} ──")
        boards = profile.get("boards", [])
        custom_boards = profile.get("custom_boards", [])
        exclude_kw = [kw.lower() for kw in profile.get("exclude_keywords", [])]
        results_per_board = profile.get("results_per_board", 25)

        for location in profile["locations"]:

            # ── JobSpy boards ──────────────────────────────────────────────────
            if boards:
                print(f"  [jobspy] {location} — boards: {', '.join(boards)}")
                try:
                    jobs: pd.DataFrame = scrape_jobs(
                        site_name=boards,
                        search_term=" OR ".join(f'"{t}"' for t in profile["titles"]),
                        location=location,
                        results_wanted=results_per_board,
                        hours_old=profile.get("hours_old", 72),
                        linkedin_fetch_description=True,
                    )
                    print(f"  [jobspy] {len(jobs)} raw results")
                except Exception as exc:
                    print(f"  [jobspy] ERROR: {exc}")
                    jobs = pd.DataFrame()

                jobspy_new = 0
                for _, job in jobs.iterrows():
                    url = str(job.get("job_url", "") or "")
                    if not url or url in ("nan", "None"):
                        continue

                    job_dict = job.to_dict()

                    # Build salary string from JobSpy numeric fields
                    min_amt = job_dict.get("min_amount")
                    max_amt = job_dict.get("max_amount")
                    salary_str = ""
                    if min_amt and max_amt and not (pd.isna(min_amt) or pd.isna(max_amt)):
                        salary_str = f"${int(min_amt):,} – ${int(max_amt):,}"
                    elif job_dict.get("salary_source") and str(job_dict["salary_source"]) not in ("nan", "None", ""):
                        salary_str = str(job_dict["salary_source"])

                    row = {
                        "url":         url,
                        "title":       _s(job_dict.get("title")),
                        "company":     _s(job_dict.get("company")),
                        "source":      _s(job_dict.get("site")),
                        "location":    _s(job_dict.get("location")),
                        "is_remote":   bool(job_dict.get("is_remote", False)),
                        "salary":      salary_str,
                        "description": _s(job_dict.get("description")),
                        "_exclude_kw": exclude_kw,
                    }
                    if _insert_if_new(row, _s(job_dict.get("site"))):
                        if notion_push:
                            push_to_notion(notion, notion_cfg["database_id"], job_dict, fm)
                        new_count += 1
                        jobspy_new += 1
                        print(f"    + {row['title']} @ {row['company']} [{row['source']}]")

                print(f"  [jobspy] {jobspy_new} new listings from {location}")

            # ── Custom boards ──────────────────────────────────────────────────
            for board_name in custom_boards:
                scraper_fn = CUSTOM_SCRAPERS.get(board_name)
                if scraper_fn is None:
                    print(f"  [{board_name}] Unknown scraper — skipping (not in CUSTOM_SCRAPERS registry)")
                    continue

                print(f"  [{board_name}] {location} — fetching up to {results_per_board} results …")
                try:
                    custom_jobs = scraper_fn(profile, location, results_wanted=results_per_board)
                except Exception as exc:
                    print(f"  [{board_name}] ERROR: {exc}")
                    custom_jobs = []

                print(f"  [{board_name}] {len(custom_jobs)} raw results")
                board_new = 0
                for job in custom_jobs:
                    row = {**job, "_exclude_kw": exclude_kw}
                    if _insert_if_new(row, board_name):
                        new_count += 1
                        board_new += 1
                        print(f"    + {job.get('title')} @ {job.get('company')} [{board_name}]")

                print(f"  [{board_name}] {board_new} new listings from {location}")

    print(f"\n[discover] Done — {new_count} new listings staged total.")
    return new_count


if __name__ == "__main__":
    run_discovery()
