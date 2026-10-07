"""Email sync must read what Settings > Connections actually saves (peregrine#224).

Settings writes non-secret fields to <config_dir>/email.yaml (with the SSL flag stored
as `ssl`) and puts the password in the credential store. Sync used to read only a
global config/email.yaml and then look for cfg["password"], so an inbox configured
through the UI could not sync, and in cloud mode every tenant would read one shared file.
"""
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from scripts import imap_sync


def _write_email_yaml(config_dir: Path, data: dict) -> None:
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "email.yaml").write_text(yaml.dump(data))


def test_password_comes_from_the_credential_store_when_yaml_has_none(tmp_path):
    _write_email_yaml(tmp_path, {"host": "imap.example.com", "username": "me@example.com"})

    with patch("scripts.imap_sync.get_credential", return_value="stored-secret") as get_cred:
        cfg = imap_sync.load_config(config_dir=tmp_path)

    assert cfg["password"] == "stored-secret"
    assert get_cred.call_args.args[:2] == ("peregrine", "imap_password")


def test_legacy_yaml_password_still_works_and_is_not_overridden(tmp_path):
    _write_email_yaml(tmp_path, {"username": "me@example.com", "password": "legacy-secret"})

    with patch("scripts.imap_sync.get_credential", return_value="stored-secret"):
        cfg = imap_sync.load_config(config_dir=tmp_path)

    assert cfg["password"] == "legacy-secret"


def test_missing_password_everywhere_leaves_it_unset(tmp_path):
    _write_email_yaml(tmp_path, {"username": "me@example.com"})

    with patch("scripts.imap_sync.get_credential", return_value=None):
        cfg = imap_sync.load_config(config_dir=tmp_path)

    assert "password" not in cfg


def test_ssl_flag_saved_by_settings_is_honoured(tmp_path):
    _write_email_yaml(tmp_path, {"username": "me@example.com", "ssl": False})

    with patch("scripts.imap_sync.get_credential", return_value=None):
        cfg = imap_sync.load_config(config_dir=tmp_path)

    assert cfg["use_ssl"] is False


def test_explicit_use_ssl_wins_over_ssl(tmp_path):
    _write_email_yaml(tmp_path, {"username": "me@example.com", "ssl": False, "use_ssl": True})

    with patch("scripts.imap_sync.get_credential", return_value=None):
        cfg = imap_sync.load_config(config_dir=tmp_path)

    assert cfg["use_ssl"] is True


def test_tenant_credentials_dir_is_passed_through(tmp_path):
    _write_email_yaml(tmp_path, {"username": "me@example.com"})
    cred_dir = tmp_path / "credentials"

    with patch("scripts.imap_sync.get_credential", return_value="s") as get_cred:
        imap_sync.load_config(config_dir=tmp_path, cred_dir=cred_dir)

    assert get_cred.call_args.kwargs["cred_dir"] == cred_dir


def test_no_config_at_all_raises_file_not_found(tmp_path):
    with pytest.raises(FileNotFoundError):
        imap_sync.load_config(config_dir=tmp_path)


def test_legacy_global_file_is_the_fallback_for_self_hosted(tmp_path, monkeypatch):
    legacy = tmp_path / "legacy" / "email.yaml"
    legacy.parent.mkdir()
    legacy.write_text(yaml.dump({"username": "legacy@example.com", "password": "p"}))
    monkeypatch.setattr(imap_sync, "CONFIG_PATH", legacy)

    cfg = imap_sync.load_config(config_dir=tmp_path / "empty-config-dir")

    assert cfg["username"] == "legacy@example.com"


def test_cloud_never_falls_back_to_the_shared_global_file(tmp_path, monkeypatch):
    legacy = tmp_path / "legacy" / "email.yaml"
    legacy.parent.mkdir()
    legacy.write_text(yaml.dump({"username": "someone-else@example.com", "password": "p"}))
    monkeypatch.setattr(imap_sync, "CONFIG_PATH", legacy)

    with pytest.raises(FileNotFoundError):
        imap_sync.load_config(config_dir=tmp_path / "tenant" / "config", allow_legacy_fallback=False)


def test_sync_all_loads_the_config_next_to_the_database(tmp_path, monkeypatch):
    monkeypatch.delenv("CLOUD_MODE", raising=False)
    db_path = tmp_path / "staging.db"
    seen = {}

    def fake_load_config(**kwargs):
        seen.update(kwargs)
        return {}

    with patch("scripts.imap_sync.load_config", side_effect=fake_load_config), \
         patch("scripts.imap_sync.init_db"), \
         patch("scripts.imap_sync.get_interview_jobs", return_value={}):
        imap_sync.sync_all(db_path)

    assert seen["config_dir"] == tmp_path / "config"
    assert seen["cred_dir"] is None
    assert seen["allow_legacy_fallback"] is True


def test_sync_all_in_cloud_mode_is_tenant_scoped(tmp_path, monkeypatch):
    monkeypatch.setenv("CLOUD_MODE", "1")
    db_path = tmp_path / "staging.db"
    seen = {}

    def fake_load_config(**kwargs):
        seen.update(kwargs)
        return {}

    with patch("scripts.imap_sync.load_config", side_effect=fake_load_config), \
         patch("scripts.imap_sync.init_db"), \
         patch("scripts.imap_sync.get_interview_jobs", return_value={}):
        imap_sync.sync_all(db_path)

    assert seen["config_dir"] == tmp_path / "config"
    assert seen["cred_dir"] == tmp_path / "config" / "credentials"
    assert seen["allow_legacy_fallback"] is False
