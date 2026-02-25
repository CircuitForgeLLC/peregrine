# app/pages/5_Interviews.py
"""
Interviews — Kanban board for tracking post-application engagement.

Pipeline: applied → phone_screen → interviewing → offer → hired
          (or rejected at any stage, with stage captured for analytics)

Features:
  - Kanban columns for each interview stage
  - Company research brief auto-generated when advancing to Phone Screen
  - Contact / email log per job
  - Email reply drafter via LLM
  - Interview date tracking with calendar push hint
  - Rejection analytics
"""
import sys
from collections import Counter
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import streamlit as st

from scripts.user_profile import UserProfile

_USER_YAML = Path(__file__).parent.parent.parent / "config" / "user.yaml"
_profile = UserProfile(_USER_YAML) if UserProfile.exists(_USER_YAML) else None
_name = _profile.name if _profile else "Job Seeker"

from scripts.db import (
    DEFAULT_DB, init_db,
    get_interview_jobs, advance_to_stage, reject_at_stage,
    set_interview_date, add_contact, get_contacts,
    get_research, get_task_for_job, get_job_by_id,
    get_unread_stage_signals, dismiss_stage_signal,
)
from scripts.task_runner import submit_task

st.title("🎯 Interviews")

init_db(DEFAULT_DB)

# ── Sidebar: Email sync ────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### 📧 Email Sync")
    _email_task = get_task_for_job(DEFAULT_DB, "email_sync", 0)
    _email_running = _email_task and _email_task["status"] in ("queued", "running")

    if st.button("🔄 Sync Emails", use_container_width=True, type="primary",
                 disabled=bool(_email_running)):
        submit_task(DEFAULT_DB, "email_sync", 0)
        st.rerun()

    if _email_running:
        @st.fragment(run_every=4)
        def _email_sidebar_status():
            t = get_task_for_job(DEFAULT_DB, "email_sync", 0)
            if t and t["status"] in ("queued", "running"):
                st.info("⏳ Syncing…")
            else:
                st.rerun()
        _email_sidebar_status()
    elif _email_task and _email_task["status"] == "completed":
        st.success(_email_task.get("error", "Done"))
    elif _email_task and _email_task["status"] == "failed":
        msg = _email_task.get("error", "")
        if "not configured" in msg.lower():
            st.error("Email not configured. Go to **Settings → Email**.")
        else:
            st.error(f"Sync failed: {msg}")

# ── Constants ─────────────────────────────────────────────────────────────────
STAGE_LABELS = {
    "phone_screen": "📞 Phone Screen",
    "interviewing":  "🎯 Interviewing",
    "offer":         "📜 Offer / Hired",
}
STAGE_NEXT = {
    "survey":       "phone_screen",
    "applied":      "phone_screen",
    "phone_screen": "interviewing",
    "interviewing": "offer",
    "offer":        "hired",
}
STAGE_NEXT_LABEL = {
    "survey":       "📞 Phone Screen",
    "applied":      "📞 Phone Screen",
    "phone_screen": "🎯 Interviewing",
    "interviewing": "📜 Offer",
    "offer":        "🎉 Hired",
}

# ── Data ──────────────────────────────────────────────────────────────────────
jobs_by_stage = get_interview_jobs(DEFAULT_DB)

# ── Helpers ───────────────────────────────────────────────────────────────────
def _days_ago(date_str: str | None) -> str:
    if not date_str:
        return "—"
    try:
        d = date.fromisoformat(date_str[:10])
        delta = (date.today() - d).days
        if delta == 0:
            return "today"
        if delta == 1:
            return "yesterday"
        return f"{delta}d ago"
    except Exception:
        return date_str[:10]

