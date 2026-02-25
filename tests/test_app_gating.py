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
