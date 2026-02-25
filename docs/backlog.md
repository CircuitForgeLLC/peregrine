# Peregrine — Feature Backlog

Unscheduled ideas and deferred features. Roughly grouped by area.

---

## Settings / Data Management

- **Backup / Restore / Teleport** — Settings panel option to export a full config snapshot (user.yaml + all gitignored configs) as a zip, restore from a snapshot, and "teleport" (export + import to a new machine or Docker volume). Useful for migrations, multi-machine setups, and safe wizard testing.
- **Complete Google Drive integration test()** — `scripts/integrations/google_drive.py` `test()` currently only checks that the credentials file exists (TODO comment). Implement actual Google Drive API call using `google-api-python-client` to verify the token works.

---

## First-Run Wizard

- **Wire real LLM test in Step 5 (Inference)** — `app/wizard/step_inference.py` validates an `endpoint_confirmed` boolean flag only. Replace with an actual LLM call: submit a minimal prompt to the configured endpoint, show pass/fail, and only set `endpoint_confirmed: true` on success. Should test whichever backend the user selected (Ollama, vLLM, Anthropic, etc.).

---

## Cover Letter / Resume Generation

- **Iterative refinement feedback loop** — Apply Workspace cover letter generator: show previous result + a "Feedback / changes requested" text area + "Regenerate" button. Pass `previous_result` and `feedback` through `generate()` in `scripts/generate_cover_letter.py` to the LLM prompt. Same pattern for resume bullet expansion in the wizard (`wizard_generate: expand_bullets`). Backend already supports `previous_result`/`feedback` in `wizard_generate` tasks (added to `_run_wizard_generate`).
- **Apply Workspace refinement UI ready to wire** — Remaining work: add a "Feedback / changes requested" text area and "Regenerate" button in `app/pages/4_Apply.py`, pass both fields through `submit_task` → `_run_wizard_generate`. Backend is complete.

---

## Apply / Browser Integration

- **Browser autofill extension** — Chrome/Firefox extension that reads job application forms and auto-fills from the user's profile + generated cover letter; syncs submitted applications back into the pipeline automatically. (Phase 2 paid+ feature per business plan.)

---

## Ultra Tier — Managed Applications (White-Glove Service)

- **Concept** — A human-in-the-loop concierge tier where a trained operator submits applications on the user's behalf, powered by AI-generated artifacts (cover letter, company research, survey responses). AI handles ~80% of the work; operator handles form submission, CAPTCHAs, and complex custom questions.
- **Pricing model** — Per-application or bundle pricing rather than flat "X apps/month" — application complexity varies too much for flat pricing to be sustainable.
- **Operator interface** — Thin admin UI (separate from user-facing app) that reads from the same `staging.db`: shows candidate profile, job listing, generated cover letter, company brief, and a "Mark submitted" button. New job status `queued_for_operator` to represent the handoff.
- **Key unlock** — Browser autofill extension (above) becomes the operator's primary tool; pre-fills forms from profile + cover letter, operator reviews and submits.
- **Tier addition** — Add `"ultra"` to `TIERS` in `app/wizard/tiers.py`; gate `"managed_applications"` feature. The existing tier system is designed to accommodate this cleanly.
- **Quality / trust** — Each submission requires explicit per-job user approval before operator acts. Full audit trail (who submitted, when, what was sent). Clear ToS around representation.
- **Bootstrap strategy** — Waitlist + small trusted operator team initially to validate workflow before scaling or automating further. Don't build operator tooling until the manual flow is proven.

---

## Container Runtime

- **Podman support** — Update `Makefile` to auto-detect `docker compose` vs `podman-compose` (e.g. `COMPOSE ?= $(shell command -v docker 2>/dev/null && echo "docker compose" || echo "podman-compose")`). Note in README that rootless Podman requires CDI GPU device spec (`nvidia.com/gpu=all`) instead of `runtime: nvidia` in `compose.yml`.
- **FastAPI migration path** — When concurrent-user scale demands it: port Streamlit pages to FastAPI + React/HTMX, keep `scripts/` layer unchanged, replace daemon threads with Celery + Redis. The `scripts/` separation already makes this clean.

---

## Email Sync

See also: `docs/plans/email-sync-testing-checklist.md` for outstanding test coverage items.

---
