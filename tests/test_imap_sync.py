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


# ── _has_rejection_or_ats_signal ──────────────────────────────────────────────

def test_rejection_phrase_at_body_boundary():
    """Rejection phrase at char 1501 is NOT caught — only first 1500 chars checked."""
    from scripts.imap_sync import _has_rejection_or_ats_signal
    # "unfortunately" appears just past the 1500-char window
    padding = "x " * 750   # 1500 chars
    body = padding + "unfortunately we will not be moving forward"
    assert _has_rejection_or_ats_signal("No subject match", body) is False


def test_rejection_phrase_within_body_limit():
    """Rejection phrase within first 1500 chars IS caught."""
    from scripts.imap_sync import _has_rejection_or_ats_signal
    body = "We regret to inform you that we will not be moving forward."
    assert _has_rejection_or_ats_signal("Application Update", body) is True


def test_dont_forget_right_single_quote():
    """Right single quotation mark (\u2019) in 'don\u2019t forget' is blocked."""
    from scripts.imap_sync import _has_rejection_or_ats_signal
    body = "don\u2019t forget to complete your application"
    assert _has_rejection_or_ats_signal("Reminder", body) is True


def test_dont_forget_left_single_quote():
    """Left single quotation mark (\u2018) in 'don\u2018t forget' is blocked."""
    from scripts.imap_sync import _has_rejection_or_ats_signal
    body = "don\u2018t forget to complete your application"
    assert _has_rejection_or_ats_signal("Reminder", body) is True


def test_ats_subject_phrase_not_matched_in_body_only():
    """ATS confirm phrase in body alone does NOT trigger — subject-only check."""
    from scripts.imap_sync import _has_rejection_or_ats_signal
    # "thank you for applying" is an ATS subject phrase; must NOT be caught in body only
    body = "Hi Alex, thank you for applying to our Senior TAM role. We'd love to chat."
    assert _has_rejection_or_ats_signal("Interview Invitation", body) is False


def test_ats_subject_phrase_matched_in_subject():
    """ATS confirm phrase in subject triggers the filter."""
    from scripts.imap_sync import _has_rejection_or_ats_signal
    assert _has_rejection_or_ats_signal("Thank you for applying to Acme", "") is True


def test_spam_subject_prefix_at_sign():
    """Subject starting with '@' is blocked (Depop / social commerce pattern)."""
    from scripts.imap_sync import _has_rejection_or_ats_signal
    assert _has_rejection_or_ats_signal("@user sent you a special offer", "") is True


def test_rejection_uppercase_lowercased():
    """'UNFORTUNATELY' in body is downcased and caught correctly."""
    from scripts.imap_sync import _has_rejection_or_ats_signal
    assert _has_rejection_or_ats_signal("Update", "UNFORTUNATELY we have decided to go another direction.") is True


def test_rejection_phrase_in_quoted_thread_beyond_limit_not_blocked():
    """Rejection phrase beyond 1500-char body window does not block the email."""
    from scripts.imap_sync import _has_rejection_or_ats_signal
    clean_intro = "Hi Alex, we'd love to schedule a call with you. " * 32  # ~1500 chars
    quoted_footer = "\n\nOn Mon, Jan 1 wrote:\n> Unfortunately we went with another candidate."
    body = clean_intro + quoted_footer
    # The phrase lands after the 1500-char cutoff — should NOT be blocked
    assert _has_rejection_or_ats_signal("Interview Invitation", body) is False


# ── _quote_folder ─────────────────────────────────────────────────────────────

def test_quote_folder_with_spaces():
    from scripts.imap_sync import _quote_folder
    assert _quote_folder("TO DO JOBS") == '"TO DO JOBS"'


def test_quote_folder_no_spaces():
    from scripts.imap_sync import _quote_folder
    assert _quote_folder("INBOX") == "INBOX"


def test_quote_folder_internal_double_quotes():
    from scripts.imap_sync import _quote_folder
    assert _quote_folder('My "Jobs"') == '"My \\"Jobs\\""'


