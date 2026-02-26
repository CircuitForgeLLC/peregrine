"""
CircuitForge license client for Peregrine.

Activates against the license server, caches a signed JWT locally,
and verifies tier offline using the embedded RS256 public key.

All functions accept override paths for testing; production code uses
the module-level defaults.
"""
from __future__ import annotations

import hashlib
import json
import socket
import threading
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import jwt as pyjwt

_HERE = Path(__file__).parent
_DEFAULT_LICENSE_PATH = _HERE.parent / "config" / "license.json"
_DEFAULT_PUBLIC_KEY_PATH = _HERE / "license_public_key.pem"
_LICENSE_SERVER = "https://license.circuitforge.tech"
_PRODUCT = "peregrine"
_REFRESH_THRESHOLD_DAYS = 5
_GRACE_PERIOD_DAYS = 7


# ── Machine fingerprint ────────────────────────────────────────────────────────

def _machine_id() -> str:
    raw = f"{socket.gethostname()}-{uuid.getnode()}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


# ── License file helpers ───────────────────────────────────────────────────────

def _read_license(license_path: Path) -> dict | None:
    try:
        return json.loads(license_path.read_text())
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None


def _write_license(data: dict, license_path: Path) -> None:
    license_path.parent.mkdir(parents=True, exist_ok=True)
    license_path.write_text(json.dumps(data, indent=2))


# ── Core verify ───────────────────────────────────────────────────────────────

def verify_local(
    license_path: Path = _DEFAULT_LICENSE_PATH,
    public_key_path: Path = _DEFAULT_PUBLIC_KEY_PATH,
) -> dict | None:
    """Verify the cached JWT offline. Returns payload dict or None (= free tier).

    Returned dict has keys: tier, in_grace (bool), sub, product, notice (optional).
    """
    stored = _read_license(license_path)
    if not stored or not stored.get("jwt"):
        return None

    if not public_key_path.exists():
        return None

    public_key = public_key_path.read_bytes()

    try:
        payload = pyjwt.decode(stored["jwt"], public_key, algorithms=["RS256"])
        if payload.get("product") != _PRODUCT:
            return None
        return {**payload, "in_grace": False}

    except pyjwt.exceptions.ExpiredSignatureError:
        # JWT expired — check local grace period before requiring a refresh
        grace_until_str = stored.get("grace_until")
        if not grace_until_str:
            return None
        try:
            grace_until = datetime.fromisoformat(grace_until_str)
            if grace_until.tzinfo is None:
                grace_until = grace_until.replace(tzinfo=timezone.utc)
        except ValueError:
            return None
        if datetime.now(timezone.utc) > grace_until:
            return None
        # Decode without expiry check to recover the payload
        try:
            payload = pyjwt.decode(
                stored["jwt"], public_key,
                algorithms=["RS256"],
                options={"verify_exp": False},
            )
            if payload.get("product") != _PRODUCT:
                return None
            return {**payload, "in_grace": True}
        except pyjwt.exceptions.PyJWTError:
            return None

    except pyjwt.exceptions.PyJWTError:
        return None


def effective_tier(
    license_path: Path = _DEFAULT_LICENSE_PATH,
    public_key_path: Path = _DEFAULT_PUBLIC_KEY_PATH,
) -> str:
    """Return the effective tier string. Falls back to 'free' on any problem."""
    result = verify_local(license_path=license_path, public_key_path=public_key_path)
    if result is None:
        return "free"
    return result.get("tier", "free")


# ── Network operations (all fire-and-forget or explicit) ──────────────────────

