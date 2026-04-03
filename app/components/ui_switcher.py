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

# When set, the app is running without a Caddy reverse proxy in front
# (local dev, direct port exposure). Switch to Vue by navigating directly
# to this URL instead of relying on cookie-based Caddy routing.
# Example: PEREGRINE_VUE_URL=http://localhost:8506
_VUE_URL = os.environ.get("PEREGRINE_VUE_URL", "").strip().rstrip("/")

# When True, a window.location.reload() after setting prgn_ui=vue will be
# intercepted by Caddy and routed to the Vue SPA. When False (no Caddy in the
# traffic path — e.g. test instances, direct Docker exposure), reloading just
# comes back to Streamlit and creates an infinite loop. Only set this in
# production/staging compose files where Caddy is actually in front.
_CADDY_PROXY = os.environ.get("PEREGRINE_CADDY_PROXY", "").lower() in ("1", "true", "yes")

_COOKIE_JS = """
<script>
(function() {{
  document.cookie = 'prgn_ui={value}; path=/; SameSite=Lax';
  {navigate_js}
}})();
</script>
"""


def _set_cookie_js(value: str, navigate: bool = False) -> None:
    """Inject JS to set the prgn_ui cookie.

    When PEREGRINE_VUE_URL is set (local dev, no Caddy): navigating to Vue
    uses window.parent.location.href to jump directly to the Vue container
    port. Without this, reload() just sends the request back to the same
    Streamlit port with no router in between to inspect the cookie.

    When PEREGRINE_CADDY_PROXY is set (production/staging): navigate=True
    triggers window.location.reload() so Caddy sees the updated cookie on
    the next HTTP request and routes accordingly.

    When neither is set (test instances, bare Docker): navigate is suppressed
    entirely — the cookie is written silently, but no reload is attempted.
    Reloading without a proxy just bounces back to Streamlit and loops.
    """
    # components.html() renders in an iframe — window.parent navigates the host page
    if navigate and value == "vue" and _VUE_URL:
        nav_js = f"window.parent.location.href = '{_VUE_URL}';"
    elif navigate and _CADDY_PROXY:
        nav_js = "window.parent.location.reload();"
    else:
        nav_js = ""
    components.html(_COOKIE_JS.format(value=value, navigate_js=nav_js), height=0)


def sync_ui_cookie(yaml_path: Path, tier: str) -> None:
    """Sync the prgn_ui cookie to match user.yaml ui_preference.

    Also handles:
    - ?prgn_switch=<value> param (Vue SPA switch-back signal): overrides yaml,
      writes yaml to match, clears the param.
    - Tier downgrade: resets vue preference to streamlit for ineligible users.
    - ?ui_fallback=1 param: Vue SPA was down — reinforce streamlit cookie and
      return early to avoid immediately navigating back to a broken Vue SPA.

    When the resolved preference is "vue", this function navigates (full page
    reload) rather than silently setting the cookie. Without navigate=True,
    Streamlit would set prgn_ui=vue mid-page-load; subsequent HTTP requests
    made by Streamlit's own frontend (lazy JS chunks, WebSocket upgrade) would
    carry the new cookie and Caddy would misroute them to the Vue nginx
    container, causing TypeError: error loading dynamically imported module.
    """
    # ── ?ui_fallback=1 — Vue SPA was down, Caddy bounced us back ──────────────
    # Return early: reinforce the streamlit cookie so we don't immediately
    # navigate back to a Vue SPA that may still be down.
    if st.query_params.get("ui_fallback"):
        st.toast("⚠️ New UI temporarily unavailable — switched back to Classic", icon="⚠️")
        st.query_params.pop("ui_fallback", None)
        _set_cookie_js("streamlit")
        return

    # ── ?prgn_switch param — Vue SPA sent us here to switch back ──────────────
    switch_param = st.query_params.get("prgn_switch")
    if switch_param in ("streamlit", "vue"):
        try:
            profile = UserProfile(yaml_path)
            profile.ui_preference = switch_param
            profile.save()
        except Exception:
            # UI components must not crash the app — silent fallback
            pass
        st.query_params.pop("prgn_switch", None)
        _set_cookie_js(switch_param)
        return

    # ── Normal path: read yaml, enforce tier, inject cookie ───────────────────
    profile = None
    try:
        profile = UserProfile(yaml_path)
        pref = profile.ui_preference
    except Exception:
        # UI components must not crash the app — silent fallback to default
        pref = "streamlit"

    # Demo mode: Vue SPA has no demo data wiring — always serve Streamlit.
    # (The tier downgrade check below is skipped in demo mode, but we must
    # also block the Vue navigation itself so Caddy doesn't route to a blank SPA.)
    if pref == "vue" and _DEMO_MODE:
        pref = "streamlit"

    # Tier downgrade protection (skip in demo — demo bypasses tier gate)
    if pref == "vue" and not _DEMO_MODE and not can_use(tier, "vue_ui_beta"):
        if profile is not None:
            try:
                profile.ui_preference = "streamlit"
                profile.save()
            except Exception:
                # UI components must not crash the app — silent fallback
                pass
        pref = "streamlit"

    # Navigate (full reload) when switching to Vue so Caddy re-routes on the
    # next HTTP request before Streamlit serves any more content. Silent
    # cookie-only set is safe for streamlit since we're already on that origin.
    _set_cookie_js(pref, navigate=(pref == "vue"))


