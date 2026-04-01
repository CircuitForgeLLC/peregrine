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
from app.cloud_session import resolve_session, get_db_path, get_config_dir, get_cloud_tier
import sqlite3

_LOGO_CIRCLE = Path(__file__).parent / "static" / "peregrine_logo_circle.png"
_LOGO_FULL   = Path(__file__).parent / "static" / "peregrine_logo.png"

st.set_page_config(
    page_title="Peregrine",
    page_icon=str(_LOGO_CIRCLE) if _LOGO_CIRCLE.exists() else "💼",
    layout="wide",
)

resolve_session("peregrine")
init_db(get_db_path())

# Demo tier — initialize once per session (cookie persistence handled client-side)
if IS_DEMO and "simulated_tier" not in st.session_state:
    st.session_state["simulated_tier"] = "paid"

if _LOGO_CIRCLE.exists():
    st.logo(str(_LOGO_CIRCLE), icon_image=str(_LOGO_CIRCLE))

# ── Startup cleanup — runs once per server process via cache_resource ──────────
@st.cache_resource
def _startup() -> None:
    """Runs exactly once per server lifetime (st.cache_resource).
    1. Marks zombie tasks as failed.
    2. Auto-queues re-runs for any research generated without SearXNG data,
       if SearXNG is now reachable.
    """
    # Reset only in-flight tasks — queued tasks survive for the scheduler to resume.
    # MUST run before any submit_task() call in this function.
    from scripts.db import reset_running_tasks
    reset_running_tasks(get_db_path())

    conn = sqlite3.connect(get_db_path())

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
_USER_YAML = get_config_dir() / "user.yaml"

_show_wizard = not IS_DEMO and (
    not _UserProfile.exists(_USER_YAML)
    or not _UserProfile(_USER_YAML).wizard_complete
)
if _show_wizard:
    _setup_page = st.Page("pages/0_Setup.py", title="Setup", icon="👋")
    st.navigation({"": [_setup_page]}).run()
    # Sync UI cookie even during wizard so vue preference redirects correctly.
    # Tier not yet computed here — use cloud tier (or "free" fallback).
    try:
        from app.components.ui_switcher import sync_ui_cookie as _sync_wizard_cookie
        from app.cloud_session import get_cloud_tier as _gctr
        _wizard_tier = _gctr() if _gctr() != "local" else "free"
        _sync_wizard_cookie(_USER_YAML, _wizard_tier)
    except Exception:
        pass
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
_TASK_LABELS = {
    "cover_letter":        "Cover letter",
    "company_research":    "Research",
    "email_sync":          "Email sync",
    "discovery":           "Discovery",
    "enrich_descriptions": "Enriching descriptions",
    "score":               "Scoring matches",
    "scrape_url":          "Scraping listing",
    "enrich_craigslist":   "Enriching listing",
    "wizard_generate":     "Wizard generation",
    "prepare_training":    "Training data",
}
_DISCOVERY_PIPELINE = ["discovery", "enrich_descriptions", "score"]


@st.fragment(run_every=3)
def _task_indicator():
    tasks = get_active_tasks(get_db_path())
    if not tasks:
        return
    st.divider()
    st.markdown(f"**⏳ {len(tasks)} task(s) running**")

    pipeline_set   = set(_DISCOVERY_PIPELINE)
    pipeline_tasks = [t for t in tasks if t["task_type"] in pipeline_set]
    other_tasks    = [t for t in tasks if t["task_type"] not in pipeline_set]

    # Discovery pipeline: render as ordered sub-queue with indented steps
    if pipeline_tasks:
        ordered = [
            next((t for t in pipeline_tasks if t["task_type"] == typ), None)
            for typ in _DISCOVERY_PIPELINE
        ]
        ordered = [t for t in ordered if t is not None]
        for i, t in enumerate(ordered):
            icon   = "⏳" if t["status"] == "running" else "🕐"
            label  = _TASK_LABELS.get(t["task_type"], t["task_type"].replace("_", " ").title())
            stage  = t.get("stage") or ""
            detail = f" · {stage}" if stage else ""
            prefix = "" if i == 0 else "↳ "
            st.caption(f"{prefix}{icon} {label}{detail}")

    # All other tasks (cover letter, email sync, etc.) as individual rows
    for t in other_tasks:
        icon   = "⏳" if t["status"] == "running" else "🕐"
        label  = _TASK_LABELS.get(t["task_type"], t["task_type"].replace("_", " ").title())
        stage  = t.get("stage") or ""
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

# ── Effective tier (resolved before sidebar so switcher can use it) ──────────
# get_cloud_tier() returns "local" in dev/self-hosted mode, real tier in cloud.
_ui_profile = _UserProfile(_USER_YAML) if _UserProfile.exists(_USER_YAML) else None
_ui_yaml_tier = _ui_profile.effective_tier if _ui_profile else "free"
_ui_cloud_tier = get_cloud_tier()
_ui_tier = _ui_cloud_tier if _ui_cloud_tier != "local" else _ui_yaml_tier

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
    try:
        from app.components.ui_switcher import render_sidebar_switcher
        render_sidebar_switcher(_USER_YAML, _ui_tier)
    except Exception:
        pass  # never crash the app over the sidebar switcher
    st.caption(f"Peregrine {_get_version()}")
    inject_feedback_button(page=pg.title)

# ── Demo toolbar (DEMO_MODE only) ───────────────────────────────────────────
if IS_DEMO:
    from app.components.demo_toolbar import render_demo_toolbar
    render_demo_toolbar()

# ── UI switcher banner (paid tier; or all visitors in demo mode) ─────────────
try:
    from app.components.ui_switcher import render_banner
    render_banner(_USER_YAML, _ui_tier)
except Exception:
    pass  # never crash the app over the banner

pg.run()

# ── UI preference cookie sync (runs after page render) ──────────────────────
try:
    from app.components.ui_switcher import sync_ui_cookie
    sync_ui_cookie(_USER_YAML, _ui_tier)
except Exception:
    pass  # never crash the app over cookie sync
