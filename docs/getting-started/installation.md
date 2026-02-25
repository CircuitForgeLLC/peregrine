# Installation

This page walks through a full Peregrine installation from scratch.

---

## Prerequisites

- **Git** — to clone the repository
- **Internet connection** — `setup.sh` downloads Docker and other dependencies
- **Operating system**: Ubuntu/Debian, Fedora/RHEL, Arch Linux, or macOS (with Docker Desktop)

!!! warning "Windows"
    Windows is not supported. Use [WSL2 with Ubuntu](https://docs.microsoft.com/windows/wsl/install) instead.

---

## Step 1 — Clone the repository

```bash
git clone https://git.circuitforge.io/circuitforge/peregrine
cd peregrine
```

---

## Step 2 — Run setup.sh

```bash
bash setup.sh
```

`setup.sh` performs the following automatically:

1. **Detects your platform** (Ubuntu/Debian, Fedora/RHEL, Arch, macOS)
2. **Installs Git** if not already present
3. **Installs Docker Engine** and the Docker Compose v2 plugin via the official Docker repositories
4. **Adds your user to the `docker` group** so you do not need `sudo` for docker commands (Linux only — log out and back in after this)
5. **Detects NVIDIA GPUs** — if `nvidia-smi` is present and working, installs the NVIDIA Container Toolkit and configures Docker to use it
6. **Creates `.env` from `.env.example`** — edit `.env` to customise ports and model storage paths before starting

!!! note "macOS"
    `setup.sh` installs Docker Desktop via Homebrew (`brew install --cask docker`) then exits. Open Docker Desktop, start it, then re-run the script.

!!! note "GPU requirement"
    For GPU support, `nvidia-smi` must return output before you run `setup.sh`. Install your NVIDIA driver first. The Container Toolkit installation will fail silently if the driver is not present.

---

## Step 3 — (Optional) Edit .env

The `.env` file controls ports and volume mount paths. The defaults work for most single-user installs:

```bash
# Default ports
STREAMLIT_PORT=8501
OLLAMA_PORT=11434
VLLM_PORT=8000
SEARXNG_PORT=8888
VISION_PORT=8002
```

Change `STREAMLIT_PORT` if 8501 is taken on your machine.

---

## Step 4 — Start Peregrine

Choose a profile based on your hardware:

```bash
make start                        # remote — no GPU, use API-only LLMs
make start PROFILE=cpu            # cpu — local models on CPU (slow)
make start PROFILE=single-gpu     # single-gpu — one NVIDIA GPU
make start PROFILE=dual-gpu       # dual-gpu — GPU 0 = Ollama, GPU 1 = vLLM
```

`make start` runs `preflight.py` first, which checks for port conflicts and writes GPU/RAM recommendations back to `.env`. Then it calls `docker compose --profile <PROFILE> up -d`.

---

## Step 5 — Open the UI

Navigate to **http://localhost:8501** (or whatever `STREAMLIT_PORT` you set).

The first-run wizard launches automatically. See [First-Run Wizard](first-run-wizard.md) for a step-by-step guide through all seven steps.

---

## Supported Platforms

| Platform | Tested | Notes |
|----------|--------|-------|
| Ubuntu 22.04 / 24.04 | Yes | Primary target |
| Debian 12 | Yes | |
| Fedora 39/40 | Yes | |
| RHEL / Rocky / AlmaLinux | Yes | |
| Arch Linux / Manjaro | Yes | |
| macOS (Apple Silicon) | Yes | Docker Desktop required; no GPU support |
| macOS (Intel) | Yes | Docker Desktop required; no GPU support |
| Windows | No | Use WSL2 with Ubuntu |

---

## GPU Support

Only NVIDIA GPUs are supported. AMD ROCm is not currently supported.

Requirements:
- NVIDIA driver installed and `nvidia-smi` working before running `setup.sh`
- CUDA 12.x recommended (CUDA 11.x may work but is untested)
- Minimum 8 GB VRAM for `single-gpu` profile with default models
- For `dual-gpu`: GPU 0 is assigned to Ollama, GPU 1 to vLLM

If your GPU has less than 10 GB VRAM, `preflight.py` will calculate a `CPU_OFFLOAD_GB` value and write it to `.env`. The vLLM container picks this up via `--cpu-offload-gb` to overflow KV cache to system RAM.

---

## Stopping Peregrine

```bash
make stop       # stop all containers
make restart    # stop then start again (runs preflight first)
```

---

## Reinstalling / Clean State

```bash
make clean      # removes containers, images, and data volumes (destructive)
```

You will be prompted to type `yes` to confirm.
