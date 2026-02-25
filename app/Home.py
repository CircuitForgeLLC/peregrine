# app/Home.py
"""
Job Seeker Dashboard — Home page.
Shows counts, Run Discovery button, and Sync to Notion button.
"""
import subprocess
import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.db import DEFAULT_DB, init_db, get_job_counts, purge_jobs, purge_email_data, \
    purge_non_remote, archive_jobs, kill_stuck_tasks, get_task_for_job, get_active_tasks, \
    insert_job, get_existing_urls
from scripts.task_runner import submit_task

init_db(DEFAULT_DB)


def _dismissible(key: str, status: str, msg: str) -> None:
    """Render a dismissible success/error message. key must be unique per task result."""
    if st.session_state.get(f"dismissed_{key}"):
        return
    col_msg, col_x = st.columns([10, 1])
    with col_msg:
        if status == "completed":
            st.success(msg)
        else:
            st.error(msg)
    with col_x:
        st.write("")
        if st.button("✕", key=f"dismiss_{key}", help="Dismiss"):
            st.session_state[f"dismissed_{key}"] = True
            st.rerun()


def _queue_url_imports(db_path: Path, urls: list) -> int:
    """Insert each URL as a pending manual job and queue a scrape_url task.
    Returns count of newly queued jobs."""
    from datetime import datetime
    from scripts.scrape_url import canonicalize_url
    existing = get_existing_urls(db_path)
    queued = 0
    for url in urls:
        url = canonicalize_url(url.strip())
        if not url.startswith("http"):
            continue
        if url in existing:
            continue
        job_id = insert_job(db_path, {
            "title": "Importing…",
            "company": "",
            "url": url,
            "source": "manual",
            "location": "",
            "description": "",
            "date_found": datetime.now().isoformat()[:10],
        })
        if job_id:
            submit_task(db_path, "scrape_url", job_id)
            queued += 1
    return queued


st.title("🔍 Alex's Job Search")
st.caption("Discover → Review → Sync to Notion")

st.divider()


@st.fragment(run_every=10)
def _live_counts():
    counts = get_job_counts(DEFAULT_DB)
    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Pending Review", counts.get("pending", 0))
    col2.metric("Approved", counts.get("approved", 0))
    col3.metric("Applied", counts.get("applied", 0))
    col4.metric("Synced to Notion", counts.get("synced", 0))
    col5.metric("Rejected", counts.get("rejected", 0))


_live_counts()

st.divider()

left, enrich_col, mid, right = st.columns(4)

with left:
    st.subheader("Find New Jobs")
    st.caption("Scrapes all configured boards and adds new listings to your review queue.")

    _disc_task = get_task_for_job(DEFAULT_DB, "discovery", 0)
    _disc_running = _disc_task and _disc_task["status"] in ("queued", "running")

    if st.button("🚀 Run Discovery", use_container_width=True, type="primary",
                 disabled=bool(_disc_running)):
        submit_task(DEFAULT_DB, "discovery", 0)
        st.rerun()

    if _disc_running:
        @st.fragment(run_every=4)
        def _disc_status():
            t = get_task_for_job(DEFAULT_DB, "discovery", 0)
            if t and t["status"] in ("queued", "running"):
                lbl = "Queued…" if t["status"] == "queued" else "Scraping job boards… this may take a minute"
                st.info(f"⏳ {lbl}")
            else:
                st.rerun()
        _disc_status()
    elif _disc_task and _disc_task["status"] == "completed":
        _dismissible(f"disc_{_disc_task['id']}", "completed",
                     f"✅ Discovery complete — {_disc_task.get('error', '')}. Head to Job Review.")
    elif _disc_task and _disc_task["status"] == "failed":
        _dismissible(f"disc_{_disc_task['id']}", "failed",
                     f"Discovery failed: {_disc_task.get('error', '')}")

