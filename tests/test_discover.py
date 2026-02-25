# tests/test_discover.py
import pytest
from unittest.mock import patch, MagicMock
import pandas as pd
from pathlib import Path

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


def test_discover_writes_to_sqlite(tmp_path):
    """run_discovery inserts new jobs into SQLite staging db."""
    from scripts.discover import run_discovery
    from scripts.db import get_jobs_by_status

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
    from scripts.discover import run_discovery
    from scripts.db import init_db, insert_job, get_jobs_by_status

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
    from scripts.discover import run_discovery
    from scripts.db import get_jobs_by_status

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
    from scripts.discover import run_discovery
    from scripts.db import init_db, insert_job, get_jobs_by_status

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
