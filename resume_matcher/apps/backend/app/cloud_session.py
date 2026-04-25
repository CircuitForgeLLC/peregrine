"""
Peregrine cloud session — thin wrapper around cf_core.cloud_session.

Sets request-scoped ContextVars with the authenticated user_id, tier, and
custom writing model so that _allocate_orch_async in llm.py can forward them
to cf-orch without any service function signature changes.

Usage — add to main.py once:

    from app.cloud_session import session_middleware_dep
    app = FastAPI(..., dependencies=[Depends(session_middleware_dep)])

From that point, any route (and every service/llm function it calls)
has access to the current user context via llm.get_request_*() helpers.

Writing model resolution order (first match wins):
  1. USER_WRITING_MODELS env var  — JSON dict mapping Directus UUID → model name
     e.g. USER_WRITING_MODELS={"5b99ca9f-...": "meghan-letter-writer:latest"}
     Use this for Monday; no Heimdall changes required.
  2. session.meta["custom_writing_model"]  — returned by Heimdall resolve endpoint
     once Heimdall is updated to expose user_preferences fields.
"""
from __future__ import annotations

import json
import logging
import os

from fastapi import Depends, Request, Response

from circuitforge_core.cloud_session import CloudSessionFactory, CloudUser, detect_byok

log = logging.getLogger(__name__)

__all__ = ["CloudUser", "get_session", "require_tier", "session_middleware_dep"]

# JSON dict mapping Directus user UUID → custom writing model name.
# Used until Heimdall's resolve endpoint exposes user_preferences.
def _load_user_writing_models() -> dict[str, str]:
    raw = os.environ.get("USER_WRITING_MODELS", "").strip()
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        log.warning("USER_WRITING_MODELS is not valid JSON — ignoring")
        return {}

_USER_WRITING_MODELS: dict[str, str] = _load_user_writing_models()


_factory = CloudSessionFactory(
    product="peregrine",
    byok_detector=detect_byok,
)

get_session = _factory.dependency()
require_tier = _factory.require_tier


def session_middleware_dep(request: Request, response: Response) -> None:
    """Global FastAPI dependency — resolves the session and sets request-scoped
    ContextVars so llm._allocate_orch_async can forward them to cf-orch.

    Sets:
      - user_id: real cloud UUID, or None for local/anon sessions
      - tier: the resolved tier string (free/paid/premium/ultra/local)
      - writing_model: custom fine-tuned model from Heimdall meta, or None

    Add as a global dependency in main.py:
        app = FastAPI(..., dependencies=[Depends(session_middleware_dep)])
    """
    from app.llm import set_request_tier, set_request_user_id, set_request_writing_model

    session = _factory.resolve(request, response)
    user_id = session.user_id

    # Only forward real cloud UUIDs — local/dev/anon sessions use the shared catalog
    if user_id in (None, "local", "local-dev") or (user_id or "").startswith("anon-"):
        user_id = None

    set_request_user_id(user_id)
    set_request_tier(session.tier)
    # Resolution order: env-var map (Monday path) → Heimdall meta (future path)
    writing_model = (
        _USER_WRITING_MODELS.get(session.user_id)
        or session.meta.get("custom_writing_model")
    )
    set_request_writing_model(writing_model)
