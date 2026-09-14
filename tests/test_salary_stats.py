"""Unit tests for scripts/salary_stats.get_salary_stats()."""
import sqlite3

import pytest

from scripts.salary_stats import get_salary_stats


@pytest.fixture
def db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE jobs (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            title    TEXT,
            location TEXT,
            salary   TEXT
        )
        """
    )
    yield conn
    conn.close()


def _insert(db, title, location, salary):
    db.execute(
        "INSERT INTO jobs (title, location, salary) VALUES (?, ?, ?)",
        (title, location, salary),
    )


def test_matches_by_title_substring_case_insensitive(db):
    _insert(db, "Senior Software Engineer", "Remote", "$100,000")
    _insert(db, "SOFTWARE ENGINEER II", "Remote", "$110,000")
    _insert(db, "Product Manager", "Remote", "$120,000")
    db.commit()

    result = get_salary_stats(db, ["software engineer"])

    assert result["count"] == 2
    assert result["count_with_salary"] == 2


def test_no_titles_matches_all_jobs_with_salary(db):
    _insert(db, "Engineer", "Remote", "$100,000")
    _insert(db, "Designer", "Remote", "$90,000")
    db.commit()

    result = get_salary_stats(db, [])

    assert result["count"] == 2
    assert result["count_with_salary"] == 2


def test_filters_by_location_when_given(db):
    _insert(db, "Engineer", "Austin, TX", "$100,000")
    _insert(db, "Engineer", "New York, NY", "$120,000")
    db.commit()

    result = get_salary_stats(db, ["Engineer"], location="Austin")

    assert result["count"] == 1
    assert result["count_with_salary"] == 1
    assert result["median"] == 100000


def test_location_ignored_when_omitted(db):
    _insert(db, "Engineer", "Austin, TX", "$100,000")
    _insert(db, "Engineer", "New York, NY", "$120,000")
    db.commit()

    result = get_salary_stats(db, ["Engineer"])

    assert result["count"] == 2


def test_median_p25_p75_known_fixture(db):
    # Round-number midpoints: 10000, 20000, 30000, 40000, 50000
    for val in (10, 20, 30, 40, 50):
        _insert(db, "Engineer", "Remote", f"${val},000")
    db.commit()

    result = get_salary_stats(db, ["Engineer"])

    assert result["count_with_salary"] == 5
    assert result["median"] == 30000
    # Linear-interpolation percentile over [10k,20k,30k,40k,50k], n=5:
    # p25 rank = 0.25*4 = 1.0 -> index 1 -> 20000
    # p75 rank = 0.75*4 = 3.0 -> index 3 -> 40000
    assert result["p25"] == 20000
    assert result["p75"] == 40000


def test_null_or_empty_salary_excluded_from_salary_stats_but_counted(db):
    _insert(db, "Engineer", "Remote", "$100,000")
    _insert(db, "Engineer", "Remote", None)
    _insert(db, "Engineer", "Remote", "")
    db.commit()

    result = get_salary_stats(db, ["Engineer"])

    assert result["count"] == 3
    assert result["count_with_salary"] == 1
    assert result["median"] == 100000


def test_unparseable_salary_excluded_but_counted(db):
    _insert(db, "Engineer", "Remote", "$100,000")
    _insert(db, "Engineer", "Remote", "Competitive salary")
    db.commit()

    result = get_salary_stats(db, ["Engineer"])

    assert result["count"] == 2
    assert result["count_with_salary"] == 1
    assert result["median"] == 100000


def test_returns_none_stats_when_no_salary_data(db):
    _insert(db, "Engineer", "Remote", None)
    _insert(db, "Engineer", "Remote", "not a salary")
    db.commit()

    result = get_salary_stats(db, ["Engineer"])

    assert result["count"] == 2
    assert result["count_with_salary"] == 0
    assert result["median"] is None
    assert result["p25"] is None
    assert result["p75"] is None


def test_single_number_salary_string_midpoint(db):
    _insert(db, "Engineer", "Remote", "$80,000")
    db.commit()

    result = get_salary_stats(db, ["Engineer"])

    assert result["count_with_salary"] == 1
    assert result["median"] == 80000
    assert result["p25"] == 80000
    assert result["p75"] == 80000
