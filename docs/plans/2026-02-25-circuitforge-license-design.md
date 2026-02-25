# CircuitForge License Server — Design Document

**Date:** 2026-02-25
**Status:** Approved — ready for implementation

---

## Goal

Build a self-hosted licensing server for Circuit Forge LLC products. v1 serves Peregrine; schema is multi-product from day one. Enforces free / paid / premium / ultra tier gates with offline-capable JWT validation, 30-day refresh cycle, 7-day grace period, seat tracking, usage telemetry, and a content violation flagging foundation.

## Architecture

```
┌─────────────────────────────────────────────────┐
│  circuitforge-license  (Heimdall:8600)           │
│  FastAPI + SQLite + RS256 JWT                    │
│                                                  │
│  Public API (/v1/…):                             │
│    POST /v1/activate     → issue JWT             │
│    POST /v1/refresh      → renew JWT             │
│    POST /v1/deactivate   → free a seat           │
│    POST /v1/usage        → record usage event    │
│    POST /v1/flag         → report violation      │
│                                                  │
│  Admin API (/admin/…, bearer token):             │
│    POST/GET /admin/keys          → CRUD keys     │
│    DELETE   /admin/keys/{id}     → revoke        │
│    GET      /admin/activations   → audit         │
│    GET      /admin/usage         → telemetry     │
│    GET/PATCH /admin/flags        → flag review   │
└─────────────────────────────────────────────────┘
         ↑ HTTPS via Caddy (license.circuitforge.com)

┌─────────────────────────────────────────────────┐
│  Peregrine (user's machine)                      │
│  scripts/license.py                              │
│                                                  │
│  activate(key)    → POST /v1/activate            │
│                     writes config/license.json   │
│  verify_local()   → validates JWT offline        │
│                     using embedded public key    │
│  refresh_if_needed() → called on app startup     │
│  effective_tier() → tier string for can_use()    │
│  report_usage(…)  → fire-and-forget telemetry    │
│  report_flag(…)   → fire-and-forget violation    │
└─────────────────────────────────────────────────┘
```

**Key properties:**
- Peregrine verifies tier **offline** on every check — RS256 public key embedded at build time
- Network required only at activation and 30-day refresh
- Revoked keys stop working at next refresh cycle (≤30 day lag — acceptable for v1)
- `config/license.json` gitignored; missing = free tier

---

## Crypto: RS256 (asymmetric JWT)

- **Private key** — lives only on the license server (`keys/private.pem`, gitignored)
- **Public key** — committed to both the license server repo and Peregrine (`scripts/license_public_key.pem`)
- Peregrine can verify JWT authenticity without ever knowing the private key
- A stolen JWT cannot be forged without the private key
- Revocation: server refuses refresh; old JWT valid until expiry then grace period expires

**Key generation (one-time, on Heimdall):**
```bash
openssl genrsa -out keys/private.pem 2048
openssl rsa -in keys/private.pem -pubout -out keys/public.pem
# copy keys/public.pem → peregrine/scripts/license_public_key.pem
```

---

## Database Schema

