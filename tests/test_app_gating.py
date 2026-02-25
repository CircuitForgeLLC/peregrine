from pathlib import Path
import yaml
from scripts.user_profile import UserProfile


def test_wizard_gating_logic(tmp_path):
    """Wizard gate should trigger when user.yaml is absent."""
    missing = tmp_path / "user.yaml"
    assert not UserProfile.exists(missing)


def test_wizard_gating_passes_after_setup(tmp_path):
    """Wizard gate should clear once user.yaml is written."""
    p = tmp_path / "user.yaml"
    p.write_text(yaml.dump({"name": "Test User", "services": {}}))
    assert UserProfile.exists(p)


def test_wizard_gating_empty_file_still_exists(tmp_path):
    """An empty user.yaml still clears the gate (wizard already ran)."""
    p = tmp_path / "user.yaml"
    p.write_text("")
    assert UserProfile.exists(p)


def test_wizard_incomplete_triggers_wizard(tmp_path):
    """wizard_complete: false should be treated as 'wizard not done'."""
    p = tmp_path / "user.yaml"
    p.write_text("name: T\nemail: t@t.com\ncareer_summary: x\nwizard_complete: false\n")
    from scripts.user_profile import UserProfile
    u = UserProfile(p)
    assert u.wizard_complete is False

def test_wizard_complete_does_not_trigger(tmp_path):
    p = tmp_path / "user.yaml"
    p.write_text("name: T\nemail: t@t.com\ncareer_summary: x\nwizard_complete: true\n")
    from scripts.user_profile import UserProfile
    u = UserProfile(p)
    assert u.wizard_complete is True
