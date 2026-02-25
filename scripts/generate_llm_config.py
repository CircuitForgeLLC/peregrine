"""Update config/llm.yaml base_url values from the user profile's services block."""
from pathlib import Path
import yaml
from scripts.user_profile import UserProfile


def apply_service_urls(profile: UserProfile, llm_yaml_path: Path) -> None:
    """Rewrite base_url for ollama, ollama_research, and vllm backends in llm.yaml."""
    if not llm_yaml_path.exists():
        return
    cfg = yaml.safe_load(llm_yaml_path.read_text()) or {}
    urls = profile.generate_llm_urls()
    backends = cfg.get("backends", {})
    for backend_name, url in urls.items():
        if backend_name in backends:
            backends[backend_name]["base_url"] = url
    cfg["backends"] = backends
    llm_yaml_path.write_text(yaml.dump(cfg, default_flow_style=False, allow_unicode=True))
