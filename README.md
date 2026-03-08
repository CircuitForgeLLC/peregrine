# Peregrine

> **Primary development** happens at [git.opensourcesolarpunk.com](https://git.opensourcesolarpunk.com/pyr0ball/peregrine) — GitHub and Codeberg are push mirrors. Issues and PRs are welcome on either platform.

[![License: BSL 1.1](https://img.shields.io/badge/License-BSL_1.1-blue.svg)](./LICENSE-BSL)
[![CI](https://github.com/CircuitForge/peregrine/actions/workflows/ci.yml/badge.svg)](https://github.com/CircuitForge/peregrine/actions/workflows/ci.yml)

**AI-powered job search pipeline — by [Circuit Forge LLC](https://circuitforge.tech)**

> *"Don't be evil, for real and forever."*

Automates the full job search lifecycle: discovery → matching → cover letters → applications → interview prep.
Privacy-first, local-first. Your data never leaves your machine.

---

## Quick Start

**1. Clone and install dependencies** (Docker, NVIDIA toolkit if needed):

```bash
git clone https://git.opensourcesolarpunk.com/pyr0ball/peregrine
cd peregrine
./manage.sh setup
```

**2. Start Peregrine:**

```bash
./manage.sh start                          # remote profile (API-only, no GPU)
./manage.sh start --profile cpu            # local Ollama (CPU, or Metal GPU on Apple Silicon — see below)
./manage.sh start --profile single-gpu    # Ollama + Vision on GPU 0  (NVIDIA only)
./manage.sh start --profile dual-gpu      # Ollama + Vision + vLLM (GPU 0 + 1)  (NVIDIA only)
```

Or use `make` directly:

```bash
make start                        # remote profile
make start PROFILE=single-gpu
```

**3.** Open http://localhost:8501 — the setup wizard guides you through the rest.

> **macOS / Apple Silicon:** Docker Desktop must be running. For Metal GPU-accelerated inference, install Ollama natively before starting — `setup.sh` will prompt you to do this. See [Apple Silicon GPU](#apple-silicon-gpu) below.
> **Windows:** Not supported — use WSL2 with Ubuntu.

### Installing to `/opt` or other system directories

If you clone into a root-owned directory (e.g. `sudo git clone ... /opt/peregrine`), two things need fixing:

**1. Git ownership warning** (`fatal: detected dubious ownership`) — `./manage.sh setup` fixes this automatically. If you need git to work *before* running setup:

```bash
git config --global --add safe.directory /opt/peregrine
```

**2. Preflight write access** — preflight writes `.env` and `compose.override.yml` into the repo directory. Fix ownership once:

```bash
sudo chown -R $USER:$USER /opt/peregrine
```

After that, run everything without `sudo`.

### Podman

Podman is rootless by default — **no `sudo` needed.** `./manage.sh setup` will configure `podman-compose` if it isn't already present.

### Docker

After `./manage.sh setup`, log out and back in for docker group membership to take effect. Until then, prefix commands with `sudo`. After re-login, `sudo` is no longer required.

---

## Inference Profiles

| Profile | Services started | Use case |
|---------|-----------------|----------|
| `remote` | app + searxng | No GPU; LLM calls go to Anthropic / OpenAI |
| `cpu` | app + ollama + searxng | No GPU; local models on CPU. On Apple Silicon, use with native Ollama for Metal acceleration — see below. |
| `single-gpu` | app + ollama + vision + searxng | One **NVIDIA** GPU: cover letters, research, vision |
| `dual-gpu` | app + ollama + vllm + vision + searxng | Two **NVIDIA** GPUs: GPU 0 = Ollama, GPU 1 = vLLM |

### Apple Silicon GPU

Docker Desktop on macOS runs in a Linux VM — it cannot access the Apple GPU. Metal-accelerated inference requires Ollama to run **natively** on the host.

`setup.sh` handles this automatically: it offers to install Ollama via Homebrew, starts it as a background service, and explains what happens next. If Ollama is running on port 11434 when you start Peregrine, preflight detects it, stubs out the Docker Ollama container, and routes inference through the native process — which uses Metal automatically.

To do it manually:

```bash
brew install ollama
brew services start ollama          # starts at login, uses Metal GPU
./manage.sh start --profile cpu     # preflight adopts native Ollama; Docker container is skipped
```

The `cpu` profile label is a slight misnomer in this context — Ollama will be running on the GPU. `single-gpu` and `dual-gpu` profiles are NVIDIA-specific and not applicable on Mac.

---

## First-Run Wizard

On first launch the setup wizard walks through seven steps:

1. **Hardware** — detects NVIDIA GPUs (Linux) or Apple Silicon GPU (macOS) and recommends a profile
2. **Tier** — choose free, paid, or premium (or use `dev_tier_override` for local testing)
3. **Identity** — name, email, phone, LinkedIn, career summary
4. **Resume** — upload a PDF/DOCX for LLM parsing, or use the guided form builder
5. **Inference** — configure LLM backends and API keys
6. **Search** — job titles, locations, boards, keywords, blocklist
7. **Integrations** — optional cloud storage, calendar, and notification services

Wizard state is saved after each step — a crash or browser close resumes where you left off.
Re-enter the wizard any time via **Settings → Developer → Reset wizard**.

---

## Features

| Feature | Tier |
|---------|------|
| Job discovery (JobSpy + custom boards) | Free |
| Resume keyword matching & gap analysis | Free |
| Document storage sync (Google Drive, Dropbox, OneDrive, MEGA, Nextcloud) | Free |
| Webhook notifications (Discord, Home Assistant) | Free |
| **Cover letter generation** | Free with LLM¹ |
| **Company research briefs** | Free with LLM¹ |
| **Interview prep & practice Q&A** | Free with LLM¹ |
| **Survey assistant** (culture-fit Q&A, screenshot analysis) | Free with LLM¹ |
| **AI wizard helpers** (career summary, bullet expansion, skill suggestions) | Free with LLM¹ |
| Managed cloud LLM (no API key needed) | Paid |
| Email sync & auto-classification | Paid |
| Job tracking integrations (Notion, Airtable, Google Sheets) | Paid |
| Calendar sync (Google, Apple) | Paid |
| Slack notifications | Paid |
| CircuitForge shared cover-letter model | Paid |
| Cover letter model fine-tuning (your writing, your model) | Premium |
| Multi-user support | Premium |

¹ **BYOK unlock:** configure any LLM backend — a local [Ollama](https://ollama.com) or vLLM instance,
or your own API key (Anthropic, OpenAI-compatible) — and all AI features marked **Free with LLM**
unlock at no charge. The paid tier earns its price by providing managed cloud inference so you
don't need a key at all, plus integrations and email sync.

---

## Email Sync

Monitors your inbox for job-related emails and automatically updates job stages (interview requests, rejections, survey links, offers).

Configure in **Settings → Email**. Requires IMAP access and, for Gmail, an App Password.

---

## Integrations

Connect external services in **Settings → Integrations**:

- **Job tracking:** Notion, Airtable, Google Sheets
- **Document storage:** Google Drive, Dropbox, OneDrive, MEGA, Nextcloud
- **Calendar:** Google Calendar, Apple Calendar (CalDAV)
- **Notifications:** Slack, Discord (webhook), Home Assistant

---

## CLI Reference (`manage.sh`)

`manage.sh` is the single entry point for all common operations — no need to remember Make targets or Docker commands.

```
./manage.sh setup               Install Docker/Podman + NVIDIA toolkit
./manage.sh start [--profile P] Preflight check then start services
./manage.sh stop                Stop all services
./manage.sh restart             Restart all services
./manage.sh status              Show running containers
./manage.sh logs [service]      Tail logs (default: app)
./manage.sh update              Pull latest images + rebuild app container
./manage.sh preflight           Check ports + resources; write .env
./manage.sh test                Run test suite
./manage.sh prepare-training    Scan docs for cover letters → training JSONL
./manage.sh finetune            Run LoRA fine-tune (needs --profile single-gpu+)
./manage.sh open                Open the web UI in your browser
./manage.sh clean               Remove containers, images, volumes (asks to confirm)
```

---

## Developer Docs

Full documentation at: https://docs.circuitforge.tech/peregrine

- [Installation guide](https://docs.circuitforge.tech/peregrine/getting-started/installation/)
- [Adding a custom job board scraper](https://docs.circuitforge.tech/peregrine/developer-guide/adding-scrapers/)
- [Adding an integration](https://docs.circuitforge.tech/peregrine/developer-guide/adding-integrations/)
- [Contributing](https://docs.circuitforge.tech/peregrine/developer-guide/contributing/)

---

## License

Core discovery pipeline: [MIT](LICENSE-MIT)
AI features (cover letter generation, company research, interview prep, UI): [BSL 1.1](LICENSE-BSL)

© 2026 Circuit Forge LLC
