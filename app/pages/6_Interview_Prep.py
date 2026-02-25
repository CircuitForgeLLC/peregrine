# app/pages/6_Interview_Prep.py
"""
Interview Prep — a clean, glanceable reference you can keep open during a call.

Left panel  : talking points, company brief, CEO info, practice Q&A
Right panel : job description, email / contact history, cover letter snippet
"""
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import streamlit as st

from scripts.db import (
    DEFAULT_DB, init_db,
    get_interview_jobs, get_contacts, get_research,
    get_task_for_job,
)
from scripts.task_runner import submit_task

init_db(DEFAULT_DB)

# ── Job selection ─────────────────────────────────────────────────────────────
jobs_by_stage = get_interview_jobs(DEFAULT_DB)
active_stages = ["phone_screen", "interviewing", "offer"]
active_jobs = [
    j for stage in active_stages
    for j in jobs_by_stage.get(stage, [])
]

if not active_jobs:
    st.title("📋 Interview Prep")
    st.info(
        "No active interviews found. "
        "Move a job to **Phone Screen** on the Interviews page first."
    )
    st.stop()

# Allow pre-selecting via session state (e.g., from Interviews page)
preselect_id = st.session_state.pop("prep_job_id", None)
job_options = {
    j["id"]: f"{j['title']} — {j['company']} ({j['status'].replace('_', ' ').title()})"
    for j in active_jobs
}
ids = list(job_options.keys())
default_idx = ids.index(preselect_id) if preselect_id in ids else 0

selected_id = st.selectbox(
    "Job",
    options=ids,
    format_func=lambda x: job_options[x],
    index=default_idx,
    label_visibility="collapsed",
)
job = next(j for j in active_jobs if j["id"] == selected_id)

# ── Header bar ────────────────────────────────────────────────────────────────
stage_label = job["status"].replace("_", " ").title()
idate = job.get("interview_date")
countdown = ""
if idate:
    try:
        delta = (date.fromisoformat(idate) - date.today()).days
        if delta == 0:
            countdown = "  🔴 **TODAY**"
        elif delta == 1:
            countdown = "  🟡 **TOMORROW**"
        elif delta > 0:
            countdown = f"  🟢 in {delta} days"
        else:
            countdown = f"  (was {abs(delta)}d ago)"
    except Exception:
        countdown = ""

st.title(f"📋 {job.get('company')} — {job.get('title')}")
st.caption(
    f"Stage: **{stage_label}**"
    + (f"  ·  Interview: {idate}{countdown}" if idate else "")
    + (f"  ·  Applied: {job.get('applied_at', '')[:10]}" if job.get("applied_at") else "")
)

if job.get("url"):
    st.link_button("Open job listing ↗", job["url"])

st.divider()

# ── Two-column layout ─────────────────────────────────────────────────────────
col_prep, col_context = st.columns([2, 3])

