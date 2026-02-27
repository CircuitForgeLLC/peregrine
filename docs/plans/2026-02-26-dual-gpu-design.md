# Peregrine — Dual-GPU / Dual-Inference Design

**Date:** 2026-02-26
**Status:** Approved — ready for implementation
**Scope:** Peregrine (reference impl; patterns propagate to future products)

---

## Goal

Replace the fixed `dual-gpu` profile (Ollama + vLLM hardwired to GPU 0 + GPU 1) with a
`DUAL_GPU_MODE` env var that selects which inference stack occupies GPU 1. Simultaneously
add a first-run download size warning to preflight so users know what they're in for before
Docker starts pulling images and models.

---

## Modes

| `DUAL_GPU_MODE` | GPU 0 | GPU 1 | Research backend |
|-----------------|-------|-------|-----------------|
| `ollama` (default) | ollama + vision | ollama_research | `ollama_research` |
| `vllm` | ollama + vision | vllm | `vllm_research` |
| `mixed` | ollama + vision | ollama_research + vllm (VRAM-split) | `vllm_research` → `ollama_research` fallback |

`mixed` requires sufficient VRAM on GPU 1. Preflight warns (not blocks) when GPU 1 has
< 12 GB free before starting in mixed mode.

Cover letters always use `ollama` on GPU 0. Research uses whichever GPU 1 backend is
reachable. The LLM router's `_is_reachable()` check handles this transparently — the
fallback chain simply skips services that aren't running.

---

## Compose Profile Architecture

Docker Compose profiles used to gate which services start per mode.
`DUAL_GPU_MODE` is read by the Makefile and passed as a second `--profile` flag.

### Service → profile mapping

| Service | Profiles |
|---------|---------|
| `ollama` | `cpu`, `single-gpu`, `dual-gpu-ollama`, `dual-gpu-vllm`, `dual-gpu-mixed` |
| `vision` | `single-gpu`, `dual-gpu-ollama`, `dual-gpu-vllm`, `dual-gpu-mixed` |
| `ollama_research` | `dual-gpu-ollama`, `dual-gpu-mixed` |
| `vllm` | `dual-gpu-vllm`, `dual-gpu-mixed` |
| `finetune` | `finetune` |

User-facing profiles remain: `remote`, `cpu`, `single-gpu`, `dual-gpu`.
Sub-profiles (`dual-gpu-ollama`, `dual-gpu-vllm`, `dual-gpu-mixed`) are injected by the
Makefile and never typed by the user.

---

## File Changes

### `compose.yml`

**`ollama`** — add all dual-gpu sub-profiles to `profiles`:
```yaml
profiles: [cpu, single-gpu, dual-gpu-ollama, dual-gpu-vllm, dual-gpu-mixed]
```

**`vision`** — same pattern:
```yaml
profiles: [single-gpu, dual-gpu-ollama, dual-gpu-vllm, dual-gpu-mixed]
```

**`vllm`** — change from `[dual-gpu]` to:
```yaml
profiles: [dual-gpu-vllm, dual-gpu-mixed]
```

**`ollama_research`** — new service:
```yaml
ollama_research:
  image: ollama/ollama:latest
  ports:
    - "${OLLAMA_RESEARCH_PORT:-11435}:11434"
  volumes:
    - ${OLLAMA_MODELS_DIR:-~/models/ollama}:/root/.ollama  # shared — no double download
    - ./docker/ollama/entrypoint.sh:/entrypoint.sh
  environment:
    - OLLAMA_MODELS=/root/.ollama
    - DEFAULT_OLLAMA_MODEL=${OLLAMA_RESEARCH_MODEL:-llama3.2:3b}
  entrypoint: ["/bin/bash", "/entrypoint.sh"]
  profiles: [dual-gpu-ollama, dual-gpu-mixed]
  restart: unless-stopped
```

### `compose.gpu.yml`

Add `ollama_research` block (GPU 1). `vllm` stays on GPU 1 as-is:
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

### `compose.podman-gpu.yml`

Same addition for Podman CDI:
```yaml
ollama_research:
  devices:
    - nvidia.com/gpu=1
  deploy:
    resources:
      reservations:
        devices: []
```

### `Makefile`

Two additions after existing `COMPOSE` detection:

```makefile
DUAL_GPU_MODE ?= $(shell grep -m1 '^DUAL_GPU_MODE=' .env 2>/dev/null | cut -d= -f2 || echo ollama)

# GPU overlay: matches single-gpu, dual-gpu (findstring gpu already covers these)
# Sub-profile injection for dual-gpu modes:
ifeq ($(PROFILE),dual-gpu)
  COMPOSE_FILES += --profile dual-gpu-$(DUAL_GPU_MODE)
endif
```

Update `manage.sh` usage block to document `dual-gpu` profile with `DUAL_GPU_MODE` note:
```
dual-gpu     Ollama + Vision on GPU 0; GPU 1 mode set by DUAL_GPU_MODE
             DUAL_GPU_MODE=ollama  (default) ollama_research on GPU 1
             DUAL_GPU_MODE=vllm             vllm on GPU 1
             DUAL_GPU_MODE=mixed            both on GPU 1 (VRAM-split; see preflight warning)
```

