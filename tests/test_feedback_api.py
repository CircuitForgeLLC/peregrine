"""Tests for the feedback API backend."""
import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path


# ── mask_pii ──────────────────────────────────────────────────────────────────

def test_mask_pii_email():
    from scripts.feedback_api import mask_pii
    assert mask_pii("contact foo@bar.com please") == "contact [email redacted] please"


def test_mask_pii_phone_dashes():
    from scripts.feedback_api import mask_pii
    assert mask_pii("call 555-123-4567 now") == "call [phone redacted] now"


def test_mask_pii_phone_parens():
    from scripts.feedback_api import mask_pii
    assert mask_pii("(555) 867-5309") == "[phone redacted]"


def test_mask_pii_clean_text():
    from scripts.feedback_api import mask_pii
    assert mask_pii("no sensitive data here") == "no sensitive data here"


def test_mask_pii_multiple_emails():
    from scripts.feedback_api import mask_pii
    result = mask_pii("a@b.com and c@d.com")
    assert result == "[email redacted] and [email redacted]"


# ── collect_context ───────────────────────────────────────────────────────────

def test_collect_context_required_keys():
    from scripts.feedback_api import collect_context
    ctx = collect_context("Home")
    for key in ("page", "version", "tier", "llm_backend", "os", "timestamp"):
        assert key in ctx, f"missing key: {key}"


def test_collect_context_page_value():
    from scripts.feedback_api import collect_context
    ctx = collect_context("MyPage")
    assert ctx["page"] == "MyPage"


def test_collect_context_timestamp_is_utc():
    from scripts.feedback_api import collect_context
    ctx = collect_context("X")
    assert ctx["timestamp"].endswith("Z")


# ── collect_logs ──────────────────────────────────────────────────────────────

def test_collect_logs_returns_string(tmp_path):
    from scripts.feedback_api import collect_logs
    log = tmp_path / ".streamlit.log"
    log.write_text("line1\nline2\nline3\n")
    result = collect_logs(log_path=log, n=10)
    assert isinstance(result, str)
    assert "line3" in result


def test_collect_logs_tails_n_lines(tmp_path):
    from scripts.feedback_api import collect_logs
    log = tmp_path / ".streamlit.log"
    log.write_text("\n".join(f"line{i}" for i in range(200)))
    result = collect_logs(log_path=log, n=10)
    assert "line199" in result
    assert "line0" not in result


def test_collect_logs_masks_pii(tmp_path):
    from scripts.feedback_api import collect_logs
    log = tmp_path / "test.log"
    log.write_text("user foo@bar.com connected\n")
    result = collect_logs(log_path=log)
    assert "foo@bar.com" not in result
    assert "[email redacted]" in result


def test_collect_logs_missing_file(tmp_path):
    from scripts.feedback_api import collect_logs
    result = collect_logs(log_path=tmp_path / "nonexistent.log")
    assert "no log file" in result.lower()


# ── collect_listings ──────────────────────────────────────────────────────────

def test_collect_listings_safe_fields_only(tmp_path):
    """Only title, company, url — no cover letters, notes, or emails."""
    from scripts.db import init_db, insert_job
    from scripts.feedback_api import collect_listings
    db = tmp_path / "test.db"
    init_db(db)
    insert_job(db, {
        "title": "CSM", "company": "Acme", "url": "https://example.com/1",
        "source": "linkedin", "location": "Remote", "is_remote": True,
        "salary": "", "description": "great role", "date_found": "2026-03-01",
    })
    results = collect_listings(db_path=db, n=5)
    assert len(results) == 1
    assert set(results[0].keys()) == {"title", "company", "url"}
    assert results[0]["title"] == "CSM"


def test_collect_listings_respects_n(tmp_path):
    from scripts.db import init_db, insert_job
    from scripts.feedback_api import collect_listings
    db = tmp_path / "test.db"
    init_db(db)
    for i in range(10):
        insert_job(db, {
            "title": f"Job {i}", "company": "Acme", "url": f"https://example.com/{i}",
            "source": "linkedin", "location": "Remote", "is_remote": False,
            "salary": "", "description": "", "date_found": "2026-03-01",
        })
    assert len(collect_listings(db_path=db, n=3)) == 3
