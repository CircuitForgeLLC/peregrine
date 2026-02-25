# tests/test_sync.py
import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path


SAMPLE_FM = {
    "title_field": "Salary", "job_title": "Job Title", "company": "Company Name",
    "url": "Role Link", "source": "Job Source", "status": "Status of Application",
    "status_new": "Application Submitted", "date_found": "Date Found",
    "remote": "Remote", "match_score": "Match Score",
    "keyword_gaps": "Keyword Gaps", "notes": "Notes", "job_description": "Job Description",
}

SAMPLE_NOTION_CFG = {"token": "secret_test", "database_id": "fake-db-id", "field_map": SAMPLE_FM}


def test_sync_pushes_approved_jobs(tmp_path):
    """sync_to_notion pushes approved jobs and marks them synced."""
    from scripts.sync import sync_to_notion
    from scripts.db import init_db, insert_job, get_jobs_by_status, update_job_status

    db_path = tmp_path / "test.db"
    init_db(db_path)
    row_id = insert_job(db_path, {
        "title": "CSM", "company": "Acme", "url": "https://example.com/1",
        "source": "linkedin", "location": "Remote", "is_remote": True,
        "salary": "$100k", "description": "Good role", "date_found": "2026-02-20",
    })
    update_job_status(db_path, [row_id], "approved")

    mock_notion = MagicMock()
    mock_notion.pages.create.return_value = {"id": "notion-page-abc"}

    with patch("scripts.sync.load_notion_config", return_value=SAMPLE_NOTION_CFG), \
         patch("scripts.sync.Client", return_value=mock_notion):
        count = sync_to_notion(db_path=db_path)

    assert count == 1
    mock_notion.pages.create.assert_called_once()
    synced = get_jobs_by_status(db_path, "synced")
    assert len(synced) == 1


def test_sync_falls_back_to_core_fields_on_validation_error(tmp_path):
    """When Notion returns a validation_error (missing column), sync retries without optional fields."""
    from scripts.sync import sync_to_notion
    from scripts.db import init_db, insert_job, get_jobs_by_status, update_job_status

    db_path = tmp_path / "test.db"
    init_db(db_path)
    row_id = insert_job(db_path, {
        "title": "CSM", "company": "Acme", "url": "https://example.com/2",
        "source": "linkedin", "location": "Remote", "is_remote": True,
        "salary": "", "description": "", "date_found": "2026-02-20",
    })
    update_job_status(db_path, [row_id], "approved")

    mock_notion = MagicMock()
    # First call raises validation_error; second call (fallback) succeeds
    mock_notion.pages.create.side_effect = [
        Exception("validation_error: Could not find property with name: Match Score"),
        {"id": "notion-page-fallback"},
    ]

    with patch("scripts.sync.load_notion_config", return_value=SAMPLE_NOTION_CFG), \
         patch("scripts.sync.Client", return_value=mock_notion):
        count = sync_to_notion(db_path=db_path)

    assert count == 1
    assert mock_notion.pages.create.call_count == 2
    synced = get_jobs_by_status(db_path, "synced")
    assert len(synced) == 1


def test_sync_returns_zero_when_nothing_approved(tmp_path):
    """sync_to_notion returns 0 when there are no approved jobs."""
    from scripts.sync import sync_to_notion
    from scripts.db import init_db

    db_path = tmp_path / "test.db"
    init_db(db_path)

    with patch("scripts.sync.load_notion_config", return_value=SAMPLE_NOTION_CFG), \
         patch("scripts.sync.Client"):
        count = sync_to_notion(db_path=db_path)

    assert count == 0