# ── _search_folder ────────────────────────────────────────────────────────────

def test_search_folder_nonexistent_returns_empty():
    """_search_folder returns [] when folder SELECT raises (folder doesn't exist)."""
    from scripts.imap_sync import _search_folder
    conn = MagicMock()
    conn.select.side_effect = Exception("NO folder not found")
    result = _search_folder(conn, "DOES_NOT_EXIST", "ALL", "01-Jan-2026")
    assert result == []


def test_search_folder_special_gmail_name():
    """[Gmail]/All Mail folder name is quoted because it contains a space."""
    from scripts.imap_sync import _search_folder
    conn = MagicMock()
    conn.select.return_value = ("OK", [b"1"])
    conn.search.return_value = ("OK", [b"1 2"])
    result = _search_folder(conn, "[Gmail]/All Mail", "ALL", "01-Jan-2026")
    # Should not raise; select should be called with the quoted form
    conn.select.assert_called_once_with('"[Gmail]/All Mail"', readonly=True)
    assert result == [b"1", b"2"]


# ── _get_existing_message_ids ─────────────────────────────────────────────────

def test_get_existing_message_ids_excludes_null(tmp_path):
    """NULL message_id rows are excluded from the returned set."""
    import sqlite3
    from scripts.db import init_db, insert_job, add_contact
    from scripts.imap_sync import _get_existing_message_ids

    db_path = tmp_path / "test.db"
    init_db(db_path)
    job_id = insert_job(db_path, {
        "title": "CSM", "company": "Acme", "url": "https://acme.com/1",
        "source": "test", "location": "", "is_remote": 0,
        "salary": "", "description": "", "date_found": "2026-01-01",
    })
    # Insert contact with NULL message_id via raw SQL
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO job_contacts (job_id, direction, subject, from_addr, body, received_at) "
        "VALUES (?, 'inbound', 'subj', 'f@x.com', 'body', '2026-01-01')",
        (job_id,)
    )
    conn.commit()
    conn.close()

    ids = _get_existing_message_ids(job_id, db_path)
    assert None not in ids
    assert "" not in ids


def test_get_existing_message_ids_excludes_empty_string(tmp_path):
    """Empty-string message_id rows are excluded."""
    import sqlite3
    from scripts.db import init_db, insert_job
    from scripts.imap_sync import _get_existing_message_ids

    db_path = tmp_path / "test.db"
    init_db(db_path)
    job_id = insert_job(db_path, {
        "title": "CSM", "company": "Acme", "url": "https://acme.com/2",
        "source": "test", "location": "", "is_remote": 0,
        "salary": "", "description": "", "date_found": "2026-01-01",
    })
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO job_contacts (job_id, direction, subject, from_addr, body, received_at, message_id) "
        "VALUES (?, 'inbound', 'subj', 'f@x.com', 'body', '2026-01-01', '')",
        (job_id,)
    )
    conn.commit()
    conn.close()

    ids = _get_existing_message_ids(job_id, db_path)
    assert "" not in ids


def test_get_existing_message_ids_no_contacts(tmp_path):
    """Job with no contacts returns an empty set."""
    from scripts.db import init_db, insert_job
    from scripts.imap_sync import _get_existing_message_ids

    db_path = tmp_path / "test.db"
    init_db(db_path)
    job_id = insert_job(db_path, {
        "title": "CSM", "company": "Acme", "url": "https://acme.com/3",
        "source": "test", "location": "", "is_remote": 0,
        "salary": "", "description": "", "date_found": "2026-01-01",
    })
    assert _get_existing_message_ids(job_id, db_path) == set()


# ── _parse_message ────────────────────────────────────────────────────────────

def test_parse_message_no_message_id_returns_none():
    """Email with no Message-ID header returns None."""
    from scripts.imap_sync import _parse_message

    raw = (
        b"From: recruiter@acme.com\r\n"
        b"Subject: Interview Invitation\r\n"
        b"\r\n"
        b"Hi Alex!"
    )
    conn = MagicMock()
    conn.fetch.return_value = ("OK", [(b"1 (RFC822 {40})", raw)])
    assert _parse_message(conn, b"1") is None


