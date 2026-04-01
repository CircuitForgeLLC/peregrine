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

_DEMO_MODE = os.environ.get("DEMO_MODE", "").lower() in ("1", "true", "yes")

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

    labels = {t: t.capitalize() + (" ✓" if t == current else "") for t in _VALID_TIERS}

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
