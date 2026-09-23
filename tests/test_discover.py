# tests/test_discover.py
from unittest.mock import MagicMock, patch

import pandas as pd

SAMPLE_JOB = {
    "title": "Customer Success Manager",
    "company": "Acme Corp",
    "location": "Remote",
    "is_remote": True,
    "job_url": "https://linkedin.com/jobs/view/123456",
    "site": "linkedin",
    "min_amount": 90000,
    "max_amount": 120000,
    "salary_source": "$90,000 - $120,000",
    "description": "Great CS role",
}

SAMPLE_FM = {
    "title_field": "Salary", "job_title": "Job Title", "company": "Company Name",
    "url": "Role Link", "source": "Job Source", "status": "Status of Application",
    "status_new": "Application Submitted", "date_found": "Date Found",
    "remote": "Remote", "match_score": "Match Score",
    "keyword_gaps": "Keyword Gaps", "notes": "Notes", "job_description": "Job Description",
}

SAMPLE_NOTION_CFG = {"token": "secret_test", "database_id": "fake-db-id", "field_map": SAMPLE_FM}
SAMPLE_PROFILES_CFG = {
    "profiles": [{"name": "cs", "titles": ["Customer Success Manager"],
                  "locations": ["Remote"], "boards": ["linkedin"],
                  "results_per_board": 5, "hours_old": 72}]
}


def make_jobs_df(jobs=None):
    return pd.DataFrame(jobs or [SAMPLE_JOB])


def test_normalize_profiles_converts_job_boards_to_boards_even_when_already_profiles_format():
    """save_search_prefs (dev-api.py) writes job_boards (Settings/API schema)
    into an entry inside an already-`profiles`-format file. The short-circuit
    `if "profiles" in raw: return raw` must not skip the job_boards -> boards
    conversion for those entries, or run_discovery's `profile.get("boards")`
    silently sees nothing and searches zero boards."""
    from scripts.discover import _normalize_profiles
    raw = {
        "profiles": [{
            "name": "default",
            "job_titles": ["Engineer"],
            "job_boards": [
                {"name": "linkedin", "enabled": True},
                {"name": "indeed", "enabled": False},
            ],
        }]
    }
    normalized = _normalize_profiles(raw)
    default = next(p for p in normalized["profiles"] if p["name"] == "default")
    assert default["boards"] == ["linkedin"]


def test_normalize_profiles_does_not_override_existing_boards_when_already_profiles_format():
    """If a profile entry already has both `boards` and `job_boards` (e.g.
    written by the wizard's own boards-seeding, then later re-saved by
    Settings), the existing `boards` list must not be silently replaced."""
    from scripts.discover import _normalize_profiles
    raw = {
        "profiles": [{
            "name": "default",
            "boards": ["custom_already_set"],
            "job_boards": [{"name": "linkedin", "enabled": True}],
        }]
    }
    normalized = _normalize_profiles(raw)
    default = next(p for p in normalized["profiles"] if p["name"] == "default")
    assert default["boards"] == ["custom_already_set"]


def test_discover_writes_to_sqlite(tmp_path):
    """run_discovery inserts new jobs into SQLite staging db."""
    from scripts.db import get_jobs_by_status
    from scripts.discover import run_discovery

    db_path = tmp_path / "test.db"
    with patch("scripts.discover.load_config", return_value=(SAMPLE_PROFILES_CFG, SAMPLE_NOTION_CFG)), \
         patch("scripts.discover.scrape_jobs", return_value=make_jobs_df()), \
         patch("scripts.discover.Client"):
        run_discovery(db_path=db_path)

    jobs = get_jobs_by_status(db_path, "pending")
    assert len(jobs) == 1
    assert jobs[0]["title"] == "Customer Success Manager"