# ════════════════════════════════════════════════
#  LEFT — prep materials
# ════════════════════════════════════════════════
with col_prep:

    research = get_research(DEFAULT_DB, job_id=selected_id)

    # Refresh / generate research
    _res_task = get_task_for_job(DEFAULT_DB, "company_research", selected_id)
    _res_running = _res_task and _res_task["status"] in ("queued", "running")

    if not research:
        if not _res_running:
            st.warning("No research brief yet for this job.")
            if _res_task and _res_task["status"] == "failed":
                st.error(f"Last attempt failed: {_res_task.get('error', '')}")
            if st.button("🔬 Generate research brief", type="primary", use_container_width=True):
                submit_task(DEFAULT_DB, "company_research", selected_id)
                st.rerun()

        if _res_running:
            @st.fragment(run_every=3)
            def _res_status_initial():
                t = get_task_for_job(DEFAULT_DB, "company_research", selected_id)
                if t and t["status"] in ("queued", "running"):
                    stage = t.get("stage") or ""
                    lbl = "Queued…" if t["status"] == "queued" else (stage or "Generating… this may take 30–60 seconds")
                    st.info(f"⏳ {lbl}")
                else:
                    st.rerun()
            _res_status_initial()

        st.stop()
    else:
        generated_at = research.get("generated_at", "")
        col_ts, col_btn = st.columns([3, 1])
        col_ts.caption(f"Research generated: {generated_at}")
        if col_btn.button("🔄 Refresh", use_container_width=True, disabled=bool(_res_running)):
            submit_task(DEFAULT_DB, "company_research", selected_id)
            st.rerun()

        if _res_running:
            @st.fragment(run_every=3)
            def _res_status_refresh():
                t = get_task_for_job(DEFAULT_DB, "company_research", selected_id)
                if t and t["status"] in ("queued", "running"):
                    stage = t.get("stage") or ""
                    lbl = "Queued…" if t["status"] == "queued" else (stage or "Refreshing research…")
                    st.info(f"⏳ {lbl}")
                else:
                    st.rerun()
            _res_status_refresh()
        elif _res_task and _res_task["status"] == "failed":
            st.error(f"Refresh failed: {_res_task.get('error', '')}")

    st.divider()

    # ── Talking points (top — most useful during a call) ──────────────────────
    st.subheader("🎯 Talking Points")
    tp = (research.get("talking_points") or "").strip()
    if tp:
        st.markdown(tp)
    else:
        st.caption("_No talking points extracted — try regenerating._")

    st.divider()

    # ── Company brief ─────────────────────────────────────────────────────────
    st.subheader("🏢 Company Overview")
    st.markdown(research.get("company_brief", "_—_"))

    st.divider()

    # ── Leadership brief ──────────────────────────────────────────────────────
    st.subheader("👤 Leadership & Culture")
    st.markdown(research.get("ceo_brief", "_—_"))

    st.divider()

    # ── Tech Stack & Product ───────────────────────────────────────────────────
    tech = (research.get("tech_brief") or "").strip()
    if tech:
        st.subheader("⚙️ Tech Stack & Product")
        st.markdown(tech)
        st.divider()

    # ── Funding & Market Position ──────────────────────────────────────────────
    funding = (research.get("funding_brief") or "").strip()
    if funding:
        st.subheader("💰 Funding & Market Position")
        st.markdown(funding)
        st.divider()

    # ── Red Flags & Watch-outs ────────────────────────────────────────────────
    red = (research.get("red_flags") or "").strip()
    if red and "no significant red flags" not in red.lower():
        st.subheader("⚠️ Red Flags & Watch-outs")
        st.warning(red)
        st.divider()

    # ── Inclusion & Accessibility ─────────────────────────────────────────────
    access = (research.get("accessibility_brief") or "").strip()
    if access:
        st.subheader("♿ Inclusion & Accessibility")
        st.caption("For your personal evaluation — not disclosed in any application.")
        st.markdown(access)
        st.divider()

    # ── Practice Q&A (collapsible — use before the call) ─────────────────────
    with st.expander("🎤 Practice Q&A (pre-call prep)", expanded=False):
        st.caption(
            "The LLM will play the interviewer. Type your answers below. "
            "Use this before the call to warm up."
        )

        qa_key = f"qa_{selected_id}"
        if qa_key not in st.session_state:
            st.session_state[qa_key] = []

        if st.button("🔄 Start / Reset session", key=f"qa_reset_{selected_id}"):
            st.session_state[qa_key] = []
            st.rerun()

        # Display history
        for msg in st.session_state[qa_key]:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])

        # Initial question if session is empty
        if not st.session_state[qa_key]:
            with st.spinner("Setting up your mock interview…"):
                try:
                    from scripts.llm_router import complete
                    opening = complete(
                        prompt=(
                            f"Start a mock phone screen for the {job.get('title')} "
                            f"role at {job.get('company')}. Ask your first question. "
                            f"Keep it realistic and concise."
                        ),
                        system=(
                            f"You are a recruiter at {job.get('company')} conducting "
                            f"a phone screen for the {job.get('title')} role. "
                            f"Ask one question at a time. After Meghan answers, give "
                            f"brief feedback (1–2 sentences), then ask your next question. "
                            f"Be professional but warm."
                        ),
                    )
                    st.session_state[qa_key] = [{"role": "assistant", "content": opening}]
                    st.rerun()
                except Exception as e:
                    st.error(f"LLM error: {e}")

        # Answer input
        answer = st.chat_input("Your answer…", key=f"qa_input_{selected_id}")
        if answer and st.session_state[qa_key]:
            history = st.session_state[qa_key]
            history.append({"role": "user", "content": answer})

            messages = [
                {
                    "role": "system",
                    "content": (
                        f"You are a recruiter at {job.get('company')} conducting "
                        f"a phone screen for the {job.get('title')} role. "
                        f"Ask one question at a time. After Meghan answers, give "
                        f"brief feedback (1–2 sentences), then ask your next question."
                    ),
                }
            ] + history

            with st.spinner("…"):
                try:
                    from scripts.llm_router import LLMRouter
                    router = LLMRouter()
                    # Build prompt from history for single-turn backends
                    convo = "\n\n".join(
                        f"{'Interviewer' if m['role'] == 'assistant' else 'Meghan'}: {m['content']}"
                        for m in history
                    )
                    response = router.complete(
                        prompt=convo + "\n\nInterviewer:",
                        system=messages[0]["content"],
                    )
                    history.append({"role": "assistant", "content": response})
                    st.session_state[qa_key] = history
                    st.rerun()
                except Exception as e:
                    st.error(f"Error: {e}")

