import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

# ── Hardware ───────────────────────────────────────────────────────────────────
from app.wizard.step_hardware import validate as hw_validate, PROFILES

def test_hw_valid():
    assert hw_validate({"inference_profile": "remote"}) == []

def test_hw_missing():
    assert hw_validate({}) != []

def test_hw_invalid():
    assert hw_validate({"inference_profile": "turbo"}) != []

def test_hw_all_profiles():
    for p in PROFILES:
        assert hw_validate({"inference_profile": p}) == []

# ── Tier ───────────────────────────────────────────────────────────────────────
from app.wizard.step_tier import validate as tier_validate

def test_tier_valid():
    assert tier_validate({"tier": "free"}) == []

def test_tier_missing():
    assert tier_validate({}) != []

def test_tier_invalid():
    assert tier_validate({"tier": "enterprise"}) != []

# ── Identity ───────────────────────────────────────────────────────────────────
from app.wizard.step_identity import validate as id_validate

def test_id_all_required_fields():
    d = {"name": "Alice", "email": "a@b.com", "career_summary": "10 years of stuff."}
    assert id_validate(d) == []

def test_id_missing_name():
    d = {"name": "", "email": "a@b.com", "career_summary": "x"}
    errors = id_validate(d)
    assert errors != []
    assert any("name" in e.lower() for e in errors)

def test_id_missing_email():
    d = {"name": "Alice", "email": "", "career_summary": "x"}
    errors = id_validate(d)
    assert errors != []
    assert any("email" in e.lower() for e in errors)

def test_id_missing_summary():
    d = {"name": "Alice", "email": "a@b.com", "career_summary": ""}
    errors = id_validate(d)
    assert errors != []
    assert any("summary" in e.lower() or "career" in e.lower() for e in errors)

def test_id_whitespace_only_name():
    d = {"name": "   ", "email": "a@b.com", "career_summary": "x"}
    assert id_validate(d) != []

# ── Resume ─────────────────────────────────────────────────────────────────────
from app.wizard.step_resume import validate as resume_validate

def test_resume_no_experience():
    assert resume_validate({"experience": []}) != []

def test_resume_one_entry():
    d = {"experience": [{"company": "Acme", "title": "Engineer", "bullets": ["did stuff"]}]}
    assert resume_validate(d) == []

def test_resume_missing_experience_key():
    assert resume_validate({}) != []

# ── Inference ──────────────────────────────────────────────────────────────────
from app.wizard.step_inference import validate as inf_validate

def test_inference_not_confirmed():
    assert inf_validate({"endpoint_confirmed": False}) != []

def test_inference_confirmed():
    assert inf_validate({"endpoint_confirmed": True}) == []

def test_inference_missing():
    assert inf_validate({}) != []

# ── Search ─────────────────────────────────────────────────────────────────────
from app.wizard.step_search import validate as search_validate

def test_search_valid():
    d = {"job_titles": ["Software Engineer"], "locations": ["Remote"]}
    assert search_validate(d) == []

def test_search_missing_titles():
    d = {"job_titles": [], "locations": ["Remote"]}
    errors = search_validate(d)
    assert errors != []
    assert any("title" in e.lower() for e in errors)

def test_search_missing_locations():
    d = {"job_titles": ["SWE"], "locations": []}
    errors = search_validate(d)
    assert errors != []
    assert any("location" in e.lower() for e in errors)

def test_search_missing_both():
    errors = search_validate({})
    assert len(errors) == 2

def test_search_none_values():
    d = {"job_titles": None, "locations": None}
    assert search_validate(d) != []
