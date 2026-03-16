# peregrine/app/cloud_session.py
"""
Cloud session middleware for multi-tenant Peregrine deployment.

In local-first mode (CLOUD_MODE unset or false), all functions are no-ops.
In cloud mode (CLOUD_MODE=true), resolves the Directus session JWT from the
X-CF-Session header, validates it, and injects user_id + db_path into
st.session_state.

All Peregrine pages call get_db_path() instead of DEFAULT_DB directly to
transparently support both local and cloud deployments.
"""
import logging
import os
import re
import hmac
import hashlib
from pathlib import Path

import requests
import streamlit as st

from scripts.db import DEFAULT_DB

log = logging.getLogger(__name__)

CLOUD_MODE: bool = os.environ.get("CLOUD_MODE", "").lower() in ("1", "true", "yes")
CLOUD_DATA_ROOT: Path = Path(os.environ.get("CLOUD_DATA_ROOT", "/devl/menagerie-data"))
DIRECTUS_JWT_SECRET: str = os.environ.get("DIRECTUS_JWT_SECRET", "")
SERVER_SECRET: str = os.environ.get("CF_SERVER_SECRET", "")

# Heimdall license server — internal URL preferred when running on the same host
HEIMDALL_URL: str = os.environ.get("HEIMDALL_URL", "https://license.circuitforge.tech")
HEIMDALL_ADMIN_TOKEN: str = os.environ.get("HEIMDALL_ADMIN_TOKEN", "")


def _extract_session_token(cookie_header: str) -> str:
    """Extract cf_session value from a Cookie header string."""
    m = re.search(r'(?:^|;)\s*cf_session=([^;]+)', cookie_header)
    return m.group(1).strip() if m else ""


def _ensure_provisioned(user_id: str, product: str) -> None:
    """Call Heimdall /admin/provision for this user if no key exists yet.

    Idempotent — Heimdall does nothing if a key already exists for this
    (user_id, product) pair. Called once per session start so new Google
    OAuth signups get a free key created automatically.
    """
    if not HEIMDALL_ADMIN_TOKEN:
        return
    try:
        requests.post(
            f"{HEIMDALL_URL}/admin/provision",
            json={"directus_user_id": user_id, "product": product, "tier": "free"},
            headers={"Authorization": f"Bearer {HEIMDALL_ADMIN_TOKEN}"},
            timeout=5,
        )
    except Exception as exc:
        log.warning("Heimdall provision failed for user %s: %s", user_id, exc)


@st.cache_data(ttl=300, show_spinner=False)
def _fetch_cloud_tier(user_id: str, product: str) -> str:
    """Call Heimdall to resolve the current cloud tier for this user.

    Cached per (user_id, product) for 5 minutes to avoid hammering Heimdall
    on every Streamlit rerun. Returns "free" on any error so the app degrades
    gracefully rather than blocking the user.
    """
    if not HEIMDALL_ADMIN_TOKEN:
        log.warning("HEIMDALL_ADMIN_TOKEN not set — defaulting tier to free")
        return "free"
    try:
        resp = requests.post(
            f"{HEIMDALL_URL}/admin/cloud/resolve",
            json={"user_id": user_id, "product": product},
            headers={"Authorization": f"Bearer {HEIMDALL_ADMIN_TOKEN}"},
            timeout=5,
        )
        if resp.status_code == 200:
            return resp.json().get("tier", "free")
        if resp.status_code == 404:
            # No cloud key yet — user signed up before provision ran; return free.
            return "free"
        log.warning("Heimdall resolve returned %s — defaulting tier to free", resp.status_code)
    except Exception as exc:
        log.warning("Heimdall tier resolve failed: %s — defaulting to free", exc)
    return "free"


def validate_session_jwt(token: str) -> str:
    """Validate a Directus session JWT and return the user UUID. Raises on failure."""
    import jwt  # PyJWT — lazy import so local mode never needs it
    payload = jwt.decode(token, DIRECTUS_JWT_SECRET, algorithms=["HS256"])
    user_id = payload.get("id") or payload.get("sub")
    if not user_id:
        raise ValueError("JWT missing user id claim")
    return user_id


