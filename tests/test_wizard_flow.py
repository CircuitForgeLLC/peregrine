"""
Wizard flow logic tests — no Streamlit dependency.
Tests validate() chain, yaml persistence helpers, and wizard state inference.
"""
import sys
from pathlib import Path
import yaml
sys.path.insert(0, str(Path(__file__).parent.parent))


# ── All mandatory steps validate correctly ────────────────────────────────────

def test_all_mandatory_steps_accept_minimal_valid_data():
    """Each step's validate() accepts the minimum required input."""
    from app.wizard.step_hardware import validate as hw
    from app.wizard.step_tier import validate as tier
    from app.wizard.step_identity import validate as ident
    from app.wizard.step_resume import validate as resume
    from app.wizard.step_inference import validate as inf
    from app.wizard.step_search import validate as search

    assert hw({"inference_profile": "remote"}) == []
    assert tier({"tier": "free"}) == []
    assert ident({"name": "A", "email": "a@b.com", "career_summary": "x"}) == []
    assert resume({"experience": [{"company": "X", "title": "T", "bullets": []}]}) == []
    assert inf({"endpoint_confirmed": True}) == []
    assert search({"job_titles": ["SWE"], "locations": ["Remote"]}) == []


def test_mandatory_steps_reject_empty_data():
    """Each step's validate() rejects completely empty input."""
    from app.wizard.step_hardware import validate as hw
    from app.wizard.step_tier import validate as tier
    from app.wizard.step_identity import validate as ident
    from app.wizard.step_resume import validate as resume
    from app.wizard.step_inference import validate as inf
    from app.wizard.step_search import validate as search

    assert hw({}) != []
    assert tier({}) != []
    assert ident({}) != []
    assert resume({}) != []
    assert inf({}) != []
    assert search({}) != []


# ── Yaml persistence helpers ──────────────────────────────────────────────────

def test_wizard_step_persists_to_yaml(tmp_path):
    """Writing wizard_step to user.yaml survives a reload."""
    p = tmp_path / "user.yaml"
    p.write_text(yaml.dump({
        "name": "Test", "email": "t@t.com",
        "career_summary": "x", "wizard_complete": False,
    }))
    # Simulate "write step 3 on Next"
    data = yaml.safe_load(p.read_text()) or {}
    data["wizard_step"] = 3
    p.write_text(yaml.dump(data))
    reloaded = yaml.safe_load(p.read_text())
    assert reloaded["wizard_step"] == 3
    assert reloaded["wizard_complete"] is False


def test_finish_sets_wizard_complete_and_removes_wizard_step(tmp_path):
    """After Finish, wizard_complete is True and wizard_step is absent."""
    p = tmp_path / "user.yaml"
    p.write_text(yaml.dump({
        "name": "Test", "email": "t@t.com",
        "career_summary": "x", "wizard_complete": False, "wizard_step": 6,
    }))
    # Simulate Finish action
    data = yaml.safe_load(p.read_text()) or {}
    data["wizard_complete"] = True
    data.pop("wizard_step", None)
    p.write_text(yaml.dump(data))
    reloaded = yaml.safe_load(p.read_text())
    assert reloaded["wizard_complete"] is True
    assert "wizard_step" not in reloaded


def test_wizard_resume_step_inferred_from_yaml(tmp_path):
    """wizard_step in user.yaml determines which step to resume at."""
    p = tmp_path / "user.yaml"
    p.write_text(yaml.dump({
        "name": "Test", "email": "t@t.com",
        "career_summary": "x", "wizard_complete": False, "wizard_step": 4,
    }))
    data = yaml.safe_load(p.read_text()) or {}
    # Wizard should resume at step 5 (last_completed + 1)
    resume_at = data.get("wizard_step", 0) + 1
    assert resume_at == 5


def test_wizard_complete_true_means_no_wizard(tmp_path):
    """If wizard_complete is True, the app should NOT show the wizard."""
    p = tmp_path / "user.yaml"
    p.write_text(yaml.dump({
        "name": "Test", "email": "t@t.com",
        "career_summary": "x", "wizard_complete": True,
    }))
    from scripts.user_profile import UserProfile
    u = UserProfile(p)
    assert u.wizard_complete is True


def test_wizard_incomplete_means_show_wizard(tmp_path):
    """If wizard_complete is False, the app SHOULD show the wizard."""
    p = tmp_path / "user.yaml"
    p.write_text(yaml.dump({
        "name": "Test", "email": "t@t.com",
        "career_summary": "x", "wizard_complete": False,
    }))
    from scripts.user_profile import UserProfile
    u = UserProfile(p)
    assert u.wizard_complete is False