with enrich_col:
    st.subheader("Enrich Descriptions")
    st.caption("Re-fetch missing descriptions for any listing (LinkedIn, Indeed, Glassdoor, Adzuna, The Ladders, generic).")

    _enrich_task = get_task_for_job(DEFAULT_DB, "enrich_descriptions", 0)
    _enrich_running = _enrich_task and _enrich_task["status"] in ("queued", "running")

    if st.button("🔍 Fill Missing Descriptions", use_container_width=True, type="primary",
                 disabled=bool(_enrich_running)):
        submit_task(DEFAULT_DB, "enrich_descriptions", 0)
        st.rerun()

    if _enrich_running:
        @st.fragment(run_every=4)
        def _enrich_status():
            t = get_task_for_job(DEFAULT_DB, "enrich_descriptions", 0)
            if t and t["status"] in ("queued", "running"):
                st.info("⏳ Fetching descriptions…")
            else:
                st.rerun()
        _enrich_status()
    elif _enrich_task and _enrich_task["status"] == "completed":
        _dismissible(f"enrich_{_enrich_task['id']}", "completed",
                     f"✅ {_enrich_task.get('error', 'Done')}")
    elif _enrich_task and _enrich_task["status"] == "failed":
        _dismissible(f"enrich_{_enrich_task['id']}", "failed",
                     f"Enrich failed: {_enrich_task.get('error', '')}")

with mid:
    unscored = sum(1 for j in __import__("scripts.db", fromlist=["get_jobs_by_status"])
                   .get_jobs_by_status(DEFAULT_DB, "pending")
                   if j.get("match_score") is None and j.get("description"))
    st.subheader("Score Listings")
    st.caption(f"Run TF-IDF match scoring against Alex's resume. {unscored} pending job{'s' if unscored != 1 else ''} unscored.")
    if st.button("📊 Score All Unscored Jobs", use_container_width=True, type="primary",
                 disabled=unscored == 0):
        with st.spinner("Scoring…"):
            result = subprocess.run(
                ["conda", "run", "-n", "job-seeker", "python", "scripts/match.py"],
                capture_output=True, text=True,
                cwd=str(Path(__file__).parent.parent),
            )
        if result.returncode == 0:
            st.success("Scoring complete!")
            st.code(result.stdout)
        else:
            st.error("Scoring failed.")
            st.code(result.stderr)
        st.rerun()

with right:
    approved_count = get_job_counts(DEFAULT_DB).get("approved", 0)
    st.subheader("Send to Notion")
    st.caption("Push all approved jobs to your Notion tracking database.")
    if approved_count == 0:
        st.info("No approved jobs yet. Review and approve some listings first.")
    else:
        if st.button(
            f"📤 Sync {approved_count} approved job{'s' if approved_count != 1 else ''} → Notion",
            use_container_width=True, type="primary",
        ):
            with st.spinner("Syncing to Notion…"):
                from scripts.sync import sync_to_notion
                count = sync_to_notion(DEFAULT_DB)
            st.success(f"Synced {count} job{'s' if count != 1 else ''} to Notion!")
            st.rerun()

st.divider()

# ── Email Sync ────────────────────────────────────────────────────────────────
email_left, email_right = st.columns([3, 1])

with email_left:
    st.subheader("Sync Emails")
    st.caption("Pull inbound recruiter emails and match them to active applications. "
               "New recruiter outreach is added to your Job Review queue.")

with email_right:
    _email_task = get_task_for_job(DEFAULT_DB, "email_sync", 0)
    _email_running = _email_task and _email_task["status"] in ("queued", "running")

    if st.button("📧 Sync Emails", use_container_width=True, type="primary",
                 disabled=bool(_email_running)):
        submit_task(DEFAULT_DB, "email_sync", 0)
        st.rerun()

    if _email_running:
        @st.fragment(run_every=4)
        def _email_status():
            t = get_task_for_job(DEFAULT_DB, "email_sync", 0)
            if t and t["status"] in ("queued", "running"):
                st.info("⏳ Syncing emails…")
            else:
                st.rerun()
        _email_status()
    elif _email_task and _email_task["status"] == "completed":
        _dismissible(f"email_{_email_task['id']}", "completed",
                     f"✅ {_email_task.get('error', 'Done')}")
    elif _email_task and _email_task["status"] == "failed":
        _dismissible(f"email_{_email_task['id']}", "failed",
                     f"Sync failed: {_email_task.get('error', '')}")

