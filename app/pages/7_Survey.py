# app/pages/7_Survey.py
"""
Survey Assistant — real-time help with culture-fit surveys.

Supports text paste and screenshot (via clipboard or file upload).
Quick mode: "pick B" + one-liner. Detailed mode: option-by-option breakdown.
"""
import base64
import io
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import requests
import streamlit as st

from scripts.db import (
    DEFAULT_DB, init_db,
    get_interview_jobs, get_job_by_id,
    insert_survey_response, get_survey_responses,
)
from scripts.llm_router import LLMRouter

st.title("📋 Survey Assistant")

init_db(DEFAULT_DB)


# ── Vision service health check ────────────────────────────────────────────────
def _vision_available() -> bool:
    try:
        r = requests.get("http://localhost:8002/health", timeout=2)
        return r.status_code == 200
    except Exception:
        return False


vision_up = _vision_available()

# ── Job selector ───────────────────────────────────────────────────────────────
jobs_by_stage = get_interview_jobs(DEFAULT_DB)
survey_jobs = jobs_by_stage.get("survey", [])
other_jobs = (
    jobs_by_stage.get("applied", []) +
    jobs_by_stage.get("phone_screen", []) +
    jobs_by_stage.get("interviewing", []) +
    jobs_by_stage.get("offer", [])
)
all_jobs = survey_jobs + other_jobs

if not all_jobs:
    st.info("No active jobs found. Add jobs in Job Review first.")
    st.stop()

job_labels = {j["id"]: f"{j.get('company', '?')} — {j.get('title', '')}" for j in all_jobs}
selected_job_id = st.selectbox(
    "Job",
    options=[j["id"] for j in all_jobs],
    format_func=lambda jid: job_labels[jid],
    index=0,
)
selected_job = get_job_by_id(DEFAULT_DB, selected_job_id)

# ── LLM prompt builders ────────────────────────────────────────────────────────
_SURVEY_SYSTEM = (
    "You are a job application advisor helping a candidate answer a culture-fit survey. "
    "The candidate values collaborative teamwork, clear communication, growth, and impact. "
    "Choose answers that present them in the best professional light."
)


def _build_text_prompt(text: str, mode: str) -> str:
    if mode == "Quick":
        return (
            "Answer each survey question below. For each, give ONLY the letter of the best "
            "option and a single-sentence reason. Format exactly as:\n"
            "1. B — reason here\n2. A — reason here\n\n"
            f"Survey:\n{text}"
        )
    return (
        "Analyze each survey question below. For each question:\n"
        "- Briefly evaluate each option (1 sentence each)\n"
        "- State your recommendation with reasoning\n\n"
        f"Survey:\n{text}"
    )


def _build_image_prompt(mode: str) -> str:
    if mode == "Quick":
        return (
            "This is a screenshot of a culture-fit survey. Read all questions and answer each "
            "with the letter of the best option for a collaborative, growth-oriented candidate. "
            "Format: '1. B — brief reason' on separate lines."
        )
    return (
        "This is a screenshot of a culture-fit survey. For each question, evaluate each option "
        "and recommend the best choice for a collaborative, growth-oriented candidate. "
        "Include a brief breakdown per option and a clear recommendation."
    )


# ── Layout ─────────────────────────────────────────────────────────────────────
left_col, right_col = st.columns([1, 1], gap="large")