def test_parse_message_rfc2047_subject_decoded():
    """RFC2047-encoded subject is decoded correctly."""
    from scripts.imap_sync import _parse_message

    # "Interview" encoded as UTF-8 base64
    raw = (
        b"From: recruiter@acme.com\r\n"
        b"Message-ID: <decode-test@acme.com>\r\n"
        b"Subject: =?utf-8?b?SW50ZXJ2aWV3?=\r\n"
        b"\r\n"
        b"Let's schedule a call."
    )
    conn = MagicMock()
    conn.fetch.return_value = ("OK", [(b"1 (RFC822 {100})", raw)])
    result = _parse_message(conn, b"1")
    assert result is not None
    assert "Interview" in result["subject"]


# ── classify_stage_signal ─────────────────────────────────────────────────────

def test_classify_stage_signal_returns_neutral_on_no_label_match():
    """Returns 'neutral' when LLM output matches no known label."""
    from scripts.imap_sync import classify_stage_signal
    with patch("scripts.imap_sync._CLASSIFIER_ROUTER") as mock_router:
        mock_router.complete.return_value = "I cannot determine the category."
        result = classify_stage_signal("Generic update", "No clear signal here.")
    assert result == "neutral"


# ── extract_lead_info ─────────────────────────────────────────────────────────

def test_extract_lead_info_returns_none_on_llm_error():
    """extract_lead_info returns (None, None) when LLM call raises."""
    from scripts.imap_sync import extract_lead_info
    with patch("scripts.imap_sync._CLASSIFIER_ROUTER") as mock_router:
        mock_router.complete.side_effect = RuntimeError("timeout")
        result = extract_lead_info("Senior TAM at Wiz", "Hi Alex…", "r@wiz.com")
    assert result == (None, None)


# ── _scan_unmatched_leads — signal gating ─────────────────────────────────────

_PLAIN_RECRUIT_EMAIL = {
    "message_id": "<recruit-001@acme.com>",
    "from_addr": "recruiter@acme.com",
    "to_addr": "alex@example.com",
    "subject": "Interview Opportunity at Acme",
    "body": "Hi Alex, we have an exciting opportunity for you.",
    "date": "2026-02-25 10:00:00",
}


def test_scan_unmatched_leads_skips_when_signal_none(tmp_path):
    """When classify_stage_signal returns None, lead is not inserted."""
    from scripts.db import init_db
    from scripts.imap_sync import _scan_unmatched_leads

    db_path = tmp_path / "test.db"
    init_db(db_path)

    with patch("scripts.imap_sync._search_folder", return_value=[b"1"]), \
         patch("scripts.imap_sync._parse_message", return_value=_PLAIN_RECRUIT_EMAIL), \
         patch("scripts.imap_sync.classify_stage_signal", return_value=None), \
         patch("scripts.imap_sync.extract_lead_info") as mock_extract:
        result = _scan_unmatched_leads(MagicMock(), {"lookback_days": 90}, db_path, set())

    assert result == 0
    mock_extract.assert_not_called()


def test_scan_unmatched_leads_skips_when_signal_rejected(tmp_path):
    """When signal is 'rejected', lead is not inserted."""
    from scripts.db import init_db
    from scripts.imap_sync import _scan_unmatched_leads

    db_path = tmp_path / "test.db"
    init_db(db_path)

    with patch("scripts.imap_sync._search_folder", return_value=[b"1"]), \
         patch("scripts.imap_sync._parse_message", return_value=_PLAIN_RECRUIT_EMAIL), \
         patch("scripts.imap_sync.classify_stage_signal", return_value="rejected"), \
         patch("scripts.imap_sync.extract_lead_info") as mock_extract:
        result = _scan_unmatched_leads(MagicMock(), {"lookback_days": 90}, db_path, set())

    assert result == 0
    mock_extract.assert_not_called()


