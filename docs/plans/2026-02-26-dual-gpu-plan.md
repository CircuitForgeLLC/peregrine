# Dual-GPU / Dual-Inference Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add `DUAL_GPU_MODE=ollama|vllm|mixed` env var that gates which inference service occupies GPU 1 on dual-GPU systems, plus a first-run download size warning in preflight.

**Architecture:** Sub-profiles (`dual-gpu-ollama`, `dual-gpu-vllm`, `dual-gpu-mixed`) are injected alongside `--profile dual-gpu` by the Makefile based on `DUAL_GPU_MODE`. The LLM router requires zero changes — `_is_reachable()` naturally skips backends that aren't running. Preflight gains `ollama_research` as a tracked service and emits a size warning block.

**Tech Stack:** Docker Compose profiles, Python (preflight.py), YAML (llm.yaml, compose files), bash (Makefile, manage.sh)

**Design doc:** `docs/plans/2026-02-26-dual-gpu-design.md`

**Test runner:** `conda run -n job-seeker python -m pytest tests/ -v`

---

### Task 1: Update `config/llm.yaml`

**Files:**
- Modify: `config/llm.yaml`

**Step 1: Add `vllm_research` backend and update `research_fallback_order`**

Open `config/llm.yaml`. After the `vllm:` block, add:

```yaml
  vllm_research:
    api_key: ''
    base_url: http://host.docker.internal:8000/v1
    enabled: true
    model: __auto__
    supports_images: false
    type: openai_compat
```

Replace `research_fallback_order:` section with:

```yaml
research_fallback_order:
- claude_code
- vllm_research
- ollama_research
- github_copilot
- anthropic
```

**Step 2: Verify YAML parses cleanly**

```bash
conda run -n job-seeker python -c "import yaml; yaml.safe_load(open('config/llm.yaml'))"
```

Expected: no output (no error).

**Step 3: Run existing llm config test**

```bash
conda run -n job-seeker python -m pytest tests/test_llm_router.py::test_config_loads -v
```

Expected: PASS

**Step 4: Commit**

```bash
git add config/llm.yaml
git commit -m "feat: add vllm_research backend and update research_fallback_order"
```

---

### Task 2: Write failing tests for preflight changes

**Files:**
- Create: `tests/test_preflight.py`

No existing test file for preflight. Write all tests upfront — they fail until Task 3–5 implement the code.

**Step 1: Create `tests/test_preflight.py`**

```python
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
    # Should map to the ollama_research llm backend
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
        # Patch LLM_YAML to point at our temp file
        with patch("scripts.preflight.LLM_YAML", tmp_path):
            update_llm_yaml(ports)

        result = yaml.safe_load(tmp_path.read_text())
        # Docker-internal: use service name + container port
        assert result["backends"]["ollama_research"]["base_url"] == "http://ollama_research:11434/v1"
        # vllm_research must match vllm's URL
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
```

**Step 2: Run tests to confirm they all fail**

```bash
conda run -n job-seeker python -m pytest tests/test_preflight.py -v 2>&1 | head -50
```

Expected: all FAIL with `ImportError` or `AssertionError` — that's correct.

**Step 3: Commit failing tests**

```bash
git add tests/test_preflight.py
git commit -m "test: add failing tests for dual-gpu preflight additions"
```

---

### Task 3: `preflight.py` — service table additions

**Files:**
- Modify: `scripts/preflight.py:46-67` (`_SERVICES`, `_LLM_BACKENDS`, `_DOCKER_INTERNAL`)

**Step 1: Update `_SERVICES`**

Find the `_SERVICES` dict (currently ends at the `"ollama"` entry). Add `ollama_research` as a new entry:

