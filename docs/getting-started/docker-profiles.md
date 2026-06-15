# Docker Profiles

Peregrine uses Docker Compose profiles to start only the services your hardware supports. Choose a profile with `./manage.sh start --profile <name>`.

`manage.sh` delegates to `make`, which auto-detects Docker vs Podman and applies the correct GPU overlay — `compose.gpu.yml` for Docker, `compose.podman-gpu.yml` for Podman (CDI-based). You do not need to specify the overlay manually.

---

## Profile Reference

| Profile | Services started | Use case |
|---------|-----------------|----------|
| `cpu` | `web`, `api`, `ollama`, `searxng` | No GPU. Local models on CPU. Recommended default for new installs. |
| `single-gpu` | `web`, `api`, `ollama`, `vision`, `searxng` | One NVIDIA GPU. Covers cover letters, research, and vision. |
| `dual-gpu` | `web`, `api`, `ollama`, `vllm`, `vision`, `searxng` | Two NVIDIA GPUs. GPU split controlled by `DUAL_GPU_MODE`. |
| `cf-orch` | `web`, `api`, `searxng` | No local LLM. Inference routed to CircuitForge GPU cluster. Requires Paid license. |
| `remote` | `web`, `api`, `searxng` | No local LLM. Inference goes to cloud API keys (Anthropic, OpenAI-compatible). |
| `memory` | (any + memory flag) | Enables RAM-optimised container limits for low-RAM machines. Combine with another profile. |

---

## Service Descriptions

| Service | Image / Source | Host Port | Purpose |
|---------|---------------|-----------|---------|
| `web` | `Dockerfile.web` (Nginx + Vue SPA) | `VUE_PORT` (default 8506) | Main UI — serves the Vue frontend and proxies `/api/` to `api` |
| `api` | `Dockerfile` (FastAPI) | Internal only (proxied through `web`) | REST API — all backend logic |
| `ollama` | `ollama/ollama` | 11434 | Local model inference — cover letters and general tasks |
| `vllm` | `vllm/vllm-openai` | 8000 | High-throughput inference — research tasks |
| `vision` | `scripts/vision_service/` | 8002 | Moondream2 — survey screenshot analysis |
| `searxng` | `searxng/searxng` | 8888 | Private meta-search — company research web scraping |

The `web` container runs Nginx internally on port 80, mapped to `VUE_PORT` on the host. The Nginx config proxies `/api/` requests to `api:8601` — the FastAPI container is not exposed directly.

---

## Choosing a Profile

### cpu

Use `cpu` if:
- You have no GPU but want local inference (good for privacy)
- Acceptable for light use; cover letter generation may take several minutes per request

Pull a model after starting:

```bash
docker exec -it peregrine-ollama-1 ollama pull llama3.2:3b
```

`llama3.2:3b` is the recommended CPU model — it runs on machines with 8 GB of system RAM.

### single-gpu

Use `single-gpu` if:
- You have one NVIDIA GPU with at least 8 GB VRAM
- Recommended for most single-user installs

The vision service (Moondream2) starts on the same GPU using 4-bit quantisation (~1.5 GB VRAM). Pull a model after starting:

```bash
docker exec -it peregrine-ollama-1 ollama pull llama3.1:8b
```

### dual-gpu

Use `dual-gpu` if:
- You have two or more NVIDIA GPUs
- Default: GPU 0 handles Ollama (cover letters), GPU 1 handles vLLM (research)

