# Apply Workspace

The Apply Workspace is where you generate cover letters, export application documents, and record that you have applied to a job.

---

## Accessing the Workspace

Navigate to page **4 — Apply** in the sidebar. The workspace lists all jobs with status `approved`, sorted by date approved.

---

## Cover Letter Generation

Click **Generate Cover Letter** on any job card. Peregrine runs as a background task so you can continue navigating the UI.

### What the generator uses

- Your **career summary** and **resume data** from `config/user.yaml`
- The **job title** and **job description**
- **Company name** — used to detect mission-aligned industries
- **Mission alignment notes** from `config/user.yaml` (e.g. a personal note about why you care about music-industry companies)

### Fallback chain

Cover letters use the cover letter fallback order from `config/llm.yaml`. By default: `ollama → claude_code → vllm → github_copilot → anthropic`. See [LLM Router](../reference/llm-router.md) for details.

### Mission alignment

If the company or job description matches one of your configured mission industries (music, animal welfare, education), the generator injects a personalised paragraph 3 hint into the prompt. This produces a cover letter that reflects authentic alignment rather than generic enthusiasm.

---

## Editing the Cover Letter

After generation, the cover letter appears in an editable text area. Edit freely — changes are saved locally and do not trigger a re-generation.

Click **Save** to write the updated text back to the database.

---

## PDF Export

Click **Export PDF** to generate a formatted PDF of the cover letter. The PDF is saved to your `docs_dir` (configured in `config/user.yaml`, default: `~/Documents/JobSearch`).

The filename format is: `{Company}_{Title}_{Date}_CoverLetter.pdf`

---

## Marking Applied

Once you have submitted your application externally, click **Mark Applied**. This:

- Sets the job status to `applied`
- Records `applied_at` timestamp
- Moves the job out of the Apply Workspace and into the Interviews kanban (in `applied` pre-stage)

---

## Rejecting a Listing

Changed your mind about a job you approved? Click **Reject Listing** to set it to `rejected` status. This removes it from the workspace without affecting your cover letter draft (the text remains in the database).

---

## Cover Letter Background Task Status

The sidebar shows a live indicator (updated every 3 seconds) of running and queued background tasks. If a cover letter generation is in progress you will see it there.

A task can have these statuses:
- **queued** — waiting to start
- **running** — actively generating
- **completed** — finished; reload the page to see the result
- **failed** — generation failed; check the logs

Only one queued or running task per job is allowed at a time. Clicking **Generate Cover Letter** on a job that already has a task in progress is a no-op.
