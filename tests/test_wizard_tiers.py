import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.wizard.tiers import can_use, tier_label, TIERS, FEATURES, BYOK_UNLOCKABLE


def test_tiers_list():
    # Peregrine uses the core tier list; "ultra" is included but no features require it yet
    assert TIERS[:3] == ["free", "paid", "premium"]
    assert "ultra" in TIERS


def test_can_use_free_feature_always():
    # Features not in FEATURES dict are available to all tiers
    assert can_use("free", "some_unknown_feature") is True


def test_can_use_paid_feature_free_tier():
    assert can_use("free", "company_research") is False


def test_can_use_paid_feature_paid_tier():
    assert can_use("paid", "company_research") is True


def test_can_use_paid_feature_premium_tier():
    assert can_use("premium", "company_research") is True


def test_can_use_premium_feature_paid_tier():
    assert can_use("paid", "model_fine_tuning") is False


def test_can_use_premium_feature_premium_tier():
    assert can_use("premium", "model_fine_tuning") is True


def test_can_use_unknown_feature_always_true():
    assert can_use("free", "nonexistent_feature") is True


def test_tier_label_paid():
    label = tier_label("company_research")
    assert "Paid" in label or "paid" in label.lower()


def test_tier_label_premium():
    label = tier_label("model_fine_tuning")
    assert "Premium" in label or "premium" in label.lower()


def test_tier_label_free_feature():
    label = tier_label("unknown_free_feature")
    assert label == ""


def test_can_use_invalid_tier_returns_false():
    # Invalid tier string should return False (safe failure mode)
    assert can_use("bogus", "company_research") is False


def test_free_integrations_are_accessible():
    # These integrations are free (not in FEATURES dict)
    for feature in ["google_drive_sync", "dropbox_sync", "discord_notifications"]:
        assert can_use("free", feature) is True


def test_paid_integrations_gated():
    assert can_use("free", "notion_sync") is False
    assert can_use("paid", "notion_sync") is True


# ── BYOK tests ────────────────────────────────────────────────────────────────

def test_byok_unlocks_llm_features_for_free_tier():
    # BYOK_UNLOCKABLE features become accessible on free tier when has_byok=True
    for feature in BYOK_UNLOCKABLE:
        assert can_use("free", feature, has_byok=True) is True, (
            f"{feature} should be accessible with BYOK on free tier"
        )


def test_byok_does_not_unlock_integrations():
    # Integrations stay gated even with BYOK — they depend on CF infrastructure
    for feature in ["notion_sync", "google_sheets_sync", "slack_notifications"]:
        assert can_use("free", feature, has_byok=True) is False, (
            f"{feature} should stay gated even with BYOK"
        )


def test_byok_does_not_unlock_orchestration_features():
    # These features depend on background pipelines, not just an LLM call
    for feature in ["llm_keywords_blocklist", "email_classifier", "model_fine_tuning"]:
        assert can_use("free", feature, has_byok=True) is False, (
            f"{feature} should stay gated even with BYOK"
        )


def test_tier_label_hidden_when_byok_unlocks():
    # BYOK_UNLOCKABLE features should show no lock label when has_byok=True
    for feature in BYOK_UNLOCKABLE:
        assert tier_label(feature, has_byok=True) == "", (
            f"{feature} should show no lock label when BYOK is active"
        )


def test_tier_label_still_shows_for_non_unlockable_with_byok():
    assert tier_label("notion_sync", has_byok=True) != ""
    assert tier_label("email_classifier", has_byok=True) != ""


def test_byok_false_preserves_original_gating():
    # has_byok=False (default) must not change existing behaviour
    assert can_use("free", "company_research", has_byok=False) is False
    assert can_use("paid", "company_research", has_byok=False) is True


# ── Vue UI Beta & Demo Tier tests ──────────────────────────────────────────────

def test_vue_ui_beta_free_tier():
    assert can_use("free", "vue_ui_beta") is False


def test_vue_ui_beta_paid_tier():
    assert can_use("paid", "vue_ui_beta") is True


def test_vue_ui_beta_premium_tier():
    assert can_use("premium", "vue_ui_beta") is True


def test_can_use_demo_tier_overrides_real_tier():
    # demo_tier="paid" overrides real tier "free" when DEMO_MODE is active
    with patch('app.wizard.tiers._DEMO_MODE', True):
        assert can_use("free", "company_research", demo_tier="paid") is True


def test_can_use_demo_tier_free_restricts():
    # demo_tier="free" restricts access even if real tier is "paid"
    with patch('app.wizard.tiers._DEMO_MODE', True):
        assert can_use("paid", "model_fine_tuning", demo_tier="free") is False


def test_can_use_demo_tier_none_falls_back_to_real():
    # demo_tier=None means no override regardless of DEMO_MODE
    with patch('app.wizard.tiers._DEMO_MODE', True):
        assert can_use("paid", "company_research", demo_tier=None) is True


def test_can_use_demo_tier_does_not_affect_non_demo():
    # When _DEMO_MODE is False, demo_tier is ignored
    with patch('app.wizard.tiers._DEMO_MODE', False):
        assert can_use("free", "company_research", demo_tier="paid") is False