st.divider()

# ── Add Jobs by URL ───────────────────────────────────────────────────────────
add_left, _add_right = st.columns([3, 1])
with add_left:
    st.subheader("Add Jobs by URL")
    st.caption("Paste job listing URLs to import and scrape in the background. "
               "Supports LinkedIn, Indeed, Glassdoor, and most job boards.")

url_tab, csv_tab = st.tabs(["Paste URLs", "Upload CSV"])

with url_tab:
    url_text = st.text_area(
        "urls",
        placeholder="https://www.linkedin.com/jobs/view/1234567/\nhttps://www.indeed.com/viewjob?jk=abc",
        height=100,
        label_visibility="collapsed",
    )
    if st.button("📥 Add Jobs", key="add_urls_btn", use_container_width=True,
                 disabled=not (url_text or "").strip()):
        _urls = [u.strip() for u in url_text.strip().splitlines() if u.strip().startswith("http")]
        if _urls:
            _n = _queue_url_imports(DEFAULT_DB, _urls)
            if _n:
                st.success(f"Queued {_n} job{'s' if _n != 1 else ''} for import. Check Job Review shortly.")
            else:
                st.info("All URLs already in the database.")
            st.rerun()

with csv_tab:
    csv_file = st.file_uploader("CSV with a URL column", type=["csv"],
                                label_visibility="collapsed")
    if csv_file:
        import csv as _csv
        import io as _io
        reader = _csv.DictReader(_io.StringIO(csv_file.read().decode("utf-8", errors="replace")))
        _csv_urls = []
        for row in reader:
            for val in row.values():
                if val and val.strip().startswith("http"):
                    _csv_urls.append(val.strip())
                    break
        if _csv_urls:
            st.caption(f"Found {len(_csv_urls)} URL(s) in CSV.")
            if st.button("📥 Import CSV Jobs", key="add_csv_btn", use_container_width=True):
                _n = _queue_url_imports(DEFAULT_DB, _csv_urls)
                st.success(f"Queued {_n} job{'s' if _n != 1 else ''} for import.")
                st.rerun()
        else:
            st.warning("No URLs found — CSV must have a column whose values start with http.")


@st.fragment(run_every=3)
def _scrape_status():
    import sqlite3 as _sq
    conn = _sq.connect(DEFAULT_DB)
    conn.row_factory = _sq.Row
    rows = conn.execute(
        """SELECT bt.status, bt.error, j.title, j.company, j.url
           FROM background_tasks bt
           JOIN jobs j ON j.id = bt.job_id
           WHERE bt.task_type = 'scrape_url'
             AND bt.updated_at >= datetime('now', '-5 minutes')
           ORDER BY bt.updated_at DESC LIMIT 20"""
    ).fetchall()
    conn.close()
    if not rows:
        return
    st.caption("Recent URL imports:")
    for r in rows:
        if r["status"] == "running":
            st.info(f"⏳ Scraping {r['url']}")
        elif r["status"] == "completed":
            label = r["title"] + (f" @ {r['company']}" if r["company"] else "")
            st.success(f"✅ {label}")
        elif r["status"] == "failed":
            st.error(f"❌ {r['url']} — {r['error'] or 'scrape failed'}")


_scrape_status()

st.divider()