See [Dual-GPU Modes](#dual-gpu-modes) below to configure how the two GPUs are split.

### cf-orch

Use `cf-orch` if:
- You have access to a CircuitForge GPU cluster running the cf-orch coordinator
- No local GPU required — inference is handled by the cluster
- Requires a Paid or higher license

Set `CF_ORCH_URL` in `.env` to your coordinator address:

```bash
CF_ORCH_URL=http://10.1.10.71:7700
```

The wizard hardware step lets you enter the URL interactively and verifies the connection before saving.

### remote

Use `remote` if:
- You have no local GPU and no cf-orch cluster
- You are using Anthropic Claude, OpenAI, or another cloud API exclusively

Configure at least one external LLM backend in **Settings → LLM Backends** after first login.

### memory (add-on)

Use the `memory` add-on alongside any profile for machines with limited RAM:

```bash
./manage.sh start --profile single-gpu --profile memory
```

This applies conservative container memory limits to prevent the OOM (out-of-memory) killer from terminating containers.

---

## Dual-GPU Modes

When using `dual-gpu`, `DUAL_GPU_MODE` in `.env` controls how the second GPU is used:

| Mode | GPU 0 | GPU 1 | Use case |
|------|-------|-------|----------|
| `mixed` (default) | Ollama | vLLM | Best overall: fast cover letters + high-throughput research |
| `ollama` | Ollama | Ollama | Both GPUs run Ollama; no vLLM; useful if vLLM models are too large for one card |
| `vllm` | vLLM | vLLM | Both GPUs run vLLM (tensor parallel); maximum research throughput |

Set in `.env`:

```bash
DUAL_GPU_MODE=mixed    # default
# DUAL_GPU_MODE=ollama
# DUAL_GPU_MODE=vllm
```

The Makefile expands `dual-gpu` into `--profile dual-gpu-$(DUAL_GPU_MODE)` before passing it to `docker compose`. The `compose.gpu.yml` overlay defines the `dual-gpu-mixed`, `dual-gpu-ollama`, and `dual-gpu-vllm` profile variants.

---

## GPU Memory Guidance

| GPU VRAM | Recommended profile | Notes |
|----------|-------------------|-------|
| < 4 GB | `cpu` | GPU too small for practical model loading |
| 4–8 GB | `single-gpu` | Run smaller models (3B–8B parameters) |
| 8–16 GB | `single-gpu` | Run 8B–13B models comfortably |
| 16–24 GB | `single-gpu` | Run 13B–34B models |
| 24 GB+ (one card) | `single-gpu` | 70B models with quantisation |
| 16+ GB (two cards) | `dual-gpu` | Parallel cover letters + research |

---

## How preflight.py Works

`./manage.sh start` calls `scripts/preflight.py` before launching Docker. Preflight does the following:

1. **Port conflict detection** — checks whether `VUE_PORT`, `OLLAMA_PORT`, `VLLM_PORT`, `SEARXNG_PORT`, and `VISION_PORT` are already in use. Reports any conflicts and suggests alternatives.

2. **External service adoption** — if Ollama or SearXNG are already running on their configured ports (common when using native Ollama on macOS, or a shared SearXNG instance), preflight writes a `compose.override.yml` that stubs out the duplicate containers. The running process is adopted rather than replaced.

3. **GPU enumeration** — queries `nvidia-smi` for GPU count and VRAM per card. On Apple Silicon Macs, falls back to `system_profiler SPDisplaysDataType` and returns unified memory as the VRAM figure.

4. **RAM check** — reads `/proc/meminfo` (Linux) or `vm_stat` (macOS) for available system RAM.

5. **KV cache offload** — if GPU VRAM is less than 10 GB, preflight calculates `CPU_OFFLOAD_GB` and writes it to `.env`. The vLLM container picks this up via `--cpu-offload-gb` to overflow the KV cache to system RAM.

6. **Profile recommendation** — writes `RECOMMENDED_PROFILE` to `.env`. This is informational only; `./manage.sh start --profile <name>` uses the profile you specify.

Run preflight independently at any time:

```bash
./manage.sh preflight
# or
conda run -n cf python scripts/preflight.py
```

---

## Podman Support

Podman is fully supported as a Docker drop-in. `install.sh` detects whether Podman or Docker is available, and `manage.sh`/`make` use it automatically.

### GPU setup for Podman (CDI)

Podman uses the CDI (Container Device Interface) standard for GPU passthrough, rather than Docker's `--gpus all` flag. Generate the CDI spec once after driver installation:

```bash
sudo nvidia-ctk cdi generate --output=/etc/cdi/nvidia.yaml
```

Without this step, GPU profiles start but containers have no GPU access.

### Rootless Podman

Rootless Podman is supported. If you encounter permission errors on the Docker socket, ensure `podman.socket` is running for your user:

```bash
systemctl --user enable --now podman.socket
```

The `make` layer auto-detects rootless Podman and uses `XDG_RUNTIME_DIR/podman/podman.sock` instead of `/var/run/docker.sock`.

---

## Customising Ports

Edit `.env` before running `./manage.sh start`:

```bash
VUE_PORT=8506          # main UI (Vue SPA)
OLLAMA_PORT=11434
VLLM_PORT=8000
SEARXNG_PORT=8888
VISION_PORT=8002
```

All containers read from `.env` via the `env_file` directive in `compose.yml`.

---

## Wizard Test Instance

A separate compose file is available for testing first-run and onboarding wizard flows without touching your main data:

```bash
docker compose -f compose.wizard-test.yml --project-name peregrine-wizard up -d
```

The wizard test instance runs on port **8507** with ephemeral storage — every `docker compose restart` wipes the database back to a clean slate. Uses the same images as the main instance but mounts a minimal LLM config so the wizard detection endpoints work correctly.
