"""Tests for scripts/backup.py — create, list, restore, and multi-instance support."""
from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from scripts.backup import (
    _detect_source_label,
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