@st.dialog("🔬 Company Research", width="large")
def _research_modal(job: dict) -> None:
    job_id = job["id"]
    st.caption(f"**{job.get('company')}** — {job.get('title')}")
    research = get_research(DEFAULT_DB, job_id=job_id)
    task = get_task_for_job(DEFAULT_DB, "company_research", job_id)
    running = task and task["status"] in ("queued", "running")

    if running:
        task_stage = (task.get("stage") or "")
        lbl = "Queued…" if task["status"] == "queued" else (task_stage or "Generating…")
        st.info(f"⏳ {lbl}")
    elif research:
        scrape_used = research.get("scrape_used")
        if not scrape_used:
            import socket as _sock
            _searxng_up = False
            try:
                with _sock.create_connection(("127.0.0.1", 8888), timeout=1):
                    _searxng_up = True
            except OSError:
                pass
            if _searxng_up:
                st.warning(
                    "⚠️ This brief was generated without live web data and may contain "
                    "inaccuracies. SearXNG is now available — re-run to get verified facts."
                )
                if st.button("🔄 Re-run with live data", key=f"modal_rescrape_{job_id}", type="primary"):
                    submit_task(DEFAULT_DB, "company_research", job_id)
                    st.rerun()
                st.divider()
            else:
                st.warning(
                    "⚠️ Generated without live web data (SearXNG was offline). "
                    "Key facts like CEO, investors, and founding date may be hallucinated — "
                    "verify before the call. Start SearXNG in Settings → Services to re-run."
                )
                st.divider()
        st.caption(
            f"Generated {research.get('generated_at', '')} "
            f"{'· web data used ✓' if scrape_used else '· LLM knowledge only'}"
        )
        st.markdown(research["raw_output"])
        if st.button("🔄 Refresh", key=f"modal_regen_{job_id}", disabled=bool(running)):
            submit_task(DEFAULT_DB, "company_research", job_id)
            st.rerun()
    else:
        st.info("No research brief yet.")
        if task and task["status"] == "failed":
            st.error(f"Last attempt failed: {task.get('error', '')}")
        if st.button("🔬 Generate now", key=f"modal_gen_{job_id}"):
            submit_task(DEFAULT_DB, "company_research", job_id)
            st.rerun()


@st.dialog("📧 Email History", width="large")
def _email_modal(job: dict) -> None:
    job_id = job["id"]
    st.caption(f"**{job.get('company')}** — {job.get('title')}")
    contacts = get_contacts(DEFAULT_DB, job_id=job_id)

    if not contacts:
        st.info("No emails logged yet. Use the form below to add one.")
    else:
        for c in contacts:
            icon = "📥" if c["direction"] == "inbound" else "📤"
            st.markdown(
                f"{icon} **{c.get('subject') or '(no subject)'}** "
                f"· _{c.get('received_at', '')[:10]}_"
            )
            if c.get("from_addr"):
                st.caption(f"From: {c['from_addr']}")
            if c.get("body"):
                st.text(c["body"][:500] + ("…" if len(c["body"]) > 500 else ""))
            st.divider()

        inbound = [c for c in contacts if c["direction"] == "inbound"]
        if inbound:
            last = inbound[-1]
            if st.button("✍️ Draft reply", key=f"modal_draft_{job_id}"):
                with st.spinner("Drafting…"):
                    try:
                        from scripts.llm_router import complete
                        _persona = (
                            f"{_name} is a {_profile.career_summary[:120] if _profile and _profile.career_summary else 'professional'}"
                        )
                        draft = complete(
                            prompt=(
                                f"Draft a professional, warm reply to this email.\n\n"
                                f"From: {last.get('from_addr', '')}\n"
                                f"Subject: {last.get('subject', '')}\n\n"
                                f"{last.get('body', '')}\n\n"
                                f"Context: {_persona} applying for "
                                f"{job.get('title')} at {job.get('company')}."
                            ),
                            system=(
                                f"You are {_name}'s professional email assistant. "
                                "Write concise, warm, and professional replies in their voice. "
                                "Keep it to 3–5 sentences unless more is needed."
                            ),
                        )
                        st.session_state[f"modal_draft_text_{job_id}"] = draft
                        st.rerun()
                    except Exception as e:
                        st.error(f"Draft failed: {e}")

            if f"modal_draft_text_{job_id}" in st.session_state:
                st.text_area(
                    "Draft (edit before sending)",
                    value=st.session_state[f"modal_draft_text_{job_id}"],
                    height=160,
                    key=f"modal_draft_area_{job_id}",
                )

    st.divider()
    st.markdown("**Log a contact**")
    with st.form(key=f"contact_form_modal_{job_id}", clear_on_submit=True):
        col_a, col_b = st.columns(2)
        direction = col_a.radio(
            "Direction", ["inbound", "outbound"],
            horizontal=True, key=f"dir_modal_{job_id}",
        )
        recv_at = col_b.text_input(
            "Date (YYYY-MM-DD)", value=str(date.today()), key=f"recv_modal_{job_id}"
        )
        subject = st.text_input("Subject", key=f"subj_modal_{job_id}")
        from_addr = st.text_input("From", key=f"from_modal_{job_id}")
        body_text = st.text_area("Body / notes", height=80, key=f"body_modal_{job_id}")
        if st.form_submit_button("📧 Save contact"):
            add_contact(
                DEFAULT_DB, job_id=job_id,
                direction=direction, subject=subject,
                from_addr=from_addr, body=body_text, received_at=recv_at,
            )
            st.rerun()

