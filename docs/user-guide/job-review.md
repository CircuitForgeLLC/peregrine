# Job Review

The Job Review page is where you approve or reject newly discovered jobs before they enter the application pipeline.

---

## The Pending Queue

All jobs with status `pending` appear in the review queue. Jobs with email leads (matching email threads already in the `job_contacts` table) are sorted to the top of the queue automatically.

---

## Sorting Options

Use the sort control at the top of the page to order the queue:

| Sort option | Description |
|-------------|-------------|
| **Match score (high to low)** | Jobs with the strongest keyword match appear first |
| **Match score (low to high)** | Useful for finding niche roles that scored low but are still interesting |
| **Date found (newest)** | Most recently discovered jobs first |
| **Date found (oldest)** | Oldest jobs first (useful for clearing a backlog) |
| **Company (A-Z)** | Alphabetical by company name |

---

## Match Score and Keyword Gaps

Each job card shows:

- **Match score** (0–100) — percentage of your resume keywords found in the job description
- **Keyword gaps** — specific keywords from your profile that the job description is missing

A high match score does not guarantee a good fit; use it as a signal to prioritise your review, not as a final filter.

---

## Reviewing Jobs

For each job in the queue you can:

- **Approve** — moves the job to `approved` status, making it available in the Apply Workspace
- **Reject** — moves the job to `rejected` status and removes it from the queue
- **Skip** — leaves the job in `pending` for a later review session

### Batch actions

Use the checkboxes to select multiple jobs at once, then click **Approve selected** or **Reject selected** to process them in bulk.

---

## Job Detail View

Click a job title to expand the full detail view, which shows:

- Full job description
- Company name and location
- Source board and original URL
- Salary (if available)
- Remote/on-site status
- Match score and keyword gaps
- Any email threads already linked to this job

---

## After Approval

Approved jobs appear in the **Apply Workspace** (page 4). From there you can generate a cover letter, export a PDF, and mark the job as applied.

If you decide not to apply after approving, you can reject the listing from within the Apply Workspace without losing your cover letter draft.
