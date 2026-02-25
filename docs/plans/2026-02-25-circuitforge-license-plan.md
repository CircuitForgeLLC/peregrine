# CircuitForge License Server — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a self-hosted RS256 JWT licensing server for Circuit Forge LLC and wire Peregrine to validate licenses offline.

**Architecture:** Two work streams — (A) a new FastAPI + SQLite service (`circuitforge-license`) deployed on Heimdall via Docker + Caddy, and (B) a `scripts/license.py` client in Peregrine that activates against the server and verifies JWTs offline using an embedded public key. The server issues 30-day signed tokens; the client verifies signatures locally on every tier check with zero network calls during normal operation.

**Tech Stack:** FastAPI, PyJWT[crypto], Pydantic v2, SQLite, pytest, httpx (test client), cryptography (RSA key gen in tests), Docker Compose V2, Caddy.

**Repos:**
- License server: `/Library/Development/devl/circuitforge-license/` → `git.opensourcesolarpunk.com/pyr0ball/circuitforge-license`
- Peregrine client: `/Library/Development/devl/peregrine/`
- Run tests: `/devl/miniconda3/envs/job-seeker/bin/pytest tests/ -v`
- Python env for local dev/test: `conda run -n job-seeker`

---

## PART A — License Server (new repo)

---

### Task 1: Repo scaffold + DB schema

**Files:**
- Create: `/Library/Development/devl/circuitforge-license/` (new directory)
- Create: `requirements.txt`
- Create: `app/__init__.py`
- Create: `app/db.py`
- Create: `tests/__init__.py`
- Create: `tests/test_db.py`
- Create: `.gitignore`

**Step 1: Create the directory and git repo**

```bash
mkdir -p /Library/Development/devl/circuitforge-license
cd /Library/Development/devl/circuitforge-license
git init
```

**Step 2: Create `.gitignore`**

```
# Secrets — never commit these
.env
keys/private.pem
data/

# Python
__pycache__/
*.pyc
.pytest_cache/
*.egg-info/
dist/
.coverage
htmlcov/
```

**Step 3: Create `requirements.txt`**

```
fastapi>=0.110
uvicorn[standard]>=0.27
pyjwt[crypto]>=2.8
pydantic>=2.0
python-dotenv>=1.0
pytest>=9.0
pytest-cov
httpx
cryptography>=42
```

**Step 4: Create `app/__init__.py`** (empty file)

**Step 5: Write the failing test**

```python
# tests/test_db.py
import pytest
from pathlib import Path
from app.db import init_db, get_db


def test_init_db_creates_all_tables(tmp_path):
    db = tmp_path / "test.db"
    init_db(db)
    with get_db(db) as conn:
        tables = {row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
    expected = {"license_keys", "activations", "usage_events", "flags", "audit_log"}
    assert expected.issubset(tables)


def test_init_db_idempotent(tmp_path):
    db = tmp_path / "test.db"
    init_db(db)
    init_db(db)  # second call must not raise or corrupt
    with get_db(db) as conn:
        count = conn.execute("SELECT COUNT(*) FROM license_keys").fetchone()[0]
    assert count == 0
```

**Step 6: Run test to verify it fails**

```bash
cd /Library/Development/devl/circuitforge-license
conda run -n job-seeker python -m pytest tests/test_db.py -v
```
Expected: `FAILED` — `ModuleNotFoundError: No module named 'app'`

**Step 7: Write `app/db.py`**

```python
# app/db.py
import sqlite3
from contextlib import contextmanager
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "license.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS license_keys (
    id             TEXT PRIMARY KEY,
    key_display    TEXT UNIQUE NOT NULL,
    product        TEXT NOT NULL,
    tier           TEXT NOT NULL,
    seats          INTEGER DEFAULT 1,
    valid_until    TEXT,
    revoked        INTEGER DEFAULT 0,
    customer_email TEXT,
    source         TEXT DEFAULT 'manual',
    trial          INTEGER DEFAULT 0,
    notes          TEXT,
    created_at     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS activations (
    id             TEXT PRIMARY KEY,
    key_id         TEXT NOT NULL REFERENCES license_keys(id),
    machine_id     TEXT NOT NULL,
    app_version    TEXT,
    platform       TEXT,
    activated_at   TEXT NOT NULL,
    last_refresh   TEXT NOT NULL,
    deactivated_at TEXT
);

CREATE TABLE IF NOT EXISTS usage_events (
    id          TEXT PRIMARY KEY,
    key_id      TEXT NOT NULL REFERENCES license_keys(id),
    machine_id  TEXT NOT NULL,
    product     TEXT NOT NULL,
    event_type  TEXT NOT NULL,
    metadata    TEXT,
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS flags (
    id           TEXT PRIMARY KEY,
    key_id       TEXT NOT NULL REFERENCES license_keys(id),
    machine_id   TEXT,
    product      TEXT NOT NULL,
    flag_type    TEXT NOT NULL,
    details      TEXT,
    status       TEXT DEFAULT 'open',
    created_at   TEXT NOT NULL,
    reviewed_at  TEXT,
    action_taken TEXT
);

CREATE TABLE IF NOT EXISTS audit_log (
    id          TEXT PRIMARY KEY,
    entity_type TEXT NOT NULL,
    entity_id   TEXT NOT NULL,
    action      TEXT NOT NULL,
    actor       TEXT,
    details     TEXT,
    created_at  TEXT NOT NULL
);
"""


@contextmanager
def get_db(db_path: Path = DB_PATH):
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db(db_path: Path = DB_PATH) -> None:
    with get_db(db_path) as conn:
        conn.executescript(_SCHEMA)
```

**Step 8: Run test to verify it passes**

```bash
conda run -n job-seeker python -m pytest tests/test_db.py -v
```
Expected: `2 passed`

**Step 9: Commit**

```bash
cd /Library/Development/devl/circuitforge-license
git add -A
git commit -m "feat: repo scaffold, DB schema, init_db"
```

---

### Task 2: Crypto module + test keypair fixture

**Files:**
- Create: `app/crypto.py`
- Create: `tests/conftest.py`
- Create: `tests/test_crypto.py`
- Create: `keys/` (directory; `public.pem` committed later)

**Step 1: Write the failing tests**

```python
# tests/test_crypto.py
import pytest
import jwt as pyjwt
from app.crypto import sign_jwt, verify_jwt


def test_sign_and_verify_roundtrip(test_keypair):
    private_pem, public_pem = test_keypair
    payload = {"sub": "CFG-PRNG-TEST", "product": "peregrine", "tier": "paid"}
    token = sign_jwt(payload, private_pem=private_pem, expiry_days=30)
    decoded = verify_jwt(token, public_pem=public_pem)
    assert decoded["sub"] == "CFG-PRNG-TEST"
    assert decoded["tier"] == "paid"
    assert "exp" in decoded
    assert "iat" in decoded


def test_verify_rejects_wrong_key(test_keypair):
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives import serialization
    private_pem, _ = test_keypair
    other_private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    other_public_pem = other_private.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    token = sign_jwt({"sub": "test"}, private_pem=private_pem, expiry_days=30)
    with pytest.raises(pyjwt.exceptions.InvalidSignatureError):
        verify_jwt(token, public_pem=other_public_pem)


def test_verify_rejects_expired_token(test_keypair):
    private_pem, public_pem = test_keypair
    token = sign_jwt({"sub": "test"}, private_pem=private_pem, expiry_days=-1)
    with pytest.raises(pyjwt.exceptions.ExpiredSignatureError):
        verify_jwt(token, public_pem=public_pem)
```

**Step 2: Write `tests/conftest.py`**

