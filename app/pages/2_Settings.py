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
RESUME_PATH = Path(__file__).parent.parent.parent / "aihawk" / "data_folder" / "plain_text_resume.yaml"
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

_dev_mode = _os.getenv("DEV_MODE", "").lower() in ("true", "1", "yes")
_u_for_dev = yaml.safe_load(USER_CFG.read_text()) or {} if USER_CFG.exists() else {}
_show_dev_tab = _dev_mode or bool(_u_for_dev.get("dev_tier_override"))

_tab_names = [
    "👤 My Profile", "🔎 Search", "🤖 LLM Backends", "📚 Notion",
    "🔌 Services", "📝 Resume Profile", "📧 Email", "🏷️ Skills", "🎯 Fine-Tune"
]
if _show_dev_tab:
    _tab_names.append("🛠️ Developer")
_all_tabs = st.tabs(_tab_names)
tab_profile, tab_search, tab_llm, tab_notion, tab_services, tab_resume, tab_email, tab_skills, tab_finetune = _all_tabs[:9]

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
        u_summary  = st.text_area("Career Summary (used in LLM prompts)",
                                   _u.get("career_summary", ""), height=100)

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

    with st.expander("📁 File Paths"):
        u_docs   = st.text_input("Documents directory",     _u.get("docs_dir", "~/Documents/JobSearch"))
        u_ollama = st.text_input("Ollama models directory", _u.get("ollama_models_dir", "~/models/ollama"))
        u_vllm   = st.text_input("vLLM models directory",   _u.get("vllm_models_dir", "~/models/vllm"))

    with st.expander("⚙️ Inference Profile"):
        _profiles = ["remote", "cpu", "single-gpu", "dual-gpu"]
        u_inf_profile = st.selectbox("Active profile", _profiles,
                                      index=_profiles.index(_u.get("inference_profile", "remote")))

    with st.expander("🔌 Service Ports & Hosts"):
        st.caption("Advanced — change only if services run on non-default ports or remote hosts.")
        sc1, sc2, sc3 = st.columns(3)
        with sc1:
            st.markdown("**Ollama**")
            svc_ollama_host   = st.text_input("Host",        _svc["ollama_host"],   key="svc_ollama_host")
            svc_ollama_port   = st.number_input("Port",      value=_svc["ollama_port"], step=1, key="svc_ollama_port")
            svc_ollama_ssl    = st.checkbox("SSL",           _svc["ollama_ssl"],    key="svc_ollama_ssl")
            svc_ollama_verify = st.checkbox("Verify cert",   _svc["ollama_ssl_verify"], key="svc_ollama_verify")
        with sc2:
            st.markdown("**vLLM**")
            svc_vllm_host   = st.text_input("Host",          _svc["vllm_host"],   key="svc_vllm_host")
            svc_vllm_port   = st.number_input("Port",        value=_svc["vllm_port"], step=1, key="svc_vllm_port")
            svc_vllm_ssl    = st.checkbox("SSL",             _svc["vllm_ssl"],    key="svc_vllm_ssl")
            svc_vllm_verify = st.checkbox("Verify cert",     _svc["vllm_ssl_verify"], key="svc_vllm_verify")
        with sc3:
            st.markdown("**SearXNG**")
            svc_sxng_host   = st.text_input("Host",          _svc["searxng_host"],   key="svc_sxng_host")
            svc_sxng_port   = st.number_input("Port",        value=_svc["searxng_port"], step=1, key="svc_sxng_port")
            svc_sxng_ssl    = st.checkbox("SSL",             _svc["searxng_ssl"],    key="svc_sxng_ssl")
            svc_sxng_verify = st.checkbox("Verify cert",     _svc["searxng_ssl_verify"], key="svc_sxng_verify")

    if st.button("💾 Save Profile", type="primary", key="save_user_profile"):
        new_data = {
            "name": u_name, "email": u_email, "phone": u_phone,
            "linkedin": u_linkedin, "career_summary": u_summary,
            "nda_companies": nda_list,
            "docs_dir": u_docs, "ollama_models_dir": u_ollama, "vllm_models_dir": u_vllm,
            "inference_profile": u_inf_profile,
            "mission_preferences": _u.get("mission_preferences", {}),
            "candidate_accessibility_focus": u_access_focus,
            "candidate_lgbtq_focus": u_lgbtq_focus,
            "services": {
                "streamlit_port": _svc["streamlit_port"],
                "ollama_host": svc_ollama_host, "ollama_port": int(svc_ollama_port),
                "ollama_ssl": svc_ollama_ssl, "ollama_ssl_verify": svc_ollama_verify,
                "vllm_host": svc_vllm_host, "vllm_port": int(svc_vllm_port),
                "vllm_ssl": svc_vllm_ssl, "vllm_ssl_verify": svc_vllm_verify,
                "searxng_host": svc_sxng_host, "searxng_port": int(svc_sxng_port),
                "searxng_ssl": svc_sxng_ssl, "searxng_ssl_verify": svc_sxng_verify,
            }
        }
        save_yaml(USER_CFG, new_data)
        # Reload from disk so URL generation uses saved values
        from scripts.generate_llm_config import apply_service_urls as _apply_urls
        _apply_urls(_UP(USER_CFG), LLM_CFG)
        st.success("Profile saved and service URLs updated.")
        st.rerun()

