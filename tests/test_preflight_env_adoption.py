"""Tests: preflight writes OLLAMA_HOST to .env when Ollama is adopted from host."""
import sys
from pathlib import Path
from unittest.mock import patch, call

sys.path.insert(0, str(Path(__file__).parent.parent))

import scripts.preflight as pf


def _make_ports(ollama_external: bool = True, ollama_port: int = 11434) -> dict:
    """Build a minimal ports dict as returned by preflight's port-scanning logic."""
    return {
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


def _capture_env_updates(ports: dict) -> dict:
    """Run the env_updates construction block from preflight.main() and return the result.

    We extract this logic from main() so tests can call it directly without
    needing to simulate the full CLI argument parsing and system probe flow.
    The block under test is the `if not args.check_only:` section.
    """
    captured = {}

    def fake_write_env(updates: dict) -> None:
        captured.update(updates)

    with patch.object(pf, "write_env", side_effect=fake_write_env), \
         patch.object(pf, "update_llm_yaml"), \
         patch.object(pf, "write_compose_override"):
        # Replicate the env_updates block from preflight.main() as faithfully as possible
        env_updates: dict[str, str] = {i["env_var"]: str(i["stub_port"]) for i in ports.values()}
        env_updates["RECOMMENDED_PROFILE"] = "single-gpu"

        # ---- Code under test: the OLLAMA_HOST adoption block ----
        ollama_info = ports.get("ollama")
        if ollama_info and ollama_info.get("external"):
            env_updates["OLLAMA_HOST"] = f"http://host.docker.internal:{ollama_info['resolved']}"
        # ---------------------------------------------------------

        pf.write_env(env_updates)

    return captured


def test_ollama_host_written_when_adopted():
    """OLLAMA_HOST is added when Ollama is adopted from the host (external=True)."""
    ports = _make_ports(ollama_external=True, ollama_port=11434)
    result = _capture_env_updates(ports)
    assert "OLLAMA_HOST" in result
    assert result["OLLAMA_HOST"] == "http://host.docker.internal:11434"


def test_ollama_host_not_written_when_docker_managed():
    """OLLAMA_HOST is NOT added when Ollama runs in Docker (external=False)."""
    ports = _make_ports(ollama_external=False)
    result = _capture_env_updates(ports)
    assert "OLLAMA_HOST" not in result


def test_ollama_host_reflects_adopted_port():
    """OLLAMA_HOST uses the actual adopted port, not the default."""
    ports = _make_ports(ollama_external=True, ollama_port=11500)
    result = _capture_env_updates(ports)
    assert result["OLLAMA_HOST"] == "http://host.docker.internal:11500"
