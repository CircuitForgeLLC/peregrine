"""
First-run setup wizard — shown by app.py when config/user.yaml is absent.
Five steps: hardware detection → identity → NDA companies → inference/keys → Notion.
Writes config/user.yaml (and optionally config/notion.yaml) on completion.
"""
import subprocess
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import streamlit as st
import yaml

CONFIG_DIR = Path(__file__).parent.parent.parent / "config"
USER_CFG   = CONFIG_DIR / "user.yaml"
NOTION_CFG = CONFIG_DIR / "notion.yaml"
LLM_CFG    = CONFIG_DIR / "llm.yaml"

PROFILES = ["remote", "cpu", "single-gpu", "dual-gpu"]


def _detect_gpus() -> list[str]:
    """Return list of GPU names via nvidia-smi, or [] if none."""
    try:
        out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
            text=True, timeout=5
        )
        return [l.strip() for l in out.strip().splitlines() if l.strip()]
    except Exception:
        return []


def _suggest_profile(gpus: list[str]) -> str:
    if len(gpus) >= 2:
        return "dual-gpu"
    if len(gpus) == 1:
        return "single-gpu"
    return "remote"


# ── Wizard state ───────────────────────────────────────────────────────────────
if "wizard_step" not in st.session_state:
    st.session_state.wizard_step = 1
if "wizard_data" not in st.session_state:
    st.session_state.wizard_data = {}

step = st.session_state.wizard_step
data = st.session_state.wizard_data

st.title("👋 Welcome to Peregrine")
st.caption("Let's get you set up. This takes about 2 minutes.")
st.progress(step / 5, text=f"Step {step} of 5")
st.divider()

# ── Step 1: Hardware detection ─────────────────────────────────────────────────
if step == 1:
    st.subheader("Step 1 — Hardware Detection")
    gpus = _detect_gpus()
    suggested = _suggest_profile(gpus)

    if gpus:
        st.success(f"Found {len(gpus)} GPU(s): {', '.join(gpus)}")
    else:
        st.info("No NVIDIA GPUs detected. Remote or CPU mode recommended.")

    profile = st.selectbox(
        "Inference mode",
        PROFILES,
        index=PROFILES.index(suggested),
        help="This controls which Docker services start. You can change it later in Settings → My Profile.",
    )
    if profile in ("single-gpu", "dual-gpu") and not gpus:
        st.warning("No GPUs detected — GPU profiles require NVIDIA Container Toolkit. See the README for install instructions.")

    if st.button("Next →", type="primary"):
        data["inference_profile"] = profile
        data["gpus_detected"] = gpus
        st.session_state.wizard_step = 2
        st.rerun()

# ── Step 2: Identity ───────────────────────────────────────────────────────────
elif step == 2:
    st.subheader("Step 2 — Your Identity")
    st.caption("Used in cover letter PDFs, LLM prompts, and the app header.")
    c1, c2 = st.columns(2)
    name     = c1.text_input("Full Name *",   data.get("name", ""))
    email    = c1.text_input("Email *",        data.get("email", ""))
    phone    = c2.text_input("Phone",          data.get("phone", ""))
    linkedin = c2.text_input("LinkedIn URL",   data.get("linkedin", ""))
    summary  = st.text_area(
        "Career Summary *",
        data.get("career_summary", ""),
        height=120,
        placeholder="Experienced professional with X years in [field]. Specialise in [skills].",
        help="This paragraph is injected into cover letter and research prompts as your professional context.",
    )

    col_back, col_next = st.columns([1, 4])
    if col_back.button("← Back"):
        st.session_state.wizard_step = 1
        st.rerun()
    if col_next.button("Next →", type="primary"):
        if not name or not email or not summary:
            st.error("Name, email, and career summary are required.")
        else:
            data.update({"name": name, "email": email, "phone": phone,
                         "linkedin": linkedin, "career_summary": summary})
            st.session_state.wizard_step = 3
            st.rerun()

# ── Step 3: NDA Companies ──────────────────────────────────────────────────────
elif step == 3:
    st.subheader("Step 3 — Sensitive Employers (Optional)")
    st.caption(
        "Previous employers listed here will appear as 'previous employer (NDA)' in "
        "research briefs and talking points. Skip if not applicable."
    )
    nda_list = list(data.get("nda_companies", []))
    if nda_list:
        cols = st.columns(min(len(nda_list), 5))
        to_remove = None
        for i, c in enumerate(nda_list):
            if cols[i % 5].button(f"× {c}", key=f"rm_{c}"):
                to_remove = c
        if to_remove:
            nda_list.remove(to_remove)
            data["nda_companies"] = nda_list
            st.rerun()
    nc, nb = st.columns([4, 1])
    new_c = nc.text_input("Add employer", key="new_nda_wiz",
                           label_visibility="collapsed", placeholder="Employer name…")
    if nb.button("＋ Add") and new_c.strip():
        nda_list.append(new_c.strip())
        data["nda_companies"] = nda_list
        st.rerun()

    col_back, col_skip, col_next = st.columns([1, 1, 3])
    if col_back.button("← Back"):
        st.session_state.wizard_step = 2
        st.rerun()
    if col_skip.button("Skip"):
        data.setdefault("nda_companies", [])
        st.session_state.wizard_step = 4
        st.rerun()
    if col_next.button("Next →", type="primary"):
        data["nda_companies"] = nda_list
        st.session_state.wizard_step = 4
        st.rerun()