with left_col:
    survey_name = st.text_input(
        "Survey name (optional)",
        placeholder="e.g. Culture Fit Round 1",
        key="survey_name",
    )
    mode = st.radio("Mode", ["Quick", "Detailed"], horizontal=True, key="survey_mode")
    st.caption(
        "**Quick** — best answer + one-liner per question  |  "
        "**Detailed** — option-by-option breakdown"
    )

    # Input tabs
    if vision_up:
        tab_text, tab_screenshot = st.tabs(["📝 Paste Text", "🖼️ Screenshot"])
    else:
        st.info(
            "📷 Screenshot input unavailable — vision service not running.  \n"
            "Start it with: `bash scripts/manage-vision.sh start`"
        )
        tab_text = st.container()
        tab_screenshot = None

    image_b64: str | None = None
    raw_text: str = ""

    with tab_text:
        raw_text = st.text_area(
            "Paste survey questions here",
            height=280,
            placeholder=(
                "Q1: Which describes your ideal work environment?\n"
                "A. Solo focused work\nB. Collaborative team\n"
                "C. Mix of both\nD. Depends on the task"
            ),
            key="survey_text",
        )

    if tab_screenshot is not None:
        with tab_screenshot:
            st.caption("Paste from clipboard or upload a screenshot file.")
            paste_col, upload_col = st.columns(2)

            with paste_col:
                try:
                    from streamlit_paste_button import paste_image_button
                    paste_result = paste_image_button("📋 Paste from clipboard", key="paste_btn")
                    if paste_result and paste_result.image_data:
                        buf = io.BytesIO()
                        paste_result.image_data.save(buf, format="PNG")
                        image_b64 = base64.b64encode(buf.getvalue()).decode()
                        st.image(
                            paste_result.image_data,
                            caption="Pasted image",
                            use_container_width=True,
                        )
                except ImportError:
                    st.warning("streamlit-paste-button not installed. Use file upload.")

            with upload_col:
                uploaded = st.file_uploader(
                    "Upload screenshot",
                    type=["png", "jpg", "jpeg"],
                    key="survey_upload",
                    label_visibility="collapsed",
                )
                if uploaded:
                    image_b64 = base64.b64encode(uploaded.read()).decode()
                    st.image(uploaded, caption="Uploaded image", use_container_width=True)

    # Analyze button
    has_input = bool(raw_text.strip()) or bool(image_b64)
    if st.button("🔍 Analyze", type="primary", disabled=not has_input, use_container_width=True):
        with st.spinner("Analyzing…"):
            try:
                router = LLMRouter()
                if image_b64:
                    prompt = _build_image_prompt(mode)
                    output = router.complete(
                        prompt,
                        images=[image_b64],
                        fallback_order=router.config.get("vision_fallback_order"),
                    )
                    source = "screenshot"
                else:
                    prompt = _build_text_prompt(raw_text, mode)
                    output = router.complete(
                        prompt,
                        system=_SURVEY_SYSTEM,
                        fallback_order=router.config.get("research_fallback_order"),
                    )
                    source = "text_paste"
                st.session_state["survey_output"] = output
                st.session_state["survey_source"] = source
                st.session_state["survey_image_b64"] = image_b64
                st.session_state["survey_raw_text"] = raw_text
            except Exception as e:
                st.error(f"Analysis failed: {e}")

with right_col:
    output = st.session_state.get("survey_output")
    if output:
        st.markdown("### Analysis")
        st.markdown(output)

        st.divider()
        with st.form("save_survey_form"):
            reported_score = st.text_input(
                "Reported score (optional)",
                placeholder="e.g. 82% or 4.2/5",
                key="reported_score_input",
            )
            if st.form_submit_button("💾 Save to Job"):
                source = st.session_state.get("survey_source", "text_paste")
                image_b64_saved = st.session_state.get("survey_image_b64")
                raw_text_saved = st.session_state.get("survey_raw_text", "")

                image_path = ""
                if image_b64_saved:
                    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                    save_dir = (
                        Path(__file__).parent.parent.parent
                        / "data"
                        / "survey_screenshots"
                        / str(selected_job_id)
                    )
                    save_dir.mkdir(parents=True, exist_ok=True)
                    img_file = save_dir / f"{ts}.png"
                    img_file.write_bytes(base64.b64decode(image_b64_saved))
                    image_path = str(img_file)

                insert_survey_response(
                    DEFAULT_DB,
                    job_id=selected_job_id,
                    survey_name=survey_name,
                    source=source,
                    raw_input=raw_text_saved,
                    image_path=image_path,
                    mode=mode.lower(),
                    llm_output=output,
                    reported_score=reported_score,
                )
                st.success("Saved!")
                del st.session_state["survey_output"]
                st.rerun()
    else:
        st.markdown("### Analysis")
        st.caption("Results will appear here after analysis.")

# ── History ────────────────────────────────────────────────────────────────────
st.divider()
st.subheader("📂 Response History")
history = get_survey_responses(DEFAULT_DB, job_id=selected_job_id)

if not history:
    st.caption("No saved responses for this job yet.")
else:
    for resp in history:
        label = resp.get("survey_name") or "Survey response"
        ts = (resp.get("created_at") or "")[:16]
        score = resp.get("reported_score")
        score_str = f" · Score: {score}" if score else ""
        with st.expander(f"{label} · {ts}{score_str}"):
            st.caption(f"Mode: {resp.get('mode', '?')} · Source: {resp.get('source', '?')}")
            if resp.get("raw_input"):
                with st.expander("Original input"):
                    st.text(resp["raw_input"])
            st.markdown(resp.get("llm_output", ""))