def test_discover_skips_duplicate_urls(tmp_path):
    """run_discovery does not insert a job whose URL is already in SQLite."""
    from scripts.db import get_jobs_by_status, init_db, insert_job
    from scripts.discover import run_discovery

    db_path = tmp_path / "test.db"
    init_db(db_path)
    insert_job(db_path, {
        "title": "Old", "company": "X", "url": "https://linkedin.com/jobs/view/123456",
        "source": "linkedin", "location": "Remote", "is_remote": True,
        "salary": "", "description": "", "date_found": "2026-01-01",
    })

    with patch("scripts.discover.load_config", return_value=(SAMPLE_PROFILES_CFG, SAMPLE_NOTION_CFG)), \
         patch("scripts.discover.scrape_jobs", return_value=make_jobs_df()), \
         patch("scripts.discover.Client"):
        run_discovery(db_path=db_path)

    jobs = get_jobs_by_status(db_path, "pending")
    assert len(jobs) == 1  # only the pre-existing one, not a duplicate


def test_discover_pushes_new_jobs(tmp_path):
    """Legacy: discover still calls push_to_notion when notion_push=True."""
    from scripts.discover import run_discovery
    db_path = tmp_path / "test.db"
    with patch("scripts.discover.load_config", return_value=(SAMPLE_PROFILES_CFG, SAMPLE_NOTION_CFG)), \
         patch("scripts.discover.scrape_jobs", return_value=make_jobs_df()), \
         patch("scripts.discover.push_to_notion") as mock_push, \
         patch("scripts.discover.get_existing_urls", return_value=set()), \
         patch("scripts.discover.Client"):
        run_discovery(db_path=db_path, notion_push=True)
    assert mock_push.call_count == 1


def test_push_to_notion_sets_status_new():
    """push_to_notion always sets Status to the configured status_new value."""
    from scripts.discover import push_to_notion
    mock_notion = MagicMock()
    push_to_notion(mock_notion, "fake-db-id", SAMPLE_JOB, SAMPLE_FM)
    call_kwargs = mock_notion.pages.create.call_args[1]
    status = call_kwargs["properties"]["Status of Application"]["select"]["name"]
    assert status == "Application Submitted"


# ── Custom boards integration ─────────────────────────────────────────────────

_PROFILE_WITH_CUSTOM = {
    "profiles": [{
        "name": "cs", "titles": ["Customer Success Manager"],
        "locations": ["Remote"], "boards": [],
        "custom_boards": ["adzuna"],
        "results_per_board": 5, "hours_old": 72,
    }]
}

_ADZUNA_JOB = {
    "title": "Customer Success Manager",
    "company": "TestCo",
    "url": "https://www.adzuna.com/jobs/details/999",
    "source": "adzuna",
    "location": "Remote",
    "is_remote": True,
    "salary": "$90,000 – $120,000",
    "description": "Great remote CSM role",
}


def test_discover_custom_board_inserts_jobs(tmp_path):
    """run_discovery dispatches custom_boards scrapers and inserts returned jobs."""
    from scripts.db import get_jobs_by_status
    from scripts.discover import run_discovery

    db_path = tmp_path / "test.db"
    with patch("scripts.discover.load_config", return_value=(_PROFILE_WITH_CUSTOM, SAMPLE_NOTION_CFG)), \
         patch("scripts.discover.scrape_jobs", return_value=pd.DataFrame()), \
         patch("scripts.discover.CUSTOM_SCRAPERS", {"adzuna": lambda *a, **kw: [_ADZUNA_JOB]}), \
         patch("scripts.discover.Client"):
        count = run_discovery(db_path=db_path)

    assert count == 1
    jobs = get_jobs_by_status(db_path, "pending")
    assert jobs[0]["title"] == "Customer Success Manager"
    assert jobs[0]["source"] == "adzuna"


