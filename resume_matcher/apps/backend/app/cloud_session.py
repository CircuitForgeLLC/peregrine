"""
Peregrine cloud session — thin wrapper around cf_core.cloud_session.

Sets request-scoped ContextVars with the authenticated user_id, tier, and
custom writing model so that _allocate_orch_async in llm.py can forward them
to cf-orch without any service function signature changes.

Usage — add to main.py once:

    from app.cloud_session import session_middleware_dep
    app = FastAPI(..., dependencies=[Depends(session_middleware_dep)])

Writing model is resolved from Heimdall's resolve response (user_preferences
JSON column, projected as custom_writing_model in the response).  Assign models
via the admin UI at /account/admin/model-assignments.
"""
from __future__ import annotations

import logging

from fastapi import Request, Response

from circuitforge_core.cloud_session import CloudSessionFactory, CloudUser, detect_byok

log = logging.getLogger(__name__)

__all__ = ["CloudUser", "get_session", "require_tier", "session_middleware_dep"]

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
    set_request_writing_model(session.meta.get("custom_writing_model") or None)