# ── Search tab ───────────────────────────────────────────────────────────────
with tab_search:
    cfg = load_yaml(SEARCH_CFG)
    profiles = cfg.get("profiles", [{}])
    p = profiles[0] if profiles else {}

    # Seed session state from config on first load (or when config changes after save)
    _sp_hash = str(p.get("titles", [])) + str(p.get("exclude_keywords", []))
    if st.session_state.get("_sp_hash") != _sp_hash:
        st.session_state["_sp_titles"] = "\n".join(p.get("titles", []))
        st.session_state["_sp_excludes"] = "\n".join(p.get("exclude_keywords", []))
        st.session_state["_sp_hash"] = _sp_hash

    # ── Titles ────────────────────────────────────────────────────────────────
    title_row, suggest_btn_col = st.columns([4, 1])
    with title_row:
        st.subheader("Job Titles to Search")
    with suggest_btn_col:
        st.write("")  # vertical align
        _run_suggest = st.button("✨ Suggest", key="sp_suggest_btn",
                                  help="Ask the LLM to suggest additional titles and exclude keywords based on your resume")

    titles_text = st.text_area(
        "One title per line",
        key="_sp_titles",
        height=150,
        help="JobSpy will search for any of these titles across all configured boards.",
        label_visibility="visible",
    )

    # ── LLM suggestions panel ────────────────────────────────────────────────
    if _run_suggest:
        current = [t.strip() for t in titles_text.splitlines() if t.strip()]
        with st.spinner("Asking LLM for suggestions…"):
            suggestions = _suggest_search_terms(current, RESUME_PATH)
        st.session_state["_sp_suggestions"] = suggestions

    if st.session_state.get("_sp_suggestions"):
        sugg = st.session_state["_sp_suggestions"]
        s_titles = sugg.get("suggested_titles", [])
        s_excl = sugg.get("suggested_excludes", [])

        existing_titles = {t.lower() for t in titles_text.splitlines() if t.strip()}
        existing_excl = {e.lower() for e in st.session_state.get("_sp_excludes", "").splitlines() if e.strip()}

        if s_titles:
            st.caption("**Suggested titles** — click to add:")
            cols = st.columns(min(len(s_titles), 4))
            for i, title in enumerate(s_titles):
                with cols[i % 4]:
                    if title.lower() not in existing_titles:
                        if st.button(f"+ {title}", key=f"sp_add_title_{i}"):
                            st.session_state["_sp_titles"] = (
                                st.session_state.get("_sp_titles", "").rstrip("\n") + f"\n{title}"
                            )
                            st.rerun()
                    else:
                        st.caption(f"✓ {title}")

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

    st.subheader("Locations")
    locations_text = st.text_area(
        "One location per line",
        value="\n".join(p.get("locations", [])),
        height=100,
    )

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
            "titles": [t.strip() for t in titles_text.splitlines() if t.strip()],
            "locations": [loc.strip() for loc in locations_text.splitlines() if loc.strip()],
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

