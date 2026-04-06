# Peregrine — Feature Backlog

Unscheduled ideas and deferred features. Roughly grouped by area.

See also: `circuitforge-plans/shared/2026-03-07-launch-checklist.md` for pre-launch blockers
(legal docs, Stripe live keys, website deployment, demo DB ownership fix).

---

## Launch Blockers (tracked in shared launch checklist)

- **ToS + Refund Policy** — required before live Stripe charges. Files go in `website/content/legal/`.
- **Stripe live key rotation** — swap test keys to live in `website/.env` (zero code changes).
- **Website deployment to bastion** — Caddy route for Nuxt frontend at `circuitforge.tech`.
- **Demo DB ownership** — `demo/data/staging.db` is root-owned (Docker artifact); fix with `sudo chown alan:alan` then re-run `demo/seed_demo.py`.

---

## Post-Launch / Infrastructure

- **Accessibility Statement** — WCAG 2.1 conformance doc at `website/content/legal/accessibility.md`. High credibility value for ND audience.
- **Data deletion request process** — published procedure at `website/content/legal/data-deletion.md` (GDPR/CCPA; references `privacy@circuitforge.tech`).
- **Uptime Kuma monitors** — 6 monitors need to be added manually (website, Heimdall, demo, Directus, Forgejo, Peregrine container health).
- **Directus admin password rotation** — change from `changeme-set-via-ui-on-first-run` before website goes public.

---

## Discovery — Community Scraper Plugin System

Design doc: `circuitforge-plans/peregrine/2026-03-07-community-scraper-plugin-design.md`

**Summary:** Add a `scripts/plugins/` directory with auto-discovery and a documented MIT-licensed
plugin API. Separates CF-built custom scrapers (paid, BSL 1.1, in `scripts/custom_boards/`) from
community-contributed and CF-freebie scrapers (free, MIT, in `scripts/plugins/`).

**Implementation tasks:**
- [ ] Add `scripts/plugins/` with `__init__.py`, `README.md`, and `example_plugin.py`
- [ ] Add `config/plugins/` directory with `.gitkeep`; gitignore `config/plugins/*.yaml` (not `.example`)
- [ ] Update `discover.py`: `load_plugins()` auto-discovery + tier gate (`custom_boards` = paid, `plugins` = free)
- [ ] Update `search_profiles.yaml` schema: add `plugins:` list + `plugin_config:` block
- [ ] Migrate `scripts/custom_boards/craigslist.py` → `scripts/plugins/craigslist.py` (CF freebie)
- [ ] Settings UI: render `CONFIG_SCHEMA` fields for installed plugins (Settings → Search)
- [ ] Rewrite `docs/developer-guide/adding-scrapers.md` to document the plugin API
- [ ] Add `scripts/plugins/LICENSE` (MIT) to make the dual-license split explicit

**CF freebie candidates** (future, after plugin system ships):
- Dice.com (tech-focused, no API key)
- We Work Remotely (remote-only, clean HTML)
- Wellfound / AngelList (startup roles)

---

## Discovery — Jobgether Non-Headless Scraper

Design doc: `peregrine/docs/superpowers/specs/2026-03-15-jobgether-integration-design.md`

**Background:** Headless Playwright is blocked by Cloudflare Turnstile on all `jobgether.com` pages.
A non-headless Playwright instance backed by `Xvfb` (virtual framebuffer) renders as a real browser and
bypasses Turnstile. Heimdall already has Xvfb available.

**Live-inspection findings (2026-03-15):**
- Search URL: `https://jobgether.com/search-offers?keyword=<query>`
- Job cards: `div.new-opportunity` — one per listing
- Card URL: `div.new-opportunity > a[href*="/offer/"]` (`href` attr)
- Title: `#offer-body h3`
- Company: `#offer-body p.font-medium`
- Dedup: existing URL-based dedup in `discover.py` covers Jobgether↔other-board overlap

**Implementation tasks (blocked until Xvfb-Playwright integration is in place):**
- [ ] Add `Xvfb` launch helper to `scripts/custom_boards/` (shared util, or inline in scraper)
- [ ] Implement `scripts/custom_boards/jobgether.py` using `p.chromium.launch(headless=False)` with `DISPLAY=:99`
- [ ] Pre-launch `Xvfb :99 -screen 0 1280x720x24` (or assert `DISPLAY` is already set)
- [ ] Register `jobgether` in `discover.py` `CUSTOM_SCRAPERS` (currently omitted — no viable scraper)
- [ ] Add `jobgether` to `custom_boards` in remote-eligible profiles in `config/search_profiles.yaml`
- [ ] Remove or update the "Jobgether discovery scraper — decided against" note in the design spec

