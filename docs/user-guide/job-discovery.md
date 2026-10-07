# Job Discovery

Discovery is how new jobs get into Peregrine. You tell it what you are looking for once, and with one click it searches several job sites for you and collects the results in one place.

![The Peregrine home page showing the Primary Workflow buttons: Run Discovery, Sync Emails, Score Unscored, and Fill Missing Descriptions, above an Add Jobs by URL box](../screenshots/01-dashboard.png#only-light)
![The Peregrine home page in dark mode showing the Primary Workflow buttons: Run Discovery, Sync Emails, Score Unscored, and Fill Missing Descriptions](../screenshots/01-dashboard-dark.png#only-dark)

---

## What you will do here

1. Tell Peregrine what to look for in **Settings → Search Prefs**.
2. Click **Run Discovery** on the home page.
3. Open **Job Review** to see what it found.

That is the whole loop. You can repeat it as often as you like.

---

## Tell Peregrine what to look for

Open **Settings → Search Prefs**. If you finished first-time setup, you have already filled most of this in.

![The Search Preferences page with Remote Preference buttons, then Job Titles, Locations, and Exclude Keywords fields, each with a Suggest button](../screenshots/onboarding-07-search.png)

| Setting | What it does |
|---------|--------------|
| **Remote Preference** | Choose **On-site**, **Remote**, **Hybrid**, or any mix. Jobs that do not match are left out before they are collected. |
| **Job Titles** | The roles to search for. Add several, because the same job goes by different names at different companies. |
| **Locations** | Where to look. Leave it empty to search everywhere. |
| **Exclude Keywords** | Words that mean a listing is not for you. Any job whose title contains one is dropped. |
| **Job Boards** | Switch individual job sites on or off. |
| **Custom Board URLs** | Add a job site that is not in the list by pasting its address. |
| **Blocklists** | Companies, industries, or locations you never want to see. |

Click **Save Search Preferences** when you finish. Changes apply the next time you run discovery. You do not need to restart anything.

!!! tip "Stuck for words?"
    Click **Suggest** beside Job Titles, Locations, or Exclude Keywords. The assistant reads your resume and offers ideas. You click the ones you want, and nothing is added until you do.

### A few habits that help

- **Start broad, then narrow.** A thin queue is easy to fix by adding titles. A flooded queue is easy to fix by adding Exclude Keywords.
- **Use Exclude Keywords for patterns.** If three listings in a row are the wrong kind of role, one keyword removes all future ones.
- **Use Blocklists for people, places, and companies you have already ruled out.** You never have to reject them again.

---

## Run Discovery

1. Open **Home**.
2. Under **Primary Workflow**, click **Run Discovery** ("Scan job boards for new listings").
3. Keep working. Discovery runs in the background, and a small task indicator shows what Peregrine is doing.
4. Open **Job Review** when it finishes. New jobs are waiting there.

Peregrine remembers every job it has collected. If a listing turns up again on a later run, it is skipped, so you will not see the same job twice.

---

## Add a job yourself

Found a listing on your own? On the home page, find **Add Jobs by URL**. Paste one web address per line under **Paste URLs**, or use **Upload CSV** to add many at once. Those jobs join the same queue as the ones Peregrine found.

---

## What happens after discovery

Once jobs arrive, Peregrine does two more things you may notice.

**It scores them.** Each job is compared with the skills in your resume. The result is a match score from 0 to 100 and a list of keywords from your resume that the listing is missing. Treat the score as a way to decide what to read first. It is a hint and never a verdict. A 40 can be a wonderful job that uses different words. Click **Score Unscored** on the home page if any jobs are missing a score.

**It may need to fill in details.** Some job sites only share the first few lines of a description. Click **Fill Missing Descriptions** and Peregrine opens each listing in the background and fetches the full text.

Both buttons run in the background, so you can leave them going and keep reading.

---

## If something looks wrong

- **Nothing new showed up.** Peregrine only adds jobs it has not seen before. Check that your **Job Titles** are not too narrow and that no Exclude Keyword or Blocklist entry is catching everything.
- **The jobs are not what you meant.** Open **Search Prefs**, adjust your titles and Exclude Keywords, and run again. Rejected jobs stay out of your way.
- **A job board is not returning results.** Job sites change often and sometimes block automated searches for a while. Try another board, or run discovery again later. A board marked **coming soon** is not available yet.
- **Descriptions are cut short.** Click **Fill Missing Descriptions**.

---

??? note "For self-hosters and developers"
    **Search profiles.** Behind the Search Prefs page is `config/search_profiles.yaml`. Each profile has `titles`, `locations`, `boards`, `custom_boards`, `exclude_keywords`, `results_per_board`, `hours_old`, and optional `mission_tags`. A new profile is picked up on the next run with no restart.

    ```yaml
    profiles:
      - name: cs_leadership
        titles:
          - Customer Success Manager
        locations:
          - Remote
        boards:
          - linkedin
          - indeed
          - glassdoor
          - zip_recruiter
          - google
        custom_boards:
          - adzuna
          - theladders
          - craigslist
        exclude_keywords:
          - sales
        results_per_board: 75
        hours_old: 240
        mission_tags:
          - music
    ```

    **How a run works.** **Run Discovery** triggers `scripts/discover.py`. It calls each configured board for each profile, inserts new rows into the `jobs` table with status `pending`, and skips any URL already present (the URL is the unique key). Then `scripts/match.py` scores the new rows against `config/resume_keywords.yaml` and stores `match_score` and `keyword_gaps`.

    **Standard boards** come from the [JobSpy](https://github.com/Bunsly/JobSpy) library: `linkedin`, `indeed`, `glassdoor`, `zip_recruiter`, `google`.

    **Custom boards** live in `scripts/custom_boards/` and are turned on per profile with `custom_boards`:

    | Key | Source | Notes |
    |-----|--------|-------|
    | `adzuna` | [Adzuna Jobs API](https://developer.adzuna.com/) | Needs `config/adzuna.yaml` with `app_id` and `app_key` |
    | `theladders` | The Ladders | No credentials needed |
    | `craigslist` | Craigslist | Needs `config/craigslist.yaml` with target city slugs |

    **Mission tags** link a profile to causes you care about (`music`, `animal_welfare`, `education`). Cover letters for jobs from a tagged profile can include a personal alignment note from `mission_preferences` in `config/user.yaml`.

    **Command line.**

    ```bash
    conda run -n cf python scripts/discover.py
    ```

    **Enrichment.** **Fill Missing Descriptions** runs the `enrich_descriptions` background task, which visits each job URL and extracts the full description from the page.

    To add your own scraper, see [Adding a Scraper](../developer-guide/adding-scrapers.md).