### `scripts/preflight.py`

**1. `_SERVICES` — add `ollama_research`:**
```python
"ollama_research": ("ollama_research_port", 11435, "OLLAMA_RESEARCH_PORT", True, True),
```

**2. `_LLM_BACKENDS` — add entries for both new backends:**
```python
"ollama_research": [("ollama_research", "/v1")],
# vllm_research is an alias for vllm's port — preflight updates base_url for both:
"vllm": [("vllm", "/v1"), ("vllm_research", "/v1")],
```

**3. `_DOCKER_INTERNAL` — add `ollama_research`:**
```python
"ollama_research": ("ollama_research", 11434),  # container-internal port is always 11434
```

**4. `recommend_profile()` — unchanged** (still returns `"dual-gpu"` for 2 GPUs).
Write `DUAL_GPU_MODE=ollama` to `.env` when first setting up a 2-GPU system.

**5. Mixed-mode VRAM warning** — after GPU resource section, before closing line:
```python
dual_gpu_mode = os.environ.get("DUAL_GPU_MODE", "ollama")
if dual_gpu_mode == "mixed" and len(gpus) >= 2:
    if gpus[1]["vram_free_gb"] < 12:
        print(f"║  ⚠  DUAL_GPU_MODE=mixed: GPU 1 has only {gpus[1]['vram_free_gb']:.1f} GB free")
        print(f"║     Running ollama_research + vllm together may cause OOM.")
        print(f"║     Consider DUAL_GPU_MODE=ollama or DUAL_GPU_MODE=vllm instead.")
```

**6. Download size warning** — profile-aware block added just before the closing `╚` line:

```
║  Download sizes (first-run estimates)
║    Docker images
║      ollama/ollama        ~800 MB  (shared by ollama + ollama_research)
║      searxng/searxng      ~300 MB
║      app (Python build)  ~1.5 GB
║      vision service      ~3.0 GB  [single-gpu and above]
║      vllm/vllm-openai   ~10.0 GB  [vllm / mixed mode only]
║
║    Model weights  (lazy-loaded on first use)
║      llama3.2:3b          ~2.0 GB  → OLLAMA_MODELS_DIR
║      moondream2            ~1.8 GB  → vision container cache  [single-gpu+]
║    Note: ollama + ollama_research share the same model dir — no double download
║
║  ⚠  Total first-run: ~X GB  (models persist between restarts)
```

Total is summed at runtime based on active profile + `DUAL_GPU_MODE`.

Size table (used by the warning calculator):
| Component | Size | Condition |
|-----------|------|-----------|
| `ollama/ollama` image | 800 MB | cpu, single-gpu, dual-gpu |
| `searxng/searxng` image | 300 MB | always |
| app image | 1,500 MB | always |
| vision service image | 3,000 MB | single-gpu, dual-gpu |
| `vllm/vllm-openai` image | 10,000 MB | vllm or mixed mode |
| llama3.2:3b weights | 2,000 MB | cpu, single-gpu, dual-gpu |
| moondream2 weights | 1,800 MB | single-gpu, dual-gpu |

### `config/llm.yaml`

**Add `vllm_research` backend:**
```yaml
vllm_research:
  api_key: ''
  base_url: http://host.docker.internal:8000/v1  # same port as vllm; preflight keeps in sync
  enabled: true
  model: __auto__
  supports_images: false
  type: openai_compat
```

**Update `research_fallback_order`:**
```yaml
research_fallback_order:
  - claude_code
  - vllm_research
  - ollama_research
  - github_copilot
  - anthropic
```

`vllm` stays in the main `fallback_order` (cover letters). `vllm_research` is the explicit
research alias for the same service — different config key, same port, makes routing intent
readable in the YAML.

---

## Downstream Compatibility

The LLM router requires no changes. `_is_reachable()` already skips backends that aren't
responding. When `DUAL_GPU_MODE=ollama`, `vllm_research` is unreachable and skipped;
`ollama_research` is up and used. When `DUAL_GPU_MODE=vllm`, the reverse. `mixed` mode
makes both reachable; `vllm_research` wins as the higher-priority entry.

Preflight's `update_llm_yaml()` keeps `base_url` values correct for both adopted (external)
and Docker-internal routing automatically, since `vllm_research` is registered under the
`"vllm"` key in `_LLM_BACKENDS`.

---

## Future Considerations

- **Triple-GPU / 3+ service configs:** When a third product is active, extract this pattern
  into `circuitforge-core` as a reusable inference topology manager.
- **Dual vLLM:** Two vLLM instances (e.g., different model sizes per task) follows the same
  pattern — add `vllm_research` as a separate compose service on its own port.
- **VRAM-aware model selection:** Preflight could suggest smaller models when VRAM is tight
  in mixed mode (e.g., swap llama3.2:3b → llama3.2:1b for the research instance).
- **Queue optimizer (1-GPU / CPU):** When only one inference backend is available and a batch
  of tasks is queued, group by task type (all cover letters first, then all research briefs)
  to avoid repeated model context switches. Tracked separately.
