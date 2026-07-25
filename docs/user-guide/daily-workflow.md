# Daily Workflow

This page describes how Peregrine fits into a typical active job search. The core loop is short: find jobs, triage them, generate and send applications, track what happens next.

---

## The Core Loop

```
Run Discovery → Review Jobs → Apply Workspace → Track in Interviews
```

Each stage feeds the next. You can run the full loop in under ten minutes on a good day, or spend longer editing cover letters and doing interview prep when you need to.

---

## Starting Your Day

### 1. Run Discovery

Open the **Home** page and click **Run Discovery**. Peregrine queries all your configured job boards simultaneously and stores results in the local database.

- Discovery runs one search profile at a time. Each profile produces results per board, then moves to the next.
- A summary at the end shows how many new jobs were found vs. already known.
- Jobs you have already seen (by URL) are skipped automatically.

If some jobs came back with short descriptions, click **Fill Missing Descriptions** to enrich them in the background while you work.

See [Job Discovery](job-discovery.md) for search profile configuration and board details.

---

### 2. Review the Queue

Navigate to **Job Review**. New jobs arrive with status `pending` and appear in the review queue.

For each job you can:
- **Approve** — sends it into the application pipeline
- **Reject** — archives it out of the queue

Sort by **Match Score** (high to low) to see the best keyword matches first. The match score compares the job description against your resume keywords — a rough signal, not a hard filter.

Jobs with incoming email leads (a recruiter contacted you about this role) sort to the top automatically.

See [Job Review](job-review.md) for sorting, keyword gaps, and bulk actions.

---

### 3. Write and Send Applications

Navigate to **Apply Workspace**. All approved jobs appear here.

For each job:
1. Click **Generate Cover Letter** — runs as a background task using your resume and career summary.
2. Read and edit the result. The generator uses your mission alignment notes when it detects company fit.
3. Click **Export PDF** to save a formatted PDF to your documents directory.
4. Apply externally (via the company site or board).
5. Click **Mark Applied** to move the job into the Interviews kanban.

See [Apply Workspace](apply-workspace.md) for cover letter configuration, PDF formatting, and ATS optimization.

---

### 4. Track Interviews

The **Interviews** page is a kanban board. Jobs move through stages as your search progresses:

```
applied → phone_screen → interviewing → offer → hired
```

When a job moves to **phone_screen**, Peregrine automatically kicks off a company research brief in the background — a one-page summary of the company, recent news, leadership, and accessibility signals.

Use **Interview Prep** to review talking points, practice Q&A, and get live reference cards during calls.

See [Interviews](interviews.md) for stage transitions, research briefs, and prep tools.

---

## Managing Your Resume

Peregrine has two resume views that work together:

### Resume Library (`/resumes`)

An archive of every resume version — uploaded originals, AI-optimised variants, and auto-backups. The starred entry is your **active default**.

- **Import** a PDF, DOCX, ODT, or plain text file to add a version to the library.
- **★ Set as Default** marks the entry as the active resume used for cover letter generation and keyword matching.
- **⇩ Apply to profile** pushes a library entry into the structured Resume Profile (see below), and links it so future profile edits sync back automatically.

### Resume Profile (`Settings → Resume Profile`)

A structured editor for personal details, work experience, education, and skills. This is the data the cover letter generator reads directly.

- When content was applied from the library, the view shows a sync status and date.
- Saving the Resume Profile automatically updates the linked library entry — keeping them in sync without manual effort.
- You can replace the current profile by uploading a new file directly from this view.

**Recommended flow:** upload to the library → set as default → "Apply to profile" → edit in Resume Profile as needed. Your library stays current automatically.

---

## Keeping Search Preferences Fresh

Go to **Settings → Search Prefs** to update what Peregrine searches for.

Key fields:

| Field | What it does |
|-------|-------------|
| Job Titles | The roles searched across all boards |
| Locations | Geographic scope (leave blank for unrestricted) |
| Remote only | Filter to remote positions only |
| Exclude Keywords | Drop any job title containing these words before it enters the database |
| Job Boards | Enable or disable specific sources |
| Blocklists | Companies, industries, or locations to always skip |

Click **Suggest** next to any field to get AI-generated suggestions based on your resume profile.

Changes take effect on the next discovery run — no restart needed.

---

## Weekly Habits

**Clean up the queue** — reject stale pending jobs at least once a week so the queue stays scannable.

**Update your search prefs** — if you are getting too many mismatches, add more terms to Exclude Keywords. If the queue is thin, broaden Locations or add boards.

**Check Interviews** — move any stalled jobs to the right stage so the kanban reflects reality. The research brief appears in Interview Prep once a job reaches `phone_screen`.

**Tune your resume keywords** — go to **Settings → Skills** if you want to add or reweight keywords used for match scoring.

---

## Tips

- **Match score is a triage signal, not a gate.** A score of 40 might be a perfect cultural fit that uses different terminology. Read the description.
- **Cover letters improve with context.** The richer your career summary and mission alignment notes (Settings → My Profile), the more specific and accurate the generated letters.
- **Company research auto-runs.** You do not need to request it manually — it starts the moment a job hits `phone_screen`.
- **Everything is local.** Your database, resume, and application history live in `data/staging.db` and `data/config/`. Back them up like any other important file.
