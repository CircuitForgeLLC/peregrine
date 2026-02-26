# Peregrine

**AI-powered job search pipeline — by [Circuit Forge LLC](https://circuitforge.io)**

> *"Don't be evil, for real and forever."*

Automates the full job search lifecycle: discovery → matching → cover letters → applications → interview prep.
Privacy-first, local-first. Your data never leaves your machine.

---

## Quick Start

**1. Install dependencies** (Docker, NVIDIA toolkit if needed):

```bash
git clone https://git.circuitforge.io/circuitforge/peregrine
cd peregrine
bash setup.sh
```

**2. Start Peregrine:**

```bash
make start                        # remote profile (API-only, no GPU)
make start PROFILE=single-gpu     # with one GPU
make start PROFILE=dual-gpu       # dual GPU (Ollama + vLLM)
```

**3.** Open http://localhost:8501 — the setup wizard guides you through the rest.

> **macOS:** Docker Desktop must be running before `make start`.
> **Windows:** Not supported — use WSL2 with Ubuntu.

---

## Inference Profiles

| Profile | Services started | Use case |
|---------|-----------------|----------|
| `remote` | app + searxng | No GPU; LLM calls go to Anthropic / OpenAI |
| `cpu` | app + ollama + searxng | No GPU; local models on CPU (slow) |
| `single-gpu` | app + ollama + vision + searxng | One GPU: cover letters, research, vision |
| `dual-gpu` | app + ollama + vllm + vision + searxng | GPU 0 = Ollama, GPU 1 = vLLM |

---

## First-Run Wizard

On first launch the setup wizard walks through seven steps:

1. **Hardware** — detects NVIDIA GPUs and recommends a profile
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
| Resume keyword matching | Free |
| Cover letter generation | Paid |
| Company research briefs | Paid |
| Interview prep & practice Q&A | Paid |
| Email sync & auto-classification | Paid |
| Survey assistant (culture-fit Q&A) | Paid |
| Integration connectors (Notion, Airtable, Google Sheets, etc.) | Paid |
| Calendar sync (Google, Apple) | Paid |
| Cover letter model fine-tuning | Premium |
| Multi-user support | Premium |

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

## Developer Docs

Full documentation at: https://docs.circuitforge.io/peregrine

- [Installation guide](https://docs.circuitforge.io/peregrine/getting-started/installation/)
- [Adding a custom job board scraper](https://docs.circuitforge.io/peregrine/developer-guide/adding-scrapers/)
- [Adding an integration](https://docs.circuitforge.io/peregrine/developer-guide/adding-integrations/)
- [Contributing](https://docs.circuitforge.io/peregrine/developer-guide/contributing/)

---

## License

Core discovery pipeline: [MIT](LICENSE-MIT)
AI features (cover letter generation, company research, interview prep, UI): [BSL 1.1](LICENSE-BSL)

© 2026 Circuit Forge LLC