# ── LLM Backends tab ─────────────────────────────────────────────────────────
with tab_llm:
    import requests as _req

    def _ollama_models(base_url: str) -> list[str]:
        """Fetch installed model names from the Ollama /api/tags endpoint."""
        try:
            r = _req.get(base_url.rstrip("/v1").rstrip("/") + "/api/tags", timeout=2)
            if r.ok:
                return [m["name"] for m in r.json().get("models", [])]
        except Exception:
            pass
        return []

    cfg = load_yaml(LLM_CFG)
    backends = cfg.get("backends", {})
    fallback_order = cfg.get("fallback_order", list(backends.keys()))

    # Persist reordering across reruns triggered by ↑↓ buttons.
    # Reset to config order whenever the config file is fresher than the session key.
    _cfg_key = str(fallback_order)
    if st.session_state.get("_llm_order_cfg_key") != _cfg_key:
        st.session_state["_llm_order"] = list(fallback_order)
        st.session_state["_llm_order_cfg_key"] = _cfg_key
    new_order: list[str] = st.session_state["_llm_order"]

    # All known backends (in current order first, then any extras)
    all_names = list(new_order) + [n for n in backends if n not in new_order]

    st.caption("Enable/disable backends and drag their priority with the ↑ ↓ buttons. "
               "First enabled + reachable backend wins on each call.")

    updated_backends = {}

    for name in all_names:
        b = backends.get(name, {})
        enabled = b.get("enabled", True)
        label = name.replace("_", " ").title()
        pos = new_order.index(name) + 1 if name in new_order else "—"
        header = f"{'🟢' if enabled else '⚫'} **{pos}. {label}**"

        with st.expander(header, expanded=False):
            col_tog, col_up, col_dn, col_spacer = st.columns([2, 1, 1, 4])

            new_enabled = col_tog.checkbox("Enabled", value=enabled, key=f"{name}_enabled")

            # Up / Down only apply to backends currently in the order
            if name in new_order:
                idx = new_order.index(name)
                if col_up.button("↑", key=f"{name}_up", disabled=idx == 0):
                    new_order[idx], new_order[idx - 1] = new_order[idx - 1], new_order[idx]
                    st.session_state["_llm_order"] = new_order
                    st.rerun()
                if col_dn.button("↓", key=f"{name}_dn", disabled=idx == len(new_order) - 1):
                    new_order[idx], new_order[idx + 1] = new_order[idx + 1], new_order[idx]
                    st.session_state["_llm_order"] = new_order
                    st.rerun()

            if b.get("type") == "openai_compat":
                url = st.text_input("URL", value=b.get("base_url", ""), key=f"{name}_url")

                # Ollama gets a live model picker; other backends get a text input
                if name == "ollama":
                    ollama_models = _ollama_models(b.get("base_url", "http://localhost:11434"))
                    current_model = b.get("model", "")
                    if ollama_models:
                        options = ollama_models
                        idx_default = options.index(current_model) if current_model in options else 0
                        model = st.selectbox(
                            "Model",
                            options,
                            index=idx_default,
                            key=f"{name}_model",
                            help="Lists models currently installed in Ollama. Pull new ones with `ollama pull <name>`.",
                        )
                    else:
                        st.caption("_Ollama not reachable — enter model name manually_")
                        model = st.text_input("Model", value=current_model, key=f"{name}_model")
                else:
                    model = st.text_input("Model", value=b.get("model", ""), key=f"{name}_model")

                updated_backends[name] = {**b, "base_url": url, "model": model, "enabled": new_enabled}
            elif b.get("type") == "anthropic":
                model = st.text_input("Model", value=b.get("model", ""), key=f"{name}_model")
                updated_backends[name] = {**b, "model": model, "enabled": new_enabled}
            else:
                updated_backends[name] = {**b, "enabled": new_enabled}

            if b.get("type") == "openai_compat":
                if st.button(f"Test connection", key=f"test_{name}"):
                    with st.spinner("Testing…"):
                        try:
                            from scripts.llm_router import LLMRouter
                            r = LLMRouter()
                            reachable = r._is_reachable(b.get("base_url", ""))
                            if reachable:
                                st.success("Reachable ✓")
                            else:
                                st.warning("Not reachable ✗")
                        except Exception as e:
                            st.error(f"Error: {e}")

    st.divider()
    st.caption("Current priority: " + " → ".join(
        f"{'✓' if backends.get(n, {}).get('enabled', True) else '✗'} {n}"
        for n in new_order
    ))

    if st.button("💾 Save LLM settings", type="primary"):
        save_yaml(LLM_CFG, {**cfg, "backends": updated_backends, "fallback_order": new_order})
        st.session_state.pop("_llm_order", None)
        st.session_state.pop("_llm_order_cfg_key", None)
        st.success("LLM settings saved!")

