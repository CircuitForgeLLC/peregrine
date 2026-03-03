"""
Floating feedback button + dialog — thin Streamlit shell.
All business logic lives in scripts/feedback_api.py.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st

# ── CSS: float the button to the bottom-right corner ─────────────────────────
# Targets the button by its aria-label (set via `help=` parameter).
_FLOAT_CSS = """
<style>
button[aria-label="Send feedback or report a bug"] {
    position: fixed !important;
    bottom: 2rem !important;
    right: 2rem !important;
    z-index: 9999 !important;
    border-radius: 25px !important;
    padding: 0.5rem 1.25rem !important;
    box-shadow: 0 4px 16px rgba(0,0,0,0.25) !important;
    font-size: 0.9rem !important;
}
</style>
"""


@st.dialog("Send Feedback", width="large")
def _feedback_dialog(page: str) -> None:
    """Two-step feedback dialog: form → consent/attachments → submit."""
    from scripts.feedback_api import (
        collect_context, collect_logs, collect_listings,
        build_issue_body, create_forgejo_issue,
        upload_attachment, screenshot_page,
    )
    from scripts.db import DEFAULT_DB

    # ── Initialise step counter ───────────────────────────────────────────────
    if "fb_step" not in st.session_state:
        st.session_state.fb_step = 1

    # ═════════════════════════════════════════════════════════════════════════
    # STEP 1 — Form
    # ═════════════════════════════════════════════════════════════════════════
    if st.session_state.fb_step == 1:
        st.subheader("What's on your mind?")

        fb_type = st.selectbox(
            "Type", ["Bug", "Feature Request", "Other"], key="fb_type"
        )
        fb_title = st.text_input(
            "Title", placeholder="Short summary of the issue or idea", key="fb_title"
        )
        fb_desc = st.text_area(
            "Description",
            placeholder="Describe what happened or what you'd like to see...",
            key="fb_desc",
        )
        if fb_type == "Bug":
            st.text_area(
                "Reproduction steps",
                placeholder="1. Go to...\n2. Click...\n3. See error",
                key="fb_repro",
            )

        col_cancel, _, col_next = st.columns([1, 3, 1])
        with col_cancel:
            if st.button("Cancel"):
                _clear_feedback_state()
                st.rerun()  # intentionally closes the dialog
        with col_next:
            if st.button(
                "Next →",
                type="primary",
                disabled=not st.session_state.get("fb_title", "").strip()
                or not st.session_state.get("fb_desc", "").strip(),
            ):
                st.session_state.fb_step = 2
                # no st.rerun() — button click already re-renders the dialog

    # ═════════════════════════════════════════════════════════════════════════
    # STEP 2 — Consent + attachments
    # ═════════════════════════════════════════════════════════════════════════
    elif st.session_state.fb_step == 2:
        st.subheader("Optional: attach diagnostic data")

        # ── Diagnostic data toggle + preview ─────────────────────────────────
        include_diag = st.toggle(
            "Include diagnostic data (logs + recent listings)", key="fb_diag"
        )
        if include_diag:
            with st.expander("Preview what will be sent", expanded=True):
                st.caption("**App logs (last 100 lines, PII masked):**")
                st.code(collect_logs(100), language=None)
                st.caption("**Recent listings (title / company / URL only):**")
                for j in collect_listings(DEFAULT_DB, 5):
                    st.write(f"- {j['title']} @ {j['company']} — {j['url']}")

        # ── Screenshot ────────────────────────────────────────────────────────
        st.divider()
        st.caption("**Screenshot** (optional)")
        col_cap, col_up = st.columns(2)

        with col_cap:
            if st.button("📸 Capture current view"):
                with st.spinner("Capturing page…"):
                    png = screenshot_page()
                if png:
                    st.session_state.fb_screenshot = png
                else:
                    st.warning(
                        "Playwright not available — install it with "
                        "`playwright install chromium`, or upload a screenshot instead."
                    )

        with col_up:
            uploaded = st.file_uploader(
                "Upload screenshot",
                type=["png", "jpg", "jpeg"],
                label_visibility="collapsed",
                key="fb_upload",
            )
            if uploaded:
                st.session_state.fb_screenshot = uploaded.read()

        if st.session_state.get("fb_screenshot"):
            st.image(
                st.session_state["fb_screenshot"],
                caption="Screenshot preview — this will be attached to the issue",
                use_container_width=True,
            )
            if st.button("🗑 Remove screenshot"):
                st.session_state.pop("fb_screenshot", None)
                # no st.rerun() — button click already re-renders the dialog

        # ── Attribution consent ───────────────────────────────────────────────
        st.divider()
        submitter: str | None = None
        try:
            import yaml
            _ROOT = Path(__file__).parent.parent
            user = yaml.safe_load((_ROOT / "config" / "user.yaml").read_text()) or {}
            name = (user.get("name") or "").strip()
            email = (user.get("email") or "").strip()
            if name or email:
                label = f"Include my name & email in the report: **{name}** ({email})"
                if st.checkbox(label, key="fb_attr"):
                    submitter = f"{name} <{email}>"
        except Exception:
            pass

        # ── Navigation ────────────────────────────────────────────────────────
        col_back, _, col_submit = st.columns([1, 3, 2])
        with col_back:
            if st.button("← Back"):
                st.session_state.fb_step = 1
                # no st.rerun() — button click already re-renders the dialog

        with col_submit:
            if st.button("Submit Feedback", type="primary"):
                _submit(page, include_diag, submitter, collect_context,
                        collect_logs, collect_listings, build_issue_body,
                        create_forgejo_issue, upload_attachment, DEFAULT_DB)


def _submit(page, include_diag, submitter, collect_context, collect_logs,
            collect_listings, build_issue_body, create_forgejo_issue,
            upload_attachment, db_path) -> None:
    """Handle form submission: build body, file issue, upload screenshot."""
    with st.spinner("Filing issue…"):
        context = collect_context(page)
        attachments: dict = {}
        if include_diag:
            attachments["logs"] = collect_logs(100)
            attachments["listings"] = collect_listings(db_path, 5)
        if submitter:
            attachments["submitter"] = submitter

        fb_type = st.session_state.get("fb_type", "Other")
        type_key = {"Bug": "bug", "Feature Request": "feature", "Other": "other"}.get(
            fb_type, "other"
        )
        labels = ["beta-feedback", "needs-triage"]
        labels.append(
            {"bug": "bug", "feature": "feature-request"}.get(type_key, "question")
        )

        form = {
            "type": type_key,
            "description": st.session_state.get("fb_desc", ""),
            "repro": st.session_state.get("fb_repro", "") if type_key == "bug" else "",
        }

        body = build_issue_body(form, context, attachments)

        try:
            result = create_forgejo_issue(
                st.session_state.get("fb_title", "Feedback"), body, labels
            )
            screenshot = st.session_state.get("fb_screenshot")
            if screenshot:
                upload_attachment(result["number"], screenshot)

            _clear_feedback_state()
            st.success(f"Issue filed! [View on Forgejo]({result['url']})")
            st.balloons()

        except Exception as exc:
            st.error(f"Failed to file issue: {exc}")


def _clear_feedback_state() -> None:
    for key in [
        "fb_step", "fb_type", "fb_title", "fb_desc", "fb_repro",
        "fb_diag", "fb_upload", "fb_attr", "fb_screenshot",
    ]:
        st.session_state.pop(key, None)


def inject_feedback_button(page: str = "Unknown") -> None:
    """
    Inject the floating feedback button. Call once per page render in app.py.
    Hidden automatically in DEMO_MODE.
    """
    if os.environ.get("DEMO_MODE", "").lower() in ("1", "true", "yes"):
        return
    if not os.environ.get("FORGEJO_API_TOKEN"):
        return  # silently skip if not configured

    st.markdown(_FLOAT_CSS, unsafe_allow_html=True)
    if st.button(
        "💬 Feedback",
        key="__feedback_floating_btn__",
        help="Send feedback or report a bug",
    ):
        _feedback_dialog(page)
