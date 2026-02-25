# Peregrine — Feature Backlog

Unscheduled ideas and deferred features. Roughly grouped by area.

---

## Settings / Data Management

- **Backup / Restore / Teleport** — Settings panel option to export a full config snapshot (user.yaml + all gitignored configs) as a zip, restore from a snapshot, and "teleport" (export + import to a new machine or Docker volume). Useful for migrations, multi-machine setups, and safe wizard testing.

---

## Cover Letter / Resume Generation

- **Iterative refinement feedback loop** — Apply Workspace cover letter generator: show previous result + a "Feedback / changes requested" text area + "Regenerate" button. Pass `previous_result` and `feedback` through `generate()` in `scripts/generate_cover_letter.py` to the LLM prompt. Same pattern for resume bullet expansion in the wizard (`wizard_generate: expand_bullets`). Backend already supports `previous_result`/`feedback` in `wizard_generate` tasks (added to `_run_wizard_generate`).

---

## Apply / Browser Integration

- **Browser autofill extension** — Chrome/Firefox extension that reads job application forms and auto-fills from the user's profile + generated cover letter; syncs submitted applications back into the pipeline automatically. (Phase 2 paid+ feature per business plan.)

---

## Container Runtime

- **Podman support** — Update `Makefile` to auto-detect `docker compose` vs `podman-compose` (e.g. `COMPOSE ?= $(shell command -v docker 2>/dev/null && echo "docker compose" || echo "podman-compose")`). Note in README that rootless Podman requires CDI GPU device spec (`nvidia.com/gpu=all`) instead of `runtime: nvidia` in `compose.yml`.
- **FastAPI migration path** — When concurrent-user scale demands it: port Streamlit pages to FastAPI + React/HTMX, keep `scripts/` layer unchanged, replace daemon threads with Celery + Redis. The `scripts/` separation already makes this clean.

---

## Email Sync

See also: `docs/plans/email-sync-testing-checklist.md` for outstanding test coverage items.

---