def test_scan_unmatched_leads_proceeds_when_signal_neutral(tmp_path):
    """When signal is 'neutral', LLM extraction is still attempted."""
    from scripts.db import init_db
    from scripts.imap_sync import _scan_unmatched_leads

    db_path = tmp_path / "test.db"
    init_db(db_path)

    with patch("scripts.imap_sync._search_folder", return_value=[b"1"]), \
         patch("scripts.imap_sync._parse_message", return_value=_PLAIN_RECRUIT_EMAIL), \
         patch("scripts.imap_sync.classify_stage_signal", return_value="neutral"), \
         patch("scripts.imap_sync.extract_lead_info", return_value=("Acme", "Senior TAM")), \
         patch("scripts.task_runner.submit_task"):
        result = _scan_unmatched_leads(MagicMock(), {"lookback_days": 90}, db_path, set())

    assert result == 1


def test_scan_unmatched_leads_rejection_phrase_blocks_llm(tmp_path):
    """Email with rejection phrase in body is filtered before LLM is called."""
    from scripts.db import init_db
    from scripts.imap_sync import _scan_unmatched_leads

    db_path = tmp_path / "test.db"
    init_db(db_path)

    rejection_email = {**_PLAIN_RECRUIT_EMAIL,
                       "body": "Unfortunately we have decided not to move forward."}

    with patch("scripts.imap_sync._search_folder", return_value=[b"1"]), \
         patch("scripts.imap_sync._parse_message", return_value=rejection_email), \
         patch("scripts.imap_sync.classify_stage_signal") as mock_classify:
        result = _scan_unmatched_leads(MagicMock(), {"lookback_days": 90}, db_path, set())

    assert result == 0
    mock_classify.assert_not_called()


def test_scan_unmatched_leads_genuine_lead_has_synthetic_url(tmp_path):
    """A genuine lead is inserted with a synthetic email:// URL."""
    import sqlite3
    from scripts.db import init_db
    from scripts.imap_sync import _scan_unmatched_leads

    db_path = tmp_path / "test.db"
    init_db(db_path)

    with patch("scripts.imap_sync._search_folder", return_value=[b"1"]), \
         patch("scripts.imap_sync._parse_message", return_value=_PLAIN_RECRUIT_EMAIL), \
         patch("scripts.imap_sync.classify_stage_signal", return_value="interview_scheduled"), \
         patch("scripts.imap_sync.extract_lead_info", return_value=("Acme", "Senior TAM")), \
         patch("scripts.task_runner.submit_task"):
        result = _scan_unmatched_leads(MagicMock(), {"lookback_days": 90}, db_path, set())

    assert result == 1
    conn = sqlite3.connect(db_path)
    row = conn.execute("SELECT url FROM jobs LIMIT 1").fetchone()
    conn.close()
    assert row[0].startswith("email://")


def test_scan_unmatched_leads_no_reinsert_on_second_run(tmp_path):
    """Same email not re-inserted on a second sync run (known_message_ids dedup)."""
    from scripts.db import init_db
    from scripts.imap_sync import _scan_unmatched_leads

    db_path = tmp_path / "test.db"
    init_db(db_path)

    known = set()
    shared_kwargs = dict(
        conn=MagicMock(),
        cfg={"lookback_days": 90},
        db_path=db_path,
    )

    with patch("scripts.imap_sync._search_folder", return_value=[b"1"]), \
         patch("scripts.imap_sync._parse_message", return_value=_PLAIN_RECRUIT_EMAIL), \
         patch("scripts.imap_sync.classify_stage_signal", return_value="neutral"), \
         patch("scripts.imap_sync.extract_lead_info", return_value=("Acme", "TAM")), \
         patch("scripts.task_runner.submit_task"):
        first = _scan_unmatched_leads(**shared_kwargs, known_message_ids=known)
        second = _scan_unmatched_leads(**shared_kwargs, known_message_ids=known)

    assert first == 1
    assert second == 0


