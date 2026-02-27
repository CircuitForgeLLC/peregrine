"""Tests for scripts/preflight.py additions: dual-GPU service table, size warning, VRAM check."""
import pytest
from pathlib import Path
from unittest.mock import patch
import yaml
import tempfile
import os


# ── Service table ──────────────────────────────────────────────────────────────

def test_ollama_research_in_services():
    """ollama_research must be in _SERVICES at port 11435."""
    from scripts.preflight import _SERVICES
    assert "ollama_research" in _SERVICES
    _, default_port, env_var, docker_owned, adoptable = _SERVICES["ollama_research"]
    assert default_port == 11435
    assert env_var == "OLLAMA_RESEARCH_PORT"
    assert docker_owned is True
    assert adoptable is True


def test_ollama_research_in_llm_backends():
    """ollama_research must be a standalone key in _LLM_BACKENDS (not nested under ollama)."""
    from scripts.preflight import _LLM_BACKENDS
    assert "ollama_research" in _LLM_BACKENDS
    backend_names = [name for name, _ in _LLM_BACKENDS["ollama_research"]]
    assert "ollama_research" in backend_names


def test_vllm_research_in_llm_backends():
    """vllm_research must be registered under vllm in _LLM_BACKENDS."""
    from scripts.preflight import _LLM_BACKENDS
    assert "vllm" in _LLM_BACKENDS
    backend_names = [name for name, _ in _LLM_BACKENDS["vllm"]]
    assert "vllm_research" in backend_names


def test_ollama_research_in_docker_internal():
    """ollama_research must map to internal port 11434 (Ollama's container port)."""
    from scripts.preflight import _DOCKER_INTERNAL
    assert "ollama_research" in _DOCKER_INTERNAL
    hostname, port = _DOCKER_INTERNAL["ollama_research"]
    assert hostname == "ollama_research"
    assert port == 11434  # container-internal port is always 11434


def test_ollama_not_mapped_to_ollama_research_backend():
    """ollama service key must only update the ollama llm backend, not ollama_research."""
    from scripts.preflight import _LLM_BACKENDS
    ollama_backend_names = [name for name, _ in _LLM_BACKENDS.get("ollama", [])]
    assert "ollama_research" not in ollama_backend_names


# ── Download size warning ──────────────────────────────────────────────────────

def test_download_size_remote_profile():
    """Remote profile: only searxng + app, no ollama, no vision, no vllm."""
    from scripts.preflight import _download_size_mb
    sizes = _download_size_mb("remote", "ollama")
    assert "searxng" in sizes
    assert "app" in sizes
    assert "ollama" not in sizes
    assert "vision_image" not in sizes
    assert "vllm_image" not in sizes


def test_download_size_cpu_profile():
    """CPU profile: adds ollama image + llama3.2:3b weights."""
    from scripts.preflight import _download_size_mb
    sizes = _download_size_mb("cpu", "ollama")
    assert "ollama" in sizes
    assert "llama3_2_3b" in sizes
    assert "vision_image" not in sizes


def test_download_size_single_gpu_profile():
    """Single-GPU: adds vision image + moondream2 weights."""
    from scripts.preflight import _download_size_mb
    sizes = _download_size_mb("single-gpu", "ollama")
    assert "vision_image" in sizes
    assert "moondream2" in sizes
    assert "vllm_image" not in sizes


def test_download_size_dual_gpu_ollama_mode():
    """dual-gpu + ollama mode: no vllm image."""
    from scripts.preflight import _download_size_mb
    sizes = _download_size_mb("dual-gpu", "ollama")
    assert "vllm_image" not in sizes


def test_download_size_dual_gpu_vllm_mode():
    """dual-gpu + vllm mode: adds ~10 GB vllm image."""
    from scripts.preflight import _download_size_mb
    sizes = _download_size_mb("dual-gpu", "vllm")
    assert "vllm_image" in sizes
    assert sizes["vllm_image"] >= 9000  # at least 9 GB


def test_download_size_dual_gpu_mixed_mode():
    """dual-gpu + mixed mode: also includes vllm image."""
    from scripts.preflight import _download_size_mb
    sizes = _download_size_mb("dual-gpu", "mixed")
    assert "vllm_image" in sizes


# ── Mixed-mode VRAM warning ────────────────────────────────────────────────────

