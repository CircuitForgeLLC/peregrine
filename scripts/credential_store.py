"""
Credential store abstraction for Peregrine.

Backends (set via CREDENTIAL_BACKEND env var):
  auto    → try keyring, fall back to file (default)
  keyring → python-keyring (OS Keychain / SecretService / libsecret)
  file    → Fernet-encrypted JSON in config/credentials/ (key at config/.credential_key)

Env var references:
  Any stored value matching ${VAR_NAME} is resolved from os.environ at read time.
  Users can store "${IMAP_PASSWORD}" as the credential value; it is never treated
  as the actual secret — only the env var it points to is used.
"""

import os
import re
import json
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_ENV_REF = re.compile(r'^\$\{([A-Z_][A-Z0-9_]*)\}$')

CRED_DIR = Path("config/credentials")
KEY_PATH = Path("config/.credential_key")


def _resolve_env_ref(value: str) -> Optional[str]:
    """If value is ${VAR_NAME}, return os.environ[VAR_NAME]; otherwise return None."""
    m = _ENV_REF.match(value)
    if m:
        resolved = os.environ.get(m.group(1))
        if resolved is None:
            logger.warning("Credential reference %s is set but env var is not defined", value)
        return resolved
    return None


def _get_backend() -> str:
    backend = os.environ.get("CREDENTIAL_BACKEND", "auto").lower()
    if backend != "auto":
        return backend
    # Auto: try keyring, fall back to file
    try:
        import keyring
        kr = keyring.get_keyring()
        # Reject the null/fail keyring — it can't actually store anything
        if "fail" in type(kr).__name__.lower() or "null" in type(kr).__name__.lower():
            raise RuntimeError("No usable keyring backend found")
        return "keyring"
    except Exception:
        return "file"


def _get_fernet():
    """Return a Fernet instance, auto-generating the key on first use."""
    try:
        from cryptography.fernet import Fernet
    except ImportError:
        return None

    if KEY_PATH.exists():
        key = KEY_PATH.read_bytes().strip()
    else:
        key = Fernet.generate_key()
        KEY_PATH.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(str(KEY_PATH), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "wb") as f:
            f.write(key)
        logger.info("Generated new credential encryption key at %s", KEY_PATH)

    return Fernet(key)


def _file_read(service: str) -> dict:
    """Read the credentials file for a service, decrypting if possible."""
    cred_file = CRED_DIR / f"{service}.json"
    if not cred_file.exists():
        return {}
    raw = cred_file.read_bytes()
    fernet = _get_fernet()
    if fernet:
        try:
            return json.loads(fernet.decrypt(raw))
        except Exception:
            # May be an older plaintext file — try reading as text
            try:
                return json.loads(raw.decode())
            except Exception:
                logger.error("Failed to read credentials for service %s", service)
                return {}
    else:
        try:
            return json.loads(raw.decode())
        except Exception:
            return {}


def _file_write(service: str, data: dict) -> None:
    """Write the credentials file for a service, encrypting if possible."""
    CRED_DIR.mkdir(parents=True, exist_ok=True)
    cred_file = CRED_DIR / f"{service}.json"
    fernet = _get_fernet()
    if fernet:
        content = fernet.encrypt(json.dumps(data).encode())
        fd = os.open(str(cred_file), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "wb") as f:
            f.write(content)
    else:
        logger.warning(
            "cryptography package not installed — storing credentials as plaintext with chmod 600. "
            "Install with: pip install cryptography"
        )
        content = json.dumps(data).encode()
        fd = os.open(str(cred_file), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "wb") as f:
            f.write(content)


def get_credential(service: str, key: str) -> Optional[str]:
    """
    Retrieve a credential. If the stored value is an env var reference (${VAR}),
    resolves it from os.environ at call time.
    """
    backend = _get_backend()
    raw: Optional[str] = None

    if backend == "keyring":
        try:
            import keyring
            raw = keyring.get_password(service, key)
        except Exception as e:
            logger.error("keyring get failed for %s/%s: %s", service, key, e)
    else:  # file
        data = _file_read(service)
        raw = data.get(key)

    if raw is None:
        return None

    # Resolve env var references transparently
    resolved = _resolve_env_ref(raw)
    if resolved is not None:
        return resolved
    if _ENV_REF.match(raw):
        return None  # reference defined but env var not set

    return raw


def set_credential(service: str, key: str, value: str) -> None:
    """
    Store a credential. Value may be a literal secret or a ${VAR_NAME} reference.
    Env var references are stored as-is and resolved at get time.
    """
    if not value:
        return

    backend = _get_backend()

    if backend == "keyring":
        try:
            import keyring
            keyring.set_password(service, key, value)
            return
        except Exception as e:
            logger.error("keyring set failed for %s/%s: %s — falling back to file", service, key, e)
            backend = "file"

    # file backend
    data = _file_read(service)
    data[key] = value
    _file_write(service, data)


def delete_credential(service: str, key: str) -> None:
    """Remove a stored credential."""
    backend = _get_backend()

    if backend == "keyring":
        try:
            import keyring
            keyring.delete_password(service, key)
            return
        except Exception:
            backend = "file"

    data = _file_read(service)
    data.pop(key, None)
    if data:
        _file_write(service, data)
    else:
        cred_file = CRED_DIR / f"{service}.json"
        if cred_file.exists():
            cred_file.unlink()