# ── Notion tab ────────────────────────────────────────────────────────────────
with tab_notion:
    cfg = load_yaml(NOTION_CFG) if NOTION_CFG.exists() else {}

    st.subheader("Notion Connection")
    token = st.text_input(
        "Integration Token",
        value=cfg.get("token", ""),
        type="password",
        help="Find this at notion.so/my-integrations → your integration → Internal Integration Token",
    )
    db_id = st.text_input(
        "Database ID",
        value=cfg.get("database_id", ""),
        help="The 32-character ID from your Notion database URL",
    )

    col_save, col_test = st.columns(2)
    if col_save.button("💾 Save Notion settings", type="primary"):
        save_yaml(NOTION_CFG, {**cfg, "token": token, "database_id": db_id})
        st.success("Notion settings saved!")

    if col_test.button("🔌 Test connection"):
        with st.spinner("Connecting…"):
            try:
                from notion_client import Client
                n = Client(auth=token)
                db = n.databases.retrieve(db_id)
                st.success(f"Connected to: **{db['title'][0]['plain_text']}**")
            except Exception as e:
                st.error(f"Connection failed: {e}")

# ── Services tab ───────────────────────────────────────────────────────────────
with tab_services:
    import subprocess as _sp

    TOKENS_CFG = CONFIG_DIR / "tokens.yaml"

    # Service definitions: (display_name, port, start_cmd, stop_cmd, notes)
    COMPOSE_DIR = str(Path(__file__).parent.parent.parent)
    _profile_name = _profile.inference_profile if _profile else "remote"

    SERVICES = [
        {
            "name": "Streamlit UI",
            "port": _profile._svc["streamlit_port"] if _profile else 8501,
            "start": ["docker", "compose", "--profile", _profile_name, "up", "-d", "app"],
            "stop":  ["docker", "compose", "stop", "app"],
            "cwd":   COMPOSE_DIR,
            "note":  "Peregrine web interface",
        },
        {
            "name": "Ollama (local LLM)",
            "port": _profile._svc["ollama_port"] if _profile else 11434,
            "start": ["docker", "compose", "--profile", _profile_name, "up", "-d", "ollama"],
            "stop":  ["docker", "compose", "stop", "ollama"],
            "cwd":   COMPOSE_DIR,
            "note":  f"Local inference engine — profile: {_profile_name}",
            "hidden": _profile_name == "remote",
        },
        {
            "name": "vLLM Server",
            "port": _profile._svc["vllm_port"] if _profile else 8000,
            "start": ["docker", "compose", "--profile", _profile_name, "up", "-d", "vllm"],
            "stop":  ["docker", "compose", "stop", "vllm"],
            "cwd":   COMPOSE_DIR,
            "model_dir": str(_profile.vllm_models_dir) if _profile else str(Path.home() / "models" / "vllm"),
            "note":  "vLLM inference — dual-gpu profile only",
            "hidden": _profile_name != "dual-gpu",
        },
        {
            "name": "Vision Service (moondream2)",
            "port": 8002,
            "start": ["docker", "compose", "--profile", _profile_name, "up", "-d", "vision"],
            "stop":  ["docker", "compose", "stop", "vision"],
            "cwd":   COMPOSE_DIR,
            "note":  "Screenshot/image understanding for survey assistant",
            "hidden": _profile_name not in ("single-gpu", "dual-gpu"),
        },
        {
            "name": "SearXNG (company scraper)",
            "port": _profile._svc["searxng_port"] if _profile else 8888,
            "start": ["docker", "compose", "up", "-d", "searxng"],
            "stop":  ["docker", "compose", "stop", "searxng"],
            "cwd":   COMPOSE_DIR,
            "note":  "Privacy-respecting meta-search for company research",
        },
    ]
    # Filter hidden services based on active profile
    SERVICES = [s for s in SERVICES if not s.get("hidden")]

    def _port_open(port: int, host: str = "127.0.0.1",
                   ssl: bool = False, verify: bool = True) -> bool:
        try:
            import requests as _r
            scheme = "https" if ssl else "http"
            _r.get(f"{scheme}://{host}:{port}/", timeout=1, verify=verify)
            return True
        except Exception:
            return False

    st.caption("Monitor and control the LLM backend services. Status is checked live on each page load.")

    for svc in SERVICES:
        _svc_host = "127.0.0.1"
        _svc_ssl = False
        _svc_verify = True
        if _profile:
            _svc_host = _profile._svc.get(f"{svc['name'].split()[0].lower()}_host", "127.0.0.1")
            _svc_ssl = _profile._svc.get(f"{svc['name'].split()[0].lower()}_ssl", False)
            _svc_verify = _profile._svc.get(f"{svc['name'].split()[0].lower()}_ssl_verify", True)
        up = _port_open(svc["port"], host=_svc_host, ssl=_svc_ssl, verify=_svc_verify)
        badge = "🟢 Running" if up else "🔴 Stopped"
        header = f"**{svc['name']}** — {badge}"

        with st.container(border=True):
            left_col, right_col = st.columns([3, 1])
            with left_col:
                st.markdown(header)
                st.caption(f"Port {svc['port']} · {svc['note']}")

                # Model selector for services backed by a local model directory (e.g. vLLM)
                if "model_dir" in svc:
                    _mdir = Path(svc["model_dir"])
                    _models = (
                        sorted(d.name for d in _mdir.iterdir() if d.is_dir())
                        if _mdir.exists() else []
                    )
                    _mk = f"svc_model_{svc['port']}"
                    _loaded_file = Path("/tmp/vllm-server.model")
                    _loaded = _loaded_file.read_text().strip() if (_loaded_file.exists()) else ""
                    if _models:
                        _default = _models.index(_loaded) if _loaded in _models else 0
                        st.selectbox(
                            "Model",
                            _models,
                            index=_default,
                            key=_mk,
                            disabled=up,
                            help="Model to load on start. Stop then Start to swap models.",
                        )
                    else:
                        st.caption(f"_No models found in {svc['model_dir']}_")

            with right_col:
                if svc["start"] is None:
                    st.caption("_Manual start only_")
                elif up:
                    if st.button("⏹ Stop", key=f"svc_stop_{svc['port']}", use_container_width=True):
                        with st.spinner(f"Stopping {svc['name']}…"):
                            r = _sp.run(svc["stop"], capture_output=True, text=True, cwd=svc["cwd"])
                        if r.returncode == 0:
                            st.success("Stopped.")
                        else:
                            st.error(f"Error: {r.stderr or r.stdout}")
                        st.rerun()
                else:
                    # Build start command, appending selected model for services with model_dir
                    _start_cmd = list(svc["start"])
                    if "model_dir" in svc:
                        _sel = st.session_state.get(f"svc_model_{svc['port']}")
                        if _sel:
                            _start_cmd.append(_sel)
                    if st.button("▶ Start", key=f"svc_start_{svc['port']}", use_container_width=True, type="primary"):
                        with st.spinner(f"Starting {svc['name']}…"):
                            r = _sp.run(_start_cmd, capture_output=True, text=True, cwd=svc["cwd"])
                        if r.returncode == 0:
                            st.success("Started!")
                        else:
                            st.error(f"Error: {r.stderr or r.stdout}")
                        st.rerun()

    st.divider()
    st.subheader("🤗 Hugging Face")
    st.caption(
        "Used for uploading training data and running fine-tune jobs on HF infrastructure. "
        "Token is stored in `config/tokens.yaml` (git-ignored). "
        "Create a **write-permission** token at huggingface.co/settings/tokens."
    )

    tok_cfg = load_yaml(TOKENS_CFG) if TOKENS_CFG.exists() else {}
    hf_token = st.text_input(
        "HF Token",
        value=tok_cfg.get("hf_token", ""),
        type="password",
        placeholder="hf_…",
    )

    col_save_hf, col_test_hf = st.columns(2)
    if col_save_hf.button("💾 Save HF token", type="primary"):
        save_yaml(TOKENS_CFG, {**tok_cfg, "hf_token": hf_token})
        TOKENS_CFG.chmod(0o600)
        st.success("Saved!")

    if col_test_hf.button("🔌 Test HF token"):
        with st.spinner("Checking…"):
            try:
                import requests as _r
                resp = _r.get(
                    "https://huggingface.co/api/whoami",
                    headers={"Authorization": f"Bearer {hf_token}"},
                    timeout=5,
                )
                if resp.ok:
                    info = resp.json()
                    name = info.get("name") or info.get("fullname") or "unknown"
                    auth = info.get("auth", {})
                    perm = auth.get("accessToken", {}).get("role", "read")
                    st.success(f"Logged in as **{name}** · permission: `{perm}`")
                    if perm == "read":
                        st.warning("Token is read-only — create a **write** token to upload datasets and run Jobs.")
                else:
                    st.error(f"Invalid token ({resp.status_code})")
            except Exception as e:
                st.error(f"Error: {e}")

