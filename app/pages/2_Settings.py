# app/pages/2_Settings.py
"""
Settings — edit search profiles, LLM backends, Notion connection, services,
and resume profile (paste-able bullets used in Apply Workspace).
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import streamlit as st
import yaml
import os as _os

from scripts.user_profile import UserProfile

_USER_YAML = Path(__file__).parent.parent.parent / "config" / "user.yaml"
_profile = UserProfile(_USER_YAML) if UserProfile.exists(_USER_YAML) else None
_name = _profile.name if _profile else "Job Seeker"

st.title("⚙️ Settings")

CONFIG_DIR = Path(__file__).parent.parent.parent / "config"
SEARCH_CFG = CONFIG_DIR / "search_profiles.yaml"
BLOCKLIST_CFG = CONFIG_DIR / "blocklist.yaml"
LLM_CFG = CONFIG_DIR / "llm.yaml"
NOTION_CFG = CONFIG_DIR / "notion.yaml"
RESUME_PATH = Path(__file__).parent.parent.parent / "config" / "plain_text_resume.yaml"
KEYWORDS_CFG = CONFIG_DIR / "resume_keywords.yaml"

def load_yaml(path: Path) -> dict:
    if path.exists():
        return yaml.safe_load(path.read_text()) or {}
    return {}

def save_yaml(path: Path, data: dict) -> None:
    path.write_text(yaml.dump(data, default_flow_style=False, allow_unicode=True))


def _suggest_search_terms(current_titles: list[str], resume_path: Path) -> dict:
    """Call LLM to suggest additional job titles and exclude keywords."""
    import json
    import re
    from scripts.llm_router import LLMRouter

    resume_context = ""
    if resume_path.exists():
        resume = load_yaml(resume_path)
        lines = []
        for exp in (resume.get("experience_details") or [])[:3]:
            pos = exp.get("position", "")
            co = exp.get("company", "")
            skills = ", ".join((exp.get("skills_acquired") or [])[:5])
            lines.append(f"- {pos} at {co}: {skills}")
        resume_context = "\n".join(lines)

    titles_str = "\n".join(f"- {t}" for t in current_titles)
    prompt = f"""You are helping a job seeker optimize their search criteria.

Their background (from resume):
{resume_context or "Customer success and technical account management leader"}

Current job titles being searched:
{titles_str}

Suggest:
1. 5-8 additional job titles they might be missing (alternative names, adjacent roles, senior variants)
2. 3-5 keywords to add to the exclusion filter (to screen out irrelevant postings)

