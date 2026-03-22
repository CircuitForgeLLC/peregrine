# UI Switcher — Design Spec
**Date:** 2026-03-22
**Status:** Approved
**Scope:** Peregrine v0.7.0

---

## Overview

Add a Reddit-style UI switcher that lets paid-tier users opt into the new Vue 3 SPA while the Streamlit UI remains the default. The Vue SPA ships merged into `main` (gated behind a paid-tier feature flag), served by a new nginx Docker service alongside Streamlit. The demo instance gets both the UI switcher (open to all visitors) and a simulated tier switcher so demo visitors can explore all feature tiers.

---

## Decisions

| Question | Decision |
|---|---|
| Switcher placement | Banner (once per session, dismissible) + Settings → System toggle |
| Vue SPA serving | New `web` Docker service (nginx) in all three compose files |
| Preference persistence | JS cookie (`prgn_ui`) as Caddy routing signal; `user.yaml` as durability layer |
| Switching mechanism | JS cookie injection via `st.components.v1.html()` (Streamlit→Vue); client-side JS (Vue→Streamlit) |
| Tier gate | `vue_ui_beta: "paid"` in `tiers.py`; bypassed in `DEMO_MODE` |
| Branch strategy | Merge `feature-vue-spa` → `main` now; future Vue work uses `feature/vue-*` → `main` PRs |
| Demo UI switcher | Open to all demo visitors (no tier gate) |
| Demo tier switcher | Slim full-width toolbar above nav; cookie-based persistence (`prgn_demo_tier`) |
| Banner dismissal | Uses existing `dismissed_banners` list in `user.yaml` (key: `ui_switcher_beta`) |

---

## Port Reference

| Compose file | Host port | Purpose |
|---|---|---|
| `compose.yml` | 8501 | Personal dev instance |
| `compose.demo.yml` | 8504 | Demo (`demo.circuitforge.tech`) |
| `compose.cloud.yml` | 8505 | Cloud managed (`menagerie.circuitforge.tech`) |
| `compose.yml` (web) | 8506 | Vue SPA — dev |
| `compose.demo.yml` (web) | 8507 | Vue SPA — demo |
| `compose.cloud.yml` (web) | 8508 | Vue SPA — cloud |

---

## Architecture

Six additive components — nothing removed from the existing stack.

### 1. `web` Docker service

A minimal nginx container serving the Vue SPA `dist/` build. Added to `compose.yml`, `compose.demo.yml`, and `compose.cloud.yml`.

- `docker/web/Dockerfile` — `FROM nginx:alpine`, copies `nginx.conf`, copies `web/dist/` into `/usr/share/nginx/html/`
- `docker/web/nginx.conf` — standard SPA config with `try_files $uri /index.html` fallback
- Build step is image-baked (not a bind-mount): `docker compose build web` runs `vite build` in `web/` via a multi-stage Dockerfile, then copies the resulting `dist/` into the nginx image. This ensures a fresh clone + `manage.sh start` works without a separate manual build step.
- `manage.sh` updated: `build` target runs `docker compose build web app` so both are built together.

### 2. Caddy cookie routing

Caddy inspects the `prgn_ui` cookie on all Peregrine requests. Two vhost blocks require changes:

**`menagerie.circuitforge.tech` (cloud, port 8505/8508):**
```
handle /peregrine* {
    @no_session not header Cookie *cf_session*
    redir @no_session https://circuitforge.tech/login?next={uri} 302

    @vue_ui header Cookie *prgn_ui=vue*
    handle @vue_ui {
        reverse_proxy http://host.docker.internal:8508
    }
    handle {
        reverse_proxy http://host.docker.internal:8505
    }
}
```

**`demo.circuitforge.tech` (demo, port 8504/8507):**
```
handle /peregrine* {
    @vue_ui header Cookie *prgn_ui=vue*
    handle @vue_ui {
        reverse_proxy http://host.docker.internal:8507
    }
    handle {
        reverse_proxy http://host.docker.internal:8504
    }
}
```

Error handling: a `handle_errors { ... }` block on each vhost catches 502 from the Vue SPA service, redirects to the Streamlit upstream with `?ui_fallback=1`, and includes a `Set-Cookie: prgn_ui=streamlit; Path=/` response header to clear the routing cookie.

### 3. Streamlit switch mechanism

New module `app/components/ui_switcher.py`:

