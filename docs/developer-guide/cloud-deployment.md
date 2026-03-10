# Cloud Deployment

This page covers operating the Peregrine cloud managed instance at `menagerie.circuitforge.tech/peregrine`.

---

## Architecture Overview

```
Browser → Caddy (bastion) → host:8505 → peregrine-cloud container
                                              │
                    ┌─────────────────────────┼──────────────────────────┐
                    │                         │                          │
              cloud_session.py        /devl/menagerie-data/       Postgres :5433
              (session routing)       <user-id>/peregrine/        (platform DB)
                                      staging.db (SQLCipher)
```

Caddy injects the Directus session cookie as `X-CF-Session`. `cloud_session.py` validates the JWT, derives the per-user db path and SQLCipher key, and injects both into `st.session_state`. All downstream DB calls are transparent — the app never knows it's multi-tenant.

---

## Compose File

```bash
# Start
docker compose -f compose.cloud.yml --project-name peregrine-cloud --env-file .env up -d

# Stop
docker compose -f compose.cloud.yml --project-name peregrine-cloud down

# Logs
docker compose -f compose.cloud.yml --project-name peregrine-cloud logs app -f

# Rebuild after code changes
docker compose -f compose.cloud.yml --project-name peregrine-cloud build app
docker compose -f compose.cloud.yml --project-name peregrine-cloud up -d
```

---

## Required Environment Variables

These must be present in `.env` (gitignored) before starting the cloud stack:

| Variable | Description | Where to find |
|----------|-------------|---------------|
| `CLOUD_MODE` | Must be `true` | Hardcoded in compose.cloud.yml |
| `CLOUD_DATA_ROOT` | Host path for per-user data trees | `/devl/menagerie-data` |
| `DIRECTUS_JWT_SECRET` | Directus signing secret — validates session JWTs | `website/.env` → `DIRECTUS_SECRET` |
| `CF_SERVER_SECRET` | Server secret for SQLCipher key derivation | Generate: `openssl rand -base64 32 \| tr -d '/=+' \| cut -c1-32` |
| `PLATFORM_DB_URL` | Postgres connection string for platform DB | `postgresql://cf_platform:<pass>@host.docker.internal:5433/circuitforge_platform` |

!!! warning "SECRET ROTATION"
    `CF_SERVER_SECRET` is used to derive all per-user SQLCipher keys via `HMAC(secret, user_id)`. Rotating this secret renders all existing user databases unreadable. Do not rotate it without a migration plan.

---

## Data Root

User data lives at `/devl/menagerie-data/` on the host, bind-mounted into the container:

```
/devl/menagerie-data/
  <directus-user-uuid>/
    peregrine/
      staging.db        ← SQLCipher-encrypted (AES-256)
      config/           ← llm.yaml, server.yaml, user.yaml, etc.
      data/             ← documents, exports, attachments
```

The directory is created automatically on first login. The SQLCipher key for each user is derived deterministically: `HMAC-SHA256(CF_SERVER_SECRET, user_id)`.

### GDPR / Data deletion

To fully delete a user's data:

```bash
# Remove all content data
rm -rf /devl/menagerie-data/<user-id>/

# Remove platform DB rows (cascades)
docker exec cf-platform-db psql -U cf_platform -d circuitforge_platform \
  -c "DELETE FROM subscriptions WHERE user_id = '<user-id>';"
```

---

## Platform Database

The Postgres platform DB runs as `cf-platform-db` in the website compose stack (port 5433 on host).

```bash
# Connect
docker exec cf-platform-db psql -U cf_platform -d circuitforge_platform

# Check tables
\dt

# View telemetry consent for a user
SELECT * FROM telemetry_consent WHERE user_id = '<uuid>';

# View recent usage events
SELECT user_id, event_type, occurred_at FROM usage_events
  ORDER BY occurred_at DESC LIMIT 20;
```

The schema is initialised on container start from `platform-db/init.sql` in the website repo.

---

## Telemetry

`app/telemetry.py` is the **only** entry point to `usage_events`. Never write to that table directly.

```python
from app.telemetry import log_usage_event

# Fires in cloud mode only; no-op locally
log_usage_event(user_id, "peregrine", "cover_letter_generated", {"words": 350})
```

Events are blocked if:

1. `telemetry_consent.all_disabled = true` (hard kill switch, overrides all)
2. `telemetry_consent.usage_events_enabled = false`

The user controls both from Settings → 🔒 Privacy.

---

## Backup / Restore (Cloud Mode)

The Settings → 💾 Data tab handles backup/restore transparently. In cloud mode:

- **Export:** the SQLCipher-encrypted DB is decrypted before zipping — the downloaded `.zip` is a portable plain SQLite archive, compatible with any local Docker install.
- **Import:** a plain SQLite backup is re-encrypted with the user's key on restore.

The user's `base_dir` in cloud mode is `get_db_path().parent` (`/devl/menagerie-data/<user-id>/peregrine/`), not the app root.

---

## Routing (Caddy)

`menagerie.circuitforge.tech` in `/devl/caddy-proxy/Caddyfile`:

```caddy
menagerie.circuitforge.tech {
    encode gzip zstd
    handle /peregrine* {
        reverse_proxy http://host.docker.internal:8505 {
            header_up X-CF-Session {header.Cookie}
        }
    }
    handle {
        respond "This app is not yet available in the managed cloud — check back soon." 503
    }
    log {
        output file /data/logs/menagerie.circuitforge.tech.log
        format json
    }
}
```

`header_up X-CF-Session {header.Cookie}` passes the full cookie header so `cloud_session.py` can extract the Directus session token.

!!! note "Caddy inode gotcha"
    After editing the Caddyfile, run `docker restart caddy-proxy` — not `caddy reload`. The Edit tool creates a new inode; Docker bind mounts pin to the original inode and `caddy reload` re-reads the stale one.

---

## Demo Instance

The public demo at `demo.circuitforge.tech/peregrine` runs separately:

```bash
# Start demo
docker compose -f compose.demo.yml --project-name peregrine-demo up -d

# Rebuild after code changes
docker compose -f compose.demo.yml --project-name peregrine-demo build app
docker compose -f compose.demo.yml --project-name peregrine-demo up -d
```

`DEMO_MODE=true` blocks all LLM inference calls at `llm_router.py`. Discovery, job enrichment, and the UI work normally. Demo data lives in `demo/config/` and `demo/data/` — isolated from personal data.

---

## Adding a New App to the Cloud

To onboard a new menagerie app (e.g. `falcon`) to the cloud:

1. Add `resolve_session("falcon")` at the top of each page (calls `cloud_session.py` with the app slug)
2. Replace `DEFAULT_DB` references with `get_db_path()`
3. Add `app/telemetry.py` import and `log_usage_event()` calls at key action points
4. Create `compose.cloud.yml` following the Peregrine pattern (port, `CLOUD_MODE=true`, data mount)
5. Add a Caddy `handle /falcon*` block in `menagerie.circuitforge.tech`, routing to the new port
6. `cloud_session.py` automatically creates `<data_root>/<user-id>/falcon/` on first login
