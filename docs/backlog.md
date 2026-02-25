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

## Circuit Forge LLC — Product Expansion ("Heinous Tasks" Platform)

The core insight: the Peregrine pipeline architecture (monitor → AI assist → human approval → execute) is domain-agnostic. Job searching is the proof-of-concept. The same pattern applies to any task that is high-stakes, repetitive, opaque, or just deeply unpleasant.

Each product ships as a **separate app** sharing the same underlying scaffold (pipeline engine, LLM router, background tasks, wizard, tier system, operator interface for Ultra tier). The business is Circuit Forge LLC; the brand positioning is: *"AI for the tasks you hate most."*

### Candidate products (rough priority order)

- **Falcon** — Government form assistance. Benefits applications, disability claims, FAFSA, immigration forms, small business permits. AI pre-fills from user profile, flags ambiguous questions, generates supporting statements. High value: mistakes here are costly and correction is slow.

- **Osprey** — Customer service queue management. Monitors hold queues, auto-navigates IVR trees via speech synthesis, escalates to human agent at the right moment, drafts complaint letters and dispute emails with the right tone and regulatory citations (CFPB, FCC, etc.). Tracks ticket status across cases.

- **Kestrel** — DMV / government appointment booking. Monitors appointment availability for DMV, passport offices, Social Security offices, USCIS biometrics, etc. Auto-books the moment a slot opens. Sends reminders with checklist of required documents.

- **Harrier** — Insurance navigation. Prior authorization tracking, claim dispute drafting, EOB reconciliation, appeal letters. High willingness-to-pay: a denied $50k claim is worth paying to fight.

- **Merlin** — Rental / housing applications. Monitors listings, auto-applies to matching properties, generates cover letters for competitive rental markets (NYC, SF), tracks responses, flags lease red flags.

- **Hobby** — Healthcare scheduling & coordination. Referral tracking, specialist waitlist monitoring, prescription renewal reminders, medical record request management.

### Shared architecture decisions

- **Separate repos, shared `circuitforge-core` package** — pipeline engine, LLM router, background task runner, wizard framework, tier system, operator interface all extracted into a private PyPI package that each product imports.
- **Same Docker Compose scaffold** — each product is a `compose.yml` away from deployment.
- **Same Ultra tier model** — operator interface reads from product's DB, human-in-the-loop for tasks that can't be automated (CAPTCHAs, phone calls, wet signatures).
- **Prove Peregrine first** — don't extract `circuitforge-core` until the second product is actively being built. Premature extraction is over-engineering.

### What makes this viable
- Each domain has the same pain profile: high-stakes, time-sensitive, opaque processes with inconsistent UX.
- Users are highly motivated to pay — the alternative is hours of their own time on hold or filling out forms.
- The human-in-the-loop (Ultra) model handles the hardest cases without requiring full automation.
- Regulatory moat: knowing which citations matter (CFPB for billing disputes, ADA for accommodation requests) is defensible knowledge that gets baked into prompts over time.

---