```python
_SERVICES: dict[str, tuple[str, int, str, bool, bool]] = {
    "streamlit":        ("streamlit_port",        8501,  "STREAMLIT_PORT",        True,  False),
    "searxng":          ("searxng_port",           8888,  "SEARXNG_PORT",          True,  True),
    "vllm":             ("vllm_port",              8000,  "VLLM_PORT",             True,  True),
    "vision":           ("vision_port",            8002,  "VISION_PORT",           True,  True),
    "ollama":           ("ollama_port",            11434, "OLLAMA_PORT",           True,  True),
    "ollama_research":  ("ollama_research_port",   11435, "OLLAMA_RESEARCH_PORT",  True,  True),
}
```

**Step 2: Update `_LLM_BACKENDS`**

Replace the existing dict:

```python
_LLM_BACKENDS: dict[str, list[tuple[str, str]]] = {
    "ollama":          [("ollama", "/v1")],
    "ollama_research": [("ollama_research", "/v1")],
    "vllm":            [("vllm", "/v1"), ("vllm_research", "/v1")],
    "vision":          [("vision_service", "")],
}
```

**Step 3: Update `_DOCKER_INTERNAL`**

Add `ollama_research` entry:

```python
_DOCKER_INTERNAL: dict[str, tuple[str, int]] = {
    "ollama":          ("ollama",          11434),
    "ollama_research": ("ollama_research", 11434),  # container-internal port is always 11434
    "vllm":            ("vllm",            8000),
    "vision":          ("vision",          8002),
    "searxng":         ("searxng",         8080),
}
```

**Step 4: Run service table tests**

```bash
conda run -n job-seeker python -m pytest tests/test_preflight.py::test_ollama_research_in_services tests/test_preflight.py::test_ollama_research_in_llm_backends tests/test_preflight.py::test_vllm_research_in_llm_backends tests/test_preflight.py::test_ollama_research_in_docker_internal tests/test_preflight.py::test_ollama_not_mapped_to_ollama_research_backend tests/test_preflight.py::test_update_llm_yaml_sets_ollama_research_url_docker_internal tests/test_preflight.py::test_update_llm_yaml_sets_ollama_research_url_external -v
```

Expected: all PASS

**Step 5: Commit**

```bash
git add scripts/preflight.py
git commit -m "feat: add ollama_research to preflight service table and LLM backend map"
```

---

### Task 4: `preflight.py` — `_download_size_mb()` pure function

**Files:**
- Modify: `scripts/preflight.py` (add new function after `calc_cpu_offload_gb`)

**Step 1: Add the function**

After `calc_cpu_offload_gb()`, add:

```python
def _download_size_mb(profile: str, dual_gpu_mode: str = "ollama") -> dict[str, int]:
    """
    Return estimated first-run download sizes in MB, keyed by component name.
    Profile-aware: only includes components that will actually be pulled.
    """
    sizes: dict[str, int] = {
        "searxng": 300,
        "app":     1500,
    }
    if profile in ("cpu", "single-gpu", "dual-gpu"):
        sizes["ollama"]      = 800
        sizes["llama3_2_3b"] = 2000
    if profile in ("single-gpu", "dual-gpu"):
        sizes["vision_image"] = 3000
        sizes["moondream2"]   = 1800
    if profile == "dual-gpu" and dual_gpu_mode in ("vllm", "mixed"):
        sizes["vllm_image"] = 10000
    return sizes
```

**Step 2: Run download size tests**

```bash
conda run -n job-seeker python -m pytest tests/test_preflight.py -k "download_size" -v
```

Expected: all PASS

**Step 3: Commit**

```bash
git add scripts/preflight.py
git commit -m "feat: add _download_size_mb() pure function for preflight size warning"
```

---

### Task 5: `preflight.py` — VRAM warning, size report block, DUAL_GPU_MODE default

**Files:**
- Modify: `scripts/preflight.py` (three additions to `main()` and a new helper)

**Step 1: Add `_mixed_mode_vram_warning()` after `_download_size_mb()`**

