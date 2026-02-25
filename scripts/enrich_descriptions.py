# scripts/enrich_descriptions.py
"""
Post-discovery enrichment: retry Glassdoor job description fetches that
returned empty/null during the initial scrape (usually rate-limit 429s or
expired listings mid-batch).

Fetches descriptions one at a time with a configurable delay between
requests to stay under Glassdoor's rate limit.

Usage:
    conda run -n job-seeker python scripts/enrich_descriptions.py
    conda run -n job-seeker python scripts/enrich_descriptions.py --dry-run
    conda run -n job-seeker python scripts/enrich_descriptions.py --delay 2.0
"""
import re
import sqlite3
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.db import DEFAULT_DB, init_db

DELAY_SECS = 1.5  # seconds between description fetches


def _extract_job_id(url: str) -> str | None:
    """Pull the Glassdoor listing ID from a job URL (…?jl=1234567890)."""
    m = re.search(r"jl=(\d+)", url or "")
    return m.group(1) if m else None


def _setup_scraper():
    """
    Create a Glassdoor scraper instance initialised just enough to call
    _fetch_job_description() — skips the full job-search setup.
    """
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
    return scraper


def enrich_glassdoor_descriptions(
    db_path: Path = DEFAULT_DB,
    dry_run: bool = False,
    delay: float = DELAY_SECS,
) -> dict:
    """
    Find Glassdoor jobs with missing descriptions and re-fetch them.

    Returns:
        {"attempted": N, "succeeded": N, "failed": N, "errors": [...]}
    """
    init_db(db_path)

    conn = sqlite3.connect(db_path)
    rows = conn.execute(
        """SELECT id, url, company, title FROM jobs
           WHERE source = 'glassdoor'
             AND (description IS NULL OR TRIM(description) = '')
           ORDER BY id ASC"""
    ).fetchall()
    conn.close()

    result = {"attempted": len(rows), "succeeded": 0, "failed": 0, "errors": []}

    if not rows:
        print("[enrich] No Glassdoor jobs missing descriptions.")
        return result

    print(f"[enrich] {len(rows)} Glassdoor job(s) missing descriptions — fetching…")

    try:
        scraper = _setup_scraper()
    except Exception as e:
        msg = f"Glassdoor scraper init failed: {e}"
        result["errors"].append(msg)
        result["failed"] = len(rows)
        print(f"[enrich] ERROR — {msg}")
        return result

    for db_id, url, company, title in rows:
        job_id = _extract_job_id(url)
        if not job_id:
            msg = f"job #{db_id}: cannot extract listing ID from URL: {url}"
            result["errors"].append(msg)
            result["failed"] += 1
            print(f"[enrich] SKIP — {msg}")
            continue

        try:
            description = scraper._fetch_job_description(int(job_id))
            if description and description.strip():
                if not dry_run:
                    upd = sqlite3.connect(db_path)
                    upd.execute(
                        "UPDATE jobs SET description = ? WHERE id = ?",
                        (description, db_id),
                    )
                    upd.commit()
                    upd.close()
                tag = "[DRY-RUN] " if dry_run else ""
                print(f"[enrich] {tag}{company} — {title}: {len(description)} chars")
                result["succeeded"] += 1
            else:
                print(f"[enrich] {company} — {title}: empty response (expired listing?)")
                result["failed"] += 1
        except Exception as e:
            msg = f"job #{db_id} ({company}): {e}"
            result["errors"].append(msg)
            result["failed"] += 1
            print(f"[enrich] ERROR — {msg}")

        if delay > 0:
            time.sleep(delay)

    return result


