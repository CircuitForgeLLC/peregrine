# app/pages/4_Apply.py
"""
Apply Workspace — side-by-side cover letter tools and job description.
Generates a PDF cover letter saved to the JobSearch docs folder.
"""
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import streamlit as st
import streamlit.components.v1 as components
import yaml

from scripts.user_profile import UserProfile

_USER_YAML = Path(__file__).parent.parent.parent / "config" / "user.yaml"
_profile = UserProfile(_USER_YAML) if UserProfile.exists(_USER_YAML) else None
_name = _profile.name if _profile else "Job Seeker"

from scripts.db import (
    DEFAULT_DB, init_db, get_jobs_by_status,
    update_cover_letter, mark_applied, update_job_status,
    get_task_for_job,
)
from scripts.task_runner import submit_task

DOCS_DIR = _profile.docs_dir if _profile else Path.home() / "Documents" / "JobSearch"
RESUME_YAML = Path(__file__).parent.parent.parent / "config" / "plain_text_resume.yaml"

st.title("🚀 Apply Workspace")

init_db(DEFAULT_DB)

# ── PDF generation ─────────────────────────────────────────────────────────────
def _make_cover_letter_pdf(job: dict, cover_letter: str, output_dir: Path) -> Path:
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.units import inch
    from reportlab.lib.colors import HexColor
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.enums import TA_LEFT
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable

    output_dir.mkdir(parents=True, exist_ok=True)
    company_safe = re.sub(r"[^a-zA-Z0-9]", "", job.get("company", "Company"))
    date_str = datetime.now().strftime("%Y-%m-%d")
    out_path = output_dir / f"CoverLetter_{company_safe}_{date_str}.pdf"

    doc = SimpleDocTemplate(
        str(out_path),
        pagesize=letter,
        leftMargin=inch, rightMargin=inch,
        topMargin=inch, bottomMargin=inch,
    )

    teal  = HexColor("#2DD4BF")
    dark  = HexColor("#0F172A")
    slate = HexColor("#64748B")

    name_style = ParagraphStyle(
        "Name", fontName="Helvetica-Bold", fontSize=22,
        textColor=teal, spaceAfter=6,
    )
    contact_style = ParagraphStyle(
        "Contact", fontName="Helvetica", fontSize=9,
        textColor=slate, spaceAfter=4,
    )
    date_style = ParagraphStyle(
        "Date", fontName="Helvetica", fontSize=11,
        textColor=dark, spaceBefore=16, spaceAfter=14,
    )
    body_style = ParagraphStyle(
        "Body", fontName="Helvetica", fontSize=11,
        textColor=dark, leading=16, spaceAfter=12, alignment=TA_LEFT,
    )

    display_name = _profile.name.upper() if _profile else "YOUR NAME"
    contact_line = " · ".join(filter(None, [
        _profile.email if _profile else "",
        _profile.phone if _profile else "",
        _profile.linkedin if _profile else "",
    ]))

    story = [
        Paragraph(display_name, name_style),
        Paragraph(contact_line, contact_style),
        HRFlowable(width="100%", thickness=1, color=teal, spaceBefore=8, spaceAfter=0),
        Paragraph(datetime.now().strftime("%B %d, %Y"), date_style),
    ]

    for para in cover_letter.strip().split("\n\n"):
        para = para.strip()
        if para:
            story.append(Paragraph(para.replace("\n", "<br/>"), body_style))

    story += [
        Spacer(1, 6),
        Paragraph(f"Warm regards,<br/><br/>{_profile.name if _profile else 'Your Name'}", body_style),
    ]

    doc.build(story)
    return out_path

