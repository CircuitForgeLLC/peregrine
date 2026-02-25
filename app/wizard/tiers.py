"""
Tier definitions and feature gates for Peregrine.

Tiers: free < paid < premium
FEATURES maps feature key → minimum tier required.
Features not in FEATURES are available to all tiers (free).
"""
from __future__ import annotations

TIERS = ["free", "paid", "premium"]

# Maps feature key → minimum tier string required.
# Features absent from this dict are free (available to all).
FEATURES: dict[str, str] = {
    # Wizard LLM generation
    "llm_career_summary":           "paid",
    "llm_expand_bullets":           "paid",
    "llm_suggest_skills":           "paid",
    "llm_voice_guidelines":         "premium",
    "llm_job_titles":               "paid",
    "llm_keywords_blocklist":       "paid",
    "llm_mission_notes":            "paid",

    # App features
    "company_research":             "paid",
    "interview_prep":               "paid",
    "email_classifier":             "paid",
    "survey_assistant":             "paid",
    "model_fine_tuning":            "premium",
    "shared_cover_writer_model":    "paid",
    "multi_user":                   "premium",

    # Integrations (paid)
    "notion_sync":                  "paid",
    "google_sheets_sync":           "paid",
    "airtable_sync":                "paid",
    "google_calendar_sync":         "paid",
    "apple_calendar_sync":          "paid",
    "slack_notifications":          "paid",
}

# Free integrations (not in FEATURES):
# google_drive_sync, dropbox_sync, onedrive_sync, mega_sync,
# nextcloud_sync, discord_notifications, home_assistant


def can_use(tier: str, feature: str) -> bool:
    """Return True if the given tier has access to the feature.

    Returns True for unknown features (not gated).
    Returns False for unknown/invalid tier strings.
    """
    required = FEATURES.get(feature)
    if required is None:
        return True  # not gated — available to all
    try:
        return TIERS.index(tier) >= TIERS.index(required)
    except ValueError:
        return False  # invalid tier string


def tier_label(feature: str) -> str:
    """Return a display label for a locked feature, or '' if free/unknown."""
    required = FEATURES.get(feature)
    if required is None:
        return ""
    return "🔒 Paid" if required == "paid" else "⭐ Premium"