Return ONLY valid JSON in this exact format:
{{"suggested_titles": ["Title 1", "Title 2"], "suggested_excludes": ["keyword 1", "keyword 2"]}}"""

    result = LLMRouter().complete(prompt).strip()
    m = re.search(r"\{.*\}", result, re.DOTALL)
    if m:
        try:
            return json.loads(m.group())
        except Exception:
            pass
    return {"suggested_titles": [], "suggested_excludes": []}

_show_finetune = bool(_profile and _profile.inference_profile in ("single-gpu", "dual-gpu"))

USER_CFG = CONFIG_DIR / "user.yaml"
SERVER_CFG = CONFIG_DIR / "server.yaml"
SERVER_CFG_EXAMPLE = CONFIG_DIR / "server.yaml.example"

_dev_mode = _os.getenv("DEV_MODE", "").lower() in ("true", "1", "yes")
_u_for_dev = yaml.safe_load(USER_CFG.read_text()) or {} if USER_CFG.exists() else {}
_show_dev_tab = _dev_mode or bool(_u_for_dev.get("dev_tier_override"))

_tab_names = [
    "👤 My Profile", "📝 Resume Profile", "🔎 Search",
    "⚙️ System", "🎯 Fine-Tune", "🔑 License", "💾 Data"
]
if _show_dev_tab:
    _tab_names.append("🛠️ Developer")
_all_tabs = st.tabs(_tab_names)
tab_profile, tab_resume, tab_search, tab_system, tab_finetune, tab_license, tab_data = _all_tabs[:7]

# ── Inline LLM generate buttons ───────────────────────────────────────────────
# Unlocked when user has a configured LLM backend (BYOK) OR a paid tier.
# Writes into session state keyed to the widget's `key=` param, then reruns.
from app.wizard.tiers import can_use as _cu, has_configured_llm as _has_llm
_byok = _has_llm()
_gen_panel_active = bool(_profile) and _cu(
    _profile.effective_tier if _profile else "free", "llm_career_summary", has_byok=_byok
)

# Seed session state for LLM-injectable text fields on first load
_u_init = yaml.safe_load(USER_CFG.read_text()) or {} if USER_CFG.exists() else {}
for _fk, _fv in [
    ("profile_career_summary", _u_init.get("career_summary", "")),
    ("profile_candidate_voice", _u_init.get("candidate_voice", "")),
]:
    if _fk not in st.session_state:
        st.session_state[_fk] = _fv

with tab_profile:
    from scripts.user_profile import UserProfile as _UP, _DEFAULTS as _UP_DEFAULTS
    import yaml as _yaml_up

    st.caption("Your identity and service configuration. Saved values drive all LLM prompts, PDF headers, and service connections.")

    _u = _yaml_up.safe_load(USER_CFG.read_text()) or {} if USER_CFG.exists() else {}
    _svc = {**_UP_DEFAULTS["services"], **_u.get("services", {})}

    with st.expander("👤 Identity", expanded=True):
        c1, c2 = st.columns(2)
        u_name     = c1.text_input("Full Name",   _u.get("name", ""))
        u_email    = c1.text_input("Email",        _u.get("email", ""))
        u_phone    = c2.text_input("Phone",        _u.get("phone", ""))
        u_linkedin = c2.text_input("LinkedIn URL", _u.get("linkedin", ""))
        u_summary = st.text_area("Career Summary (used in LLM prompts)",
                                  key="profile_career_summary", height=100)
        if _gen_panel_active:
            if st.button("✨ Generate", key="gen_career_summary", help="Generate career summary with AI"):
                _cs_draft = st.session_state.get("profile_career_summary", "").strip()
                _cs_resume_ctx = ""
                if RESUME_PATH.exists():
                    _rdata = load_yaml(RESUME_PATH)
                    _exps = (_rdata.get("experience_details") or [])[:3]
                    _exp_lines = []
                    for _e in _exps:
                        _t = _e.get("position", "")
                        _c = _e.get("company", "")
                        _b = "; ".join((_e.get("key_responsibilities") or [])[:2])
                        _exp_lines.append(f"- {_t} at {_c}: {_b}")
                    _cs_resume_ctx = "\n".join(_exp_lines)
                _cs_prompt = (
                    f"Write a 3-4 sentence professional career summary for {_profile.name} in first person, "
                    f"suitable for use in cover letters and LLM prompts. "
                    f"Return only the summary, no preamble.\n"
                )
                if _cs_draft:
                    _cs_prompt += f"\nExisting draft to improve or replace:\n{_cs_draft}\n"
                if _cs_resume_ctx:
                    _cs_prompt += f"\nRecent experience for context:\n{_cs_resume_ctx}\n"
                with st.spinner("Generating…"):
                    from scripts.llm_router import LLMRouter as _LLMRouter
                    st.session_state["profile_career_summary"] = _LLMRouter().complete(_cs_prompt).strip()
                st.rerun()
        u_voice = st.text_area(
            "Voice & Personality (shapes cover letter tone)",
            key="profile_candidate_voice",
            height=80,
            help="Personality traits and writing voice that the LLM uses to write authentically in your style. Never disclosed in applications.",
        )
        if _gen_panel_active:
            if st.button("✨ Generate", key="gen_candidate_voice", help="Generate voice descriptor with AI"):
                _vc_draft = st.session_state.get("profile_candidate_voice", "").strip()
                _vc_prompt = (
                    f"Write a 2-4 sentence voice and personality descriptor for {_profile.name} "
                    f"to guide an LLM writing cover letters in their authentic style. "
                    f"Describe personality traits, tone, and writing voice — not a bio. "
                    f"Career context: {_profile.career_summary}. "
                    f"Return only the descriptor, no preamble.\n"
                )
                if _vc_draft:
                    _vc_prompt += f"\nExisting descriptor to improve:\n{_vc_draft}\n"
                with st.spinner("Generating…"):
                    from scripts.llm_router import LLMRouter as _LLMRouter
                    st.session_state["profile_candidate_voice"] = _LLMRouter().complete(_vc_prompt).strip()
                st.rerun()

    with st.expander("🎯 Mission & Values"):
        st.caption("Industry passions and causes you care about. Used to inject authentic Para 3 alignment when a company matches. Never disclosed in applications.")

        # Initialise session state from saved YAML; re-sync after a save (version bump)
        _mission_ver = str(_u.get("mission_preferences", {}))
        if "mission_rows" not in st.session_state or st.session_state.get("mission_ver") != _mission_ver:
            st.session_state.mission_rows = [
                {"key": k, "value": v}
                for k, v in _u.get("mission_preferences", {}).items()
            ]
            st.session_state.mission_ver = _mission_ver

        _can_generate = _gen_panel_active

        _to_delete = None
        for _idx, _row in enumerate(st.session_state.mission_rows):
            _rc1, _rc2 = st.columns([1, 3])
            with _rc1:
                _row["key"] = st.text_input(
                    "Domain", _row["key"],
                    key=f"mkey_{_idx}",
                    label_visibility="collapsed",
                    placeholder="e.g. animal_welfare",
                )
            with _rc2:
                _btn_col, _area_col = st.columns([1, 5])
                with _area_col:
                    _row["value"] = st.text_area(
                        "Alignment note", _row["value"],
                        key=f"mval_{_idx}",
                        label_visibility="collapsed",
                        placeholder="Your personal connection to this domain…",
                        height=68,
                    )
                with _btn_col:
                    if _can_generate:
                        if st.button("✨", key=f"mgen_{_idx}", help="Generate alignment note with AI"):
                            _domain = _row["key"].replace("_", " ")
                            _m_draft = st.session_state.get(f"mval_{_idx}", _row["value"]).strip()
                            _gen_prompt = (
                                f"Write a 2–3 sentence personal mission alignment note "
                                f"(first person, warm, authentic) for {_profile.name if _profile else 'the candidate'} "
                                f"in the '{_domain}' domain for use in cover letters. "
                                f"Background: {_profile.career_summary if _profile else ''}. "
                                f"Voice: {_profile.candidate_voice if _profile else ''}. "
                                f"The note should explain their genuine personal connection and why they'd "
                                f"be motivated working in this space. Do not start with 'I'. "
                                f"Return only the note, no preamble.\n"
                            )
                            if _m_draft:
                                _gen_prompt += f"\nExisting note to improve:\n{_m_draft}\n"
                            with st.spinner(f"Generating note for {_domain}…"):
                                from scripts.llm_router import LLMRouter as _LLMRouter
                                _row["value"] = _LLMRouter().complete(_gen_prompt).strip()
                            st.rerun()
                    if st.button("🗑", key=f"mdel_{_idx}", help="Remove this domain"):
                        _to_delete = _idx

        if _to_delete is not None:
            st.session_state.mission_rows.pop(_to_delete)
            st.rerun()

        _ac1, _ac2 = st.columns([3, 1])
        _new_domain = _ac1.text_input("New domain", key="mission_new_key",
                                       label_visibility="collapsed", placeholder="Add a domain…")
        if _ac2.button("＋ Add", key="mission_add") and _new_domain.strip():
            st.session_state.mission_rows.append({"key": _new_domain.strip(), "value": ""})
            st.rerun()

        if not _can_generate:
            st.caption("✨ AI generation requires a paid tier or a configured LLM backend (BYOK).")

        _mission_updated = {
            r["key"]: r["value"]
            for r in st.session_state.mission_rows
            if r["key"].strip()
        }

    with st.expander("🔒 Sensitive Employers (NDA)"):
        st.caption("Companies listed here appear as 'previous employer (NDA)' in research briefs.")
        nda_list = list(_u.get("nda_companies", []))
        if nda_list:
            nda_cols = st.columns(len(nda_list))
            _to_remove = None
            for i, company in enumerate(nda_list):
                if nda_cols[i].button(f"× {company}", key=f"rm_nda_{company}"):
                    _to_remove = company
            if _to_remove:
                nda_list.remove(_to_remove)
        nc, nb = st.columns([4, 1])
        new_nda = nc.text_input("Add employer", key="new_nda",
                                 label_visibility="collapsed", placeholder="Employer name…")
        if nb.button("＋ Add", key="add_nda") and new_nda.strip():
            nda_list.append(new_nda.strip())

    with st.expander("🔍 Research Brief Preferences"):
        st.caption("Optional identity-related sections added to pre-interview research briefs. For your personal decision-making only — never included in applications.")
        u_access_focus = st.checkbox(
            "Include disability & accessibility section",
            value=_u.get("candidate_accessibility_focus", False),
            help="Adds an ADA accommodation, ERG, and WCAG assessment to each company brief.",
        )
        u_lgbtq_focus = st.checkbox(
            "Include LGBTQIA+ inclusion section",
            value=_u.get("candidate_lgbtq_focus", False),
            help="Adds an assessment of the company's LGBTQIA+ ERGs, policies, and culture signals.",
        )

    if st.button("💾 Save Profile", type="primary", key="save_user_profile"):
        # Merge: read existing YAML and update only profile fields, preserving system fields
        _existing = _yaml_up.safe_load(USER_CFG.read_text()) or {} if USER_CFG.exists() else {}
        _existing.update({
            "name": u_name, "email": u_email, "phone": u_phone,
            "linkedin": u_linkedin, "career_summary": u_summary,
            "candidate_voice": u_voice,
            "nda_companies": nda_list,
            "mission_preferences": {k: v for k, v in _mission_updated.items() if v.strip()},
            "candidate_accessibility_focus": u_access_focus,
            "candidate_lgbtq_focus": u_lgbtq_focus,
        })
        save_yaml(USER_CFG, _existing)
        st.success("Profile saved.")
        st.rerun()

# ── Search tab ───────────────────────────────────────────────────────────────
with tab_search:
    cfg = load_yaml(SEARCH_CFG)
    profiles = cfg.get("profiles", [{}])
    p = profiles[0] if profiles else {}

    # Seed session state from config on first load (or when config changes after save)
    _sp_hash = str(p.get("titles", [])) + str(p.get("locations", [])) + str(p.get("exclude_keywords", []))
    if st.session_state.get("_sp_hash") != _sp_hash:
        _saved_titles = list(p.get("titles", []))
        st.session_state["_sp_title_options"] = _saved_titles.copy()
        st.session_state["_sp_titles_multi"] = _saved_titles.copy()
        _saved_locs = list(p.get("locations", []))
        st.session_state["_sp_loc_options"] = _saved_locs.copy()
        st.session_state["_sp_locations_multi"] = _saved_locs.copy()
        st.session_state["_sp_excludes"] = "\n".join(p.get("exclude_keywords", []))
        st.session_state["_sp_hash"] = _sp_hash

    # ── Titles ────────────────────────────────────────────────────────────────
    _title_row, _suggest_btn_col = st.columns([4, 1])
    with _title_row:
        st.subheader("Job Titles to Search")
    with _suggest_btn_col:
        st.write("")
        _run_suggest = st.button("✨ Suggest", key="sp_suggest_btn",
                                  help="Ask the LLM to suggest additional titles and exclude keywords based on your resume")

    st.multiselect(
        "Job titles",
        options=st.session_state.get("_sp_title_options", p.get("titles", [])),
        key="_sp_titles_multi",
        help="Select from known titles. Suggestions from ✨ Suggest appear here — pick the ones you want.",
        label_visibility="collapsed",
    )
    _add_t_col, _add_t_btn = st.columns([5, 1])
    with _add_t_col:
        st.text_input("Add a title", key="_sp_new_title", label_visibility="collapsed",
                      placeholder="Type a title and press ＋")
    with _add_t_btn:
        if st.button("＋", key="sp_add_title_btn", use_container_width=True, help="Add custom title"):
            _t = st.session_state.get("_sp_new_title", "").strip()
            if _t:
                _opts = list(st.session_state.get("_sp_title_options", []))
                _sel  = list(st.session_state.get("_sp_titles_multi", []))
                if _t not in _opts:
                    _opts.append(_t)
                    st.session_state["_sp_title_options"] = _opts
                if _t not in _sel:
                    _sel.append(_t)
                    st.session_state["_sp_titles_multi"] = _sel
                st.session_state["_sp_new_title"] = ""
                st.rerun()
    with st.expander("📋 Paste a list of titles"):
        st.text_area("One title per line", key="_sp_paste_titles", height=80, label_visibility="collapsed",
                     placeholder="Paste one title per line…")
        if st.button("Import", key="sp_import_titles"):
            _new = [t.strip() for t in st.session_state.get("_sp_paste_titles", "").splitlines() if t.strip()]
            _opts = list(st.session_state.get("_sp_title_options", []))
            _sel  = list(st.session_state.get("_sp_titles_multi", []))
            for _t in _new:
                if _t not in _opts:
                    _opts.append(_t)
                if _t not in _sel:
                    _sel.append(_t)
            st.session_state["_sp_title_options"] = _opts
            st.session_state["_sp_titles_multi"] = _sel
            st.session_state["_sp_paste_titles"] = ""
            st.rerun()

    # ── LLM suggestions panel ────────────────────────────────────────────────
    if _run_suggest:
        _current_titles = list(st.session_state.get("_sp_titles_multi", []))
        with st.spinner("Asking LLM for suggestions…"):
            suggestions = _suggest_search_terms(_current_titles, RESUME_PATH)
        # Add suggested titles to options list (not auto-selected — user picks from dropdown)
        _opts = list(st.session_state.get("_sp_title_options", []))
        for _t in suggestions.get("suggested_titles", []):
            if _t not in _opts:
                _opts.append(_t)
        st.session_state["_sp_title_options"] = _opts
        st.session_state["_sp_suggestions"] = suggestions
        st.rerun()

    if st.session_state.get("_sp_suggestions"):
        sugg = st.session_state["_sp_suggestions"]
        s_excl = sugg.get("suggested_excludes", [])
        existing_excl = {e.lower() for e in st.session_state.get("_sp_excludes", "").splitlines() if e.strip()}

        if s_excl:
            st.caption("**Suggested exclusions** — click to add:")
            cols2 = st.columns(min(len(s_excl), 4))
            for i, kw in enumerate(s_excl):
                with cols2[i % 4]:
                    if kw.lower() not in existing_excl:
                        if st.button(f"+ {kw}", key=f"sp_add_excl_{i}"):
                            st.session_state["_sp_excludes"] = (
                                st.session_state.get("_sp_excludes", "").rstrip("\n") + f"\n{kw}"
                            )
                            st.rerun()
                    else:
                        st.caption(f"✓ {kw}")

        if st.button("✕ Clear suggestions", key="sp_clear_sugg"):
            st.session_state.pop("_sp_suggestions", None)
            st.rerun()

    # ── Locations ─────────────────────────────────────────────────────────────
    st.subheader("Locations")
    st.multiselect(
        "Locations",
        options=st.session_state.get("_sp_loc_options", p.get("locations", [])),
        key="_sp_locations_multi",
        help="Select from known locations or add your own below.",
        label_visibility="collapsed",
    )
    _add_l_col, _add_l_btn = st.columns([5, 1])
    with _add_l_col:
        st.text_input("Add a location", key="_sp_new_loc", label_visibility="collapsed",
                      placeholder="Type a location and press ＋")
    with _add_l_btn:
        if st.button("＋", key="sp_add_loc_btn", use_container_width=True, help="Add custom location"):
            _l = st.session_state.get("_sp_new_loc", "").strip()
            if _l:
                _opts = list(st.session_state.get("_sp_loc_options", []))
                _sel  = list(st.session_state.get("_sp_locations_multi", []))
                if _l not in _opts:
                    _opts.append(_l)
                    st.session_state["_sp_loc_options"] = _opts
                if _l not in _sel:
                    _sel.append(_l)
                    st.session_state["_sp_locations_multi"] = _sel
                st.session_state["_sp_new_loc"] = ""
                st.rerun()
    with st.expander("📋 Paste a list of locations"):
        st.text_area("One location per line", key="_sp_paste_locs", height=80, label_visibility="collapsed",
                     placeholder="Paste one location per line…")
        if st.button("Import", key="sp_import_locs"):
            _new = [l.strip() for l in st.session_state.get("_sp_paste_locs", "").splitlines() if l.strip()]
            _opts = list(st.session_state.get("_sp_loc_options", []))
            _sel  = list(st.session_state.get("_sp_locations_multi", []))
            for _l in _new:
                if _l not in _opts:
                    _opts.append(_l)
                if _l not in _sel:
                    _sel.append(_l)
            st.session_state["_sp_loc_options"] = _opts
            st.session_state["_sp_locations_multi"] = _sel
            st.session_state["_sp_paste_locs"] = ""
            st.rerun()

    st.subheader("Exclude Keywords")
    st.caption("Jobs whose **title or description** contain any of these words are silently dropped before entering the queue. Case-insensitive.")
    exclude_text = st.text_area(
        "One keyword or phrase per line",
        key="_sp_excludes",
        height=150,
        help="e.g. 'sales', 'account executive', 'SDR'",
    )

    st.subheader("Job Boards")
    board_options = ["linkedin", "indeed", "glassdoor", "zip_recruiter", "google"]
    selected_boards = st.multiselect(
        "Standard boards (via JobSpy)", board_options,
        default=[b for b in p.get("boards", board_options) if b in board_options],
        help="Google Jobs aggregates listings from many sources and often finds roles the other boards miss.",
    )

    _custom_board_options = ["adzuna", "theladders"]
    _custom_board_labels = {
        "adzuna":     "Adzuna (free API — requires app_id + app_key in config/adzuna.yaml)",
        "theladders": "The Ladders (curl_cffi scraper — $100K+ roles, requires curl_cffi)",
    }
    st.caption("**Custom boards** — scrapers built into this app, not part of JobSpy.")
    selected_custom = st.multiselect(
        "Custom boards",
        options=_custom_board_options,
        default=[b for b in p.get("custom_boards", []) if b in _custom_board_options],
        format_func=lambda b: _custom_board_labels.get(b, b),
    )

    col1, col2 = st.columns(2)
    results_per = col1.slider("Results per board", 5, 100, p.get("results_per_board", 25))
    hours_old = col2.slider("How far back to look (hours)", 24, 720, p.get("hours_old", 72))

    if st.button("💾 Save search settings", type="primary"):
        profiles[0] = {
            **p,
            "titles": list(st.session_state.get("_sp_titles_multi", [])),
            "locations": list(st.session_state.get("_sp_locations_multi", [])),
            "boards": selected_boards,
            "custom_boards": selected_custom,
            "results_per_board": results_per,
            "hours_old": hours_old,
            "exclude_keywords": [k.strip() for k in exclude_text.splitlines() if k.strip()],
        }
        save_yaml(SEARCH_CFG, {"profiles": profiles})
        st.session_state["_sp_hash"] = ""  # force re-seed on next load
        st.session_state.pop("_sp_suggestions", None)
        st.success("Search settings saved!")

    st.divider()

    # ── Blocklist ──────────────────────────────────────────────────────────────
    with st.expander("🚫 Blocklist — companies, industries, and locations I will never work at", expanded=False):
        st.caption(
            "Listings matching any rule below are **silently dropped before entering the review queue**, "
            "across all search profiles and custom boards. Changes take effect on the next discovery run."
        )
        bl = load_yaml(BLOCKLIST_CFG)

        bl_companies = st.text_area(
            "Company names (partial match, one per line)",
            value="\n".join(bl.get("companies", [])),
            height=120,
            help="e.g. 'Amazon' blocks any listing where the company name contains 'amazon' (case-insensitive).",
            key="bl_companies",
        )
        bl_industries = st.text_area(
            "Industry / content keywords (one per line)",
            value="\n".join(bl.get("industries", [])),
            height=100,
            help="Blocked if the keyword appears in the company name OR job description. "
                 "e.g. 'gambling', 'crypto', 'tobacco', 'defense contractor'.",
            key="bl_industries",
        )
        bl_locations = st.text_area(
            "Location strings to exclude (one per line)",
            value="\n".join(bl.get("locations", [])),
            height=80,
            help="e.g. 'Dallas' blocks any listing whose location contains 'dallas'.",
            key="bl_locations",
        )

        if st.button("💾 Save blocklist", type="primary", key="save_blocklist"):
            save_yaml(BLOCKLIST_CFG, {
                "companies":  [c.strip() for c in bl_companies.splitlines() if c.strip()],
                "industries": [i.strip() for i in bl_industries.splitlines() if i.strip()],
                "locations":  [loc.strip() for loc in bl_locations.splitlines() if loc.strip()],
            })
            st.success("Blocklist saved — takes effect on next discovery run.")

# ── Resume Profile tab ────────────────────────────────────────────────────────

def _upload_resume_widget(key_prefix: str) -> None:
    """Upload + parse + save a resume file. Overwrites config/plain_text_resume.yaml on success."""
    _uf = st.file_uploader(
        "Upload resume (PDF, DOCX, or ODT)",
        type=["pdf", "docx", "odt"],
        key=f"{key_prefix}_file",
    )
    if _uf and st.button("Parse & Save", type="primary", key=f"{key_prefix}_parse"):
        from scripts.resume_parser import (
            extract_text_from_pdf, extract_text_from_docx,
            extract_text_from_odt, structure_resume,
        )
        _fb = _uf.read()
        _ext = _uf.name.rsplit(".", 1)[-1].lower()
        if _ext == "pdf":
            _raw = extract_text_from_pdf(_fb)
        elif _ext == "odt":
            _raw = extract_text_from_odt(_fb)
        else:
            _raw = extract_text_from_docx(_fb)
        with st.spinner("Parsing resume…"):
            _parsed, _perr = structure_resume(_raw)
        if _parsed and any(_parsed.get(k) for k in ("name", "experience", "skills")):
            RESUME_PATH.parent.mkdir(parents=True, exist_ok=True)
            RESUME_PATH.write_text(yaml.dump(_parsed, default_flow_style=False, allow_unicode=True))
            # Persist raw text to user.yaml for LLM context
            if USER_CFG.exists():
                _uy = yaml.safe_load(USER_CFG.read_text()) or {}
                _uy["resume_raw_text"] = _raw[:8000]
                save_yaml(USER_CFG, _uy)
            st.success("Resume parsed and saved!")
            st.rerun()
        else:
            st.warning(
                f"Parsing found limited data — try a different file format. "
                f"{('Error: ' + _perr) if _perr else ''}"
            )

with tab_resume:
    st.caption(
        f"Edit {_name}'s application profile. "
        "Bullets are used as paste-able shortcuts in the Apply Workspace."
    )

    if not RESUME_PATH.exists():
        st.info(
            "No resume profile found yet. Upload your resume below to get started, "
            "or re-run the [Setup wizard](/0_Setup) to build one step-by-step."
        )
        _upload_resume_widget("rp_new")
        st.stop()

    with st.expander("🔄 Replace Resume"):
        st.caption("Re-upload to overwrite your saved profile. Parsed fields will replace the current data.")
        _upload_resume_widget("rp_replace")

    _data = yaml.safe_load(RESUME_PATH.read_text()) or {}

    if "FILL_IN" in RESUME_PATH.read_text():
        st.info(
            "Some fields still need attention (marked ⚠️ below). "
            "Re-upload your resume above to auto-fill them, or "
            "re-run the [Setup wizard](/0_Setup) to fill them step-by-step."
        )

    def _field(label: str, value: str, key: str, help: str = "", password: bool = False) -> str:
        needs_attention = str(value).startswith("FILL_IN") or value == ""
        if needs_attention:
            st.markdown(
                '<p style="color:#F59E0B;font-size:0.8em;margin-bottom:2px">⚠️ Needs attention</p>',
                unsafe_allow_html=True,
            )
        return st.text_input(label, value=value or "", key=key, help=help,
                             type="password" if password else "default")

    # ── Personal Info ─────────────────────────────────────────────────────────
    with st.expander("👤 Personal Information", expanded=True):
        _info = _data.get("personal_information", {})
        _c1, _c2 = st.columns(2)
        with _c1:
            _name     = _field("First Name", _info.get("name", ""),    "rp_name")
            _email    = _field("Email",      _info.get("email", ""),   "rp_email")
            _phone    = _field("Phone",      _info.get("phone", ""),   "rp_phone")
            _city     = _field("City",       _info.get("city", ""),    "rp_city")
        with _c2:
            _surname  = _field("Last Name",  _info.get("surname", ""), "rp_surname")
            _linkedin = _field("LinkedIn URL", _info.get("linkedin", ""), "rp_linkedin")
            _zip_code = _field("Zip Code",   _info.get("zip_code", ""), "rp_zip")
            _dob      = _field("Date of Birth", _info.get("date_of_birth", ""), "rp_dob",
                               help="MM/DD/YYYY")
        _address = _field("Street Address", _info.get("address", ""), "rp_address",
                          help="Used in job applications. Not shown on your resume.")

    # ── Experience ────────────────────────────────────────────────────────────
    with st.expander("💼 Work Experience"):
        _exp_list = _data.get("experience_details", [{}])
        if "rp_exp_count" not in st.session_state:
            st.session_state.rp_exp_count = len(_exp_list)
        if st.button("+ Add Experience Entry", key="rp_add_exp"):
            st.session_state.rp_exp_count += 1
            _exp_list.append({})

        _updated_exp = []
        for _i in range(st.session_state.rp_exp_count):
            _exp = _exp_list[_i] if _i < len(_exp_list) else {}
            st.markdown(f"**Position {_i + 1}**")
            _ec1, _ec2 = st.columns(2)
            with _ec1:
                _pos    = _field("Job Title",    _exp.get("position", ""),          f"rp_pos_{_i}")
                _co     = _field("Company",      _exp.get("company", ""),           f"rp_co_{_i}")
                _period = _field("Period",        _exp.get("employment_period", ""), f"rp_period_{_i}",
                                 help="e.g. 01/2022 - Present")
            with _ec2:
                _loc = st.text_input("Location", _exp.get("location", ""), key=f"rp_loc_{_i}")
                _ind = st.text_input("Industry", _exp.get("industry", ""), key=f"rp_ind_{_i}")
            _resp_raw = st.text_area(
                "Key Responsibilities (one per line)",
                value="\n".join(
                    r.get(f"responsibility_{j+1}", "") if isinstance(r, dict) else str(r)
                    for j, r in enumerate(_exp.get("key_responsibilities", []))
                ),
                key=f"rp_resp_{_i}", height=100,
            )
            _skills_raw = st.text_input(
                "Skills (comma-separated)",
                value=", ".join(_exp.get("skills_acquired", [])),
                key=f"rp_skills_{_i}",
            )
            _updated_exp.append({
                "position": _pos, "company": _co, "employment_period": _period,
                "location": _loc, "industry": _ind,
                "key_responsibilities": [{"responsibility_1": r.strip()} for r in _resp_raw.splitlines() if r.strip()],
                "skills_acquired": [s.strip() for s in _skills_raw.split(",") if s.strip()],
            })
            st.divider()

    # ── Preferences ───────────────────────────────────────────────────────────
    with st.expander("⚙️ Preferences & Availability"):
        _wp   = _data.get("work_preferences", {})
        _sal  = _data.get("salary_expectations", {})
        _avail = _data.get("availability", {})
        _pc1, _pc2 = st.columns(2)
        with _pc1:
            _salary_range = st.text_input("Salary Range (USD)", _sal.get("salary_range_usd", ""),
                                          key="rp_salary", help="e.g. 120000 - 180000")
            _notice = st.text_input("Notice Period", _avail.get("notice_period", "2 weeks"), key="rp_notice")
        with _pc2:
            _remote      = st.checkbox("Open to Remote",     value=_wp.get("remote_work", "Yes") == "Yes",         key="rp_remote")
            _reloc       = st.checkbox("Open to Relocation", value=_wp.get("open_to_relocation", "No") == "Yes",   key="rp_reloc")
            _assessments = st.checkbox("Willing to complete assessments",
                                       value=_wp.get("willing_to_complete_assessments", "Yes") == "Yes",           key="rp_assess")
            _bg          = st.checkbox("Willing to undergo background checks",
                                       value=_wp.get("willing_to_undergo_background_checks", "Yes") == "Yes",      key="rp_bg")

    # ── Self-ID ───────────────────────────────────────────────────────────────
    with st.expander("🏳️‍🌈 Self-Identification (optional)"):
        _sid = _data.get("self_identification", {})
        _sc1, _sc2 = st.columns(2)
        with _sc1:
            _gender    = st.text_input("Gender identity", _sid.get("gender", "Non-binary"),   key="rp_gender")
            _pronouns  = st.text_input("Pronouns",        _sid.get("pronouns", "Any"),         key="rp_pronouns")
            _ethnicity = _field("Ethnicity", _sid.get("ethnicity", ""), "rp_ethnicity")
        with _sc2:
            _vet_opts = ["No", "Yes", "Prefer not to say"]
            _veteran  = st.selectbox("Veteran status", _vet_opts,
                                     index=_vet_opts.index(_sid.get("veteran", "No")), key="rp_vet")
            _dis_opts = ["Prefer not to say", "No", "Yes"]
            _disability = st.selectbox("Disability disclosure", _dis_opts,
                                       index=_dis_opts.index(_sid.get("disability", "Prefer not to say")),
                                       key="rp_dis")

    st.divider()
    if st.button("💾 Save Resume Profile", type="primary", use_container_width=True, key="rp_save"):
        _data["personal_information"] = {
            **_data.get("personal_information", {}),
            "name": _name, "surname": _surname, "email": _email, "phone": _phone,
            "city": _city, "zip_code": _zip_code, "address": _address,
            "linkedin": _linkedin, "date_of_birth": _dob,
        }
        _data["experience_details"] = _updated_exp
        _data["salary_expectations"] = {"salary_range_usd": _salary_range}
        _data["availability"] = {"notice_period": _notice}
        _data["work_preferences"] = {
            **_data.get("work_preferences", {}),
            "remote_work": "Yes" if _remote else "No",
            "open_to_relocation": "Yes" if _reloc else "No",
            "willing_to_complete_assessments": "Yes" if _assessments else "No",
            "willing_to_undergo_background_checks": "Yes" if _bg else "No",
        }
        _data["self_identification"] = {
            "gender": _gender, "pronouns": _pronouns, "veteran": _veteran,
            "disability": _disability, "ethnicity": _ethnicity,
        }
        RESUME_PATH.write_text(yaml.dump(_data, default_flow_style=False, allow_unicode=True))
        st.success("✅ Resume profile saved!")
        st.balloons()

    st.divider()
    st.subheader("🏷️ Skills & Keywords")
    st.caption(
        f"Matched against job descriptions to surface {_name}'s most relevant experience "
        "and highlight keyword overlap in research briefs. Search the bundled list or add your own."
    )

    from scripts.skills_utils import load_suggestions as _load_sugg, filter_tag as _filter_tag

    if not KEYWORDS_CFG.exists():
        st.warning("resume_keywords.yaml not found — create it at config/resume_keywords.yaml")
    else:
        kw_data = load_yaml(KEYWORDS_CFG)
        kw_changed = False

        _KW_META = {
            "skills":   ("🛠️ Skills",   "e.g. Customer Success, SQL, Project Management"),
            "domains":  ("🏢 Domains",  "e.g. B2B SaaS, EdTech, Non-profit"),
            "keywords": ("🔑 Keywords", "e.g. NPS, churn prevention, cross-functional"),
        }

        for kw_category, (kw_label, kw_placeholder) in _KW_META.items():
            st.markdown(f"**{kw_label}**")
            kw_current: list[str] = kw_data.get(kw_category, [])
            kw_suggestions = _load_sugg(kw_category)

            # Merge: suggestions first, then any custom tags not in suggestions
            kw_custom = [t for t in kw_current if t not in kw_suggestions]
            kw_options = kw_suggestions + kw_custom

            kw_selected = st.multiselect(
                kw_label,
                options=kw_options,
                default=[t for t in kw_current if t in kw_options],
                key=f"kw_ms_{kw_category}",
                label_visibility="collapsed",
                help=f"Search and select from the bundled list, or add custom tags below.",
            )

            # Custom tag input — for entries not in the suggestions list
            kw_add_col, kw_btn_col = st.columns([5, 1])
            kw_raw = kw_add_col.text_input(
                "Custom tag", key=f"kw_custom_{kw_category}",
                label_visibility="collapsed",
                placeholder=f"Custom: {kw_placeholder}",
            )
            if kw_btn_col.button("＋", key=f"kw_add_{kw_category}", help="Add custom tag"):
                cleaned = _filter_tag(kw_raw)
                if cleaned is None:
                    st.warning(f"'{kw_raw}' was rejected — check length, characters, or content.")
                elif cleaned in kw_options:
                    st.info(f"'{cleaned}' is already in the list — select it above.")
                else:
                    # Persist custom tag: add to YAML and session state so it appears in options
                    kw_new_list = kw_selected + [cleaned]
                    kw_data[kw_category] = kw_new_list
                    kw_changed = True

            # Detect multiselect changes
            if sorted(kw_selected) != sorted(kw_current):
                kw_data[kw_category] = kw_selected
                kw_changed = True

            st.markdown("---")

        if kw_changed:
            save_yaml(KEYWORDS_CFG, kw_data)
            st.rerun()

# ── System tab ────────────────────────────────────────────────────────────────
with tab_system:
    st.caption("Infrastructure, LLM backends, integrations, and service connections.")

    # ── File Paths & Inference ────────────────────────────────────────────────
    with st.expander("📁 File Paths & Inference Profile"):
        _su = _yaml_up.safe_load(USER_CFG.read_text()) or {} if USER_CFG.exists() else {}
        _ssvc = {**_UP_DEFAULTS["services"], **_su.get("services", {})}
        s_docs   = st.text_input("Documents directory",     _su.get("docs_dir", "~/Documents/JobSearch"))
        s_ollama = st.text_input("Ollama models directory", _su.get("ollama_models_dir", "~/models/ollama"))
        s_vllm   = st.text_input("vLLM models directory",   _su.get("vllm_models_dir", "~/models/vllm"))
        _inf_profiles = ["remote", "cpu", "single-gpu", "dual-gpu"]
        s_inf_profile = st.selectbox("Inference profile", _inf_profiles,
                                      index=_inf_profiles.index(_su.get("inference_profile", "remote")))

    # ── Service Hosts & Ports ─────────────────────────────────────────────────
    with st.expander("🔌 Service Hosts & Ports"):
        st.caption("Advanced — change only if services run on non-default ports or remote hosts.")
        ssc1, ssc2, ssc3 = st.columns(3)
        with ssc1:
            st.markdown("**Ollama**")
            s_ollama_host   = st.text_input("Host",       _ssvc["ollama_host"],        key="sys_ollama_host")
            s_ollama_port   = st.number_input("Port",     value=_ssvc["ollama_port"],  step=1, key="sys_ollama_port")
            s_ollama_ssl    = st.checkbox("SSL",          _ssvc["ollama_ssl"],          key="sys_ollama_ssl")
            s_ollama_verify = st.checkbox("Verify cert",  _ssvc["ollama_ssl_verify"],   key="sys_ollama_verify")
        with ssc2:
            st.markdown("**vLLM**")
            s_vllm_host   = st.text_input("Host",         _ssvc["vllm_host"],          key="sys_vllm_host")
            s_vllm_port   = st.number_input("Port",       value=_ssvc["vllm_port"],    step=1, key="sys_vllm_port")
            s_vllm_ssl    = st.checkbox("SSL",            _ssvc["vllm_ssl"],            key="sys_vllm_ssl")
            s_vllm_verify = st.checkbox("Verify cert",    _ssvc["vllm_ssl_verify"],     key="sys_vllm_verify")
        with ssc3:
            st.markdown("**SearXNG**")
            s_sxng_host   = st.text_input("Host",         _ssvc["searxng_host"],       key="sys_sxng_host")
            s_sxng_port   = st.number_input("Port",       value=_ssvc["searxng_port"], step=1, key="sys_sxng_port")
            s_sxng_ssl    = st.checkbox("SSL",            _ssvc["searxng_ssl"],          key="sys_sxng_ssl")
            s_sxng_verify = st.checkbox("Verify cert",    _ssvc["searxng_ssl_verify"],   key="sys_sxng_verify")

    if st.button("💾 Save System Settings", type="primary", key="save_system"):
        _sys_existing = _yaml_up.safe_load(USER_CFG.read_text()) or {} if USER_CFG.exists() else {}
        _sys_existing.update({
            "docs_dir": s_docs, "ollama_models_dir": s_ollama, "vllm_models_dir": s_vllm,
            "inference_profile": s_inf_profile,
            "services": {
                "streamlit_port": _ssvc["streamlit_port"],
                "ollama_host": s_ollama_host, "ollama_port": int(s_ollama_port),
                "ollama_ssl": s_ollama_ssl, "ollama_ssl_verify": s_ollama_verify,
                "vllm_host": s_vllm_host, "vllm_port": int(s_vllm_port),
                "vllm_ssl": s_vllm_ssl, "vllm_ssl_verify": s_vllm_verify,
                "searxng_host": s_sxng_host, "searxng_port": int(s_sxng_port),
                "searxng_ssl": s_sxng_ssl, "searxng_ssl_verify": s_sxng_verify,
            },
        })
        save_yaml(USER_CFG, _sys_existing)
        from scripts.generate_llm_config import apply_service_urls as _apply_urls
        _apply_urls(_UP(USER_CFG), LLM_CFG)
        st.success("System settings saved and service URLs updated.")
        st.rerun()

    st.divider()

    # ── Deployment / Server ───────────────────────────────────────────────────
    with st.expander("🖥️ Deployment / Server", expanded=False):
        st.caption(
            "Settings that affect how Peregrine is served. "
            "Changes require a restart (`./manage.sh restart`) to take effect."
        )

        _srv = _yaml_up.safe_load(SERVER_CFG.read_text()) if SERVER_CFG.exists() else {}
        _srv_example = _yaml_up.safe_load(SERVER_CFG_EXAMPLE.read_text()) if SERVER_CFG_EXAMPLE.exists() else {}
        _srv_defaults = {**_srv_example, **_srv}

        _active_base_url = _os.environ.get("STREAMLIT_SERVER_BASE_URL_PATH", "")
        if _active_base_url:
            st.info(f"**Active base URL path:** `/{_active_base_url}` (set via environment)")
        else:
            st.info("**Active base URL path:** *(none — serving at root `/`)*")

        s_base_url = st.text_input(
            "Base URL path",
            value=_srv_defaults.get("base_url_path", ""),
            placeholder="e.g. peregrine",
            help=(
                "URL prefix when serving behind a reverse proxy at a sub-path. "
                "Leave empty for direct access. "
                "Maps to STREAMLIT_BASE_URL_PATH in .env.\n\n"
                "Docs: https://docs.streamlit.io/develop/api-reference/configuration/config.toml#server.baseUrlPath"
            ),
        )
        s_server_port = st.number_input(
            "Container port",
            value=int(_srv_defaults.get("server_port", 8501)),
            min_value=1024, max_value=65535, step=1,
            help="Port Streamlit listens on inside the container. The host port is set via STREAMLIT_PORT in .env.",
        )

        if st.button("💾 Save Deployment Settings", key="save_server"):
            _new_srv = {"base_url_path": s_base_url.strip(), "server_port": int(s_server_port)}
            save_yaml(SERVER_CFG, _new_srv)
            # Mirror base_url_path into .env so compose picks it up on next restart
            _env_path = Path(__file__).parent.parent.parent / ".env"
            if _env_path.exists():
                _env_lines = [l for l in _env_path.read_text().splitlines()
                               if not l.startswith("STREAMLIT_BASE_URL_PATH=")]
                _env_lines.append(f"STREAMLIT_BASE_URL_PATH={s_base_url.strip()}")
                _env_path.write_text("\n".join(_env_lines) + "\n")
            st.success("Deployment settings saved. Run `./manage.sh restart` to apply.")

    st.divider()

    # ── LLM Backends ─────────────────────────────────────────────────────────
    with st.expander("🤖 LLM Backends", expanded=False):
        import requests as _req

        def _ollama_models(base_url: str) -> list[str]:
            try:
                r = _req.get(base_url.rstrip("/v1").rstrip("/") + "/api/tags", timeout=2)
                if r.ok:
                    return [m["name"] for m in r.json().get("models", [])]
            except Exception:
                pass
            return []

        llm_cfg = load_yaml(LLM_CFG)
        llm_backends = llm_cfg.get("backends", {})
        llm_fallback_order = llm_cfg.get("fallback_order", list(llm_backends.keys()))

        _llm_cfg_key = str(llm_fallback_order)
        if st.session_state.get("_llm_order_cfg_key") != _llm_cfg_key:
            st.session_state["_llm_order"] = list(llm_fallback_order)
            st.session_state["_llm_order_cfg_key"] = _llm_cfg_key
        llm_new_order: list[str] = st.session_state["_llm_order"]
        llm_all_names = list(llm_new_order) + [n for n in llm_backends if n not in llm_new_order]

        st.caption("Enable/disable backends and set priority with ↑ ↓. First enabled + reachable backend wins.")
        llm_updated_backends = {}
        for llm_name in llm_all_names:
            b = llm_backends.get(llm_name, {})
            llm_enabled = b.get("enabled", True)
            llm_label = llm_name.replace("_", " ").title()
            llm_pos = llm_new_order.index(llm_name) + 1 if llm_name in llm_new_order else "—"
            llm_header = f"{'🟢' if llm_enabled else '⚫'} **{llm_pos}. {llm_label}**"
            with st.expander(llm_header, expanded=False):
                llm_c1, llm_c2, llm_c3, llm_c4 = st.columns([2, 1, 1, 4])
                llm_new_enabled = llm_c1.checkbox("Enabled", value=llm_enabled, key=f"{llm_name}_enabled")
                if llm_name in llm_new_order:
                    llm_idx = llm_new_order.index(llm_name)
                    if llm_c2.button("↑", key=f"{llm_name}_up", disabled=llm_idx == 0):
                        llm_new_order[llm_idx], llm_new_order[llm_idx-1] = llm_new_order[llm_idx-1], llm_new_order[llm_idx]
                        st.session_state["_llm_order"] = llm_new_order
                        st.rerun()
                    if llm_c3.button("↓", key=f"{llm_name}_dn", disabled=llm_idx == len(llm_new_order)-1):
                        llm_new_order[llm_idx], llm_new_order[llm_idx+1] = llm_new_order[llm_idx+1], llm_new_order[llm_idx]
                        st.session_state["_llm_order"] = llm_new_order
                        st.rerun()
                if b.get("type") == "openai_compat":
                    llm_url = st.text_input("URL", value=b.get("base_url", ""), key=f"{llm_name}_url")
                    if llm_name == "ollama":
                        llm_om = _ollama_models(b.get("base_url", "http://localhost:11434"))
                        llm_cur = b.get("model", "")
                        if llm_om:
                            llm_model = st.selectbox("Model", llm_om,
                                index=llm_om.index(llm_cur) if llm_cur in llm_om else 0,
                                key=f"{llm_name}_model",
                                help="Lists models currently installed in Ollama.")
                        else:
                            st.caption("_Ollama not reachable — enter model name manually. Start it in the **Services** section below._")
                            llm_model = st.text_input("Model", value=llm_cur, key=f"{llm_name}_model")
                    else:
                        llm_model = st.text_input("Model", value=b.get("model", ""), key=f"{llm_name}_model")
                    llm_updated_backends[llm_name] = {**b, "base_url": llm_url, "model": llm_model, "enabled": llm_new_enabled}
                elif b.get("type") == "anthropic":
                    llm_model = st.text_input("Model", value=b.get("model", ""), key=f"{llm_name}_model")
                    llm_updated_backends[llm_name] = {**b, "model": llm_model, "enabled": llm_new_enabled}
                else:
                    llm_updated_backends[llm_name] = {**b, "enabled": llm_new_enabled}
                if b.get("type") == "openai_compat":
                    if st.button("Test connection", key=f"test_{llm_name}"):
                        with st.spinner("Testing…"):
                            try:
                                from scripts.llm_router import LLMRouter as _LR
                                reachable = _LR()._is_reachable(b.get("base_url", ""))
                                st.success("Reachable ✓") if reachable else st.warning("Not reachable ✗")
                            except Exception as e:
                                st.error(f"Error: {e}")

        st.caption("Priority: " + " → ".join(
            f"{'✓' if llm_backends.get(n, {}).get('enabled', True) else '✗'} {n}"
            for n in llm_new_order
        ))
        if st.button("💾 Save LLM settings", type="primary", key="sys_save_llm"):
            save_yaml(LLM_CFG, {**llm_cfg, "backends": llm_updated_backends, "fallback_order": llm_new_order})
            st.session_state.pop("_llm_order", None)
            st.session_state.pop("_llm_order_cfg_key", None)
            st.success("LLM settings saved!")

    # ── Services ──────────────────────────────────────────────────────────────
    with st.expander("🔌 Services", expanded=True):
        import subprocess as _sp
        import shutil as _shutil
        TOKENS_CFG = CONFIG_DIR / "tokens.yaml"
        COMPOSE_DIR = str(Path(__file__).parent.parent.parent)
        _docker_available = bool(_shutil.which("docker"))
        _sys_profile_name = _profile.inference_profile if _profile else "remote"
        SYS_SERVICES = [
            {
                "name": "Streamlit UI",
                "port": _profile._svc["streamlit_port"] if _profile else 8501,
                "start": ["docker", "compose", "--profile", _sys_profile_name, "up", "-d", "app"],
                "stop":  ["docker", "compose", "stop", "app"],
                "cwd":   COMPOSE_DIR, "note": "Peregrine web interface",
            },
            {
                "name": "Ollama (local LLM)",
                "port": _profile._svc["ollama_port"] if _profile else 11434,
                "start": ["docker", "compose", "--profile", _sys_profile_name, "up", "-d", "ollama"],
                "stop":  ["docker", "compose", "stop", "ollama"],
                "cwd":   COMPOSE_DIR,
                "note":  f"Local inference — profile: {_sys_profile_name}",
                "hidden": _sys_profile_name == "remote",
            },
            {
                "name": "vLLM Server",
                "port": _profile._svc["vllm_port"] if _profile else 8000,
                "start": ["docker", "compose", "--profile", _sys_profile_name, "up", "-d", "vllm"],
                "stop":  ["docker", "compose", "stop", "vllm"],
                "cwd":   COMPOSE_DIR,
                "model_dir": str(_profile.vllm_models_dir) if _profile else str(Path.home() / "models" / "vllm"),
                "note":  "vLLM inference — dual-gpu profile only",
                "hidden": _sys_profile_name != "dual-gpu",
            },
            {
                "name": "Vision Service (moondream2)",
                "port": 8002,
                "start": ["docker", "compose", "--profile", _sys_profile_name, "up", "-d", "vision"],
                "stop":  ["docker", "compose", "stop", "vision"],
                "cwd":   COMPOSE_DIR, "note": "Screenshot analysis for survey assistant",
                "hidden": _sys_profile_name not in ("single-gpu", "dual-gpu"),
            },
            {
                "name": "SearXNG (company scraper)",
                "port": _profile._svc["searxng_port"] if _profile else 8888,
                "start": ["docker", "compose", "up", "-d", "searxng"],
                "stop":  ["docker", "compose", "stop", "searxng"],
                "cwd":   COMPOSE_DIR, "note": "Privacy-respecting meta-search for company research",
            },
        ]
        SYS_SERVICES = [s for s in SYS_SERVICES if not s.get("hidden")]

        def _port_open(port: int, host: str = "127.0.0.1", ssl: bool = False, verify: bool = True) -> bool:
            try:
                import requests as _r
                scheme = "https" if ssl else "http"
                _r.get(f"{scheme}://{host}:{port}/", timeout=1, verify=verify)
                return True
            except Exception:
                return False

        st.caption("Monitor and control backend services. Status checked live on each page load.")
        for svc in SYS_SERVICES:
            _sh = "127.0.0.1"
            _ss = False
            _sv = True
            if _profile:
                _sh = _profile._svc.get(f"{svc['name'].split()[0].lower()}_host", "127.0.0.1")
                _ss = _profile._svc.get(f"{svc['name'].split()[0].lower()}_ssl", False)
                _sv = _profile._svc.get(f"{svc['name'].split()[0].lower()}_ssl_verify", True)
            up = _port_open(svc["port"], host=_sh, ssl=_ss, verify=_sv)
            with st.container(border=True):
                lc, rc = st.columns([3, 1])
                with lc:
                    st.markdown(f"**{svc['name']}** — {'🟢 Running' if up else '🔴 Stopped'}")
                    st.caption(f"Port {svc['port']} · {svc['note']}")
                    if "model_dir" in svc:
                        _mdir = Path(svc["model_dir"])
                        _models = sorted(d.name for d in _mdir.iterdir() if d.is_dir()) if _mdir.exists() else []
                        _mk = f"svc_model_{svc['port']}"
                        _loaded_file = Path("/tmp/vllm-server.model")
                        _loaded = _loaded_file.read_text().strip() if _loaded_file.exists() else ""
                        if _models:
                            st.selectbox("Model", _models,
                                index=_models.index(_loaded) if _loaded in _models else 0,
                                key=_mk)
                        else:
                            st.caption(f"_No models found in `{svc['model_dir']}` — train one in the **🎯 Fine-Tune** tab above_")
                with rc:
                    if svc.get("start") is None or not _docker_available:
                        _hint_cmd = " ".join(svc.get("start") or [])
                        st.caption(f"_Run from host terminal:_")
                        st.code(_hint_cmd, language=None)
                    elif up:
                        if st.button("⏹ Stop", key=f"sys_svc_stop_{svc['port']}", use_container_width=True):
                            with st.spinner(f"Stopping {svc['name']}…"):
                                r = _sp.run(svc["stop"], capture_output=True, text=True, cwd=svc["cwd"])
                            st.success("Stopped.") if r.returncode == 0 else st.error(r.stderr or r.stdout)
                            st.rerun()
                    else:
                        _start_cmd = list(svc["start"])
                        if "model_dir" in svc:
                            _sel = st.session_state.get(f"svc_model_{svc['port']}")
                            if _sel:
                                _start_cmd.append(_sel)
                        if st.button("▶ Start", key=f"sys_svc_start_{svc['port']}", use_container_width=True, type="primary"):
                            with st.spinner(f"Starting {svc['name']}…"):
                                r = _sp.run(_start_cmd, capture_output=True, text=True, cwd=svc["cwd"])
                            st.success("Started!") if r.returncode == 0 else st.error(r.stderr or r.stdout)
                            st.rerun()

    # ── Email ─────────────────────────────────────────────────────────────────
    with st.expander("📧 Email"):
        EMAIL_CFG = CONFIG_DIR / "email.yaml"
        if not EMAIL_CFG.exists():
            st.info("No email config found — fill in credentials below and click Save to create it.")
        em_cfg = load_yaml(EMAIL_CFG) if EMAIL_CFG.exists() else {}
        em_c1, em_c2 = st.columns(2)
        with em_c1:
            em_host = st.text_input("IMAP Host", em_cfg.get("host", "imap.gmail.com"), key="sys_em_host")
            em_port = st.number_input("Port", value=int(em_cfg.get("port", 993)), min_value=1, max_value=65535, key="sys_em_port")
            em_ssl  = st.checkbox("Use SSL", value=em_cfg.get("use_ssl", True), key="sys_em_ssl")
        with em_c2:
            em_user = st.text_input("Username (email)", em_cfg.get("username", ""), key="sys_em_user")
            em_pass = st.text_input("Password / App Password", em_cfg.get("password", ""), type="password", key="sys_em_pass")
            em_sent = st.text_input("Sent folder (blank = auto-detect)", em_cfg.get("sent_folder", ""),
                                    key="sys_em_sent", placeholder='e.g. "[Gmail]/Sent Mail"')
        em_days = st.slider("Look-back window (days)", 14, 365, int(em_cfg.get("lookback_days", 90)), key="sys_em_days")
        st.caption("**Gmail users:** create an App Password at myaccount.google.com/apppasswords. Enable IMAP at Gmail Settings → Forwarding and POP/IMAP.")
        em_s1, em_s2 = st.columns(2)
        if em_s1.button("💾 Save Email", type="primary", key="sys_em_save"):
            save_yaml(EMAIL_CFG, {
                "host": em_host, "port": int(em_port), "use_ssl": em_ssl,
                "username": em_user, "password": em_pass,
                "sent_folder": em_sent, "lookback_days": int(em_days),
            })
            EMAIL_CFG.chmod(0o600)
            st.success("Saved!")
        if em_s2.button("🔌 Test Email", key="sys_em_test"):
            with st.spinner("Connecting…"):
                try:
                    import imaplib as _imap
                    _conn = (_imap.IMAP4_SSL if em_ssl else _imap.IMAP4)(em_host, int(em_port))
                    _conn.login(em_user, em_pass)
                    _conn.logout()
                    st.success(f"Connected to {em_host}")
                except Exception as e:
                    st.error(f"Connection failed: {e}")

    # ── Integrations ──────────────────────────────────────────────────────────
    with st.expander("🔗 Integrations"):
        from scripts.integrations import REGISTRY as _IREGISTRY
        from app.wizard.tiers import can_use as _ican_use, tier_label as _itier_label, TIERS as _ITIERS
        _INTEG_CONFIG_DIR = CONFIG_DIR
        _effective_tier = _profile.effective_tier if _profile else "free"
        st.caption("Connect external services for job tracking, document storage, notifications, and calendar sync.")
        for _iname, _icls in _IREGISTRY.items():
            _iaccess = (
                _ITIERS.index(_icls.tier) <= _ITIERS.index(_effective_tier)
                if _icls.tier in _ITIERS and _effective_tier in _ITIERS
                else _icls.tier == "free"
            )
            _iconfig_exists = _icls.is_configured(_INTEG_CONFIG_DIR)
            _ilabel = _itier_label(_iname + "_sync") or ""
            with st.container(border=True):
                _ih1, _ih2 = st.columns([8, 2])
                with _ih1:
                    st.markdown(f"**{_icls.label}** &nbsp; {'🟢 Connected' if _iconfig_exists else '⚪ Not connected'}")
                with _ih2:
                    if _ilabel:
                        st.caption(_ilabel)
                if not _iaccess:
                    st.caption(f"Upgrade to {_icls.tier} to enable {_icls.label}.")
                elif _iconfig_exists:
                    _ic1, _ic2 = st.columns(2)
                    if _ic1.button("🔌 Test", key=f"itest_{_iname}", use_container_width=True):
                        _iinst = _icls()
                        _iinst.connect(_iinst.load_config(_INTEG_CONFIG_DIR))
                        with st.spinner("Testing…"):
                            st.success("Connection verified.") if _iinst.test() else st.error("Test failed — check credentials.")
                    if _ic2.button("🗑 Disconnect", key=f"idisconnect_{_iname}", use_container_width=True):
                        _icls.config_path(_INTEG_CONFIG_DIR).unlink(missing_ok=True)
                        st.rerun()
                else:
                    _iinst = _icls()
                    _ifields = _iinst.fields()
                    _iform_vals: dict = {}
                    for _ifield in _ifields:
                        _iform_vals[_ifield["key"]] = st.text_input(
                            _ifield["label"],
                            placeholder=_ifield.get("placeholder", ""),
                            type="password" if _ifield["type"] == "password" else "default",
                            help=_ifield.get("help", ""),
                            key=f"ifield_{_iname}_{_ifield['key']}",
                        )
                    if st.button("🔗 Connect & Test", key=f"iconnect_{_iname}", type="primary"):
                        _imissing = [f["label"] for f in _ifields if f.get("required") and not _iform_vals.get(f["key"], "").strip()]
                        if _imissing:
                            st.warning(f"Required: {', '.join(_imissing)}")
                        else:
                            _iinst.connect(_iform_vals)
                            with st.spinner("Testing connection…"):
                                if _iinst.test():
                                    _iinst.save_config(_iform_vals, _INTEG_CONFIG_DIR)
                                    st.success(f"{_icls.label} connected!")
                                    st.rerun()
                                else:
                                    st.error("Connection test failed — check your credentials.")

# ── Fine-Tune Wizard tab ───────────────────────────────────────────────────────
with tab_finetune:
    if not _show_finetune:
        st.info(
            f"Fine-tuning requires a GPU profile. "
            f"Current profile: `{_profile.inference_profile if _profile else 'not configured'}`. "
            "Switch to the **👤 My Profile** tab above and change your inference profile to `single-gpu` or `dual-gpu`."
        )
    else:
        st.subheader("Fine-Tune Your Cover Letter Model")
        st.caption(
            "Upload your existing cover letters to train a personalised writing model. "
            "Requires a GPU. The base model is used until fine-tuning completes."
        )

        ft_step = st.session_state.get("ft_step", 1)

        if ft_step == 1:
            st.markdown("**Step 1: Upload Cover Letters**")
            st.caption("Accepted formats: `.md` or `.txt`. Convert PDFs to text before uploading.")
            uploaded = st.file_uploader(
                "Upload cover letters (.md or .txt)",
                type=["md", "txt"],
                accept_multiple_files=True,
            )
            if uploaded and st.button("Extract Training Pairs →", type="primary", key="ft_extract"):
                upload_dir = _profile.docs_dir / "training_data" / "uploads"
                upload_dir.mkdir(parents=True, exist_ok=True)
                for f in uploaded:
                    (upload_dir / f.name).write_bytes(f.read())
                st.session_state.ft_step = 2
                st.rerun()

        elif ft_step == 2:
            st.markdown("**Step 2: Extract Training Pairs**")
            import json as _json
            import sqlite3 as _sqlite3
            from scripts.db import DEFAULT_DB as _FT_DB

            jsonl_path = _profile.docs_dir / "training_data" / "cover_letters.jsonl"

            # Show task status
            _ft_conn = _sqlite3.connect(_FT_DB)
            _ft_conn.row_factory = _sqlite3.Row
            _ft_task = _ft_conn.execute(
                "SELECT * FROM background_tasks WHERE task_type='prepare_training' ORDER BY id DESC LIMIT 1"
            ).fetchone()
            _ft_conn.close()

            if _ft_task:
                _ft_status = _ft_task["status"]
                if _ft_status == "completed":
                    st.success(f"✅ {_ft_task['error'] or 'Extraction complete'}")
                elif _ft_status in ("running", "queued"):
                    st.info(f"⏳ {_ft_status.capitalize()}… refresh to check progress.")
                elif _ft_status == "failed":
                    st.error(f"Extraction failed: {_ft_task['error']}")

            if st.button("⚙️ Extract Training Pairs", type="primary", key="ft_extract2"):
                from scripts.task_runner import submit_task as _ft_submit
                _ft_submit(_FT_DB, "prepare_training", 0)
                st.info("Extracting in the background — refresh in a moment.")
                st.rerun()

            if jsonl_path.exists():
                pairs = [_json.loads(l) for l in jsonl_path.read_text().splitlines() if l.strip()]
                st.caption(f"{len(pairs)} training pairs ready.")
                for i, p in enumerate(pairs[:3]):
                    with st.expander(f"Pair {i+1}"):
                        st.text(p.get("output", p.get("input", ""))[:300])
            else:
                st.caption("No training pairs yet — click Extract above.")

            col_back, col_next = st.columns([1, 4])
            if col_back.button("← Back", key="ft_back2"):
                st.session_state.ft_step = 1
                st.rerun()
            if col_next.button("Start Training →", type="primary", key="ft_next2"):
                st.session_state.ft_step = 3
                st.rerun()

        elif ft_step == 3:
            st.markdown("**Step 3: Fine-Tune**")

            _ft_profile_name = ((_profile.name.split() or ["cover"])[0].lower()
                                if _profile else "cover")
            _ft_model_name = f"{_ft_profile_name}-cover-writer"

            st.info(
                "Run the command below from your terminal. Training takes 30–90 min on GPU "
                "and registers the model automatically when complete."
            )
            st.code("make finetune PROFILE=single-gpu", language="bash")
            st.caption(
                f"Your model will appear as **{_ft_model_name}:latest** in Ollama. "
                "Cover letter generation will use it automatically."
            )

            st.markdown("**Model status:**")
            try:
                import os as _os
                import requests as _ft_req
                _ollama_url = _os.environ.get("OLLAMA_URL", "http://localhost:11434")
                _tags = _ft_req.get(f"{_ollama_url}/api/tags", timeout=3)
                if _tags.status_code == 200:
                    _model_names = [m["name"] for m in _tags.json().get("models", [])]
                    if any(_ft_model_name in m for m in _model_names):
                        st.success(f"✅ `{_ft_model_name}:latest` is ready in Ollama!")
                    else:
                        st.warning(f"⏳ `{_ft_model_name}:latest` not registered yet.")
                else:
                    st.caption("Ollama returned an unexpected response.")
            except Exception:
                st.caption("Could not reach Ollama — ensure services are running with `make start`.")

            col_back, col_refresh = st.columns([1, 3])
            if col_back.button("← Back", key="ft_back3"):
                st.session_state.ft_step = 2
                st.rerun()
            if col_refresh.button("🔄 Check model status", key="ft_refresh3"):
                st.rerun()

# ── License tab ───────────────────────────────────────────────────────────────
with tab_license:
    st.subheader("🔑 License")

    from scripts.license import (
        verify_local as _verify_local,
        activate as _activate,
        deactivate as _deactivate,
        _DEFAULT_LICENSE_PATH,
        _DEFAULT_PUBLIC_KEY_PATH,
    )

    _lic = _verify_local()

    if _lic:
        _grace_note = " _(grace period active)_" if _lic.get("in_grace") else ""
        st.success(f"**{_lic['tier'].title()} tier** active{_grace_note}")
        try:
            import json as _json
            _key_display = _json.loads(_DEFAULT_LICENSE_PATH.read_text()).get("key_display", "—")
        except Exception:
            _key_display = "—"
        st.caption(f"Key: `{_key_display}`")
        if _lic.get("notice"):
            st.info(_lic["notice"])
        if st.button("Deactivate this machine", type="secondary", key="lic_deactivate"):
            _deactivate()
            st.success("Deactivated. Restart the app to apply.")
            st.rerun()
    else:
        st.info("No active license — running on **free tier**.")
        st.caption("Enter a license key to unlock paid features.")
        _key_input = st.text_input(
            "License key",
            placeholder="CFG-PRNG-XXXX-XXXX-XXXX",
            label_visibility="collapsed",
            key="lic_key_input",
        )
        if st.button("Activate", disabled=not (_key_input or "").strip(), key="lic_activate"):
            with st.spinner("Activating…"):
                try:
                    result = _activate(_key_input.strip())
                    st.success(f"Activated! Tier: **{result['tier']}**")
                    st.rerun()
                except Exception as _e:
                    st.error(f"Activation failed: {_e}")

# ── Data tab — Backup / Restore / Teleport ────────────────────────────────────
with tab_data:
    st.subheader("💾 Backup / Restore / Teleport")
    st.caption(
        "Export all your personal configs and job data as a portable zip. "
        "Use to migrate between machines, back up before testing, or transfer to a new Docker volume."
    )

    from scripts.backup import create_backup, list_backup_contents, restore_backup as _do_restore

    _base_dir = Path(__file__).parent.parent.parent

    # ── Backup ────────────────────────────────────────────────────────────────
    st.markdown("### 📦 Create Backup")
    _incl_db = st.checkbox("Include staging.db (job data)", value=True, key="backup_incl_db")
    if st.button("Create Backup", key="backup_create"):
        with st.spinner("Creating backup…"):
            try:
                _zip_bytes = create_backup(_base_dir, include_db=_incl_db)
                _info = list_backup_contents(_zip_bytes)
                from datetime import datetime as _dt
                _ts = _dt.now().strftime("%Y%m%d-%H%M%S")
                _fname = f"peregrine-backup-{_ts}.zip"
                st.success(
                    f"Backup ready — {len(_info['files'])} files, "
                    f"{_info['total_bytes'] / 1024:.0f} KB uncompressed"
                )
                st.download_button(
                    label="⬇️ Download backup zip",
                    data=_zip_bytes,
                    file_name=_fname,
                    mime="application/zip",
                    key="backup_download",
                )
                with st.expander("Files included"):
                    for _fn in _info["files"]:
                        _sz = _info["sizes"].get(_fn, 0)
                        st.caption(f"`{_fn}` — {_sz:,} bytes")
            except Exception as _e:
                st.error(f"Backup failed: {_e}")

    st.divider()

    # ── Restore ───────────────────────────────────────────────────────────────
    st.markdown("### 📂 Restore from Backup")
    st.warning(
        "Restoring overwrites existing config files and (optionally) staging.db. "
        "Create a fresh backup first if you want to preserve current settings.",
        icon="⚠️",
    )
    _restore_file = st.file_uploader(
        "Upload backup zip", type=["zip"], key="restore_upload",
        help="Select a peregrine-backup-*.zip created by this tool."
    )
    _restore_db = st.checkbox("Restore staging.db (job data)", value=True, key="restore_incl_db")
    _restore_overwrite = st.checkbox("Overwrite existing files", value=True, key="restore_overwrite")

    if _restore_file and st.button("Restore", type="primary", key="restore_go"):
        with st.spinner("Restoring…"):
            try:
                _zip_bytes = _restore_file.read()
                _result = _do_restore(
                    _zip_bytes, _base_dir,
                    include_db=_restore_db,
                    overwrite=_restore_overwrite,
                )
                st.success(f"Restored {len(_result['restored'])} files.")
                with st.expander("Details"):
                    for _fn in _result["restored"]:
                        st.caption(f"✓ `{_fn}`")
                    for _fn in _result["skipped"]:
                        st.caption(f"— `{_fn}` (skipped)")
                st.info("Restart the app for changes to take effect.", icon="ℹ️")
            except Exception as _e:
                st.error(f"Restore failed: {_e}")

    st.divider()

    # ── Teleport ──────────────────────────────────────────────────────────────
    st.markdown("### 🚀 Teleport to Another Machine")
    st.markdown("""