```python
def _mixed_mode_vram_warning(gpus: list[dict], dual_gpu_mode: str) -> str | None:
    """
    Return a warning string if GPU 1 likely lacks VRAM for mixed mode, else None.
    Only relevant when dual_gpu_mode == 'mixed' and at least 2 GPUs are present.
    """
    if dual_gpu_mode != "mixed" or len(gpus) < 2:
        return None
    free = gpus[1]["vram_free_gb"]
    if free < 12:
        return (
            f"⚠  DUAL_GPU_MODE=mixed: GPU 1 has only {free:.1f} GB free — "
            f"running ollama_research + vllm together may cause OOM. "
            f"Consider DUAL_GPU_MODE=ollama or DUAL_GPU_MODE=vllm."
        )
    return None
```

**Step 2: Run VRAM warning tests**

```bash
conda run -n job-seeker python -m pytest tests/test_preflight.py -k "vram" -v
```

Expected: all PASS

**Step 3: Wire size warning into `main()` report block**

In `main()`, find the closing `print("╚═...═╝")` line. Add the size warning block just before it:

```python
        # ── Download size warning ──────────────────────────────────────────────
        dual_gpu_mode = os.environ.get("DUAL_GPU_MODE", "ollama")
        sizes = _download_size_mb(profile, dual_gpu_mode)
        total_mb = sum(sizes.values())
        print("║")
        print("║  Download sizes (first-run estimates)")
        print("║    Docker images")
        print(f"║      app (Python build)   ~{sizes.get('app', 0):,} MB")
        if "searxng" in sizes:
            print(f"║      searxng/searxng       ~{sizes['searxng']:,} MB")
        if "ollama" in sizes:
            shared_note = "  (shared by ollama + ollama_research)" if profile == "dual-gpu" and dual_gpu_mode in ("ollama", "mixed") else ""
            print(f"║      ollama/ollama         ~{sizes['ollama']:,} MB{shared_note}")
        if "vision_image" in sizes:
            print(f"║      vision service        ~{sizes['vision_image']:,} MB  (torch + moondream)")
        if "vllm_image" in sizes:
            print(f"║      vllm/vllm-openai      ~{sizes['vllm_image']:,} MB")
        print("║    Model weights  (lazy-loaded on first use)")
        if "llama3_2_3b" in sizes:
            print(f"║      llama3.2:3b            ~{sizes['llama3_2_3b']:,} MB  → OLLAMA_MODELS_DIR")
        if "moondream2" in sizes:
            print(f"║      moondream2             ~{sizes['moondream2']:,} MB  → vision container cache")
        if profile == "dual-gpu" and dual_gpu_mode in ("ollama", "mixed"):
            print("║    Note: ollama + ollama_research share model dir — no double download")
        print(f"║  ⚠  Total first-run: ~{total_mb / 1024:.1f} GB  (models persist between restarts)")

        # ── Mixed-mode VRAM warning ────────────────────────────────────────────
        vram_warn = _mixed_mode_vram_warning(gpus, dual_gpu_mode)
        if vram_warn:
            print("║")
            print(f"║  {vram_warn}")
```

**Step 4: Wire `DUAL_GPU_MODE` default into `write_env()` block in `main()`**

In `main()`, find the `if not args.check_only:` block. After `env_updates["PEREGRINE_GPU_NAMES"]`, add:

```python
        # Write DUAL_GPU_MODE default for new 2-GPU setups (don't override user's choice)
        if len(gpus) >= 2:
            existing_env: dict[str, str] = {}
            if ENV_FILE.exists():
                for line in ENV_FILE.read_text().splitlines():
                    if "=" in line and not line.startswith("#"):
                        k, _, v = line.partition("=")
                        existing_env[k.strip()] = v.strip()
            if "DUAL_GPU_MODE" not in existing_env:
                env_updates["DUAL_GPU_MODE"] = "ollama"
```

**Step 5: Add `import os` if not already present at top of file**

Check line 1–30 of `scripts/preflight.py`. `import os` is already present inside `get_cpu_cores()` as a local import — move it to the top-level imports block:

