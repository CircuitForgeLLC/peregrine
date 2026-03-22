# UI Switcher Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Reddit-style UI switcher letting paid-tier users opt into the Vue 3 SPA, plus a demo tier toolbar for exploring feature tiers without a real license.

**Architecture:** A `prgn_ui` cookie acts as Caddy's routing signal — `vue` routes to a new nginx Docker service serving the Vue SPA, absent/`streamlit` routes to Streamlit. `user.yaml` persists the preference across browser clears. The Vue SPA switches back via a `?prgn_switch=streamlit` query param (Streamlit can't read HTTP cookies server-side; the param is the bridge). The demo toolbar uses the same cookie-injection pattern to simulate tiers via `st.session_state.simulated_tier`.

**Tech Stack:** Python 3.11, Streamlit, `st.components.v1.html()` for JS cookie injection, Vue 3 + Vite, nginx:alpine, Docker Compose, Caddy

**Spec:** `docs/superpowers/specs/2026-03-22-ui-switcher-design.md`

> **Implementation note — switch-back mechanism:** The spec's Vue→Streamlit flow assumed Streamlit could read the `prgn_ui` cookie server-side to detect the switch and update `user.yaml`. Streamlit cannot read HTTP cookies from Python. This plan uses `?prgn_switch=streamlit` as a query param bridge instead: `ClassicUIButton.vue` sets the cookie AND appends the param; `sync_ui_cookie()` reads `st.query_params` to detect it and update `user.yaml`. This supersedes the "cookie wins" description in spec §3/§4.

**Test command:** `/devl/miniconda3/envs/job-seeker/bin/pytest tests/ -v`
**Vue test command:** `cd web && npm run test`

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `app/wizard/tiers.py` | Modify | Add `vue_ui_beta` feature key; add `demo_tier` kwarg to `can_use()` |
| `tests/test_wizard_tiers.py` | Modify | Tests for new feature key and demo_tier behaviour |
| `scripts/user_profile.py` | Modify | Add `ui_preference` field (default: `"streamlit"`) |
| `tests/test_user_profile.py` | Modify | Tests for `ui_preference` round-trip |
| `app/components/ui_switcher.py` | Create | `sync_ui_cookie`, `switch_ui`, `render_banner`, `render_settings_toggle` |
| `tests/test_ui_switcher.py` | Create | Unit tests for switcher logic (mocked st + UserProfile) |
| `app/components/demo_toolbar.py` | Create | `render_demo_toolbar`, `set_simulated_tier` |
| `tests/test_demo_toolbar.py` | Create | Unit tests for toolbar logic |
| `app/app.py` | Modify | Wire in `sync_ui_cookie`, `render_demo_toolbar`, `render_banner` |
| `app/pages/2_Settings.py` | Modify | Add `render_settings_toggle` in Deployment expander |
| `web/src/components/ClassicUIButton.vue` | Create | Switch-back button (sets cookie + appends `?prgn_switch=streamlit`) |
| `web/src/composables/useFeatureFlag.ts` | Create | Demo-only: reads `prgn_demo_tier` cookie for display |
| `web/src/components/AppNav.vue` | Modify | Mount `ClassicUIButton` in nav |
| `docker/web/Dockerfile` | Create | Multi-stage: node build → nginx:alpine serve |
| `docker/web/nginx.conf` | Create | SPA-aware nginx config with `try_files` fallback |
| `compose.yml` | Modify | Add `web` service (port 8506) |
| `compose.demo.yml` | Modify | Add `web` service (port 8507) |
| `compose.cloud.yml` | Modify | Add `web` service (port 8508) |
| `manage.sh` | Modify | Include `web` in `build` target |
| `/devl/caddy-proxy/Caddyfile` | Modify | Add `prgn_ui` cookie matchers for both peregrine vhosts |

---

## Task 1: Extend `tiers.py` — add `vue_ui_beta` and `demo_tier`

**Files:**
- Modify: `app/wizard/tiers.py:50` (FEATURES dict), `app/wizard/tiers.py:104` (can_use signature)
- Modify: `tests/test_wizard_tiers.py`

- [ ] **Step 1.1: Write failing tests**

Add to `tests/test_wizard_tiers.py`:

```python
def test_vue_ui_beta_free_tier():
    assert can_use("free", "vue_ui_beta") is False

def test_vue_ui_beta_paid_tier():
    assert can_use("paid", "vue_ui_beta") is True

def test_vue_ui_beta_premium_tier():
    assert can_use("premium", "vue_ui_beta") is True

def test_can_use_demo_tier_overrides_real_tier():
    # demo_tier kwarg substitutes for the real tier when provided
    assert can_use("free", "company_research", demo_tier="paid") is True

def test_can_use_demo_tier_free_restricts():
    assert can_use("paid", "model_fine_tuning", demo_tier="free") is False

def test_can_use_demo_tier_none_falls_back_to_real():
    # demo_tier=None means no override — real tier is used
    assert can_use("paid", "company_research", demo_tier=None) is True

def test_can_use_demo_tier_does_not_affect_non_demo():
    # demo_tier is only applied when DEMO_MODE_FLAG is set;
    # in tests DEMO_MODE_FLAG is False by default, so demo_tier is ignored
    # (this tests thread-safety: no st.session_state access inside can_use)
    import os
    os.environ.pop("DEMO_MODE", None)
    assert can_use("free", "company_research", demo_tier="paid") is False
```

- [ ] **Step 1.2: Run to confirm failures**

```bash
/devl/miniconda3/envs/job-seeker/bin/pytest tests/test_wizard_tiers.py -v -k "vue_ui_beta or demo_tier"
```