# ── Application Q&A helper ─────────────────────────────────────────────────────
def _answer_question(job: dict, question: str) -> str:
    """Call the LLM to answer an application question in the user's voice.

    Uses research_fallback_order (claude_code → vllm → ollama_research)
    rather than the default cover-letter order — the fine-tuned cover letter
    model is not suited for answering general application questions.
    """
    from scripts.llm_router import LLMRouter
    router = LLMRouter()
    fallback = router.config.get("research_fallback_order") or router.config.get("fallback_order")
    description_snippet = (job.get("description") or "")[:1200].strip()
    _persona_summary = (
        _profile.career_summary[:200] if _profile and _profile.career_summary
        else "a professional with experience in their field"
    )
    prompt = f"""You are answering job application questions for {_name}.

Background:
{_persona_summary}

Role they're applying to: {job.get("title", "")} at {job.get("company", "")}
{f"Job description excerpt:{chr(10)}{description_snippet}" if description_snippet else ""}

Application Question:
{question}

Answer in {_name}'s voice — specific, warm, and confident. If the question specifies a word or character limit, respect it. Answer only the question with no preamble or sign-off."""
    return router.complete(prompt, fallback_order=fallback).strip()


# ── Copy-to-clipboard button ───────────────────────────────────────────────────
def _copy_btn(text: str, label: str = "📋 Copy", done: str = "✅ Copied!", height: int = 44) -> None:
    import json
    # Each components.html call renders in its own sandboxed iframe, so a fixed
    # element id is fine. json.dumps handles all special chars (quotes, newlines,
    # backslashes, etc.) — avoids the fragile inline-onclick escaping approach.
    components.html(
        f"""<button id="b"
            style="width:100%;background:#2DD4BF;color:#0F172A;border:none;
                   padding:6px 10px;border-radius:6px;cursor:pointer;
                   font-size:13px;font-weight:600">{label}</button>
        <script>
        document.getElementById('b').addEventListener('click', function() {{
            navigator.clipboard.writeText({json.dumps(text)});
            this.textContent = {json.dumps(done)};
            setTimeout(() => this.textContent = {json.dumps(label)}, 2000);
        }});
        </script>""",
        height=height,
    )

# ── Job selection ──────────────────────────────────────────────────────────────
approved = get_jobs_by_status(DEFAULT_DB, "approved")
if not approved:
    st.info("No approved jobs — head to Job Review to approve some listings first.")
    st.stop()

preselect_id = st.session_state.pop("apply_job_id", None)
job_options = {j["id"]: f"{j['title']} — {j['company']}" for j in approved}
ids = list(job_options.keys())
default_idx = ids.index(preselect_id) if preselect_id in ids else 0

selected_id = st.selectbox(
    "Job",
    options=ids,
    format_func=lambda x: job_options[x],
    index=default_idx,
    label_visibility="collapsed",
)
job = next(j for j in approved if j["id"] == selected_id)

st.divider()

# ── Two-column workspace ───────────────────────────────────────────────────────
col_tools, col_jd = st.columns([2, 3])

# ════════════════════════════════════════════════
#  RIGHT — job description
# ════════════════════════════════════════════════
with col_jd:
    score = job.get("match_score")
    score_badge = (
        "⬜ No score" if score is None else
        f"🟢 {score:.0f}%" if score >= 70 else
        f"🟡 {score:.0f}%" if score >= 40 else f"🔴 {score:.0f}%"
    )
    remote_badge = "🌐 Remote" if job.get("is_remote") else "🏢 On-site"
    src = (job.get("source") or "").lower()
    source_badge = f"🤖 {src.title()}" if src == "linkedin" else f"👤 {src.title() or 'Manual'}"

    st.subheader(job["title"])
    st.caption(
        f"**{job['company']}**  ·  {job.get('location', '')}  ·  "
        f"{remote_badge}  ·  {source_badge}  ·  {score_badge}"
    )
    if job.get("salary"):
        st.caption(f"💰 {job['salary']}")
    if job.get("keyword_gaps"):
        st.caption(f"**Gaps to address in letter:** {job['keyword_gaps']}")

    st.divider()
    st.markdown(job.get("description") or "_No description scraped for this listing._")