def _render_card(job: dict, stage: str, compact: bool = False) -> None:
    """Render a single job card appropriate for the given stage."""
    job_id = job["id"]
    contacts = get_contacts(DEFAULT_DB, job_id=job_id)
    last_contact = contacts[-1] if contacts else None

    with st.container(border=True):
        st.markdown(f"**{job.get('company', '?')}**")
        st.caption(job.get("title", ""))

        col_a, col_b = st.columns(2)
        col_a.caption(f"Applied: {_days_ago(job.get('applied_at'))}")
        if last_contact:
            col_b.caption(f"Last contact: {_days_ago(last_contact.get('received_at'))}")

        # Interview date picker (phone_screen / interviewing stages)
        if stage in ("phone_screen", "interviewing"):
            current_idate = job.get("interview_date") or ""
            with st.form(key=f"idate_form_{job_id}"):
                new_date = st.date_input(
                    "Interview date",
                    value=date.fromisoformat(current_idate) if current_idate else None,
                    key=f"idate_{job_id}",
                    format="YYYY-MM-DD",
                )
                if st.form_submit_button("📅 Save date"):
                    set_interview_date(DEFAULT_DB, job_id=job_id, date_str=str(new_date))
                    st.success("Saved!")
                    st.rerun()

        if not compact:
            if stage in ("applied", "phone_screen", "interviewing"):
                signals = get_unread_stage_signals(DEFAULT_DB, job_id=job_id)
                if signals:
                    sig = signals[-1]
                    _SIGNAL_TO_STAGE = {
                        "interview_scheduled": ("phone_screen", "📞 Phone Screen"),
                        "positive_response":   ("phone_screen", "📞 Phone Screen"),
                        "offer_received":      ("offer",        "📜 Offer"),
                        "survey_received":     ("survey",       "📋 Survey"),
                    }
                    target_stage, target_label = _SIGNAL_TO_STAGE.get(
                        sig["stage_signal"], (None, None)
                    )
                    with st.container(border=True):
                        st.caption(
                            f"💡 Email suggests: **{sig['stage_signal'].replace('_', ' ')}**  \n"
                            f"_{sig.get('subject', '')}_ · {(sig.get('received_at') or '')[:10]}"
                        )
                        b1, b2 = st.columns(2)
                        if sig["stage_signal"] == "rejected":
                            if b1.button("✗ Reject", key=f"sig_rej_{sig['id']}",
                                         use_container_width=True):
                                reject_at_stage(DEFAULT_DB, job_id=job_id, rejection_stage=stage)
                                dismiss_stage_signal(DEFAULT_DB, sig["id"])
                                st.rerun(scope="app")
                        elif target_stage and b1.button(
                            f"→ {target_label}", key=f"sig_adv_{sig['id']}",
                            use_container_width=True, type="primary",
                        ):
                            if target_stage == "phone_screen" and stage == "applied":
                                advance_to_stage(DEFAULT_DB, job_id=job_id, stage="phone_screen")
                                submit_task(DEFAULT_DB, "company_research", job_id)
                            elif target_stage:
                                advance_to_stage(DEFAULT_DB, job_id=job_id, stage=target_stage)
                            dismiss_stage_signal(DEFAULT_DB, sig["id"])
                            st.rerun(scope="app")
                        if b2.button("Dismiss", key=f"sig_dis_{sig['id']}",
                                     use_container_width=True):
                            dismiss_stage_signal(DEFAULT_DB, sig["id"])
                            st.rerun()

            # Advance / Reject buttons
            next_stage = STAGE_NEXT.get(stage)
            c1, c2 = st.columns(2)
            if next_stage:
                next_label = STAGE_NEXT_LABEL.get(stage, next_stage)
                if c1.button(
                    f"→ {next_label}", key=f"adv_{job_id}",
                    use_container_width=True, type="primary",
                ):
                    advance_to_stage(DEFAULT_DB, job_id=job_id, stage=next_stage)
                    if next_stage == "phone_screen":
                        submit_task(DEFAULT_DB, "company_research", job_id)
                    st.rerun(scope="app")  # full rerun — card must appear in new column

            if c2.button(
                "✗ Reject", key=f"rej_{job_id}",
                use_container_width=True,
            ):
                reject_at_stage(DEFAULT_DB, job_id=job_id, rejection_stage=stage)
                st.rerun()  # fragment-scope rerun — card disappears without scroll-to-top

            if job.get("url"):
                st.link_button("Open listing ↗", job["url"], use_container_width=True)

            if stage in ("phone_screen", "interviewing", "offer"):
                if st.button(
                    "📋 Open Prep Sheet", key=f"prep_{job_id}",
                    use_container_width=True,
                    help="Open the Interview Prep page for this job",
                ):
                    st.session_state["prep_job_id"] = job_id
                    st.switch_page("pages/6_Interview_Prep.py")

            # Detail modals — full-width overlays replace narrow inline expanders
            if stage in ("phone_screen", "interviewing", "offer"):
                mc1, mc2 = st.columns(2)
                if mc1.button("🔬 Research", key=f"res_btn_{job_id}", use_container_width=True):
                    _research_modal(job)
                if mc2.button("📧 Emails", key=f"email_btn_{job_id}", use_container_width=True):
                    _email_modal(job)
            else:
                if st.button("📧 Emails", key=f"email_btn_{job_id}", use_container_width=True):
                    _email_modal(job)