```python
# tests/conftest.py
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization


@pytest.fixture(scope="session")
def test_keypair():
    """Generate a fresh RSA-2048 keypair for the test session."""
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return private_pem, public_pem
```

**Step 3: Run test to verify it fails**

```bash
conda run -n job-seeker python -m pytest tests/test_crypto.py -v
```
Expected: `FAILED` — `ModuleNotFoundError: No module named 'app.crypto'`

**Step 4: Write `app/crypto.py`**

```python
# app/crypto.py
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import jwt as pyjwt


def _load_key(env_var: str, override: bytes | None) -> bytes:
    if override is not None:
        return override
    path = Path(os.environ[env_var])
    return path.read_bytes()


def sign_jwt(
    payload: dict,
    expiry_days: int | None = None,
    private_pem: bytes | None = None,
) -> str:
    if expiry_days is None:
        expiry_days = int(os.environ.get("JWT_EXPIRY_DAYS", "30"))
    now = datetime.now(timezone.utc)
    full_payload = {
        **payload,
        "iat": now,
        "exp": now + timedelta(days=expiry_days),
    }
    key = _load_key("JWT_PRIVATE_KEY_PATH", private_pem)
    return pyjwt.encode(full_payload, key, algorithm="RS256")


def verify_jwt(token: str, public_pem: bytes | None = None) -> dict:
    """Verify RS256 JWT and return decoded payload. Raises on invalid/expired."""
    key = _load_key("JWT_PUBLIC_KEY_PATH", public_pem)
    return pyjwt.decode(token, key, algorithms=["RS256"])
```

**Step 5: Run test to verify it passes**

```bash
conda run -n job-seeker python -m pytest tests/test_crypto.py -v
```
Expected: `3 passed`

**Step 6: Commit**

```bash
git add -A
git commit -m "feat: crypto module — RS256 sign/verify with test keypair fixture"
```

---

### Task 3: Pydantic models

**Files:**
- Create: `app/models.py`
- Create: `tests/test_models.py`

**Step 1: Write the failing test**

```python
# tests/test_models.py
from app.models import (
    ActivateRequest, ActivateResponse,
    RefreshRequest, DeactivateRequest,
    UsageRequest, FlagRequest,
    CreateKeyRequest,
)


def test_activate_request_requires_key_machine_product():
    req = ActivateRequest(key="CFG-PRNG-A1B2-C3D4-E5F6",
                          machine_id="abc123", product="peregrine")
    assert req.key == "CFG-PRNG-A1B2-C3D4-E5F6"
    assert req.app_version is None
    assert req.platform is None


def test_create_key_request_defaults():
    req = CreateKeyRequest(product="peregrine", tier="paid")
    assert req.seats == 1
    assert req.source == "manual"
    assert req.trial is False
    assert req.valid_until is None
```

**Step 2: Run to verify failure**

```bash
conda run -n job-seeker python -m pytest tests/test_models.py -v
```
Expected: `FAILED` — `ModuleNotFoundError: No module named 'app.models'`

**Step 3: Write `app/models.py`**

```python
# app/models.py
from __future__ import annotations
from typing import Optional
from pydantic import BaseModel


class ActivateRequest(BaseModel):
    key: str
    machine_id: str
    product: str
    app_version: Optional[str] = None
    platform: Optional[str] = None


class ActivateResponse(BaseModel):
    jwt: str
    tier: str
    valid_until: Optional[str] = None
    notice: Optional[str] = None


class RefreshRequest(BaseModel):
    jwt: str
    machine_id: str
    app_version: Optional[str] = None
    platform: Optional[str] = None


class DeactivateRequest(BaseModel):
    jwt: str
    machine_id: str


class UsageRequest(BaseModel):
    event_type: str
    product: str
    metadata: Optional[dict] = None


class FlagRequest(BaseModel):
    flag_type: str
    product: str
    details: Optional[dict] = None


class CreateKeyRequest(BaseModel):
    product: str
    tier: str
    seats: int = 1
    valid_until: Optional[str] = None
    customer_email: Optional[str] = None
    source: str = "manual"
    trial: bool = False
    notes: Optional[str] = None


class KeyResponse(BaseModel):
    id: str
    key_display: str
    product: str
    tier: str
    seats: int
    valid_until: Optional[str]
    revoked: bool
    customer_email: Optional[str]
    source: str
    trial: bool
    notes: Optional[str]
    created_at: str
    active_seat_count: int = 0


class FlagUpdateRequest(BaseModel):
    status: str   # reviewed | dismissed | actioned
    action_taken: Optional[str] = None   # none | warned | revoked
```

**Step 4: Run to verify it passes**

```bash
conda run -n job-seeker python -m pytest tests/test_models.py -v
```
Expected: `2 passed`

**Step 5: Commit**

```bash
git add -A
git commit -m "feat: Pydantic v2 request/response models"
```

---

### Task 4: Public routes — activate, refresh, deactivate

**Files:**
- Create: `app/routes/__init__.py` (empty)
- Create: `app/routes/public.py`
- Create: `tests/test_public_routes.py`

**Step 1: Write failing tests**

```python
# tests/test_public_routes.py
import json
import pytest
from fastapi.testclient import TestClient
from app.main import create_app
from app.db import init_db


@pytest.fixture()
def client(tmp_path, test_keypair, monkeypatch):
    db = tmp_path / "test.db"
    private_pem, public_pem = test_keypair
    # Write keys to tmp files
    (tmp_path / "private.pem").write_bytes(private_pem)
    (tmp_path / "public.pem").write_bytes(public_pem)
    monkeypatch.setenv("JWT_PRIVATE_KEY_PATH", str(tmp_path / "private.pem"))
    monkeypatch.setenv("JWT_PUBLIC_KEY_PATH", str(tmp_path / "public.pem"))
    monkeypatch.setenv("JWT_EXPIRY_DAYS", "30")
    monkeypatch.setenv("GRACE_PERIOD_DAYS", "7")
    monkeypatch.setenv("ADMIN_TOKEN", "test-admin-token")
    monkeypatch.setenv("SERVER_NOTICE", "")
    init_db(db)
    app = create_app(db_path=db)
    return TestClient(app)


@pytest.fixture()
def active_key(client):
    """Create a paid key via admin API, return key_display."""
    resp = client.post("/admin/keys", json={
        "product": "peregrine", "tier": "paid", "seats": 2,
        "customer_email": "test@example.com",
    }, headers={"Authorization": "Bearer test-admin-token"})
    assert resp.status_code == 200
    return resp.json()["key_display"]


def test_activate_returns_jwt(client, active_key):
    resp = client.post("/v1/activate", json={
        "key": active_key, "machine_id": "machine-1", "product": "peregrine",
        "platform": "linux", "app_version": "1.0.0",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "jwt" in data
    assert data["tier"] == "paid"


def test_activate_same_machine_twice_ok(client, active_key):
    payload = {"key": active_key, "machine_id": "machine-1", "product": "peregrine"}
    resp1 = client.post("/v1/activate", json=payload)
    resp2 = client.post("/v1/activate", json=payload)
    assert resp1.status_code == 200
    assert resp2.status_code == 200


def test_activate_seat_limit_enforced(client, active_key):
    # seats=2, so machine-1 and machine-2 OK, machine-3 rejected
    for mid in ["machine-1", "machine-2"]:
        r = client.post("/v1/activate", json={
            "key": active_key, "machine_id": mid, "product": "peregrine"
        })
        assert r.status_code == 200
    r3 = client.post("/v1/activate", json={
        "key": active_key, "machine_id": "machine-3", "product": "peregrine"
    })
    assert r3.status_code == 409


def test_activate_invalid_key_rejected(client):
    resp = client.post("/v1/activate", json={
        "key": "CFG-PRNG-FAKE-FAKE-FAKE", "machine_id": "m1", "product": "peregrine"
    })
    assert resp.status_code == 403


def test_activate_wrong_product_rejected(client, active_key):
    resp = client.post("/v1/activate", json={
        "key": active_key, "machine_id": "m1", "product": "falcon"
    })
    assert resp.status_code == 403


def test_refresh_returns_new_jwt(client, active_key):
    act = client.post("/v1/activate", json={
        "key": active_key, "machine_id": "m1", "product": "peregrine"
    })
    old_jwt = act.json()["jwt"]
    resp = client.post("/v1/refresh", json={"jwt": old_jwt, "machine_id": "m1"})
    assert resp.status_code == 200
    assert "jwt" in resp.json()


def test_deactivate_frees_seat(client, active_key):
    # Fill both seats
    for mid in ["machine-1", "machine-2"]:
        client.post("/v1/activate", json={
            "key": active_key, "machine_id": mid, "product": "peregrine"
        })
    # Deactivate machine-1
    act = client.post("/v1/activate", json={
        "key": active_key, "machine_id": "machine-1", "product": "peregrine"
    })
    token = act.json()["jwt"]
    deact = client.post("/v1/deactivate", json={"jwt": token, "machine_id": "machine-1"})
    assert deact.status_code == 200
    # Now machine-3 can activate
    r3 = client.post("/v1/activate", json={
        "key": active_key, "machine_id": "machine-3", "product": "peregrine"
    })
    assert r3.status_code == 200
```