def activate(
    key: str,
    license_path: Path = _DEFAULT_LICENSE_PATH,
    public_key_path: Path = _DEFAULT_PUBLIC_KEY_PATH,
    app_version: str | None = None,
) -> dict:
    """Activate a license key. Returns response dict. Raises on failure."""
    import httpx
    mid = _machine_id()
    resp = httpx.post(
        f"{_LICENSE_SERVER}/activate",
        json={
            "key": key,
            "machine_id": mid,
            "product": _PRODUCT,
            "app_version": app_version,
            "platform": _detect_platform(),
        },
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()
    stored = {
        "jwt": data["jwt"],
        "key_display": key,
        "tier": data["tier"],
        "valid_until": data.get("valid_until"),
        "machine_id": mid,
        "last_refresh": datetime.now(timezone.utc).isoformat(),
        "grace_until": None,
    }
    _write_license(stored, license_path)
    return data


def deactivate(
    license_path: Path = _DEFAULT_LICENSE_PATH,
) -> None:
    """Deactivate this machine. Deletes license.json."""
    import httpx
    stored = _read_license(license_path)
    if not stored:
        return
    try:
        httpx.post(
            f"{_LICENSE_SERVER}/deactivate",
            json={"jwt": stored["jwt"], "machine_id": stored.get("machine_id", _machine_id())},
            timeout=10,
        )
    except Exception:
        pass  # best-effort
    license_path.unlink(missing_ok=True)


def refresh_if_needed(
    license_path: Path = _DEFAULT_LICENSE_PATH,
    public_key_path: Path = _DEFAULT_PUBLIC_KEY_PATH,
) -> None:
    """Silently refresh JWT if it expires within threshold. No-op on network failure."""
    stored = _read_license(license_path)
    if not stored or not stored.get("jwt"):
        return
    try:
        payload = pyjwt.decode(
            stored["jwt"], public_key_path.read_bytes(), algorithms=["RS256"]
        )
        exp = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
        if exp - datetime.now(timezone.utc) > timedelta(days=_REFRESH_THRESHOLD_DAYS):
            return
    except pyjwt.exceptions.ExpiredSignatureError:
        # Already expired — try to refresh anyway, set grace if unreachable
        pass
    except Exception:
        return

    try:
        import httpx
        resp = httpx.post(
            f"{_LICENSE_SERVER}/refresh",
            json={"jwt": stored["jwt"], "machine_id": stored.get("machine_id", _machine_id())},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        stored["jwt"] = data["jwt"]
        stored["tier"] = data["tier"]
        stored["last_refresh"] = datetime.now(timezone.utc).isoformat()
        stored["grace_until"] = None
        _write_license(stored, license_path)
    except Exception:
        # Server unreachable — set grace period if not already set
        if not stored.get("grace_until"):
            grace = datetime.now(timezone.utc) + timedelta(days=_GRACE_PERIOD_DAYS)
            stored["grace_until"] = grace.isoformat()
            _write_license(stored, license_path)


def report_usage(
    event_type: str,
    metadata: dict | None = None,
    license_path: Path = _DEFAULT_LICENSE_PATH,
) -> None:
    """Fire-and-forget usage telemetry. Never blocks, never raises."""
    stored = _read_license(license_path)
    if not stored or not stored.get("jwt"):
        return

    def _send():
        try:
            import httpx
            httpx.post(
                f"{_LICENSE_SERVER}/usage",
                json={"event_type": event_type, "product": _PRODUCT, "metadata": metadata or {}},
                headers={"Authorization": f"Bearer {stored['jwt']}"},
                timeout=5,
            )
        except Exception:
            pass

    threading.Thread(target=_send, daemon=True).start()


def report_flag(
    flag_type: str,
    details: dict | None = None,
    license_path: Path = _DEFAULT_LICENSE_PATH,
) -> None:
    """Fire-and-forget violation report. Never blocks, never raises."""
    stored = _read_license(license_path)
    if not stored or not stored.get("jwt"):
        return

    def _send():
        try:
            import httpx
            httpx.post(
                f"{_LICENSE_SERVER}/flag",
                json={"flag_type": flag_type, "product": _PRODUCT, "details": details or {}},
                headers={"Authorization": f"Bearer {stored['jwt']}"},
                timeout=5,
            )
        except Exception:
            pass

    threading.Thread(target=_send, daemon=True).start()


def _detect_platform() -> str:
    import sys
    if sys.platform.startswith("linux"):
        return "linux"
    if sys.platform == "darwin":
        return "macos"
    if sys.platform == "win32":
        return "windows"
    return "unknown"