# ── Resume Profile tab ────────────────────────────────────────────────────────
with tab_resume:
    st.caption(
        f"Edit {_name}'s application profile. "
        "Bullets are used as paste-able shortcuts in the Apply Workspace."
    )

    if not RESUME_PATH.exists():
        st.error(f"Resume YAML not found at `{RESUME_PATH}`. Is AIHawk cloned?")
        st.stop()

    _data = yaml.safe_load(RESUME_PATH.read_text()) or {}

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
            "city": _city, "zip_code": _zip_code, "linkedin": _linkedin, "date_of_birth": _dob,
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

# ── Email tab ─────────────────────────────────────────────────────────────────
with tab_email:
    EMAIL_CFG = CONFIG_DIR / "email.yaml"
    EMAIL_EXAMPLE = CONFIG_DIR / "email.yaml.example"

    st.caption(
        f"Connect {_name}'s email via IMAP to automatically associate recruitment "
        "emails with job applications. Only emails that mention the company name "
        "AND contain a recruitment keyword are ever imported — no personal emails "
        "are touched."
    )

    if not EMAIL_CFG.exists():
        st.info("No email config found — fill in your credentials below and click **Save** to create it.")

    em_cfg = load_yaml(EMAIL_CFG) if EMAIL_CFG.exists() else {}

    col_a, col_b = st.columns(2)
    with col_a:
        em_host = st.text_input("IMAP Host", em_cfg.get("host", "imap.gmail.com"), key="em_host")
        em_port = st.number_input("Port", value=int(em_cfg.get("port", 993)),
                                  min_value=1, max_value=65535, key="em_port")
        em_ssl  = st.checkbox("Use SSL", value=em_cfg.get("use_ssl", True), key="em_ssl")
    with col_b:
        em_user = st.text_input("Username (email address)", em_cfg.get("username", ""), key="em_user")
        em_pass = st.text_input("Password / App Password", em_cfg.get("password", ""),
                                type="password", key="em_pass")
        em_sent = st.text_input("Sent folder (blank = auto-detect)",
                                em_cfg.get("sent_folder", ""), key="em_sent",
                                placeholder='e.g. "[Gmail]/Sent Mail"')

    em_days = st.slider("Look-back window (days)", 14, 365,
                        int(em_cfg.get("lookback_days", 90)), key="em_days")

    st.caption(
        "**Gmail users:** create an App Password at "
        "myaccount.google.com/apppasswords (requires 2-Step Verification). "
        "Enable IMAP at Gmail Settings → Forwarding and POP/IMAP."
    )

    col_save, col_test = st.columns(2)

    if col_save.button("💾 Save email settings", type="primary", key="em_save"):
        save_yaml(EMAIL_CFG, {
            "host": em_host, "port": int(em_port), "use_ssl": em_ssl,
            "username": em_user, "password": em_pass,
            "sent_folder": em_sent, "lookback_days": int(em_days),
        })
        EMAIL_CFG.chmod(0o600)
        st.success("Saved!")

    if col_test.button("🔌 Test connection", key="em_test"):
        with st.spinner("Connecting…"):
            try:
                import imaplib as _imap
                _conn = (_imap.IMAP4_SSL if em_ssl else _imap.IMAP4)(em_host, int(em_port))
                _conn.login(em_user, em_pass)
                _, _caps = _conn.capability()
                _conn.logout()
                st.success(f"Connected successfully to {em_host}")
            except Exception as e:
                st.error(f"Connection failed: {e}")