**Step 2: Run to verify failure**

```bash
conda run -n job-seeker python -m pytest tests/test_public_routes.py -v
```
Expected: `FAILED` — `ModuleNotFoundError: No module named 'app.main'`

**Step 3: Write `app/routes/__init__.py`** (empty)

**Step 4: Write `app/routes/public.py`**

```python
# app/routes/public.py
import json
import os
import uuid
from datetime import datetime, timezone

import jwt as pyjwt
from fastapi import APIRouter, Depends, HTTPException

from app.crypto import sign_jwt, verify_jwt
from app.db import get_db
from app.models import (
    ActivateRequest, ActivateResponse,
    RefreshRequest, DeactivateRequest,
    UsageRequest, FlagRequest,
)

router = APIRouter()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _get_key_row(conn, key_display: str, product: str):
    row = conn.execute(
        "SELECT * FROM license_keys WHERE key_display=? AND product=?",
        (key_display, product),
    ).fetchone()
    if not row or row["revoked"]:
        raise HTTPException(status_code=403, detail="Invalid or revoked license key")
    if row["valid_until"] and row["valid_until"] < datetime.now(timezone.utc).date().isoformat():
        raise HTTPException(status_code=403, detail="License key expired")
    return row


def _build_jwt(key_row, machine_id: str) -> str:
    notice = os.environ.get("SERVER_NOTICE", "")
    payload = {
        "sub": key_row["key_display"],
        "product": key_row["product"],
        "tier": key_row["tier"],
        "seats": key_row["seats"],
        "machine": machine_id,
    }
    if notice:
        payload["notice"] = notice
    return sign_jwt(payload)


def _audit(conn, entity_type: str, entity_id: str, action: str, details: dict | None = None):
    conn.execute(
        "INSERT INTO audit_log (id, entity_type, entity_id, action, details, created_at) "
        "VALUES (?,?,?,?,?,?)",
        (str(uuid.uuid4()), entity_type, entity_id, action,
         json.dumps(details) if details else None, _now()),
    )


@router.post("/activate", response_model=ActivateResponse)
def activate(req: ActivateRequest, db_path=Depends(lambda: None)):
    from app.routes._db_dep import get_db_path
    with get_db(get_db_path()) as conn:
        key_row = _get_key_row(conn, req.key, req.product)
        # Count active seats, excluding this machine
        active_seats = conn.execute(
            "SELECT COUNT(*) FROM activations "
            "WHERE key_id=? AND deactivated_at IS NULL AND machine_id!=?",
            (key_row["id"], req.machine_id),
        ).fetchone()[0]
        existing = conn.execute(
            "SELECT * FROM activations WHERE key_id=? AND machine_id=?",
            (key_row["id"], req.machine_id),
        ).fetchone()
        if not existing and active_seats >= key_row["seats"]:
            raise HTTPException(status_code=409, detail=f"Seat limit reached ({key_row['seats']} seats)")
        now = _now()
        if existing:
            conn.execute(
                "UPDATE activations SET last_refresh=?, app_version=?, platform=?, "
                "deactivated_at=NULL WHERE id=?",
                (now, req.app_version, req.platform, existing["id"]),
            )
            activation_id = existing["id"]
        else:
            activation_id = str(uuid.uuid4())
            conn.execute(
                "INSERT INTO activations (id, key_id, machine_id, app_version, platform, "
                "activated_at, last_refresh) VALUES (?,?,?,?,?,?,?)",
                (activation_id, key_row["id"], req.machine_id,
                 req.app_version, req.platform, now, now),
            )
        _audit(conn, "activation", activation_id, "activated", {"machine_id": req.machine_id})
        token = _build_jwt(key_row, req.machine_id)
        notice = os.environ.get("SERVER_NOTICE") or None
        return ActivateResponse(jwt=token, tier=key_row["tier"],
                                valid_until=key_row["valid_until"], notice=notice)


@router.post("/refresh", response_model=ActivateResponse)
def refresh(req: RefreshRequest, db_path=Depends(lambda: None)):
    from app.routes._db_dep import get_db_path
    # Decode without expiry check so we can refresh near-expired tokens
    try:
        payload = verify_jwt(req.jwt)
    except pyjwt.exceptions.ExpiredSignatureError:
        # Allow refresh of just-expired tokens
        payload = pyjwt.decode(req.jwt, options={"verify_exp": False,
                                                   "verify_signature": False})
    except pyjwt.exceptions.InvalidTokenError as e:
        raise HTTPException(status_code=403, detail=str(e))

    with get_db(get_db_path()) as conn:
        key_row = _get_key_row(conn, payload.get("sub", ""), payload.get("product", ""))
        existing = conn.execute(
            "SELECT * FROM activations WHERE key_id=? AND machine_id=? AND deactivated_at IS NULL",
            (key_row["id"], req.machine_id),
        ).fetchone()
        if not existing:
            raise HTTPException(status_code=403, detail="Machine not registered for this key")
        now = _now()
        conn.execute(
            "UPDATE activations SET last_refresh=?, app_version=? WHERE id=?",
            (now, req.app_version or existing["app_version"], existing["id"]),
        )
        _audit(conn, "activation", existing["id"], "refreshed", {"machine_id": req.machine_id})
        token = _build_jwt(key_row, req.machine_id)
        notice = os.environ.get("SERVER_NOTICE") or None
        return ActivateResponse(jwt=token, tier=key_row["tier"],
                                valid_until=key_row["valid_until"], notice=notice)


@router.post("/deactivate")
def deactivate(req: DeactivateRequest):
    from app.routes._db_dep import get_db_path
    try:
        payload = verify_jwt(req.jwt)
    except pyjwt.exceptions.PyJWTError as e:
        raise HTTPException(status_code=403, detail=str(e))
    with get_db(get_db_path()) as conn:
        existing = conn.execute(
            "SELECT a.id FROM activations a "
            "JOIN license_keys k ON k.id=a.key_id "
            "WHERE k.key_display=? AND a.machine_id=? AND a.deactivated_at IS NULL",
            (payload.get("sub", ""), req.machine_id),
        ).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail="No active seat found")
        now = _now()
        conn.execute("UPDATE activations SET deactivated_at=? WHERE id=?",
                     (now, existing["id"]))
        _audit(conn, "activation", existing["id"], "deactivated", {"machine_id": req.machine_id})
    return {"status": "deactivated"}
```

