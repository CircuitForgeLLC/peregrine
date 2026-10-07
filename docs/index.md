# Peregrine

**LLM-powered job search pipeline — by [Circuit Forge LLC](https://circuitforge.tech)**

Peregrine automates the full job search lifecycle: discovery, matching, cover letter generation, application tracking, and interview preparation. It is privacy-first and local-first — your data never leaves your machine unless you configure an external integration.

![Peregrine dashboard](screenshots/01-dashboard.png#only-light)
![Peregrine dashboard](screenshots/01-dashboard-dark.png#only-dark)

---

## Quick Start

```bash
# 1. Clone and install dependencies
git clone https://git.circuitforge.tech/Circuit-Forge/peregrine
cd peregrine
bash install.sh

# 2. Start Peregrine
make start                        # no GPU, API-only
make start PROFILE=single-gpu     # one NVIDIA GPU
make start PROFILE=dual-gpu       # dual GPU (Ollama + vLLM)

# 3. Open the UI
# http://localhost:8501
```

The first time you open Peregrine, a short setup checklist walks you through your resume, your profile, and the jobs you want. See [Your First Setup](getting-started/first-run-wizard.md) for a screenshot tour, or [Installation](getting-started/installation.md) for the full install walkthrough.

---

## Feature Overview

| Feature | Free | Paid† | Premium |
|---------|------|-------|---------|
| Job discovery (JobSpy + custom boards) | Yes | Yes | Yes |
| Resume keyword matching | Yes | Yes | Yes |
| Cover letter generation | BYOK‡ | Yes | Yes |
| Company research briefs | BYOK‡ | Yes | Yes |
| Interview prep & practice Q&A | BYOK‡ | Yes | Yes |
| Email sync & auto-classification | - | Yes | Yes |
| Survey assistant (culture-fit Q&A) | BYOK‡ | Yes | Yes |
| Integration connectors (Notion, Airtable, etc.) | Partial | Yes | Yes |
| Calendar sync (Google, Apple) | - | Yes | Yes |
| Cover letter model fine-tuning | - | - | Yes |
| Multi-user support | - | - | Yes |

† **Paid** gives access to CircuitForge's hosted inference — no API key required.  
‡ **BYOK** — configure any LLM backend in `config/llm.yaml` (local Ollama/vLLM or an API key) and these features unlock at no charge, regardless of tier.

See [Tier System](reference/tier-system.md) for the full feature gate table.

---

## Documentation Sections

- **[Your First Setup](getting-started/first-run-wizard.md)**: A screenshot tour of the setup checklist, start here if you are new
- **[Getting Started](getting-started/installation.md)**: Install, configure, and launch Peregrine (self-hosting)
- **[User Guide](user-guide/daily-workflow.md)**: How to use Peregrine day to day, no technical background needed
- **[Developer Guide](developer-guide/contributing.md)**: Add scrapers, integrations, and contribute code
- **[Reference](reference/tier-system.md)**: Tier system, LLM router, and config file schemas

---

## License

Core discovery pipeline: [MIT](https://git.circuitforge.tech/Circuit-Forge/peregrine/src/branch/main/LICENSE-MIT)

AI features (cover letter generation, company research, interview prep, UI): [BSL 1.1](https://git.circuitforge.tech/Circuit-Forge/peregrine/src/branch/main/LICENSE-BSL)

© 2026 Circuit Forge LLC
