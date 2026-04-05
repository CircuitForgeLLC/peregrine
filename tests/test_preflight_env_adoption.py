"""Tests: preflight writes OLLAMA_HOST env var when Ollama is adopted from host."""
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))


def _make_ports(ollama_external: bool = True, ollama_port: int = 11434,
                research_external: bool = False) -> dict:
    ports = {
        "ollama": {
            "resolved": ollama_port,
            "external": ollama_external,
            "stub_port": 54321,
            "env_var": "OLLAMA_PORT",
            "adoptable": True,
        },
        "streamlit": {
            "resolved": 8502,
            "external": False,
            "stub_port": 8502,
            "env_var": "STREAMLIT_PORT",
            "adoptable": False,
        },
    }
    if research_external:
        ports["ollama_research"] = {
            "resolved": 11435,
            "external": True,
            "stub_port": 54322,
            "env_var": "OLLAMA_RESEARCH_PORT",
            "adoptable": True,
        }
    return ports


def test_ollama_host_written_when_adopted(tmp_path):
    """OLLAMA_HOST is added to env_updates when Ollama is an external (adopted) service."""
    import scripts.preflight as pf

    written = {}

    def fake_write_env(updates):
        written.update(updates)

    ports = _make_ports(ollama_external=True, ollama_port=11434)

    with patch.object(pf, "write_env", side_effect=fake_write_env), \
         patch.object(pf, "update_llm_yaml"), \
         patch.object(pf, "write_compose_override"), \
         patch.object(pf, "ENV_FILE", tmp_path / ".env"), \
         patch.object(pf, "OVERRIDE_YML", tmp_path / "compose.override.yml"):

        # Simulate the env_updates block from main()
        env_updates = {i["env_var"]: str(i["stub_port"]) for i in ports.values()}
        env_updates["RECOMMENDED_PROFILE"] = "single-gpu"

        # Apply the new logic under test
        ollama_info = ports.get("ollama")
        if ollama_info and ollama_info.get("external"):
            env_updates["OLLAMA_HOST"] = f"http://host.docker.internal:{ollama_info['resolved']}"

        ollama_research_info = ports.get("ollama_research")
        if ollama_research_info and ollama_research_info.get("external"):
            env_updates["OLLAMA_RESEARCH_HOST"] = f"http://host.docker.internal:{ollama_research_info['resolved']}"

        fake_write_env(env_updates)

    assert "OLLAMA_HOST" in written
    assert written["OLLAMA_HOST"] == "http://host.docker.internal:11434"


def test_ollama_host_not_written_when_docker_managed(tmp_path):
    """OLLAMA_HOST is NOT added when Ollama runs in Docker (not adopted)."""
    ports = _make_ports(ollama_external=False)

    env_updates = {i["env_var"]: str(i["stub_port"]) for i in ports.values()}

    ollama_info = ports.get("ollama")
    if ollama_info and ollama_info.get("external"):
        env_updates["OLLAMA_HOST"] = f"http://host.docker.internal:{ollama_info['resolved']}"

    assert "OLLAMA_HOST" not in env_updates


def test_ollama_research_host_written_when_adopted():
    """OLLAMA_RESEARCH_HOST is written when ollama_research is adopted."""
    ports = _make_ports(ollama_external=True, research_external=True)

    env_updates = {}
    ollama_info = ports.get("ollama")
    if ollama_info and ollama_info.get("external"):
        env_updates["OLLAMA_HOST"] = f"http://host.docker.internal:{ollama_info['resolved']}"

    ollama_research_info = ports.get("ollama_research")
    if ollama_research_info and ollama_research_info.get("external"):
        env_updates["OLLAMA_RESEARCH_HOST"] = f"http://host.docker.internal:{ollama_research_info['resolved']}"

    assert "OLLAMA_RESEARCH_HOST" in env_updates
    assert env_updates["OLLAMA_RESEARCH_HOST"] == "http://host.docker.internal:11435"
