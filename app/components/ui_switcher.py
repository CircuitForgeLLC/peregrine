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
        # UI components must not crash the app — silent fallback
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
        # UI components must not crash the app — silent fallback
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
