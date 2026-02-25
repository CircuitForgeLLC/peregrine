# Job Discovery

Peregrine discovers new job listings by running search profiles against multiple job boards simultaneously. Results are deduplicated by URL and stored in the local SQLite database (`staging.db`).

---

## How Discovery Works

1. **Search profiles** in `config/search_profiles.yaml` define what to search for
2. The Home page **Run Discovery** button triggers `scripts/discover.py`
3. `discover.py` calls each configured board (standard + custom) for each active profile
4. Results are inserted into the `jobs` table with status `pending`
5. Jobs with URLs already in the database are silently skipped (URL is the unique key)
6. After insertion, `scripts/match.py` runs keyword scoring on all new jobs

---

## Search Profiles

Profiles are defined in `config/search_profiles.yaml`. You can have multiple profiles running simultaneously.

### Profile fields

```yaml
profiles:
  - name: cs_leadership              # unique identifier
    titles:
      - Customer Success Manager
      - Director of Customer Success
    locations:
      - Remote
      - San Francisco Bay Area, CA
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
    exclude_keywords:                # titles containing these words are dropped
      - sales
      - account executive
      - SDR
    results_per_board: 75            # max jobs per board per run
    hours_old: 240                   # only fetch jobs posted in last N hours
    mission_tags:                    # optional — triggers mission-alignment cover letter hints
      - music
```

### Adding a new profile

Open `config/search_profiles.yaml` and add an entry under `profiles:`. The next discovery run picks it up automatically — no restart required.

### Mission tags

`mission_tags` links a profile to industries you care about. When cover letters are generated for jobs from a mission-tagged profile, the LLM prompt includes a personal alignment note (configured in `config/user.yaml` under `mission_preferences`). Supported tags: `music`, `animal_welfare`, `education`.

---

## Standard Job Boards

These boards are powered by the [JobSpy](https://github.com/Bunsly/JobSpy) library:

| Board key | Source |
|-----------|--------|
| `linkedin` | LinkedIn Jobs |
| `indeed` | Indeed |
| `glassdoor` | Glassdoor |
| `zip_recruiter` | ZipRecruiter |
| `google` | Google Jobs |

---

## Custom Job Board Scrapers

Custom scrapers are in `scripts/custom_boards/`. They are registered in `discover.py` and activated per-profile via the `custom_boards` list.

| Key | Source | Notes |
|-----|--------|-------|
| `adzuna` | [Adzuna Jobs API](https://developer.adzuna.com/) | Requires `config/adzuna.yaml` with `app_id` and `app_key` |
| `theladders` | The Ladders | SSR scraper via `curl_cffi`; no credentials needed |
| `craigslist` | Craigslist | Requires `config/craigslist.yaml` with target city slugs |

To add your own scraper, see [Adding a Scraper](../developer-guide/adding-scrapers.md).

---

## Running Discovery

### From the UI

1. Open the **Home** page
2. Click **Run Discovery**
3. Peregrine runs all active search profiles in sequence
4. A progress bar shows board-by-board status
5. A summary shows how many new jobs were inserted vs. already known

### From the command line

```bash
conda run -n job-seeker python scripts/discover.py
```

---

## Filling Missing Descriptions

Some boards (particularly Glassdoor) return only a short description snippet. Click **Fill Missing Descriptions** on the Home page to trigger the `enrich_descriptions` background task.

The enricher visits each job URL and attempts to extract the full description from the page HTML. This runs as a background task so you can continue using the UI.

You can also enrich a specific job from the Job Review page by clicking the refresh icon next to its description.

---

## Keyword Matching

After discovery, `scripts/match.py` scores each new job by comparing the job description against your resume keywords (from `config/resume_keywords.yaml`). The score is stored as `match_score` (0–100). Gaps are stored as `keyword_gaps` (comma-separated missing keywords).

Both fields appear in the Job Review queue and can be used to sort and prioritise jobs.
