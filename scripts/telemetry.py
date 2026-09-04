# peregrine/app/telemetry.py
"""
Usage event telemetry for cloud-hosted Peregrine.

In local-first mode (CLOUD_MODE unset/false), all functions are no-ops —
no network calls, no DB writes, no imports of psycopg2.

In cloud mode, events are written to the platform Postgres DB ONLY after
confirming the user's telemetry consent.

THE HARD RULE: if telemetry_consent.all_disabled is True for a user,
nothing is written, no exceptions. This function is the ONLY path to
usage_events — no feature may write there directly.
"""
import os
import json
from typing import Any

CLOUD_MODE: bool = os.environ.get("CLOUD_MODE", "").lower() in ("1", "true", "yes")
PLATFORM_DB_URL: str = os.environ.get("PLATFORM_DB_URL", "")

_platform_conn = None


def get_platform_conn():
    """Lazy psycopg2 connection to the platform Postgres DB. Reconnects if closed."""
    global _platform_conn
    if _platform_conn is None or _platform_conn.closed:
        import psycopg2
        _platform_conn = psycopg2.connect(PLATFORM_DB_URL)
    return _platform_conn


def get_consent(user_id: str) -> dict:
    """
    Fetch telemetry consent for the user.
    Returns safe defaults if record doesn't exist yet:
      - usage_events_enabled: True  (new cloud users start opted-in, per onboarding disclosure)
      - all_disabled: False
    """
    conn = get_platform_conn()
    with conn.cursor() as cur:
        cur.execute(
            "SELECT all_disabled, usage_events_enabled "
            "FROM telemetry_consent WHERE user_id = %s",
            (user_id,)
        )
        row = cur.fetchone()
    if row is None:
        return {"all_disabled": False, "usage_events_enabled": True}
    return {"all_disabled": row[0], "usage_events_enabled": row[1]}


def log_usage_event(
    user_id: str,
    app: str,
    event_type: str,
    metadata: dict[str, Any] | None = None,
) -> None:
    """
    Write a usage event to the platform DB if consent allows.

    Silent no-op in local mode. Silent no-op if telemetry is disabled.
    Swallows all exceptions — telemetry must never crash the app.

    Args:
        user_id:    Directus user UUID (from st.session_state["user_id"])
        app:        App slug ('peregrine', 'falcon', etc.)
        event_type: Snake_case event label ('cover_letter_generated', 'job_applied', etc.)
        metadata:   Optional JSON-serialisable dict — NO PII
    """
    if not CLOUD_MODE:
        return

    try:
        consent = get_consent(user_id)
        if consent.get("all_disabled") or not consent.get("usage_events_enabled", True):
            return

        conn = get_platform_conn()
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO usage_events (user_id, app, event_type, metadata) "
                "VALUES (%s, %s, %s, %s)",
                (user_id, app, event_type, json.dumps(metadata) if metadata else None),
            )
        conn.commit()
    except Exception:
        # Telemetry must never crash the app
        pass


def update_consent(user_id: str, **fields) -> None:
    """
    UPSERT telemetry consent for a user.

    Accepted keyword args (all optional, any subset may be provided):
        all_disabled: bool
        usage_events_enabled: bool
        content_sharing_enabled: bool
        support_access_enabled: bool

    Safe to call in cloud mode only — no-op in local mode.
    Swallows all exceptions so the Settings UI is never broken by a DB hiccup.
    """
    if not CLOUD_MODE:
        return
    allowed = {"all_disabled", "usage_events_enabled", "content_sharing_enabled", "support_access_enabled"}
    cols = {k: v for k, v in fields.items() if k in allowed}
    if not cols:
        return
    try:
        conn = get_platform_conn()
        col_names = ", ".join(cols)
        placeholders = ", ".join(["%s"] * len(cols))
        set_clause = ", ".join(f"{k} = EXCLUDED.{k}" for k in cols)
        col_vals = list(cols.values())
        with conn.cursor() as cur:
            cur.execute(
                f"INSERT INTO telemetry_consent (user_id, {col_names}) "
                f"VALUES (%s, {placeholders}) "
                f"ON CONFLICT (user_id) DO UPDATE SET {set_clause}, updated_at = NOW()",
                [user_id] + col_vals,
            )
        conn.commit()
    except Exception:
        pass
