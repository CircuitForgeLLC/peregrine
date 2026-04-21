"""
DB helpers for the messaging feature.

Messages table: manual log entries and LLM drafts (one row per message).
Message templates table: built-in seeds and user-created templates.

Conventions (match scripts/db.py):
- All functions take db_path: Path as first argument.
- sqlite3.connect(db_path), row_factory = sqlite3.Row
- Return plain dicts (dict(row))
- Always close connection in finally
"""
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _connect(db_path: Path) -> sqlite3.Connection:
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    return con


def _now_utc() -> str:
    """Return current UTC time as ISO 8601 string."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


# ---------------------------------------------------------------------------
# Messages
# ---------------------------------------------------------------------------

def create_message(
    db_path: Path,
    *,
    job_id: Optional[int],
    job_contact_id: Optional[int],
    type: str,
    direction: str,
    subject: Optional[str],
    body: Optional[str],
    from_addr: Optional[str],
    to_addr: Optional[str],
    template_id: Optional[int],
    logged_at: Optional[str] = None,
) -> dict:
    """Insert a new message row and return it as a dict."""
    con = _connect(db_path)
    try:
        cur = con.execute(
            """
            INSERT INTO messages
                (job_id, job_contact_id, type, direction, subject, body,
                 from_addr, to_addr, logged_at, template_id)
            VALUES
                (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (job_id, job_contact_id, type, direction, subject, body,
             from_addr, to_addr, logged_at or _now_utc(), template_id),
        )
        con.commit()
        row = con.execute(
            "SELECT * FROM messages WHERE id = ?", (cur.lastrowid,)
        ).fetchone()
        return dict(row)
    finally:
        con.close()


def list_messages(
    db_path: Path,
    *,
    job_id: Optional[int] = None,
    type: Optional[str] = None,
    direction: Optional[str] = None,
    limit: int = 100,
) -> list[dict]:
    """Return messages, optionally filtered. Ordered by logged_at DESC."""
    conditions: list[str] = []
    params: list = []

    if job_id is not None:
        conditions.append("job_id = ?")
        params.append(job_id)
    if type is not None:
        conditions.append("type = ?")
        params.append(type)
    if direction is not None:
        conditions.append("direction = ?")
        params.append(direction)

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    params.append(limit)

    con = _connect(db_path)
    try:
        rows = con.execute(
            f"SELECT * FROM messages {where} ORDER BY logged_at DESC LIMIT ?",
            params,
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        con.close()


def delete_message(db_path: Path, message_id: int) -> None:
    """Delete a message by id. Raises KeyError if not found."""
    con = _connect(db_path)
    try:
        row = con.execute(
            "SELECT id FROM messages WHERE id = ?", (message_id,)
        ).fetchone()
        if row is None:
            raise KeyError(f"Message {message_id} not found")
        con.execute("DELETE FROM messages WHERE id = ?", (message_id,))
        con.commit()
    finally:
        con.close()


def approve_message(db_path: Path, message_id: int) -> dict:
    """Set approved_at to now for the given message. Raises KeyError if not found."""
    con = _connect(db_path)
    try:
        row = con.execute(
            "SELECT id FROM messages WHERE id = ?", (message_id,)
        ).fetchone()
        if row is None:
            raise KeyError(f"Message {message_id} not found")
        con.execute(
            "UPDATE messages SET approved_at = ? WHERE id = ?",
            (_now_utc(), message_id),
        )
        con.commit()
        updated = con.execute(
            "SELECT * FROM messages WHERE id = ?", (message_id,)
        ).fetchone()
        return dict(updated)
    finally:
        con.close()


# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------

def list_templates(db_path: Path) -> list[dict]:
    """Return all templates ordered by is_builtin DESC, then title ASC."""
    con = _connect(db_path)
    try:
        rows = con.execute(
            "SELECT * FROM message_templates ORDER BY is_builtin DESC, title ASC"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        con.close()


def create_template(
    db_path: Path,
    *,
    title: str,
    category: str = "custom",
    subject_template: Optional[str] = None,
    body_template: str,
) -> dict:
    """Insert a new user-defined template and return it as a dict."""
    con = _connect(db_path)
    try:
        cur = con.execute(
            """
            INSERT INTO message_templates
                (title, category, subject_template, body_template, is_builtin)
            VALUES
                (?, ?, ?, ?, 0)
            """,
            (title, category, subject_template, body_template),
        )
        con.commit()
        row = con.execute(
            "SELECT * FROM message_templates WHERE id = ?", (cur.lastrowid,)
        ).fetchone()
        return dict(row)
    finally:
        con.close()


def update_template(db_path: Path, template_id: int, **fields) -> dict:
    """
    Update allowed fields on a user-defined template.

    Raises PermissionError if the template is a built-in (is_builtin=1).
    Raises KeyError if the template is not found.
    """
    if not fields:
        # Nothing to update — just return current state
        con = _connect(db_path)
        try:
            row = con.execute(
                "SELECT * FROM message_templates WHERE id = ?", (template_id,)
            ).fetchone()
            if row is None:
                raise KeyError(f"Template {template_id} not found")
            return dict(row)
        finally:
            con.close()

    _ALLOWED_FIELDS = {
        "title", "category", "subject_template", "body_template",
    }
    invalid = set(fields) - _ALLOWED_FIELDS
    if invalid:
        raise ValueError(f"Cannot update field(s): {invalid}")

    con = _connect(db_path)
    try:
        row = con.execute(
            "SELECT id, is_builtin FROM message_templates WHERE id = ?",
            (template_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"Template {template_id} not found")
        if row["is_builtin"]:
            raise PermissionError(
                f"Template {template_id} is a built-in and cannot be modified"
            )

        set_clause = ", ".join(f"{col} = ?" for col in fields)
        values = list(fields.values()) + [_now_utc(), template_id]
        con.execute(
            f"UPDATE message_templates SET {set_clause}, updated_at = ? WHERE id = ?",
            values,
        )
        con.commit()
        updated = con.execute(
            "SELECT * FROM message_templates WHERE id = ?", (template_id,)
        ).fetchone()
        return dict(updated)
    finally:
        con.close()


def delete_template(db_path: Path, template_id: int) -> None:
    """
    Delete a user-defined template.

    Raises PermissionError if the template is a built-in (is_builtin=1).
    Raises KeyError if the template is not found.
    """
    con = _connect(db_path)
    try:
        row = con.execute(
            "SELECT id, is_builtin FROM message_templates WHERE id = ?",
            (template_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"Template {template_id} not found")
        if row["is_builtin"]:
            raise PermissionError(
                f"Template {template_id} is a built-in and cannot be deleted"
            )
        con.execute("DELETE FROM message_templates WHERE id = ?", (template_id,))
        con.commit()
    finally:
        con.close()


def update_message_body(db_path: Path, message_id: int, body: str) -> dict:
    """Update the body text of a draft message before approval. Returns updated row."""
    con = _connect(db_path)
    try:
        row = con.execute("SELECT id FROM messages WHERE id=?", (message_id,)).fetchone()
        if not row:
            raise KeyError(f"message {message_id} not found")
        con.execute("UPDATE messages SET body=? WHERE id=?", (body, message_id))
        con.commit()
        updated = con.execute("SELECT * FROM messages WHERE id=?", (message_id,)).fetchone()
        return dict(updated)
    finally:
        con.close()