Expected: 7 failures (`can_use` doesn't accept `demo_tier` yet, `vue_ui_beta` not in FEATURES)

- [ ] **Step 1.3: Implement changes in `tiers.py`**

Add to `FEATURES` dict (after the existing entries):
```python
    # Beta UI access — stays gated (access management, not compute)
    "vue_ui_beta":                  "paid",
```

Add module-level constant after the `BYOK_UNLOCKABLE` block:
```python
import os as _os
_DEMO_MODE = _os.environ.get("DEMO_MODE", "").lower() in ("1", "true", "yes")
```

Update `can_use()` signature (preserve existing positional order, add keyword-only arg):
```python
def can_use(
    tier: str,
    feature: str,
    has_byok: bool = False,
    *,
    demo_tier: str | None = None,
) -> bool:
    """Return True if the given tier has access to the feature.

    has_byok: pass has_configured_llm() to unlock BYOK_UNLOCKABLE features.
    demo_tier: when set AND _DEMO_MODE is True, substitutes for `tier`.
               Read from st.session_state by the *caller*, not here — keeps
               this function thread-safe for background tasks and tests.
    """
    effective_tier = demo_tier if (demo_tier is not None and _DEMO_MODE) else tier
    required = FEATURES.get(feature)
    if required is None:
        return True
    if has_byok and feature in BYOK_UNLOCKABLE:
        return True
    try:
        return TIERS.index(effective_tier) >= TIERS.index(required)
    except ValueError:
        return False
```

- [ ] **Step 1.4: Run tests — expect all pass**

```bash
/devl/miniconda3/envs/job-seeker/bin/pytest tests/test_wizard_tiers.py -v
```

Expected: all existing tests still pass + 7 new tests pass (the `demo_tier` env test is context-sensitive — if DEMO_MODE is unset, `demo_tier` override is skipped)

- [ ] **Step 1.5: Commit**

```bash
git add app/wizard/tiers.py tests/test_wizard_tiers.py
git commit -m "feat(tiers): add vue_ui_beta feature key and demo_tier kwarg to can_use"
```

---

## Task 2: Extend `user_profile.py` — add `ui_preference`

**Files:**
- Modify: `scripts/user_profile.py` (lines ~12–80)
- Modify: `tests/test_user_profile.py`
- Modify: `config/user.yaml.example`

- [ ] **Step 2.1: Write failing tests**

Add to `tests/test_user_profile.py`:

```python
def test_ui_preference_default(tmp_path):
    """Fresh profile defaults to streamlit."""
    p = tmp_path / "user.yaml"
    p.write_text("name: Test User\n")
    profile = UserProfile(p)
    assert profile.ui_preference == "streamlit"

def test_ui_preference_vue(tmp_path):
    """Saved vue preference loads correctly."""
    p = tmp_path / "user.yaml"
    p.write_text("name: Test\nui_preference: vue\n")
    profile = UserProfile(p)
    assert profile.ui_preference == "vue"

def test_ui_preference_roundtrip(tmp_path):
    """Saving ui_preference: vue persists and reloads."""
    p = tmp_path / "user.yaml"
    p.write_text("name: Test\n")
    profile = UserProfile(p)
    profile.ui_preference = "vue"
    profile.save()
    reloaded = UserProfile(p)
    assert reloaded.ui_preference == "vue"

def test_ui_preference_invalid_falls_back(tmp_path):
    """Unknown value falls back to streamlit."""
    p = tmp_path / "user.yaml"
    p.write_text("name: Test\nui_preference: newui\n")
    profile = UserProfile(p)
    assert profile.ui_preference == "streamlit"
```

- [ ] **Step 2.2: Run to confirm failures**

```bash
/devl/miniconda3/envs/job-seeker/bin/pytest tests/test_user_profile.py -v -k "ui_preference"
```

Expected: 4 failures (`UserProfile` has no `ui_preference` attribute)

- [ ] **Step 2.3: Implement in `user_profile.py`**

In `_DEFAULTS` dict, add:
```python
    "ui_preference": "streamlit",
```

In `UserProfile.__init__()`, after the `dismissed_banners` line:
```python
        raw_pref = data.get("ui_preference", "streamlit")
        self.ui_preference: str = raw_pref if raw_pref in ("streamlit", "vue") else "streamlit"
```

In `UserProfile.save()` (or wherever other fields are serialised to yaml), add `ui_preference` to the output dict:
```python
        "ui_preference": self.ui_preference,
```

- [ ] **Step 2.4: Run tests**

```bash
/devl/miniconda3/envs/job-seeker/bin/pytest tests/test_user_profile.py -v
```

Expected: all pass

- [ ] **Step 2.5: Update `config/user.yaml.example`**

Add after existing fields:
```yaml
# UI preference — "streamlit" (default) or "vue" (Beta: Paid tier)
ui_preference: streamlit
```

- [ ] **Step 2.6: Commit**

```bash
git add scripts/user_profile.py tests/test_user_profile.py config/user.yaml.example
git commit -m "feat(profile): add ui_preference field (streamlit|vue, default: streamlit)"
```

---

## Task 3: Create `app/components/ui_switcher.py`

**Files:**
- Create: `app/components/ui_switcher.py`
- Create: `tests/test_ui_switcher.py`

**Key implementation note:** Streamlit cannot read HTTP cookies from Python — only JavaScript running in the browser can. The `sync_ui_cookie()` function injects JS that sets the cookie. For the Vue→Streamlit switch-back, the Vue SPA appends `?prgn_switch=streamlit` to the redirect URL; `sync_ui_cookie()` detects this param via `st.query_params` and treats it as an override signal.

- [ ] **Step 3.1: Write failing tests**

Create `tests/test_ui_switcher.py`:

```python
"""Tests for app/components/ui_switcher.py.

Streamlit is not running during tests — mock all st.* calls.
"""
import sys
from pathlib import Path
import pytest
import yaml

sys.path.insert(0, str(Path(__file__).parent.parent))


@pytest.fixture
def profile_yaml(tmp_path):
    data = {"name": "Test", "ui_preference": "streamlit", "wizard_complete": True}
    p = tmp_path / "user.yaml"
    p.write_text(yaml.dump(data))
    return p


def test_sync_cookie_injects_vue_js(profile_yaml, monkeypatch):
    """When ui_preference is vue, JS sets prgn_ui=vue."""
    import yaml as _yaml
    profile_yaml.write_text(_yaml.dump({"name": "T", "ui_preference": "vue"}))

    injected = []
    monkeypatch.setattr("streamlit.components.v1.html", lambda html, height=0: injected.append(html))
    monkeypatch.setattr("streamlit.query_params", {}, raising=False)

    from app.components.ui_switcher import sync_ui_cookie
    sync_ui_cookie(profile_yaml, tier="paid")

    assert any("prgn_ui=vue" in s for s in injected)


def test_sync_cookie_injects_streamlit_js(profile_yaml, monkeypatch):
    """When ui_preference is streamlit, JS sets prgn_ui=streamlit."""
    injected = []
    monkeypatch.setattr("streamlit.components.v1.html", lambda html, height=0: injected.append(html))
    monkeypatch.setattr("streamlit.query_params", {}, raising=False)

    from app.components.ui_switcher import sync_ui_cookie
    sync_ui_cookie(profile_yaml, tier="paid")

    assert any("prgn_ui=streamlit" in s for s in injected)


def test_sync_cookie_prgn_switch_param_overrides_yaml(profile_yaml, monkeypatch):
    """?prgn_switch=streamlit in query params resets ui_preference to streamlit."""
    import yaml as _yaml
    profile_yaml.write_text(_yaml.dump({"name": "T", "ui_preference": "vue"}))

    injected = []
    monkeypatch.setattr("streamlit.components.v1.html", lambda html, height=0: injected.append(html))
    monkeypatch.setattr("streamlit.query_params", {"prgn_switch": "streamlit"}, raising=False)

    from importlib import reload
    import app.components.ui_switcher as m
    reload(m)

    m.sync_ui_cookie(profile_yaml, tier="paid")

    # user.yaml should now say streamlit
    saved = _yaml.safe_load(profile_yaml.read_text())
    assert saved["ui_preference"] == "streamlit"
    # JS should set cookie to streamlit
    assert any("prgn_ui=streamlit" in s for s in injected)


def test_sync_cookie_downgrades_tier_resets_to_streamlit(profile_yaml, monkeypatch):
    """Free-tier user with vue preference gets reset to streamlit."""
    import yaml as _yaml
    profile_yaml.write_text(_yaml.dump({"name": "T", "ui_preference": "vue"}))

    injected = []
    monkeypatch.setattr("streamlit.components.v1.html", lambda html, height=0: injected.append(html))
    monkeypatch.setattr("streamlit.query_params", {}, raising=False)

    from importlib import reload
    import app.components.ui_switcher as m
    reload(m)

    m.sync_ui_cookie(profile_yaml, tier="free")

    saved = _yaml.safe_load(profile_yaml.read_text())
    assert saved["ui_preference"] == "streamlit"
    assert any("prgn_ui=streamlit" in s for s in injected)


def test_switch_ui_writes_yaml_and_calls_sync(profile_yaml, monkeypatch):
    """switch_ui(to='vue') writes user.yaml and calls sync."""
    import yaml as _yaml
    synced = []
    monkeypatch.setattr("streamlit.components.v1.html", lambda html, height=0: synced.append(html))
    monkeypatch.setattr("streamlit.query_params", {}, raising=False)
    monkeypatch.setattr("streamlit.rerun", lambda: None)

    from importlib import reload
    import app.components.ui_switcher as m
    reload(m)

    m.switch_ui(profile_yaml, to="vue", tier="paid")

    saved = _yaml.safe_load(profile_yaml.read_text())
    assert saved["ui_preference"] == "vue"
    assert any("prgn_ui=vue" in s for s in synced)
```

- [ ] **Step 3.2: Run to confirm failures**

```bash
/devl/miniconda3/envs/job-seeker/bin/pytest tests/test_ui_switcher.py -v
```

Expected: ImportError — module doesn't exist yet

- [ ] **Step 3.3: Create `app/components/ui_switcher.py`**

```python
"""UI switcher component for Peregrine.

Manages the prgn_ui cookie (Caddy routing signal) and user.yaml
ui_preference (durability across browser clears).

Cookie mechanics
----------------
Streamlit cannot read HTTP cookies server-side. Instead:
- sync_ui_cookie() injects a JS snippet that sets document.cookie.
- Vue SPA switch-back appends ?prgn_switch=streamlit to the redirect URL.
  sync_ui_cookie() reads this param via st.query_params and uses it as
  an override signal, then writes user.yaml to match.

Call sync_ui_cookie() in the app.py render pass (after pg.run()).
"""
from __future__ import annotations

import os
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

from scripts.user_profile import UserProfile
from app.wizard.tiers import can_use

_DEMO_MODE = os.environ.get("DEMO_MODE", "").lower() in ("1", "true", "yes")

_COOKIE_JS = """
<script>
(function() {{
  document.cookie = 'prgn_ui={value}; path=/; SameSite=Lax';
}})();
</script>
"""


def _set_cookie_js(value: str) -> None:
    components.html(_COOKIE_JS.format(value=value), height=0)


def sync_ui_cookie(yaml_path: Path, tier: str) -> None:
    """Sync the prgn_ui cookie to match user.yaml ui_preference.

    Also handles:
    - ?prgn_switch=<value> param (Vue SPA switch-back signal): overrides yaml,
      writes yaml to match, clears the param.
    - Tier downgrade: resets vue preference to streamlit for ineligible users.
    - ?ui_fallback=1 param: shows a toast (Vue SPA was unreachable).
    """
    # ── ?ui_fallback=1 — Vue SPA was down, Caddy bounced us back ──────────────
    if st.query_params.get("ui_fallback"):
        st.toast("⚠️ New UI temporarily unavailable — switched back to Classic", icon="⚠️")
        st.query_params.pop("ui_fallback", None)

    # ── ?prgn_switch param — Vue SPA sent us here to switch back ──────────────
    switch_param = st.query_params.get("prgn_switch")
    if switch_param in ("streamlit", "vue"):
        try:
            profile = UserProfile(yaml_path)
            profile.ui_preference = switch_param
            profile.save()
        except Exception:
            pass
        st.query_params.pop("prgn_switch", None)
        _set_cookie_js(switch_param)
        return

    # ── Normal path: read yaml, enforce tier, inject cookie ───────────────────
    try:
        profile = UserProfile(yaml_path)
        pref = profile.ui_preference
    except Exception:
        pref = "streamlit"

    # Tier downgrade protection (skip in demo — demo bypasses tier gate)
    if pref == "vue" and not _DEMO_MODE and not can_use(tier, "vue_ui_beta"):
        try:
            profile = UserProfile(yaml_path)
            profile.ui_preference = "streamlit"
            profile.save()
        except Exception:
            pass
        pref = "streamlit"

    _set_cookie_js(pref)


def switch_ui(yaml_path: Path, to: str, tier: str) -> None:
    """Write user.yaml, sync cookie, rerun.

    to: "vue" | "streamlit"
    """
    if to not in ("vue", "streamlit"):
        return
    try:
        profile = UserProfile(yaml_path)
        profile.ui_preference = to
        profile.save()
    except Exception:
        pass
    sync_ui_cookie(yaml_path, tier=tier)
    st.rerun()


def render_banner(yaml_path: Path, tier: str) -> None:
    """Show the 'Try the new UI' banner once per session.

    Dismissed flag stored in user.yaml dismissed_banners list so it
    persists across sessions (uses the existing dismissed_banners pattern).
    Eligible: paid+ tier, OR demo mode. Not shown if already on vue.
    """
    eligible = _DEMO_MODE or can_use(tier, "vue_ui_beta")
    if not eligible:
        return

    try:
        profile = UserProfile(yaml_path)
    except Exception:
        return

    if profile.ui_preference == "vue":
        return
    if "ui_switcher_beta" in (profile.dismissed_banners or []):
        return

    col1, col2, col3 = st.columns([8, 1, 1])
    with col1:
        st.info("✨ **New Peregrine UI available** — try the modern Vue interface (Beta, Paid tier)")
    with col2:
        if st.button("Try it", key="_ui_banner_try"):
            switch_ui(yaml_path, to="vue", tier=tier)
    with col3:
        if st.button("Dismiss", key="_ui_banner_dismiss"):
            profile.dismissed_banners = list(profile.dismissed_banners or []) + ["ui_switcher_beta"]
            profile.save()
            st.rerun()


def render_settings_toggle(yaml_path: Path, tier: str) -> None:
    """Toggle in Settings → System → Deployment expander."""
    eligible = _DEMO_MODE or can_use(tier, "vue_ui_beta")
    if not eligible:
        return

    try:
        profile = UserProfile(yaml_path)
        current = profile.ui_preference
    except Exception:
        current = "streamlit"

    options = ["streamlit", "vue"]
    labels = ["Classic (Streamlit)", "✨ New UI (Vue, Beta)"]
    current_idx = options.index(current) if current in options else 0

    st.markdown("**UI Version**")
    chosen = st.radio(
        "UI Version",
        options=labels,
        index=current_idx,
        key="_ui_toggle_radio",
        label_visibility="collapsed",
    )
    chosen_val = options[labels.index(chosen)]

    if chosen_val != current:
        switch_ui(yaml_path, to=chosen_val, tier=tier)
```

- [ ] **Step 3.4: Run tests**

```bash
/devl/miniconda3/envs/job-seeker/bin/pytest tests/test_ui_switcher.py -v
```

Expected: all pass

- [ ] **Step 3.5: Commit**

```bash
git add app/components/ui_switcher.py tests/test_ui_switcher.py
git commit -m "feat(ui-switcher): add ui_switcher component (sync_ui_cookie, switch_ui, render_banner, render_settings_toggle)"
```

---

## Task 4: Create `app/components/demo_toolbar.py`

**Files:**
- Create: `app/components/demo_toolbar.py`
- Create: `tests/test_demo_toolbar.py`

- [ ] **Step 4.1: Write failing tests**

Create `tests/test_demo_toolbar.py`:

```python
"""Tests for app/components/demo_toolbar.py."""
import sys, os
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

# Ensure DEMO_MODE is set so the module initialises correctly
os.environ["DEMO_MODE"] = "true"


def test_set_simulated_tier_updates_session_state(monkeypatch):
    """set_simulated_tier writes to st.session_state.simulated_tier."""
    session = {}
    injected = []
    monkeypatch.setattr("streamlit.components.v1.html", lambda h, height=0: injected.append(h))
    monkeypatch.setattr("streamlit.session_state", session, raising=False)
    monkeypatch.setattr("streamlit.rerun", lambda: None)

    from importlib import reload
    import app.components.demo_toolbar as m
    reload(m)

    m.set_simulated_tier("premium")

    assert session.get("simulated_tier") == "premium"
    assert any("prgn_demo_tier=premium" in h for h in injected)


def test_set_simulated_tier_invalid_ignored(monkeypatch):
    """Invalid tier strings are rejected."""
    session = {}
    monkeypatch.setattr("streamlit.components.v1.html", lambda h, height=0: None)
    monkeypatch.setattr("streamlit.session_state", session, raising=False)
    monkeypatch.setattr("streamlit.rerun", lambda: None)

    from importlib import reload
    import app.components.demo_toolbar as m
    reload(m)

    m.set_simulated_tier("ultramax")

    assert "simulated_tier" not in session


def test_get_simulated_tier_defaults_to_paid(monkeypatch):
    """Returns 'paid' when no tier is set yet."""
    monkeypatch.setattr("streamlit.session_state", {}, raising=False)
    monkeypatch.setattr("streamlit.query_params", {}, raising=False)

    from importlib import reload
    import app.components.demo_toolbar as m
    reload(m)

    assert m.get_simulated_tier() == "paid"


def test_get_simulated_tier_reads_session(monkeypatch):
    """Returns tier from st.session_state when set."""
    monkeypatch.setattr("streamlit.session_state", {"simulated_tier": "free"}, raising=False)
    monkeypatch.setattr("streamlit.query_params", {}, raising=False)

    from importlib import reload
    import app.components.demo_toolbar as m
    reload(m)

    assert m.get_simulated_tier() == "free"
```

- [ ] **Step 4.2: Run to confirm failures**

```bash
/devl/miniconda3/envs/job-seeker/bin/pytest tests/test_demo_toolbar.py -v
```

Expected: ImportError — module doesn't exist yet

- [ ] **Step 4.3: Create `app/components/demo_toolbar.py`**

```python
"""Demo toolbar — tier simulation for DEMO_MODE instances.

Renders a slim full-width bar above the Streamlit nav showing
Free / Paid / Premium pills. Clicking a pill sets a prgn_demo_tier
cookie (for persistence across reloads) and st.session_state.simulated_tier
(for immediate use within the current render pass).

Only ever rendered when DEMO_MODE=true.
"""
from __future__ import annotations

import os

import streamlit as st
import streamlit.components.v1 as components

_VALID_TIERS = ("free", "paid", "premium")
_DEFAULT_TIER = "paid"  # most compelling first impression

_COOKIE_JS = """
<script>
(function() {{
  document.cookie = 'prgn_demo_tier={tier}; path=/; SameSite=Lax';
}})();
</script>
"""


def get_simulated_tier() -> str:
    """Return the current simulated tier, defaulting to 'paid'."""
    return st.session_state.get("simulated_tier", _DEFAULT_TIER)


def set_simulated_tier(tier: str) -> None:
    """Set simulated tier in session state + cookie. Reruns the page."""
    if tier not in _VALID_TIERS:
        return
    st.session_state["simulated_tier"] = tier
    components.html(_COOKIE_JS.format(tier=tier), height=0)
    st.rerun()


def render_demo_toolbar() -> None:
    """Render the demo mode toolbar.

    Shows a dismissible info bar with tier-selection pills.
    Call this at the TOP of app.py's render pass, before pg.run().
    """
    current = get_simulated_tier()

    labels = {
        "free": "Free",
        "paid": "Paid ✓" if current == "paid" else "Paid",
        "premium": "Premium ✓" if current == "premium" else "Premium",
    }

    with st.container():
        cols = st.columns([3, 1, 1, 1, 2])
        with cols[0]:
            st.caption("🎭 **Demo mode** — exploring as:")
        for i, tier in enumerate(_VALID_TIERS):
            with cols[i + 1]:
                is_active = tier == current
                if st.button(
                    labels[tier],
                    key=f"_demo_tier_{tier}",
                    type="primary" if is_active else "secondary",
                    use_container_width=True,
                ):
                    if not is_active:
                        set_simulated_tier(tier)
        with cols[4]:
            st.caption("[Get your own →](https://circuitforge.tech/software/peregrine)")
        st.divider()
```

- [ ] **Step 4.4: Run tests**

```bash
/devl/miniconda3/envs/job-seeker/bin/pytest tests/test_demo_toolbar.py -v
```

Expected: all pass

- [ ] **Step 4.5: Commit**

```bash
git add app/components/demo_toolbar.py tests/test_demo_toolbar.py
git commit -m "feat(demo): add demo_toolbar component (tier simulation for DEMO_MODE)"
```

---

## Task 5: Wire components into `app/app.py` and Settings

**Files:**
- Modify: `app/app.py`
- Modify: `app/pages/2_Settings.py:997–1042`

- [ ] **Step 5.1: Wire `sync_ui_cookie` and banners into `app.py`**

Find the block after `pg.run()` in `app/app.py` (currently ends around line 175). Add imports near the top of `app.py` after existing imports:

```python
from app.components.ui_switcher import sync_ui_cookie, render_banner
```

After `_startup()` and the wizard gate block, before `pg = st.navigation(pages)`, add:

```python
# ── Demo toolbar ───────────────────────────────────────────────────────────────
if IS_DEMO:
    from app.components.demo_toolbar import render_demo_toolbar
    render_demo_toolbar()
```

After `pg.run()`, add:

```python
# ── UI switcher cookie sync + banner ──────────────────────────────────────────
# Must run after pg.run() — st.components.v1.html requires an active render pass.
try:
    _current_tier = _UserProfile(_USER_YAML).tier  # UserProfile.tier reads user.yaml + dev_tier_override
except Exception:
    _current_tier = "free"

if IS_DEMO:
    from app.components.demo_toolbar import get_simulated_tier as _get_sim_tier
    _current_tier = _get_sim_tier()

sync_ui_cookie(_USER_YAML, tier=_current_tier)
render_banner(_USER_YAML, tier=_current_tier)
```

- [ ] **Step 5.2: Wire `render_settings_toggle` into Settings**

In `app/pages/2_Settings.py`, find the `🖥️ Deployment / Server` expander (around line 997). At the end of that expander block (after the existing save button), add:

```python
        # ── UI Version switcher (Paid tier / Demo) ────────────────────────────
        st.markdown("---")
        from app.components.ui_switcher import render_settings_toggle as _render_ui_toggle
        _render_ui_toggle(_USER_YAML, tier=_tier)
```

Where `_tier` is however the Settings page resolves the current tier (check the existing pattern — typically `UserProfile(_USER_YAML).tier` or via the license module).

- [ ] **Step 5.3: Smoke test — start Peregrine and verify no crash**

```bash
conda run -n job-seeker python -c "
import sys; sys.path.insert(0, '.')
from app.components.ui_switcher import sync_ui_cookie, render_banner, render_settings_toggle
from app.components.demo_toolbar import render_demo_toolbar, get_simulated_tier, set_simulated_tier
print('imports OK')
"
```

Expected: `imports OK` (no ImportError or AttributeError)

- [ ] **Step 5.4: Run full test suite**

```bash
/devl/miniconda3/envs/job-seeker/bin/pytest tests/ -v --ignore=tests/e2e -x
```

Expected: all pass (no regressions)

- [ ] **Step 5.5: Commit**

```bash
git add app/app.py app/pages/2_Settings.py
git commit -m "feat(app): wire ui_switcher and demo_toolbar into render pass"
```

---

## Task 6: Merge Vue SPA + add `ClassicUIButton.vue` + `useFeatureFlag.ts`

**Files:**
- Merge `.worktrees/feature-vue-spa/web/` → `web/` in main branch
- Create: `web/src/components/ClassicUIButton.vue`
- Create: `web/src/composables/useFeatureFlag.ts`
- Modify: `web/src/components/AppNav.vue`

- [ ] **Step 6.1: Merge the Vue SPA worktree into main**

```bash
# From the peregrine repo root
git merge feature-vue-spa --no-ff -m "feat(web): merge Vue SPA from feature-vue-spa"
```

If the worktree was never committed as a branch and only exists as a local worktree checkout:

```bash
# Check if feature-vue-spa is a branch
git branch | grep feature-vue-spa

# If it exists, merge it
git merge feature-vue-spa --no-ff -m "feat(web): merge Vue SPA from feature-vue-spa"
```

After merge, confirm `web/` directory is present in the repo root:

```bash
ls web/src/components/ web/src/views/
```

Expected: `AppNav.vue`, `JobCard.vue`, views etc.

- [ ] **Step 6.2: Write failing Vitest test for `ClassicUIButton`**

Create `web/src/components/__tests__/ClassicUIButton.test.ts`:

```typescript
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import ClassicUIButton from '../ClassicUIButton.vue'

describe('ClassicUIButton', () => {
  beforeEach(() => {
    // Reset cookie and location mock
    Object.defineProperty(document, 'cookie', {
      writable: true,
      value: 'prgn_ui=vue',
    })
    delete (window as any).location
    ;(window as any).location = { reload: vi.fn(), href: '' }
  })

  it('renders a button', () => {
    const wrapper = mount(ClassicUIButton)
    expect(wrapper.find('button').exists()).toBe(true)
  })

  it('sets prgn_ui=streamlit cookie and appends prgn_switch param on click', async () => {
    const wrapper = mount(ClassicUIButton)
    await wrapper.find('button').trigger('click')
    expect(document.cookie).toContain('prgn_ui=streamlit')
    expect((window.location as any).href).toContain('prgn_switch=streamlit')
  })
})
```

- [ ] **Step 6.3: Run test to confirm failure**

```bash
cd /Library/Development/CircuitForge/peregrine/web && npm run test -- --reporter=verbose ClassicUIButton
```

Expected: component file not found

- [ ] **Step 6.4: Create `web/src/components/ClassicUIButton.vue`**

```vue
<template>
  <button
    class="classic-ui-btn"
    @click="switchToClassic"
    title="Switch back to the classic Streamlit interface"
  >
    ← Classic UI
  </button>
</template>

<script setup lang="ts">
function switchToClassic(): void {
  // Set the Caddy routing cookie
  document.cookie = 'prgn_ui=streamlit; path=/; SameSite=Lax'

  // Append ?prgn_switch=streamlit so Streamlit's sync_ui_cookie()
  // can detect the switch-back and update user.yaml accordingly.
  const url = new URL(window.location.href)
  url.searchParams.set('prgn_switch', 'streamlit')
  window.location.href = url.toString()
}
</script>

<style scoped>
.classic-ui-btn {
  font-size: 0.8rem;
  opacity: 0.7;
  cursor: pointer;
  background: none;
  border: 1px solid currentColor;
  border-radius: 4px;
  padding: 2px 8px;
  transition: opacity 0.15s;
}
.classic-ui-btn:hover {
  opacity: 1;
}
</style>
```

- [ ] **Step 6.5: Create `web/src/composables/useFeatureFlag.ts`**

```typescript
/**
 * useFeatureFlag — demo-mode tier display only.
 *
 * Reads the prgn_demo_tier cookie set by Streamlit's demo toolbar.
 * NOT an authoritative feature gate — for display/visual consistency only.
 * Real feature gating in the Vue SPA will use /api/features (future, issue #8).
 */

const TIERS = ['free', 'paid', 'premium'] as const
type Tier = typeof TIERS[number]

const TIER_RANKS: Record<Tier, number> = { free: 0, paid: 1, premium: 2 }

function getDemoTier(): Tier {
  const match = document.cookie.match(/prgn_demo_tier=([^;]+)/)
  const raw = match?.[1] ?? 'paid'
  return (TIERS as readonly string[]).includes(raw) ? (raw as Tier) : 'paid'
}

export function useFeatureFlag() {
  const demoTier = getDemoTier()
  const demoTierRank = TIER_RANKS[demoTier]

  function canUseInDemo(requiredTier: Tier): boolean {
    return demoTierRank >= TIER_RANKS[requiredTier]
  }

  return { demoTier, canUseInDemo }
}
```

- [ ] **Step 6.6: Mount `ClassicUIButton` in `AppNav.vue`**

In `web/src/components/AppNav.vue`, import and mount the button in the nav bar. Find the nav template and add:

```vue
<script setup lang="ts">
// existing imports ...
import ClassicUIButton from './ClassicUIButton.vue'
</script>

<!-- in the template, inside the nav element near other controls -->
<ClassicUIButton />
```

Exact placement: alongside the existing nav controls (check `AppNav.vue` for the current structure and place it in a consistent spot, e.g. right side of the nav bar).

- [ ] **Step 6.7: Run all Vue tests**

```bash
cd /Library/Development/CircuitForge/peregrine/web && npm run test
```

Expected: all pass including new ClassicUIButton tests

- [ ] **Step 6.8: Commit**

```bash
cd /Library/Development/CircuitForge/peregrine
git add web/src/components/ClassicUIButton.vue \
        web/src/components/__tests__/ClassicUIButton.test.ts \
        web/src/composables/useFeatureFlag.ts \
        web/src/components/AppNav.vue
git commit -m "feat(web): add ClassicUIButton and useFeatureFlag composable"
```

---

## Task 7: Docker `web` service

**Files:**
- Create: `docker/web/Dockerfile`
- Create: `docker/web/nginx.conf`
- Modify: `compose.yml`, `compose.demo.yml`, `compose.cloud.yml`

- [ ] **Step 7.1: Create `docker/web/nginx.conf`**

```nginx
server {
    listen 80;
    root /usr/share/nginx/html;
    index index.html;

    # SPA fallback — all unknown paths serve index.html for Vue Router
    location / {
        try_files $uri $uri/ /index.html;
    }

    # Cache-bust JS/CSS assets (Vite hashes filenames)
    location ~* \.(js|css|woff2?|ttf|eot|svg|png|jpg|jpeg|gif|ico)$ {
        expires 1y;
        add_header Cache-Control "public, immutable";
        access_log off;
    }

    # Health check endpoint for Docker/Caddy
    location /healthz {
        return 200 "ok";
        add_header Content-Type text/plain;
    }
}
```

- [ ] **Step 7.2: Create `docker/web/Dockerfile`**

```dockerfile
# Stage 1: Build Vue SPA
FROM node:20-alpine AS builder
WORKDIR /build
COPY web/package*.json ./
RUN npm ci --prefer-offline
COPY web/ ./
RUN npm run build

# Stage 2: Serve with nginx
FROM nginx:alpine
COPY docker/web/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /build/dist /usr/share/nginx/html
EXPOSE 80
HEALTHCHECK --interval=30s --timeout=5s \
  CMD wget -qO- http://localhost/healthz || exit 1
```

- [ ] **Step 7.3: Add `web` service to `compose.yml`**

Add after the last service in `compose.yml`:

```yaml
  web:
    build:
      context: .
      dockerfile: docker/web/Dockerfile
    ports:
      - "8506:80"
    restart: unless-stopped
```

- [ ] **Step 7.4: Add `web` service to `compose.demo.yml`**

```yaml
  web:
    build:
      context: .
      dockerfile: docker/web/Dockerfile
    ports:
      - "8507:80"
    restart: unless-stopped
```

- [ ] **Step 7.5: Add `web` service to `compose.cloud.yml`**

```yaml
  web:
    build:
      context: .
      dockerfile: docker/web/Dockerfile
    ports:
      - "8508:80"
    restart: unless-stopped
```

- [ ] **Step 7.6: Update `manage.sh` to build web service**

Find the `update` case in `manage.sh` (around line 138):
```bash
        $COMPOSE build app
```

Change to:
```bash
        $COMPOSE build app web
```

Also find anywhere `docker compose build` is called without specifying services and ensure `web` is included. Add a note to the help text listing `web` as one of the built services.

- [ ] **Step 7.7: Build and verify**

```bash
cd /Library/Development/CircuitForge/peregrine
docker compose build web 2>&1 | tail -20
```

Expected: `Successfully built` with no errors. The build will run `npm ci` + `vite build` inside the container.

```bash
docker compose up -d web
curl -s http://localhost:8506/healthz
```

Expected: `ok`

```bash
curl -s http://localhost:8506/ | head -5
```

Expected: HTML starting with `<!DOCTYPE html>` (the Vue SPA index)

- [ ] **Step 7.8: Commit**

```bash
git add docker/web/Dockerfile docker/web/nginx.conf \
        compose.yml compose.demo.yml compose.cloud.yml manage.sh
git commit -m "feat(docker): add web service for Vue SPA (nginx:alpine, ports 8506/8507/8508)"
```

---

## Task 8: Caddy routing

**Files:**
- Modify: `/devl/caddy-proxy/Caddyfile`

⚠️ **Caddy GOTCHA:** The Edit tool replaces files with a new inode. After editing, run `docker restart caddy-proxy` (not `caddy reload`).

- [ ] **Step 8.1: Update `menagerie.circuitforge.tech` peregrine block**

Find the existing block in the Caddyfile:
```
handle /peregrine* {
    @no_session not header Cookie *cf_session*
    redir @no_session https://circuitforge.tech/login?next={uri} 302

    reverse_proxy http://host.docker.internal:8505 {
```

Replace with:
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

Also add a `handle_errors` block within the `menagerie.circuitforge.tech` vhost (outside the `/peregrine*` handle, at vhost level):
```
handle_errors 502 {
    @vue_err {
        header Cookie *prgn_ui=vue*
        path /peregrine*
    }
    handle @vue_err {
        header Set-Cookie "prgn_ui=streamlit; Path=/; SameSite=Lax"
        redir * /peregrine?ui_fallback=1 302
    }
}
```

- [ ] **Step 8.2: Update `demo.circuitforge.tech` peregrine block**

Find:
```
handle /peregrine* {
    reverse_proxy http://host.docker.internal:8504
}
```

Replace with:
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

Add error handling within the `demo.circuitforge.tech` vhost:
```
handle_errors 502 {
    @vue_err {
        header Cookie *prgn_ui=vue*
        path /peregrine*
    }
    handle @vue_err {
        header Set-Cookie "prgn_ui=streamlit; Path=/; SameSite=Lax"
        redir * /peregrine?ui_fallback=1 302
    }
}
```

- [ ] **Step 8.3: Restart Caddy**

```bash
docker restart caddy-proxy
```

Wait 5 seconds, then verify Caddy is healthy:

```bash
docker logs caddy-proxy --tail=20
```

Expected: no `ERROR` lines, Caddy reports it is serving.

- [ ] **Step 8.4: Smoke test routing**

Test the cookie routing locally by simulating the cookie header:

```bash
# Without cookie — should hit Streamlit (8505 / 8504)
curl -s -o /dev/null -w "%{http_code}" https://menagerie.circuitforge.tech/peregrine

# With vue cookie — should hit Vue SPA (8508)
curl -s -o /dev/null -w "%{http_code}" \
  -H "Cookie: prgn_ui=vue; cf_session=test" \
  https://menagerie.circuitforge.tech/peregrine
```

Both should return 200 (or redirect codes if session auth kicks in — that's expected).

- [ ] **Step 8.5: Commit Caddyfile**

```bash
git -C /devl/caddy-proxy add Caddyfile
git -C /devl/caddy-proxy commit -m "feat(caddy): add prgn_ui cookie routing for peregrine Vue SPA"
```

---

## Task 9: Integration smoke test

- [ ] **Step 9.1: Full Python test suite**

```bash
/devl/miniconda3/envs/job-seeker/bin/pytest tests/ -v --ignore=tests/e2e -x
```

Expected: all pass

- [ ] **Step 9.2: Docker stack smoke test**

```bash
cd /Library/Development/CircuitForge/peregrine
./manage.sh start
sleep 10
curl -s http://localhost:8502 | grep -i "streamlit\|peregrine" | head -3
curl -s http://localhost:8506/healthz
```

Expected: Streamlit on 8502 responds, Vue SPA health check returns `ok`

- [ ] **Step 9.3: Manual switcher test (personal instance)**

1. Open http://localhost:8501 (or 8502)
2. Confirm the "Try it" banner appears (if on paid tier) or is absent (free tier)
3. Click "Try it" — confirm the page reloads and now serves from port 8506 (Vue SPA)
4. In the Vue SPA, click "← Classic UI" — confirm redirects back to Streamlit
5. Open Settings → System → Deployment → confirm the UI radio is present
6. Confirm `config/user.yaml` shows `ui_preference: vue` / `streamlit` after each switch

- [ ] **Step 9.4: Demo stack smoke test**

```bash
docker compose -f compose.demo.yml --project-name peregrine-demo up -d
sleep 10
curl -s http://localhost:8504 | head -5  # Streamlit demo
curl -s http://localhost:8507/healthz     # Vue SPA demo
```

1. Open http://localhost:8504 (demo)
2. Confirm the demo toolbar appears with Free / Paid / Premium pills
3. Click "Free" — confirm gated features disappear
4. Click "Paid ✓" — confirm gated features reappear
5. Click "Try it" banner (should appear for all demo visitors)
6. Confirm routes to http://localhost:8507

- [ ] **Step 9.5: Final commit + tag**

```bash
cd /Library/Development/CircuitForge/peregrine
git tag v0.7.0-ui-switcher
git push origin main --tags
```

---

## Appendix: Checking `_tier` in `Settings.py`

Before wiring `render_settings_toggle`, check how `2_Settings.py` currently resolves the user's tier. Search for:

```bash
grep -n "tier\|can_use\|license" /Library/Development/CircuitForge/peregrine/app/pages/2_Settings.py | head -20
```

If the page already has a `_tier` or `_profile.tier` variable, use it directly. If not, use the same pattern as `app.py` (import `get_tier` from `scripts/license`).