def test_discover_custom_board_skips_unknown(tmp_path, capsys):
    """run_discovery logs and skips an unregistered custom board name."""
    from scripts.discover import run_discovery

    profile_unknown = {
        "profiles": [{
            "name": "cs", "titles": ["CSM"], "locations": ["Remote"],
            "boards": [], "custom_boards": ["nonexistent_board"],
            "results_per_board": 5, "hours_old": 72,
        }]
    }
    db_path = tmp_path / "test.db"
    with patch("scripts.discover.load_config", return_value=(profile_unknown, SAMPLE_NOTION_CFG)), \
         patch("scripts.discover.scrape_jobs", return_value=pd.DataFrame()), \
         patch("scripts.discover.Client"):
        run_discovery(db_path=db_path)

    captured = capsys.readouterr()
    assert "nonexistent_board" in captured.out
    assert "Unknown scraper" in captured.out


def test_discover_custom_board_deduplicates(tmp_path):
    """Custom board results are deduplicated by URL against pre-existing jobs."""
    from scripts.db import get_jobs_by_status, init_db, insert_job
    from scripts.discover import run_discovery

    db_path = tmp_path / "test.db"
    init_db(db_path)
    insert_job(db_path, {
        "title": "CSM", "company": "TestCo",
        "url": "https://www.adzuna.com/jobs/details/999",
        "source": "adzuna", "location": "Remote", "is_remote": True,
        "salary": "", "description": "", "date_found": "2026-01-01",
    })

    with patch("scripts.discover.load_config", return_value=(_PROFILE_WITH_CUSTOM, SAMPLE_NOTION_CFG)), \
         patch("scripts.discover.scrape_jobs", return_value=pd.DataFrame()), \
         patch("scripts.discover.CUSTOM_SCRAPERS", {"adzuna": lambda *a, **kw: [_ADZUNA_JOB]}), \
         patch("scripts.discover.Client"):
        count = run_discovery(db_path=db_path)

    assert count == 0  # duplicate skipped
    assert len(get_jobs_by_status(db_path, "pending")) == 1


# ── Hybrid remote_preference ─────────────────────────────────────────────────
# Board-side is_remote tagging is unreliable for hybrid roles (LinkedIn tags
# many hybrid listings is_remote=True), so 'hybrid' preference doesn't filter
# on JobSpy's is_remote param at all -- instead it requires the description
# to match one of the same hybrid-arrangement phrases already used to
# *exclude* hybrid roles under 'remote' preference, inverted into a
# *require* filter.

_PROFILE_HYBRID = {
    "profiles": [{
        "name": "cs", "titles": ["Customer Success Manager"], "locations": ["Remote"],
        "boards": ["linkedin"], "results_per_board": 5, "hours_old": 72,
        "remote_preference": "hybrid",
    }]
}


def test_discover_hybrid_preference_keeps_jobs_matching_hybrid_phrases(tmp_path):
    from scripts.db import get_jobs_by_status
    from scripts.discover import run_discovery

    hybrid_job = {**SAMPLE_JOB, "job_url": "https://linkedin.com/jobs/view/111",
                  "description": "This is a hybrid role, 3 days in office per week."}
    db_path = tmp_path / "test.db"
    with patch("scripts.discover.load_config", return_value=(_PROFILE_HYBRID, SAMPLE_NOTION_CFG)), \
         patch("scripts.discover.scrape_jobs", return_value=make_jobs_df([hybrid_job])), \
         patch("scripts.discover.Client"):
        count = run_discovery(db_path=db_path)

    assert count == 1
    assert len(get_jobs_by_status(db_path, "pending")) == 1


def test_discover_hybrid_preference_drops_jobs_without_hybrid_phrases(tmp_path):
    from scripts.db import get_jobs_by_status
    from scripts.discover import run_discovery

    plain_job = {**SAMPLE_JOB, "job_url": "https://linkedin.com/jobs/view/222",
                 "description": "Fully remote customer success role."}
    db_path = tmp_path / "test.db"
    with patch("scripts.discover.load_config", return_value=(_PROFILE_HYBRID, SAMPLE_NOTION_CFG)), \
         patch("scripts.discover.scrape_jobs", return_value=make_jobs_df([plain_job])), \
         patch("scripts.discover.Client"):
        count = run_discovery(db_path=db_path)

    assert count == 0
    assert len(get_jobs_by_status(db_path, "pending")) == 0


