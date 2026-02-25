# app/pages/1_Job_Review.py
"""
Job Review — browse listings, approve/reject inline, generate cover letters,
and mark approved jobs as applied.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import streamlit as st
from scripts.db import (
    DEFAULT_DB, init_db, get_jobs_by_status, update_job_status,
    update_cover_letter, mark_applied, get_email_leads,
)

st.title("📋 Job Review")

init_db(DEFAULT_DB)

_email_leads = get_email_leads(DEFAULT_DB)

# ── Sidebar filters ────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("Filters")
    show_status = st.selectbox(
        "Show",
        ["pending", "approved", "applied", "rejected", "synced"],
        index=0,
    )
    remote_only = st.checkbox("Remote only", value=False)
    min_score = st.slider("Min match score", 0, 100, 0)

    st.header("Sort")
    sort_by = st.selectbox(
        "Sort by",
        ["Date Found (newest)", "Date Found (oldest)", "Match Score (high→low)", "Match Score (low→high)", "Company A–Z", "Title A–Z"],
        index=0,
    )

jobs = get_jobs_by_status(DEFAULT_DB, show_status)

if remote_only:
    jobs = [j for j in jobs if j.get("is_remote")]
if min_score > 0:
    jobs = [j for j in jobs if (j.get("match_score") or 0) >= min_score]

# Apply sort
if sort_by == "Date Found (newest)":
    jobs = sorted(jobs, key=lambda j: j.get("date_found") or "", reverse=True)
elif sort_by == "Date Found (oldest)":
    jobs = sorted(jobs, key=lambda j: j.get("date_found") or "")
elif sort_by == "Match Score (high→low)":
    jobs = sorted(jobs, key=lambda j: j.get("match_score") or 0, reverse=True)
elif sort_by == "Match Score (low→high)":
    jobs = sorted(jobs, key=lambda j: j.get("match_score") or 0)
elif sort_by == "Company A–Z":
    jobs = sorted(jobs, key=lambda j: (j.get("company") or "").lower())
elif sort_by == "Title A–Z":
    jobs = sorted(jobs, key=lambda j: (j.get("title") or "").lower())

if not jobs:
    st.info(f"No {show_status} jobs matching your filters.")
    st.stop()

st.caption(f"Showing {len(jobs)} {show_status} job{'s' if len(jobs) != 1 else ''}")
st.divider()

if show_status == "pending" and _email_leads:
    st.subheader(f"📧 Email Leads ({len(_email_leads)})")
    st.caption(
        "Inbound recruiter emails not yet matched to a scraped listing. "
        "Approve to add to Job Review; Reject to dismiss."
    )
    for lead in _email_leads:
        lead_id = lead["id"]
        with st.container(border=True):
            left_l, right_l = st.columns([7, 3])
            with left_l:
                st.markdown(f"**{lead['title']}** — {lead['company']}")
                badge_cols = st.columns(4)
                badge_cols[0].caption("📧 Email Lead")
                badge_cols[1].caption(f"📅 {lead.get('date_found', '')}")
                if lead.get("description"):
                    with st.expander("📄 Email excerpt", expanded=False):
                        st.text(lead["description"][:500])
            with right_l:
                if st.button("✅ Approve", key=f"el_approve_{lead_id}",
                             type="primary", use_container_width=True):
                    update_job_status(DEFAULT_DB, [lead_id], "approved")
                    st.rerun()
                if st.button("❌ Reject", key=f"el_reject_{lead_id}",
                             use_container_width=True):
                    update_job_status(DEFAULT_DB, [lead_id], "rejected")
                    st.rerun()
    st.divider()

# Filter email leads out of the main pending list (already shown above)
if show_status == "pending":
    jobs = [j for j in jobs if j.get("source") != "email"]

# ── Job cards ──────────────────────────────────────────────────────────────────
for job in jobs:
    job_id = job["id"]

    score = job.get("match_score")
    if score is None:
        score_badge = "⬜ No score"
    elif score >= 70:
        score_badge = f"🟢 {score:.0f}%"
    elif score >= 40:
        score_badge = f"🟡 {score:.0f}%"
    else:
        score_badge = f"🔴 {score:.0f}%"

    remote_badge = "🌐 Remote" if job.get("is_remote") else "🏢 On-site"
    src = (job.get("source") or "").lower()
    source_badge = f"🤖 {src.title()}" if src == "linkedin" else f"👤 {src.title() or 'Manual'}"

    with st.container(border=True):
        left, right = st.columns([7, 3])

        # ── Left: job info ─────────────────────────────────────────────────────
        with left:
            st.markdown(f"**{job['title']}** — {job['company']}")

            badge_cols = st.columns(4)
            badge_cols[0].caption(remote_badge)
            badge_cols[1].caption(source_badge)
            badge_cols[2].caption(score_badge)
            badge_cols[3].caption(f"📅 {job.get('date_found', '')}")

            if job.get("keyword_gaps"):
                st.caption(f"**Keyword gaps:** {job['keyword_gaps']}")

            # Cover letter expander (approved view)
            if show_status == "approved":
                _cl_key = f"cl_{job_id}"
                if _cl_key not in st.session_state:
                    st.session_state[_cl_key] = job.get("cover_letter") or ""

                cl_exists = bool(st.session_state[_cl_key])
                with st.expander("📝 Cover Letter", expanded=cl_exists):
                    gen_label = "Regenerate" if cl_exists else "Generate Cover Letter"
                    if st.button(gen_label, key=f"gen_{job_id}"):
                        with st.spinner("Generating via LLM…"):
                            try:
                                from scripts.generate_cover_letter import generate as _gen
                                st.session_state[_cl_key] = _gen(
                                    job.get("title", ""),
                                    job.get("company", ""),
                                    job.get("description", ""),
                                )
                                st.rerun()
                            except Exception as e:
                                st.error(f"Generation failed: {e}")

                    st.text_area(
                        "cover_letter_edit",
                        key=_cl_key,
                        height=300,
                        label_visibility="collapsed",
                    )
                    save_col, _ = st.columns([2, 5])
                    if save_col.button("💾 Save draft", key=f"save_cl_{job_id}"):
                        update_cover_letter(DEFAULT_DB, job_id, st.session_state[_cl_key])
                        st.success("Saved!")

            # Applied date + cover letter preview (applied/synced)
            if show_status in ("applied", "synced") and job.get("applied_at"):
                st.caption(f"✅ Applied: {job['applied_at']}")
            if show_status in ("applied", "synced") and job.get("cover_letter"):
                with st.expander("📝 Cover Letter (sent)"):
                    st.text(job["cover_letter"])

        # ── Right: actions ─────────────────────────────────────────────────────
        with right:
            if job.get("url"):
                st.link_button("View listing →", job["url"], use_container_width=True)
            if job.get("salary"):
                st.caption(f"💰 {job['salary']}")

            if show_status == "pending":
                if st.button("✅ Approve", key=f"approve_{job_id}",
                             type="primary", use_container_width=True):
                    update_job_status(DEFAULT_DB, [job_id], "approved")
                    st.rerun()
                if st.button("❌ Reject", key=f"reject_{job_id}",
                             use_container_width=True):
                    update_job_status(DEFAULT_DB, [job_id], "rejected")
                    st.rerun()

            elif show_status == "approved":
                if st.button("🚀 Apply →", key=f"apply_page_{job_id}",
                             type="primary", use_container_width=True):
                    st.session_state["apply_job_id"] = job_id
                    st.switch_page("pages/4_Apply.py")
                if st.button("✅ Mark Applied", key=f"applied_{job_id}",
                             use_container_width=True):
                    cl_text = st.session_state.get(f"cl_{job_id}", "")
                    if cl_text:
                        update_cover_letter(DEFAULT_DB, job_id, cl_text)
                    mark_applied(DEFAULT_DB, [job_id])
                    st.rerun()