**Step 5: Write `app/routes/_db_dep.py`** (module-level DB path holder, allows test injection)

```python
# app/routes/_db_dep.py
from pathlib import Path
from app.db import DB_PATH

_db_path: Path = DB_PATH


def set_db_path(p: Path) -> None:
    global _db_path
    _db_path = p


def get_db_path() -> Path:
    return _db_path
```

**Step 6: Write `app/main.py`** (minimal, enough for tests)

```python
# app/main.py
from pathlib import Path
from fastapi import FastAPI
from app.db import init_db, DB_PATH
from app.routes import public, admin
from app.routes._db_dep import set_db_path


def create_app(db_path: Path = DB_PATH) -> FastAPI:
    set_db_path(db_path)
    init_db(db_path)
    app = FastAPI(title="CircuitForge License Server", version="1.0.0")
    app.include_router(public.router, prefix="/v1")
    app.include_router(admin.router, prefix="/admin")
    return app


app = create_app()
```

**Step 7: Write minimal `app/routes/admin.py`** (enough for `active_key` fixture to work)

```python
# app/routes/admin.py — skeleton; full implementation in Task 5
import os
import uuid
import secrets
import string
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Header
from app.db import get_db
from app.models import CreateKeyRequest, KeyResponse
from app.routes._db_dep import get_db_path

router = APIRouter()


def _require_admin(authorization: str = Header(...)):
    expected = f"Bearer {os.environ.get('ADMIN_TOKEN', '')}"
    if authorization != expected:
        raise HTTPException(status_code=401, detail="Unauthorized")


def _gen_key_display(product: str) -> str:
    codes = {"peregrine": "PRNG", "falcon": "FLCN", "osprey": "OSPY",
             "kestrel": "KSTR", "harrier": "HARR", "merlin": "MRLN",
             "ibis": "IBIS", "tern": "TERN", "wren": "WREN", "martin": "MRTN"}
    code = codes.get(product, product[:4].upper())
    chars = string.ascii_uppercase + string.digits
    segs = [secrets.choice(chars) + secrets.choice(chars) +
            secrets.choice(chars) + secrets.choice(chars) for _ in range(3)]
    return f"CFG-{code}-{segs[0]}-{segs[1]}-{segs[2]}"


@router.post("/keys", response_model=KeyResponse)
def create_key(req: CreateKeyRequest, authorization: str = Header(...)):
    _require_admin(authorization)
    with get_db(get_db_path()) as conn:
        key_id = str(uuid.uuid4())
        key_display = _gen_key_display(req.product)
        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            "INSERT INTO license_keys (id, key_display, product, tier, seats, valid_until, "
            "customer_email, source, trial, notes, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (key_id, key_display, req.product, req.tier, req.seats, req.valid_until,
             req.customer_email, req.source, 1 if req.trial else 0, req.notes, now),
        )
        return KeyResponse(id=key_id, key_display=key_display, product=req.product,
                           tier=req.tier, seats=req.seats, valid_until=req.valid_until,
                           revoked=False, customer_email=req.customer_email,
                           source=req.source, trial=req.trial, notes=req.notes,
                           created_at=now, active_seat_count=0)
```

**Step 8: Fix test `client` fixture** — remove the broken `Depends` in activate and use `_db_dep` properly. Update `tests/test_public_routes.py` fixture to call `set_db_path`:

```python
# Update the client fixture in tests/test_public_routes.py
@pytest.fixture()
def client(tmp_path, test_keypair, monkeypatch):
    db = tmp_path / "test.db"
    private_pem, public_pem = test_keypair
    (tmp_path / "private.pem").write_bytes(private_pem)
    (tmp_path / "public.pem").write_bytes(public_pem)
    monkeypatch.setenv("JWT_PRIVATE_KEY_PATH", str(tmp_path / "private.pem"))
    monkeypatch.setenv("JWT_PUBLIC_KEY_PATH", str(tmp_path / "public.pem"))
    monkeypatch.setenv("JWT_EXPIRY_DAYS", "30")
    monkeypatch.setenv("GRACE_PERIOD_DAYS", "7")
    monkeypatch.setenv("ADMIN_TOKEN", "test-admin-token")
    monkeypatch.setenv("SERVER_NOTICE", "")
    from app.routes._db_dep import set_db_path
    set_db_path(db)
    from app.main import create_app
    init_db(db)
    app = create_app(db_path=db)
    return TestClient(app)
```

Also remove the broken `db_path=Depends(lambda: None)` from route functions — they should call `get_db_path()` directly (already done in the implementation above).

**Step 9: Run tests to verify they pass**

```bash
conda run -n job-seeker python -m pytest tests/test_public_routes.py -v
```
Expected: `7 passed`

**Step 10: Commit**

```bash
git add -A
git commit -m "feat: public routes — activate, refresh, deactivate with seat enforcement"
```

---

### Task 5: Public routes — usage + flag; Admin routes

**Files:**
- Modify: `app/routes/public.py` (add `/usage`, `/flag`)
- Modify: `app/routes/admin.py` (add list, delete, activations, usage, flags endpoints)
- Modify: `tests/test_public_routes.py` (add usage/flag tests)
- Create: `tests/test_admin_routes.py`

**Step 1: Add usage/flag tests to `tests/test_public_routes.py`**

```python
def test_usage_event_recorded(client, active_key):
    act = client.post("/v1/activate", json={
        "key": active_key, "machine_id": "m1", "product": "peregrine"
    })
    token = act.json()["jwt"]
    resp = client.post("/v1/usage", json={
        "event_type": "cover_letter_generated",
        "product": "peregrine",
        "metadata": {"job_id": 42},
    }, headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200


def test_flag_recorded(client, active_key):
    act = client.post("/v1/activate", json={
        "key": active_key, "machine_id": "m1", "product": "peregrine"
    })
    token = act.json()["jwt"]
    resp = client.post("/v1/flag", json={
        "flag_type": "content_violation",
        "product": "peregrine",
        "details": {"prompt_snippet": "test"},
    }, headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200


def test_usage_with_invalid_jwt_rejected(client):
    resp = client.post("/v1/usage", json={
        "event_type": "test", "product": "peregrine"
    }, headers={"Authorization": "Bearer not-a-jwt"})
    assert resp.status_code == 403
```

**Step 2: Write `tests/test_admin_routes.py`**

