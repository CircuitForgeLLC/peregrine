# Installation

This page walks through a full Peregrine installation from scratch.

---

## Prerequisites

- **Git** — to clone the repository
- **Internet connection** — `install.sh` downloads Docker/Podman and other dependencies
- **Operating system**: Ubuntu/Debian, Fedora/RHEL, Arch Linux, or macOS (with Docker Desktop)

!!! warning "Windows"
    Windows is not supported. Use [WSL2 with Ubuntu](https://docs.microsoft.com/windows/wsl/install) instead.

---

## Step 1 — Clone the repository

```bash
git clone https://git.opensourcesolarpunk.com/Circuit-Forge/peregrine
cd peregrine
```

---

## Step 2 — Run install.sh

```bash
bash install.sh
```

`install.sh` performs the following automatically:

1. **Detects your platform** (Ubuntu/Debian, Fedora/RHEL, Arch, macOS)
2. **Installs Git** if not already present
3. **Installs Docker Engine** (or Podman if Docker is not available) via official repositories
4. **Adds your user to the `docker` group** so you do not need `sudo` for docker commands (Linux only — log out and back in after this)
5. **Detects NVIDIA GPUs** — if `nvidia-smi` is present and working, installs the NVIDIA Container Toolkit and configures Docker/Podman to use it
6. **Creates `.env` from `.env.example`** — edit `.env` to customise ports and model storage paths before starting

!!! note "macOS"
    `install.sh` installs Docker Desktop via Homebrew (`brew install --cask docker`) then exits. Open Docker Desktop, start it, then re-run the script. Ollama can also run natively for Metal GPU-accelerated inference — see the macOS note in Step 4.

!!! note "GPU requirement"
    For GPU support, `nvidia-smi` must return output before you run `install.sh`. Install your NVIDIA driver first.

---

## Step 2a — Podman users: GPU CDI setup

If you prefer rootless Podman over Docker, `install.sh` detects it and manages.sh/make use it automatically. For GPU profiles to work with Podman you must generate a CDI spec first:

```bash
sudo nvidia-ctk cdi generate --output=/etc/cdi/nvidia.yaml
```

This needs to be done once after driver installation. Without it, GPU profiles will start but containers will not have GPU access. Docker users can skip this step — Docker uses `--gpus all` instead of CDI.

---

## Step 3 — (Optional) Edit .env

The `.env` file controls ports and volume mount paths. The defaults work for most single-user installs:

```bash
# Main UI port
VUE_PORT=8506

# Model paths — use full absolute paths, not ~ (tilde does not expand inside containers)
DOCS_DIR=/home/yourname/Documents/JobSearch
OLLAMA_MODELS_DIR=/home/yourname/models/ollama

# Inference model defaults
OLLAMA_DEFAULT_MODEL=llama3.2:3b

# External API keys — only needed for the "remote" profile or BYOK unlock
ANTHROPIC_API_KEY=
```

Change `VUE_PORT` if 8506 is taken on your machine. See [Docker Profiles](docker-profiles.md) for a full port reference.

---

## Step 4 — Start Peregrine

Choose a profile based on your hardware:

```bash
./manage.sh start                        # cpu — local Ollama on CPU (recommended default)
./manage.sh start --profile single-gpu   # one NVIDIA GPU
./manage.sh start --profile dual-gpu     # two NVIDIA GPUs
./manage.sh start --profile remote       # no local LLM — use cloud API keys only
```

`manage.sh start` runs `preflight.py` first, which checks for port conflicts and writes GPU/RAM recommendations to `.env`. Then it calls `docker compose` (or `podman compose`) with the right compose file overlay for your hardware.

!!! tip "macOS with native Ollama"
    If you installed Ollama natively via Homebrew for Metal GPU inference, start with `--profile cpu`. The container API on port 8506 connects to your host's Ollama at `localhost:11434` automatically.

---

## Step 5 — Open the UI

Navigate to **http://localhost:8506** (or whatever `VUE_PORT` you set).

The first-run wizard launches automatically. See [First-Run Wizard](first-run-wizard.md) for a step-by-step guide.

---

## Supported Platforms

| Platform | Tested | Notes |
|----------|--------|-------|
| Ubuntu 22.04 / 24.04 | Yes | Primary target |
| Debian 12 | Yes | |
| Fedora 39/40 | Yes | |
| RHEL / Rocky / AlmaLinux | Yes | |
| Arch Linux / Manjaro | Yes | |
| macOS (Apple Silicon) | Yes | Docker Desktop required; GPU via native Ollama (Metal) |
| macOS (Intel) | Yes | Docker Desktop required; no GPU support |
| Windows | No | Use WSL2 with Ubuntu |

---

## GPU Support

Only NVIDIA GPUs are supported. AMD ROCm is not currently supported.

Requirements:

- NVIDIA driver installed and `nvidia-smi` working before running `install.sh`
- CUDA 12.x recommended (CUDA 11.x may work but is untested)
- Minimum 8 GB VRAM for `single-gpu` profile with default models
- **Podman users:** CDI spec required — see Step 2a above

For `dual-gpu`, both cards must be NVIDIA. GPU 0 handles Ollama (cover letters, general tasks) and GPU 1 handles the research workload. The exact behaviour is controlled by `DUAL_GPU_MODE` — see [Docker Profiles](docker-profiles.md#dual-gpu-modes).

If your GPU has less than 10 GB VRAM, `preflight.py` calculates a `CPU_OFFLOAD_GB` value and writes it to `.env`. The vLLM container picks this up via `--cpu-offload-gb` to overflow KV cache to system RAM.

---

## Stopping Peregrine

```bash
./manage.sh stop       # stop all containers
./manage.sh restart    # stop then start again (runs preflight first)
```

---

## Reinstalling / Clean State

```bash
./manage.sh clean      # removes containers, images, and data volumes (destructive)
```

You will be prompted to type `yes` to confirm.
