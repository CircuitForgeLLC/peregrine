"""Tests for scripts/db_migrate.py — numbered SQL migration runner."""

import sqlite3
import textwrap
from pathlib import Path

import pytest

from scripts.db_migrate import migrate_db


# ── helpers ───────────────────────────────────────────────────────────────────

def _applied(db_path: Path) -> list[str]:
    con = sqlite3.connect(db_path)
    try:
        rows = con.execute("SELECT version FROM schema_migrations ORDER BY version").fetchall()
        return [r[0] for r in rows]
    finally:
        con.close()


def _tables(db_path: Path) -> set[str]:
    con = sqlite3.connect(db_path)
    try:
        rows = con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
        return {r[0] for r in rows}
    finally:
        con.close()


# ── tests ──────────────────────────────────────────────────────────────────────

def test_creates_schema_migrations_table(tmp_path):
    """Running against an empty DB creates the tracking table."""
    db = tmp_path / "test.db"
    (tmp_path / "migrations").mkdir()  # empty migrations dir
    # Patch the module-level _MIGRATIONS_DIR
    import scripts.db_migrate as m
    orig = m._MIGRATIONS_DIR
    m._MIGRATIONS_DIR = tmp_path / "migrations"
    try:
        migrate_db(db)
        assert "schema_migrations" in _tables(db)
    finally:
        m._MIGRATIONS_DIR = orig


def test_applies_migration_file(tmp_path):
    """A .sql file in migrations/ is applied and recorded."""
    db = tmp_path / "test.db"
    mdir = tmp_path / "migrations"
    mdir.mkdir()
    (mdir / "001_test.sql").write_text(
        "CREATE TABLE IF NOT EXISTS widgets (id INTEGER PRIMARY KEY, name TEXT);"
    )

    import scripts.db_migrate as m
    orig = m._MIGRATIONS_DIR
    m._MIGRATIONS_DIR = mdir
    try:
        applied = migrate_db(db)
        assert applied == ["001_test"]
        assert "widgets" in _tables(db)
        assert _applied(db) == ["001_test"]
    finally:
        m._MIGRATIONS_DIR = orig


def test_idempotent_second_run(tmp_path):
    """Running migrate_db twice does not re-apply migrations."""
    db = tmp_path / "test.db"
    mdir = tmp_path / "migrations"
    mdir.mkdir()
    (mdir / "001_test.sql").write_text(
        "CREATE TABLE IF NOT EXISTS widgets (id INTEGER PRIMARY KEY, name TEXT);"
    )

    import scripts.db_migrate as m
    orig = m._MIGRATIONS_DIR
    m._MIGRATIONS_DIR = mdir
    try:
        migrate_db(db)
        applied = migrate_db(db)  # second run
        assert applied == []
        assert _applied(db) == ["001_test"]
    finally:
        m._MIGRATIONS_DIR = orig


def test_applies_only_new_migrations(tmp_path):
    """Migrations already in schema_migrations are skipped; only new ones run."""
    db = tmp_path / "test.db"
    mdir = tmp_path / "migrations"
    mdir.mkdir()
    (mdir / "001_first.sql").write_text(
        "CREATE TABLE IF NOT EXISTS first_table (id INTEGER PRIMARY KEY);"
    )

    import scripts.db_migrate as m
    orig = m._MIGRATIONS_DIR
    m._MIGRATIONS_DIR = mdir
    try:
        migrate_db(db)

        # Add a second migration
        (mdir / "002_second.sql").write_text(
            "CREATE TABLE IF NOT EXISTS second_table (id INTEGER PRIMARY KEY);"
        )
        applied = migrate_db(db)
        assert applied == ["002_second"]
        assert set(_applied(db)) == {"001_first", "002_second"}
        assert "second_table" in _tables(db)
    finally:
        m._MIGRATIONS_DIR = orig


def test_migration_failure_raises(tmp_path):
    """A bad migration raises RuntimeError and does not record the version."""
    db = tmp_path / "test.db"
    mdir = tmp_path / "migrations"
    mdir.mkdir()
    (mdir / "001_bad.sql").write_text("THIS IS NOT VALID SQL !!!")

    import scripts.db_migrate as m
    orig = m._MIGRATIONS_DIR
    m._MIGRATIONS_DIR = mdir
    try:
        with pytest.raises(RuntimeError, match="001_bad"):
            migrate_db(db)
        assert _applied(db) == []
    finally:
        m._MIGRATIONS_DIR = orig


def test_baseline_migration_runs(tmp_path):
    """The real 001_baseline.sql applies cleanly to a fresh database."""
    db = tmp_path / "test.db"
    applied = migrate_db(db)
    assert "001_baseline" in applied
    expected_tables = {
        "jobs", "job_contacts", "company_research",
        "background_tasks", "survey_responses", "digest_queue",
        "schema_migrations",
    }
    assert expected_tables <= _tables(db)