def test_discover_hybrid_preference_does_not_set_jobspy_is_remote_kwarg(tmp_path):
    """Board-side is_remote tagging is unreliable for hybrid -- 'hybrid' must
    not pass is_remote=True/False to JobSpy at all (unlike 'remote'/'onsite')."""
    from scripts.discover import run_discovery

    hybrid_job = {**SAMPLE_JOB, "job_url": "https://linkedin.com/jobs/view/333",
                  "description": "Hybrid schedule, 2 days onsite."}
    db_path = tmp_path / "test.db"
    with patch("scripts.discover.load_config", return_value=(_PROFILE_HYBRID, SAMPLE_NOTION_CFG)), \
         patch("scripts.discover.scrape_jobs", return_value=make_jobs_df([hybrid_job])) as mock_scrape, \
         patch("scripts.discover.Client"):
        run_discovery(db_path=db_path)

    assert "is_remote" not in mock_scrape.call_args.kwargs


# ── remote_preference as a multi-select ─────────────────────────────────────
# Replaced the old single-value 'both' with a genuine multi-select: any
# subset of {onsite, remote, hybrid}. Old string-shaped profiles (including
# the retired 'both') are still handled above -- these cover the new list shape.

def _profile_with_remote_pref(selection):
    return {
        "profiles": [{
            "name": "cs", "titles": ["Customer Success Manager"], "locations": ["Remote"],
            "boards": ["linkedin"], "results_per_board": 5, "hours_old": 72,
            "remote_preference": selection,
        }]
    }


def test_discover_list_remote_only_sets_is_remote_true_and_excludes_hybrid(tmp_path):
    from scripts.db import get_jobs_by_status
    from scripts.discover import run_discovery

    hybrid_job = {**SAMPLE_JOB, "job_url": "https://linkedin.com/jobs/view/401",
                  "description": "Hybrid role, 3 days in office per week."}
    plain_job = {**SAMPLE_JOB, "job_url": "https://linkedin.com/jobs/view/402",
                 "description": "Fully remote customer success role."}
    db_path = tmp_path / "test.db"
    with patch("scripts.discover.load_config", return_value=(_profile_with_remote_pref(["remote"]), SAMPLE_NOTION_CFG)), \
         patch("scripts.discover.scrape_jobs", return_value=make_jobs_df([hybrid_job, plain_job])) as mock_scrape, \
         patch("scripts.discover.Client"):
        count = run_discovery(db_path=db_path)

    assert mock_scrape.call_args.kwargs.get("is_remote") is True
    assert count == 1
    assert len(get_jobs_by_status(db_path, "pending")) == 1


def test_discover_list_onsite_only_sets_is_remote_false(tmp_path):
    from scripts.discover import run_discovery

    db_path = tmp_path / "test.db"
    with patch("scripts.discover.load_config", return_value=(_profile_with_remote_pref(["onsite"]), SAMPLE_NOTION_CFG)), \
         patch("scripts.discover.scrape_jobs", return_value=make_jobs_df([SAMPLE_JOB])) as mock_scrape, \
         patch("scripts.discover.Client"):
        run_discovery(db_path=db_path)

    assert mock_scrape.call_args.kwargs.get("is_remote") is False


def test_discover_list_hybrid_only_matches_old_string_hybrid_behavior(tmp_path):
    from scripts.db import get_jobs_by_status
    from scripts.discover import run_discovery

    hybrid_job = {**SAMPLE_JOB, "job_url": "https://linkedin.com/jobs/view/403",
                  "description": "This is a hybrid role, 3 days in office per week."}
    db_path = tmp_path / "test.db"
    with patch("scripts.discover.load_config", return_value=(_profile_with_remote_pref(["hybrid"]), SAMPLE_NOTION_CFG)), \
         patch("scripts.discover.scrape_jobs", return_value=make_jobs_df([hybrid_job])) as mock_scrape, \
         patch("scripts.discover.Client"):
        count = run_discovery(db_path=db_path)

    assert "is_remote" not in mock_scrape.call_args.kwargs
    assert count == 1
    assert len(get_jobs_by_status(db_path, "pending")) == 1


