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
import os
import re
import hmac
import hashlib
from pathlib import Path

import streamlit as st

from scripts.db import DEFAULT_DB

CLOUD_MODE: bool = os.environ.get("CLOUD_MODE", "").lower() in ("1", "true", "yes")


def _extract_session_token(cookie_header: str) -> str:
    """Extract cf_session value from a Cookie header string."""
    m = re.search(r'(?:^|;)\s*cf_session=([^;]+)', cookie_header)
    return m.group(1).strip() if m else ""
CLOUD_DATA_ROOT: Path = Path(os.environ.get("CLOUD_DATA_ROOT", "/devl/menagerie-data"))
DIRECTUS_JWT_SECRET: str = os.environ.get("DIRECTUS_JWT_SECRET", "")
SERVER_SECRET: str = os.environ.get("CF_SERVER_SECRET", "")


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


def resolve_session(app: str = "peregrine") -> None:
    """
    Call at the top of each Streamlit page.
    In local mode: no-op.
    In cloud mode: reads X-CF-Session header, validates JWT, creates user
    data directory on first visit, and sets st.session_state keys:
      - user_id: str
      - db_path: Path
      - db_key: str  (SQLCipher key for this user)
    Idempotent — skips if user_id already in session_state.
    """
    if not CLOUD_MODE:
        return
    if st.session_state.get("user_id"):
        return

    cookie_header = st.context.headers.get("x-cf-session", "")
    session_jwt = _extract_session_token(cookie_header)
    if not session_jwt:
        st.error("Session token missing. Please log in at circuitforge.tech.")
        st.stop()

    try:
        user_id = validate_session_jwt(session_jwt)
    except Exception as exc:
        st.error(f"Invalid session — please log in again. ({exc})")
        st.stop()

    user_path = _user_data_path(user_id, app)
    user_path.mkdir(parents=True, exist_ok=True)
    (user_path / "config").mkdir(exist_ok=True)
    (user_path / "data").mkdir(exist_ok=True)

    st.session_state["user_id"] = user_id
    st.session_state["db_path"] = user_path / "staging.db"
    st.session_state["db_key"] = derive_db_key(user_id)


def get_db_path() -> Path:
    """
    Return the active db_path for this session.
    Cloud: user-scoped path from session_state.
    Local: DEFAULT_DB (from STAGING_DB env var or repo default).
    """
    return st.session_state.get("db_path", DEFAULT_DB)