- `sync_ui_cookie()` — called **in the render pass** (after `pg.run()` in `app.py`), not inside the cached startup hook. Reads `user.yaml.ui_preference`; injects JS to set/clear `prgn_ui` cookie. Cookie/user.yaml conflict: **cookie wins** — if `prgn_ui` cookie is already present, writes user.yaml to match before re-injecting. If `DEMO_MODE`, skips tier check. If not `DEMO_MODE` and not `can_use("vue_ui_beta")`, resets preference to `streamlit` and clears cookie.
- `switch_ui(to: str)` — writes `user.yaml.ui_preference`, calls `sync_ui_cookie()`, then `st.rerun()`.
- `render_banner()` — dismissible banner shown to eligible users when `ui_switcher_beta` is not in `user_profile.dismissed_banners`. On dismiss: appends `ui_switcher_beta` to `dismissed_banners`, saves `user.yaml`. On "Try it": calls `switch_ui("vue")`. Also detects `?ui_fallback=1` in `st.query_params` and shows a toast ("New UI temporarily unavailable — switched back to Classic") then clears the param.
- `render_settings_toggle()` — toggle in Settings → System → Deployment expander. Calls `switch_ui()` on change.

### 4. Vue SPA switch-back

New `web/src/components/ClassicUIButton.vue`:

```js
function switchToClassic() {
  document.cookie = 'prgn_ui=streamlit; path=/';
  window.location.reload();
}
```

No backend call needed. On next Streamlit load, `sync_ui_cookie()` sees `prgn_ui=streamlit`, writes user.yaml to match.

### 5. Tier gate

`app/wizard/tiers.py`:

```python
FEATURES: dict[str, str] = {
    ...
    "vue_ui_beta": "paid",   # add this
}
```

Not in `BYOK_UNLOCKABLE` — the Vue UI has no LLM dependency; the gate is purely about beta access management.

`can_use()` signature change — keyword-only argument with a safe default:

```python
def can_use(
    tier: str,
    feature: str,
    has_byok: bool = False,
    *,
    demo_tier: str | None = None,
) -> bool:
    effective_tier = demo_tier if (demo_tier and DEMO_MODE_FLAG) else tier
    ...
```

Argument order preserved from the existing implementation (`tier` first, `feature` second) — no existing call sites need updating. `DEMO_MODE_FLAG` is read from the environment, not from `st.session_state`, so this function is safe to call from background task threads and tests. `st.session_state.simulated_tier` is only read by the **caller** (`render_banner()`, `render_settings_toggle()`, page feature gates) which then passes it as `demo_tier=`.

### 6. Demo toolbar

New module `app/components/demo_toolbar.py`:

- `render_demo_toolbar()` — slim full-width bar rendered at the top of `app.py`'s render pass when `DEMO_MODE=true`. Shows `🎭 Demo mode · Free · Paid · Premium` pills with the active tier highlighted.
- `set_simulated_tier(tier: str)` — injects JS to set `prgn_demo_tier` cookie, updates `st.session_state.simulated_tier`, calls `st.rerun()`.
- Initialization: on each page load in demo mode, `app.py` reads `prgn_demo_tier` from `st.query_params` or the cookie (via a JS→hidden Streamlit input bridge, same pattern used by existing components) and sets `st.session_state.simulated_tier`. **Default if not set: `paid`** — shows the full feature set immediately on first demo load.

`useFeatureFlag.ts` (Vue SPA, `web/src/composables/`) is **demo-toolbar only** — it reads `prgn_demo_tier` cookie for the visual indicator in the Vue SPA's ClassicUIButton area. It is **not** an authoritative feature gate. All real feature gating in the Vue SPA will use a future `/api/features` endpoint (tracked under issue #8). This composable exists solely so the demo toolbar's simulated tier is visually consistent when the user has switched to the Vue SPA.

---

## File Changes

### New files
| File | Purpose |
|---|---|
| `app/components/ui_switcher.py` | `sync_ui_cookie`, `switch_ui`, `render_banner`, `render_settings_toggle` |
| `app/components/demo_toolbar.py` | `render_demo_toolbar`, `set_simulated_tier` |
| `docker/web/Dockerfile` | Multi-stage: `node` build stage → `nginx:alpine` serve stage |
| `docker/web/nginx.conf` | SPA-aware nginx config |
| `web/` | Vue SPA source (merged from `feature-vue-spa` worktree) |
| `web/src/components/ClassicUIButton.vue` | Switch-back button for Vue SPA nav |
| `web/src/composables/useFeatureFlag.ts` | Demo toolbar tier display (not a production gate) |