```python
import os  # add alongside existing stdlib imports
```

And remove the local `import os` inside `get_cpu_cores()`.

**Step 6: Run all preflight tests**

```bash
conda run -n job-seeker python -m pytest tests/test_preflight.py -v
```

Expected: all PASS

**Step 7: Smoke-check the preflight report output**

```bash
conda run -n job-seeker python scripts/preflight.py --check-only
```

Expected: report includes the `Download sizes` block near the bottom.

**Step 8: Commit**

```bash
git add scripts/preflight.py
git commit -m "feat: add DUAL_GPU_MODE default, VRAM warning, and download size report to preflight"
```

---

### Task 6: `compose.yml` — `ollama_research` service + profile updates

**Files:**
- Modify: `compose.yml`

**Step 1: Update `ollama` profiles line**

Find:
```yaml
    profiles: [cpu, single-gpu, dual-gpu]
```
Replace with:
```yaml
    profiles: [cpu, single-gpu, dual-gpu-ollama, dual-gpu-vllm, dual-gpu-mixed]
```

**Step 2: Update `vision` profiles line**

Find:
```yaml
    profiles: [single-gpu, dual-gpu]
```
Replace with:
```yaml
    profiles: [single-gpu, dual-gpu-ollama, dual-gpu-vllm, dual-gpu-mixed]
```

**Step 3: Update `vllm` profiles line**

Find:
```yaml
    profiles: [dual-gpu]
```
Replace with:
```yaml
    profiles: [dual-gpu-vllm, dual-gpu-mixed]
```

**Step 4: Add `ollama_research` service**

After the closing lines of the `ollama` service block, add:

```yaml
  ollama_research:
    image: ollama/ollama:latest
    ports:
      - "${OLLAMA_RESEARCH_PORT:-11435}:11434"
    volumes:
      - ${OLLAMA_MODELS_DIR:-~/models/ollama}:/root/.ollama
      - ./docker/ollama/entrypoint.sh:/entrypoint.sh
    environment:
      - OLLAMA_MODELS=/root/.ollama
      - DEFAULT_OLLAMA_MODEL=${OLLAMA_RESEARCH_MODEL:-llama3.2:3b}
    entrypoint: ["/bin/bash", "/entrypoint.sh"]
    profiles: [dual-gpu-ollama, dual-gpu-mixed]
    restart: unless-stopped
```

**Step 5: Validate compose YAML**

```bash
docker compose -f compose.yml config --quiet
```

Expected: no errors.

**Step 6: Commit**

```bash
git add compose.yml
git commit -m "feat: add ollama_research service and update profiles for dual-gpu sub-profiles"
```

---

### Task 7: GPU overlay files — `compose.gpu.yml` and `compose.podman-gpu.yml`

**Files:**
- Modify: `compose.gpu.yml`
- Modify: `compose.podman-gpu.yml`

**Step 1: Add `ollama_research` to `compose.gpu.yml`**

After the `ollama:` block, add:

```yaml
  ollama_research:
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              device_ids: ["1"]
              capabilities: [gpu]
```

**Step 2: Add `ollama_research` to `compose.podman-gpu.yml`**

After the `ollama:` block, add:

```yaml
  ollama_research:
    devices:
      - nvidia.com/gpu=1
    deploy:
      resources:
        reservations:
          devices: []
```

**Step 3: Validate both files**

```bash
docker compose -f compose.yml -f compose.gpu.yml config --quiet
```

Expected: no errors.

**Step 4: Commit**

```bash
git add compose.gpu.yml compose.podman-gpu.yml
git commit -m "feat: assign ollama_research to GPU 1 in Docker and Podman GPU overlays"
```

---

### Task 8: `Makefile` + `manage.sh` — `DUAL_GPU_MODE` injection and help text

**Files:**
- Modify: `Makefile`
- Modify: `manage.sh`

