"""
Peregrine cloud session — thin wrapper around cf_core.cloud_session.

Sets a request-scoped ContextVar with the authenticated user_id so that
_allocate_orch_async in llm.py can pass it to cf-orch without any service
function signature changes.

Usage — add to main.py once:

    from app.cloud_session import session_middleware_dep
    app = FastAPI(..., dependencies=[Depends(session_middleware_dep)])

From that point, any route (and every service/llm function it calls)
has access to the current user_id via llm.get_request_user_id().
"""
from __future__ import annotations

import os
from pathlib import Path

from fastapi import Depends, Request, Response

from circuitforge_core.cloud_session import CloudSessionFactory, CloudUser

__all__ = ["CloudUser", "get_session", "require_tier", "session_middleware_dep"]

_BYOK_CONFIG = Path.home() / ".config" / "circuitforge" / "llm.yaml"


def _detect_byok() -> bool:
    try:
        import yaml
        with open(_BYOK_CONFIG) as f:
            cfg = yaml.safe_load(f) or {}
        return any(
            b.get("enabled", True) and b.get("type") != "vision_service"
            for b in cfg.get("backends", {}).values()
        )
    except Exception:
        return False


_factory = CloudSessionFactory(
    product="peregrine",
    byok_detector=_detect_byok,
)

get_session = _factory.dependency()
require_tier = _factory.require_tier


def session_middleware_dep(request: Request, response: Response) -> None:
    """Global FastAPI dependency — resolves the session and sets the request-scoped
    user_id ContextVar so llm._allocate_orch_async can forward it to cf-orch.

    Add as a global dependency in main.py:
        app = FastAPI(..., dependencies=[Depends(session_middleware_dep)])
    """
    from app.llm import set_request_user_id

    session = _factory.resolve(request, response)
    user_id = session.user_id

    # Only forward real cloud UUIDs — local/dev/anon sessions use the shared catalog
    if user_id in (None, "local", "local-dev") or (user_id or "").startswith("anon-"):
        user_id = None

    set_request_user_id(user_id)
