"""Per-user rate limiting for Peregrine LLM generation endpoints."""
from pathlib import Path

from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from starlette.requests import Request
from starlette.responses import JSONResponse


def _rate_key(request: Request) -> str:
    """Cloud mode: user_id from DB path. Local mode: client IP. Demo: unique key (no rate limit)."""
    from dev_api import IS_DEMO, _CLOUD_MODE, _request_db  # lazy import avoids circular
    if IS_DEMO:
        return f"demo-{id(request)}"  # unique per request — effectively no rate limiting
    db_path = _request_db.get()
    if _CLOUD_MODE and db_path:
        return Path(db_path).parts[-3]  # user_id segment
    return get_remote_address(request)


limiter = Limiter(key_func=_rate_key)


def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    """Return 429 with Retry-After header."""
    retry_after = getattr(exc, "retry_after", 60)
    return JSONResponse(
        status_code=429,
        content={"error": "rate_limit_exceeded", "retry_after": retry_after},
        headers={"Retry-After": str(retry_after)},
    )