def test_mixed_mode_vram_warning_triggered():
    """Should return a warning string when GPU 1 has < 12 GB free in mixed mode."""
    from scripts.preflight import _mixed_mode_vram_warning
    gpus = [
        {"name": "RTX 3090", "vram_total_gb": 24.0, "vram_free_gb": 20.0},
        {"name": "RTX 3090", "vram_total_gb": 24.0, "vram_free_gb": 8.0},  # tight
    ]
    warning = _mixed_mode_vram_warning(gpus, "mixed")
    assert warning is not None
    assert "8.0" in warning or "GPU 1" in warning


def test_mixed_mode_vram_warning_not_triggered_with_headroom():
    """Should return None when GPU 1 has >= 12 GB free."""
    from scripts.preflight import _mixed_mode_vram_warning
    gpus = [
        {"name": "RTX 4090", "vram_total_gb": 24.0, "vram_free_gb": 20.0},
        {"name": "RTX 4090", "vram_total_gb": 24.0, "vram_free_gb": 18.0},  # plenty
    ]
    warning = _mixed_mode_vram_warning(gpus, "mixed")
    assert warning is None


def test_mixed_mode_vram_warning_not_triggered_for_other_modes():
    """Warning only applies in mixed mode."""
    from scripts.preflight import _mixed_mode_vram_warning
    gpus = [
        {"name": "RTX 3090", "vram_total_gb": 24.0, "vram_free_gb": 20.0},
        {"name": "RTX 3090", "vram_total_gb": 24.0, "vram_free_gb": 6.0},
    ]
    assert _mixed_mode_vram_warning(gpus, "ollama") is None
    assert _mixed_mode_vram_warning(gpus, "vllm") is None


# ── update_llm_yaml with ollama_research ──────────────────────────────────────

def test_update_llm_yaml_sets_ollama_research_url_docker_internal():
    """ollama_research backend URL must be set to ollama_research:11434 when Docker-owned."""
    from scripts.preflight import update_llm_yaml

    llm_cfg = {
        "backends": {
            "ollama": {"base_url": "http://old", "type": "openai_compat"},
            "ollama_research": {"base_url": "http://old", "type": "openai_compat"},
            "vllm": {"base_url": "http://old", "type": "openai_compat"},
            "vllm_research": {"base_url": "http://old", "type": "openai_compat"},
            "vision_service": {"base_url": "http://old", "type": "vision_service"},
        }
    }

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.dump(llm_cfg, f)
        tmp_path = Path(f.name)

    ports = {
        "ollama": {
            "resolved": 11434, "external": False, "env_var": "OLLAMA_PORT"
        },
        "ollama_research": {
            "resolved": 11435, "external": False, "env_var": "OLLAMA_RESEARCH_PORT"
        },
        "vllm": {
            "resolved": 8000, "external": False, "env_var": "VLLM_PORT"
        },
        "vision": {
            "resolved": 8002, "external": False, "env_var": "VISION_PORT"
        },
    }

    try:
        with patch("scripts.preflight.LLM_YAML", tmp_path):
            update_llm_yaml(ports)

        result = yaml.safe_load(tmp_path.read_text())
        assert result["backends"]["ollama_research"]["base_url"] == "http://ollama_research:11434/v1"
        assert result["backends"]["vllm_research"]["base_url"] == result["backends"]["vllm"]["base_url"]
    finally:
        tmp_path.unlink()


def test_update_llm_yaml_sets_ollama_research_url_external():
    """When ollama_research is external (adopted), URL uses host.docker.internal:11435."""
    from scripts.preflight import update_llm_yaml

    llm_cfg = {
        "backends": {
            "ollama": {"base_url": "http://old", "type": "openai_compat"},
            "ollama_research": {"base_url": "http://old", "type": "openai_compat"},
        }
    }

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.dump(llm_cfg, f)
        tmp_path = Path(f.name)

    ports = {
        "ollama": {"resolved": 11434, "external": False, "env_var": "OLLAMA_PORT"},
        "ollama_research": {"resolved": 11435, "external": True, "env_var": "OLLAMA_RESEARCH_PORT"},
    }

    try:
        with patch("scripts.preflight.LLM_YAML", tmp_path):
            update_llm_yaml(ports)
        result = yaml.safe_load(tmp_path.read_text())
        assert result["backends"]["ollama_research"]["base_url"] == "http://host.docker.internal:11435/v1"
    finally:
        tmp_path.unlink()
