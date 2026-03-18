"""Cloud mode config — port 8505, CLOUD_MODE=true, Directus JWT auth."""
from __future__ import annotations
import os
import time
import logging
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv

from tests.e2e.models import ModeConfig

load_dotenv(".env.e2e")

log = logging.getLogger(__name__)

_BASE_SETTINGS_TABS = [
    "👤 My Profile", "📝 Resume Profile", "🔎 Search",
    "⚙️ System", "🎯 Fine-Tune", "🔑 License", "💾 Data", "🔒 Privacy",
]

_token_cache: dict[str, Any] = {"token": None, "expires_at": 0.0}


def _get_jwt() -> str:
    """
    Acquire a Directus JWT for the e2e test user.
    Strategy A: user/pass login (preferred).
    Strategy B: persistent JWT from E2E_DIRECTUS_JWT env var.
    Caches the token and refreshes 100s before expiry.
    """
    if not os.environ.get("E2E_DIRECTUS_EMAIL"):
        jwt = os.environ.get("E2E_DIRECTUS_JWT", "")
        if not jwt:
            raise RuntimeError(
                "Cloud mode requires E2E_DIRECTUS_EMAIL+PASSWORD or E2E_DIRECTUS_JWT in .env.e2e"
            )
        return jwt

    if _token_cache["token"] and time.time() < _token_cache["expires_at"] - 100:
        return _token_cache["token"]

    directus_url = os.environ.get("E2E_DIRECTUS_URL", "http://172.31.0.2:8055")
    resp = requests.post(
        f"{directus_url}/auth/login",
        json={
            "email": os.environ["E2E_DIRECTUS_EMAIL"],
            "password": os.environ["E2E_DIRECTUS_PASSWORD"],
        },
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()["data"]
    token = data["access_token"]
    expires_in_ms = data.get("expires", 900_000)

    _token_cache["token"] = token
    _token_cache["expires_at"] = time.time() + (expires_in_ms / 1000)
    log.info("Acquired Directus JWT (expires in %ds)", expires_in_ms // 1000)
    return token


def _cloud_auth_setup(context: Any) -> None:
    """Placeholder — actual JWT injection done via context.route() in conftest."""
    pass  # Route-based injection set up in conftest.py mode_contexts fixture


CLOUD = ModeConfig(
    name="cloud",
    base_url="http://localhost:8505/peregrine",
    auth_setup=_cloud_auth_setup,
    expected_failures=[],
    results_dir=Path("tests/e2e/results/cloud"),
    settings_tabs=_BASE_SETTINGS_TABS,
)