**How to move Peregrine to a new machine or Docker volume:**

1. **Here (source):** click **Create Backup** above and download the zip.
2. **On the target machine:** clone the repo and run `./manage.sh start`.
3. **In the target Peregrine UI:** go to Settings → 💾 Data → Restore from Backup and upload the zip.
4. Restart the target app: `./manage.sh restart`.

The zip contains all gitignored configs (email credentials, Notion token, LLM settings, resume YAML)
and optionally your staging database (all discovered/applied jobs, contacts, cover letters).
""")


# ── Developer tab ─────────────────────────────────────────────────────────────
if _show_dev_tab:
    with _all_tabs[-1]:
        st.subheader("Developer Settings")
        st.caption("These settings are for local testing only and are never used in production.")

        st.markdown("**Tier Override**")
        st.caption("Instantly switches effective tier without changing your billing tier.")
        from app.wizard.tiers import TIERS as _TIERS
        _current_override = _u_for_dev.get("dev_tier_override") or ""
        _override_opts = ["(none — use real tier)"] + _TIERS
        _override_idx = (_TIERS.index(_current_override) + 1) if _current_override in _TIERS else 0
        _new_override = st.selectbox("dev_tier_override", _override_opts, index=_override_idx)
        _new_override_val = None if _new_override.startswith("(none") else _new_override

        if st.button("Apply tier override", key="apply_tier_override"):
            _u_for_dev["dev_tier_override"] = _new_override_val
            save_yaml(USER_CFG, _u_for_dev)
            st.success(f"Tier override set to: {_new_override_val or 'none'}. Page will reload.")
            st.rerun()

        st.divider()
        st.markdown("**Wizard Reset**")
        st.caption("Sets `wizard_complete: false` to re-enter the wizard without deleting your config.")

        if st.button("↩ Reset wizard", key="reset_wizard"):
            _u_for_dev["wizard_complete"] = False
            _u_for_dev["wizard_step"] = 0
            save_yaml(USER_CFG, _u_for_dev)
            st.success("Wizard reset. Reload the app to re-run setup.")

        st.divider()
        st.markdown("**🤗 Hugging Face Token**")
        st.caption(
            "Used for uploading training data and running fine-tune jobs on HF infrastructure. "
            "Stored in `config/tokens.yaml` (git-ignored). "
            "Create a **write-permission** token at huggingface.co/settings/tokens."
        )
        _tok_cfg = load_yaml(TOKENS_CFG) if TOKENS_CFG.exists() else {}
        _hf_token = st.text_input(
            "HF Token",
            value=_tok_cfg.get("hf_token", ""),
            type="password",
            placeholder="hf_…",
            key="dev_hf_token",
        )
        _col_save_hf, _col_test_hf = st.columns(2)
        if _col_save_hf.button("💾 Save HF token", type="primary", key="dev_save_hf"):
            save_yaml(TOKENS_CFG, {**_tok_cfg, "hf_token": _hf_token})
            TOKENS_CFG.chmod(0o600)
            st.success("Saved!")
        if _col_test_hf.button("🔌 Test HF token", key="dev_test_hf"):
            with st.spinner("Checking…"):
                try:
                    import requests as _r
                    resp = _r.get(
                        "https://huggingface.co/api/whoami",
                        headers={"Authorization": f"Bearer {_hf_token}"},
                        timeout=5,
                    )
                    if resp.ok:
                        info = resp.json()
                        name = info.get("name") or info.get("fullname") or "unknown"
                        perm = info.get("auth", {}).get("accessToken", {}).get("role", "read")
                        st.success(f"Logged in as **{name}** · permission: `{perm}`")
                        if perm == "read":
                            st.warning("Token is read-only — create a **write** token to upload datasets and run Jobs.")
                    else:
                        st.error(f"Invalid token ({resp.status_code})")
                except Exception as e:
                    st.error(f"Error: {e}")

        st.divider()
        st.markdown("**📊 Export Classifier Training Data**")
        st.caption(
            "Exports inbound emails from `job_contacts` (labeled by the IMAP sync classifier) "
            "to `data/email_score.jsonl` for use with `scripts/benchmark_classifier.py --score`. "
            "⚠️ Labels are generated by llama3.1:8b — review before using as ground truth."
        )
        _db_candidates = [
            Path(__file__).parent.parent.parent / "data" / "staging.db",
            Path(__file__).parent.parent.parent / "staging.db",
        ]
        _db_path = next((p for p in _db_candidates if p.exists()), None)
        _score_out = Path(__file__).parent.parent.parent / "data" / "email_score.jsonl"

        if _db_path is None:
            st.warning("No `staging.db` found — run discovery first to create the database.")
        else:
            st.caption(f"Database: `{_db_path.name}` · Output: `data/email_score.jsonl`")
            if st.button("📤 Export DB labels → email_score.jsonl", key="dev_export_db"):
                import sqlite3 as _sqlite3
                from scripts.benchmark_classifier import LABELS as _BC_LABELS
                _conn = _sqlite3.connect(_db_path)
                _cur = _conn.cursor()
                _cur.execute("""
                    SELECT subject, body, stage_signal
                    FROM job_contacts
                    WHERE stage_signal IS NOT NULL
                      AND stage_signal != ''
                      AND direction = 'inbound'
                    ORDER BY received_at
                """)
                _rows = _cur.fetchall()
                _conn.close()

                if not _rows:
                    st.warning("No labeled emails in `job_contacts`. Run IMAP sync first.")
                else:
                    _score_out.parent.mkdir(parents=True, exist_ok=True)
                    _written, _skipped = 0, 0
                    _label_counts: dict = {}
                    with _score_out.open("w") as _f:
                        for _subj, _body, _label in _rows:
                            if _label not in _BC_LABELS:
                                _skipped += 1
                                continue
                            import json as _json_dev
                            _f.write(_json_dev.dumps({
                                "subject": _subj or "",
                                "body": (_body or "")[:800],
                                "label": _label,
                            }) + "\n")
                            _written += 1
                            _label_counts[_label] = _label_counts.get(_label, 0) + 1
                    st.success(f"Exported **{_written}** emails → `data/email_score.jsonl` ({_skipped} skipped — unknown labels)")
                    st.caption("Label distribution:")
                    for _lbl, _cnt in sorted(_label_counts.items(), key=lambda x: -x[1]):
                        st.caption(f"  `{_lbl}`: {_cnt}")
