import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.wizard.tiers import can_use, tier_label, TIERS, FEATURES


def test_tiers_list():
    assert TIERS == ["free", "paid", "premium"]


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
