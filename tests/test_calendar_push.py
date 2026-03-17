# tests/test_calendar_push.py
"""Unit tests for scripts/calendar_push.py.

Integration classes are mocked — no real CalDAV or Google API calls.
"""
import sys
from datetime import timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _make_db(tmp_path, interview_date="2026-04-15", calendar_event_id=None):
    from scripts.db import init_db, insert_job, set_interview_date, set_calendar_event_id
    db = tmp_path / "test.db"
    init_db(db)
    job_id = insert_job(db, {
        "title": "Customer Success Manager", "company": "Acme Corp",
        "url": "https://example.com/job/1", "source": "linkedin",
        "location": "Remote", "is_remote": True,
        "salary": "", "description": "Great role.", "date_found": "2026-04-01",
        "status": "phone_screen",
    })
    if interview_date:
        set_interview_date(db, job_id=job_id, date_str=interview_date)
    if calendar_event_id:
        set_calendar_event_id(db, job_id=job_id, event_id=calendar_event_id)
    return db, job_id


def _config_dir_with(tmp_path, integration_name: str) -> Path:
    """Create a minimal integration config file and return the config dir."""
    integrations_dir = tmp_path / "config" / "integrations"
    integrations_dir.mkdir(parents=True)
    (integrations_dir / f"{integration_name}.yaml").write_text(
        "caldav_url: https://caldav.example.com/\n"
        "username: user@example.com\n"
        "app_password: test-password\n"
        "calendar_name: Interviews\n"
    )
    return tmp_path / "config"


# ── No integration configured ─────────────────────────────────────────────────

def test_push_returns_error_when_no_integration_configured(tmp_path):
    db, job_id = _make_db(tmp_path)
    config_dir = tmp_path / "config"
    config_dir.mkdir()

    from scripts.calendar_push import push_interview_event
    result = push_interview_event(db, job_id=job_id, config_dir=config_dir)

    assert result["ok"] is False
    assert "No calendar integration" in result["error"]


# ── No interview date ─────────────────────────────────────────────────────────

def test_push_returns_error_when_no_interview_date(tmp_path):
    db, job_id = _make_db(tmp_path, interview_date=None)
    config_dir = _config_dir_with(tmp_path, "apple_calendar")

    from scripts.calendar_push import push_interview_event
    result = push_interview_event(db, job_id=job_id, config_dir=config_dir)

    assert result["ok"] is False
    assert "No interview date" in result["error"]


# ── Successful create ─────────────────────────────────────────────────────────

def test_push_creates_event_and_stores_event_id(tmp_path):
    db, job_id = _make_db(tmp_path)
    config_dir = _config_dir_with(tmp_path, "apple_calendar")

    mock_integration = MagicMock()
    mock_integration.create_event.return_value = "peregrine-job-1@circuitforge.tech"

    with patch("scripts.calendar_push._load_integration", return_value=mock_integration):
        from scripts.calendar_push import push_interview_event
        result = push_interview_event(db, job_id=job_id, config_dir=config_dir)

    assert result["ok"] is True
    assert result["event_id"] == "peregrine-job-1@circuitforge.tech"
    mock_integration.create_event.assert_called_once()


def test_push_event_title_includes_stage_and_company(tmp_path):
    db, job_id = _make_db(tmp_path)
    from scripts.db import advance_to_stage
    advance_to_stage(db, job_id=job_id, stage="phone_screen")
    config_dir = _config_dir_with(tmp_path, "apple_calendar")

    mock_integration = MagicMock()
    mock_integration.create_event.return_value = "uid-123"

    with patch("scripts.calendar_push._load_integration", return_value=mock_integration):
        from scripts.calendar_push import push_interview_event
        push_interview_event(db, job_id=job_id, config_dir=config_dir)

    call_kwargs = mock_integration.create_event.call_args
    title = call_kwargs.args[1] if call_kwargs.args else call_kwargs.kwargs.get("title", "")
    assert "Acme Corp" in title
    assert "Phone Screen" in title


def test_push_event_start_is_noon_utc(tmp_path):
    db, job_id = _make_db(tmp_path, interview_date="2026-04-15")
    config_dir = _config_dir_with(tmp_path, "apple_calendar")

    mock_integration = MagicMock()
    mock_integration.create_event.return_value = "uid-abc"

    with patch("scripts.calendar_push._load_integration", return_value=mock_integration):
        from scripts.calendar_push import push_interview_event
        push_interview_event(db, job_id=job_id, config_dir=config_dir)

    call_args = mock_integration.create_event.call_args.args
    start_dt = call_args[2]
    assert start_dt.hour == 12
    assert start_dt.tzinfo == timezone.utc


def test_push_event_duration_is_one_hour(tmp_path):
    db, job_id = _make_db(tmp_path, interview_date="2026-04-15")
    config_dir = _config_dir_with(tmp_path, "apple_calendar")

    mock_integration = MagicMock()
    mock_integration.create_event.return_value = "uid-abc"

    with patch("scripts.calendar_push._load_integration", return_value=mock_integration):
        from scripts.calendar_push import push_interview_event
        push_interview_event(db, job_id=job_id, config_dir=config_dir)

    call_args = mock_integration.create_event.call_args.args
    start_dt, end_dt = call_args[2], call_args[3]
    assert (end_dt - start_dt).seconds == 3600


# ── Idempotent update ─────────────────────────────────────────────────────────

def test_push_calls_update_when_event_id_already_exists(tmp_path):
    db, job_id = _make_db(tmp_path, calendar_event_id="existing-event-id")
    config_dir = _config_dir_with(tmp_path, "apple_calendar")

    mock_integration = MagicMock()
    mock_integration.update_event.return_value = "existing-event-id"

    with patch("scripts.calendar_push._load_integration", return_value=mock_integration):
        from scripts.calendar_push import push_interview_event
        result = push_interview_event(db, job_id=job_id, config_dir=config_dir)

    assert result["ok"] is True
    mock_integration.update_event.assert_called_once()
    mock_integration.create_event.assert_not_called()


# ── Integration error handling ────────────────────────────────────────────────

def test_push_returns_error_on_integration_exception(tmp_path):
    db, job_id = _make_db(tmp_path)
    config_dir = _config_dir_with(tmp_path, "apple_calendar")

    mock_integration = MagicMock()
    mock_integration.create_event.side_effect = RuntimeError("CalDAV server unreachable")

    with patch("scripts.calendar_push._load_integration", return_value=mock_integration):
        from scripts.calendar_push import push_interview_event
        result = push_interview_event(db, job_id=job_id, config_dir=config_dir)

    assert result["ok"] is False
    assert "CalDAV server unreachable" in result["error"]


# ── Missing job ───────────────────────────────────────────────────────────────

def test_push_returns_error_for_unknown_job_id(tmp_path):
    from scripts.db import init_db
    db = tmp_path / "test.db"
    init_db(db)
    config_dir = _config_dir_with(tmp_path, "apple_calendar")

    from scripts.calendar_push import push_interview_event
    result = push_interview_event(db, job_id=9999, config_dir=config_dir)

    assert result["ok"] is False
    assert "9999" in result["error"]
