"""
db_migrate.py — Rails-style numbered SQL migration runner for Peregrine user DBs.

Migration files live in migrations/ (sibling to this script's parent directory),
named NNN_description.sql (e.g. 001_baseline.sql). They are applied in sorted
order and tracked in the schema_migrations table so each runs exactly once.

Usage:
    from scripts.db_migrate import migrate_db
    migrate_db(Path("/path/to/user.db"))
"""

import logging
import sqlite3
from pathlib import Path

log = logging.getLogger(__name__)

# Resolved at import time: peregrine repo root / migrations/
_MIGRATIONS_DIR = Path(__file__).parent.parent / "migrations"

_CREATE_MIGRATIONS_TABLE = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version TEXT PRIMARY KEY,
    applied_at TEXT NOT NULL DEFAULT (datetime('now'))
)
"""


def migrate_db(db_path: Path) -> list[str]:
    """Apply any pending migrations to db_path. Returns list of applied versions."""
    applied: list[str] = []

    con = sqlite3.connect(db_path)
    try:
        con.execute(_CREATE_MIGRATIONS_TABLE)
        con.commit()

        if not _MIGRATIONS_DIR.is_dir():
            log.warning("migrations/ directory not found at %s — skipping", _MIGRATIONS_DIR)
            return applied

        migration_files = sorted(_MIGRATIONS_DIR.glob("*.sql"))
        if not migration_files:
            return applied

        already_applied = {
            row[0] for row in con.execute("SELECT version FROM schema_migrations")
        }

        for path in migration_files:
            version = path.stem  # e.g. "001_baseline"
            if version in already_applied:
                continue

            sql = path.read_text(encoding="utf-8")
            log.info("Applying migration %s to %s", version, db_path.name)
            try:
                con.executescript(sql)
                con.execute(
                    "INSERT INTO schema_migrations (version) VALUES (?)", (version,)
                )
                con.commit()
                applied.append(version)
                log.info("Migration %s applied successfully", version)
            except Exception as exc:
                con.rollback()
                log.error("Migration %s failed: %s", version, exc)
                raise RuntimeError(f"Migration {version} failed: {exc}") from exc
    finally:
        con.close()

    return applied
