# app/Home.py
"""
Job Seeker Dashboard — Home page.
Shows counts, Run Discovery button, and Sync to Notion button.
"""
import subprocess
import sys
from pathlib import Path

import streamlit as st
import yaml

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.user_profile import UserProfile

_USER_YAML = Path(__file__).parent.parent / "config" / "user.yaml"
_profile = UserProfile(_USER_YAML) if UserProfile.exists(_USER_YAML) else None
_name = _profile.name if _profile else "Job Seeker"

from scripts.db import init_db, get_job_counts, purge_jobs, purge_email_data, \
    purge_non_remote, archive_jobs, kill_stuck_tasks, cancel_task, \
    get_task_for_job, get_active_tasks, insert_job, get_existing_urls
from scripts.task_runner import submit_task
from app.cloud_session import resolve_session, get_db_path

_CONFIG_DIR = Path(__file__).parent.parent / "config"
_NOTION_CONNECTED = (_CONFIG_DIR / "integrations" / "notion.yaml").exists()

resolve_session("peregrine")
init_db(get_db_path())

def _email_configured() -> bool:
    _e = Path(__file__).parent.parent / "config" / "email.yaml"
    if not _e.exists():
        return False
    import yaml as _yaml
    _cfg = _yaml.safe_load(_e.read_text()) or {}
    return bool(_cfg.get("username") or _cfg.get("user") or _cfg.get("imap_host"))

def _notion_configured() -> bool:
    _n = Path(__file__).parent.parent / "config" / "notion.yaml"
    if not _n.exists():
        return False
    import yaml as _yaml
    _cfg = _yaml.safe_load(_n.read_text()) or {}
    return bool(_cfg.get("token"))

def _keywords_configured() -> bool:
    _k = Path(__file__).parent.parent / "config" / "resume_keywords.yaml"
    if not _k.exists():
        return False
    import yaml as _yaml
    _cfg = _yaml.safe_load(_k.read_text()) or {}
    return bool(_cfg.get("keywords") or _cfg.get("required") or _cfg.get("preferred"))

_SETUP_BANNERS = [
    {"key": "connect_cloud",       "text": "Connect a cloud service for resume/cover letter storage",
     "link_label": "Settings → Integrations",
     "done": _notion_configured},
    {"key": "setup_email",         "text": "Set up email sync to catch recruiter outreach",
     "link_label": "Settings → Email",
     "done": _email_configured},
    {"key": "setup_email_labels",  "text": "Set up email label filters for auto-classification",
     "link_label": "Settings → Email (label guide)",
     "done": _email_configured},
    {"key": "tune_mission",        "text": "Tune your mission preferences for better cover letters",
     "link_label": "Settings → My Profile"},
    {"key": "configure_keywords",  "text": "Configure keywords and blocklist for smarter search",
     "link_label": "Settings → Search",
     "done": _keywords_configured},
    {"key": "upload_corpus",       "text": "Upload your cover letter corpus for voice fine-tuning",
     "link_label": "Settings → Fine-Tune"},
    {"key": "configure_linkedin",  "text": "Configure LinkedIn Easy Apply automation",
     "link_label": "Settings → Integrations"},
    {"key": "setup_searxng",       "text": "Set up company research with SearXNG",
     "link_label": "Settings → Services"},
    {"key": "target_companies",    "text": "Build a target company list for focused outreach",
     "link_label": "Settings → Search"},
    {"key": "setup_notifications", "text": "Set up notifications for stage changes",
     "link_label": "Settings → Integrations"},
    {"key": "tune_model",          "text": "Tune a custom cover letter model on your writing",
     "link_label": "Settings → Fine-Tune"},
    {"key": "review_training",     "text": "Review and curate training data for model tuning",
     "link_label": "Settings → Fine-Tune"},
    {"key": "setup_calendar",      "text": "Set up calendar sync to track interview dates",
     "link_label": "Settings → Integrations"},
]


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


st.title(f"🔍 {_name}'s Job Search")
st.caption("Discover → Review → Sync to Notion")

