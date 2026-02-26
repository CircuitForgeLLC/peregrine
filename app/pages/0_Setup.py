"""
First-run setup wizard orchestrator.
Shown by app.py when user.yaml is absent OR wizard_complete is False.
Seven steps: hardware → tier → identity → resume → inference → search → integrations (optional).
Steps 1-6 are mandatory; step 7 is optional and can be skipped.
Each step writes to user.yaml on "Next" for crash recovery.
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import streamlit as st
import yaml

_ROOT       = Path(__file__).parent.parent.parent
CONFIG_DIR  = _ROOT / "config"
USER_YAML   = CONFIG_DIR / "user.yaml"
STEPS       = 6  # mandatory steps
STEP_LABELS = ["Hardware", "Tier", "Identity", "Resume", "Inference", "Search"]


# ── Helpers ────────────────────────────────────────────────────────────────────

def _load_yaml() -> dict:
    if USER_YAML.exists():
        return yaml.safe_load(USER_YAML.read_text()) or {}
    return {}


def _save_yaml(updates: dict) -> None:
    existing = _load_yaml()
    existing.update(updates)
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    USER_YAML.write_text(
        yaml.dump(existing, default_flow_style=False, allow_unicode=True)
    )


def _detect_gpus() -> list[str]:
    """Detect GPUs. Prefers env vars written by preflight (works inside Docker)."""
    import os
    import subprocess
    # Preflight writes PEREGRINE_GPU_NAMES to .env; compose passes it to the container.
    # This is the reliable path when running inside Docker without nvidia-smi access.
    env_names = os.environ.get("PEREGRINE_GPU_NAMES", "").strip()
    if env_names:
        return [n.strip() for n in env_names.split(",") if n.strip()]
    # Fallback: try nvidia-smi directly (works when running bare or with GPU passthrough)
    try:
        out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
            text=True, timeout=5,
        )
        return [l.strip() for l in out.strip().splitlines() if l.strip()]
    except Exception:
        return []


def _suggest_profile(gpus: list[str]) -> str:
    import os
    # If preflight already ran and wrote a profile recommendation, use it.
    recommended = os.environ.get("RECOMMENDED_PROFILE", "").strip()
    if recommended:
        return recommended
    if len(gpus) >= 2:
        return "dual-gpu"
    if len(gpus) == 1:
        return "single-gpu"
    return "remote"


def _submit_wizard_task(section: str, input_data: dict) -> int:
    """Submit a wizard_generate background task. Returns task_id."""
    from scripts.db import DEFAULT_DB
    from scripts.task_runner import submit_task
    params = json.dumps({"section": section, "input": input_data})
    task_id, _ = submit_task(DEFAULT_DB, "wizard_generate", 0, params=params)
    return task_id


def _poll_wizard_task(section: str) -> dict | None:
    """Return the most recent wizard_generate task row for a given section, or None."""
    import sqlite3
    from scripts.db import DEFAULT_DB
    conn = sqlite3.connect(DEFAULT_DB)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT * FROM background_tasks "
        "WHERE task_type='wizard_generate' AND params LIKE ? "
        "ORDER BY id DESC LIMIT 1",
        (f'%"section": "{section}"%',),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def _generation_widget(section: str, label: str, tier: str,
                        feature_key: str, input_data: dict) -> str | None:
    """Render a generation button + polling fragment.

    Returns the generated result string if completed and not yet applied, else None.
    Call this inside a step to add LLM generation support.
    The caller decides whether to auto-populate a field with the result.
    """
    from app.wizard.tiers import can_use, tier_label as tl

    if not can_use(tier, feature_key):
        st.caption(f"{tl(feature_key)} {label}")
        return None

    col_btn, col_fb = st.columns([2, 5])
    if col_btn.button(f"\u2728 {label}", key=f"gen_{section}"):
        _submit_wizard_task(section, input_data)
        st.rerun()

    with st.expander("\u270f\ufe0f Request changes (optional)", expanded=False):
        prev = st.session_state.get(f"_gen_result_{section}", "")
        feedback = st.text_area(
            "Describe what to change", key=f"_feedback_{section}",
            placeholder="e.g. Make it shorter and emphasise leadership",
            height=60,
        )
        if prev and st.button(f"\u21ba Regenerate with feedback", key=f"regen_{section}"):
            _submit_wizard_task(section, {**input_data,
                                          "previous_result": prev,
                                          "feedback": feedback})
            st.rerun()

    # Polling fragment
    result_key = f"_gen_result_{section}"

    @st.fragment(run_every=3)
    def _poll():
        task = _poll_wizard_task(section)
        if not task:
            return
        status = task.get("status")
        if status in ("queued", "running"):
            stage = task.get("stage") or "Queued"
            st.info(f"\u23f3 {stage}\u2026")
        elif status == "completed":
            payload = json.loads(task.get("error") or "{}")
            result = payload.get("result", "")
            if result and result != st.session_state.get(result_key):
                st.session_state[result_key] = result
                st.rerun()
        elif status == "failed":
            st.warning(f"Generation failed: {task.get('error', 'unknown error')}")

    _poll()

    return st.session_state.get(result_key)


# ── Wizard state init ──────────────────────────────────────────────────────────

if "wizard_step" not in st.session_state:
    saved = _load_yaml()
    last_completed = saved.get("wizard_step", 0)
    st.session_state.wizard_step = min(last_completed + 1, STEPS + 1)  # resume at next step

step = st.session_state.wizard_step
saved_yaml = _load_yaml()
_tier = saved_yaml.get("dev_tier_override") or saved_yaml.get("tier", "free")

st.title("\U0001f44b Welcome to Peregrine")
st.caption("Complete the setup to start your job search. Progress saves automatically.")
st.progress(
    min((step - 1) / STEPS, 1.0),
    text=f"Step {min(step, STEPS)} of {STEPS}" if step <= STEPS else "Almost done!",
)
st.divider()


# ── Step 1: Hardware ───────────────────────────────────────────────────────────
if step == 1:
    from app.wizard.step_hardware import validate, PROFILES

    st.subheader("Step 1 \u2014 Hardware Detection")
    gpus = _detect_gpus()
    suggested = _suggest_profile(gpus)

    if gpus:
        st.success(f"Detected {len(gpus)} GPU(s): {', '.join(gpus)}")
    else:
        st.info("No NVIDIA GPUs detected. 'Remote' or 'CPU' mode recommended.")

    profile = st.selectbox(
        "Inference mode", PROFILES, index=PROFILES.index(suggested),
        help="Controls which Docker services start. Change later in Settings \u2192 Services.",
    )
    if profile in ("single-gpu", "dual-gpu") and not gpus:
        st.warning(
            "No GPUs detected \u2014 GPU profiles require the NVIDIA Container Toolkit. "
            "See README for install instructions."
        )

    if st.button("Next \u2192", type="primary", key="hw_next"):
        errs = validate({"inference_profile": profile})
        if errs:
            st.error("\n".join(errs))
        else:
            _save_yaml({"inference_profile": profile, "wizard_step": 1})
            st.session_state.wizard_step = 2
            st.rerun()


# ── Step 2: Tier ───────────────────────────────────────────────────────────────
elif step == 2:
    from app.wizard.step_tier import validate

    st.subheader("Step 2 \u2014 Choose Your Plan")
    st.caption(
        "**Free** is fully functional for self-hosted local use. "
        "**Paid/Premium** unlock LLM-assisted features."
    )

    tier_options = {
        "free":    "\U0001f193 **Free** \u2014 Local discovery, apply workspace, interviews kanban",
        "paid":    "\U0001f4bc **Paid** \u2014 + AI career summary, company research, email classifier, calendar sync",
        "premium": "\u2b50 **Premium** \u2014 + Voice guidelines, model fine-tuning, multi-user",
    }
    from app.wizard.tiers import TIERS
    current_tier = saved_yaml.get("tier", "free")
    selected_tier = st.radio(
        "Plan",
        list(tier_options.keys()),
        format_func=lambda x: tier_options[x],
        index=TIERS.index(current_tier) if current_tier in TIERS else 0,
    )

    col_back, col_next = st.columns([1, 4])
    if col_back.button("\u2190 Back", key="tier_back"):
        st.session_state.wizard_step = 1
        st.rerun()
    if col_next.button("Next \u2192", type="primary", key="tier_next"):
        errs = validate({"tier": selected_tier})
        if errs:
            st.error("\n".join(errs))
        else:
            _save_yaml({"tier": selected_tier, "wizard_step": 2})
            st.session_state.wizard_step = 3
            st.rerun()


# ── Step 3: Identity ───────────────────────────────────────────────────────────
elif step == 3:
    from app.wizard.step_identity import validate

    st.subheader("Step 3 \u2014 Your Identity")
    st.caption("Used in cover letter PDFs, LLM prompts, and the app header.")

    c1, c2 = st.columns(2)
    name     = c1.text_input("Full Name *",  saved_yaml.get("name", ""))
    email    = c1.text_input("Email *",      saved_yaml.get("email", ""))
    phone    = c2.text_input("Phone",        saved_yaml.get("phone", ""))
    linkedin = c2.text_input("LinkedIn URL", saved_yaml.get("linkedin", ""))

    # Career summary with optional LLM generation
    summary_default = st.session_state.get("_gen_result_career_summary") or saved_yaml.get("career_summary", "")
    summary = st.text_area(
        "Career Summary *", value=summary_default, height=120,
        placeholder="Experienced professional with X years in [field]. Specialise in [skills].",
        help="Injected into cover letter and research prompts as your professional context.",
    )

    gen_result = _generation_widget(
        section="career_summary",
        label="Generate from resume",
        tier=_tier,
        feature_key="llm_career_summary",
        input_data={"resume_text": saved_yaml.get("_raw_resume_text", "")},
    )
    if gen_result and gen_result != summary:
        st.info(f"\u2728 Suggested summary \u2014 paste it above if it looks good:\n\n{gen_result}")

    col_back, col_next = st.columns([1, 4])
    if col_back.button("\u2190 Back", key="ident_back"):
        st.session_state.wizard_step = 2
        st.rerun()
    if col_next.button("Next \u2192", type="primary", key="ident_next"):
        errs = validate({"name": name, "email": email, "career_summary": summary})
        if errs:
            st.error("\n".join(errs))
        else:
            _save_yaml({
                "name": name, "email": email, "phone": phone,
                "linkedin": linkedin, "career_summary": summary,
                "wizard_complete": False, "wizard_step": 3,
            })
            st.session_state.wizard_step = 4
            st.rerun()


# ── Step 4: Resume ─────────────────────────────────────────────────────────────
elif step == 4:
    from app.wizard.step_resume import validate

    st.subheader("Step 4 \u2014 Resume")
    st.caption("Upload your resume for fast parsing, or build it section by section.")

    tab_upload, tab_builder = st.tabs(["\U0001f4ce Upload", "\U0001f4dd Build manually"])

    with tab_upload:
        uploaded = st.file_uploader("Upload PDF or DOCX", type=["pdf", "docx"])
        if uploaded and st.button("Parse Resume", type="primary", key="parse_resume"):
            from scripts.resume_parser import (
                extract_text_from_pdf, extract_text_from_docx, structure_resume,
            )
            file_bytes = uploaded.read()
            ext = uploaded.name.rsplit(".", 1)[-1].lower()
            raw_text = (
                extract_text_from_pdf(file_bytes) if ext == "pdf"
                else extract_text_from_docx(file_bytes)
            )
            with st.spinner("Parsing\u2026"):
                parsed, parse_err = structure_resume(raw_text)

            # Diagnostic: show raw extraction + detected fields regardless of outcome
            with st.expander("🔍 Parse diagnostics", expanded=not bool(parsed and any(
                parsed.get(k) for k in ("name", "experience", "skills")
            ))):
                st.caption("**Raw extracted text (first 800 chars)**")
                st.code(raw_text[:800] if raw_text else "(empty)", language="text")
                if parsed:
                    st.caption("**Detected fields**")
                    st.json({k: (v[:3] if isinstance(v, list) else v) for k, v in parsed.items()})

            if parsed and any(parsed.get(k) for k in ("name", "experience", "skills")):
                st.session_state["_parsed_resume"] = parsed
                st.session_state["_raw_resume_text"] = raw_text
                _save_yaml({"_raw_resume_text": raw_text[:8000]})
                st.success("Parsed! Review the builder tab to edit entries.")
            elif parsed:
                # Parsed but empty — show what we got and let them proceed or build manually
                st.session_state["_parsed_resume"] = parsed
                st.warning("Resume text was extracted but no fields were recognised. "
                           "Check the diagnostics above — the section headers may use unusual labels. "
                           "You can still fill in the Build tab manually.")
            else:
                st.warning("Auto-parse failed \u2014 switch to the Build tab and add entries manually.")
                if parse_err:
                    st.caption(f"Reason: {parse_err}")

    with tab_builder:
        parsed = st.session_state.get("_parsed_resume", {})
        experience = st.session_state.get(
            "_experience",
            parsed.get("experience") or saved_yaml.get("experience", []),
        )

        for i, entry in enumerate(experience):
            with st.expander(
                f"{entry.get('title', 'Entry')} @ {entry.get('company', '?')}",
                expanded=(i == len(experience) - 1),
            ):
                entry["company"] = st.text_input("Company", entry.get("company", ""), key=f"co_{i}")
                entry["title"]   = st.text_input("Title",   entry.get("title",   ""), key=f"ti_{i}")
                raw_bullets = st.text_area(
                    "Responsibilities (one per line)",
                    "\n".join(entry.get("bullets", [])),
                    key=f"bu_{i}", height=80,
                )
                entry["bullets"] = [b.strip() for b in raw_bullets.splitlines() if b.strip()]
                if st.button("Remove entry", key=f"rm_{i}"):
                    experience.pop(i)
                    st.session_state["_experience"] = experience
                    st.rerun()

        if st.button("\uff0b Add work experience entry", key="add_exp"):
            experience.append({"company": "", "title": "", "bullets": []})
            st.session_state["_experience"] = experience
            st.rerun()

        # Bullet expansion generation
        if experience:
            all_bullets = "\n".join(
                b for e in experience for b in e.get("bullets", [])
            )
            _generation_widget(
                section="expand_bullets",
                label="Expand bullet points",
                tier=_tier,
                feature_key="llm_expand_bullets",
                input_data={"bullet_notes": all_bullets},
            )

    col_back, col_next = st.columns([1, 4])
    if col_back.button("\u2190 Back", key="resume_back"):
        st.session_state.wizard_step = 3
        st.rerun()
    if col_next.button("Next \u2192", type="primary", key="resume_next"):
        parsed = st.session_state.get("_parsed_resume", {})
        experience = (
            parsed.get("experience") or
            st.session_state.get("_experience", [])
        )
        errs = validate({"experience": experience})
        if errs:
            st.error("\n".join(errs))
        else:
            resume_yaml_path = _ROOT / "aihawk" / "data_folder" / "plain_text_resume.yaml"
            resume_yaml_path.parent.mkdir(parents=True, exist_ok=True)
            resume_data = {**parsed, "experience": experience} if parsed else {"experience": experience}
            resume_yaml_path.write_text(
                yaml.dump(resume_data, default_flow_style=False, allow_unicode=True)
            )
            _save_yaml({"wizard_step": 4})
            st.session_state.wizard_step = 5
            st.rerun()


# ── Step 5: Inference ──────────────────────────────────────────────────────────
elif step == 5:
    from app.wizard.step_inference import validate

    st.subheader("Step 5 \u2014 Inference & API Keys")
    profile = saved_yaml.get("inference_profile", "remote")

    if profile == "remote":
        st.info("Remote mode: at least one external API key is required.")
        anthropic_key = st.text_input("Anthropic API Key", type="password", placeholder="sk-ant-\u2026")
        openai_url    = st.text_input("OpenAI-compatible endpoint (optional)",
                                       placeholder="https://api.together.xyz/v1")
        openai_key    = st.text_input("Endpoint API Key (optional)", type="password",
                                       key="oai_key") if openai_url else ""
    else:
        st.info(f"Local mode ({profile}): Ollama provides inference.")
        anthropic_key = openai_url = openai_key = ""

    with st.expander("Advanced \u2014 Service Ports & Hosts"):
        st.caption("Change only if services run on non-default ports or remote hosts.")
        svc = dict(saved_yaml.get("services", {}))
        for svc_name, default_host, default_port in [
            ("ollama",  "ollama",   11434),  # Docker service name
            ("vllm",    "vllm",     8000),   # Docker service name
            ("searxng", "searxng",  8080),   # Docker internal port (host-mapped: 8888)
        ]:
            c1, c2 = st.columns([3, 1])
            svc[f"{svc_name}_host"] = c1.text_input(
                f"{svc_name} host",
                svc.get(f"{svc_name}_host", default_host),
                key=f"h_{svc_name}",
            )
            svc[f"{svc_name}_port"] = int(c2.number_input(
                "port",
                value=int(svc.get(f"{svc_name}_port", default_port)),
                step=1, key=f"p_{svc_name}",
            ))

    confirmed = st.session_state.get("_inf_confirmed", False)
    test_label = "\U0001f50c Test Ollama connection" if profile != "remote" else "\U0001f50c Test LLM connection"
    if st.button(test_label, key="inf_test"):
        if profile == "remote":
            from scripts.llm_router import LLMRouter
            try:
                r = LLMRouter().complete("Reply with only: OK")
                if r and r.strip():
                    st.success("LLM responding.")
                    st.session_state["_inf_confirmed"] = True
                    confirmed = True
            except Exception as e:
                st.error(f"LLM test failed: {e}")
        else:
            import requests
            ollama_url = f"http://{svc.get('ollama_host','localhost')}:{svc.get('ollama_port',11434)}"
            try:
                requests.get(f"{ollama_url}/api/tags", timeout=5)
                st.success("Ollama is running.")
                st.session_state["_inf_confirmed"] = True
                confirmed = True
            except Exception:
                st.warning("Ollama not responding \u2014 you can skip this check and configure later.")
                st.session_state["_inf_confirmed"] = True
                confirmed = True

    col_back, col_next = st.columns([1, 4])
    if col_back.button("\u2190 Back", key="inf_back"):
        st.session_state.wizard_step = 4
        st.rerun()
    if col_next.button("Next \u2192", type="primary", key="inf_next", disabled=not confirmed):
        errs = validate({"endpoint_confirmed": confirmed})
        if errs:
            st.error("\n".join(errs))
        else:
            # Write API keys to .env
            env_path = _ROOT / ".env"
            env_lines = env_path.read_text().splitlines() if env_path.exists() else []

            def _set_env(lines: list[str], key: str, val: str) -> list[str]:
                for i, l in enumerate(lines):
                    if l.startswith(f"{key}="):
                        lines[i] = f"{key}={val}"
                        return lines
                lines.append(f"{key}={val}")
                return lines

            if anthropic_key:
                env_lines = _set_env(env_lines, "ANTHROPIC_API_KEY", anthropic_key)
            if openai_url:
                env_lines = _set_env(env_lines, "OPENAI_COMPAT_URL", openai_url)
            if openai_key:
                env_lines = _set_env(env_lines, "OPENAI_COMPAT_KEY", openai_key)
            if anthropic_key or openai_url:
                env_path.write_text("\n".join(env_lines) + "\n")

            _save_yaml({"services": svc, "wizard_step": 5})
            st.session_state.wizard_step = 6
            st.rerun()


# ── Step 6: Search ─────────────────────────────────────────────────────────────
elif step == 6:
    from app.wizard.step_search import validate

    st.subheader("Step 6 \u2014 Job Search Preferences")
    st.caption("Set up what to search for. You can refine these in Settings \u2192 Search later.")

    titles    = st.session_state.get("_titles",    saved_yaml.get("_wiz_titles", []))
    locations = st.session_state.get("_locations", saved_yaml.get("_wiz_locations", []))

    c1, c2 = st.columns(2)

    with c1:
        st.markdown("**Job Titles**")
        for i, t in enumerate(titles):
            tc1, tc2 = st.columns([5, 1])
            tc1.text(t)
            if tc2.button("\u00d7", key=f"rmtitle_{i}"):
                titles.pop(i)
                st.session_state["_titles"] = titles
                st.rerun()
        new_title = st.text_input("Add title", key="new_title_wiz",
                                   placeholder="Software Engineer, Product Manager\u2026")
        ac1, ac2 = st.columns([4, 1])
        if ac2.button("\uff0b", key="add_title"):
            if new_title.strip() and new_title.strip() not in titles:
                titles.append(new_title.strip())
                st.session_state["_titles"] = titles
                st.rerun()

        # LLM title suggestions
        _generation_widget(
            section="job_titles",
            label="Suggest job titles",
            tier=_tier,
            feature_key="llm_job_titles",
            input_data={
                "resume_text": saved_yaml.get("_raw_resume_text", ""),
                "current_titles": str(titles),
            },
        )

    with c2:
        st.markdown("**Locations**")
        for i, l in enumerate(locations):
            lc1, lc2 = st.columns([5, 1])
            lc1.text(l)
            if lc2.button("\u00d7", key=f"rmloc_{i}"):
                locations.pop(i)
                st.session_state["_locations"] = locations
                st.rerun()
        new_loc = st.text_input("Add location", key="new_loc_wiz",
                                 placeholder="Remote, New York NY, San Francisco CA\u2026")
        ll1, ll2 = st.columns([4, 1])
        if ll2.button("\uff0b", key="add_loc"):
            if new_loc.strip():
                locations.append(new_loc.strip())
                st.session_state["_locations"] = locations
                st.rerun()

    col_back, col_next = st.columns([1, 4])
    if col_back.button("\u2190 Back", key="search_back"):
        st.session_state.wizard_step = 5
        st.rerun()
    if col_next.button("Next \u2192", type="primary", key="search_next"):
        errs = validate({"job_titles": titles, "locations": locations})
        if errs:
            st.error("\n".join(errs))
        else:
            search_profile_path = CONFIG_DIR / "search_profiles.yaml"
            existing_profiles = {}
            if search_profile_path.exists():
                existing_profiles = yaml.safe_load(search_profile_path.read_text()) or {}
            profiles_list = existing_profiles.get("profiles", [])
            # Update or create "default" profile
            default_idx = next(
                (i for i, p in enumerate(profiles_list) if p.get("name") == "default"), None
            )
            default_profile = {
                "name": "default",
                "job_titles": titles,
                "locations": locations,
                "remote_only": False,
                "boards": ["linkedin", "indeed", "glassdoor", "zip_recruiter"],
            }
            if default_idx is not None:
                profiles_list[default_idx] = default_profile
            else:
                profiles_list.insert(0, default_profile)
            search_profile_path.write_text(
                yaml.dump({"profiles": profiles_list},
                          default_flow_style=False, allow_unicode=True)
            )
            _save_yaml({"wizard_step": 6})
            st.session_state.wizard_step = 7
            st.rerun()


# ── Step 7: Integrations (optional) ───────────────────────────────────────────
elif step == 7:
    st.subheader("Step 7 \u2014 Integrations (Optional)")
    st.caption(
        "Connect cloud services, calendars, and notification tools. "
        "You can add or change these any time in Settings \u2192 Integrations."
    )

    from scripts.integrations import REGISTRY
    from app.wizard.step_integrations import get_available, is_connected
    from app.wizard.tiers import tier_label

    available = get_available(_tier)

    for name, cls in sorted(REGISTRY.items(), key=lambda x: (x[0] not in available, x[0])):
        is_conn = is_connected(name, CONFIG_DIR)
        icon    = "\u2705" if is_conn else "\u25cb"
        lock    = tier_label(f"{name}_sync") or tier_label(f"{name}_notifications")

        with st.expander(f"{icon} {cls.label}  {lock}"):
            if name not in available:
                st.caption(f"Upgrade to {cls.tier} to unlock {cls.label}.")
                continue

            inst   = cls()
            config: dict = {}
            for field in inst.fields():
                val = st.text_input(
                    field["label"],
                    type="password" if field["type"] == "password" else "default",
                    placeholder=field.get("placeholder", ""),
                    help=field.get("help", ""),
                    key=f"int_{name}_{field['key']}",
                )
                config[field["key"]] = val

            required_filled = all(
                config.get(f["key"])
                for f in inst.fields()
                if f.get("required")
            )
            if st.button(f"Connect {cls.label}", key=f"conn_{name}",
                          disabled=not required_filled):
                inst.connect(config)
                with st.spinner(f"Testing {cls.label} connection\u2026"):
                    if inst.test():
                        inst.save_config(config, CONFIG_DIR)
                        st.success(f"{cls.label} connected!")
                        st.rerun()
                    else:
                        st.error(
                            f"Connection test failed for {cls.label}. "
                            "Double-check your credentials."
                        )

    st.divider()
    col_back, col_skip, col_finish = st.columns([1, 1, 3])

    if col_back.button("\u2190 Back", key="int_back"):
        st.session_state.wizard_step = 6
        st.rerun()

    if col_skip.button("Skip \u2192"):
        st.session_state.wizard_step = 8  # trigger Finish
        st.rerun()

    if col_finish.button("\U0001f389 Finish Setup", type="primary", key="finish_btn"):
        st.session_state.wizard_step = 8
        st.rerun()


# ── Finish ─────────────────────────────────────────────────────────────────────
elif step >= 8:
    with st.spinner("Finalising setup\u2026"):
        from scripts.user_profile import UserProfile
        from scripts.generate_llm_config import apply_service_urls

        try:
            profile_obj = UserProfile(USER_YAML)
            if (CONFIG_DIR / "llm.yaml").exists():
                apply_service_urls(profile_obj, CONFIG_DIR / "llm.yaml")
        except Exception:
            pass  # don't block finish on llm.yaml errors

        data = _load_yaml()
        data["wizard_complete"] = True
        data.pop("wizard_step", None)
        USER_YAML.write_text(
            yaml.dump(data, default_flow_style=False, allow_unicode=True)
        )

    st.success("\u2705 Setup complete! Loading Peregrine\u2026")
    st.session_state.clear()
    st.rerun()
