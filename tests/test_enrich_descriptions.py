# tests/test_enrich_descriptions.py
"""Tests for scripts/enrich_descriptions.py — enrich_craigslist_fields()."""
from unittest.mock import patch, MagicMock
import sqlite3


def test_enrich_craigslist_fields_skips_non_craigslist(tmp_path):
    """Non-craigslist source → returns {} without calling LLM."""
    from scripts.db import init_db, insert_job
    from scripts.enrich_descriptions import enrich_craigslist_fields
    db = tmp_path / "test.db"
    init_db(db)
    job_id = insert_job(db, {
        "title": "CSM", "company": "", "url": "https://example.com/1",
        "source": "linkedin", "location": "", "description": "Some company here.",
        "date_found": "2026-02-24",
    })
    with patch("scripts.llm_router.LLMRouter") as mock_llm:
        result = enrich_craigslist_fields(db, job_id)
    assert result == {}
    mock_llm.assert_not_called()


def test_enrich_craigslist_fields_skips_populated_company(tmp_path):
    """Company already set → returns {} without calling LLM."""
    from scripts.db import init_db, insert_job
    from scripts.enrich_descriptions import enrich_craigslist_fields
    db = tmp_path / "test.db"
    init_db(db)
    job_id = insert_job(db, {
        "title": "CSM", "company": "Acme Corp", "url": "https://sfbay.craigslist.org/jjj/d/1.html",
        "source": "craigslist", "location": "", "description": "Join Acme Corp today.",
        "date_found": "2026-02-24",
    })
    with patch("scripts.llm_router.LLMRouter") as mock_llm:
        result = enrich_craigslist_fields(db, job_id)
    assert result == {}
    mock_llm.assert_not_called()


def test_enrich_craigslist_fields_skips_empty_description(tmp_path):
    """Empty description → returns {} without calling LLM."""
    from scripts.db import init_db, insert_job
    from scripts.enrich_descriptions import enrich_craigslist_fields
    db = tmp_path / "test.db"
    init_db(db)
    job_id = insert_job(db, {
        "title": "CSM", "company": "", "url": "https://sfbay.craigslist.org/jjj/d/2.html",
        "source": "craigslist", "location": "", "description": "",
        "date_found": "2026-02-24",
    })
    with patch("scripts.llm_router.LLMRouter") as mock_llm:
        result = enrich_craigslist_fields(db, job_id)
    assert result == {}
    mock_llm.assert_not_called()


def test_enrich_craigslist_fields_extracts_and_updates(tmp_path):
    """Valid LLM response → updates company/salary in DB, returns extracted dict."""
    from scripts.db import init_db, insert_job
    from scripts.enrich_descriptions import enrich_craigslist_fields
    db = tmp_path / "test.db"
    init_db(db)
    job_id = insert_job(db, {
        "title": "CSM", "company": "", "url": "https://sfbay.craigslist.org/jjj/d/3.html",
        "source": "craigslist", "location": "", "description": "Join Acme Corp. Pay: $120k/yr.",
        "date_found": "2026-02-24",
    })
    mock_router = MagicMock()
    mock_router.complete.return_value = '{"company": "Acme Corp", "salary": "$120k/yr"}'
    with patch("scripts.llm_router.LLMRouter", return_value=mock_router):
        result = enrich_craigslist_fields(db, job_id)
    assert result == {"company": "Acme Corp", "salary": "$120k/yr"}
    conn = sqlite3.connect(db)
    row = conn.execute("SELECT company, salary FROM jobs WHERE id=?", (job_id,)).fetchone()
    conn.close()
    assert row[0] == "Acme Corp"
    assert row[1] == "$120k/yr"


def test_enrich_craigslist_fields_handles_bad_llm_json(tmp_path):
    """Unparseable LLM response → returns {} without raising."""
    from scripts.db import init_db, insert_job
    from scripts.enrich_descriptions import enrich_craigslist_fields
    db = tmp_path / "test.db"
    init_db(db)
    job_id = insert_job(db, {
        "title": "CSM", "company": "", "url": "https://sfbay.craigslist.org/jjj/d/4.html",
        "source": "craigslist", "location": "", "description": "Great opportunity.",
        "date_found": "2026-02-24",
    })
    mock_router = MagicMock()
    mock_router.complete.return_value = "Sorry, I cannot extract that."
    with patch("scripts.llm_router.LLMRouter", return_value=mock_router):
        result = enrich_craigslist_fields(db, job_id)
    assert result == {}