# ── Step 4: Inference & API Keys ───────────────────────────────────────────────
elif step == 4:
    profile = data.get("inference_profile", "remote")
    st.subheader("Step 4 — Inference & API Keys")

    if profile == "remote":
        st.info("Remote mode: LLM calls go to external APIs. At least one key is needed.")
        anthropic_key = st.text_input("Anthropic API Key", type="password",
                                       placeholder="sk-ant-…")
        openai_url = st.text_input("OpenAI-compatible endpoint (optional)",
                                    placeholder="https://api.together.xyz/v1")
        openai_key = st.text_input("Endpoint API Key (optional)", type="password") if openai_url else ""
        data.update({"anthropic_key": anthropic_key, "openai_url": openai_url,
                     "openai_key": openai_key})
    else:
        st.info(f"Local mode ({profile}): Ollama handles cover letters. Configure model below.")
        ollama_model = st.text_input("Cover letter model name",
                                      data.get("ollama_model", "llama3.2:3b"),
                                      help="This model will be pulled by Ollama on first start.")
        data["ollama_model"] = ollama_model

    st.divider()
    with st.expander("Advanced — Service Ports & Hosts"):
        st.caption("Change only if services run on non-default ports or remote hosts.")
        svc = data.get("services", {})
        for svc_name, default_host, default_port in [
            ("ollama",  "localhost", 11434),
            ("vllm",    "localhost", 8000),
            ("searxng", "localhost", 8888),
        ]:
            c1, c2, c3, c4 = st.columns([2, 1, 0.5, 0.5])
            svc[f"{svc_name}_host"]       = c1.text_input(f"{svc_name} host", svc.get(f"{svc_name}_host", default_host), key=f"adv_{svc_name}_host")
            svc[f"{svc_name}_port"]       = int(c2.number_input("port", value=svc.get(f"{svc_name}_port", default_port), step=1, key=f"adv_{svc_name}_port"))
            svc[f"{svc_name}_ssl"]        = c3.checkbox("SSL",    svc.get(f"{svc_name}_ssl", False),       key=f"adv_{svc_name}_ssl")
            svc[f"{svc_name}_ssl_verify"] = c4.checkbox("Verify", svc.get(f"{svc_name}_ssl_verify", True), key=f"adv_{svc_name}_verify")
        data["services"] = svc

    col_back, col_next = st.columns([1, 4])
    if col_back.button("← Back"):
        st.session_state.wizard_step = 3
        st.rerun()
    if col_next.button("Next →", type="primary"):
        st.session_state.wizard_step = 5
        st.rerun()

# ── Step 5: Notion (optional) ──────────────────────────────────────────────────
elif step == 5:
    st.subheader("Step 5 — Notion Sync (Optional)")
    st.caption("Syncs approved and applied jobs to a Notion database. Skip if not using Notion.")
    notion_token = st.text_input("Integration Token", type="password", placeholder="secret_…")
    notion_db    = st.text_input("Database ID", placeholder="32-character ID from Notion URL")

    if notion_token and notion_db:
        if st.button("🔌 Test connection"):
            with st.spinner("Connecting…"):
                try:
                    from notion_client import Client
                    db = Client(auth=notion_token).databases.retrieve(notion_db)
                    st.success(f"Connected: {db['title'][0]['plain_text']}")
                except Exception as e:
                    st.error(f"Connection failed: {e}")

    col_back, col_skip, col_finish = st.columns([1, 1, 3])
    if col_back.button("← Back"):
        st.session_state.wizard_step = 4
        st.rerun()

    def _finish(save_notion: bool) -> None:
        svc_defaults = {
            "streamlit_port": 8501,
            "ollama_host":   "localhost", "ollama_port": 11434,
            "ollama_ssl":    False,       "ollama_ssl_verify": True,
            "vllm_host":     "localhost", "vllm_port":   8000,
            "vllm_ssl":      False,       "vllm_ssl_verify":   True,
            "searxng_host":  "localhost", "searxng_port": 8888,
            "searxng_ssl":   False,       "searxng_ssl_verify": True,
        }
        svc_defaults.update(data.get("services", {}))
        user_data = {
            "name":             data.get("name", ""),
            "email":            data.get("email", ""),
            "phone":            data.get("phone", ""),
            "linkedin":         data.get("linkedin", ""),
            "career_summary":   data.get("career_summary", ""),
            "nda_companies":    data.get("nda_companies", []),
            "docs_dir":         "~/Documents/JobSearch",
            "ollama_models_dir": "~/models/ollama",
            "vllm_models_dir":  "~/models/vllm",
            "inference_profile": data.get("inference_profile", "remote"),
            "services":         svc_defaults,
        }
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        USER_CFG.write_text(yaml.dump(user_data, default_flow_style=False, allow_unicode=True))

        if LLM_CFG.exists():
            from scripts.user_profile import UserProfile
            from scripts.generate_llm_config import apply_service_urls
            apply_service_urls(UserProfile(USER_CFG), LLM_CFG)

        if save_notion and notion_token and notion_db:
            NOTION_CFG.write_text(yaml.dump({
                "token": notion_token,
                "database_id": notion_db,
            }))

        st.session_state.wizard_step = 1
        st.session_state.wizard_data = {}
        st.success("Setup complete! Redirecting…")
        st.rerun()

    if col_skip.button("Skip & Finish"):
        _finish(save_notion=False)
    if col_finish.button("💾 Save & Finish", type="primary"):
        _finish(save_notion=True)