# ── Fragment wrappers — keep scroll position on card actions ─────────────────
@st.fragment
def _card_fragment(job_id: int, stage: str) -> None:
    """Re-fetches the job on each fragment rerun; renders nothing if moved/rejected."""
    job = get_job_by_id(DEFAULT_DB, job_id)
    if job is None or job.get("status") != stage:
        return
    _render_card(job, stage)


@st.fragment
def _pre_kanban_row_fragment(job_id: int) -> None:
    """Pre-kanban compact row for applied and survey-stage jobs."""
    job = get_job_by_id(DEFAULT_DB, job_id)
    if job is None or job.get("status") not in ("applied", "survey"):
        return
    stage = job["status"]
    contacts = get_contacts(DEFAULT_DB, job_id=job_id)
    last_contact = contacts[-1] if contacts else None

    with st.container(border=True):
        left, mid, right = st.columns([3, 2, 2])
        badge = " 📋 **Survey**" if stage == "survey" else ""
        left.markdown(f"**{job.get('company')}** — {job.get('title', '')}{badge}")
        left.caption(f"Applied: {_days_ago(job.get('applied_at'))}")

        with mid:
            if last_contact:
                st.caption(f"Last contact: {_days_ago(last_contact.get('received_at'))}")
            if st.button("📧 Emails", key=f"email_pre_{job_id}", use_container_width=True):
                _email_modal(job)

            # Stage signal hint (email-detected next steps)
            signals = get_unread_stage_signals(DEFAULT_DB, job_id=job_id)
            if signals:
                sig = signals[-1]
                _SIGNAL_TO_STAGE = {
                    "interview_scheduled": ("phone_screen", "📞 Phone Screen"),
                    "positive_response":   ("phone_screen", "📞 Phone Screen"),
                    "offer_received":      ("offer",        "📜 Offer"),
                    "survey_received":     ("survey",       "📋 Survey"),
                }
                target_stage, target_label = _SIGNAL_TO_STAGE.get(
                    sig["stage_signal"], (None, None)
                )
                with st.container(border=True):
                    st.caption(
                        f"💡 **{sig['stage_signal'].replace('_', ' ')}**  \n"
                        f"_{sig.get('subject', '')}_ · {(sig.get('received_at') or '')[:10]}"
                    )
                    s1, s2 = st.columns(2)
                    if target_stage and s1.button(
                        f"→ {target_label}", key=f"sig_adv_pre_{sig['id']}",
                        use_container_width=True, type="primary",
                    ):
                        if target_stage == "phone_screen":
                            advance_to_stage(DEFAULT_DB, job_id=job_id, stage="phone_screen")
                            submit_task(DEFAULT_DB, "company_research", job_id)
                        else:
                            advance_to_stage(DEFAULT_DB, job_id=job_id, stage=target_stage)
                        dismiss_stage_signal(DEFAULT_DB, sig["id"])
                        st.rerun(scope="app")
                    if s2.button("Dismiss", key=f"sig_dis_pre_{sig['id']}",
                                 use_container_width=True):
                        dismiss_stage_signal(DEFAULT_DB, sig["id"])
                        st.rerun()

        with right:
            if st.button(
                "→ 📞 Phone Screen", key=f"adv_pre_{job_id}",
                use_container_width=True, type="primary",
            ):
                advance_to_stage(DEFAULT_DB, job_id=job_id, stage="phone_screen")
                submit_task(DEFAULT_DB, "company_research", job_id)
                st.rerun(scope="app")
            col_a, col_b = st.columns(2)
            if stage == "applied" and col_a.button(
                "📋 Survey", key=f"to_survey_{job_id}", use_container_width=True,
            ):
                advance_to_stage(DEFAULT_DB, job_id=job_id, stage="survey")
                st.rerun(scope="app")
            if col_b.button("✗ Reject", key=f"rej_pre_{job_id}", use_container_width=True):
                reject_at_stage(DEFAULT_DB, job_id=job_id, rejection_stage=stage)
                st.rerun()