### Modified files
| File | Change |
|---|---|
| `app/app.py` | Call `sync_ui_cookie()` + `render_demo_toolbar()` + `render_banner()` in render pass |
| `app/wizard/tiers.py` | Add `vue_ui_beta: "paid"` to `FEATURES`; add `demo_tier` keyword arg to `can_use()` |
| `app/pages/2_Settings.py` | Add `render_settings_toggle()` in System → Deployment expander |
| `config/user.yaml.example` | Add `ui_preference: streamlit` |
| `scripts/user_profile.py` | Add `ui_preference` field to schema (default: `streamlit`) |
| `compose.yml` | Add `web` service (port 8506) |
| `compose.demo.yml` | Add `web` service (port 8507) |
| `compose.cloud.yml` | Add `web` service (port 8508) |
| `manage.sh` | `build` target includes `web` service |
| `/devl/caddy-proxy/Caddyfile` | Cookie routing in `menagerie.circuitforge.tech` + `demo.circuitforge.tech` peregrine blocks |

---

## Data Flow

### Streamlit → Vue
```
User clicks "Try it" banner or Settings toggle
  → switch_ui(to="vue")
      → write user.yaml: ui_preference: vue
      → sync_ui_cookie(): inject JS → document.cookie = 'prgn_ui=vue; path=/'
      → st.rerun()
  → browser reloads → Caddy sees prgn_ui=vue → :8508/:8507 (Vue SPA)
```

### Vue → Streamlit
```
User clicks "Classic UI" in Vue nav
  → document.cookie = 'prgn_ui=streamlit; path=/'
  → window.location.reload()
  → Caddy sees prgn_ui=streamlit → :8505/:8504 (Streamlit)
  → app.py render pass: sync_ui_cookie() sees cookie=streamlit
      → writes user.yaml: ui_preference: streamlit
```

### Demo tier switch
```
User clicks tier pill in demo toolbar
  → set_simulated_tier("paid")
      → inject JS → document.cookie = 'prgn_demo_tier=paid; path=/'
      → st.session_state.simulated_tier = "paid"
      → st.rerun()
  → render_banner() / page feature gates call can_use(..., demo_tier=st.session_state.simulated_tier)
```

### Cookie cleared (durability)
```
Browser cookies cleared
  → next Streamlit load: sync_ui_cookie() reads user.yaml: ui_preference: vue
      → re-injects prgn_ui=vue cookie
      → next navigation: Caddy routes to Vue SPA
```

---

## Error Handling

| Scenario | Handling |
|---|---|
| Vue SPA service down (502) | Caddy `handle_errors` sets `Set-Cookie: prgn_ui=streamlit` + redirects to Streamlit with `?ui_fallback=1` |
| `?ui_fallback=1` detected | `render_banner()` shows toast "New UI temporarily unavailable — switched back to Classic"; calls `switch_ui("streamlit")` |
| user.yaml missing/malformed | `sync_ui_cookie()` try/except defaults to `streamlit`; no crash |
| Cookie/user.yaml conflict | Cookie wins — `sync_ui_cookie()` writes user.yaml to match cookie if present |
| Tier downgrade with vue cookie | `sync_ui_cookie()` detects `not can_use("vue_ui_beta")` → clears cookie + resets user.yaml |
| Demo toolbar in non-demo mode | `render_demo_toolbar()` only called when `DEMO_MODE=true`; `prgn_demo_tier` ignored by `can_use()` outside demo |
| `can_use()` called from background thread | `demo_tier` param defaults to `None`; `DEMO_MODE_FLAG` is env-only — no `st.session_state` access in the function body; thread-safe |
| First demo load (no cookie yet) | `st.session_state.simulated_tier` initialized to `"paid"` if `prgn_demo_tier` cookie absent |

---

## Testing

- **Unit**: `sync_ui_cookie()` with all three conflict cases; `can_use("vue_ui_beta")` for free/paid/premium/demo tiers; `set_simulated_tier()` state transitions; `can_use()` called with `demo_tier=` from a non-Streamlit context (no `RuntimeError`)
- **Integration**: Caddy routing with mocked cookie headers (both directions); 502 fallback redirect + cookie clear chain
- **E2E**: Streamlit→Vue switch → verify served from Vue SPA port; Vue→Streamlit → verify Streamlit port; demo tier pill → verify feature gate state changes; cookie persistence across Streamlit restart; fresh clone `./manage.sh start` builds and serves Vue SPA correctly

---

## Out of Scope

- Vue SPA feature parity with Streamlit (tracked under issue #8)
- Removing the Streamlit UI (v1 GA milestone)
- `old.peregrine.circuitforge.tech` subdomain alias (not needed — cookie approach is sufficient)
- Authoritative Vue-side feature gating via `/api/features` endpoint (post-parity, issue #8)
- Fine-tuned model or integrations gating in the Vue SPA (future work)
