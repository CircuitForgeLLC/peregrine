"""
Tier definitions and feature gates for Peregrine.

Tiers: free < paid < premium
FEATURES maps feature key → minimum tier required.
Features not in FEATURES are available to all tiers (free).

BYOK policy
-----------
Features in BYOK_UNLOCKABLE are gated only because CircuitForge would otherwise
be providing the LLM compute. When a user has any configured LLM backend (local
ollama/vllm or their own API key), those features unlock regardless of tier.
Pass has_byok=has_configured_llm() to can_use() at call sites.

Features that stay gated even with BYOK:
  - Integrations (Notion sync, calendars, etc.) — infrastructure we run
  - llm_keywords_blocklist — orchestration pipeline over background keyword data
  - email_classifier — training pipeline, not a single LLM call
  - shared_cover_writer_model — our fine-tuned model weights
  - model_fine_tuning — GPU infrastructure
  - multi_user — account infrastructure
"""
from __future__ import annotations

import os as _os
from pathlib import Path

TIERS = ["free", "paid", "premium"]

# Maps feature key → minimum tier string required.
# Features absent from this dict are free (available to all).
FEATURES: dict[str, str] = {
    # Wizard LLM generation — BYOK-unlockable (pure LLM calls)
    "llm_career_summary":           "paid",
    "llm_expand_bullets":           "paid",
    "llm_suggest_skills":           "paid",
    "llm_voice_guidelines":         "premium",
    "llm_job_titles":               "paid",
    "llm_mission_notes":            "paid",

    # Orchestration — stays gated (background data pipeline, not just an LLM call)
    "llm_keywords_blocklist":       "paid",

    # App features — BYOK-unlockable (pure LLM calls over job/profile data)
    "company_research":             "paid",
    "interview_prep":               "paid",
    "survey_assistant":             "paid",

    # Orchestration / infrastructure — stays gated
    "email_classifier":             "paid",
    "model_fine_tuning":            "premium",
    "shared_cover_writer_model":    "paid",
    "multi_user":                   "premium",

    # Integrations — stays gated (infrastructure CircuitForge operates)
    "notion_sync":                  "paid",
    "google_sheets_sync":           "paid",
    "airtable_sync":                "paid",
    "google_calendar_sync":         "paid",
    "apple_calendar_sync":          "paid",
    "slack_notifications":          "paid",

    # Beta UI access — stays gated (access management, not compute)
    "vue_ui_beta":                  "paid",
}

# Features that unlock when the user supplies any LLM backend (local or BYOK).
# These are pure LLM-call features — the only reason they're behind a tier is
# because CircuitForge would otherwise be providing the compute.
BYOK_UNLOCKABLE: frozenset[str] = frozenset({
    "llm_career_summary",
    "llm_expand_bullets",
    "llm_suggest_skills",
    "llm_voice_guidelines",
    "llm_job_titles",
    "llm_mission_notes",
    "company_research",
    "interview_prep",
    "survey_assistant",
})

# Demo mode flag — read from environment at module load time.
# Allows demo toolbar to override tier without accessing st.session_state (thread-safe).
# _DEMO_MODE is immutable after import for the process lifetime.
# DEMO_MODE must be set in the environment before the process starts (e.g., via
# Docker Compose environment:). Runtime toggling is not supported.
_DEMO_MODE = _os.environ.get("DEMO_MODE", "").lower() in ("1", "true", "yes")

# Free integrations (not in FEATURES):
# google_drive_sync, dropbox_sync, onedrive_sync, mega_sync,
# nextcloud_sync, discord_notifications, home_assistant

_LLM_CFG = Path(__file__).parent.parent.parent / "config" / "llm.yaml"


def has_configured_llm(config_path: Path | None = None) -> bool:
    """Return True if at least one non-vision LLM backend is enabled in llm.yaml.

    Local backends (ollama, vllm) count — the policy is "you're providing the
    compute", whether that's your own hardware or your own API key.
    """
    import yaml
    path = config_path or _LLM_CFG
    try:
        with open(path) as f:
            cfg = yaml.safe_load(f) or {}
        return any(
            b.get("enabled", True) and b.get("type") != "vision_service"
            for b in cfg.get("backends", {}).values()
        )
    except Exception:
        return False


def can_use(
    tier: str,
    feature: str,
    has_byok: bool = False,
    *,
    demo_tier: str | None = None,
) -> bool:
    """Return True if the given tier has access to the feature.

    has_byok: pass has_configured_llm() to unlock BYOK_UNLOCKABLE features
    for users who supply their own LLM backend regardless of tier.

    demo_tier: when set AND _DEMO_MODE is True, substitutes for `tier`.
               Read from st.session_state by the *caller*, not here — keeps
               this function thread-safe for background tasks and tests.

    Returns True for unknown features (not gated).
    Returns False for unknown/invalid tier strings.
    """
    effective_tier = demo_tier if (demo_tier is not None and _DEMO_MODE) else tier
    required = FEATURES.get(feature)
    if required is None:
        return True  # not gated — available to all
    if has_byok and feature in BYOK_UNLOCKABLE:
        return True
    try:
        return TIERS.index(effective_tier) >= TIERS.index(required)
    except ValueError:
        return False  # invalid tier string


def tier_label(feature: str, has_byok: bool = False) -> str:
    """Return a display label for a locked feature, or '' if free/unlocked."""
    if has_byok and feature in BYOK_UNLOCKABLE:
        return ""
    required = FEATURES.get(feature)
    if required is None:
        return ""
    return "🔒 Paid" if required == "paid" else "⭐ Premium"


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