```python
# tests/test_admin_routes.py
import pytest
from fastapi.testclient import TestClient
from app.main import create_app
from app.db import init_db
from app.routes._db_dep import set_db_path

ADMIN_HDR = {"Authorization": "Bearer test-admin-token"}


@pytest.fixture()
def client(tmp_path, test_keypair, monkeypatch):
    db = tmp_path / "test.db"
    private_pem, public_pem = test_keypair
    (tmp_path / "private.pem").write_bytes(private_pem)
    (tmp_path / "public.pem").write_bytes(public_pem)
    monkeypatch.setenv("JWT_PRIVATE_KEY_PATH", str(tmp_path / "private.pem"))
    monkeypatch.setenv("JWT_PUBLIC_KEY_PATH", str(tmp_path / "public.pem"))
    monkeypatch.setenv("JWT_EXPIRY_DAYS", "30")
    monkeypatch.setenv("ADMIN_TOKEN", "test-admin-token")
    monkeypatch.setenv("SERVER_NOTICE", "")
    set_db_path(db)
    init_db(db)
    return TestClient(create_app(db_path=db))


def test_create_key_returns_display(client):
    resp = client.post("/admin/keys", json={
        "product": "peregrine", "tier": "paid"
    }, headers=ADMIN_HDR)
    assert resp.status_code == 200
    assert resp.json()["key_display"].startswith("CFG-PRNG-")


def test_list_keys(client):
    client.post("/admin/keys", json={"product": "peregrine", "tier": "paid"},
                headers=ADMIN_HDR)
    resp = client.get("/admin/keys", headers=ADMIN_HDR)
    assert resp.status_code == 200
    assert len(resp.json()) == 1


def test_revoke_key(client):
    create = client.post("/admin/keys", json={"product": "peregrine", "tier": "paid"},
                         headers=ADMIN_HDR)
    key_id = create.json()["id"]
    resp = client.delete(f"/admin/keys/{key_id}", headers=ADMIN_HDR)
    assert resp.status_code == 200
    # Activation should now fail
    key_display = create.json()["key_display"]
    act = client.post("/v1/activate", json={
        "key": key_display, "machine_id": "m1", "product": "peregrine"
    })
    assert act.status_code == 403


def test_admin_requires_token(client):
    resp = client.get("/admin/keys", headers={"Authorization": "Bearer wrong"})
    assert resp.status_code == 401


def test_admin_usage_returns_events(client):
    # Create key, activate, report usage
    create = client.post("/admin/keys", json={"product": "peregrine", "tier": "paid"},
                         headers=ADMIN_HDR)
    key_display = create.json()["key_display"]
    act = client.post("/v1/activate", json={
        "key": key_display, "machine_id": "m1", "product": "peregrine"
    })
    token = act.json()["jwt"]
    client.post("/v1/usage", json={"event_type": "cover_letter_generated",
                                    "product": "peregrine"},
                headers={"Authorization": f"Bearer {token}"})
    resp = client.get("/admin/usage", headers=ADMIN_HDR)
    assert resp.status_code == 200
    assert len(resp.json()) >= 1


def test_admin_flags_returns_list(client):
    create = client.post("/admin/keys", json={"product": "peregrine", "tier": "paid"},
                         headers=ADMIN_HDR)
    key_display = create.json()["key_display"]
    act = client.post("/v1/activate", json={
        "key": key_display, "machine_id": "m1", "product": "peregrine"
    })
    token = act.json()["jwt"]
    client.post("/v1/flag", json={"flag_type": "content_violation", "product": "peregrine"},
                headers={"Authorization": f"Bearer {token}"})
    resp = client.get("/admin/flags", headers=ADMIN_HDR)
    assert resp.status_code == 200
    flags = resp.json()
    assert len(flags) == 1
    assert flags[0]["status"] == "open"
```

**Step 3: Run to verify failure**

```bash
conda run -n job-seeker python -m pytest tests/test_public_routes.py tests/test_admin_routes.py -v
```
Expected: failures on new tests

**Step 4: Add `/usage` and `/flag` to `app/routes/public.py`**

```python
# Add these imports at top of public.py
import json as _json
from fastapi import Header

# Add to router (append after deactivate):

def _jwt_bearer(authorization: str = Header(...)) -> dict:
    try:
        token = authorization.removeprefix("Bearer ")
        return verify_jwt(token)
    except pyjwt.exceptions.PyJWTError as e:
        raise HTTPException(status_code=403, detail=str(e))


@router.post("/usage")
def record_usage(req: UsageRequest, payload: dict = Depends(_jwt_bearer)):
    from app.routes._db_dep import get_db_path
    with get_db(get_db_path()) as conn:
        key_row = conn.execute(
            "SELECT id FROM license_keys WHERE key_display=?",
            (payload.get("sub", ""),),
        ).fetchone()
        if not key_row:
            raise HTTPException(status_code=403, detail="Key not found")
        conn.execute(
            "INSERT INTO usage_events (id, key_id, machine_id, product, event_type, metadata, created_at) "
            "VALUES (?,?,?,?,?,?,?)",
            (str(uuid.uuid4()), key_row["id"], payload.get("machine", ""),
             req.product, req.event_type,
             _json.dumps(req.metadata) if req.metadata else None, _now()),
        )
    return {"status": "recorded"}


@router.post("/flag")
def record_flag(req: FlagRequest, payload: dict = Depends(_jwt_bearer)):
    from app.routes._db_dep import get_db_path
    with get_db(get_db_path()) as conn:
        key_row = conn.execute(
            "SELECT id FROM license_keys WHERE key_display=?",
            (payload.get("sub", ""),),
        ).fetchone()
        if not key_row:
            raise HTTPException(status_code=403, detail="Key not found")
        conn.execute(
            "INSERT INTO flags (id, key_id, machine_id, product, flag_type, details, created_at) "
            "VALUES (?,?,?,?,?,?,?)",
            (str(uuid.uuid4()), key_row["id"], payload.get("machine", ""),
             req.product, req.flag_type,
             _json.dumps(req.details) if req.details else None, _now()),
        )
    return {"status": "flagged"}
```

**Step 5: Complete `app/routes/admin.py`** — add GET keys, DELETE, activations, usage, flags, PATCH flag:

```python
# Append to app/routes/admin.py

@router.get("/keys")
def list_keys(authorization: str = Header(...)):
    _require_admin(authorization)
    with get_db(get_db_path()) as conn:
        rows = conn.execute("SELECT * FROM license_keys ORDER BY created_at DESC").fetchall()
        result = []
        for row in rows:
            seat_count = conn.execute(
                "SELECT COUNT(*) FROM activations WHERE key_id=? AND deactivated_at IS NULL",
                (row["id"],),
            ).fetchone()[0]
            result.append({**dict(row), "active_seat_count": seat_count, "revoked": bool(row["revoked"])})
        return result


@router.delete("/keys/{key_id}")
def revoke_key(key_id: str, authorization: str = Header(...)):
    _require_admin(authorization)
    with get_db(get_db_path()) as conn:
        row = conn.execute("SELECT id FROM license_keys WHERE id=?", (key_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Key not found")
        now = datetime.now(timezone.utc).isoformat()
        conn.execute("UPDATE license_keys SET revoked=1 WHERE id=?", (key_id,))
        conn.execute(
            "INSERT INTO audit_log (id, entity_type, entity_id, action, created_at) "
            "VALUES (?,?,?,?,?)",
            (str(uuid.uuid4()), "key", key_id, "revoked", now),
        )
    return {"status": "revoked"}


@router.get("/activations")
def list_activations(authorization: str = Header(...)):
    _require_admin(authorization)
    with get_db(get_db_path()) as conn:
        rows = conn.execute(
            "SELECT a.*, k.key_display, k.product FROM activations a "
            "JOIN license_keys k ON k.id=a.key_id ORDER BY a.activated_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]


@router.get("/usage")
def list_usage(key_id: str | None = None, authorization: str = Header(...)):
    _require_admin(authorization)
    with get_db(get_db_path()) as conn:
        if key_id:
            rows = conn.execute(
                "SELECT * FROM usage_events WHERE key_id=? ORDER BY created_at DESC",
                (key_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM usage_events ORDER BY created_at DESC LIMIT 500"
            ).fetchall()
        return [dict(r) for r in rows]


@router.get("/flags")
def list_flags(status: str = "open", authorization: str = Header(...)):
    _require_admin(authorization)
    with get_db(get_db_path()) as conn:
        rows = conn.execute(
            "SELECT * FROM flags WHERE status=? ORDER BY created_at DESC", (status,)
        ).fetchall()
        return [dict(r) for r in rows]


@router.patch("/flags/{flag_id}")
def update_flag(flag_id: str, req: "FlagUpdateRequest", authorization: str = Header(...)):
    from app.models import FlagUpdateRequest as FUR
    _require_admin(authorization)
    with get_db(get_db_path()) as conn:
        row = conn.execute("SELECT id FROM flags WHERE id=?", (flag_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Flag not found")
        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            "UPDATE flags SET status=?, action_taken=?, reviewed_at=? WHERE id=?",
            (req.status, req.action_taken, now, flag_id),
        )
        conn.execute(
            "INSERT INTO audit_log (id, entity_type, entity_id, action, created_at) "
            "VALUES (?,?,?,?,?)",
            (str(uuid.uuid4()), "flag", flag_id, f"flag_{req.status}", now),
        )
    return {"status": "updated"}
```

