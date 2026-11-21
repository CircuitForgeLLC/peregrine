# Apply Workspace

![Peregrine apply workspace with cover letter generator and ATS optimizer](../screenshots/03-apply.png){ .only-light }
![Peregrine apply workspace with cover letter generator and ATS optimizer](../screenshots/03-apply-dark.png){ .only-dark }

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

## ATS Resume Optimizer

The optimizer helps your resume match a job. ATS means applicant tracking system, the software many employers use to filter resumes by keyword. The optimizer has two steps.

1. Click **Analyze Keywords**. Peregrine lists the keywords from the job that your resume is missing. Use the checkboxes to choose which keywords you want to target. Only the ones you tick are used.
2. Click **Optimize Resume** to rewrite your resume toward those keywords. This button is not shown on the free tier.

### Questions before the rewrite

Before anything is rewritten, Peregrine asks one short question for each keyword you selected. You pick one answer:

- **Yes, I have done this**: add a few words of your own about it.
- **Something similar**: add a few words about what you did that is close.
- **No, not something I have done**: the keyword is left out.
- **Skip for now**: the keyword is left out this time, and you can answer later.

Your answers are saved in your own account and reused on later jobs. If you already answered a keyword before, the saved answer is filled in and you can use it again with one click.

Tick **Keep this private** if you want an answer saved for you but never used in your documents.

### What the rewrite uses

The rewrite only uses keywords you answered "Yes" or "Something similar" to, and only when the answer is not private. Keywords with no answer are not used. If none of your keywords have a usable answer, no rewrite starts and the panel tells you so.

### Checking the result

On the review step, you may see a short notice called **A few things to check**. It lists:

- Words that appear in the rewritten resume but not in your original resume or your saved answers. Please check that each one is true for you. Some may just be rewordings.
- Keywords that were not used because you have not told us about them yet.

You decide what goes into the final resume. Nothing is applied until you approve it.

To look at, edit or remove your saved answers, see **My Experience** in [Settings](settings.md#my-experience).

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
