"""POST /api/settings/resume/upload failure handling.

A cloud beta tester's upload returned a bare 500 and left nothing in the logs, so the
cause could not be found. The handler also treated every file that was not a PDF or ODT
as a DOCX, so any other file type crashed inside the DOCX reader. (Text formats are now
supported, see test_resume_text_formats.py. This file covers what happens when they fail.)

Contract: an unsupported or unreadable file gets a friendly {"ok": false, "error": ...}
(same shape as other parse failures), and anything unexpected is a 500 that is logged.
Logs carry the error type, file extension and size only, never the filename or contents,
because resumes and the names on them are personal data.
"""
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from scripts.db_migrate import migrate_db

PARSED = {
    "name": "Alex", "surname": "Rivera", "email": "", "phone": "", "career_summary": "",
    "experience": [], "education": [], "skills": [], "achievements": [],
}


@pytest.fixture
def client(tmp_path, monkeypatch):
    db = tmp_path / "test.db"
    (tmp_path / "config").mkdir()
    monkeypatch.setenv("STAGING_DB", str(db))
    migrate_db(db)
    import dev_api

    monkeypatch.setattr(
        dev_api, "_request_db",
        type("CV", (), {"get": lambda self: str(db), "set": lambda *a: None})(),
    )
    return TestClient(dev_api.app)


def _post(client, filename: str, content: bytes = b"bytes"):
    return client.post(
        "/api/settings/resume/upload",
        files={"file": (filename, content, "application/octet-stream")},
    )


@pytest.mark.parametrize("filename", ["resume", "resume.xyz", "resume.exe", "resume.jpg"])
def test_unsupported_file_types_get_a_friendly_error(client, filename):
    resp = _post(client, filename)

    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is False
    for supported in ("PDF", "DOCX", "ODT"):
        assert supported in body["error"]


def test_extension_check_is_case_insensitive(client):
    with patch("scripts.resume_parser.extract_text_from_pdf", return_value="Alex Rivera"), \
         patch("scripts.resume_parser.structure_resume", return_value=(dict(PARSED), "")):
        resp = _post(client, "RESUME.PDF")

    assert resp.json()["ok"] is True


@pytest.mark.parametrize("filename", ["resume.pdf", "resume.docx", "resume.odt"])
def test_unreadable_file_gets_a_friendly_error_not_a_500(client, filename):
    resp = _post(client, filename, b"this is not a real document")

    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is False
    assert "couldn't read" in body["error"].lower()


def test_unreadable_file_is_logged_without_the_filename(client):
    import dev_api

    fake_log = MagicMock()
    with patch.object(dev_api, "_log", fake_log):
        _post(client, "Jane-Q-Public-Resume.pdf", b"this is not a real document")

    assert fake_log.warning.called, "an unreadable upload should leave a log line"
    logged = str(fake_log.warning.call_args_list)
    assert "upload_resume" in logged
    assert ".pdf" in logged
    assert "Jane" not in logged
    assert "Public" not in logged


def test_unexpected_failure_is_still_a_500_and_is_logged(client):
    import dev_api

    fake_log = MagicMock()
    with patch.object(dev_api, "_log", fake_log), \
         patch("scripts.resume_parser.extract_text_from_docx", return_value="Alex Rivera"), \
         patch("scripts.resume_parser.structure_resume", return_value=(dict(PARSED), "")), \
         patch("scripts.db.create_resume", side_effect=RuntimeError("database exploded")):
        resp = _post(client, "resume.docx")

    assert resp.status_code == 500
    assert fake_log.error.called, "unexpected failures must leave a log line"
    logged = str(fake_log.error.call_args_list)
    assert "upload_resume" in logged
    assert "RuntimeError" in logged


def test_logs_and_responses_never_carry_exception_text(client):
    """Exception messages from parsers and the database can quote the document, so only the
    exception type and where it came from are logged, and the client gets a generic message."""
    import dev_api

    fake_log = MagicMock()
    with patch.object(dev_api, "_log", fake_log), \
         patch("scripts.resume_parser.extract_text_from_docx", return_value="Alex Rivera"), \
         patch("scripts.resume_parser.structure_resume", return_value=(dict(PARSED), "")), \
         patch("scripts.db.create_resume", side_effect=RuntimeError("SECRET-RESUME-LINE 555-0100")):
        resp = _post(client, "resume.docx")

    assert "SECRET-RESUME-LINE" not in resp.text
    assert "SECRET-RESUME-LINE" not in str(fake_log.mock_calls)
    for call in fake_log.mock_calls:
        assert not call.kwargs.get("exc_info"), "tracebacks carry the exception message"


def test_unreadable_file_log_has_no_exception_text(client):
    import dev_api

    fake_log = MagicMock()
    with patch.object(dev_api, "_log", fake_log), \
         patch("scripts.resume_parser.extract_text_from_pdf", side_effect=ValueError("page text: SECRET-RESUME-LINE")):
        resp = _post(client, "resume.pdf", b"x")

    assert resp.json()["ok"] is False
    assert "SECRET-RESUME-LINE" not in str(fake_log.mock_calls)
    assert "ValueError" in str(fake_log.warning.call_args_list)


def test_oversized_uploads_get_a_friendly_error_before_any_parsing(client, monkeypatch):
    import dev_api

    monkeypatch.setattr(dev_api, "_RESUME_UPLOAD_MAX_BYTES", 100)
    with patch("scripts.resume_parser.extract_text") as extract:
        resp = _post(client, "resume.pdf", b"x" * 500)

    body = resp.json()
    assert body["ok"] is False
    assert "too large" in body["error"].lower()
    extract.assert_not_called()


def test_library_import_rejects_oversized_files(client, monkeypatch):
    import dev_api

    monkeypatch.setattr(dev_api, "_RESUME_UPLOAD_MAX_BYTES", 100)

    resp = client.post(
        "/api/resumes/import",
        files={"file": ("big.txt", b"x" * 500, "text/plain")},
        data={"name": "big"},
    )

    assert resp.status_code == 413
