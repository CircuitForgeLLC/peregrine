"""Tests for imap_sync helpers (no live IMAP connection required)."""
import pytest
from unittest.mock import patch, MagicMock


def test_classify_stage_signal_interview():
    """classify_stage_signal returns interview_scheduled for a call-scheduling email."""
    from scripts.imap_sync import classify_stage_signal
    with patch("scripts.imap_sync._CLASSIFIER_ROUTER") as mock_router:
        mock_router.complete.return_value = "interview_scheduled"
        result = classify_stage_signal(
            "Let's schedule a call",
            "Hi Alex, we'd love to book a 30-min phone screen with you.",
        )
    assert result == "interview_scheduled"


def test_classify_stage_signal_returns_none_on_error():
    """classify_stage_signal returns None when LLM call raises."""
    from scripts.imap_sync import classify_stage_signal
    with patch("scripts.imap_sync._CLASSIFIER_ROUTER") as mock_router:
        mock_router.complete.side_effect = RuntimeError("model not loaded")
        result = classify_stage_signal("subject", "body")
    assert result is None


def test_classify_stage_signal_strips_think_tags():
    """classify_stage_signal strips <think>...</think> blocks before parsing."""
    from scripts.imap_sync import classify_stage_signal
    with patch("scripts.imap_sync._CLASSIFIER_ROUTER") as mock_router:
        mock_router.complete.return_value = "<think>Let me think...</think>\nrejected"
        result = classify_stage_signal("Update on your application", "We went with another candidate.")
    assert result == "rejected"


def test_normalise_company():
    """_normalise_company strips legal suffixes."""
    from scripts.imap_sync import _normalise_company
    assert _normalise_company("DataStax, Inc.") == "DataStax"
    assert _normalise_company("Wiz Ltd") == "Wiz"
    assert _normalise_company("Crusoe Energy") == "Crusoe Energy"


def test_company_search_terms_excludes_job_board_sld():
    """Job-board domains like linkedin.com are never used as match terms."""
    from scripts.imap_sync import _company_search_terms
    # LinkedIn-sourced job: SLD "linkedin" must not appear in the terms
    terms = _company_search_terms("Bamboo Health", "https://www.linkedin.com/jobs/view/123")
    assert "linkedin" not in terms
    assert "bamboo health" in terms

    # Company with its own domain: SLD should be included
    terms = _company_search_terms("Crusoe Energy", "https://crusoe.ai/jobs/456")
    assert "crusoe" in terms

    # Indeed-sourced job: "indeed" excluded
    terms = _company_search_terms("DoorDash", "https://www.indeed.com/viewjob?jk=abc")
    assert "indeed" not in terms
    assert "doordash" in terms


def test_has_recruitment_keyword():
    """_has_recruitment_keyword matches known keywords."""
    from scripts.imap_sync import _has_recruitment_keyword
    assert _has_recruitment_keyword("Interview Invitation — Senior TAM")
    assert _has_recruitment_keyword("Your application with DataStax")
    assert not _has_recruitment_keyword("Team lunch tomorrow")


def test_extract_lead_info_returns_company_and_title():
    """extract_lead_info parses LLM JSON response into (company, title)."""
    from scripts.imap_sync import extract_lead_info
    with patch("scripts.imap_sync._CLASSIFIER_ROUTER") as mock_router:
        mock_router.complete.return_value = '{"company": "Wiz", "title": "Senior TAM"}'
        result = extract_lead_info("Senior TAM at Wiz", "Hi Alex, we have a role…", "recruiter@wiz.com")
    assert result == ("Wiz", "Senior TAM")


def test_extract_lead_info_returns_none_on_bad_json():
    """extract_lead_info returns (None, None) when LLM returns unparseable output."""
    from scripts.imap_sync import extract_lead_info
    with patch("scripts.imap_sync._CLASSIFIER_ROUTER") as mock_router:
        mock_router.complete.return_value = "I cannot determine the company."
        result = extract_lead_info("Job opportunity", "blah", "noreply@example.com")
    assert result == (None, None)


def test_classify_labels_includes_survey_received():
    """_CLASSIFY_LABELS includes survey_received."""
    from scripts.imap_sync import _CLASSIFY_LABELS
    assert "survey_received" in _CLASSIFY_LABELS


