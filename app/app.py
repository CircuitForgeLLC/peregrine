# app/app.py
"""
Streamlit entry point — uses st.navigation() to control the sidebar.
Main workflow pages are listed at the top; Settings is separated into
a "System" section so it doesn't crowd the navigation.

Run: streamlit run app/app.py
     bash scripts/manage-ui.sh start
"""
import logging
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(level=logging.WARNING, format="%(name)s %(levelname)s: %(message)s")

IS_DEMO = os.environ.get("DEMO_MODE", "").lower() in ("1", "true", "yes")

import streamlit as st
from scripts.db import DEFAULT_DB, init_db, get_active_tasks
from app.feedback import inject_feedback_button
from app.cloud_session import resolve_session, get_db_path
import sqlite3

st.set_page_config(
    page_title="Job Seeker",
    page_icon="💼",
    layout="wide",
)

resolve_session("peregrine")
init_db(get_db_path())

# ── Startup cleanup — runs once per server process via cache_resource ──────────
@st.cache_resource
def _startup() -> None:
    """Runs exactly once per server lifetime (st.cache_resource).
    1. Marks zombie tasks as failed.
    2. Auto-queues re-runs for any research generated without SearXNG data,
       if SearXNG is now reachable.
    """
    conn = sqlite3.connect(get_db_path())
    conn.execute(
        "UPDATE background_tasks SET status='failed', error='Interrupted by server restart',"
        " finished_at=datetime('now') WHERE status IN ('queued','running')"
    )
    conn.commit()

    # Auto-recovery: re-run LLM-only research when SearXNG is available
    try:
        import requests as _req
        if _req.get("http://localhost:8888/", timeout=3).status_code == 200:
            from scripts.task_runner import submit_task
            _ACTIVE_STAGES = ("phone_screen", "interviewing", "offer", "hired")
            rows = conn.execute(
                """SELECT cr.job_id FROM company_research cr
                   JOIN jobs j ON j.id = cr.job_id
                   WHERE (cr.scrape_used IS NULL OR cr.scrape_used = 0)
                   AND j.status IN ({})""".format(",".join("?" * len(_ACTIVE_STAGES))),
                _ACTIVE_STAGES,
            ).fetchall()
            for (job_id,) in rows:
                submit_task(str(get_db_path()), "company_research", job_id)
    except Exception:
        pass  # never block startup

    conn.close()

_startup()

# Silent license refresh on startup — no-op if unreachable
try:
    from scripts.license import refresh_if_needed as _refresh_license
    _refresh_license()
except Exception:
    pass

# ── First-run wizard gate ───────────────────────────────────────────────────────
from scripts.user_profile import UserProfile as _UserProfile
_USER_YAML = Path(__file__).parent.parent / "config" / "user.yaml"

_show_wizard = not IS_DEMO and (
    not _UserProfile.exists(_USER_YAML)
    or not _UserProfile(_USER_YAML).wizard_complete
)
if _show_wizard:
    _setup_page = st.Page("pages/0_Setup.py", title="Setup", icon="👋")
    st.navigation({"": [_setup_page]}).run()
    st.stop()

# ── Navigation ─────────────────────────────────────────────────────────────────
# st.navigation() must be called before any sidebar writes so it can establish
# the navigation structure first; sidebar additions come after.
pages = {
    "": [
        st.Page("Home.py",                   title="Home",            icon="🏠"),
        st.Page("pages/1_Job_Review.py",     title="Job Review",      icon="📋"),
        st.Page("pages/4_Apply.py",          title="Apply Workspace", icon="🚀"),
        st.Page("pages/5_Interviews.py",     title="Interviews",      icon="🎯"),
        st.Page("pages/6_Interview_Prep.py", title="Interview Prep",  icon="📞"),
        st.Page("pages/7_Survey.py",         title="Survey Assistant", icon="📋"),
    ],
    "System": [
        st.Page("pages/2_Settings.py",       title="Settings",        icon="⚙️"),
    ],
}

pg = st.navigation(pages)

# ── Background task sidebar indicator ─────────────────────────────────────────
# Fragment polls every 3s so stage labels update live without a full page reload.
# The sidebar context WRAPS the fragment call — do not write to st.sidebar inside it.
@st.fragment(run_every=3)
def _task_indicator():
    tasks = get_active_tasks(get_db_path())
    if not tasks:
        return
    st.divider()
    st.markdown(f"**⏳ {len(tasks)} task(s) running**")
    for t in tasks:
        icon = "⏳" if t["status"] == "running" else "🕐"
        task_type = t["task_type"]
        if task_type == "cover_letter":
            label = "Cover letter"
        elif task_type == "company_research":
            label = "Research"
        elif task_type == "email_sync":
            label = "Email sync"
        elif task_type == "discovery":
            label = "Discovery"
        elif task_type == "enrich_descriptions":
            label = "Enriching"
        elif task_type == "scrape_url":
            label = "Scraping URL"
        elif task_type == "wizard_generate":
            label = "Wizard generation"
        elif task_type == "enrich_craigslist":
            label = "Enriching listing"
        else:
            label = task_type.replace("_", " ").title()
        stage = t.get("stage") or ""
        detail = f" · {stage}" if stage else (f" — {t.get('company')}" if t.get("company") else "")
        st.caption(f"{icon} {label}{detail}")

@st.cache_resource
def _get_version() -> str:
    try:
        return subprocess.check_output(
            ["git", "describe", "--tags", "--always"],
            cwd=Path(__file__).parent.parent,
            text=True,
        ).strip()
    except Exception:
        return "dev"

with st.sidebar:
    if IS_DEMO:
        st.info(
            "**Public demo** — read-only sample data. "
            "AI features and data saves are disabled.\n\n"
            "[Get your own instance →](https://circuitforge.tech/software/peregrine)",
            icon="🔒",
        )
    _task_indicator()

    # Cloud LLM indicator — shown whenever any cloud backend is active
    _llm_cfg_path = Path(__file__).parent.parent / "config" / "llm.yaml"
    try:
        import yaml as _yaml
        from scripts.byok_guard import cloud_backends as _cloud_backends
        _active_cloud = _cloud_backends(_yaml.safe_load(_llm_cfg_path.read_text(encoding="utf-8")) or {})
    except Exception:
        _active_cloud = []
    if _active_cloud:
        _provider_names = ", ".join(b.replace("_", " ").title() for b in _active_cloud)
        st.warning(
            f"**Cloud LLM active**\n\n"
            f"{_provider_names}\n\n"
            "AI features send content to this provider. "
            "[Change in Settings](2_Settings)",
            icon="🔓",
        )

    st.divider()
    st.caption(f"Peregrine {_get_version()}")
    inject_feedback_button(page=pg.title)

pg.run()
