import threading
import time
import pytest
from pathlib import Path
from unittest.mock import patch
import sqlite3


@pytest.fixture(autouse=True)
def clean_scheduler():
    """Reset the TaskScheduler singleton between tests to prevent cross-test contamination."""
    yield
    from scripts.task_scheduler import reset_scheduler
    reset_scheduler()


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
    """Integration: submit_task routes LLM tasks through the scheduler and they complete."""
    db, job_id = _make_db(tmp_path)
    from scripts.db import get_task_for_job
    from scripts.task_scheduler import get_scheduler
    from scripts.task_runner import _run_task

    # Prime the singleton with the correct db_path before submit_task runs.
    # get_scheduler() already calls start() internally.
    get_scheduler(db, run_task_fn=_run_task)

    with patch("scripts.generate_cover_letter.generate", return_value="Cover letter text"):
        from scripts.task_runner import submit_task
        task_id, _ = submit_task(db, "cover_letter", job_id)
        # Wait for scheduler to complete the task (max 5s)
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


import json as _json

def test_wizard_generate_unknown_section_fails(tmp_path):
    """wizard_generate with unknown section marks task failed."""
    db = tmp_path / "t.db"
    from scripts.db import init_db, insert_task
    init_db(db)

    params = _json.dumps({"section": "nonexistent_section", "input": {}})
    task_id, _ = insert_task(db, "wizard_generate", 0, params=params)

    # Call _run_task directly (not via thread) to test synchronously
    from scripts.task_runner import _run_task
    _run_task(db, task_id, "wizard_generate", 0, params=params)

    import sqlite3
    conn = sqlite3.connect(db)
    row = conn.execute("SELECT status, error FROM background_tasks WHERE id=?", (task_id,)).fetchone()
    conn.close()
    assert row[0] == "failed", f"Expected 'failed', got '{row[0]}'"


def test_wizard_generate_missing_section_fails(tmp_path):
    """wizard_generate with no section key marks task failed."""
    db = tmp_path / "t.db"
    from scripts.db import init_db, insert_task
    init_db(db)

    params = _json.dumps({"input": {"resume_text": "some text"}})  # missing section key
    task_id, _ = insert_task(db, "wizard_generate", 0, params=params)

    from scripts.task_runner import _run_task
    _run_task(db, task_id, "wizard_generate", 0, params=params)

    import sqlite3
    conn = sqlite3.connect(db)
    row = conn.execute("SELECT status FROM background_tasks WHERE id=?", (task_id,)).fetchone()
    conn.close()
    assert row[0] == "failed"


def test_wizard_generate_null_params_fails(tmp_path):
    """wizard_generate with params=None marks task failed."""
    db = tmp_path / "t.db"
    from scripts.db import init_db, insert_task
    init_db(db)

    task_id, _ = insert_task(db, "wizard_generate", 0, params=None)

    from scripts.task_runner import _run_task
    _run_task(db, task_id, "wizard_generate", 0, params=None)

    import sqlite3
    conn = sqlite3.connect(db)
    row = conn.execute("SELECT status FROM background_tasks WHERE id=?", (task_id,)).fetchone()
    conn.close()
    assert row[0] == "failed"


def test_wizard_generate_stores_result_as_json(tmp_path):
    """wizard_generate stores result JSON in error field on success."""
    from unittest.mock import patch, MagicMock
    db = tmp_path / "t.db"
    from scripts.db import init_db, insert_task
    init_db(db)

    params = _json.dumps({"section": "career_summary", "input": {"resume_text": "10 years Python"}})
    task_id, _ = insert_task(db, "wizard_generate", 0, params=params)

    # Mock _run_wizard_generate to return a simple string
    with patch("scripts.task_runner._run_wizard_generate", return_value="Experienced Python developer."):
        from scripts.task_runner import _run_task
        _run_task(db, task_id, "wizard_generate", 0, params=params)

    import sqlite3
    conn = sqlite3.connect(db)
    row = conn.execute("SELECT status, error FROM background_tasks WHERE id=?", (task_id,)).fetchone()
    conn.close()

    assert row[0] == "completed", f"Expected 'completed', got '{row[0]}'"
    payload = _json.loads(row[1])
    assert payload["section"] == "career_summary"
    assert payload["result"] == "Experienced Python developer."


def test_wizard_generate_feedback_appended_to_prompt(tmp_path):
    """feedback and previous_result fields in input_data are appended to the prompt."""
    from unittest.mock import patch, MagicMock
    db = tmp_path / "t.db"
    from scripts.db import init_db, insert_task
    init_db(db)

    captured_prompts = []

    def mock_complete(prompt):
        captured_prompts.append(prompt)
        return "Revised career summary."

    import json as _json
    params = _json.dumps({
        "section": "career_summary",
        "input": {
            "resume_text": "10 years Python dev",
            "previous_result": "Original summary text.",
            "feedback": "Make it shorter and focus on leadership.",
        }
    })
    task_id, _ = insert_task(db, "wizard_generate", 0, params=params)

    with patch("scripts.llm_router.LLMRouter") as MockRouter:
        MockRouter.return_value.complete.side_effect = mock_complete
        from scripts.task_runner import _run_task
        _run_task(db, task_id, "wizard_generate", 0, params=params)

    assert len(captured_prompts) == 1
    prompt_used = captured_prompts[0]
    assert "Original summary text." in prompt_used
    assert "Make it shorter and focus on leadership." in prompt_used
    assert "Please revise accordingly." in prompt_used


def test_wizard_generate_no_feedback_no_revision_block(tmp_path):
    """When no feedback/previous_result provided, prompt has no revision block."""
    from unittest.mock import patch
    db = tmp_path / "t.db"
    from scripts.db import init_db, insert_task
    init_db(db)

    captured_prompts = []

    import json as _json
    params = _json.dumps({
        "section": "career_summary",
        "input": {"resume_text": "5 years QA engineer"}
    })
    task_id, _ = insert_task(db, "wizard_generate", 0, params=params)

    with patch("scripts.llm_router.LLMRouter") as MockRouter:
        MockRouter.return_value.complete.side_effect = lambda p: (captured_prompts.append(p) or "Summary.")
        from scripts.task_runner import _run_task
        _run_task(db, task_id, "wizard_generate", 0, params=params)

    assert "Please revise accordingly." not in captured_prompts[0]
    assert "Previous output:" not in captured_prompts[0]