def test_classify_stage_signal_returns_survey_received():
    """classify_stage_signal returns 'survey_received' when LLM outputs that label."""
    from unittest.mock import patch
    from scripts.imap_sync import classify_stage_signal

    with patch("scripts.imap_sync._CLASSIFIER_ROUTER") as mock_router:
        mock_router.complete.return_value = "survey_received"
        result = classify_stage_signal("Complete our culture survey", "Please fill out this form")
    assert result == "survey_received"


def test_sync_job_emails_classifies_inbound(tmp_path):
    """sync_job_emails classifies inbound emails and stores the stage_signal."""
    from scripts.db import init_db, insert_job, get_contacts
    from scripts.imap_sync import sync_job_emails

    db_path = tmp_path / "test.db"
    init_db(db_path)
    job_id = insert_job(db_path, {
        "title": "CSM", "company": "Acme",
        "url": "https://acme.com/jobs/1",
        "source": "linkedin", "location": "Remote",
        "is_remote": True, "salary": "", "description": "",
        "date_found": "2026-02-21",
    })
    job = {"id": job_id, "company": "Acme", "url": "https://acme.com/jobs/1"}

    fake_msg_bytes = (
        b"From: recruiter@acme.com\r\n"
        b"To: alex@example.com\r\n"
        b"Subject: Interview Invitation\r\n"
        b"Message-ID: <unique-001@acme.com>\r\n"
        b"\r\n"
        b"Hi Alex, we'd like to schedule a phone screen."
    )

    conn_mock = MagicMock()
    conn_mock.select.return_value = ("OK", [b"1"])
    conn_mock.search.return_value = ("OK", [b"1"])
    conn_mock.fetch.return_value = ("OK", [(b"1 (RFC822 {123})", fake_msg_bytes)])

    with patch("scripts.imap_sync.classify_stage_signal", return_value="interview_scheduled"):
        inb, out = sync_job_emails(job, conn_mock, {"lookback_days": 90}, db_path)

    assert inb == 1
    contacts = get_contacts(db_path, job_id=job_id)
    assert contacts[0]["stage_signal"] == "interview_scheduled"


def test_parse_linkedin_alert_extracts_jobs():
    from scripts.imap_sync import parse_linkedin_alert
    body = """\
Your job alert for customer success manager in United States
New jobs match your preferences.
Manage alerts: https://www.linkedin.com/comm/jobs/alerts?...

Customer Success Manager
Reflow
California, United States
View job: https://www.linkedin.com/comm/jobs/view/4376518925/?trackingId=abc%3D%3D&refId=xyz

---------------------------------------------------------

Customer Engagement Manager
Bitwarden
United States

2 school alumni
Apply with resume & profile
View job: https://www.linkedin.com/comm/jobs/view/4359824983/?trackingId=def%3D%3D

---------------------------------------------------------

"""
    jobs = parse_linkedin_alert(body)
    assert len(jobs) == 2
    assert jobs[0]["title"] == "Customer Success Manager"
    assert jobs[0]["company"] == "Reflow"
    assert jobs[0]["location"] == "California, United States"
    assert jobs[0]["url"] == "https://www.linkedin.com/jobs/view/4376518925/"
    assert jobs[1]["title"] == "Customer Engagement Manager"
    assert jobs[1]["company"] == "Bitwarden"
    assert jobs[1]["url"] == "https://www.linkedin.com/jobs/view/4359824983/"


def test_parse_linkedin_alert_skips_blocks_without_view_job():
    from scripts.imap_sync import parse_linkedin_alert
    body = """\
Customer Success Manager
Some Company
United States

---------------------------------------------------------

Valid Job Title
Valid Company
Remote
View job: https://www.linkedin.com/comm/jobs/view/1111111/?x=y

---------------------------------------------------------
"""
    jobs = parse_linkedin_alert(body)
    assert len(jobs) == 1
    assert jobs[0]["title"] == "Valid Job Title"


def test_parse_linkedin_alert_empty_body():
    from scripts.imap_sync import parse_linkedin_alert
    assert parse_linkedin_alert("") == []
    assert parse_linkedin_alert("No jobs here.") == []


# ── _scan_unmatched_leads integration ─────────────────────────────────────────

_ALERT_BODY = """\
Your job alert for customer success manager in United States
New jobs match your preferences.

Customer Success Manager
Acme Corp
California, United States
View job: https://www.linkedin.com/comm/jobs/view/9999001/?trackingId=abc

---------------------------------------------------------

Director of Customer Success
Beta Inc
Remote
View job: https://www.linkedin.com/comm/jobs/view/9999002/?trackingId=def

---------------------------------------------------------
"""