def switch_ui(yaml_path: Path, to: str, tier: str) -> None:
    """Write user.yaml, set cookie, and navigate.

    to: "vue" | "streamlit"

    Switching to Vue triggers window.location.reload() so Caddy sees the
    updated prgn_ui cookie and routes to the Vue SPA. st.rerun() alone is
    not sufficient — it operates over WebSocket and produces no HTTP request.

    Switching back to streamlit uses st.rerun() (no full reload needed since
    we're already on the Streamlit origin and no Caddy re-routing is required).
    """
    if to not in ("vue", "streamlit"):
        return
    try:
        profile = UserProfile(yaml_path)
        profile.ui_preference = to
        profile.save()
    except Exception:
        # UI components must not crash the app — silent fallback
        pass
    if to == "vue":
        # navigate=True triggers window.location.reload() after setting cookie
        _set_cookie_js("vue", navigate=True)
    else:
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
        # UI components must not crash the app — silent fallback
        return

    if profile.ui_preference == "vue":
        return
    if "ui_switcher_beta" in (profile.dismissed_banners or []):
        return

    col1, col2, col3 = st.columns([8, 1, 1])
    with col1:
        st.info("✨ **New Peregrine UI available** — try the modern Vue interface (Beta)")
    with col2:
        if st.button("Try it", key="_ui_banner_try"):
            switch_ui(yaml_path, to="vue", tier=tier)
    with col3:
        if st.button("Dismiss", key="_ui_banner_dismiss"):
            profile.dismissed_banners = list(profile.dismissed_banners or []) + ["ui_switcher_beta"]
            profile.save()
            st.rerun()


def render_sidebar_switcher(yaml_path: Path, tier: str) -> None:
    """Persistent sidebar button to switch to the Vue UI.

    Shown when the user is eligible (paid+ or demo) and currently on Streamlit.
    This is always visible — unlike the banner which can be dismissed.
    """
    eligible = _DEMO_MODE or can_use(tier, "vue_ui_beta")
    if not eligible:
        return
    try:
        profile = UserProfile(yaml_path)
        if profile.ui_preference == "vue":
            return
    except Exception:
        pass

    if st.button("✨ Switch to New UI", key="_sidebar_switch_vue", use_container_width=True):
        switch_ui(yaml_path, to="vue", tier=tier)


def render_settings_toggle(yaml_path: Path, tier: str) -> None:
    """Toggle in Settings → System → Deployment expander."""
    eligible = _DEMO_MODE or can_use(tier, "vue_ui_beta")
    if not eligible:
        return

    try:
        profile = UserProfile(yaml_path)
        current = profile.ui_preference
    except Exception:
        # UI components must not crash the app — silent fallback to default
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
