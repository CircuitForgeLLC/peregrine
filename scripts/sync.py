# scripts/sync.py
"""
Push approved jobs from SQLite staging to Notion.

Usage:
    conda run -n job-seeker python scripts/sync.py
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import yaml
from datetime import datetime

from notion_client import Client

from scripts.db import DEFAULT_DB, get_jobs_by_status, update_job_status

CONFIG_DIR = Path(__file__).parent.parent / "config"


def load_notion_config() -> dict:
    return yaml.safe_load((CONFIG_DIR / "notion.yaml").read_text())


def _build_properties(job: dict, fm: dict, include_optional: bool = True) -> dict:
    """Build the Notion properties dict for a job. Optional fields (match_score,
    keyword_gaps) are included by default but can be dropped for DBs that don't
    have those columns yet."""
    props = {
        fm["title_field"]: {"title": [{"text": {"content": job.get("salary") or job.get("title", "")}}]},
        fm["job_title"]:   {"rich_text": [{"text": {"content": job.get("title", "")}}]},
        fm["company"]:     {"rich_text": [{"text": {"content": job.get("company", "")}}]},
        fm["url"]:         {"url": job.get("url") or None},
        fm["source"]:      {"multi_select": [{"name": job.get("source", "unknown").title()}]},
        fm["status"]:      {"select": {"name": fm["status_new"]}},
        fm["remote"]:      {"checkbox": bool(job.get("is_remote", 0))},
        fm["date_found"]:  {"date": {"start": job.get("date_found", datetime.now().isoformat()[:10])}},
    }
    if include_optional:
        score = job.get("match_score")
        if score is not None and fm.get("match_score"):
            props[fm["match_score"]] = {"number": score}
        gaps = job.get("keyword_gaps")
        if gaps and fm.get("keyword_gaps"):
            props[fm["keyword_gaps"]] = {"rich_text": [{"text": {"content": gaps}}]}
    return props


def sync_to_notion(db_path: Path = DEFAULT_DB) -> int:
    """Push all approved and applied jobs to Notion. Returns count synced."""
    cfg = load_notion_config()
    notion = Client(auth=cfg["token"])
    db_id = cfg["database_id"]
    fm = cfg["field_map"]

    approved = get_jobs_by_status(db_path, "approved")
    applied = get_jobs_by_status(db_path, "applied")
    pending_sync = approved + applied
    if not pending_sync:
        print("[sync] No approved/applied jobs to sync.")
        return 0

    synced_ids = []
    for job in pending_sync:
        try:
            notion.pages.create(
                parent={"database_id": db_id},
                properties=_build_properties(job, fm, include_optional=True),
            )
            synced_ids.append(job["id"])
            print(f"[sync] + {job.get('title')} @ {job.get('company')}")
        except Exception as e:
            err = str(e)
            # Notion returns 400 validation_error when a property column doesn't exist yet.
            # Fall back to core fields only and warn the user.
            if "validation_error" in err or "Could not find property" in err:
                try:
                    notion.pages.create(
                        parent={"database_id": db_id},
                        properties=_build_properties(job, fm, include_optional=False),
                    )
                    synced_ids.append(job["id"])
                    print(f"[sync] + {job.get('title')} @ {job.get('company')} "
                          f"(skipped optional fields — add Match Score / Keyword Gaps columns to Notion DB)")
                except Exception as e2:
                    print(f"[sync] Error syncing {job.get('url')}: {e2}")
            else:
                print(f"[sync] Error syncing {job.get('url')}: {e}")

    update_job_status(db_path, synced_ids, "synced")
    print(f"[sync] Done — {len(synced_ids)} jobs synced to Notion.")
    return len(synced_ids)


if __name__ == "__main__":
    sync_to_notion()
