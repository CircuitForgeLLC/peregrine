# Interviews

The Interviews page is a kanban board that tracks your progress through the interview pipeline after you have applied to a job.

---

## Kanban Stages

Jobs move left to right through the pipeline:

```
applied → phone_screen → interviewing → offer → hired
                                                    ↓
                                              (any stage) → rejected
```

| Stage | Description |
|-------|-------------|
| `applied` | Pre-kanban holding area — job applied to but no response yet |
| `phone_screen` | Initial recruiter/HR screen scheduled or completed |
| `interviewing` | Active interview loop (first-round, technical, panel, etc.) |
| `offer` | Offer received; evaluating |
| `hired` | Offer accepted |
| `rejected` | Declined or ghosted at any stage (captures `rejection_stage`) |

---

## Moving Jobs Between Stages

Drag a job card to the target column, or use the stage-advance button on each card. Moving a job to `phone_screen` triggers an automatic company research task (see below).

---

## Company Research (Auto-trigger)

When a job moves to `phone_screen`, Peregrine automatically queues a **company research** background task (`scripts/company_research.py`). The research brief is generated in three phases:

1. **SearXNG web scrape** — queries the SearXNG meta-search engine (running locally on port 8888) for company information from public sources
2. **SearXNG news snippets** — fetches recent news about the company
3. **LLM synthesis** — combines the scraped content into a structured brief

The brief includes:
- Company overview (mission, size, funding stage)
- CEO / leadership summary
- Talking points tailored to your role
- Optional: Inclusion and Accessibility section (ADA signals, WCAG, ERGs)
- Optional: LGBTQIA+ inclusion section (non-discrimination policies, culture signals)

Both optional sections are controlled by `candidate_accessibility_focus` and `candidate_lgbtq_focus` booleans in `config/user.yaml`. They are for personal decision-making only and are never included in applications.

---

## Interview Prep Page

Navigate to page **6 — Interview Prep** for a job in the `phone_screen` or `interviewing` stage. This page provides:

- The full company research brief (generated automatically when the job moved to `phone_screen`)
- A live reference sheet you can keep open during a call
- **Practice Q&A** — a back-and-forth interview simulation powered by your LLM backend

!!! note "Tier requirement"
    Interview prep is a Paid feature. See [Tier System](../reference/tier-system.md).

---

## Survey Assistant

When a job moves to the `survey` stage (via the "Survey" button on an applied job), the Survey Assistant page (page 7) becomes active for that job. It helps you complete culture-fit surveys by:

- Accepting pasted survey text
- Accepting screenshot uploads (analysed by the Moondream2 vision service)
- Generating suggested answers via your configured LLM backend

After completing the survey, move the job to `phone_screen` to continue the pipeline.

!!! note "Tier requirement"
    Survey assistant is a Paid feature.

---

## Rejection Tracking

When you reject a job from the kanban (at any stage), Peregrine captures the `rejection_stage` — the stage at which the rejection occurred. This data is available for pipeline analytics.

---

## Email-Driven Stage Updates

If email sync is configured (see [Email Sync](email-sync.md)), Peregrine can automatically advance jobs based on incoming email:

| Email classification | Stage action |
|---------------------|-------------|
| `interview_request` | Moves job toward `phone_screen` if still `applied` |
| `rejection` | Moves job to `rejected` (captures `rejection_stage`) |
| `offer` | Flags job for review; moves toward `offer` |
| `survey_received` | Moves job to `survey` stage |