Add `from app.models import FlagUpdateRequest` to the imports at top of admin.py.

**Step 6: Run all server tests**

```bash
conda run -n job-seeker python -m pytest tests/ -v
```
Expected: all tests pass

**Step 7: Commit**

```bash
git add -A
git commit -m "feat: usage/flag endpoints + complete admin CRUD"
```

---

### Task 6: Docker + infrastructure files

**Files:**
- Create: `Dockerfile`
- Create: `docker-compose.yml`
- Create: `.env.example`
- Create: `keys/README.md`

**Step 1: Write `Dockerfile`**

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app/ ./app/
EXPOSE 8600
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8600", "--workers", "1"]
```

**Step 2: Write `docker-compose.yml`**

```yaml
services:
  license:
    build: .
    restart: unless-stopped
    ports:
      - "127.0.0.1:8600:8600"
    volumes:
      - license_data:/app/data
      - ./keys:/app/keys:ro
    env_file: .env

volumes:
  license_data:
```

**Step 3: Write `.env.example`**

```bash
# Copy to .env and fill in values — never commit .env
ADMIN_TOKEN=replace-with-long-random-string
JWT_PRIVATE_KEY_PATH=/app/keys/private.pem
JWT_PUBLIC_KEY_PATH=/app/keys/public.pem
JWT_EXPIRY_DAYS=30
GRACE_PERIOD_DAYS=7
# Optional: shown to users as a banner on next JWT refresh
SERVER_NOTICE=
```

**Step 4: Write `keys/README.md`**

```markdown
# Keys

Generate the RSA keypair once on the server, then copy `public.pem` into the Peregrine repo.

```bash
openssl genrsa -out private.pem 2048
openssl rsa -in private.pem -pubout -out public.pem
```

- `private.pem` — NEVER commit. Stays on Heimdall only.
- `public.pem` — committed to this repo AND to `peregrine/scripts/license_public_key.pem`.
```

**Step 5: Write `scripts/issue-key.sh`**

```bash
#!/usr/bin/env bash
# scripts/issue-key.sh — Issue a CircuitForge license key
# Usage: ./scripts/issue-key.sh [--product peregrine] [--tier paid] [--seats 2]
#                                [--email user@example.com] [--notes "Beta user"]
#                                [--trial] [--valid-until 2027-01-01]

set -euo pipefail

SERVER="${LICENSE_SERVER:-https://license.circuitforge.com}"
TOKEN="${ADMIN_TOKEN:-}"

if [[ -z "$TOKEN" ]]; then
  echo "Error: set ADMIN_TOKEN env var" >&2
  exit 1
fi

PRODUCT="peregrine"
TIER="paid"
SEATS=1
EMAIL=""
NOTES=""
TRIAL="false"
VALID_UNTIL="null"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --product)    PRODUCT="$2";     shift 2 ;;
    --tier)       TIER="$2";        shift 2 ;;
    --seats)      SEATS="$2";       shift 2 ;;
    --email)      EMAIL="$2";       shift 2 ;;
    --notes)      NOTES="$2";       shift 2 ;;
    --trial)      TRIAL="true";     shift 1 ;;
    --valid-until) VALID_UNTIL="\"$2\""; shift 2 ;;
    *) echo "Unknown arg: $1" >&2; exit 1 ;;
  esac
done

EMAIL_JSON=$([ -n "$EMAIL" ] && echo "\"$EMAIL\"" || echo "null")
NOTES_JSON=$([ -n "$NOTES" ] && echo "\"$NOTES\"" || echo "null")

curl -s -X POST "$SERVER/admin/keys" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{
    \"product\": \"$PRODUCT\",
    \"tier\": \"$TIER\",
    \"seats\": $SEATS,
    \"valid_until\": $VALID_UNTIL,
    \"customer_email\": $EMAIL_JSON,
    \"source\": \"manual\",
    \"trial\": $TRIAL,
    \"notes\": $NOTES_JSON
  }" | python3 -c "
import json, sys
data = json.load(sys.stdin)
if 'key_display' in data:
    print(f'Key: {data[\"key_display\"]}')
    print(f'ID:  {data[\"id\"]}')
    print(f'Tier: {data[\"tier\"]} ({data[\"seats\"]} seat(s))')
else:
    print('Error:', json.dumps(data, indent=2))
"
```

```bash
chmod +x scripts/issue-key.sh
```

**Step 6: Commit**

```bash
git add -A
git commit -m "feat: Dockerfile, docker-compose.yml, .env.example, issue-key.sh"
```

---

### Task 7: Init Forgejo repo + push

**Step 1: Create repo on Forgejo**

Using `gh` CLI configured for your Forgejo instance, or via the web UI at `https://git.opensourcesolarpunk.com`. Create a **private** repo named `circuitforge-license` under the `pyr0ball` user.

```bash
# If gh is configured for Forgejo:
gh repo create pyr0ball/circuitforge-license --private \
  --gitea-url https://git.opensourcesolarpunk.com

# Or create manually at https://git.opensourcesolarpunk.com and add remote:
cd /Library/Development/devl/circuitforge-license
git remote add origin https://git.opensourcesolarpunk.com/pyr0ball/circuitforge-license.git
```

**Step 2: Push**

```bash
git push -u origin main
```

**Step 3: Generate real keypair on Heimdall (do once, after deployment)**

```bash
# SSH to Heimdall or run locally — keys go in circuitforge-license/keys/
mkdir -p /Library/Development/devl/circuitforge-license/keys
cd /Library/Development/devl/circuitforge-license/keys
openssl genrsa -out private.pem 2048
openssl rsa -in private.pem -pubout -out public.pem
git add public.pem
git commit -m "chore: add RSA public key"
git push
```

---

## PART B — Peregrine Client Integration

**Working directory for all Part B tasks:** `/Library/Development/devl/peregrine/`
**Run tests:** `/devl/miniconda3/envs/job-seeker/bin/pytest tests/ -v`

---

### Task 8: `scripts/license.py` + public key

**Files:**
- Create: `scripts/license_public_key.pem` (copy from license server `keys/public.pem`)
- Create: `scripts/license.py`
- Create: `tests/test_license.py`

**Step 1: Copy the public key**

```bash
cp /Library/Development/devl/circuitforge-license/keys/public.pem \
   /Library/Development/devl/peregrine/scripts/license_public_key.pem
```

**Step 2: Write failing tests**

