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
                # Execute statements individually so that ALTER TABLE ADD COLUMN
                # errors caused by already-existing columns (pre-migration DBs
                # created from a newer schema) are treated as no-ops rather than
                # fatal failures.
                statements = [s.strip() for s in sql.split(";") if s.strip()]
                for stmt in statements:
                    # Strip leading SQL comment lines (-- ...) before processing.
                    # Checking startswith("--") on the raw chunk would skip entire
                    # multi-line statements whose first line is a comment.
                    stripped_lines = [
                        ln for ln in stmt.splitlines()
                        if not ln.strip().startswith("--")
                    ]
                    stmt = "\n".join(stripped_lines).strip()
                    if not stmt:
                        continue
                    # Pre-check: if this is ADD COLUMN and the column already exists, skip.
                    # This guards against schema_migrations being ahead of the actual schema
                    # (e.g. DB reset after migrations were recorded).
                    stmt_upper = stmt.upper()
                    if "ALTER TABLE" in stmt_upper and "ADD COLUMN" in stmt_upper:
                        # Extract table name and column name from the statement
                        import re as _re
                        m = _re.match(
                            r"ALTER\s+TABLE\s+(\w+)\s+ADD\s+COLUMN\s+(\w+)",
                            stmt, _re.IGNORECASE
                        )
                        if m:
                            tbl, col = m.group(1), m.group(2)
                            existing = {
                                row[1]
                                for row in con.execute(f"PRAGMA table_info({tbl})")
                            }
                            if col in existing:
                                log.info(
                                    "Migration %s: column %s.%s already exists, skipping",
                                    version, tbl, col,
                                )
                                continue
                    try:
                        con.execute(stmt)
                    except sqlite3.OperationalError as stmt_exc:
                        msg = str(stmt_exc).lower()
                        if "duplicate column name" in msg or "already exists" in msg:
                            log.info(
                                "Migration %s: statement already applied, skipping: %s",
                                version, stmt_exc,
                            )
                        else:
                            raise
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