# ── Skills & Keywords tab ─────────────────────────────────────────────────────
with tab_skills:
    st.subheader("🏷️ Skills & Keywords")
    st.caption(
        f"These are matched against job descriptions to select {_name}'s most relevant "
        "experience and highlight keyword overlap in the research brief."
    )

    if not KEYWORDS_CFG.exists():
        st.warning("resume_keywords.yaml not found — create it at config/resume_keywords.yaml")
    else:
        kw_data = load_yaml(KEYWORDS_CFG)

        changed = False
        for category in ["skills", "domains", "keywords"]:
            st.markdown(f"**{category.title()}**")
            tags: list[str] = kw_data.get(category, [])

            if not tags:
                st.caption("No tags yet — add one below.")

            # Render existing tags as removable chips (value-based keys for stability)
            n_cols = min(max(len(tags), 1), 6)
            cols = st.columns(n_cols)
            to_remove = None
            for i, tag in enumerate(tags):
                with cols[i % n_cols]:
                    if st.button(f"× {tag}", key=f"rm_{category}_{tag}", use_container_width=True):
                        to_remove = tag
            if to_remove:
                tags.remove(to_remove)
                kw_data[category] = tags
                changed = True

            # Add new tag
            new_col, btn_col = st.columns([4, 1])
            new_tag = new_col.text_input(
                "Add",
                key=f"new_{category}",
                label_visibility="collapsed",
                placeholder=f"Add {category[:-1] if category.endswith('s') else category}…",
            )
            if btn_col.button("＋ Add", key=f"add_{category}"):
                tag = new_tag.strip()
                if tag and tag not in tags:
                    tags.append(tag)
                    kw_data[category] = tags
                    changed = True

            st.markdown("---")

        if changed:
            save_yaml(KEYWORDS_CFG, kw_data)
            st.success("Saved.")
            st.rerun()

