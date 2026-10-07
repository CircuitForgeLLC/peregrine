# Apply Workspace

The **Apply** page is where you write your cover letter, check your resume against a job, and keep track of the jobs you have applied to.

![Apply page with a list of approved jobs on the left and the cover letter workspace on the right](../screenshots/03-apply.png#only-light)
![Apply page with a list of approved jobs on the left and the cover letter workspace on the right](../screenshots/03-apply-dark.png#only-dark)

## What you will do here

1. Click **Apply** in the sidebar. You see the jobs you approved in **Job Review**.
2. Click a job. On a wide screen it opens beside the list. On a phone or narrow window it opens as its own page.
3. Under **Cover Letter**, click **Generate with AI** or write your own.
4. Read it, change anything you like, and click **Save**.
5. Click **Download PDF** and send your application on the company's own site or email.
6. Come back and click **Mark as Applied**. The job leaves this list and moves on to your **Interviews** page.

Everything here is a draft until you say it is done. Nothing is sent to an employer for you.

## What does the job list show?

Each job shows its match percentage, its company, and a tick if it already has a cover letter. On a phone the list also shows **Draft** or **No draft**. On a wide screen you can tick **Remote only** to hide the rest, and use the arrow button to fold the list away for more room.

If the list is empty, you see **No approved jobs yet** and a link to **Job Review**.

## How do I write a cover letter?

Open a job. Under **Cover Letter** you have two choices:

- **Generate with AI** asks the writing assistant (a large language model, or LLM) for a first draft. It uses your resume, your profile and the job description. It usually takes 20 to 60 seconds. You can keep using Peregrine while you wait.
- **Paste / write manually** gives you a blank box for your own words.

The draft is a starting point. It can get details wrong or sound off. Read all of it and change what does not sound like you.

If generation fails, you see the reason and two buttons: **Retry** and **Write manually instead**.

### How do I edit and save?

Click in the text box and type. A word count sits above it. Your changes are not stored until you click **Save**, which then shows **Saved**. **Regenerate** asks for a fresh draft and replaces what is in the box, so save a copy of anything you want to keep first.

### How do I get a PDF?

Click **Download PDF**. Your browser downloads a file named like `CoverLetter_Acme_2026-10-06.pdf`. If it fails, click **Save** first and try again.

## How do I check my resume for this job?

Open **Resume** on the job. It shows the resume attached to this job. Use **Switch** to pick a different saved resume or **Manage** to open your **Resumes** page.

Click **Optimize for ATS**. ATS means applicant tracking system, the software many employers use to filter resumes before a person reads them. The **Resume Optimizer** opens.

1. Click **Analyze Keywords**. You get a list of words the job asks for that your resume does not mention.
2. Untick any that do not honestly apply to you.
3. Click **Optimize Resume** to have the writing assistant rewrite sections to include the ones you kept.
4. Click **Review Changes** and go through the proposed edits section by section.
5. Edit the preview if you want, then click **Approve & Save**. You can tick **Save to Resume Library** to keep it under its own name.

After approving you can download the result as text, PDF or YAML (a plain data format some tools read). Earlier versions are kept under **Show previous versions** so you can go back.

Only add keywords for skills you really have.

!!! note "Paid feature"
    The keyword report is free. The full rewrite needs a Paid license, or your own LLM connection (bring your own key, BYOK).

### Is there a resume score?

Yes, but it lives on the **Resumes** page, not here. Open a resume there and click **Score this resume**. You get a score out of 10, strengths, areas to improve, and suggested rewording you can apply one at a time. A separate score covers ATS-friendliness.

## What is Application Q&A?

Many applications ask extra questions. Under **Application Q&A**, type the question into **Add a question from the application…** and click **Add**. Write your own answer, or click **Suggest** for an LLM draft. Click **Save All** when you are done.

## How do I mark a job as applied?

After you have submitted your application, click **Mark as Applied**. Peregrine saves your cover letter if you have unsaved changes, records that you applied, and takes the job off this list. You find it again on **Interviews**.

## What if I change my mind?

Click **Reject Listing**. Peregrine asks you to confirm because it cannot be undone from here. The job leaves the Apply list.

## If something looks wrong

- **"AI features are disabled in demo mode".** You are in the demo. Writing assistant features are turned off there.
- **"Save failed".** Try again. Your text is still in the box.
- **The draft never appears.** Wait a minute, then use **Retry**. If it keeps failing, check that an LLM is set up in **Settings**.

!!! note "Cover letters and your own key"
    Cover letter generation is not tier-gated in the app's tier list. It needs a working LLM, whether Peregrine's or your own.

??? note "For self-hosters and developers"
    - Routes: `/apply` (split pane on screens 1024px and wider, list on narrower) and `/apply/:id` (full-page workspace, used on mobile).
    - The list comes from `GET /api/jobs?status=approved`. **Mark as Applied** calls `POST /api/jobs/{id}/applied`, which sets `status = 'applied'` and `applied_at`. **Reject Listing** calls `POST /api/jobs/{id}/reject`.
    - Cover letter endpoints: `POST /api/jobs/{id}/cover_letter/generate` (background task), `GET /api/jobs/{id}/cover_letter/task` (polled for status), `PATCH /api/jobs/{id}/cover_letter` (save), `GET /api/jobs/{id}/cover_letter/pdf` (PDF built server-side with ReportLab and downloaded by the browser).
    - Application Q&A uses `GET` and `PATCH` on `/api/jobs/{id}/qa` and `POST /api/jobs/{id}/qa/suggest`.
    - The generator uses your career summary, resume data and mission-alignment notes from `config/user.yaml`, plus the job title, description and company. Backends follow the cover letter fallback order in `config/llm.yaml`. By default that is `ollama → claude_code → vllm → github_copilot → anthropic`. See [LLM Router](../reference/llm-router.md).
    - The ATS rewrite is gated in the UI when `config.tier` is `free`. In `scripts/wizard/tiers.py`, cover letter generation has no entry in `FEATURES`, so it is free. BYOK-unlockable features are listed in `BYOK_UNLOCKABLE`.
    - The Resume Score modal (`ResumeScoreModal.vue`) is opened from `/resumes`, not from Apply.
