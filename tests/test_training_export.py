"""Tests for cover letter training export helpers."""
import json
import sqlite3
import pytest
from pathlib import Path


def _make_db(tmp_path: Path) -> Path:
    from scripts.db import init_db
    db = tmp_path / "test.db"
    init_db(db)
    # excluded_from_training column is added by _migrate_db via _MIGRATIONS — no manual ALTER needed
    return db


def _insert_job(db: Path, *, title="Engineer", company="Acme", status="applied",
                cover_letter="Dear Hiring Manager,\n\nI am excited.", description="Build stuff.",
                excluded=0) -> int:
    conn = sqlite3.connect(db)
    cur = conn.execute(
        "INSERT INTO jobs (title, company, url, source, location, is_remote, salary, "
        "description, date_found, status, cover_letter, excluded_from_training) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (title, company, f"https://example.com/{title}", "test", "Remote", 1, "",
         description, "2026-01-01", status, cover_letter, excluded),
    )
    conn.commit()
    job_id = cur.lastrowid
    conn.close()
    return job_id


def test_get_training_pairs_returns_applied_jobs(tmp_path):
    from scripts.db import get_training_pairs
    db = _make_db(tmp_path)
    _insert_job(db, title="Engineer", company="Acme", status="applied")
    pairs = get_training_pairs(db)
    assert len(pairs) == 1
    assert pairs[0]["source"] == "db"
    assert pairs[0]["instruction"] == "Write a cover letter for the Engineer position at Acme."
    assert "job_id" in pairs[0]


def test_get_training_pairs_strips_greeting(tmp_path):
    from scripts.db import get_training_pairs
    db = _make_db(tmp_path)
    _insert_job(db, cover_letter="Dear Hiring Manager,\n\nI am excited to apply.\n\nSincerely, Me")
    pairs = get_training_pairs(db)
    assert not pairs[0]["output"].startswith("Dear")
    assert "I am excited" in pairs[0]["output"]


def test_get_training_pairs_excludes_non_applied(tmp_path):
    from scripts.db import get_training_pairs
    db = _make_db(tmp_path)
    _insert_job(db, title="PendingJob", status="pending")
    _insert_job(db, title="ApprovedJob", status="approved")
    pairs = get_training_pairs(db)
    assert len(pairs) == 0


def test_get_training_pairs_excludes_opted_out(tmp_path):
    from scripts.db import get_training_pairs
    db = _make_db(tmp_path)
    _insert_job(db, excluded=1)
    pairs = get_training_pairs(db)
    assert len(pairs) == 0


def test_get_training_pairs_null_description_gives_empty_input(tmp_path):
    from scripts.db import get_training_pairs
    db = _make_db(tmp_path)
    conn = sqlite3.connect(db)
    conn.execute(
        "INSERT INTO jobs (title, company, url, source, location, is_remote, salary, "
        "date_found, status, cover_letter, excluded_from_training) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        ("Dev", "Corp", "https://x.com/1", "test", "Remote", 1, "",
         "2026-01-01", "applied", "Great letter body", 0),
    )
    conn.commit()
    conn.close()
    pairs = get_training_pairs(db)
    assert pairs[0]["input"] == ""


def test_get_db_pairs_includes_excluded_with_flag(tmp_path):
    from scripts.db import get_db_pairs
    db = _make_db(tmp_path)
    _insert_job(db, excluded=0)
    _insert_job(db, title="Other", excluded=1)
    pairs = get_db_pairs(db)
    assert len(pairs) == 2
    excluded = [p for p in pairs if p["excluded"]]
    included = [p for p in pairs if not p["excluded"]]
    assert len(excluded) == 1
    assert len(included) == 1


def test_set_training_exclusion_excludes(tmp_path):
    from scripts.db import get_training_pairs, set_training_exclusion
    db = _make_db(tmp_path)
    job_id = _insert_job(db)
    assert len(get_training_pairs(db)) == 1
    set_training_exclusion(db, job_id, excluded=True)
    assert len(get_training_pairs(db)) == 0


def test_set_training_exclusion_restores(tmp_path):
    from scripts.db import get_training_pairs, set_training_exclusion
    db = _make_db(tmp_path)
    job_id = _insert_job(db, excluded=1)
    assert len(get_training_pairs(db)) == 0
    set_training_exclusion(db, job_id, excluded=False)
    assert len(get_training_pairs(db)) == 1


def test_strip_greeting_returns_original_when_no_body(tmp_path):
    from scripts.db import _strip_greeting
    # A letter that is only a salutation with no body should return the original text
    result = _strip_greeting("Dear Hiring Manager,")
    assert result == "Dear Hiring Manager,"