def test_scan_unmatched_leads_extract_none_no_insert(tmp_path):
    """When extract_lead_info returns (None, None), no job is inserted."""
    import sqlite3
    from scripts.db import init_db
    from scripts.imap_sync import _scan_unmatched_leads

    db_path = tmp_path / "test.db"
    init_db(db_path)

    with patch("scripts.imap_sync._search_folder", return_value=[b"1"]), \
         patch("scripts.imap_sync._parse_message", return_value=_PLAIN_RECRUIT_EMAIL), \
         patch("scripts.imap_sync.classify_stage_signal", return_value="neutral"), \
         patch("scripts.imap_sync.extract_lead_info", return_value=(None, None)):
        result = _scan_unmatched_leads(MagicMock(), {"lookback_days": 90}, db_path, set())

    assert result == 0
    conn = sqlite3.connect(db_path)
    count = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
    conn.close()
    assert count == 0


# ── _scan_todo_label ──────────────────────────────────────────────────────────

def _make_job(db_path, company="Acme", url="https://acme.com/job/1"):
    from scripts.db import init_db, insert_job
    init_db(db_path)
    return insert_job(db_path, {
        "title": "CSM", "company": company, "url": url,
        "source": "test", "location": "", "is_remote": 0,
        "salary": "", "description": "", "date_found": "2026-01-01",
    })


def test_scan_todo_label_empty_string_returns_zero(tmp_path):
    from scripts.imap_sync import _scan_todo_label
    db_path = tmp_path / "test.db"
    _make_job(db_path)
    assert _scan_todo_label(MagicMock(), {"todo_label": ""}, db_path, [], set()) == 0


def test_scan_todo_label_missing_key_returns_zero(tmp_path):
    from scripts.imap_sync import _scan_todo_label
    db_path = tmp_path / "test.db"
    _make_job(db_path)
    assert _scan_todo_label(MagicMock(), {}, db_path, [], set()) == 0


def test_scan_todo_label_folder_not_found_returns_zero(tmp_path):
    """When folder doesn't exist on server, returns 0 without crashing."""
    from scripts.imap_sync import _scan_todo_label
    db_path = tmp_path / "test.db"
    _make_job(db_path)
    with patch("scripts.imap_sync._search_folder", return_value=[]):
        result = _scan_todo_label(
            MagicMock(), {"todo_label": "TO DO JOBS", "lookback_days": 90},
            db_path, [], set()
        )
    assert result == 0


def test_scan_todo_label_email_matches_company_and_keyword(tmp_path):
    """Email matching company name + TODO action keyword gets attached."""
    from scripts.db import get_contacts
    from scripts.imap_sync import _scan_todo_label

    db_path = tmp_path / "test.db"
    job_id = _make_job(db_path)
    active_jobs = [{"id": job_id, "company": "Acme", "url": "https://acme.com/job/1"}]

    todo_email = {
        "message_id": "<todo-001@acme.com>",
        "from_addr": "recruiter@acme.com",
        "to_addr": "alex@example.com",
        "subject": "Interview scheduled with Acme",
        "body": "Hi Alex, your interview is confirmed.",
        "date": "2026-02-25 10:00:00",
    }

    with patch("scripts.imap_sync._search_folder", return_value=[b"1"]), \
         patch("scripts.imap_sync._parse_message", return_value=todo_email), \
         patch("scripts.imap_sync.classify_stage_signal", return_value="neutral"):
        result = _scan_todo_label(
            MagicMock(), {"todo_label": "TO DO JOBS", "lookback_days": 90},
            db_path, active_jobs, set()
        )

    assert result == 1
    contacts = get_contacts(db_path, job_id=job_id)
    assert len(contacts) == 1
    assert contacts[0]["subject"] == "Interview scheduled with Acme"