```sql
CREATE TABLE license_keys (
    id             TEXT PRIMARY KEY,            -- UUID
    key_display    TEXT UNIQUE NOT NULL,        -- CFG-PRNG-XXXX-XXXX-XXXX
    product        TEXT NOT NULL,               -- peregrine | falcon | osprey | …
    tier           TEXT NOT NULL,               -- paid | premium | ultra
    seats          INTEGER DEFAULT 1,
    valid_until    TEXT,                        -- ISO date or NULL (perpetual)
    revoked        INTEGER DEFAULT 0,
    customer_email TEXT,                        -- proper field, not buried in notes
    source         TEXT DEFAULT 'manual',       -- manual | beta | promo | stripe
    trial          INTEGER DEFAULT 0,           -- 1 = time-limited trial key
    notes          TEXT,
    created_at     TEXT NOT NULL
);

CREATE TABLE activations (
    id             TEXT PRIMARY KEY,
    key_id         TEXT NOT NULL REFERENCES license_keys(id),
    machine_id     TEXT NOT NULL,               -- sha256(hostname + MAC)
    app_version    TEXT,                        -- Peregrine version at last refresh
    platform       TEXT,                        -- linux | macos | windows | docker
    activated_at   TEXT NOT NULL,
    last_refresh   TEXT NOT NULL,
    deactivated_at TEXT                         -- NULL = still active
);

CREATE TABLE usage_events (
    id          TEXT PRIMARY KEY,
    key_id      TEXT NOT NULL REFERENCES license_keys(id),
    machine_id  TEXT NOT NULL,
    product     TEXT NOT NULL,
    event_type  TEXT NOT NULL,                  -- cover_letter_generated |
                                                --   company_research | email_sync |
                                                --   interview_prep | survey | etc.
    metadata    TEXT,                           -- JSON blob for context
    created_at  TEXT NOT NULL
);

CREATE TABLE flags (
    id           TEXT PRIMARY KEY,
    key_id       TEXT NOT NULL REFERENCES license_keys(id),
    machine_id   TEXT,
    product      TEXT NOT NULL,
    flag_type    TEXT NOT NULL,                 -- content_violation | tos_violation |
                                                --   abuse | manual
    details      TEXT,                          -- JSON: prompt snippet, output excerpt
    status       TEXT DEFAULT 'open',           -- open | reviewed | dismissed | actioned
    created_at   TEXT NOT NULL,
    reviewed_at  TEXT,
    action_taken TEXT                           -- none | warned | revoked
);

CREATE TABLE audit_log (
    id          TEXT PRIMARY KEY,
    entity_type TEXT NOT NULL,                  -- key | activation | flag
    entity_id   TEXT NOT NULL,
    action      TEXT NOT NULL,                  -- created | revoked | activated |
                                                --   deactivated | flag_actioned
    actor       TEXT,                           -- admin identifier (future multi-admin)
    details     TEXT,                           -- JSON
    created_at  TEXT NOT NULL
);
```

**Flags scope (v1):** Schema and `POST /v1/flag` endpoint capture data. No admin enforcement UI in v1 — query DB directly. Build review UI in v2 when there's data to act on.

---

## JWT Payload

```json
{
  "sub":      "CFG-PRNG-A1B2-C3D4-E5F6",
  "product":  "peregrine",
  "tier":     "paid",
  "seats":    2,
  "machine":  "a3f9c2…",
  "notice":   "Version 1.1 available — see circuitforge.com/update",
  "iat":      1740000000,
  "exp":      1742592000
}
```

`notice` is optional — set via a server config value; included in refresh responses so Peregrine can surface it as a banner. No DB table needed.

---

## Key Format

`CFG-PRNG-A1B2-C3D4-E5F6`

- `CFG` — Circuit Forge
- `PRNG` / `FLCN` / `OSPY` / … — 4-char product code
- Three random 4-char alphanumeric segments
- Human-readable, easy to copy/paste into a support email

---

## Endpoint Reference

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| POST | `/v1/activate` | none | Issue JWT for key + machine |
| POST | `/v1/refresh` | JWT bearer | Renew JWT before expiry |
| POST | `/v1/deactivate` | JWT bearer | Free a seat |
| POST | `/v1/usage` | JWT bearer | Record usage event (fire-and-forget) |
| POST | `/v1/flag` | JWT bearer | Report content/ToS violation |
| POST | `/admin/keys` | admin token | Create a new key |
| GET | `/admin/keys` | admin token | List all keys + activation counts |
| DELETE | `/admin/keys/{id}` | admin token | Revoke a key |
| GET | `/admin/activations` | admin token | Full activation audit |
| GET | `/admin/usage` | admin token | Usage breakdown per key/product/event |
| GET | `/admin/flags` | admin token | List flags (open by default) |
| PATCH | `/admin/flags/{id}` | admin token | Update flag status + action |

---

## Peregrine Client (`scripts/license.py`)

**Public API:**
```python
def activate(key: str) -> dict             # POST /v1/activate, writes license.json
def verify_local() -> dict | None          # validates JWT offline; None = free tier
def refresh_if_needed() -> None            # silent; called on app startup
def effective_tier() -> str                # "free"|"paid"|"premium"|"ultra"
def report_usage(event_type: str,          # fire-and-forget; failures silently dropped
                 metadata: dict = {}) -> None
def report_flag(flag_type: str,            # fire-and-forget
                details: dict) -> None
```

**`effective_tier()` decision tree:**
```
license.json missing or unreadable     → "free"
JWT signature invalid                  → "free"
JWT product != "peregrine"             → "free"
JWT not expired                        → tier from payload
JWT expired, within grace period       → tier from payload + show banner
JWT expired, grace period expired      → "free" + show banner
```

