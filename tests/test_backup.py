"""Tests for scripts/backup.py — create, list, restore, and multi-instance support."""
from __future__ import annotations

import json
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from scripts.backup import (
    _decrypt_db_to_bytes,
    _detect_source_label,
    _encrypt_db_from_bytes,
    create_backup,
    list_backup_contents,
    restore_backup,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_instance(tmp_path: Path, name: str, *, root_db: bool = False) -> Path:
    """Build a minimal fake instance directory for testing."""
    base = tmp_path / name
    base.mkdir()

    # Secret configs
    (base / "config").mkdir()
    (base / "config" / "notion.yaml").write_text("token: secret")
    (base / "config" / "email.yaml").write_text("user: test@example.com")

    # Extra config
    (base / "config" / "llm.yaml").write_text("backend: ollama")
    (base / "config" / "resume_keywords.yaml").write_text("keywords: [python]")
    (base / "config" / "server.yaml").write_text("port: 8502")

    # DB — either at data/staging.db (Peregrine) or staging.db root (legacy)
    if root_db:
        (base / "staging.db").write_bytes(b"SQLite legacy")
    else:
        (base / "data").mkdir()
        (base / "data" / "staging.db").write_bytes(b"SQLite peregrine")

    return base


# ---------------------------------------------------------------------------
# create_backup
# ---------------------------------------------------------------------------

class TestCreateBackup:
    def test_returns_valid_zip(self, tmp_path):
        base = _make_instance(tmp_path, "peregrine")
        data = create_backup(base)
        assert zipfile.is_zipfile(__import__("io").BytesIO(data))

    def test_includes_secret_configs(self, tmp_path):
        base = _make_instance(tmp_path, "peregrine")
        data = create_backup(base)
        info = list_backup_contents(data)
        assert "config/notion.yaml" in info["files"]
        assert "config/email.yaml" in info["files"]

    def test_includes_extra_configs(self, tmp_path):
        base = _make_instance(tmp_path, "peregrine")
        data = create_backup(base)
        info = list_backup_contents(data)
        assert "config/llm.yaml" in info["files"]
        assert "config/resume_keywords.yaml" in info["files"]
        assert "config/server.yaml" in info["files"]

    def test_includes_db_by_default(self, tmp_path):
        base = _make_instance(tmp_path, "peregrine")
        data = create_backup(base)
        info = list_backup_contents(data)
        assert info["manifest"]["includes_db"] is True
        assert any(f.endswith(".db") for f in info["files"])

    def test_excludes_db_when_flag_false(self, tmp_path):
        base = _make_instance(tmp_path, "peregrine")
        data = create_backup(base, include_db=False)
        info = list_backup_contents(data)
        assert info["manifest"]["includes_db"] is False
        assert not any(f.endswith(".db") for f in info["files"])

    def test_silently_skips_missing_files(self, tmp_path):
        base = _make_instance(tmp_path, "peregrine")
        # tokens.yaml not created in fixture — should not raise
        data = create_backup(base)
        info = list_backup_contents(data)
        assert "config/tokens.yaml" not in info["files"]

    def test_manifest_contains_source_label(self, tmp_path):
        base = _make_instance(tmp_path, "peregrine")
        data = create_backup(base)
        info = list_backup_contents(data)
        assert info["manifest"]["source"] == "peregrine"

    def test_source_label_override(self, tmp_path):
        base = _make_instance(tmp_path, "peregrine")
        data = create_backup(base, source_label="custom-label")
        info = list_backup_contents(data)
        assert info["manifest"]["source"] == "custom-label"


# ---------------------------------------------------------------------------
# Legacy instance (staging.db at repo root)
# ---------------------------------------------------------------------------

class TestLegacyInstance:
    def test_picks_up_root_db(self, tmp_path):
        base = _make_instance(tmp_path, "job-seeker", root_db=True)
        data = create_backup(base)
        info = list_backup_contents(data)
        assert "staging.db" in info["files"]
        assert "data/staging.db" not in info["files"]

    def test_source_label_is_job_seeker(self, tmp_path):
        base = _make_instance(tmp_path, "job-seeker", root_db=True)
        data = create_backup(base)
        info = list_backup_contents(data)
        assert info["manifest"]["source"] == "job-seeker"

    def test_missing_peregrine_only_configs_skipped(self, tmp_path):
        """Legacy doesn't have server.yaml, user.yaml, etc. — should not error."""
        base = _make_instance(tmp_path, "job-seeker", root_db=True)
        # Remove server.yaml to simulate legacy (it won't exist there)
        (base / "config" / "server.yaml").unlink()
        data = create_backup(base)
        info = list_backup_contents(data)
        assert "config/server.yaml" not in info["files"]
        assert "config/notion.yaml" in info["files"]


# ---------------------------------------------------------------------------
# list_backup_contents
# ---------------------------------------------------------------------------

class TestListBackupContents:
    def test_returns_manifest_and_files(self, tmp_path):
        base = _make_instance(tmp_path, "peregrine")
        data = create_backup(base)
        info = list_backup_contents(data)
        assert "manifest" in info
        assert "files" in info
        assert "sizes" in info
        assert "total_bytes" in info

    def test_total_bytes_is_sum_of_file_sizes(self, tmp_path):
        base = _make_instance(tmp_path, "peregrine")
        data = create_backup(base)
        info = list_backup_contents(data)
        expected = sum(info["sizes"][f] for f in info["files"] if f in info["sizes"])
        assert info["total_bytes"] == expected

    def test_manifest_not_in_files_list(self, tmp_path):
        base = _make_instance(tmp_path, "peregrine")
        data = create_backup(base)
        info = list_backup_contents(data)
        assert "backup-manifest.json" not in info["files"]


# ---------------------------------------------------------------------------
# restore_backup
# ---------------------------------------------------------------------------

class TestRestoreBackup:
    def test_restores_all_files(self, tmp_path):
        src = _make_instance(tmp_path, "peregrine")
        dst = tmp_path / "restored"
        dst.mkdir()
        data = create_backup(src)
        result = restore_backup(data, dst)
        assert len(result["restored"]) > 0
        assert (dst / "config" / "notion.yaml").exists()

    def test_skips_db_when_flag_false(self, tmp_path):
        src = _make_instance(tmp_path, "peregrine")
        dst = tmp_path / "restored"
        dst.mkdir()
        data = create_backup(src)
        result = restore_backup(data, dst, include_db=False)
        assert not any(f.endswith(".db") for f in result["restored"])
        assert any(f.endswith(".db") for f in result["skipped"])

    def test_no_overwrite_skips_existing(self, tmp_path):
        src = _make_instance(tmp_path, "peregrine")
        dst = tmp_path / "restored"
        dst.mkdir()
        (dst / "config").mkdir()
        existing = dst / "config" / "notion.yaml"
        existing.write_text("original content")
        data = create_backup(src)
        result = restore_backup(data, dst, overwrite=False)
        assert "config/notion.yaml" in result["skipped"]
        assert existing.read_text() == "original content"

    def test_overwrite_replaces_existing(self, tmp_path):
        src = _make_instance(tmp_path, "peregrine")
        dst = tmp_path / "restored"
        dst.mkdir()
        (dst / "config").mkdir()
        (dst / "config" / "notion.yaml").write_text("stale content")
        data = create_backup(src)
        restore_backup(data, dst, overwrite=True)
        assert (dst / "config" / "notion.yaml").read_text() == "token: secret"

    def test_roundtrip_preserves_content(self, tmp_path):
        src = _make_instance(tmp_path, "peregrine")
        original = (src / "config" / "notion.yaml").read_text()
        dst = tmp_path / "restored"
        dst.mkdir()
        data = create_backup(src)
        restore_backup(data, dst)
        assert (dst / "config" / "notion.yaml").read_text() == original


# ---------------------------------------------------------------------------
# _detect_source_label
# ---------------------------------------------------------------------------

class TestDetectSourceLabel:
    def test_returns_directory_name(self, tmp_path):
        base = tmp_path / "peregrine"
        base.mkdir()
        assert _detect_source_label(base) == "peregrine"

    def test_legacy_label(self, tmp_path):
        base = tmp_path / "job-seeker"
        base.mkdir()
        assert _detect_source_label(base) == "job-seeker"


# ---------------------------------------------------------------------------
# Cloud mode — SQLCipher encrypt / decrypt (pysqlcipher3 mocked)
# ---------------------------------------------------------------------------

class _FakeCursor:
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def execute(self, *a): pass
    def fetchone(self): return None


def _make_mock_sqlcipher_conn(plain_bytes: bytes, tmp_path: Path):
    """Return a mock pysqlcipher3 connection that writes plain_bytes to the
    first 'ATTACH DATABASE' path it sees (simulating sqlcipher_export)."""
    attached: dict = {}

    conn = MagicMock()

    def fake_execute(sql, *args):
        if "ATTACH DATABASE" in sql:
            # Extract path between first pair of quotes
            parts = sql.split("'")
            path = parts[1]
            attached["path"] = path
        elif "sqlcipher_export" in sql:
            # Simulate export: write plain_bytes to the attached path
            Path(attached["path"]).write_bytes(plain_bytes)

    conn.execute.side_effect = fake_execute
    conn.close = MagicMock()
    return conn


class TestCloudBackup:
    """Backup/restore with SQLCipher encryption — pysqlcipher3 mocked out."""

    def test_create_backup_decrypts_db_when_key_set(self, tmp_path):
        """With db_key, _decrypt_db_to_bytes is called and plain bytes go into zip."""
        base = _make_instance(tmp_path, "cloud-user")
        plain_db = b"SQLite format 3\x00plain-content"

        with patch("scripts.backup._decrypt_db_to_bytes", return_value=plain_db) as mock_dec:
            data = create_backup(base, include_db=True, db_key="testkey")

        mock_dec.assert_called_once()
        # The zip should contain the plain bytes, not the raw encrypted file
        with zipfile.ZipFile(__import__("io").BytesIO(data)) as zf:
            db_files = [n for n in zf.namelist() if n.endswith(".db")]
            assert len(db_files) == 1
            assert zf.read(db_files[0]) == plain_db

    def test_create_backup_no_key_reads_file_directly(self, tmp_path):
        """Without db_key, _decrypt_db_to_bytes is NOT called."""
        base = _make_instance(tmp_path, "local-user")

        with patch("scripts.backup._decrypt_db_to_bytes") as mock_dec:
            create_backup(base, include_db=True, db_key="")

        mock_dec.assert_not_called()

    def test_restore_backup_encrypts_db_when_key_set(self, tmp_path):
        """With db_key, _encrypt_db_from_bytes is called for .db files."""
        src = _make_instance(tmp_path, "cloud-src")
        dst = tmp_path / "cloud-dst"
        dst.mkdir()
        plain_db = b"SQLite format 3\x00plain-content"

        # Create a backup with plain DB bytes
        with patch("scripts.backup._decrypt_db_to_bytes", return_value=plain_db):
            data = create_backup(src, include_db=True, db_key="testkey")

        with patch("scripts.backup._encrypt_db_from_bytes") as mock_enc:
            restore_backup(data, dst, include_db=True, db_key="testkey")

        mock_enc.assert_called_once()
        call_args = mock_enc.call_args
        assert call_args[0][0] == plain_db      # plain_bytes
        assert call_args[0][2] == "testkey"     # db_key

    def test_restore_backup_no_key_writes_file_directly(self, tmp_path):
        """Without db_key, _encrypt_db_from_bytes is NOT called."""
        src = _make_instance(tmp_path, "local-src")
        dst = tmp_path / "local-dst"
        dst.mkdir()
        data = create_backup(src, include_db=True, db_key="")

        with patch("scripts.backup._encrypt_db_from_bytes") as mock_enc:
            restore_backup(data, dst, include_db=True, db_key="")

        mock_enc.assert_not_called()

    def test_decrypt_db_to_bytes_calls_sqlcipher(self, tmp_path):
        """_decrypt_db_to_bytes imports pysqlcipher3.dbapi2 and calls sqlcipher_export."""
        fake_db = tmp_path / "staging.db"
        fake_db.write_bytes(b"encrypted")
        plain_bytes = b"SQLite format 3\x00"

        mock_conn = _make_mock_sqlcipher_conn(plain_bytes, tmp_path)
        mock_module = MagicMock()
        mock_module.connect.return_value = mock_conn

        # Must set dbapi2 explicitly on the package mock so `from pysqlcipher3 import
        # dbapi2` resolves to mock_module (not a new auto-created MagicMock attr).
        mock_pkg = MagicMock()
        mock_pkg.dbapi2 = mock_module

        with patch.dict("sys.modules", {"pysqlcipher3": mock_pkg, "pysqlcipher3.dbapi2": mock_module}):
            result = _decrypt_db_to_bytes(fake_db, "testkey")

        mock_module.connect.assert_called_once_with(str(fake_db))
        assert result == plain_bytes

    def test_encrypt_db_from_bytes_calls_sqlcipher(self, tmp_path):
        """_encrypt_db_from_bytes imports pysqlcipher3.dbapi2 and calls sqlcipher_export."""
        dest = tmp_path / "staging.db"
        plain_bytes = b"SQLite format 3\x00"

        mock_conn = MagicMock()
        mock_module = MagicMock()
        mock_module.connect.return_value = mock_conn

        mock_pkg = MagicMock()
        mock_pkg.dbapi2 = mock_module

        with patch.dict("sys.modules", {"pysqlcipher3": mock_pkg, "pysqlcipher3.dbapi2": mock_module}):
            _encrypt_db_from_bytes(plain_bytes, dest, "testkey")

        mock_module.connect.assert_called_once()
        # Verify ATTACH DATABASE call included the dest path and key
        attach_calls = [
            call for call in mock_conn.execute.call_args_list
            if "ATTACH DATABASE" in str(call)
        ]
        assert len(attach_calls) == 1
        assert str(dest) in str(attach_calls[0])
        assert "testkey" in str(attach_calls[0])