def _user_data_path(user_id: str, app: str) -> Path:
    return CLOUD_DATA_ROOT / user_id / app


def derive_db_key(user_id: str) -> str:
    """Derive a per-user SQLCipher encryption key from the server secret."""
    return hmac.new(
        SERVER_SECRET.encode(),
        user_id.encode(),
        hashlib.sha256,
    ).hexdigest()


def _render_auth_wall(message: str = "Please sign in to continue.") -> None:
    """Render a branded sign-in prompt and halt the page."""
    st.markdown(
        """
        <style>
        [data-testid="stSidebar"] { display: none; }
        [data-testid="collapsedControl"] { display: none; }
        </style>
        """,
        unsafe_allow_html=True,
    )
    col = st.columns([1, 2, 1])[1]
    with col:
        st.markdown("## 🦅 Peregrine")
        st.info(message, icon="🔒")
        st.link_button(
            "Sign in to CircuitForge",
            url=f"https://circuitforge.tech/login?next=/peregrine",
            use_container_width=True,
        )


def resolve_session(app: str = "peregrine") -> None:
    """
    Call at the top of each Streamlit page.
    In local mode: no-op.
    In cloud mode: reads X-CF-Session header, validates JWT, creates user
    data directory on first visit, and sets st.session_state keys:
      - user_id: str
      - db_path: Path
      - db_key: str   (SQLCipher key for this user)
      - cloud_tier: str  (free | paid | premium | ultra — resolved from Heimdall)
    Idempotent — skips if user_id already in session_state.
    """
    if not CLOUD_MODE:
        return
    if st.session_state.get("user_id"):
        return

    cookie_header = st.context.headers.get("x-cf-session", "")
    session_jwt = _extract_session_token(cookie_header)
    if not session_jwt:
        _render_auth_wall("Please sign in to access Peregrine.")
        st.stop()

    try:
        user_id = validate_session_jwt(session_jwt)
    except Exception:
        _render_auth_wall("Your session has expired. Please sign in again.")
        st.stop()

    user_path = _user_data_path(user_id, app)
    user_path.mkdir(parents=True, exist_ok=True)
    config_path = user_path / "config"
    config_path.mkdir(exist_ok=True)
    (user_path / "data").mkdir(exist_ok=True)

    # Bootstrap config files that the UI requires to exist — never overwrite
    _kw = config_path / "resume_keywords.yaml"
    if not _kw.exists():
        _kw.write_text("skills: []\ndomains: []\nkeywords: []\n")

    st.session_state["user_id"] = user_id
    st.session_state["db_path"] = user_path / "staging.db"
    st.session_state["db_key"] = derive_db_key(user_id)
    _ensure_provisioned(user_id, app)
    st.session_state["cloud_tier"] = _fetch_cloud_tier(user_id, app)


def get_db_path() -> Path:
    """
    Return the active db_path for this session.
    Cloud: user-scoped path from session_state.
    Local: DEFAULT_DB (from STAGING_DB env var or repo default).
    """
    return st.session_state.get("db_path", DEFAULT_DB)


def get_config_dir() -> Path:
    """
    Return the config directory for this session.
    Cloud: per-user path (<data_root>/<user_id>/peregrine/config/) so each
           user's YAML files (user.yaml, plain_text_resume.yaml, etc.) are
           isolated and never shared across tenants.
    Local: repo-level config/ directory.
    """
    if CLOUD_MODE and st.session_state.get("db_path"):
        return Path(st.session_state["db_path"]).parent / "config"
    return Path(__file__).parent.parent / "config"


def get_cloud_tier() -> str:
    """
    Return the current user's cloud tier.
    Cloud mode: resolved from Heimdall at session start (cached 5 min).
    Local mode: always returns "local" so pages can distinguish self-hosted from cloud.
    """
    if not CLOUD_MODE:
        return "local"
    return st.session_state.get("cloud_tier", "free")
