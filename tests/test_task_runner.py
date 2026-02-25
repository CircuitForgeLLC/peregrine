import threading
import time
import pytest
from pathlib import Path
from unittest.mock import patch
import sqlite3


def _make_db(tmp_path):
    from scripts.db import init_db, insert_job
    db = tmp_path / "test.db"
    init_db(db)
    job_id = insert_job(db, {
        "title": "CSM", "company": "Acme", "url": "https://ex.com/1",
        "source": "linkedin", "location": "Remote", "is_remote": True,
        "salary": "", "description": "Great role.", "date_found": "2026-02-20",
    })
    return db, job_id


def test_submit_task_returns_id_and_true(tmp_path):
    """submit_task returns (task_id, True) and spawns a thread."""
    db, job_id = _make_db(tmp_path)
    with patch("scripts.task_runner._run_task"):  # don't actually call LLM
        from scripts.task_runner import submit_task
        task_id, is_new = submit_task(db, "cover_letter", job_id)
    assert isinstance(task_id, int) and task_id > 0
    assert is_new is True


def test_submit_task_deduplicates(tmp_path):
    """submit_task returns (existing_id, False) for a duplicate in-flight task."""
    db, job_id = _make_db(tmp_path)
    with patch("scripts.task_runner._run_task"):
        from scripts.task_runner import submit_task
        first_id, _ = submit_task(db, "cover_letter", job_id)
        second_id, is_new = submit_task(db, "cover_letter", job_id)
    assert second_id == first_id
    assert is_new is False


def test_run_task_cover_letter_success(tmp_path):
    """_run_task marks running→completed and saves cover letter to DB."""
    db, job_id = _make_db(tmp_path)
    from scripts.db import insert_task, get_task_for_job
    task_id, _ = insert_task(db, "cover_letter", job_id)

    with patch("scripts.generate_cover_letter.generate", return_value="Dear Hiring Manager,\nGreat fit!"):
        from scripts.task_runner import _run_task
        _run_task(db, task_id, "cover_letter", job_id)

    task = get_task_for_job(db, "cover_letter", job_id)
    assert task["status"] == "completed"
    assert task["error"] is None

    conn = sqlite3.connect(db)
    row = conn.execute("SELECT cover_letter FROM jobs WHERE id=?", (job_id,)).fetchone()
    conn.close()
    assert row[0] == "Dear Hiring Manager,\nGreat fit!"


def test_run_task_company_research_success(tmp_path):
    """_run_task marks running→completed and saves research to DB."""
    db, job_id = _make_db(tmp_path)
    from scripts.db import insert_task, get_task_for_job, get_research

    task_id, _ = insert_task(db, "company_research", job_id)
    fake_result = {
        "raw_output": "raw", "company_brief": "brief",
        "ceo_brief": "ceo", "talking_points": "points",
    }
    with patch("scripts.company_research.research_company", return_value=fake_result):
        from scripts.task_runner import _run_task
        _run_task(db, task_id, "company_research", job_id)

    task = get_task_for_job(db, "company_research", job_id)
    assert task["status"] == "completed"

    research = get_research(db, job_id=job_id)
    assert research["company_brief"] == "brief"


def test_run_task_marks_failed_on_exception(tmp_path):
    """_run_task marks status=failed and stores error when generator raises."""
    db, job_id = _make_db(tmp_path)
    from scripts.db import insert_task, get_task_for_job
    task_id, _ = insert_task(db, "cover_letter", job_id)

    with patch("scripts.generate_cover_letter.generate", side_effect=RuntimeError("LLM timeout")):
        from scripts.task_runner import _run_task
        _run_task(db, task_id, "cover_letter", job_id)

    task = get_task_for_job(db, "cover_letter", job_id)
    assert task["status"] == "failed"
    assert "LLM timeout" in task["error"]


def test_run_task_discovery_success(tmp_path):
    """_run_task with task_type=discovery calls run_discovery and stores count in error field."""
    from scripts.db import init_db, insert_task, get_task_for_job
    db = tmp_path / "test.db"
    init_db(db)
    task_id, _ = insert_task(db, "discovery", 0)

    with patch("scripts.discover.run_discovery", return_value=7):
        from scripts.task_runner import _run_task
        _run_task(db, task_id, "discovery", 0)

    task = get_task_for_job(db, "discovery", 0)
    assert task["status"] == "completed"
    assert "7 new listings" in task["error"]