st.divider()


@st.fragment(run_every=10)
def _live_counts():
    counts = get_job_counts(get_db_path())
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

    _disc_task = get_task_for_job(get_db_path(), "discovery", 0)
    _disc_running = _disc_task and _disc_task["status"] in ("queued", "running")

    if st.button("🚀 Run Discovery", use_container_width=True, type="primary",
                 disabled=bool(_disc_running)):
        submit_task(get_db_path(), "discovery", 0)
        st.rerun()

    if _disc_running:
        @st.fragment(run_every=4)
        def _disc_status():
            t = get_task_for_job(get_db_path(), "discovery", 0)
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

    _enrich_task = get_task_for_job(get_db_path(), "enrich_descriptions", 0)
    _enrich_running = _enrich_task and _enrich_task["status"] in ("queued", "running")

    if st.button("🔍 Fill Missing Descriptions", use_container_width=True, type="primary",
                 disabled=bool(_enrich_running)):
        submit_task(get_db_path(), "enrich_descriptions", 0)
        st.rerun()

    if _enrich_running:
        @st.fragment(run_every=4)
        def _enrich_status():
            t = get_task_for_job(get_db_path(), "enrich_descriptions", 0)
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
                   .get_jobs_by_status(get_db_path(), "pending")
                   if j.get("match_score") is None and j.get("description"))
    st.subheader("Score Listings")
    st.caption(f"Run TF-IDF match scoring against {_name}'s resume. {unscored} pending job{'s' if unscored != 1 else ''} unscored.")
    if st.button("📊 Score All Unscored Jobs", use_container_width=True, type="primary",
                 disabled=unscored == 0):
        with st.spinner("Scoring…"):
            result = subprocess.run(
                [sys.executable, "scripts/match.py"],
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
    approved_count = get_job_counts(get_db_path()).get("approved", 0)
    if _NOTION_CONNECTED:
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
                    count = sync_to_notion(get_db_path())
                st.success(f"Synced {count} job{'s' if count != 1 else ''} to Notion!")
                st.rerun()
    else:
        st.subheader("Set up a sync integration")
        st.caption("Connect an integration to push approved jobs to your tracking database.")
        if st.button("⚙️ Go to Integrations", use_container_width=True):
            st.switch_page("pages/2_Settings.py")

st.divider()

# ── Email Sync ────────────────────────────────────────────────────────────────
email_left, email_right = st.columns([3, 1])

with email_left:
    st.subheader("Sync Emails")
    st.caption("Pull inbound recruiter emails and match them to active applications. "
               "New recruiter outreach is added to your Job Review queue.")

with email_right:
    _email_task = get_task_for_job(get_db_path(), "email_sync", 0)
    _email_running = _email_task and _email_task["status"] in ("queued", "running")

    if st.button("📧 Sync Emails", use_container_width=True, type="primary",
                 disabled=bool(_email_running)):
        submit_task(get_db_path(), "email_sync", 0)
        st.rerun()

    if _email_running:
        @st.fragment(run_every=4)
        def _email_status():
            t = get_task_for_job(get_db_path(), "email_sync", 0)
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
            _n = _queue_url_imports(get_db_path(), _urls)
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
                _n = _queue_url_imports(get_db_path(),_csv_urls)
                st.success(f"Queued {_n} job{'s' if _n != 1 else ''} for import.")
                st.rerun()
        else:
            st.warning("No URLs found — CSV must have a column whose values start with http.")


@st.fragment(run_every=3)
def _scrape_status():
    import sqlite3 as _sq
    conn = _sq.connect(get_db_path())
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

# ── Danger zone ───────────────────────────────────────────────────────────────
with st.expander("⚠️ Danger Zone", expanded=False):

    # ── Queue reset (the common case) ─────────────────────────────────────────
    st.markdown("**Queue reset**")
    st.caption(
        "Archive clears your review queue while keeping job URLs for dedup, "
        "so the same listings won't resurface on the next discovery run. "
        "Use hard purge only if you want a full clean slate including dedup history."
    )

    _scope = st.radio(
        "Clear scope",
        ["Pending only", "Pending + approved (stale search)"],
        horizontal=True,
        label_visibility="collapsed",
    )
    _scope_statuses = (
        ["pending"] if _scope == "Pending only" else ["pending", "approved"]
    )

    _qc1, _qc2, _qc3 = st.columns([2, 2, 4])
    if _qc1.button("📦 Archive & reset", use_container_width=True, type="primary"):
        st.session_state["confirm_dz"] = "archive"
    if _qc2.button("🗑 Hard purge (delete)", use_container_width=True):
        st.session_state["confirm_dz"] = "purge"

    if st.session_state.get("confirm_dz") == "archive":
        st.info(
            f"Archive **{', '.join(_scope_statuses)}** jobs? "
            "URLs are kept for dedup — nothing is permanently deleted."
        )
        _dc1, _dc2 = st.columns(2)
        if _dc1.button("Yes, archive", type="primary", use_container_width=True, key="dz_archive_confirm"):
            n = archive_jobs(get_db_path(), statuses=_scope_statuses)
            st.success(f"Archived {n} jobs.")
            st.session_state.pop("confirm_dz", None)
            st.rerun()
        if _dc2.button("Cancel", use_container_width=True, key="dz_archive_cancel"):
            st.session_state.pop("confirm_dz", None)
            st.rerun()

    if st.session_state.get("confirm_dz") == "purge":
        st.warning(
            f"Permanently delete **{', '.join(_scope_statuses)}** jobs? "
            "This removes the URLs from dedup history too. Cannot be undone."
        )
        _dc1, _dc2 = st.columns(2)
        if _dc1.button("Yes, delete", type="primary", use_container_width=True, key="dz_purge_confirm"):
            n = purge_jobs(get_db_path(), statuses=_scope_statuses)
            st.success(f"Deleted {n} jobs.")
            st.session_state.pop("confirm_dz", None)
            st.rerun()
        if _dc2.button("Cancel", use_container_width=True, key="dz_purge_cancel"):
            st.session_state.pop("confirm_dz", None)
            st.rerun()

    st.divider()

    # ── Background tasks ──────────────────────────────────────────────────────
    _active = get_active_tasks(get_db_path())
    st.markdown(f"**Background tasks** — {len(_active)} active")

    if _active:
        _task_icons = {"cover_letter": "✉️", "research": "🔍", "discovery": "🌐", "enrich_descriptions": "📝"}
        for _t in _active:
            _tc1, _tc2, _tc3 = st.columns([3, 4, 2])
            _icon = _task_icons.get(_t["task_type"], "⚙️")
            _tc1.caption(f"{_icon} `{_t['task_type']}`")
            _job_label = f"{_t['title']} @ {_t['company']}" if _t.get("title") else f"job #{_t['job_id']}"
            _tc2.caption(_job_label)
            _tc3.caption(f"_{_t['status']}_")
            if st.button("✕ Cancel", key=f"dz_cancel_task_{_t['id']}", use_container_width=True):
                cancel_task(get_db_path(), _t["id"])
                st.rerun()
        st.caption("")

    _kill_col, _ = st.columns([2, 6])
    if _kill_col.button("⏹ Kill all stuck", use_container_width=True, disabled=len(_active) == 0):
        killed = kill_stuck_tasks(get_db_path())
        st.success(f"Killed {killed} task(s).")
        st.rerun()

    st.divider()

    # ── Rarely needed (collapsed) ─────────────────────────────────────────────
    with st.expander("More options", expanded=False):
        _rare1, _rare2, _rare3 = st.columns(3)

        with _rare1:
            st.markdown("**Purge email data**")
            st.caption("Clears all email thread logs and email-sourced pending jobs.")
            if st.button("📧 Purge Email Data", use_container_width=True):
                st.session_state["confirm_dz"] = "email"
            if st.session_state.get("confirm_dz") == "email":
                st.warning("Deletes all email contacts and email-sourced jobs. Cannot be undone.")
                _ec1, _ec2 = st.columns(2)
                if _ec1.button("Yes, purge emails", type="primary", use_container_width=True, key="dz_email_confirm"):
                    contacts, jobs = purge_email_data(get_db_path())
                    st.success(f"Purged {contacts} email contacts, {jobs} email jobs.")
                    st.session_state.pop("confirm_dz", None)
                    st.rerun()
                if _ec2.button("Cancel", use_container_width=True, key="dz_email_cancel"):
                    st.session_state.pop("confirm_dz", None)
                    st.rerun()

        with _rare2:
            st.markdown("**Purge non-remote**")
            st.caption("Removes pending/approved/rejected on-site listings from the DB.")
            if st.button("🏢 Purge On-site Jobs", use_container_width=True):
                st.session_state["confirm_dz"] = "non_remote"
            if st.session_state.get("confirm_dz") == "non_remote":
                st.warning("Deletes all non-remote jobs not yet applied to. Cannot be undone.")
                _rc1, _rc2 = st.columns(2)
                if _rc1.button("Yes, purge on-site", type="primary", use_container_width=True, key="dz_nonremote_confirm"):
                    deleted = purge_non_remote(get_db_path())
                    st.success(f"Purged {deleted} non-remote jobs.")
                    st.session_state.pop("confirm_dz", None)
                    st.rerun()
                if _rc2.button("Cancel", use_container_width=True, key="dz_nonremote_cancel"):
                    st.session_state.pop("confirm_dz", None)
                    st.rerun()

        with _rare3:
            st.markdown("**Wipe all + re-scrape**")
            st.caption("Deletes all non-applied jobs then immediately runs a fresh discovery.")
            if st.button("🔄 Wipe + Re-scrape", use_container_width=True):
                st.session_state["confirm_dz"] = "rescrape"
            if st.session_state.get("confirm_dz") == "rescrape":
                st.warning("Wipes ALL pending, approved, and rejected jobs, then re-scrapes. Applied and synced records are kept.")
                _wc1, _wc2 = st.columns(2)
                if _wc1.button("Yes, wipe + scrape", type="primary", use_container_width=True, key="dz_rescrape_confirm"):
                    purge_jobs(get_db_path(), statuses=["pending", "approved", "rejected"])
                    submit_task(get_db_path(), "discovery", 0)
                    st.session_state.pop("confirm_dz", None)
                    st.rerun()
                if _wc2.button("Cancel", use_container_width=True, key="dz_rescrape_cancel"):
                    st.session_state.pop("confirm_dz", None)
                    st.rerun()

# ── Setup banners ─────────────────────────────────────────────────────────────
if _profile and _profile.wizard_complete:
    _dismissed = set(_profile.dismissed_banners)
    _pending_banners = [
        b for b in _SETUP_BANNERS
        if b["key"] not in _dismissed and not b.get("done", lambda: False)()
    ]
    if _pending_banners:
        st.divider()
        st.markdown("#### Finish setting up Peregrine")
        for banner in _pending_banners:
            _bcol, _bdismiss = st.columns([10, 1])
            with _bcol:
                _ic, _lc = st.columns([3, 1])
                _ic.info(f"💡 {banner['text']}")
                with _lc:
                    st.write("")
                    st.page_link("pages/2_Settings.py", label=banner['link_label'], icon="⚙️")
            with _bdismiss:
                st.write("")
                if st.button("✕", key=f"dismiss_banner_{banner['key']}", help="Dismiss"):
                    _data = yaml.safe_load(_USER_YAML.read_text()) if _USER_YAML.exists() else {}
                    _data.setdefault("dismissed_banners", [])
                    if banner["key"] not in _data["dismissed_banners"]:
                        _data["dismissed_banners"].append(banner["key"])
                    _USER_YAML.write_text(yaml.dump(_data, default_flow_style=False, allow_unicode=True))
                    st.rerun()