**`config/license.json` (gitignored):**
```json
{
  "jwt":          "eyJ…",
  "key_display":  "CFG-PRNG-A1B2-C3D4-E5F6",
  "tier":         "paid",
  "valid_until":  "2026-03-27",
  "machine_id":   "a3f9c2…",
  "last_refresh": "2026-02-25T12:00:00Z",
  "grace_until":  null
}
```

**Integration point in `tiers.py`:**
```python
def effective_tier(profile) -> str:
    from scripts.license import effective_tier as _license_tier
    if profile.dev_tier_override:      # dev override still works in dev mode
        return profile.dev_tier_override
    return _license_tier()
```

**Settings License tab** (new tab in `app/pages/2_Settings.py`):
- Text input: enter license key → calls `activate()` → shows result
- If active: tier badge, key display string, expiry date, seat count
- Grace period: amber banner with days remaining
- "Deactivate this machine" button → `/v1/deactivate`, deletes `license.json`

---

## Deployment

**Repo:** `git.opensourcesolarpunk.com/pyr0ball/circuitforge-license` (private)

**Repo layout:**
```
circuitforge-license/
├── app/
│   ├── main.py          # FastAPI app
│   ├── db.py            # SQLite helpers, schema init
│   ├── models.py        # Pydantic models
│   ├── crypto.py        # RSA sign/verify helpers
│   └── routes/
│       ├── public.py    # /v1/* endpoints
│       └── admin.py     # /admin/* endpoints
├── data/                # SQLite DB (named volume)
├── keys/
│   ├── private.pem      # gitignored
│   └── public.pem       # committed
├── scripts/
│   └── issue-key.sh     # curl wrapper for key issuance
├── tests/
├── Dockerfile
├── docker-compose.yml
├── .env.example
└── requirements.txt
```

**`docker-compose.yml` (on Heimdall):**
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

**`.env` (gitignored):**
```
ADMIN_TOKEN=<long random string>
JWT_PRIVATE_KEY_PATH=/app/keys/private.pem
JWT_PUBLIC_KEY_PATH=/app/keys/public.pem
JWT_EXPIRY_DAYS=30
GRACE_PERIOD_DAYS=7
```

**Caddy block (add to Heimdall Caddyfile):**
```caddy
license.circuitforge.com {
    reverse_proxy localhost:8600
}
```

---

## Admin Workflow (v1)

All operations via `curl` or `scripts/issue-key.sh`:

```bash
# Issue a key
./scripts/issue-key.sh --product peregrine --tier paid --seats 2 \
  --email user@example.com --notes "Beta — manual payment 2026-02-25"
# → CFG-PRNG-A1B2-C3D4-E5F6  (email to customer)

# List all keys
curl https://license.circuitforge.com/admin/keys \
  -H "Authorization: Bearer $ADMIN_TOKEN"

# Revoke a key
curl -X DELETE https://license.circuitforge.com/admin/keys/{id} \
  -H "Authorization: Bearer $ADMIN_TOKEN"
```

---

## Testing Strategy

**License server:**
- pytest with in-memory SQLite and generated test keypair
- All endpoints tested: activate, refresh, deactivate, usage, flag, admin CRUD
- Seat limit enforcement, expiry, revocation all unit tested

**Peregrine client:**
- `verify_local()` tested with pre-signed test JWT using test keypair
- `activate()` / `refresh()` tested with `httpx` mocks
- `effective_tier()` tested across all states: valid, expired, grace, revoked, missing

**Integration smoke test:**
```bash
docker compose up -d
# create test key via admin API
# call /v1/activate with test key
# verify JWT signature with public key
# verify /v1/refresh extends expiry
```

---

## Decisions Log

| Decision | Rationale |
|----------|-----------|
| RS256 over HS256 | Public key embeddable in client; private key never leaves server |
| SQLite over Postgres | Matches Peregrine's SQLite-first philosophy; trivially backupable |
| 30-day JWT lifetime | Standard SaaS pattern; invisible to users in normal operation |
| 7-day grace period | Covers travel, network outages, server maintenance |
| Flags v1: capture only | No volume to justify review UI yet; add in v2 |
| No payment integration | Manual issuance until customer volume justifies automation |
| Multi-product schema | Adding a column now vs migrating a live DB later |
| Separate repo | License server is infrastructure, not part of Peregrine's BSL scope |
