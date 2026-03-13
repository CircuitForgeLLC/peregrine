# app/components/linkedin_import.py
"""
Shared LinkedIn import widget.

Usage in a page:
    from app.components.linkedin_import import render_linkedin_tab

    # At top of page render — check for pending import:
    _li_data = st.session_state.pop("_linkedin_extracted", None)
    if _li_data:
        st.session_state["_parsed_resume"] = _li_data
        st.rerun()

    # Inside the LinkedIn tab:
    with tab_linkedin:
        render_linkedin_tab(config_dir=CONFIG_DIR, tier=tier)
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

import streamlit as st

_LINKEDIN_PROFILE_RE = re.compile(r"https?://(www\.)?linkedin\.com/in/", re.I)


def _stage_path(config_dir: Path) -> Path:
    return config_dir / "linkedin_stage.json"


def _load_stage(config_dir: Path) -> dict | None:
    path = _stage_path(config_dir)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except Exception:
        return None


def _days_ago(iso_ts: str) -> str:
    try:
        dt = datetime.fromisoformat(iso_ts)
        delta = datetime.now(timezone.utc) - dt
        days = delta.days
        if days == 0:
            return "today"
        if days == 1:
            return "yesterday"
        return f"{days} days ago"
    except Exception:
        return "unknown"


def _do_scrape(url: str, config_dir: Path) -> None:
    """Validate URL, run scrape, update state."""
    if not _LINKEDIN_PROFILE_RE.match(url):
        st.error("Please enter a LinkedIn profile URL (linkedin.com/in/…)")
        return

    with st.spinner("Fetching LinkedIn profile… (10–20 seconds)"):
        try:
            from scripts.linkedin_scraper import scrape_profile
            scrape_profile(url, _stage_path(config_dir))
            st.success("Profile imported successfully.")
            st.rerun()
        except ValueError as e:
            st.error(str(e))
        except RuntimeError as e:
            st.warning(str(e))
        except Exception as e:
            st.error(f"Unexpected error: {e}")


def render_linkedin_tab(config_dir: Path, tier: str) -> None:
    """
    Render the LinkedIn import UI.

    When the user clicks "Use this data", writes the extracted dict to
    st.session_state["_linkedin_extracted"] and calls st.rerun().

    Caller reads: data = st.session_state.pop("_linkedin_extracted", None)
    """
    stage = _load_stage(config_dir)

    # ── Staged data status bar ────────────────────────────────────────────────
    if stage:
        scraped_at = stage.get("scraped_at", "")
        source_label = "LinkedIn export" if stage.get("source") == "export_zip" else "LinkedIn profile"
        col_info, col_refresh = st.columns([4, 1])
        col_info.caption(f"Last imported from {source_label}: {_days_ago(scraped_at)}")
        if col_refresh.button("🔄 Refresh", key="li_refresh"):
            url = stage.get("url")
            if url:
                _do_scrape(url, config_dir)
            else:
                st.info("Original URL not available — paste the URL below to re-import.")

    # ── URL import ────────────────────────────────────────────────────────────
    st.markdown("**Import from LinkedIn profile URL**")
    url_input = st.text_input(
        "LinkedIn profile URL",
        placeholder="https://linkedin.com/in/your-name",
        label_visibility="collapsed",
        key="li_url_input",
    )
    if st.button("🔗 Import from LinkedIn", key="li_import_btn", type="primary"):
        if not url_input.strip():
            st.warning("Please enter your LinkedIn profile URL.")
        else:
            _do_scrape(url_input.strip(), config_dir)

    st.caption(
        "Imports from your public LinkedIn profile. No login or credentials required. "
        "Scraping typically takes 10–20 seconds."
    )

    # ── Section preview + use button ─────────────────────────────────────────
    if stage:
        from scripts.linkedin_parser import parse_stage
        extracted, err = parse_stage(_stage_path(config_dir))

        if err:
            st.warning(f"Could not read staged data: {err}")
        else:
            st.divider()
            st.markdown("**Preview**")
            col1, col2, col3 = st.columns(3)
            col1.metric("Experience entries", len(extracted.get("experience", [])))
            col2.metric("Skills", len(extracted.get("skills", [])))
            col3.metric("Certifications", len(extracted.get("achievements", [])))

            if extracted.get("career_summary"):
                with st.expander("Summary"):
                    st.write(extracted["career_summary"])

            if extracted.get("experience"):
                with st.expander(f"Experience ({len(extracted['experience'])} entries)"):
                    for exp in extracted["experience"]:
                        st.markdown(f"**{exp.get('title')}** @ {exp.get('company')} · {exp.get('date_range', '')}")

            if extracted.get("education"):
                with st.expander("Education"):
                    for edu in extracted["education"]:
                        st.markdown(f"**{edu.get('school')}** — {edu.get('degree')} {edu.get('field', '')}".strip())

            if extracted.get("skills"):
                with st.expander("Skills"):
                    st.write(", ".join(extracted["skills"]))

            st.divider()
            if st.button("✅ Use this data", key="li_use_btn", type="primary"):
                st.session_state["_linkedin_extracted"] = extracted
                st.rerun()

    # ── Advanced: data export ─────────────────────────────────────────────────
    with st.expander("⬇️ Import from LinkedIn data export (advanced)", expanded=False):
        st.caption(
            "Download your LinkedIn data: **Settings & Privacy → Data Privacy → "
            "Get a copy of your data → Request archive → Fast file**. "
            "The Fast file is available immediately and contains your profile, "
            "experience, education, and skills."
        )
        zip_file = st.file_uploader(
            "Upload LinkedIn export zip", type=["zip"], key="li_zip_upload"
        )
        if zip_file is not None:
            if st.button("📦 Parse export", key="li_parse_zip"):
                with st.spinner("Parsing export archive…"):
                    try:
                        from scripts.linkedin_scraper import parse_export_zip
                        extracted = parse_export_zip(
                            zip_file.read(), _stage_path(config_dir)
                        )
                        st.success(
                            f"Imported {len(extracted.get('experience', []))} experience entries, "
                            f"{len(extracted.get('skills', []))} skills. "
                            "Click 'Use this data' above to apply."
                        )
                        st.rerun()
                    except Exception as e:
                        st.error(f"Failed to parse export: {e}")
