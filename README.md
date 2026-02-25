# Peregrine

**AI-powered job search pipeline — by [Circuit Forge LLC](https://circuitforge.io)**

Automates the full job search lifecycle: discovery → matching → cover letters → applications → interview prep.
Privacy-first, local-first. Your data never leaves your machine.

---

## Quick Start

```bash
git clone https://git.circuitforge.io/circuitforge/peregrine
cd peregrine
cp .env.example .env
docker compose --profile remote up -d
```

Open http://localhost:8501 — the setup wizard will guide you through the rest.

---

## Inference Profiles

| Profile | Services | Use case |
|---------|----------|----------|
| `remote` | app + searxng | No GPU; LLM calls go to Anthropic/OpenAI |
| `cpu` | app + ollama + searxng | No GPU; local models on CPU (slow) |
| `single-gpu` | app + ollama + vision + searxng | One GPU for cover letters + research + vision |
| `dual-gpu` | app + ollama + vllm + vision + searxng | GPU 0 = Ollama, GPU 1 = vLLM |

Set the profile in `.env`:
```bash
# .env
DOCKER_COMPOSE_PROFILES=single-gpu
```

Or select it during the setup wizard.

---

## First-Run Wizard

On first launch, the app shows a 5-step setup wizard:

1. **Hardware Detection** — auto-detects NVIDIA GPUs and suggests a profile
2. **Your Identity** — name, email, career summary (used in cover letters and prompts)
3. **Sensitive Employers** — companies masked as "previous employer (NDA)" in research briefs
4. **Inference & API Keys** — Anthropic/OpenAI keys (remote), or Ollama model (local)
5. **Notion Sync** — optional; syncs jobs to a Notion database

Wizard writes `config/user.yaml`. Re-run by deleting that file.

---

## Email Sync (Optional)

Peregrine can monitor your inbox for job-related emails (interview requests, rejections, survey links) and automatically update job stages.

Configure via **Settings → Email** after setup. Requires:
- IMAP access to your email account
- For Gmail: enable IMAP + create an App Password

---

## License

Core discovery pipeline: [MIT](LICENSE-MIT)
AI features (cover letter generation, company research, interview prep): [BSL 1.1](LICENSE-BSL)

© 2026 Circuit Forge LLC
