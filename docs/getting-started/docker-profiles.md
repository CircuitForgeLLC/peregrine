# Docker Profiles

Peregrine uses Docker Compose profiles to start only the services your hardware can support. Choose a profile with `make start PROFILE=<name>`.

---

## Profile Reference

| Profile | Services started | Use case |
|---------|----------------|----------|
| `remote` | `app`, `searxng` | No GPU. LLM calls go to an external API (Anthropic, OpenAI-compatible). |
| `cpu` | `app`, `ollama`, `searxng` | No GPU. Runs local models on CPU — functional but slow. |
| `single-gpu` | `app`, `ollama`, `vision`, `searxng` | One NVIDIA GPU. Covers cover letters, research, and vision (survey screenshots). |
| `dual-gpu` | `app`, `ollama`, `vllm`, `vision`, `searxng` | Two NVIDIA GPUs. GPU 0 = Ollama (cover letters), GPU 1 = vLLM (research). |

---

## Service Descriptions

| Service | Image / Source | Port | Purpose |
|---------|---------------|------|---------|
| `app` | `Dockerfile` (Streamlit) | 8501 | The main Peregrine UI |
| `ollama` | `ollama/ollama` | 11434 | Local model inference — cover letters and general tasks |
| `vllm` | `vllm/vllm-openai` | 8000 | High-throughput local inference — research tasks |
| `vision` | `scripts/vision_service/` | 8002 | Moondream2 — survey screenshot analysis |
| `searxng` | `searxng/searxng` | 8888 | Private meta-search engine — company research web scraping |

---

## Choosing a Profile

### remote

Use `remote` if:
- You have no NVIDIA GPU
- You plan to use Anthropic Claude or another API-hosted model exclusively
- You want the fastest startup (only two containers)

You must configure at least one external LLM backend in **Settings → LLM Backends**.

### cpu

Use `cpu` if:
- You have no GPU but want to run models locally (e.g. for privacy)
- Acceptable for light use; cover letter generation may take several minutes per request

Pull a model after the container starts:

```bash
docker exec -it peregrine-ollama-1 ollama pull llama3.1:8b
```

### single-gpu

Use `single-gpu` if:
- You have one NVIDIA GPU with at least 8 GB VRAM
- Recommended for most single-user installs
- The vision service (Moondream2) starts on the same GPU using 4-bit quantisation (~1.5 GB VRAM)

### dual-gpu

Use `dual-gpu` if:
- You have two or more NVIDIA GPUs
- GPU 0 handles Ollama (cover letters, quick tasks)
- GPU 1 handles vLLM (research, long-context tasks)
- The vision service shares GPU 0 with Ollama

---

## GPU Memory Guidance

| GPU VRAM | Recommended profile | Notes |
|----------|-------------------|-------|
| < 4 GB | `cpu` | GPU too small for practical model loading |
| 4–8 GB | `single-gpu` | Run smaller models (3B–8B parameters) |
| 8–16 GB | `single-gpu` | Run 8B–13B models comfortably |
| 16–24 GB | `single-gpu` | Run 13B–34B models |
| 24 GB+ | `single-gpu` or `dual-gpu` | 70B models with quantisation |

---

## How preflight.py Works

`make start` calls `scripts/preflight.py` before launching Docker. Preflight does the following:

1. **Port conflict detection** — checks whether `STREAMLIT_PORT`, `OLLAMA_PORT`, `VLLM_PORT`, `SEARXNG_PORT`, and `VISION_PORT` are already in use. Reports any conflicts and suggests alternatives.

2. **GPU enumeration** — queries `nvidia-smi` for GPU count and VRAM per card.

3. **RAM check** — reads `/proc/meminfo` (Linux) or `vm_stat` (macOS) to determine available system RAM.

4. **KV cache offload** — if GPU VRAM is less than 10 GB, preflight calculates `CPU_OFFLOAD_GB` (the amount of KV cache to spill to system RAM) and writes it to `.env`. The vLLM container picks this up via `--cpu-offload-gb`.

5. **Profile recommendation** — writes `RECOMMENDED_PROFILE` to `.env`. This is informational; `make start` uses the `PROFILE` variable you specify (defaulting to `remote`).

You can run preflight independently:

```bash
make preflight
# or
python scripts/preflight.py
```

---

## Customising Ports

Edit `.env` before running `make start`:

```bash
STREAMLIT_PORT=8501
OLLAMA_PORT=11434
VLLM_PORT=8000
SEARXNG_PORT=8888
VISION_PORT=8002
```

All containers read from `.env` via the `env_file` directive in `compose.yml`.
