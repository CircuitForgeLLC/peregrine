"""Tests for scripts/db_migrate.py — numbered SQL migration runner."""

import sqlite3
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


def test_reapplies_add_column_when_recorded_but_missing(tmp_path):
    """peregrine (found 2026-09-24): a live tenant DB had schema_migrations
    recording 004_resume_final_struct as applied, but the actual ALTER TABLE
    had never taken effect -- jobs.resume_final_struct was missing, breaking
    resume-optimizer save/export for that tenant with no way to notice short
    of the runtime error. migrate_db() must verify the column actually
    exists, not just trust the tracking table, and self-heal if it doesn't."""
    db = tmp_path / "test.db"
    mdir = tmp_path / "migrations"
    mdir.mkdir()
    (mdir / "001_widgets.sql").write_text(
        "CREATE TABLE IF NOT EXISTS widgets (id INTEGER PRIMARY KEY);"
    )
    (mdir / "002_add_name.sql").write_text(
        "ALTER TABLE widgets ADD COLUMN name TEXT;"
    )

    import scripts.db_migrate as m
    orig = m._MIGRATIONS_DIR
    m._MIGRATIONS_DIR = mdir
    try:
        migrate_db(db)  # normal first run: both migrations apply correctly

        # Simulate the exact broken state found in production: schema_migrations
        # says 002_add_name ran, but the column doesn't actually exist (e.g.
        # from ad-hoc/manual DB state that never went through the real runner).
        con = sqlite3.connect(db)
        con.execute("DROP TABLE widgets")
        con.execute("CREATE TABLE widgets (id INTEGER PRIMARY KEY)")  # no `name` column
        con.commit()
        con.close()

        cols_before = {r[1] for r in sqlite3.connect(db).execute("PRAGMA table_info(widgets)")}
        assert "name" not in cols_before  # sanity: broken state reproduced

        applied = migrate_db(db)
        assert applied == ["002_add_name"]  # re-applied despite being recorded

        cols_after = {r[1] for r in sqlite3.connect(db).execute("PRAGMA table_info(widgets)")}
        assert "name" in cols_after

        # schema_migrations still has exactly one row for this version --
        # re-applying must not create a duplicate or violate the PRIMARY KEY.
        assert _applied(db).count("002_add_name") == 1
    finally:
        m._MIGRATIONS_DIR = orig


def test_does_not_reapply_when_recorded_and_column_present(tmp_path):
    """The normal, healthy case: recorded + column present -> skipped, same
    as before this fix. Guards against the self-healing check becoming a
    performance regression that re-runs every migration on every call."""
    db = tmp_path / "test.db"
    mdir = tmp_path / "migrations"
    mdir.mkdir()
    (mdir / "001_widgets.sql").write_text(
        "CREATE TABLE IF NOT EXISTS widgets (id INTEGER PRIMARY KEY, name TEXT);"
    )

    import scripts.db_migrate as m
    orig = m._MIGRATIONS_DIR
    m._MIGRATIONS_DIR = mdir
    try:
        migrate_db(db)
        applied = migrate_db(db)
        assert applied == []
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