```python
# tests/test_license.py
import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
import jwt as pyjwt
from datetime import datetime, timedelta, timezone


@pytest.fixture()
def test_keys(tmp_path):
    """Generate test RSA keypair and return (private_pem, public_pem, public_path)."""
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    public_path = tmp_path / "test_public.pem"
    public_path.write_bytes(public_pem)
    return private_pem, public_pem, public_path


def _make_jwt(private_pem: bytes, tier: str = "paid",
              product: str = "peregrine",
              exp_delta_days: int = 30,
              machine: str = "test-machine") -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": "CFG-PRNG-TEST-TEST-TEST",
        "product": product,
        "tier": tier,
        "seats": 1,
        "machine": machine,
        "iat": now,
        "exp": now + timedelta(days=exp_delta_days),
    }
    return pyjwt.encode(payload, private_pem, algorithm="RS256")


def _write_license(tmp_path, jwt_token: str, grace_until: str | None = None) -> Path:
    data = {
        "jwt": jwt_token,
        "key_display": "CFG-PRNG-TEST-TEST-TEST",
        "tier": "paid",
        "valid_until": None,
        "machine_id": "test-machine",
        "last_refresh": datetime.now(timezone.utc).isoformat(),
        "grace_until": grace_until,
    }
    p = tmp_path / "license.json"
    p.write_text(json.dumps(data))
    return p


class TestVerifyLocal:
    def test_valid_jwt_returns_tier(self, test_keys, tmp_path):
        private_pem, _, public_path = test_keys
        token = _make_jwt(private_pem)
        license_path = _write_license(tmp_path, token)
        from scripts.license import verify_local
        result = verify_local(license_path=license_path, public_key_path=public_path)
        assert result is not None
        assert result["tier"] == "paid"

    def test_missing_file_returns_none(self, tmp_path):
        from scripts.license import verify_local
        result = verify_local(license_path=tmp_path / "missing.json",
                              public_key_path=tmp_path / "key.pem")
        assert result is None

    def test_wrong_product_returns_none(self, test_keys, tmp_path):
        private_pem, _, public_path = test_keys
        token = _make_jwt(private_pem, product="falcon")
        license_path = _write_license(tmp_path, token)
        from scripts.license import verify_local
        result = verify_local(license_path=license_path, public_key_path=public_path)
        assert result is None

    def test_expired_within_grace_returns_tier(self, test_keys, tmp_path):
        private_pem, _, public_path = test_keys
        token = _make_jwt(private_pem, exp_delta_days=-1)
        grace_until = (datetime.now(timezone.utc) + timedelta(days=3)).isoformat()
        license_path = _write_license(tmp_path, token, grace_until=grace_until)
        from scripts.license import verify_local
        result = verify_local(license_path=license_path, public_key_path=public_path)
        assert result is not None
        assert result["tier"] == "paid"
        assert result["in_grace"] is True

    def test_expired_past_grace_returns_none(self, test_keys, tmp_path):
        private_pem, _, public_path = test_keys
        token = _make_jwt(private_pem, exp_delta_days=-10)
        grace_until = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        license_path = _write_license(tmp_path, token, grace_until=grace_until)
        from scripts.license import verify_local
        result = verify_local(license_path=license_path, public_key_path=public_path)
        assert result is None


class TestEffectiveTier:
    def test_returns_free_when_no_license(self, tmp_path):
        from scripts.license import effective_tier
        result = effective_tier(
            license_path=tmp_path / "missing.json",
            public_key_path=tmp_path / "key.pem",
        )
        assert result == "free"

    def test_returns_tier_from_valid_jwt(self, test_keys, tmp_path):
        private_pem, _, public_path = test_keys
        token = _make_jwt(private_pem, tier="premium")
        license_path = _write_license(tmp_path, token)
        from scripts.license import effective_tier
        result = effective_tier(license_path=license_path, public_key_path=public_path)
        assert result == "premium"
```

**Step 3: Run to verify failure**

```bash
/devl/miniconda3/envs/job-seeker/bin/pytest tests/test_license.py -v
```
Expected: `FAILED` — `ModuleNotFoundError: No module named 'scripts.license'`

**Step 4: Write `scripts/license.py`**

```python
# scripts/license.py
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
from typing import Any

import jwt as pyjwt

_HERE = Path(__file__).parent
_DEFAULT_LICENSE_PATH = _HERE.parent / "config" / "license.json"
_DEFAULT_PUBLIC_KEY_PATH = _HERE / "license_public_key.pem"
_LICENSE_SERVER = "https://license.circuitforge.com"
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

    Returns dict has keys: tier, in_grace (bool), sub, product, notice (optional).
    """
    stored = _read_license(license_path)
    if not stored or not stored.get("jwt"):
        return None

    if not public_key_path.exists():
        return None

    public_key = public_key_path.read_bytes()

    try:
        payload = pyjwt.decode(stored["jwt"], public_key, algorithms=["RS256"])
        # Valid and not expired
        if payload.get("product") != _PRODUCT:
            return None
        return {**payload, "in_grace": False}

    except pyjwt.exceptions.ExpiredSignatureError:
        # JWT expired — check grace period
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
        # Decode without verification to get payload
        try:
            payload = pyjwt.decode(stored["jwt"], public_key,
                                   algorithms=["RS256"],
                                   options={"verify_exp": False})
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
        f"{_LICENSE_SERVER}/v1/activate",
        json={"key": key, "machine_id": mid, "product": _PRODUCT,
              "app_version": app_version, "platform": _detect_platform()},
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
            f"{_LICENSE_SERVER}/v1/deactivate",
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
        payload = pyjwt.decode(stored["jwt"], public_key_path.read_bytes(),
                               algorithms=["RS256"])
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
            f"{_LICENSE_SERVER}/v1/refresh",
            json={"jwt": stored["jwt"],
                  "machine_id": stored.get("machine_id", _machine_id())},
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
        # Unreachable — set grace period if not already set
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
                f"{_LICENSE_SERVER}/v1/usage",
                json={"event_type": event_type, "product": _PRODUCT,
                      "metadata": metadata or {}},
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
                f"{_LICENSE_SERVER}/v1/flag",
                json={"flag_type": flag_type, "product": _PRODUCT,
                      "details": details or {}},
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
```

**Step 5: Run tests to verify they pass**

```bash
/devl/miniconda3/envs/job-seeker/bin/pytest tests/test_license.py -v
```
Expected: all tests pass

**Step 6: Commit**

```bash
cd /Library/Development/devl/peregrine
git add scripts/license.py scripts/license_public_key.pem tests/test_license.py
git commit -m "feat: license.py client — verify_local, effective_tier, activate, refresh, report_usage"
```

---

### Task 9: Wire `tiers.py` + update `.gitignore`

**Files:**
- Modify: `app/wizard/tiers.py`
- Modify: `.gitignore`
- Create: `tests/test_license_tier_integration.py`

**Step 1: Write failing test**

```python
# tests/test_license_tier_integration.py
import json
import pytest
from pathlib import Path
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
import jwt as pyjwt


@pytest.fixture()
def license_env(tmp_path):
    """Returns (private_pem, public_path, license_path) for tier integration tests."""
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    public_path = tmp_path / "public.pem"
    public_path.write_bytes(public_pem)
    license_path = tmp_path / "license.json"
    return private_pem, public_path, license_path


def _write_jwt_license(license_path, private_pem, tier="paid", days=30):
    now = datetime.now(timezone.utc)
    token = pyjwt.encode({
        "sub": "CFG-PRNG-TEST", "product": "peregrine", "tier": tier,
        "iat": now, "exp": now + timedelta(days=days),
    }, private_pem, algorithm="RS256")
    license_path.write_text(json.dumps({"jwt": token, "grace_until": None}))


def test_effective_tier_free_without_license(tmp_path):
    from app.wizard.tiers import effective_tier
    tier = effective_tier(
        profile=None,
        license_path=tmp_path / "missing.json",
        public_key_path=tmp_path / "key.pem",
    )
    assert tier == "free"


def test_effective_tier_paid_with_valid_license(license_env):
    private_pem, public_path, license_path = license_env
    _write_jwt_license(license_path, private_pem, tier="paid")
    from app.wizard.tiers import effective_tier
    tier = effective_tier(profile=None, license_path=license_path,
                          public_key_path=public_path)
    assert tier == "paid"


def test_effective_tier_dev_override_takes_precedence(license_env):
    """dev_tier_override wins even when a valid license is present."""
    private_pem, public_path, license_path = license_env
    _write_jwt_license(license_path, private_pem, tier="paid")

    class FakeProfile:
        dev_tier_override = "premium"

    from app.wizard.tiers import effective_tier
    tier = effective_tier(profile=FakeProfile(), license_path=license_path,
                          public_key_path=public_path)
    assert tier == "premium"
```

