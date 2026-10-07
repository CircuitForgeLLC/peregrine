# Daily Workflow

This page shows how Peregrine fits into an ordinary day of job searching. The short version: find jobs, decide which ones deserve your time, write your application, then keep track of what happens next.

You do not need to do all of it every day. Ten focused minutes is a good day.

---

## The loop

```
Find jobs  →  Review them  →  Apply  →  Track what happens
(Home)        (Job Review)    (Apply)    (Interviews)
```

Each stage feeds the next one. Whatever you finish today is waiting for you tomorrow, so there is no pressure to clear everything at once.

![The Peregrine home page showing your job counts and the Primary Workflow buttons](../screenshots/01-dashboard.png#only-light)
![The Peregrine home page in dark mode showing your job counts and the Primary Workflow buttons](../screenshots/01-dashboard-dark.png#only-dark)

---

## A ten-minute day

### 1. Find new jobs

Open **Home** and click **Run Discovery**. Peregrine searches your job sites in the background, so you can move on to the next step while it works.

Read more in [Job Discovery](job-discovery.md).

### 2. Decide what is worth your time

Open **Job Review**. You see one job at a time, best matches first. Choose **Approve**, **Reject**, or **Skip**. Approving sends the job to the Apply page, and Skip lets you come back to it.

You can use buttons, the keyboard, or a swipe, and every choice can be undone. Read more in [Job Review](job-review.md).

### 3. Write and send your applications

Open **Apply**. Every job you approved is listed here. For each one, open it, draft a cover letter, read it, and make it yours. When you have applied on the company's own site or job board, click **Mark as Applied**.

A draft is only a starting point. You read it, you edit it, and you decide what goes out. Read more in [Apply Workspace](apply-workspace.md).

### 4. Keep track

Open **Interviews** to see where each application stands. Move a job along as things happen, such as a phone screen or an offer, so the board matches real life. Read more in [Interviews](interviews.md).

---

## Your resume in Peregrine

Peregrine keeps your resume in two places that work together.

**Resumes** (in the sidebar) is your library. It holds every version you have, including the original you uploaded and any tailored copies.

- **Import** adds a resume file to the library.
- **★ Set as Default** marks the version Peregrine uses for drafting letters and matching jobs.
- **Apply to profile** copies a library version into your Resume Profile, described next.

**Settings → Resume Profile** is the structured version: your jobs, schooling, and skills as editable fields. This is the version that letters are drafted from. Saving changes here keeps the linked library entry up to date, so you do not have to do it twice.

A good order for a first time: upload your resume, set it as default, click **Apply to profile**, then fix anything that looks off in Resume Profile.

---

## Keeping your search fresh

Your results are only as good as what you ask for. Open **Settings → Search Prefs** whenever your goals change.

| If you see... | Try... |
|---------------|--------|
| Too many jobs that do not fit | Add words to **Exclude Keywords**, or add a company or industry to **Blocklists** |
| Too few jobs | Add more **Job Titles**, widen **Locations**, or switch on another job board |
| Jobs in the wrong place | Check **Remote Preference** and **Locations** |

Changes apply to the next discovery run. Use **Suggest** beside a field if you want ideas based on your resume.

---

## Once a week

- **Tidy the queue.** Spend a few minutes rejecting jobs in Job Review that no longer interest you, so the queue stays easy to read.
- **Adjust your search.** If the last week's results felt off, change your Exclude Keywords or titles.
- **Update your board.** Move any application that has changed in **Interviews** so you do not have to remember what is pending.
- **Update your profile.** If you gained a new skill or finished a project, add it to Resume Profile. Better information means better drafts.

---

## Things worth knowing

- **The match score is a hint, never a verdict.** A job that scores 40 can be a great fit that uses different words. Read the listing before you decide.
- **More detail makes better letters.** A specific career summary in **Settings → My Profile** helps far more than a long generic one.
- **You are always in charge.** Peregrine drafts, suggests, and organises. It never sends an application for you.
- **A slow day is fine.** If you only get through Job Review, that is still progress.

---

??? note "For self-hosters and developers"
    **Where your data lives.** Your job database is `data/staging.db`. Your profile, preferences, and settings are in `data/config/` and `config/`. These are ordinary files, so back them up like any other important file. Nothing leaves your machine unless you connect an outside service.

    **Run discovery from the command line.**

    ```bash
    conda run -n cf python scripts/discover.py
    ```

    **Resume library and profile sync.** Library entries are linked to the profile when you use **Apply to profile**, and saving the profile writes back to the linked entry.

    **Related reference.** See [Tier System](../reference/tier-system.md) for which features need a Paid plan, and [Config Files](../reference/config-files.md) for every setting.