def test_scan_todo_label_no_action_keyword_skipped(tmp_path):
    """Email with company match but no TODO keyword is skipped."""
    from scripts.imap_sync import _scan_todo_label

    db_path = tmp_path / "test.db"
    job_id = _make_job(db_path)
    active_jobs = [{"id": job_id, "company": "Acme", "url": "https://acme.com/job/1"}]

    no_keyword_email = {
        "message_id": "<todo-002@acme.com>",
        "from_addr": "noreply@acme.com",
        "to_addr": "alex@example.com",
        "subject": "Acme newsletter",
        "body": "Company updates this week.",
        "date": "2026-02-25 10:00:00",
    }

    with patch("scripts.imap_sync._search_folder", return_value=[b"1"]), \
         patch("scripts.imap_sync._parse_message", return_value=no_keyword_email):
        result = _scan_todo_label(
            MagicMock(), {"todo_label": "TO DO JOBS", "lookback_days": 90},
            db_path, active_jobs, set()
        )

    assert result == 0


def test_scan_todo_label_no_company_match_skipped(tmp_path):
    """Email with no company name in from/subject/body[:300] is skipped."""
    from scripts.imap_sync import _scan_todo_label

    db_path = tmp_path / "test.db"
    job_id = _make_job(db_path, company="Acme")
    active_jobs = [{"id": job_id, "company": "Acme", "url": "https://acme.com/job/1"}]

    unrelated_email = {
        "message_id": "<todo-003@other.com>",
        "from_addr": "recruiter@other.com",
        "to_addr": "alex@example.com",
        "subject": "Interview scheduled with OtherCo",
        "body": "Hi Alex, interview with OtherCo confirmed.",
        "date": "2026-02-25 10:00:00",
    }

    with patch("scripts.imap_sync._search_folder", return_value=[b"1"]), \
         patch("scripts.imap_sync._parse_message", return_value=unrelated_email):
        result = _scan_todo_label(
            MagicMock(), {"todo_label": "TO DO JOBS", "lookback_days": 90},
            db_path, active_jobs, set()
        )

    assert result == 0


def test_scan_todo_label_duplicate_message_id_not_reinserted(tmp_path):
    """Email already in known_message_ids is not re-attached."""
    from scripts.imap_sync import _scan_todo_label

    db_path = tmp_path / "test.db"
    job_id = _make_job(db_path)
    active_jobs = [{"id": job_id, "company": "Acme", "url": "https://acme.com/job/1"}]

    todo_email = {
        "message_id": "<already-seen@acme.com>",
        "from_addr": "recruiter@acme.com",
        "to_addr": "alex@example.com",
        "subject": "Interview scheduled with Acme",
        "body": "Hi Alex.",
        "date": "2026-02-25 10:00:00",
    }

    known = {"<already-seen@acme.com>"}

    with patch("scripts.imap_sync._search_folder", return_value=[b"1"]), \
         patch("scripts.imap_sync._parse_message", return_value=todo_email):
        result = _scan_todo_label(
            MagicMock(), {"todo_label": "TO DO JOBS", "lookback_days": 90},
            db_path, active_jobs, known
        )

    assert result == 0


def test_scan_todo_label_stage_signal_set_for_non_neutral(tmp_path):
    """Non-neutral classifier signal is written to the contact row."""
    import sqlite3
    from scripts.imap_sync import _scan_todo_label

    db_path = tmp_path / "test.db"
    job_id = _make_job(db_path)
    active_jobs = [{"id": job_id, "company": "Acme", "url": "https://acme.com/job/1"}]

    todo_email = {
        "message_id": "<signal-001@acme.com>",
        "from_addr": "recruiter@acme.com",
        "to_addr": "alex@example.com",
        "subject": "Interview scheduled with Acme",
        "body": "Your phone screen is confirmed.",
        "date": "2026-02-25 10:00:00",
    }

    with patch("scripts.imap_sync._search_folder", return_value=[b"1"]), \
         patch("scripts.imap_sync._parse_message", return_value=todo_email), \
         patch("scripts.imap_sync.classify_stage_signal", return_value="interview_scheduled"):
        _scan_todo_label(
            MagicMock(), {"todo_label": "TO DO JOBS", "lookback_days": 90},
            db_path, active_jobs, set()
        )

    conn = sqlite3.connect(db_path)
    row = conn.execute("SELECT stage_signal FROM job_contacts LIMIT 1").fetchone()
    conn.close()
    assert row[0] == "interview_scheduled"


