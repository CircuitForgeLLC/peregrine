# tests/test_user_profile.py
import pytest
from pathlib import Path
import tempfile, yaml
from scripts.user_profile import UserProfile

@pytest.fixture
def profile_yaml(tmp_path):
    data = {
        "name": "Jane Smith",
        "email": "jane@example.com",
        "phone": "555-1234",
        "linkedin": "linkedin.com/in/janesmith",
        "career_summary": "Experienced CSM with 8 years in SaaS.",
        "nda_companies": ["AcmeCorp"],
        "docs_dir": "~/Documents/JobSearch",
        "ollama_models_dir": "~/models/ollama",
        "vllm_models_dir": "~/models/vllm",
        "inference_profile": "single-gpu",
        "services": {
            "streamlit_port": 8501,
            "ollama_host": "localhost",
            "ollama_port": 11434,
            "ollama_ssl": False,
            "ollama_ssl_verify": True,
            "vllm_host": "localhost",
            "vllm_port": 8000,
            "vllm_ssl": False,
            "vllm_ssl_verify": True,
            "searxng_host": "localhost",
            "searxng_port": 8888,
            "searxng_ssl": False,
            "searxng_ssl_verify": True,
        }
    }
    p = tmp_path / "user.yaml"
    p.write_text(yaml.dump(data))
    return p

def test_loads_fields(profile_yaml):
    p = UserProfile(profile_yaml)
    assert p.name == "Jane Smith"
    assert p.email == "jane@example.com"
    assert p.nda_companies == ["acmecorp"]  # stored lowercase
    assert p.inference_profile == "single-gpu"

def test_service_url_http(profile_yaml):
    p = UserProfile(profile_yaml)
    assert p.ollama_url == "http://localhost:11434"
    assert p.vllm_url == "http://localhost:8000"
    assert p.searxng_url == "http://localhost:8888"

def test_service_url_https(tmp_path):
    data = {
        "name": "X", "services": {
            "ollama_host": "myserver.com", "ollama_port": 443,
            "ollama_ssl": True, "ollama_ssl_verify": True,
            "vllm_host": "localhost", "vllm_port": 8000,
            "vllm_ssl": False, "vllm_ssl_verify": True,
            "searxng_host": "localhost", "searxng_port": 8888,
            "searxng_ssl": False, "searxng_ssl_verify": True,
        }
    }
    p2 = tmp_path / "user2.yaml"
    p2.write_text(yaml.dump(data))
    prof = UserProfile(p2)
    assert prof.ollama_url == "https://myserver.com:443"

def test_nda_mask(profile_yaml):
    p = UserProfile(profile_yaml)
    assert p.is_nda("AcmeCorp")
    assert p.is_nda("acmecorp")  # case-insensitive
    assert not p.is_nda("Google")

def test_missing_file_raises():
    with pytest.raises(FileNotFoundError):
        UserProfile(Path("/nonexistent/user.yaml"))

def test_exists_check(profile_yaml, tmp_path):
    assert UserProfile.exists(profile_yaml)
    assert not UserProfile.exists(tmp_path / "missing.yaml")

def test_docs_dir_expanded(profile_yaml):
    p = UserProfile(profile_yaml)
    assert not str(p.docs_dir).startswith("~")
    assert p.docs_dir.is_absolute()

def test_wizard_defaults(tmp_path):
    p = tmp_path / "user.yaml"
    p.write_text("name: Test\nemail: t@t.com\ncareer_summary: x\n")
    u = UserProfile(p)
    assert u.wizard_complete is False
    assert u.wizard_step == 0
    assert u.tier == "free"
    assert u.dev_tier_override is None
    assert u.dismissed_banners == []

def test_effective_tier_override(tmp_path):
    p = tmp_path / "user.yaml"
    p.write_text("name: T\nemail: t@t.com\ncareer_summary: x\ntier: free\ndev_tier_override: premium\n")
    u = UserProfile(p)
    assert u.effective_tier == "premium"

def test_effective_tier_no_override(tmp_path):
    p = tmp_path / "user.yaml"
    p.write_text("name: T\nemail: t@t.com\ncareer_summary: x\ntier: paid\n")
    u = UserProfile(p)
    assert u.effective_tier == "paid"