**Step 1: Update `Makefile`**

After the `COMPOSE_OVERRIDE` variable, add `DUAL_GPU_MODE` reading:

```makefile
DUAL_GPU_MODE ?= $(shell grep -m1 '^DUAL_GPU_MODE=' .env 2>/dev/null | cut -d= -f2 || echo ollama)
```

In the GPU overlay block, find:
```makefile
else
  ifneq (,$(findstring gpu,$(PROFILE)))
    COMPOSE_FILES := -f compose.yml $(COMPOSE_OVERRIDE) -f compose.gpu.yml
  endif
endif
```

Replace the `else` branch with:
```makefile
else
  ifneq (,$(findstring gpu,$(PROFILE)))
    COMPOSE_FILES := -f compose.yml $(COMPOSE_OVERRIDE) -f compose.gpu.yml
  endif
endif
ifeq ($(PROFILE),dual-gpu)
  COMPOSE_FILES += --profile dual-gpu-$(DUAL_GPU_MODE)
endif
```

**Step 2: Update `manage.sh` — profiles help block**

Find the profiles section in `usage()`:
```bash
    echo "    dual-gpu     Ollama + Vision + vLLM on GPU 0+1"
```

Replace with:
```bash
    echo "    dual-gpu     Ollama + Vision on GPU 0; GPU 1 set by DUAL_GPU_MODE"
    echo "                 DUAL_GPU_MODE=ollama  (default) ollama_research on GPU 1"
    echo "                 DUAL_GPU_MODE=vllm             vllm on GPU 1"
    echo "                 DUAL_GPU_MODE=mixed            both on GPU 1 (VRAM-split)"
```

**Step 3: Verify Makefile parses**

```bash
make help
```

Expected: help table prints cleanly, no make errors.

**Step 4: Verify manage.sh help**

```bash
./manage.sh help
```

Expected: new dual-gpu description appears in profiles section.

**Step 5: Commit**

```bash
git add Makefile manage.sh
git commit -m "feat: inject DUAL_GPU_MODE sub-profile in Makefile; update manage.sh help"
```

---

### Task 9: Integration smoke test

**Goal:** Verify the full chain works for `DUAL_GPU_MODE=ollama` without actually starting Docker (dry-run compose config check).

**Step 1: Write `DUAL_GPU_MODE=ollama` to `.env` temporarily**

```bash
echo "DUAL_GPU_MODE=ollama" >> .env
```

**Step 2: Dry-run compose config for dual-gpu + dual-gpu-ollama**

```bash
docker compose -f compose.yml -f compose.gpu.yml --profile dual-gpu --profile dual-gpu-ollama config 2>&1 | grep -E "^  [a-z]|image:|ports:"
```

Expected output includes:
- `ollama:` service with port 11434
- `ollama_research:` service with port 11435
- `vision:` service
- `searxng:` service
- **No** `vllm:` service

**Step 3: Dry-run for `DUAL_GPU_MODE=vllm`**

```bash
docker compose -f compose.yml -f compose.gpu.yml --profile dual-gpu --profile dual-gpu-vllm config 2>&1 | grep -E "^  [a-z]|image:|ports:"
```

Expected:
- `ollama:` service (port 11434)
- `vllm:` service (port 8000)
- **No** `ollama_research:` service

**Step 4: Run full test suite**

```bash
conda run -n job-seeker python -m pytest tests/ -v
```

Expected: all existing tests PASS, all new preflight tests PASS.

**Step 5: Clean up `.env` test entry**

```bash
# Remove the test DUAL_GPU_MODE line (preflight will re-write it correctly on next run)
sed -i '/^DUAL_GPU_MODE=/d' .env
```

**Step 6: Final commit**

```bash
git add .env  # in case preflight rewrote it during testing
git commit -m "feat: dual-gpu DUAL_GPU_MODE complete — ollama/vllm/mixed GPU 1 selection"
```