def test_scan_todo_label_body_fallback_matches(tmp_path):
    """Company name only in body[:300] still triggers a match (body fallback)."""
    from scripts.db import get_contacts
    from scripts.imap_sync import _scan_todo_label

    db_path = tmp_path / "test.db"
    job_id = _make_job(db_path, company="Acme")
    active_jobs = [{"id": job_id, "company": "Acme", "url": "https://acme.com/job/1"}]

    # Company not in from_addr or subject — only in body
    body_only_email = {
        "message_id": "<body-fallback@noreply.greenhouse.io>",
        "from_addr": "noreply@greenhouse.io",
        "to_addr": "alex@example.com",
        "subject": "Interview scheduled",
        "body": "Your interview with Acme has been confirmed for tomorrow.",
        "date": "2026-02-25 10:00:00",
    }

    with patch("scripts.imap_sync._search_folder", return_value=[b"1"]), \
         patch("scripts.imap_sync._parse_message", return_value=body_only_email), \
         patch("scripts.imap_sync.classify_stage_signal", return_value="neutral"):
        result = _scan_todo_label(
            MagicMock(), {"todo_label": "TO DO JOBS", "lookback_days": 90},
            db_path, active_jobs, set()
        )

    assert result == 1


# ── sync_all ──────────────────────────────────────────────────────────────────

def test_sync_all_no_active_jobs_returns_full_dict(tmp_path):
    """With no active jobs, sync_all returns a dict with all 6 expected keys."""
    from scripts.db import init_db
    from scripts.imap_sync import sync_all

    db_path = tmp_path / "test.db"
    init_db(db_path)

    with patch("scripts.imap_sync.load_config", return_value={}), \
         patch("scripts.imap_sync.get_interview_jobs", return_value={}):
        result = sync_all(db_path=db_path)

    expected_keys = {"synced", "inbound", "outbound", "new_leads", "todo_attached", "errors"}
    assert set(result.keys()) == expected_keys
    assert result["todo_attached"] == 0


def test_sync_all_on_stage_callback_fires(tmp_path):
    """on_stage callback is called with expected stage labels."""
    from scripts.db import init_db
    from scripts.imap_sync import sync_all

    db_path = tmp_path / "test.db"
    init_db(db_path)

    fake_job = {"id": 1, "company": "Acme", "url": "https://acme.com/1"}
    stages = []
    conn_mock = MagicMock()
    conn_mock.logout.return_value = ("OK", [])

    with patch("scripts.imap_sync.load_config", return_value={}), \
         patch("scripts.imap_sync.get_interview_jobs", return_value={"applied": [fake_job]}), \
         patch("scripts.imap_sync.connect", return_value=conn_mock), \
         patch("scripts.imap_sync.sync_job_emails", return_value=(0, 0)), \
         patch("scripts.db.get_all_message_ids", return_value=set()), \
         patch("scripts.imap_sync._scan_todo_label", return_value=0), \
         patch("scripts.imap_sync._scan_unmatched_leads", return_value=0):
        sync_all(db_path=db_path, on_stage=stages.append)

    assert "connecting" in stages
    assert "scanning todo label" in stages
    assert "scanning leads" in stages