# ── Fine-Tune Wizard tab ───────────────────────────────────────────────────────
with tab_finetune:
    if not _show_finetune:
        st.info(
            f"Fine-tuning requires a GPU profile. "
            f"Current profile: `{_profile.inference_profile if _profile else 'not configured'}`. "
            "Change it in **My Profile** to enable this feature."
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
            uploaded = st.file_uploader(
                "Upload cover letters (PDF, DOCX, or TXT)",
                type=["pdf", "docx", "txt"],
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
            st.markdown("**Step 2: Preview Training Pairs**")
            st.info("Run `python scripts/prepare_training_data.py` to extract pairs, then return here.")
            jsonl_path = _profile.docs_dir / "training_data" / "cover_letters.jsonl"
            if jsonl_path.exists():
                import json as _json
                pairs = [_json.loads(l) for l in jsonl_path.read_text().splitlines() if l.strip()]
                st.caption(f"{len(pairs)} training pairs extracted.")
                for i, p in enumerate(pairs[:3]):
                    with st.expander(f"Pair {i+1}"):
                        st.text(p.get("input", "")[:300])
            else:
                st.warning("No training pairs found. Run `prepare_training_data.py` first.")
            col_back, col_next = st.columns([1, 4])
            if col_back.button("← Back", key="ft_back2"):
                st.session_state.ft_step = 1
                st.rerun()
            if col_next.button("Start Training →", type="primary", key="ft_next2"):
                st.session_state.ft_step = 3
                st.rerun()

        elif ft_step == 3:
            st.markdown("**Step 3: Train**")
            st.slider("Epochs", 3, 20, 10, key="ft_epochs")
            if st.button("🚀 Start Fine-Tune", type="primary", key="ft_start"):
                st.info("Fine-tune queued as a background task. Check back in 30–60 minutes.")
            if st.button("← Back", key="ft_back3"):
                st.session_state.ft_step = 2
                st.rerun()

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