def test_discover_all_three_selected_behaves_like_old_both(tmp_path):
    """No is_remote filter, no hybrid include/exclude -- matches the old 'both'."""
    from scripts.db import get_jobs_by_status
    from scripts.discover import run_discovery

    hybrid_job = {**SAMPLE_JOB, "job_url": "https://linkedin.com/jobs/view/404",
                  "company": "Hybrid Co", "description": "Hybrid role, 3 days in office."}
    plain_job = {**SAMPLE_JOB, "job_url": "https://linkedin.com/jobs/view/405",
                 "company": "Remote Co", "description": "Fully remote role."}
    db_path = tmp_path / "test.db"
    with patch("scripts.discover.load_config",
               return_value=(_profile_with_remote_pref(["onsite", "remote", "hybrid"]), SAMPLE_NOTION_CFG)), \
         patch("scripts.discover.scrape_jobs", return_value=make_jobs_df([hybrid_job, plain_job])) as mock_scrape, \
         patch("scripts.discover.Client"):
        count = run_discovery(db_path=db_path)

    assert "is_remote" not in mock_scrape.call_args.kwargs
    assert count == 2
    assert len(get_jobs_by_status(db_path, "pending")) == 2


def test_discover_remote_and_hybrid_selected_keeps_both_excludes_neither(tmp_path):
    """Partial multi-select (not all three, not a single value): no is_remote
    filter, and since hybrid IS selected, hybrid-phrase jobs are not excluded
    -- but since it's not hybrid-only, hybrid phrasing isn't required either."""
    from scripts.db import get_jobs_by_status
    from scripts.discover import run_discovery

    hybrid_job = {**SAMPLE_JOB, "job_url": "https://linkedin.com/jobs/view/406",
                  "company": "Hybrid Co", "description": "Hybrid role, 2 days onsite."}
    plain_remote_job = {**SAMPLE_JOB, "job_url": "https://linkedin.com/jobs/view/407",
                        "company": "Remote Co", "description": "Fully remote role, no office."}
    db_path = tmp_path / "test.db"
    with patch("scripts.discover.load_config",
               return_value=(_profile_with_remote_pref(["remote", "hybrid"]), SAMPLE_NOTION_CFG)), \
         patch("scripts.discover.scrape_jobs", return_value=make_jobs_df([hybrid_job, plain_remote_job])) as mock_scrape, \
         patch("scripts.discover.Client"):
        count = run_discovery(db_path=db_path)

    assert "is_remote" not in mock_scrape.call_args.kwargs
    assert count == 2
    assert len(get_jobs_by_status(db_path, "pending")) == 2


def test_discover_empty_remote_preference_list_defaults_to_all_three(tmp_path):
    """An empty list (shouldn't normally happen from the UI, but is a valid
    edge case) falls back to the same behavior as selecting all three."""
    from scripts.db import get_jobs_by_status
    from scripts.discover import run_discovery

    hybrid_job = {**SAMPLE_JOB, "job_url": "https://linkedin.com/jobs/view/408",
                  "description": "Hybrid role, 3 days in office."}
    db_path = tmp_path / "test.db"
    with patch("scripts.discover.load_config", return_value=(_profile_with_remote_pref([]), SAMPLE_NOTION_CFG)), \
         patch("scripts.discover.scrape_jobs", return_value=make_jobs_df([hybrid_job])) as mock_scrape, \
         patch("scripts.discover.Client"):
        count = run_discovery(db_path=db_path)

    assert "is_remote" not in mock_scrape.call_args.kwargs
    assert count == 1
    assert len(get_jobs_by_status(db_path, "pending")) == 1