def test_sync_all_per_job_exception_continues(tmp_path):
    """Exception for one job does not abort sync of remaining jobs."""
    from scripts.db import init_db
    from scripts.imap_sync import sync_all

    db_path = tmp_path / "test.db"
    init_db(db_path)

    fake_jobs = [
        {"id": 1, "company": "Co0", "url": "https://co0.com/1"},
        {"id": 2, "company": "Co1", "url": "https://co1.com/1"},
    ]
    conn_mock = MagicMock()
    conn_mock.logout.return_value = ("OK", [])

    call_count = {"n": 0}
    def flaky_sync(job, *args, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise RuntimeError("IMAP timeout")
        return (1, 0)

    with patch("scripts.imap_sync.load_config", return_value={}), \
         patch("scripts.imap_sync.get_interview_jobs", return_value={"applied": fake_jobs}), \
         patch("scripts.imap_sync.connect", return_value=conn_mock), \
         patch("scripts.imap_sync.sync_job_emails", side_effect=flaky_sync), \
         patch("scripts.db.get_all_message_ids", return_value=set()), \
         patch("scripts.imap_sync._scan_todo_label", return_value=0), \
         patch("scripts.imap_sync._scan_unmatched_leads", return_value=0):
        result = sync_all(db_path=db_path)

    assert len(result["errors"]) == 1
    assert result["synced"] == 1  # second job succeeded


# ── Performance / edge cases ──────────────────────────────────────────────────

def test_parse_message_large_body_truncated():
    """Body longer than 4000 chars is silently truncated to 4000."""
    from scripts.imap_sync import _parse_message

    big_body = ("x" * 10_000).encode()
    raw = (
        b"From: r@acme.com\r\nMessage-ID: <big@acme.com>\r\n"
        b"Subject: Interview\r\n\r\n"
    ) + big_body
    conn = MagicMock()
    conn.fetch.return_value = ("OK", [(b"1 (RFC822)", raw)])
    result = _parse_message(conn, b"1")
    assert result is not None
    assert len(result["body"]) <= 4000


def test_parse_message_binary_attachment_no_crash():
    """Email with binary attachment returns a valid dict without crashing."""
    from scripts.imap_sync import _parse_message
    import email as _email
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText
    from email.mime.application import MIMEApplication

    msg = MIMEMultipart()
    msg["From"] = "r@acme.com"
    msg["Message-ID"] = "<attach@acme.com>"
    msg["Subject"] = "Offer letter attached"
    msg.attach(MIMEText("Please find the attached offer letter.", "plain"))
    msg.attach(MIMEApplication(b"\x00\x01\x02\x03" * 100, Name="offer.pdf"))

    conn = MagicMock()
    conn.fetch.return_value = ("OK", [(b"1 (RFC822)", msg.as_bytes())])
    result = _parse_message(conn, b"1")
    assert result is not None
    assert result["message_id"] == "<attach@acme.com>"


def test_parse_message_multiple_text_parts_takes_first():
    """Email with multiple text/plain MIME parts uses only the first."""
    from scripts.imap_sync import _parse_message
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText

    msg = MIMEMultipart()
    msg["From"] = "r@acme.com"
    msg["Message-ID"] = "<multipart@acme.com>"
    msg["Subject"] = "Interview"
    msg.attach(MIMEText("First part — the real body.", "plain"))
    msg.attach(MIMEText("Second part — should be ignored.", "plain"))

    conn = MagicMock()
    conn.fetch.return_value = ("OK", [(b"1 (RFC822)", msg.as_bytes())])
    result = _parse_message(conn, b"1")
    assert result is not None
    assert "First part" in result["body"]
    assert "Second part" not in result["body"]


def test_get_all_message_ids_performance(tmp_path):
    """get_all_message_ids with 1000 rows completes quickly (smoke test for scale)."""
    import sqlite3
    import time
    from scripts.db import init_db, insert_job
    from scripts.db import get_all_message_ids

    db_path = tmp_path / "test.db"
    init_db(db_path)
    job_id = insert_job(db_path, {
        "title": "CSM", "company": "Acme", "url": "https://acme.com/perf",
        "source": "test", "location": "", "is_remote": 0,
        "salary": "", "description": "", "date_found": "2026-01-01",
    })

    conn = sqlite3.connect(db_path)
    conn.executemany(
        "INSERT INTO job_contacts (job_id, direction, subject, from_addr, body, received_at, message_id) "
        "VALUES (?, 'inbound', 'subj', 'f@x.com', 'body', '2026-01-01', ?)",
        [(job_id, f"<mid-{i}@x.com>") for i in range(1000)]
    )
    conn.commit()
    conn.close()

    start = time.monotonic()
    ids = get_all_message_ids(db_path)
    elapsed = time.monotonic() - start

    assert len(ids) == 1000
    assert elapsed < 1.0
