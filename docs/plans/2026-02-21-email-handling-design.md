# Email Handling Design

**Date:** 2026-02-21
**Status:** Approved

## Problem

IMAP sync already pulls emails for active pipeline jobs, but two gaps exist:
1. Inbound emails suggesting a stage change (e.g. "let's schedule a call") produce no signal — the recruiter's message just sits in the email log.
2. Recruiter outreach to email addresses not yet in the pipeline is invisible — those leads never enter Job Review.

## Goals

- Surface stage-change suggestions inline on the Interviews kanban card (suggest-only, never auto-advance).
- Capture recruiter leads from unmatched inbound email and surface them in Job Review.
- Make email sync a background task triggerable from the UI (Home page + Interviews sidebar).

## Data Model

**No new tables.** Two columns added to `job_contacts`:

```sql
ALTER TABLE job_contacts ADD COLUMN stage_signal          TEXT;
ALTER TABLE job_contacts ADD COLUMN suggestion_dismissed  INTEGER DEFAULT 0;
```

- `stage_signal` — one of: `interview_scheduled`, `offer_received`, `rejected`, `positive_response`, `neutral` (or NULL if not yet classified).
- `suggestion_dismissed` — 1 when the user clicks Dismiss; prevents the banner re-appearing.

Email leads reuse the existing `jobs` table with `source = 'email'` and `status = 'pending'`. No new columns needed.

## Components

### 1. Stage Signal Classification (`scripts/imap_sync.py`)

After saving each **inbound** contact row, call `phi3:mini` via Ollama to classify the email into one of the five labels. Store the result in `stage_signal`. If classification fails, default to `NULL` (no suggestion shown).

**Model:** `phi3:mini` via `LLMRouter.complete(model_override="phi3:mini", fallback_order=["ollama_research"])`.
Benchmarked at 100% accuracy / 3.0 s per email on a 12-case test suite. Runner-up Qwen2.5-3B untested but phi3-mini is the safe choice.

### 2. Recruiter Lead Extraction (`scripts/imap_sync.py`)

A second pass after per-job sync: scan INBOX broadly for recruitment-keyword emails that don't match any known pipeline company. For each unmatched email, call **Nemotron 1.5B** (already in use for company research) to extract `{company, title}`. If extraction returns a company name not already in the DB, insert a new job row `source='email', status='pending'`.

**Dedup:** checked by `message_id` against all known contacts (cross-job), plus `url` uniqueness on the jobs table (the email lead URL is set to a synthetic `email://<from_domain>/<message_id>` value).

### 3. Background Task (`scripts/task_runner.py`)

New task type: `email_sync` with `job_id = 0`.
`submit_task(db, "email_sync", 0)` → daemon thread → `sync_all()` → returns summary via task `error` field.

Deduplication: only one `email_sync` can be queued/running at a time (existing insert_task logic handles this).

### 4. UI — Sync Button (Home + Interviews)

**Home.py:** New "Sync Emails" section alongside Find Jobs / Score / Notion sync.
**5_Interviews.py:** Existing sync button already present in sidebar; convert from synchronous `sync_all()` call to `submit_task()` + fragment polling.

### 5. UI — Email Leads (Job Review)

When `show_status == "pending"`, prepend email leads (`source = 'email'`) at the top of the list with a distinct `📧 Email Lead` badge. Actions are identical to scraped pending jobs (Approve / Reject).

### 6. UI — Stage Suggestion Banner (Interviews Kanban)

Inside `_render_card()`, before the advance/reject buttons, check for unseen stage signals:

```
💡 Email suggests: interview_scheduled
From: sarah@company.com · "Let's book a call"
[→ Move to Phone Screen]   [Dismiss]
```

- "Move" calls `advance_to_stage()` + `submit_task("company_research")` then reruns.
- "Dismiss" calls `dismiss_stage_signal(contact_id)` then reruns.
- Only the most recent undismissed signal is shown per card.

## Error Handling

| Failure | Behaviour |
|---------|-----------|
| IMAP connection fails | Error stored in task `error` field; shown as warning in UI after sync |
| Classifier call fails | `stage_signal` left NULL; no suggestion shown; sync continues |
| Lead extractor fails | Email skipped; appended to `result["errors"]`; sync continues |
| Duplicate `email_sync` task | `insert_task` returns existing id; no new thread spawned |
| LLM extraction returns no company | Email silently skipped (not a lead) |

## Out of Scope

- Auto-advancing pipeline stage (suggest only).
- Sending email replies from the app (draft helper already exists).
- OAuth / token-refresh IMAP (config/email.yaml credentials only).