# ════════════════════════════════════════════════
#  LEFT — copy tools
# ════════════════════════════════════════════════
with col_tools:

    # ── Cover letter ──────────────────────────────
    st.subheader("📝 Cover Letter")

    _cl_key = f"cl_{selected_id}"
    if _cl_key not in st.session_state:
        st.session_state[_cl_key] = job.get("cover_letter") or ""

    _cl_task = get_task_for_job(DEFAULT_DB, "cover_letter", selected_id)
    _cl_running = _cl_task and _cl_task["status"] in ("queued", "running")

    if st.button("✨ Generate / Regenerate", use_container_width=True, disabled=bool(_cl_running)):
        submit_task(DEFAULT_DB, "cover_letter", selected_id)
        st.rerun()

    if _cl_running:
        @st.fragment(run_every=3)
        def _cl_status_fragment():
            t = get_task_for_job(DEFAULT_DB, "cover_letter", selected_id)
            if t and t["status"] in ("queued", "running"):
                lbl = "Queued…" if t["status"] == "queued" else "Generating via LLM…"
                st.info(f"⏳ {lbl}")
            else:
                st.rerun()  # full page rerun — reloads cover letter from DB
        _cl_status_fragment()
    elif _cl_task and _cl_task["status"] == "failed":
        st.error(f"Generation failed: {_cl_task.get('error', 'unknown error')}")

    # Refresh session state only when a NEW task has just completed — not on every rerun.
    # Without this guard, every Save Draft click would overwrite the edited text with the
    # old DB value before cl_text could be captured.
    _cl_loaded_key = f"cl_loaded_{selected_id}"
    if not _cl_running and _cl_task and _cl_task["status"] == "completed":
        if st.session_state.get(_cl_loaded_key) != _cl_task["id"]:
            st.session_state[_cl_key] = job.get("cover_letter") or ""
            st.session_state[_cl_loaded_key] = _cl_task["id"]

    cl_text = st.text_area(
        "cover_letter_body",
        key=_cl_key,
        height=280,
        label_visibility="collapsed",
    )

    # ── Iterative refinement ──────────────────────
    if cl_text and not _cl_running:
        with st.expander("✏️ Refine with Feedback"):
            st.caption("Describe what to change. The current draft is passed to the LLM as context.")
            _fb_key = f"fb_{selected_id}"
            feedback_text = st.text_area(
                "Feedback",
                placeholder="e.g. Shorten the second paragraph and add a line about cross-functional leadership.",
                height=80,
                key=_fb_key,
                label_visibility="collapsed",
            )
            if st.button("✨ Regenerate with Feedback", use_container_width=True,
                         disabled=not (feedback_text or "").strip(),
                         key=f"cl_refine_{selected_id}"):
                import json as _json
                submit_task(
                    DEFAULT_DB, "cover_letter", selected_id,
                    params=_json.dumps({
                        "previous_result": cl_text,
                        "feedback": feedback_text.strip(),
                    }),
                )
                st.session_state.pop(_fb_key, None)
                st.rerun()

    # Copy + Save row
    c1, c2 = st.columns(2)
    with c1:
        if cl_text:
            _copy_btn(cl_text, label="📋 Copy Letter")
    with c2:
        if st.button("💾 Save draft", use_container_width=True):
            update_cover_letter(DEFAULT_DB, selected_id, cl_text)
            st.success("Saved!")

    # PDF generation
    if cl_text:
        if st.button("📄 Export PDF → JobSearch folder", use_container_width=True, type="primary"):
            with st.spinner("Generating PDF…"):
                try:
                    pdf_path = _make_cover_letter_pdf(job, cl_text, DOCS_DIR)
                    update_cover_letter(DEFAULT_DB, selected_id, cl_text)
                    st.success(f"Saved: `{pdf_path.name}`")
                except Exception as e:
                    st.error(f"PDF error: {e}")

    st.divider()

    # Open listing + Mark Applied
    c3, c4 = st.columns(2)
    with c3:
        if job.get("url"):
            st.link_button("Open listing ↗", job["url"], use_container_width=True)
    with c4:
        if st.button("✅ Mark as Applied", use_container_width=True, type="primary"):
            if cl_text:
                update_cover_letter(DEFAULT_DB, selected_id, cl_text)
            mark_applied(DEFAULT_DB, [selected_id])
            st.success("Marked as applied!")
            st.rerun()

    if st.button("🚫 Reject listing", use_container_width=True):
        update_job_status(DEFAULT_DB, [selected_id], "rejected")
        # Advance selectbox to next job so list doesn't snap to first item
        current_idx = ids.index(selected_id) if selected_id in ids else 0
        if current_idx + 1 < len(ids):
            st.session_state["apply_job_id"] = ids[current_idx + 1]
        st.rerun()

    st.divider()

    # ── Resume highlights ─────────────────────────
    with st.expander("📄 Resume Highlights"):
        if RESUME_YAML.exists():
            resume = yaml.safe_load(RESUME_YAML.read_text()) or {}
            for exp in resume.get("experience_details", []):
                position = exp.get("position", "")
                company  = exp.get("company", "")
                period   = exp.get("employment_period", "")

                # Parse start / end dates (handles "MM/YYYY - Present" style)
                if " - " in period:
                    date_start, date_end = [p.strip() for p in period.split(" - ", 1)]
                else:
                    date_start, date_end = period, ""

                # Flatten bullets
                bullets = [
                    v
                    for resp_dict in exp.get("key_responsibilities", [])
                    for v in resp_dict.values()
                ]
                all_duties = "\n".join(f"• {b}" for b in bullets)

                # ── Header ────────────────────────────────────────────────────
                st.markdown(
                    f"**{position}** &nbsp;·&nbsp; "
                    f"{company} &nbsp;·&nbsp; "
                    f"*{period}*"
                )

                # ── Copy row: title | start | end | all duties ────────────────
                cp_t, cp_s, cp_e, cp_d = st.columns(4)
                with cp_t:
                    st.caption("Title")
                    _copy_btn(position, label="📋 Copy", height=34)
                with cp_s:
                    st.caption("Start")
                    _copy_btn(date_start, label="📋 Copy", height=34)
                with cp_e:
                    st.caption("End")
                    _copy_btn(date_end or period, label="📋 Copy", height=34)
                with cp_d:
                    st.caption("All Duties")
                    if bullets:
                        _copy_btn(all_duties, label="📋 Copy", height=34)

                # ── Individual bullets ────────────────────────────────────────
                for bullet in bullets:
                    b_col, cp_col = st.columns([6, 1])
                    b_col.caption(f"• {bullet}")
                    with cp_col:
                        _copy_btn(bullet, label="📋", done="✅", height=32)

                st.markdown("---")
        else:
            st.warning("Resume YAML not found — check that AIHawk is cloned.")

    # ── Application Q&A ───────────────────────────────────────────────────────
    with st.expander("💬 Answer Application Questions"):
        st.caption("Paste a question from the application and get an answer in your voice.")

        _qa_key = f"qa_list_{selected_id}"
        if _qa_key not in st.session_state:
            st.session_state[_qa_key] = []

        q_input = st.text_area(
            "Paste question",
            placeholder="In 200 words or less, explain why you're a strong fit for this role.",
            height=80,
            key=f"qa_input_{selected_id}",
            label_visibility="collapsed",
        )
        if st.button("✨ Generate Answer", key=f"qa_gen_{selected_id}",
                     use_container_width=True,
                     disabled=not (q_input or "").strip()):
            with st.spinner("Generating answer…"):
                _answer = _answer_question(job, q_input.strip())
            st.session_state[_qa_key].append({"q": q_input.strip(), "a": _answer})
            st.rerun()

        for _i, _pair in enumerate(reversed(st.session_state[_qa_key])):
            _real_idx = len(st.session_state[_qa_key]) - 1 - _i
            st.markdown(f"**Q:** {_pair['q']}")
            _a_key = f"qa_ans_{selected_id}_{_real_idx}"
            if _a_key not in st.session_state:
                st.session_state[_a_key] = _pair["a"]
            _answer_text = st.text_area(
                "answer",
                key=_a_key,
                height=120,
                label_visibility="collapsed",
            )
            _copy_btn(_answer_text, label="📋 Copy Answer")
            if _i < len(st.session_state[_qa_key]) - 1:
                st.markdown("---")