def enrich_all_descriptions(
    db_path: Path = DEFAULT_DB,
    dry_run: bool = False,
    delay: float = DELAY_SECS,
) -> dict:
    """
    Find ALL jobs with missing/empty descriptions (any source) and re-fetch them.

    Uses scrape_job_url for every source — it handles LinkedIn, Indeed, Glassdoor,
    Adzuna, The Ladders, and any generic URL via JSON-LD / og: tags.

    Returns:
        {"attempted": N, "succeeded": N, "failed": N, "errors": [...]}
    """
    from scripts.scrape_url import scrape_job_url

    init_db(db_path)

    conn = sqlite3.connect(db_path)
    rows = conn.execute(
        """SELECT id, url, company, title, source FROM jobs
           WHERE (description IS NULL OR TRIM(description) = '')
             AND url IS NOT NULL AND url != ''
           ORDER BY source, id ASC"""
    ).fetchall()
    conn.close()

    result = {"attempted": len(rows), "succeeded": 0, "failed": 0, "errors": []}

    if not rows:
        print("[enrich] No jobs with missing descriptions.")
        return result

    print(f"[enrich] {len(rows)} job(s) missing descriptions — fetching…")

    for db_id, url, company, title, source in rows:
        if not url.startswith("http"):
            result["failed"] += 1
            continue

        tag = "[DRY-RUN] " if dry_run else ""
        try:
            fields = {} if dry_run else scrape_job_url(db_path, db_id)
            if fields or dry_run:
                desc_len = len(fields.get("description", "") or "")
                print(f"[enrich] {tag}[{source}] {company} — {title}: {desc_len} chars")
                result["succeeded"] += 1
            else:
                print(f"[enrich] [{source}] {company} — {title}: no data returned")
                result["failed"] += 1
        except Exception as e:
            msg = f"job #{db_id} ({company}): {e}"
            result["errors"].append(msg)
            result["failed"] += 1
            print(f"[enrich] ERROR — {msg}")

        if delay > 0:
            time.sleep(delay)

    return result


def enrich_craigslist_fields(
    db_path: Path = DEFAULT_DB,
    job_id: int = None,
) -> dict:
    """
    Use LLM to extract company name and salary from a Craigslist job description.

    Called after scrape_url populates the description for a craigslist job.
    Only runs when: source='craigslist', company='', description non-empty.

    Returns dict with keys 'company' and/or 'salary' (may be empty strings).
    """
    import json

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT id, description, company, source FROM jobs WHERE id=?", (job_id,)
    ).fetchone()
    conn.close()

    if not row:
        return {}
    if row["source"] != "craigslist":
        return {}
    if row["company"]:  # already populated
        return {}
    if not (row["description"] or "").strip():
        return {}

    from scripts.llm_router import LLMRouter

    prompt = (
        "Extract the following from this job posting. "
        "Return JSON only, no commentary.\n\n"
        '{"company": "<company name or empty string>", '
        '"salary": "<salary/compensation or empty string>"}\n\n'
        f"Posting:\n{row['description'][:3000]}"
    )

    try:
        router = LLMRouter()
        raw = router.complete(prompt)
    except Exception as exc:
        print(f"[enrich_craigslist] LLM error for job {job_id}: {exc}")
        return {}

    try:
        clean = re.sub(r"```(?:json)?|```", "", raw).strip()
        fields = json.loads(clean)
    except (json.JSONDecodeError, ValueError):
        print(f"[enrich_craigslist] Could not parse LLM response for job {job_id}: {raw!r}")
        return {}

    extracted = {
        k: (fields.get(k) or "").strip()
        for k in ("company", "salary")
        if (fields.get(k) or "").strip()
    }

    if extracted:
        from scripts.db import update_job_fields
        update_job_fields(db_path, job_id, extracted)
        print(f"[enrich_craigslist] job {job_id}: "
              f"company={extracted.get('company', '—')} "
              f"salary={extracted.get('salary', '—')}")

    return extracted


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Re-fetch missing job descriptions (all sources)"
    )
    parser.add_argument("--glassdoor-only", action="store_true",
                        help="Only re-fetch Glassdoor listings (legacy behaviour)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would be fetched without saving")
    parser.add_argument("--delay", type=float, default=DELAY_SECS,
                        help=f"Seconds between requests (default: {DELAY_SECS})")
    args = parser.parse_args()

    if args.glassdoor_only:
        r = enrich_glassdoor_descriptions(dry_run=args.dry_run, delay=args.delay)
    else:
        r = enrich_all_descriptions(dry_run=args.dry_run, delay=args.delay)

    print(
        f"\n[enrich] Done — {r['succeeded']} fetched, {r['failed']} failed"
        + (f", {len(r['errors'])} error(s)" if r["errors"] else "")
    )