_ALERT_EMAIL = {
    "message_id": "<alert-001@linkedin.com>",
    "from_addr": "jobalerts-noreply@linkedin.com",
    "to_addr": "alex@example.com",
    "subject": "2 new jobs for customer success manager",
    "body": _ALERT_BODY,
    "date": "2026-02-24 12:00:00",
}


def test_scan_unmatched_leads_linkedin_alert_inserts_jobs(tmp_path):
    """_scan_unmatched_leads detects a LinkedIn alert and inserts each job card."""
    import sqlite3
    from unittest.mock import patch, MagicMock
    from scripts.db import init_db

    db_path = tmp_path / "test.db"
    init_db(db_path)

    conn_mock = MagicMock()

    with patch("scripts.imap_sync._search_folder", return_value=[b"1"]), \
         patch("scripts.imap_sync._parse_message", return_value=_ALERT_EMAIL), \
         patch("scripts.task_runner.submit_task") as mock_submit:

        from scripts.imap_sync import _scan_unmatched_leads
        known_ids: set = set()
        new_leads = _scan_unmatched_leads(conn_mock, {"lookback_days": 90}, db_path, known_ids)

    assert new_leads == 2

    # Message ID added so it won't be reprocessed
    assert "<alert-001@linkedin.com>" in known_ids

    # Both jobs inserted with correct fields
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    jobs = conn.execute("SELECT * FROM jobs ORDER BY id").fetchall()
    conn.close()

    assert len(jobs) == 2
    assert jobs[0]["title"] == "Customer Success Manager"
    assert jobs[0]["company"] == "Acme Corp"
    assert jobs[0]["url"] == "https://www.linkedin.com/jobs/view/9999001/"
    assert jobs[0]["source"] == "linkedin"
    assert jobs[1]["title"] == "Director of Customer Success"
    assert jobs[1]["url"] == "https://www.linkedin.com/jobs/view/9999002/"

    # scrape_url task submitted for each inserted job
    assert mock_submit.call_count == 2
    task_types = [call.args[1] for call in mock_submit.call_args_list]
    assert task_types == ["scrape_url", "scrape_url"]


def test_scan_unmatched_leads_linkedin_alert_skips_duplicates(tmp_path):
    """URLs already in the DB are not re-inserted."""
    from unittest.mock import patch, MagicMock
    from scripts.db import init_db, insert_job

    db_path = tmp_path / "test.db"
    init_db(db_path)

    # Pre-insert one of the two URLs
    insert_job(db_path, {
        "title": "Customer Success Manager", "company": "Acme Corp",
        "url": "https://www.linkedin.com/jobs/view/9999001/",
        "source": "linkedin", "location": "", "is_remote": 0,
        "salary": "", "description": "", "date_found": "2026-02-24",
    })

    conn_mock = MagicMock()

    with patch("scripts.imap_sync._search_folder", return_value=[b"1"]), \
         patch("scripts.imap_sync._parse_message", return_value=_ALERT_EMAIL), \
         patch("scripts.task_runner.submit_task") as mock_submit:

        from scripts.imap_sync import _scan_unmatched_leads
        new_leads = _scan_unmatched_leads(conn_mock, {"lookback_days": 90}, db_path, set())

    # Only one new job (the duplicate was skipped)
    assert new_leads == 1
    assert mock_submit.call_count == 1


def test_scan_unmatched_leads_linkedin_alert_skips_llm_path(tmp_path):
    """After a LinkedIn alert email, the LLM extraction path is never reached."""
    from unittest.mock import patch, MagicMock
    from scripts.db import init_db

    db_path = tmp_path / "test.db"
    init_db(db_path)

    conn_mock = MagicMock()

    with patch("scripts.imap_sync._search_folder", return_value=[b"1"]), \
         patch("scripts.imap_sync._parse_message", return_value=_ALERT_EMAIL), \
         patch("scripts.task_runner.submit_task"), \
         patch("scripts.imap_sync.extract_lead_info") as mock_llm:

        from scripts.imap_sync import _scan_unmatched_leads
        _scan_unmatched_leads(conn_mock, {"lookback_days": 90}, db_path, set())

    # LLM extraction must never be called for alert emails
    mock_llm.assert_not_called()