# ── Blocklist integration ─────────────────────────────────────────────────────

def test_is_blocklisted_jobgether():
    """_is_blocklisted filters jobs from Jobgether (case-insensitive)."""
    from scripts.discover import _is_blocklisted
    blocklist = {"companies": ["jobgether"], "industries": [], "locations": []}
    assert _is_blocklisted({"company": "Jobgether", "location": "", "description": ""}, blocklist)
    assert _is_blocklisted({"company": "jobgether inc", "location": "", "description": ""}, blocklist)
    assert not _is_blocklisted({"company": "Acme Corp", "location": "", "description": ""}, blocklist)


def test_discover_applies_profile_blocklist_companies(tmp_path):
    """peregrine#194-class bug: save_search_prefs() (dev-api.py) writes a
    user's Settings -> Search Prefs 'Blocked Companies' entries onto the
    profile as `blocklist_companies`, but run_discovery() used to only ever
    filter against the separate, unwired config/blocklist.yaml -- so a
    company blocked in the UI never actually got excluded. A job from a
    blocked company must not be inserted, even though config/blocklist.yaml
    itself has no matching entry."""
    from scripts.db import get_jobs_by_status
    from scripts.discover import run_discovery

    db_path = tmp_path / "test.db"
    profiles_cfg = {
        "profiles": [{
            "name": "default", "titles": ["Customer Success Manager"],
            "locations": ["Remote"], "boards": ["linkedin"],
            "results_per_board": 5, "hours_old": 72,
            "blocklist_companies": ["Google"],
        }]
    }
    google_job = {**SAMPLE_JOB, "company": "Google", "job_url": "https://linkedin.com/jobs/view/999"}

    with patch("scripts.discover.load_config", return_value=(profiles_cfg, SAMPLE_NOTION_CFG)), \
         patch("scripts.discover.load_blocklist", return_value={"companies": [], "industries": [], "locations": []}), \
         patch("scripts.discover.scrape_jobs", return_value=make_jobs_df([google_job])), \
         patch("scripts.discover.Client"):
        run_discovery(db_path=db_path)

    jobs = get_jobs_by_status(db_path, "pending")
    assert len(jobs) == 0


def test_discover_profile_blocklist_is_scoped_per_profile(tmp_path):
    """A blocklist_companies entry on one profile must not leak into
    another profile's filtering within the same run_discovery() call."""
    from scripts.db import get_jobs_by_status
    from scripts.discover import run_discovery

    db_path = tmp_path / "test.db"
    profiles_cfg = {
        "profiles": [
            {"name": "blocks-google", "titles": ["Engineer"], "locations": ["Remote"],
             "boards": ["linkedin"], "results_per_board": 5, "hours_old": 72,
             "blocklist_companies": ["Google"]},
            {"name": "no-blocklist", "titles": ["Engineer"], "locations": ["Remote"],
             "boards": ["linkedin"], "results_per_board": 5, "hours_old": 72},
        ]
    }
    google_job = {**SAMPLE_JOB, "company": "Google", "job_url": "https://linkedin.com/jobs/view/888"}

    with patch("scripts.discover.load_config", return_value=(profiles_cfg, SAMPLE_NOTION_CFG)), \
         patch("scripts.discover.load_blocklist", return_value={"companies": [], "industries": [], "locations": []}), \
         patch("scripts.discover.scrape_jobs", return_value=make_jobs_df([google_job])), \
         patch("scripts.discover.Client"):
        run_discovery(db_path=db_path)

    # First profile blocks Google and finds nothing new; second profile has
    # no blocklist and inserts the same URL first -- so exactly one row
    # lands, proving the block was scoped to its own profile rather than
    # either leaking to the other or persisting from a stale closure value.
    jobs = get_jobs_by_status(db_path, "pending")
    assert len(jobs) == 1
    assert jobs[0]["company"] == "Google"
