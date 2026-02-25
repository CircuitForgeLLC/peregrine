# Circuit Forge LLC — Product Brief

**Tagline:** AI for the tasks you hate most.

**Company:** Circuit Forge LLC
**Status:** Proof-of-concept (Peregrine) in active development. All other products deferred until Peregrine proves the model.

---

## The Idea

There is a category of task that is:

- **High-stakes** — getting it wrong has real consequences (denied claim, missed appointment, bad lease)
- **Opaque** — the rules are unclear, the process is inconsistent, the UI is hostile
- **Time-consuming** — hours of hold music, form-filling, or inbox-watching
- **Repeated** — you'll face this again, and so will everyone you know

These tasks are not hard because they require intelligence. They are hard because they are designed — intentionally or by neglect — to exhaust the person trying to complete them. Bureaucratic friction as a feature.

The Circuit Forge model: AI handles the research, drafting, monitoring, and preparation. A human reviews and approves before anything is submitted or committed. For the hardest cases (CAPTCHAs, phone calls, wet signatures), an operator steps in under the Ultra tier.

---

## Architecture

Every Circuit Forge product shares the same underlying scaffold:

```
Monitor / Discover → AI Assist → Human Approval → Execute → Track
```

Implemented as:
- **Pipeline engine** — SQLite staging DB, status machine, background task runner
- **LLM router** — fallback chain across local (Ollama/vLLM) and cloud (Anthropic/OpenAI-compat) backends
- **Wizard** — 7-step first-run onboarding, tier-gated features, crash recovery
- **Integrations** — pluggable connectors (calendar, storage, notifications)
- **Operator interface** — thin admin UI for Ultra tier human-in-the-loop execution

Products are **separate apps** sharing a private `circuitforge-core` package (extracted when the second product begins). Each ships as a Docker Compose stack.

---

## Product Suite

| Product | Domain | Key pain | Status |
|---------|--------|----------|--------|
| **Peregrine** | Job search | Applications, cover letters, interview prep | Active development |
| **Falcon** | Government forms | Benefits, immigration, permits, FAFSA | Backlog |
| **Osprey** | Customer service | IVR queues, complaint letters, dispute tracking | Backlog |
| **Kestrel** | Gov't appointments | DMV, passport, USCIS slot monitoring | Backlog |
| **Harrier** | Insurance | Prior auth, claim disputes, appeals | Backlog |
| **Merlin** | Rentals | Listing monitor, applications, lease review | Backlog |
| **Ibis** | Healthcare | Referrals, waitlists, records, prior auth | Backlog |
| **Tern** | Travel | Flights, itineraries, visas, disruption | Backlog |
| **Wren** | Contractors | Quotes, scope of work, milestones, disputes | Backlog |
| **Martin** | Home / car | Maintenance, scheduling, warranties, recalls | Backlog |

---

## Tiers (across all products)

| Tier | What you get |
|------|-------------|
| **Free** | Core pipeline, basic AI assist, local LLM only |
| **Paid** | Cloud LLM, integrations, email sync, full AI generation suite |
| **Premium** | Fine-tuned models, multi-user, advanced analytics |
| **Ultra** | Human-in-the-loop execution — operator handles what AI can't |

---

## Ultra Tier — Human-in-the-Loop

The hardest tasks can't be fully automated: CAPTCHAs, phone calls, wet signatures, in-person appearances. The Ultra tier provides a trained human operator who:

1. Receives a queued task with all AI-generated context (brief, filled form, talking points)
2. Executes the task (submits the form, makes the call, books the appointment)
3. Marks it complete with an audit trail

The user must explicitly approve each task before the operator acts. Pricing is per-task or bundled, not flat-rate — complexity varies too much.

**Bootstrap strategy:** Waitlist + small trusted operator team to validate the workflow manually before investing in operator tooling. The browser autofill extension (in development for Peregrine) becomes the operator's primary tool across all products.

---

## Naming

All products are named after birds. The names were chosen for:

- **Peregrine** — the peregrine falcon: fastest animal on earth, precise hunter
- **Falcon** — strength, directness, cutting through bureaucracy
- **Osprey** — patient, circles overhead, dives with precision when ready
- **Kestrel** — hovers perfectly still before striking (waiting for the appointment slot)
- **Harrier** — low, fast, persistent — the insurance fight you don't give up on
- **Merlin** — small but fierce; also evokes the wizard (documents, magic)
- **Ibis** — sacred to Thoth, Egyptian god of medicine and healing
- **Tern** — Arctic tern: the world's greatest traveler, pole to pole every year
- **Wren** — legendary nest-builder, meticulous and structural
- **Martin** — house martin: nests on buildings, returns every year to maintain them

---

## What to build next

1. Prove Peregrine: paying users, validated LTV, operator workflow tested
2. Extract `circuitforge-core` when starting the second product
3. Second product TBD based on Peregrine user feedback — likely **Falcon** (government forms) or **Osprey** (customer service) given overlap in skill set and user base
