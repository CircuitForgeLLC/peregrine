from pathlib import Path
import yaml
from scripts.user_profile import UserProfile
from scripts.generate_llm_config import apply_service_urls


def test_urls_applied_to_llm_yaml(tmp_path):
    user_yaml = tmp_path / "user.yaml"
    user_yaml.write_text(yaml.dump({
        "name": "Test",
        "services": {
            "ollama_host": "myserver", "ollama_port": 11434, "ollama_ssl": False,
            "ollama_ssl_verify": True,
            "vllm_host": "localhost", "vllm_port": 8000, "vllm_ssl": False,
            "vllm_ssl_verify": True,
            "searxng_host": "localhost", "searxng_port": 8888,
            "searxng_ssl": False, "searxng_ssl_verify": True,
        }
    }))
    llm_yaml = tmp_path / "llm.yaml"
    llm_yaml.write_text(yaml.dump({"backends": {
        "ollama":          {"base_url": "http://old:11434/v1", "type": "openai_compat"},
        "ollama_research": {"base_url": "http://old:11434/v1", "type": "openai_compat"},
        "vllm":            {"base_url": "http://old:8000/v1",  "type": "openai_compat"},
    }}))

    profile = UserProfile(user_yaml)
    apply_service_urls(profile, llm_yaml)

    result = yaml.safe_load(llm_yaml.read_text())
    assert result["backends"]["ollama"]["base_url"] == "http://myserver:11434/v1"
    assert result["backends"]["ollama_research"]["base_url"] == "http://myserver:11434/v1"
    assert result["backends"]["vllm"]["base_url"] == "http://localhost:8000/v1"


def test_missing_llm_yaml_is_noop(tmp_path):
    """apply_service_urls should not crash if llm.yaml doesn't exist."""
    user_yaml = tmp_path / "user.yaml"
    user_yaml.write_text(yaml.dump({"name": "Test", "services": {
        "ollama_host": "localhost", "ollama_port": 11434, "ollama_ssl": False,
        "ollama_ssl_verify": True,
        "vllm_host": "localhost", "vllm_port": 8000, "vllm_ssl": False,
        "vllm_ssl_verify": True,
        "searxng_host": "localhost", "searxng_port": 8888,
        "searxng_ssl": False, "searxng_ssl_verify": True,
    }}))
    profile = UserProfile(user_yaml)
    # Should not raise
    apply_service_urls(profile, tmp_path / "nonexistent.yaml")