# ════════════════════════════════════════════════
#  RIGHT — context / reference
# ════════════════════════════════════════════════
with col_context:

    tab_jd, tab_emails, tab_letter = st.tabs(
        ["📄 Job Description", "📧 Email History", "📝 Cover Letter"]
    )

    with tab_jd:
        score = job.get("match_score")
        if score is not None:
            badge = (
                f"🟢 {score:.0f}% match" if score >= 70 else
                f"🟡 {score:.0f}% match" if score >= 40 else
                f"🔴 {score:.0f}% match"
            )
            st.caption(badge)
        if job.get("keyword_gaps"):
            st.caption(f"**Gaps to address:** {job['keyword_gaps']}")
        st.markdown(job.get("description") or "_No description saved for this listing._")

    with tab_emails:
        contacts = get_contacts(DEFAULT_DB, job_id=selected_id)
        if not contacts:
            st.info("No contacts logged yet. Use the Interviews page to log emails.")
        else:
            for c in contacts:
                icon = "📥" if c["direction"] == "inbound" else "📤"
                recv = (c.get("received_at") or "")[:10]
                st.markdown(
                    f"{icon} **{c.get('subject') or '(no subject)'}** · _{recv}_"
                )
                if c.get("from_addr"):
                    st.caption(f"From: {c['from_addr']}")
                if c.get("body"):
                    st.text(c["body"][:500] + ("…" if len(c["body"]) > 500 else ""))
                st.divider()

            # Quick draft reply
            inbound = [c for c in contacts if c["direction"] == "inbound"]
            if inbound:
                last = inbound[-1]
                if st.button("✍️ Draft reply to last email"):
                    with st.spinner("Drafting…"):
                        try:
                            from scripts.llm_router import complete
                            draft = complete(
                                prompt=(
                                    f"Draft a professional, warm reply.\n\n"
                                    f"From: {last.get('from_addr', '')}\n"
                                    f"Subject: {last.get('subject', '')}\n\n"
                                    f"{last.get('body', '')}\n\n"
                                    f"Context: Meghan is a CS/TAM professional applying "
                                    f"for {job.get('title')} at {job.get('company')}."
                                ),
                                system=(
                                    "You are Meghan McCann's professional email assistant. "
                                    "Write concise, warm, and professional replies in her voice."
                                ),
                            )
                            st.session_state[f"draft_{selected_id}"] = draft
                        except Exception as e:
                            st.error(f"Draft failed: {e}")

                if f"draft_{selected_id}" in st.session_state:
                    st.text_area(
                        "Draft (edit before sending)",
                        value=st.session_state[f"draft_{selected_id}"],
                        height=180,
                    )

    with tab_letter:
        cl = (job.get("cover_letter") or "").strip()
        if cl:
            st.markdown(cl)
        else:
            st.info("No cover letter saved for this job.")

    st.divider()

    # ── Notes (freeform, stored in session only — not persisted to DB) ────────
    st.subheader("📝 Call Notes")
    st.caption("Notes are per-session only — copy anything important before navigating away.")
    st.text_area(
        "notes",
        placeholder="Type notes during or after the call…",
        height=200,
        key=f"notes_{selected_id}",
        label_visibility="collapsed",
    )
