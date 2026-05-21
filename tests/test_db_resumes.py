"""Tests for resume library db helpers."""
import sqlite3

import pytest

from scripts.db_migrate import migrate_db


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "test.db"
    migrate_db(path)
    return path


def test_create_and_get_resume(db):
    from scripts.db import create_resume, get_resume
    r = create_resume(db, name="Q1 2026", text="Software engineer with 5 years experience.")
    assert r["id"] > 0
    assert r["name"] == "Q1 2026"
    assert r["word_count"] == 6
    assert r["source"] == "manual"
    assert r["is_default"] == 0

    fetched = get_resume(db, r["id"])
    assert fetched["name"] == "Q1 2026"


def test_list_resumes(db):
    from scripts.db import create_resume, list_resumes
    create_resume(db, name="A", text="alpha beta")
    create_resume(db, name="B", text="gamma delta")
    results = list_resumes(db)
    assert len(results) == 2


def test_update_resume(db):
    from scripts.db import create_resume, update_resume
    r = create_resume(db, name="Old name", text="old text here")
    updated = update_resume(db, r["id"], name="New name", text="new text content here updated")
    assert updated["name"] == "New name"
    assert updated["word_count"] == 5


def test_delete_resume(db):
    from scripts.db import create_resume, delete_resume, get_resume
    r = create_resume(db, name="Temp", text="temp text")
    delete_resume(db, r["id"])
    assert get_resume(db, r["id"]) is None


def test_set_default_resume(db):
    from scripts.db import create_resume, set_default_resume, list_resumes
    a = create_resume(db, name="A", text="text a")
    b = create_resume(db, name="B", text="text b")
    set_default_resume(db, a["id"])
    set_default_resume(db, b["id"])
    resumes = {r["id"]: r for r in list_resumes(db)}
    assert resumes[a["id"]]["is_default"] == 0
    assert resumes[b["id"]]["is_default"] == 1


def test_get_job_resume_default_fallback(db):
    from scripts.db import create_resume, set_default_resume, get_job_resume
    # Insert a minimal job row
    conn = sqlite3.connect(db)
    conn.execute("INSERT INTO jobs (id, title, company, source) VALUES (1, 'Eng', 'Co', 'test')")
    conn.commit()
    conn.close()
    r = create_resume(db, name="Default", text="default resume text")
    set_default_resume(db, r["id"])
    result = get_job_resume(db, 1)
    assert result["id"] == r["id"]


def test_get_job_resume_job_specific_override(db):
    from scripts.db import create_resume, set_default_resume, get_job_resume, set_job_resume
    conn = sqlite3.connect(db)
    conn.execute("INSERT INTO jobs (id, title, company, source) VALUES (1, 'Eng', 'Co', 'test')")
    conn.commit()
    conn.close()
    default_r = create_resume(db, name="Default", text="default resume text")
    set_default_resume(db, default_r["id"])
    specific_r = create_resume(db, name="Specific", text="job specific resume text")
    set_job_resume(db, job_id=1, resume_id=specific_r["id"])
    result = get_job_resume(db, 1)
    assert result["id"] == specific_r["id"]