**Step 2: Run to verify failure**

```bash
/devl/miniconda3/envs/job-seeker/bin/pytest tests/test_license_tier_integration.py -v
```
Expected: `FAILED` — `effective_tier() got unexpected keyword argument 'license_path'`

**Step 3: Update `app/wizard/tiers.py`** — add `effective_tier()` function

```python
# Add at bottom of app/wizard/tiers.py (after existing functions):

def effective_tier(
    profile=None,
    license_path=None,
    public_key_path=None,
) -> str:
    """Return the effective tier for this installation.

    Priority:
    1. profile.dev_tier_override (developer mode override)
    2. License JWT verification (offline RS256 check)
    3. "free" (fallback)

    license_path and public_key_path default to production paths when None.
    Pass explicit paths in tests to avoid touching real files.
    """
    if profile and getattr(profile, "dev_tier_override", None):
        return profile.dev_tier_override

    from scripts.license import effective_tier as _license_tier
    from pathlib import Path as _Path

    kwargs = {}
    if license_path is not None:
        kwargs["license_path"] = _Path(license_path)
    if public_key_path is not None:
        kwargs["public_key_path"] = _Path(public_key_path)
    return _license_tier(**kwargs)
```

**Step 4: Add `config/license.json` to `.gitignore`**

Open `/Library/Development/devl/peregrine/.gitignore` and add:
```
config/license.json
```

**Step 5: Run tests**

```bash
/devl/miniconda3/envs/job-seeker/bin/pytest tests/test_license_tier_integration.py -v
```
Expected: `3 passed`

**Step 6: Run full suite to check for regressions**

```bash
/devl/miniconda3/envs/job-seeker/bin/pytest tests/ -v
```
Expected: all existing tests still pass

**Step 7: Commit**

```bash
git add app/wizard/tiers.py .gitignore tests/test_license_tier_integration.py
git commit -m "feat: wire license.effective_tier into tiers.py; add dev_override priority"
```

---

### Task 10: Settings License tab + app.py startup refresh

**Files:**
- Modify: `app/pages/2_Settings.py` (add License tab)
- Modify: `app/app.py` (call `refresh_if_needed` on startup)

**Step 1: Add License tab to `app/pages/2_Settings.py`**

Find the `_tab_names` list and insert `"🔑 License"` after `"🛠️ Developer"` (or at the end of the list before Developer). Then find the corresponding tab variable assignment block and add:

```python
# In the tab variables section:
tab_license = _all_tabs[<correct index>]
```

Then add the license tab content block:

```python
# ── License tab ──────────────────────────────────────────────────────────────
with tab_license:
    st.subheader("🔑 License")

    from scripts.license import (
        verify_local as _verify_local,
        activate as _activate,
        deactivate as _deactivate,
        _DEFAULT_LICENSE_PATH,
        _DEFAULT_PUBLIC_KEY_PATH,
    )

    _lic = _verify_local()

    if _lic:
        # Active license
        _grace_note = " _(grace period active)_" if _lic.get("in_grace") else ""
        st.success(f"**{_lic['tier'].title()} tier** active{_grace_note}")
        st.caption(f"Key: `{_DEFAULT_LICENSE_PATH.exists() and __import__('json').loads(_DEFAULT_LICENSE_PATH.read_text()).get('key_display', '—') or '—'}`")
        if _lic.get("notice"):
            st.info(_lic["notice"])
        if st.button("Deactivate this machine", type="secondary"):
            _deactivate()
            st.success("Deactivated. Restart the app to apply.")
            st.rerun()
    else:
        st.info("No active license — running on **free tier**.")
        st.caption("Enter a license key to unlock paid features.")
        _key_input = st.text_input(
            "License key",
            placeholder="CFG-PRNG-XXXX-XXXX-XXXX",
            label_visibility="collapsed",
        )
        if st.button("Activate", disabled=not (_key_input or "").strip()):
            with st.spinner("Activating…"):
                try:
                    result = _activate(_key_input.strip())
                    st.success(f"Activated! Tier: **{result['tier']}**")
                    st.rerun()
                except Exception as _e:
                    st.error(f"Activation failed: {_e}")
```

**Step 2: Add startup refresh to `app/app.py`**

Find the startup block (near where `init_db` is called, before `st.navigation`). Add:

```python
# Silent license refresh on startup — no-op if unreachable
try:
    from scripts.license import refresh_if_needed as _refresh_license
    _refresh_license()
except Exception:
    pass
```

**Step 3: Run full test suite**

```bash
/devl/miniconda3/envs/job-seeker/bin/pytest tests/ -v
```
Expected: all tests pass (License tab is UI-only, no new unit tests needed — covered by existing Settings tests for tab structure)

**Step 4: Commit**

```bash
git add app/pages/2_Settings.py app/app.py
git commit -m "feat: License tab in Settings (activate/deactivate UI) + startup refresh"
```

---

### Task 11: Final check + Forgejo push

**Step 1: Run full suite one last time**

```bash
/devl/miniconda3/envs/job-seeker/bin/pytest tests/ -v --tb=short
```
Expected: all tests pass

**Step 2: Push Peregrine to Forgejo**

```bash
cd /Library/Development/devl/peregrine
git push origin main
```

**Step 3: Verify Caddy route is ready**

Add to `/opt/containers/caddy/Caddyfile` on Heimdall (SSH in and edit):

```caddy
license.circuitforge.com {
    reverse_proxy localhost:8600
}
```

Reload Caddy:
```bash
docker exec caddy-proxy caddy reload --config /etc/caddy/Caddyfile
```

**Step 4: Deploy license server on Heimdall**

```bash
# SSH to Heimdall
cd /Library/Development/devl/circuitforge-license  # or wherever cloned
cp .env.example .env
# Edit .env: set ADMIN_TOKEN to a long random string
# keys/ already has private.pem + public.pem from Task 7 step 3
docker compose up -d
```

**Step 5: Smoke test**

```bash
# Create a test key
export ADMIN_TOKEN=<your token>
./scripts/issue-key.sh --product peregrine --tier paid --email test@example.com
# → Key: CFG-PRNG-XXXX-XXXX-XXXX

# Test activation from Peregrine machine
curl -X POST https://license.circuitforge.com/v1/activate \
  -H "Content-Type: application/json" \
  -d '{"key":"CFG-PRNG-XXXX-XXXX-XXXX","machine_id":"test","product":"peregrine"}'
# → {"jwt":"eyJ...","tier":"paid",...}
```

---

## Summary

| Task | Repo | Deliverable |
|------|------|-------------|
| 1 | license-server | Repo scaffold + DB schema |
| 2 | license-server | `crypto.py` + test keypair fixture |
| 3 | license-server | Pydantic models |
| 4 | license-server | `/v1/activate`, `/v1/refresh`, `/v1/deactivate` |
| 5 | license-server | `/v1/usage`, `/v1/flag`, full admin CRUD |
| 6 | license-server | Docker + Caddy + `issue-key.sh` |
| 7 | license-server | Forgejo push + real keypair |
| 8 | peregrine | `scripts/license.py` + public key |
| 9 | peregrine | `tiers.py` wired + `.gitignore` updated |
| 10 | peregrine | License tab in Settings + startup refresh |
| 11 | both | Deploy to Heimdall + smoke test |