**Pre-condition:** Validate Xvfb approach manually (headless=False + `DISPLAY=:99`) before implementing.
The `filter-api.jobgether.com` endpoint still requires auth and `robots.txt` still blocks bots —
confirm Turnstile acceptance is the only remaining blocker before beginning.

---

## Settings / Data Management

- **Backup / Restore / Teleport** — Settings panel option to export a full config snapshot (user.yaml + all gitignored configs) as a zip, restore from a snapshot, and "teleport" (export + import to a new machine or Docker volume). Useful for migrations, multi-machine setups, and safe wizard testing.
- **Complete Google Drive integration test()** — `scripts/integrations/google_drive.py` `test()` currently only checks that the credentials file exists (TODO comment). Implement actual Google Drive API call using `google-api-python-client` to verify the token works.

---

## First-Run Wizard

- **Wire real LLM test in Step 5 (Inference)** — `app/wizard/step_inference.py` validates an `endpoint_confirmed` boolean flag only. Replace with an actual LLM call: submit a minimal prompt to the configured endpoint, show pass/fail, and only set `endpoint_confirmed: true` on success. Should test whichever backend the user selected (Ollama, vLLM, Anthropic, etc.).

---

## LinkedIn Import

Shipped in v0.4.0. Ongoing maintenance and known decisions:

- **Selector maintenance** — LinkedIn changes their DOM periodically. When import stops working, update
  CSS selectors in `scripts/linkedin_utils.py` only (all other files import from there). Real `data-section`
  attribute values (as of 2025 DOM): `summary`, `currentPositionsDetails`, `educationsDetails`,
  `certifications`, `posts`, `volunteering`, `publications`, `projects`.

- **Data export zip is the recommended path for full history** — LinkedIn's unauthenticated public profile
  page is server-side degraded: experience titles, past roles, education, and skills are blurred/omitted.
  Only available without login: name, About summary (truncated), current employer name, certifications.
  The "Import from LinkedIn data export zip" expander (Settings → Resume Profile and Wizard step 3) is the
  correct path for full career history. UI already shows an `ℹ️` callout explaining this.

- **LinkedIn OAuth — decided: not viable** — LinkedIn's OAuth API is restricted to approved partner
  programs. Even if approved, it only grants name + email (not career history, experience, or skills).
  This is a deliberate LinkedIn platform restriction, not a technical gap. Do not pursue this path.

- **Selector test harness** (future) — A lightweight test that fetches a known-public LinkedIn profile
  and asserts at least N fields non-empty would catch DOM breakage before users report it. Low priority
  until selector breakage becomes a recurring support issue.

---

## Cover Letter / Resume Generation

- ~~**Iterative refinement feedback loop**~~ — ✅ Done (`94225c9`): `generate()` accepts `previous_result`/`feedback`; task_runner parses params JSON; Apply Workspace has "Refine with Feedback" expander. Same pattern available for wizard `expand_bullets` via `_run_wizard_generate`.

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

- ~~**Podman support**~~ — ✅ Done: `Makefile` auto-detects `docker compose` / `podman compose` / `podman-compose`; `compose.podman-gpu.yml` CDI override for GPU profiles; `install.sh` detects existing Podman and skips Docker install.
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

- **Merlin** — Rental / housing applications. Monitors listings, auto-applies to matching properties, generates cover letters for competitive rental markets, tracks responses, flags lease red flags.

- **Ibis** — Healthcare coordination. The sacred ibis was the symbol of Thoth, Egyptian god of medicine — the name carries genuine medical heritage. Referral tracking, specialist waitlist monitoring, prescription renewal reminders, medical record request management, prior auth paper trails.

- **Tern** — Travel planning. The Arctic tern makes the longest migration of any animal (44,000 miles/year, pole to pole) — the ultimate traveler. Flight/hotel monitoring, itinerary generation, visa requirement research, travel insurance comparison, rebooking assistance on disruption.

- **Wren** — Contractor engagement. Wrens are legendary nest-builders — meticulous, structural, persistent. Contractor discovery, quote comparison, scope-of-work generation, milestone tracking, dispute documentation, lien waiver management.

- **Martin** — Car / home maintenance. The house martin nests on the exterior of buildings and returns to the same site every year to maintain it — almost too on-the-nose. Service scheduling, maintenance history tracking, recall monitoring, warranty tracking, finding trusted local providers.

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