@st.fragment
def _hired_card_fragment(job_id: int) -> None:
    """Compact hired job card — shown in the Offer/Hired column."""
    job = get_job_by_id(DEFAULT_DB, job_id)
    if job is None or job.get("status") != "hired":
        return
    with st.container(border=True):
        st.markdown(f"✅ **{job.get('company', '?')}**")
        st.caption(job.get("title", ""))
        st.caption(f"Hired {_days_ago(job.get('hired_at'))}")


# ── Stats bar ─────────────────────────────────────────────────────────────────
c1, c2, c3, c4, c5, c6 = st.columns(6)
c1.metric("Applied",      len(jobs_by_stage.get("applied", [])))
c2.metric("Survey",       len(jobs_by_stage.get("survey", [])))
c3.metric("Phone Screen", len(jobs_by_stage.get("phone_screen", [])))
c4.metric("Interviewing", len(jobs_by_stage.get("interviewing", [])))
c5.metric("Offer/Hired",  len(jobs_by_stage.get("offer", [])) + len(jobs_by_stage.get("hired", [])))
c6.metric("Rejected",     len(jobs_by_stage.get("rejected", [])))

st.divider()

# ── Pre-kanban: Applied + Survey ───────────────────────────────────────────────
applied_jobs = jobs_by_stage.get("applied", [])
survey_jobs  = jobs_by_stage.get("survey", [])
pre_kanban   = survey_jobs + applied_jobs  # survey shown first

if pre_kanban:
    st.subheader(f"📋 Pre-pipeline ({len(pre_kanban)})")
    st.caption(
        "Move a job to **Phone Screen** once you receive an outreach. "
        "A company research brief will be auto-generated to help you prepare."
    )
    for job in pre_kanban:
        _pre_kanban_row_fragment(job["id"])
    st.divider()

# ── Kanban columns ─────────────────────────────────────────────────────────────
kanban_stages = ["phone_screen", "interviewing", "offer"]
cols = st.columns(len(kanban_stages))

for col, stage in zip(cols, kanban_stages):
    with col:
        stage_jobs = jobs_by_stage.get(stage, [])
        hired_jobs = jobs_by_stage.get("hired", []) if stage == "offer" else []
        all_col_jobs = stage_jobs + hired_jobs
        st.markdown(f"### {STAGE_LABELS[stage]}")
        st.caption(f"{len(all_col_jobs)} job{'s' if len(all_col_jobs) != 1 else ''}")
        st.divider()

        if not all_col_jobs:
            st.caption("_Empty_")
        else:
            for job in stage_jobs:
                _card_fragment(job["id"], stage)
            for job in hired_jobs:
                _hired_card_fragment(job["id"])

st.divider()

# ── Rejected log + analytics ───────────────────────────────────────────────────
rejected_jobs = jobs_by_stage.get("rejected", [])
if rejected_jobs:
    with st.expander(f"❌ Rejected ({len(rejected_jobs)})", expanded=False):
        # Stage breakdown
        stage_counts = Counter(
            j.get("rejection_stage") or "unknown" for j in rejected_jobs
        )
        st.caption(
            "Rejection by stage: "
            + " · ".join(f"**{k}**: {v}" for k, v in stage_counts.most_common())
        )

        # Rejection rate timeline (simple)
        if len(rejected_jobs) > 1:
            by_month: dict[str, int] = {}
            for j in rejected_jobs:
                mo = (j.get("applied_at") or "")[:7]
                if mo:
                    by_month[mo] = by_month.get(mo, 0) + 1
            if by_month:
                import pandas as pd
                chart_data = pd.DataFrame(
                    list(by_month.items()), columns=["Month", "Rejections"]
                ).sort_values("Month")
                st.bar_chart(chart_data.set_index("Month"))

        st.divider()
        for job in rejected_jobs:
            r_stage = job.get("rejection_stage") or "unknown"
            company = job.get("company") or "?"
            title = job.get("title") or ""
            applied = _days_ago(job.get("applied_at"))
            st.markdown(
                f"**{company}** — {title}  "
                f"· rejected at _**{r_stage}**_ · applied {applied}"
            )
