# Job Seeker Platform — Monetization Business Plan

**Date:** 2026-02-24
**Status:** Draft — pre-VC pitch
**Author:** Brainstorming session

---

## 1. Product Overview

An automated job discovery, resume matching, and application pipeline platform. Built originally as a personal tool for a single job seeker; architecture is already generalized — user identity, preferences, and data are fully parameterized via onboarding, not hardcoded.

### Core pipeline
```
Job Discovery (multi-board) → Resume Matching → Job Review UI
→ Apply Workspace (cover letter + PDF)
→ Interviews Kanban (phone_screen → offer → hired)
→ Notion Sync
```

### Key feature surface
- Multi-board job discovery (LinkedIn, Indeed, Glassdoor, ZipRecruiter, Google, Adzuna, The Ladders)
- LinkedIn Alert email ingestion + email classifier (interview requests, rejections, surveys)
- Resume keyword matching + match scoring
- AI cover letter generation (local model, shared hosted model, or cloud LLM)
- Company research briefs (web scrape + LLM synthesis)
- Interview prep + practice Q&A
- Culture-fit survey assistant with vision/screenshot support
- Application pipeline kanban with stage tracking
- Notion sync for external tracking
- Mission alignment + accessibility preferences (personal decision-making only)
- Per-user fine-tuned cover letter model (trained on user's own writing corpus)

---

## 2. Target Market

### Primary: Individual job seekers (B2C)
- Actively searching, technically comfortable, value privacy
- Frustrated by manual tracking (spreadsheets, Notion boards)
- Want AI-assisted applications without giving their data to a third party
- Typical job search duration: 3–6 months → average subscription length ~4.5 months

### Secondary: Career coaches (B2B, seat-based)
- Manage 10–20 active clients simultaneously
- High willingness to pay for tools that make their service more efficient
- **20× revenue multiplier** vs. solo users (base + per-seat pricing)

### Tertiary: Outplacement firms / staffing agencies (B2B enterprise)
- Future expansion; validates product-market fit at coach tier first

---

## 3. Distribution Model

### Starting point: Local-first (self-hosted)

Users run the application on their own machine via Docker Compose or a native installer. All job data, resume data, and preferences stay local. AI features are optional and configurable — users can use their own LLM backends or subscribe for hosted AI.

**Why local-first:**
- Zero infrastructure cost per free user
- Strong privacy story (no job search data on your servers)
- Reversible — easy to add a hosted SaaS path later without a rewrite
- Aligns with the open core licensing model

### Future path: Cloud Edition (SaaS)

Same codebase deployed as a hosted service. Users sign up at a URL, no install required. Unlocked when revenue and user feedback validate the market.

**Architecture readiness:** The config layer, per-user data isolation, and SQLite-per-user design already support multi-tenancy with minimal refactoring. SaaS is a deployment mode, not a rewrite.

---

## 4. Licensing Strategy

### Open Core

| Component | License | Rationale |
|---|---|---|
| Job discovery pipeline | MIT | Community maintains scrapers (boards break constantly) |
| SQLite schema + `db.py` | MIT | Interoperability, trust |
| Application pipeline state machine | MIT | Core value is visible, auditable |
| Streamlit UI shell | MIT | Community contributions, forks welcome |
| AI cover letter generation | BSL 1.1 | Proprietary prompt engineering + model routing |
| Company research synthesis | BSL 1.1 | LLM orchestration is the moat |
| Interview prep + practice Q&A | BSL 1.1 | Premium feature |
| Survey assistant (vision) | BSL 1.1 | Premium feature |
| Email classifier | BSL 1.1 | Premium feature |
| Notion sync | BSL 1.1 | Integration layer |
| Team / multi-user features | Proprietary | Future enterprise feature |
| Analytics dashboard | Proprietary | Future feature |
| Fine-tuned model weights | Proprietary | Per-user, not redistributable |

**Business Source License (BSL 1.1):** Code is visible and auditable on GitHub. Free for personal, non-commercial self-hosting. Commercial use or SaaS re-hosting requires a paid license. Converts to MIT after 4 years. Used by HashiCorp (Vault, Terraform), MariaDB, and others — well understood by the VC community.

**Why this works here:** The value is not in the code. A competitor could clone the repo and still not have: the fine-tuned model, the user's corpus, the orchestration prompts, or the UX polish. The moat is the system, not any individual file.

---

## 5. Tier Structure

### Free — $0/mo
Self-hosted, local-only. Genuinely useful as a privacy-respecting job tracker.

| Feature | Included |
|---|---|
| Multi-board job discovery | ✓ |
| Custom board scrapers (Adzuna, The Ladders) | ✓ |
| LinkedIn Alert email ingestion | ✓ |
| Add jobs by URL | ✓ |
| Resume keyword matching | ✓ |
| Cover letter generation (local Ollama only) | ✓ |
| Application pipeline kanban | ✓ |
| Mission alignment + accessibility preferences | ✓ |
| Search profiles | 1 |
| AI backend | User's local Ollama |
| Support | Community (GitHub Discussions) |

**Purpose:** Acquisition engine. GitHub stars = distribution. Users who get a job on free tier refer friends.

---

### Paid — $12/mo
For job seekers who want quality AI output without GPU setup or API key management.

Includes everything in Free, plus:

| Feature | Included |
|---|---|
| Shared hosted fine-tuned cover letter model | ✓ |
| Claude API (BYOK — bring your own key) | ✓ |
| Company research briefs | ✓ |
| Interview prep + practice Q&A | ✓ |
| Survey assistant (vision/screenshot) | ✓ |
| Search criteria LLM suggestions | ✓ |
| Email classifier | ✓ |
| Notion sync | ✓ |
| Search profiles | 5 |
| Support | Email |

**Purpose:** Primary revenue tier. High margin, low support burden. Targets the individual job seeker who wants "it just works."

---

### Premium — $29/mo
For power users and career coaches who want best-in-class output and personal model training.

Includes everything in Paid, plus:

| Feature | Included |
|---|---|
| Claude Sonnet (your hosted key, 150 ops/mo included) | ✓ |
| Per-user fine-tuned model (trained on their corpus) | ✓ (one-time onboarding) |
| Corpus re-training | ✓ (quarterly) |
| Search profiles | Unlimited |
| Multi-user / coach mode | ✓ (+$15/seat) |
| Shared job pool across seats | ✓ |
| Priority support + onboarding call | ✓ |

**Purpose:** Highest LTV tier. Coach accounts at 3+ seats generate $59–$239/mo each. Fine-tuned personal model is a high-perceived-value differentiator that costs ~$0.50 to produce.

---

## 6. AI Inference — Claude API Cost Model

Pricing basis: Haiku 4.5 = $0.80/MTok in · $4/MTok out | Sonnet 4.6 = $3/MTok in · $15/MTok out

### Per-operation costs

| Operation | Tokens In | Tokens Out | Haiku | Sonnet |
|---|---|---|---|---|
| Cover letter generation | ~2,400 | ~400 | $0.0035 | $0.013 |
| Company research brief | ~3,000 | ~800 | $0.0056 | $0.021 |
| Survey Q&A (5 questions) | ~3,000 | ~1,500 | $0.0084 | $0.031 |
| Job description enrichment | ~800 | ~300 | $0.0018 | $0.007 |
| Search criteria suggestion | ~400 | ~200 | $0.0010 | $0.004 |

### Monthly inference cost per active user
Assumptions: 12 cover letters, 3 research briefs, 2 surveys, 40 enrichments, 2 search suggestions

| Backend mix | Cost/user/mo |
|---|---|
| Haiku only (paid tier) | ~$0.15 |
| Sonnet only | ~$0.57 |
| Mixed: Sonnet for CL + research, Haiku for rest (premium tier) | ~$0.31 |

### Per-user fine-tuning cost (premium, one-time)
| Provider | Cost |
|---|---|
| User's local GPU | $0 |
| RunPod A100 (~20 min) | $0.25–$0.40 |
| Together AI / Replicate | $0.50–$0.75 |
| Quarterly re-train | Same as above |

**Amortized over 12 months:** ~$0.04–$0.06/user/mo

---

## 7. Full Infrastructure Cost Model

Local-first architecture means most compute runs on the user's machine. Your infra is limited to: AI inference API calls, shared model serving, fine-tune jobs, license/auth server, and storage for model artifacts.

### Monthly infrastructure at 100K users
(4% paid conversion = 4,000 paid; 20% of paid premium = 800 premium)

| Cost center | Detail | Monthly cost |
|---|---|---|
| Claude API inference (paid tier, Haiku) | 4,000 users × $0.15 | $600 |
| Claude API inference (premium tier, mixed) | 800 users × $0.31 | $248 |
| Shared model serving (Together AI, 3B model) | 48,000 requests/mo | $27 |
| Per-user fine-tune jobs | 800 users / 12mo × $0.50 | $33 |
| App hosting (license server, auth API, DB) | VPS + PostgreSQL | $200 |
| Model artifact storage (800 × 1.5GB on S3) | 1.2TB | $28 |
| **Total** | | **$1,136/mo** |

---

## 8. Revenue Model & Unit Economics

### Monthly revenue at scale

| Total users | Paid (4%) | Premium (20% of paid) | Revenue/mo | Infra/mo | **Gross margin** |
|---|---|---|---|---|---|
| 10,000 | 400 | 80 | $7,120 | $196 | **97.2%** |
| 100,000 | 4,000 | 800 | $88,250 | $1,136 | **98.7%** |

### Blended ARPU
- Across all users (including free): **~$0.71/user/mo**
- Across paying users only: **~$17.30/user/mo**
- Coach account (3 seats avg): **~$74/mo**

### LTV per user segment
- Paid individual (4.5mo avg job search): **~$54**
- Premium individual (4.5mo avg): **~$130**
- Coach account (ongoing, low churn): **$74/mo × 18mo estimated = ~$1,330**
- **Note:** Success churn is real — users leave when they get a job. Re-subscription rate on next job search partially offsets this.

### ARR projections

| Scale | ARR |
|---|---|
| 10K users | **~$85K** |
| 100K users | **~$1.06M** |
| 1M users | **~$10.6M** |

To reach $10M ARR: ~1M total users **or** meaningful coach/enterprise penetration at lower user counts.

---

## 9. VC Pitch Angles

### The thesis
> "GitHub is our distribution channel. Local-first is our privacy moat. Coaches are our revenue engine."

### Key metrics to hit before Series A
- 10K GitHub stars (validates distribution thesis)
- 500 paying users (validates willingness to pay)
- 20 coach accounts (validates B2B multiplier)
- 97%+ gross margin (already proven in model)

### Competitive differentiation
1. **Privacy-first** — job search data never leaves your machine on free/paid tiers
2. **Fine-tuned personal model** — no other tool trains a cover letter model on your specific writing voice
3. **Full pipeline** — discovery through hired, not just one step (most competitors are point solutions)
4. **Open core** — community maintains job board scrapers, which break constantly; competitors pay engineers for this
5. **LLM-agnostic** — works with Ollama, Claude, GPT, vLLM; users aren't locked to one provider

### Risks to address
- **Success churn** — mitigated by re-subscription on next job search, coach accounts (persistent), and potential pivot to ongoing career management
- **Job board scraping fragility** — mitigated by open core (community patches), multiple board sources, email ingestion fallback
- **LLM cost spikes** — mitigated by Haiku-first routing, local model fallback, user BYOK option
- **Copying by incumbents** — LinkedIn, Indeed have distribution but not privacy story; fine-tuned personal model is hard to replicate at their scale

---

## 10. Roadmap

### Phase 1 — Local-first launch (now)
- Docker Compose installer + setup wizard
- License key server (simple, hosted)
- Paid tier: shared model endpoint + Notion sync + email classifier
- Premium tier: fine-tune pipeline + Claude API routing
- Open core GitHub repo (MIT core, BSL premium)

### Phase 2 — Coach tier validation (3–6 months post-launch)
- Multi-user mode with seat management
- Coach dashboard: shared job pool, per-candidate pipeline view
- Billing portal (Stripe)
- Outplacement firm pilot

### Phase 3 — Cloud Edition (6–12 months, revenue-funded or post-seed)
- Hosted SaaS version at a URL (no install)
- Same codebase, cloud deployment mode
- Converts local-first users who want convenience
- Enables mobile access

### Phase 4 — Enterprise (post-Series A)
- SSO / SAML
- Admin dashboard + analytics
- API for ATS integrations
- Custom fine-tune models for outplacement firm's brand voice

---

## 11. Competitive Landscape

### Direct competitors

| Product | Price | Pipeline | AI CL | Privacy | Fine-tune | Open Source |
|---|---|---|---|---|---|---|
| **Job Seeker Platform** | Free–$29 | Full (discovery→hired) | Personal fine-tune | Local-first | Per-user | Core (MIT) |
| Teal | Free/$29 | Partial (tracker + resume) | Generic AI | Cloud | No | No |
| Jobscan | $49.95 | Resume scan only | No | Cloud | No | No |
| Huntr | Free/$30 | Tracker only | No | Cloud | No | No |
| Rezi | $29 | Resume/CL only | Generic AI | Cloud | No | No |
| Kickresume | $19 | Resume/CL only | Generic AI | Cloud | No | No |
| LinkedIn Premium | $40 | Job search only | No | Cloud (them) | No | No |
| AIHawk | Free | LinkedIn Easy Apply | No | Local | No | Yes (MIT) |
| Simplify | Free | Auto-fill only | No | Extension | No | No |

### Competitive analysis

**Teal** ($29/mo) is the closest feature competitor — job tracker + resume builder + AI cover letters. Key gaps: cloud-only (privacy risk), no discovery automation, generic AI (not fine-tuned to your voice), no interview prep, no email classifier. Their paid tier costs the same as our premium and delivers substantially less.

**Jobscan** ($49.95/mo) is the premium ATS-optimization tool. Single-purpose, no pipeline, no cover letters. Overpriced for what it does. Users often use it alongside a tracker — this platform replaces both.

**AIHawk** (open source) automates LinkedIn Easy Apply but has no pipeline, no AI beyond form filling, no cover letter gen, no tracking. It's a macro, not a platform. We already integrate with it as a downstream action. We're complementary, not competitive at the free tier.

**LinkedIn Premium** ($40/mo) has distribution but actively works against user privacy and owns the candidate relationship. Users are the product. Our privacy story is a direct counter-positioning.

### The whitespace

No competitor offers all three of: **full pipeline automation + privacy-first local storage + personalized fine-tuned AI**. Every existing tool is either a point solution (just resume, just tracker, just auto-apply) or cloud-based SaaS that monetizes user data. The combination is the moat.

### Indirect competition

- **Spreadsheets + Notion templates** — free, flexible, no AI. The baseline we replace for free users.
- **Recruiting agencies** — human-assisted job search; we're a complement, not a replacement.
- **Career coaches** — we sell *to* them, not against them.

---

## 12. Go-to-Market Strategy

### Phase 1: Developer + privacy community launch

**Channel:** GitHub → Hacker News → Reddit

The open core model makes GitHub the primary distribution channel. A compelling README, one-command Docker install, and a working free tier are the launch. Target communities:

- Hacker News "Show HN" — privacy-first self-hosted tools get strong traction
- r/cscareerquestions (1.2M members) — active job seekers, technically literate
- r/selfhosted (2.8M members) — prime audience for local-first tools
- r/ExperiencedDevs, r/remotework — secondary seeding

**Goal:** 1,000 GitHub stars and 100 free installs in first 30 days.

**Content hook:** "I built a private job search AI that runs entirely on your machine — no data leaves your computer." Privacy angle resonates deeply post-2024 data breach fatigue.

### Phase 2: Career coaching channel

**Channel:** LinkedIn → direct outreach → coach partnerships

Career coaches are the highest-LTV customer and the most efficient channel to reach many job seekers at once. One coach onboarded = 10–20 active users.

Tactics:
- Identify coaches on LinkedIn who post about job search tools
- Offer white-glove onboarding + 60-day free trial of coach seats
- Co-create content: "How I run 15 client job searches simultaneously"
- Referral program: coach gets 1 free seat per paid client referral

**Goal:** 20 coach accounts within 90 days of paid tier launch.

### Phase 3: Content + SEO (SaaS phase)

Once the hosted Cloud Edition exists, invest in organic content:

- "Best job tracker apps 2027" (comparison content — we win on privacy + AI)
- "How to write a cover letter that sounds like you, not ChatGPT"
- "Job search automation without giving LinkedIn your data"
- Tutorial videos: full setup walkthrough, fine-tuning demo

**Goal:** 10K organic monthly visitors driving 2–5% free tier signups.

### Phase 4: Outplacement firm partnerships (enterprise)

Target HR consultancies and outplacement firms (Challenger, Gray & Christmas; Right Management; Lee Hecht Harrison). These firms place thousands of candidates per year and pay per-seat enterprise licenses.

**Goal:** 3 enterprise pilots within 12 months of coach tier validation.

### Pricing strategy by channel

| Channel | Entry offer | Conversion lever |
|---|---|---|
| GitHub / OSS | Free forever | Upgrade friction: GPU setup, no shared model |
| Direct / ProductHunt | Free 30-day paid trial | AI quality gap is immediately visible |
| Coach outreach | Free 60-day coach trial | Efficiency gain across client base |
| Enterprise | Pilot with 10 seats | ROI vs. current manual process |

### Key metrics by phase

| Phase | Primary metric | Target |
|---|---|---|
| Launch | GitHub stars | 1K in 30 days |
| Paid validation | Paying users | 500 in 90 days |
| Coach validation | Coach accounts | 20 in 90 days |
| SaaS launch | Cloud signups | 10K in 6 months |
| Enterprise | ARR from enterprise | $100K in 12 months |

---

## 13. Pricing Sensitivity Analysis

### Paid tier sensitivity ($8 / $12 / $15 / $20)

Assumption: 100K total users, 4% base conversion, gross infra cost $1,136/mo

| Price | Conversion assumption | Paying users | Revenue/mo | Gross margin |
|---|---|---|---|---|
| $8 | 5.5% (price-elastic) | 5,500 | $44,000 | 97.4% |
| **$12** | **4.0% (base)** | **4,000** | **$48,000** | **97.6%** |
| $15 | 3.2% (slight drop) | 3,200 | $48,000 | 97.6% |
| $20 | 2.5% (meaningful drop) | 2,500 | $50,000 | 97.7% |

**Finding:** Revenue is relatively flat between $12 and $20 because conversion drops offset the price increase. $12 is the sweet spot — maximizes paying user count (more data, more referrals, more upgrade candidates) without sacrificing revenue. Going below $10 requires meaningfully higher conversion to justify.

### Premium tier sensitivity ($19 / $29 / $39 / $49)

Assumption: 800 base premium users (20% of 4,000 paid), conversion adjusts with price

| Price | Conversion from paid | Premium users | Revenue/mo | Fine-tune cost | Net/mo |
|---|---|---|---|---|---|
| $19 | 25% | 1,000 | $19,000 | $42 | $18,958 |
| **$29** | **20%** | **800** | **$23,200** | **$33** | **$23,167** |
| $39 | 15% | 600 | $23,400 | $25 | $23,375 |
| $49 | 10% | 400 | $19,600 | $17 | $19,583 |

**Finding:** $29–$39 is the revenue-maximizing range. $29 wins on user volume (more fine-tune data, stronger coach acquisition funnel). $39 wins marginally on revenue but shrinks the premium base significantly. Recommend $29 at launch with the option to test $34–$39 once the fine-tuned model quality is demonstrated.

### Coach seat sensitivity ($10 / $15 / $20 per seat)

Assumption: 50 coach accounts, 3 seats avg, base $29 already captured above

| Seat price | Seat revenue/mo | Total coach revenue/mo |
|---|---|---|
| $10 | $1,500 | $1,500 |
| **$15** | **$2,250** | **$2,250** |
| $20 | $3,000 | $3,000 |

**Finding:** Seat pricing is relatively inelastic for coaches — $15–$20 is well within their cost of tools per client. $15 is conservative and easy to raise. $20 is defensible once coach ROI is documented. Consider $15 at launch, $20 after first 20 coach accounts are active.

### Blended revenue at optimized pricing (100K users)

| Component | Users | Price | Revenue/mo |
|---|---|---|---|
| Paid tier | 4,000 | $12 | $48,000 |
| Premium individual | 720 | $29 | $20,880 |
| Premium coach base | 80 | $29 | $2,320 |
| Coach seats (80 accounts × 3 avg) | 240 seats | $15 | $3,600 |
| **Total** | | | **$74,800/mo** |
| Infrastructure | | | -$1,136/mo |
| **Net** | | | **$73,664/mo (~$884K ARR)** |

### Sensitivity to conversion rate (at $12/$29 pricing, 100K users)

| Free→Paid conversion | Paid→Premium conversion | Revenue/mo | ARR |
|---|---|---|---|
| 2% | 15% | $30,720 | $369K |
| 3% | 18% | $47,664 | $572K |
| **4%** | **20%** | **$65,600** | **$787K** |
| 5% | 22% | $84,480 | $1.01M |
| 6% | 25% | $104,400 | $1.25M |

**Key insight:** Conversion rate is the highest-leverage variable. Going from 4% → 5% free-to-paid conversion adds $228K ARR at 100K users. Investment in onboarding quality and the free-tier value proposition has outsized return vs. price adjustments.
