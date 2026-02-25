import sys
from pathlib import Path
import yaml
sys.path.insert(0, str(Path(__file__).parent.parent))


def test_dev_tab_visible_when_override_set(tmp_path):
    p = tmp_path / "user.yaml"
    p.write_text("name: T\nemail: t@t.com\ncareer_summary: x\ndev_tier_override: premium\n")
    from scripts.user_profile import UserProfile
    u = UserProfile(p)
    assert u.dev_tier_override == "premium"
    assert u.effective_tier == "premium"


def test_dev_tab_not_visible_without_override(tmp_path):
    p = tmp_path / "user.yaml"
    p.write_text("name: T\nemail: t@t.com\ncareer_summary: x\ntier: free\n")
    from scripts.user_profile import UserProfile
    u = UserProfile(p)
    assert u.dev_tier_override is None
    assert u.effective_tier == "free"


def test_can_use_uses_effective_tier(tmp_path):
    p = tmp_path / "user.yaml"
    p.write_text("name: T\nemail: t@t.com\ncareer_summary: x\ntier: free\ndev_tier_override: premium\n")
    from scripts.user_profile import UserProfile
    from app.wizard.tiers import can_use
    u = UserProfile(p)
    assert can_use(u.effective_tier, "model_fine_tuning") is True
    assert can_use(u.tier, "model_fine_tuning") is False