# ── Danger zone: purge + re-scrape ────────────────────────────────────────────
with st.expander("⚠️ Danger Zone", expanded=False):
    st.caption(
        "**Purge** permanently deletes jobs from the local database. "
        "Applied and synced jobs are never touched."
    )

    purge_col, rescrape_col, email_col, tasks_col = st.columns(4)

    with purge_col:
        st.markdown("**Purge pending & rejected**")
        st.caption("Removes all _pending_ and _rejected_ listings so the next discovery starts fresh.")
        if st.button("🗑 Purge Pending + Rejected", use_container_width=True):
            st.session_state["confirm_purge"] = "partial"

        if st.session_state.get("confirm_purge") == "partial":
            st.warning("Are you sure? This cannot be undone.")
            c1, c2 = st.columns(2)
            if c1.button("Yes, purge", type="primary", use_container_width=True):
                deleted = purge_jobs(DEFAULT_DB, statuses=["pending", "rejected"])
                st.success(f"Purged {deleted} jobs.")
                st.session_state.pop("confirm_purge", None)
                st.rerun()
            if c2.button("Cancel", use_container_width=True):
                st.session_state.pop("confirm_purge", None)
                st.rerun()

    with email_col:
        st.markdown("**Purge email data**")
        st.caption("Clears all email thread logs and email-sourced pending jobs so the next sync starts fresh.")
        if st.button("📧 Purge Email Data", use_container_width=True):
            st.session_state["confirm_purge"] = "email"

        if st.session_state.get("confirm_purge") == "email":
            st.warning("This deletes all email contacts and email-sourced jobs. Cannot be undone.")
            c1, c2 = st.columns(2)
            if c1.button("Yes, purge emails", type="primary", use_container_width=True):
                contacts, jobs = purge_email_data(DEFAULT_DB)
                st.success(f"Purged {contacts} email contacts, {jobs} email jobs.")
                st.session_state.pop("confirm_purge", None)
                st.rerun()
            if c2.button("Cancel  ", use_container_width=True):
                st.session_state.pop("confirm_purge", None)
                st.rerun()

    with tasks_col:
        _active = get_active_tasks(DEFAULT_DB)
        st.markdown("**Kill stuck tasks**")
        st.caption(f"Force-fail all queued/running background tasks. Currently **{len(_active)}** active.")
        if st.button("⏹ Kill All Tasks", use_container_width=True, disabled=len(_active) == 0):
            killed = kill_stuck_tasks(DEFAULT_DB)
            st.success(f"Killed {killed} task(s).")
            st.rerun()

    with rescrape_col:
        st.markdown("**Purge all & re-scrape**")
        st.caption("Wipes _all_ non-applied, non-synced jobs then immediately runs a fresh discovery.")
        if st.button("🔄 Purge All + Re-scrape", use_container_width=True):
            st.session_state["confirm_purge"] = "full"

        if st.session_state.get("confirm_purge") == "full":
            st.warning("This will delete ALL pending, approved, and rejected jobs, then re-scrape. Applied and synced records are kept.")
            c1, c2 = st.columns(2)
            if c1.button("Yes, wipe + scrape", type="primary", use_container_width=True):
                purge_jobs(DEFAULT_DB, statuses=["pending", "approved", "rejected"])
                submit_task(DEFAULT_DB, "discovery", 0)
                st.session_state.pop("confirm_purge", None)
                st.rerun()
            if c2.button("Cancel ", use_container_width=True):
                st.session_state.pop("confirm_purge", None)
                st.rerun()

    st.divider()

    pending_col, nonremote_col, approved_col, _ = st.columns(4)

    with pending_col:
        st.markdown("**Purge pending review**")
        st.caption("Removes only _pending_ listings, keeping your rejected history intact.")
        if st.button("🗑 Purge Pending Only", use_container_width=True):
            st.session_state["confirm_purge"] = "pending_only"

        if st.session_state.get("confirm_purge") == "pending_only":
            st.warning("Deletes all pending jobs. Rejected jobs are kept. Cannot be undone.")
            c1, c2 = st.columns(2)
            if c1.button("Yes, purge pending", type="primary", use_container_width=True):
                deleted = purge_jobs(DEFAULT_DB, statuses=["pending"])
                st.success(f"Purged {deleted} pending jobs.")
                st.session_state.pop("confirm_purge", None)
                st.rerun()
            if c2.button("Cancel   ", use_container_width=True):
                st.session_state.pop("confirm_purge", None)
                st.rerun()

    with nonremote_col:
        st.markdown("**Purge non-remote**")
        st.caption("Removes pending/approved/rejected jobs where remote is not set. Keeps anything already in the pipeline.")
        if st.button("🏢 Purge On-site Jobs", use_container_width=True):
            st.session_state["confirm_purge"] = "non_remote"

        if st.session_state.get("confirm_purge") == "non_remote":
            st.warning("Deletes all non-remote jobs not yet applied to. Cannot be undone.")
            c1, c2 = st.columns(2)
            if c1.button("Yes, purge on-site", type="primary", use_container_width=True):
                deleted = purge_non_remote(DEFAULT_DB)
                st.success(f"Purged {deleted} non-remote jobs.")
                st.session_state.pop("confirm_purge", None)
                st.rerun()
            if c2.button("Cancel    ", use_container_width=True):
                st.session_state.pop("confirm_purge", None)
                st.rerun()

    with approved_col:
        st.markdown("**Purge approved (unapplied)**")
        st.caption("Removes _approved_ jobs you haven't applied to yet — e.g. to reset after a review pass.")
        if st.button("🗑 Purge Approved", use_container_width=True):
            st.session_state["confirm_purge"] = "approved_only"

        if st.session_state.get("confirm_purge") == "approved_only":
            st.warning("Deletes all approved-but-not-applied jobs. Cannot be undone.")
            c1, c2 = st.columns(2)
            if c1.button("Yes, purge approved", type="primary", use_container_width=True):
                deleted = purge_jobs(DEFAULT_DB, statuses=["approved"])
                st.success(f"Purged {deleted} approved jobs.")
                st.session_state.pop("confirm_purge", None)
                st.rerun()
            if c2.button("Cancel     ", use_container_width=True):
                st.session_state.pop("confirm_purge", None)
                st.rerun()

    st.divider()

    archive_col1, archive_col2, _, _ = st.columns(4)

    with archive_col1:
        st.markdown("**Archive remaining**")
        st.caption(
            "Move all _pending_ and _rejected_ jobs to archived status. "
            "Archived jobs stay in the DB for dedup — they just won't appear in Job Review."
        )
        if st.button("📦 Archive Pending + Rejected", use_container_width=True):
            st.session_state["confirm_purge"] = "archive_remaining"

        if st.session_state.get("confirm_purge") == "archive_remaining":
            st.info("Jobs will be archived (not deleted) — URLs are kept for dedup.")
            c1, c2 = st.columns(2)
            if c1.button("Yes, archive", type="primary", use_container_width=True):
                archived = archive_jobs(DEFAULT_DB, statuses=["pending", "rejected"])
                st.success(f"Archived {archived} jobs.")
                st.session_state.pop("confirm_purge", None)
                st.rerun()
            if c2.button("Cancel      ", use_container_width=True):
                st.session_state.pop("confirm_purge", None)
                st.rerun()

    with archive_col2:
        st.markdown("**Archive approved (unapplied)**")
        st.caption("Archive _approved_ listings you decided to skip — keeps history without cluttering the apply queue.")
        if st.button("📦 Archive Approved", use_container_width=True):
            st.session_state["confirm_purge"] = "archive_approved"

        if st.session_state.get("confirm_purge") == "archive_approved":
            st.info("Approved jobs will be archived (not deleted).")
            c1, c2 = st.columns(2)
            if c1.button("Yes, archive approved", type="primary", use_container_width=True):
                archived = archive_jobs(DEFAULT_DB, statuses=["approved"])
                st.success(f"Archived {archived} approved jobs.")
                st.session_state.pop("confirm_purge", None)
                st.rerun()
            if c2.button("Cancel       ", use_container_width=True):
                st.session_state.pop("confirm_purge", None)
                st.rerun()
