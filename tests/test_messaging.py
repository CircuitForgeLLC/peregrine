"""
Unit tests for scripts/messaging.py — DB helpers for messages and message_templates.

TDD approach: tests written before implementation.
"""
import sqlite3
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _apply_migration_008(db_path: Path) -> None:
    """Apply migration 008 directly so tests run without the full migrate_db stack."""
    migration = (
        Path(__file__).parent.parent / "migrations" / "008_messaging.sql"
    )
    sql = migration.read_text(encoding="utf-8")
    con = sqlite3.connect(db_path)
    try:
        # Create jobs table stub so FK references don't break
        con.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT
            )
        """)
        con.execute("""
            CREATE TABLE IF NOT EXISTS job_contacts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id INTEGER
            )
        """)
        # Execute migration statements
        statements = [s.strip() for s in sql.split(";") if s.strip()]
        for stmt in statements:
            stripped = "\n".join(
                ln for ln in stmt.splitlines() if not ln.strip().startswith("--")
            ).strip()
            if stripped:
                con.execute(stripped)
        con.commit()
    finally:
        con.close()


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    """Temporary SQLite DB with migration 008 applied."""
    path = tmp_path / "test.db"
    _apply_migration_008(path)
    return path


@pytest.fixture()
def job_id(db_path: Path) -> int:
    """Insert a dummy job and return its id."""
    con = sqlite3.connect(db_path)
    try:
        cur = con.execute("INSERT INTO jobs (title) VALUES ('Test Job')")
        con.commit()
        return cur.lastrowid
    finally:
        con.close()


# ---------------------------------------------------------------------------
# Message tests
# ---------------------------------------------------------------------------

class TestCreateMessage:
    def test_create_returns_dict(self, db_path: Path, job_id: int) -> None:
        from scripts.messaging import create_message

        msg = create_message(
            db_path,
            job_id=job_id,
            job_contact_id=None,
            type="email",
            direction="outbound",
            subject="Hello",
            body="Body text",
            from_addr="me@example.com",
            to_addr="them@example.com",
            template_id=None,
        )

        assert isinstance(msg, dict)
        assert msg["subject"] == "Hello"
        assert msg["body"] == "Body text"
        assert msg["direction"] == "outbound"
        assert msg["type"] == "email"
        assert "id" in msg
        assert msg["id"] > 0

    def test_create_persists_to_db(self, db_path: Path, job_id: int) -> None:
        from scripts.messaging import create_message

        create_message(
            db_path,
            job_id=job_id,
            job_contact_id=None,
            type="email",
            direction="outbound",
            subject="Persisted",
            body="Stored body",
            from_addr="a@b.com",
            to_addr="c@d.com",
            template_id=None,
        )

        con = sqlite3.connect(db_path)
        try:
            row = con.execute(
                "SELECT subject FROM messages WHERE subject='Persisted'"
            ).fetchone()
            assert row is not None
        finally:
            con.close()


class TestListMessages:
    def _make_message(
        self,
        db_path: Path,
        job_id: int,
        *,
        type: str = "email",
        direction: str = "outbound",
        subject: str = "Subject",
    ) -> dict:
        from scripts.messaging import create_message
        return create_message(
            db_path,
            job_id=job_id,
            job_contact_id=None,
            type=type,
            direction=direction,
            subject=subject,
            body="body",
            from_addr="a@b.com",
            to_addr="c@d.com",
            template_id=None,
        )

    def test_list_returns_all_messages(self, db_path: Path, job_id: int) -> None:
        from scripts.messaging import list_messages

        self._make_message(db_path, job_id, subject="First")
        self._make_message(db_path, job_id, subject="Second")

        result = list_messages(db_path)
        assert len(result) == 2

    def test_list_filtered_by_job_id(self, db_path: Path, job_id: int) -> None:
        from scripts.messaging import list_messages

        # Create a second job
        con = sqlite3.connect(db_path)
        try:
            cur = con.execute("INSERT INTO jobs (title) VALUES ('Other Job')")
            con.commit()
            other_job_id = cur.lastrowid
        finally:
            con.close()

        self._make_message(db_path, job_id, subject="For job 1")
        self._make_message(db_path, other_job_id, subject="For job 2")

        result = list_messages(db_path, job_id=job_id)
        assert len(result) == 1
        assert result[0]["subject"] == "For job 1"

    def test_list_filtered_by_type(self, db_path: Path, job_id: int) -> None:
        from scripts.messaging import list_messages

        self._make_message(db_path, job_id, type="email", subject="Email msg")
        self._make_message(db_path, job_id, type="sms", subject="SMS msg")

        emails = list_messages(db_path, type="email")
        assert len(emails) == 1
        assert emails[0]["type"] == "email"

    def test_list_filtered_by_direction(self, db_path: Path, job_id: int) -> None:
        from scripts.messaging import list_messages

        self._make_message(db_path, job_id, direction="outbound")
        self._make_message(db_path, job_id, direction="inbound")

        outbound = list_messages(db_path, direction="outbound")
        assert len(outbound) == 1
        assert outbound[0]["direction"] == "outbound"

    def test_list_respects_limit(self, db_path: Path, job_id: int) -> None:
        from scripts.messaging import list_messages

        for i in range(5):
            self._make_message(db_path, job_id, subject=f"Msg {i}")

        result = list_messages(db_path, limit=3)
        assert len(result) == 3


class TestDeleteMessage:
    def test_delete_removes_message(self, db_path: Path, job_id: int) -> None:
        from scripts.messaging import create_message, delete_message, list_messages

        msg = create_message(
            db_path,
            job_id=job_id,
            job_contact_id=None,
            type="email",
            direction="outbound",
            subject="To delete",
            body="bye",
            from_addr="a@b.com",
            to_addr="c@d.com",
            template_id=None,
        )

        delete_message(db_path, msg["id"])
        assert list_messages(db_path) == []

    def test_delete_raises_key_error_when_not_found(self, db_path: Path) -> None:
        from scripts.messaging import delete_message

        with pytest.raises(KeyError):
            delete_message(db_path, 99999)


class TestApproveMessage:
    def test_approve_sets_approved_at(self, db_path: Path, job_id: int) -> None:
        from scripts.messaging import approve_message, create_message

        msg = create_message(
            db_path,
            job_id=job_id,
            job_contact_id=None,
            type="email",
            direction="outbound",
            subject="Draft",
            body="Draft body",
            from_addr="a@b.com",
            to_addr="c@d.com",
            template_id=None,
        )
        assert msg.get("approved_at") is None

        updated = approve_message(db_path, msg["id"])
        assert updated["approved_at"] is not None
        assert updated["id"] == msg["id"]

    def test_approve_returns_full_dict(self, db_path: Path, job_id: int) -> None:
        from scripts.messaging import approve_message, create_message

        msg = create_message(
            db_path,
            job_id=job_id,
            job_contact_id=None,
            type="email",
            direction="outbound",
            subject="Draft",
            body="Body here",
            from_addr="a@b.com",
            to_addr="c@d.com",
            template_id=None,
        )

        updated = approve_message(db_path, msg["id"])
        assert updated["body"] == "Body here"
        assert updated["subject"] == "Draft"

    def test_approve_raises_key_error_when_not_found(self, db_path: Path) -> None:
        from scripts.messaging import approve_message

        with pytest.raises(KeyError):
            approve_message(db_path, 99999)


# ---------------------------------------------------------------------------
# Template tests
# ---------------------------------------------------------------------------

class TestListTemplates:
    def test_includes_four_builtins(self, db_path: Path) -> None:
        from scripts.messaging import list_templates

        templates = list_templates(db_path)
        builtin_keys = {t["key"] for t in templates if t["is_builtin"]}
        assert builtin_keys == {
            "follow_up",
            "thank_you",
            "accommodation_request",
            "withdrawal",
        }

    def test_returns_list_of_dicts(self, db_path: Path) -> None:
        from scripts.messaging import list_templates

        templates = list_templates(db_path)
        assert isinstance(templates, list)
        assert all(isinstance(t, dict) for t in templates)


class TestCreateTemplate:
    def test_create_returns_dict(self, db_path: Path) -> None:
        from scripts.messaging import create_template

        tmpl = create_template(
            db_path,
            title="My Template",
            category="custom",
            subject_template="Hello {{name}}",
            body_template="Dear {{name}}, ...",
        )

        assert isinstance(tmpl, dict)
        assert tmpl["title"] == "My Template"
        assert tmpl["category"] == "custom"
        assert tmpl["is_builtin"] == 0
        assert "id" in tmpl

    def test_create_default_category(self, db_path: Path) -> None:
        from scripts.messaging import create_template

        tmpl = create_template(
            db_path,
            title="No Category",
            body_template="Body",
        )
        assert tmpl["category"] == "custom"

    def test_create_appears_in_list(self, db_path: Path) -> None:
        from scripts.messaging import create_template, list_templates

        create_template(db_path, title="Listed", body_template="Body")
        titles = [t["title"] for t in list_templates(db_path)]
        assert "Listed" in titles


class TestUpdateTemplate:
    def test_update_user_template(self, db_path: Path) -> None:
        from scripts.messaging import create_template, update_template

        tmpl = create_template(db_path, title="Original", body_template="Old body")
        updated = update_template(db_path, tmpl["id"], title="Updated", body_template="New body")

        assert updated["title"] == "Updated"
        assert updated["body_template"] == "New body"

    def test_update_returns_persisted_values(self, db_path: Path) -> None:
        from scripts.messaging import create_template, list_templates, update_template

        tmpl = create_template(db_path, title="Before", body_template="x")
        update_template(db_path, tmpl["id"], title="After")

        templates = list_templates(db_path)
        titles = [t["title"] for t in templates]
        assert "After" in titles
        assert "Before" not in titles

    def test_update_builtin_raises_permission_error(self, db_path: Path) -> None:
        from scripts.messaging import list_templates, update_template

        builtin = next(t for t in list_templates(db_path) if t["is_builtin"])
        with pytest.raises(PermissionError):
            update_template(db_path, builtin["id"], title="Hacked")

    def test_update_missing_raises_key_error(self, db_path):
        from scripts.messaging import update_template

        with pytest.raises(KeyError):
            update_template(db_path, 9999, title="Ghost")


class TestDeleteTemplate:
    def test_delete_user_template(self, db_path: Path) -> None:
        from scripts.messaging import create_template, delete_template, list_templates

        tmpl = create_template(db_path, title="To Delete", body_template="bye")
        initial_count = len(list_templates(db_path))
        delete_template(db_path, tmpl["id"])
        assert len(list_templates(db_path)) == initial_count - 1

    def test_delete_builtin_raises_permission_error(self, db_path: Path) -> None:
        from scripts.messaging import delete_template, list_templates

        builtin = next(t for t in list_templates(db_path) if t["is_builtin"])
        with pytest.raises(PermissionError):
            delete_template(db_path, builtin["id"])

    def test_delete_missing_raises_key_error(self, db_path: Path) -> None:
        from scripts.messaging import delete_template

        with pytest.raises(KeyError):
            delete_template(db_path, 99999)
