"""Endpoint tests for GET /api/salary-stats."""
import sqlite3

import yaml
from fastapi.testclient import TestClient


def _seed_db(db_path, rows):
    """Create a jobs table at db_path with the given (title, location, salary) rows."""
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE jobs (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            title    TEXT,
            company  TEXT,
            url      TEXT UNIQUE,
            source   TEXT,
            location TEXT,
            is_remote INTEGER DEFAULT 0,
            salary   TEXT,
            description TEXT,
            match_score REAL,
            keyword_gaps TEXT,
            date_found TEXT,
            status TEXT DEFAULT 'pending',
            notion_page_id TEXT,
            cover_letter TEXT,
            applied_at TEXT
        )
        """
    )
    for i, (title, location, salary) in enumerate(rows):
        conn.execute(
            "INSERT INTO jobs (title, location, salary, url) VALUES (?, ?, ?, ?)",
            (title, location, salary, f"https://example.test/job/{i}"),
        )
    conn.commit()
    conn.close()


def test_salary_stats_returns_200_with_expected_shape(tmp_path, monkeypatch):
    db_path = tmp_path / "staging.db"
    _seed_db(db_path, [
        ("Software Engineer", "Remote", "$100,000"),
        ("Software Engineer", "Remote", "$120,000"),
    ])
    monkeypatch.setenv("STAGING_DB", str(db_path))
    monkeypatch.setattr("dev_api.DB_PATH", str(db_path))

    from dev_api import app
    c = TestClient(app)
    resp = c.get("/api/salary-stats", params={"titles": "Software Engineer"})

    assert resp.status_code == 200
    data = resp.json()
    assert set(data.keys()) == {"count", "count_with_salary", "median", "p25", "p75"}
    assert data["count"] == 2
    assert data["count_with_salary"] == 2
    assert data["median"] == 110000


def test_salary_stats_honors_titles_and_location_params(tmp_path, monkeypatch):
    db_path = tmp_path / "staging.db"
    _seed_db(db_path, [
        ("Software Engineer", "Austin, TX", "$100,000"),
        ("Software Engineer", "New York, NY", "$150,000"),
        ("Product Manager", "Austin, TX", "$130,000"),
    ])
    monkeypatch.setenv("STAGING_DB", str(db_path))
    monkeypatch.setattr("dev_api.DB_PATH", str(db_path))

    from dev_api import app
    c = TestClient(app)
    resp = c.get("/api/salary-stats", params={
        "titles": "Software Engineer",
        "location": "Austin",
    })

    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 1
    assert data["count_with_salary"] == 1
    assert data["median"] == 100000


def test_salary_stats_omitting_titles_falls_back_to_search_profile(tmp_path, monkeypatch):
    db_path = tmp_path / "staging.db"
    _seed_db(db_path, [
        ("Data Scientist", "Remote", "$140,000"),
        ("Barista", "Remote", "$40,000"),
    ])
    monkeypatch.setenv("STAGING_DB", str(db_path))
    monkeypatch.setattr("dev_api.DB_PATH", str(db_path))

    fake_search_path = tmp_path / "config" / "search_profiles.yaml"
    fake_search_path.parent.mkdir(parents=True, exist_ok=True)
    with open(fake_search_path, "w") as f:
        yaml.dump({"default": {"job_titles": ["Data Scientist"], "locations": []}}, f)
    monkeypatch.setattr("dev_api._search_prefs_path", lambda: fake_search_path)

    from dev_api import app
    c = TestClient(app)
    resp = c.get("/api/salary-stats")

    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 1
    assert data["count_with_salary"] == 1
    assert data["median"] == 140000