def test_run_task_email_sync_success(tmp_path):
    """email_sync task calls sync_all and marks completed with summary."""
    db, _ = _make_db(tmp_path)
    from scripts.db import insert_task, get_task_for_job
    task_id, _ = insert_task(db, "email_sync", 0)

    summary = {"synced": 3, "inbound": 5, "outbound": 2, "new_leads": 1, "errors": []}
    with patch("scripts.imap_sync.sync_all", return_value=summary):
        from scripts.task_runner import _run_task
        _run_task(db, task_id, "email_sync", 0)

    task = get_task_for_job(db, "email_sync", 0)
    assert task["status"] == "completed"
    assert "3 jobs" in task["error"]


def test_run_task_email_sync_file_not_found(tmp_path):
    """email_sync marks failed with helpful message when config is missing."""
    db, _ = _make_db(tmp_path)
    from scripts.db import insert_task, get_task_for_job
    task_id, _ = insert_task(db, "email_sync", 0)

    with patch("scripts.imap_sync.sync_all", side_effect=FileNotFoundError("config/email.yaml")):
        from scripts.task_runner import _run_task
        _run_task(db, task_id, "email_sync", 0)

    task = get_task_for_job(db, "email_sync", 0)
    assert task["status"] == "failed"
    assert "email" in task["error"].lower()


def test_submit_task_actually_completes(tmp_path):
    """Integration: submit_task spawns a thread that completes asynchronously."""
    db, job_id = _make_db(tmp_path)
    from scripts.db import get_task_for_job

    with patch("scripts.generate_cover_letter.generate", return_value="Cover letter text"):
        from scripts.task_runner import submit_task
        task_id, _ = submit_task(db, "cover_letter", job_id)
        # Wait for thread to complete (max 5s)
        for _ in range(50):
            task = get_task_for_job(db, "cover_letter", job_id)
            if task and task["status"] in ("completed", "failed"):
                break
            time.sleep(0.1)

    task = get_task_for_job(db, "cover_letter", job_id)
    assert task["status"] == "completed"


def test_run_task_enrich_craigslist_success(tmp_path):
    """enrich_craigslist task calls enrich_craigslist_fields and marks completed."""
    from scripts.db import init_db, insert_job, insert_task, get_task_for_job
    from unittest.mock import MagicMock
    db = tmp_path / "test.db"
    init_db(db)
    job_id = insert_job(db, {
        "title": "CSM", "company": "", "url": "https://sfbay.craigslist.org/jjj/d/9.html",
        "source": "craigslist", "location": "", "description": "Join Acme Corp. Pay: $100k.",
        "date_found": "2026-02-24",
    })
    task_id, _ = insert_task(db, "enrich_craigslist", job_id)

    with patch("scripts.enrich_descriptions.enrich_craigslist_fields",
               return_value={"company": "Acme Corp", "salary": "$100k"}) as mock_enrich:
        from scripts.task_runner import _run_task
        _run_task(db, task_id, "enrich_craigslist", job_id)

    mock_enrich.assert_called_once_with(db, job_id)
    task = get_task_for_job(db, "enrich_craigslist", job_id)
    assert task["status"] == "completed"


def test_scrape_url_submits_enrich_craigslist_for_craigslist_job(tmp_path):
    """After scrape_url completes for a craigslist job with empty company, enrich_craigslist is queued."""
    from scripts.db import init_db, insert_job, insert_task, get_task_for_job
    db = tmp_path / "test.db"
    init_db(db)
    job_id = insert_job(db, {
        "title": "CSM", "company": "", "url": "https://sfbay.craigslist.org/jjj/d/10.html",
        "source": "craigslist", "location": "", "description": "",
        "date_found": "2026-02-24",
    })
    task_id, _ = insert_task(db, "scrape_url", job_id)

    with patch("scripts.scrape_url.scrape_job_url", return_value={"title": "CSM", "company": ""}):
        with patch("scripts.task_runner.submit_task", wraps=None) as mock_submit:
            # Use wraps=None so we can capture calls without actually spawning threads
            mock_submit.return_value = (99, True)
            from scripts.task_runner import _run_task
            _run_task(db, task_id, "scrape_url", job_id)

    # submit_task should have been called with enrich_craigslist
    assert mock_submit.called
    call_args = mock_submit.call_args
    assert call_args[0][1] == "enrich_craigslist"
    assert call_args[0][2] == job_id
