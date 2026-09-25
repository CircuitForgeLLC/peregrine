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
import re
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

_ADD_COLUMN_RE = re.compile(
    r"ALTER\s+TABLE\s+(\w+)\s+ADD\s+COLUMN\s+(\w+)", re.IGNORECASE
)


def _statements(sql: str) -> list[str]:
    """Split a migration file's SQL into individual statements, stripping
    leading comment lines from each (a chunk whose first line is a comment
    would otherwise be skipped whole by a naive startswith("--") check)."""
    statements = []
    for raw in sql.split(";"):
        raw = raw.strip()
        if not raw:
            continue
        stripped_lines = [ln for ln in raw.splitlines() if not ln.strip().startswith("--")]
        stmt = "\n".join(stripped_lines).strip()
        if stmt:
            statements.append(stmt)
    return statements


def _missing_add_columns(con: sqlite3.Connection, statements: list[str]) -> list[tuple[str, str]]:
    """Return (table, column) pairs from ADD COLUMN statements in `statements`
    whose column does not actually exist in `con`'s schema."""
    missing = []
    for stmt in statements:
        m = _ADD_COLUMN_RE.match(stmt)
        if not m:
            continue
        tbl, col = m.group(1), m.group(2)
        try:
            existing = {row[1] for row in con.execute(f"PRAGMA table_info({tbl})")}
        except sqlite3.OperationalError:
            continue  # table doesn't exist yet -- not this function's concern
        if col not in existing:
            missing.append((tbl, col))
    return missing


def migrate_db(db_path: Path) -> list[str]:
    """Apply any pending migrations to db_path. Returns list of applied versions.

    A migration already recorded in schema_migrations is normally skipped.
    But if it added columns via ADD COLUMN and one of those columns is
    actually missing from the live schema, it's re-applied anyway (found
    2026-09-24: a tenant DB's schema_migrations can claim a migration ran
    when its ALTER TABLE never actually took effect -- e.g. from manual/
    ad-hoc DB state during dev testing -- silently leaving that tenant's
    schema permanently out of sync with no way to notice short of a runtime
    error on first use. Re-applying is safe: ADD COLUMN is idempotent here,
    guarded by the same column-exists check used during normal execution).
    """
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
            sql = path.read_text(encoding="utf-8")
            statements = _statements(sql)

            was_recorded = version in already_applied
            if was_recorded:
                missing = _missing_add_columns(con, statements)
                if not missing:
                    continue
                log.warning(
                    "Migration %s recorded as applied to %s but %s missing "
                    "from the live schema — re-applying",
                    version, db_path.name,
                    ", ".join(f"{t}.{c}" for t, c in missing),
                )

            try:
                # Execute statements individually so that ALTER TABLE ADD COLUMN
                # errors caused by already-existing columns (pre-migration DBs
                # created from a newer schema) are treated as no-ops rather than
                # fatal failures.
                for stmt in statements:
                    # Pre-check: if this is ADD COLUMN and the column already exists, skip.
                    # This guards against schema_migrations being ahead of the actual schema
                    # (e.g. DB reset after migrations were recorded).
                    m = _ADD_COLUMN_RE.match(stmt)
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
                if not was_recorded:
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
