"""POST /api/settings/data/backup/restore (peregrine#222).

The Data page offered "Restore from Backup", but the dialog's Restore button did nothing
and there was no backend route behind it. The route restores settings files only, from a
zip the user uploads, so it is deliberately strict: an allowlist of file names, YAML that
must parse, size limits, and no writes outside the user's config directory.
"""
import io
import zipfile

import pytest
import yaml
from fastapi.testclient import TestClient

URL = "/api/settings/data/backup/restore"


def _zip(files: dict[str, str | bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, content in files.items():
            zf.writestr(name, content)
    return buf.getvalue()


@pytest.fixture
def api(tmp_path, monkeypatch):
    import dev_api

    cfg = tmp_path / "data" / "config"
    cfg.mkdir(parents=True)
    monkeypatch.setattr(dev_api, "_config_dir", lambda: cfg)
    monkeypatch.setattr(dev_api, "_CLOUD_MODE", False)
    monkeypatch.setattr(dev_api, "IS_DEMO", False)
    return TestClient(dev_api.app), cfg, tmp_path


def _post(client, payload: bytes, name: str = "backup.zip", headers: dict | None = None):
    return client.post(
        URL,
        files={"file": (name, payload, "application/zip")},
        headers={"X-Requested-With": "peregrine"} if headers is None else headers,
    )


def test_a_cross_site_form_post_cannot_trigger_a_restore(api):
    """A multipart POST needs no CORS preflight, so any web page the user visits could submit
    one to a self-hosted instance. Browsers cannot add a custom header to a cross-site form,
    so requiring one stops that."""
    client, cfg, _ = api

    resp = _post(client, _zip({"config/user.yaml": "name: attacker\n"}), headers={})

    assert resp.status_code == 403
    assert not (cfg / "user.yaml").exists()


def test_restores_config_files_and_overwrites_existing(api):
    client, cfg, _ = api
    (cfg / "user.yaml").write_text("name: Old Name\n")

    resp = _post(client, _zip({
        "config/user.yaml": "name: New Name\n",
        "config/search_profiles.yaml": "profiles: []\n",
    }))

    assert resp.status_code == 200
    body = resp.json()
    assert sorted(body["restored"]) == ["config/search_profiles.yaml", "config/user.yaml"]
    assert body["skipped"] == []
    assert yaml.safe_load((cfg / "user.yaml").read_text()) == {"name": "New Name"}
    assert (cfg / "search_profiles.yaml").exists()


def test_restores_integration_configs_into_the_integrations_folder(api):
    client, cfg, _ = api

    resp = _post(client, _zip({"config/integrations/slack.yaml": "webhook_url: https://example.com/hook\n"}))

    assert resp.status_code == 200
    assert yaml.safe_load((cfg / "integrations" / "slack.yaml").read_text())["webhook_url"].startswith("https://")


def test_files_outside_the_allowlist_are_skipped_not_written(api):
    client, cfg, root = api

    resp = _post(client, _zip({
        "config/user.yaml": "name: Kept\n",
        "data/staging.db": b"SQLite format 3\x00",
        "config/tokens.yaml": "secret: nope\n",
        "config/license.json": "{}",
        "config/notes.txt": "hello",
        "config/sub/deep.yaml": "a: 1\n",
        "backup-manifest.json": "{}",
    }))

    body = resp.json()
    assert body["restored"] == ["config/user.yaml"]
    assert sorted(body["skipped"]) == sorted([
        "data/staging.db", "config/tokens.yaml", "config/license.json", "config/notes.txt", "config/sub/deep.yaml",
    ])
    assert not (cfg / "tokens.yaml").exists()
    assert not (cfg / "license.json").exists()
    assert not (root / "data" / "staging.db").exists()


@pytest.mark.parametrize("evil", [
    "../escape.yaml",
    "config/../../escape.yaml",
    "config/../escape.yaml",
    "/tmp/escape.yaml",
    "config/..\\escape.yaml",
])
def test_path_traversal_names_never_write_outside_the_config_dir(api, evil):
    client, _cfg, root = api

    resp = _post(client, _zip({"config/user.yaml": "name: ok\n", evil: "owned: true\n"}))

    assert resp.status_code == 200
    assert evil in resp.json()["skipped"]
    written = {p.relative_to(root) for p in root.rglob("*") if p.is_file()}
    assert all("escape" not in str(p) for p in written)


def test_invalid_yaml_rejects_the_whole_restore_and_writes_nothing(api):
    client, cfg, _ = api
    (cfg / "user.yaml").write_text("name: Original\n")

    resp = _post(client, _zip({
        "config/user.yaml": "name: Replaced\n",
        "config/search_profiles.yaml": "profiles: [unclosed\n",
    }))

    assert resp.status_code == 400
    assert "search_profiles.yaml" in resp.json()["detail"]
    assert yaml.safe_load((cfg / "user.yaml").read_text()) == {"name": "Original"}


def test_not_a_zip_is_a_friendly_400(api):
    client, _, _ = api

    resp = _post(client, b"this is not a zip file")

    assert resp.status_code == 400
    assert "backup" in resp.json()["detail"].lower()


def test_a_zip_with_nothing_restorable_is_a_400(api):
    client, _, _ = api

    resp = _post(client, _zip({"data/staging.db": b"x", "readme.txt": "hi"}))

    assert resp.status_code == 400
    assert "settings" in resp.json()["detail"].lower()


def test_oversized_upload_is_rejected(api, monkeypatch):
    import dev_api

    client, _, _ = api
    monkeypatch.setattr(dev_api, "_RESTORE_MAX_UPLOAD_BYTES", 100)

    resp = _post(client, _zip({"config/user.yaml": "name: " + "x" * 500 + "\n"}))

    assert resp.status_code == 413


def test_zip_bomb_by_uncompressed_size_is_rejected(api, monkeypatch):
    import dev_api

    client, _, _ = api
    monkeypatch.setattr(dev_api, "_RESTORE_MAX_UNCOMPRESSED_BYTES", 1000)

    resp = _post(client, _zip({"config/user.yaml": "a: " + "0" * 5000 + "\n"}))

    assert resp.status_code == 413


def test_single_oversized_settings_file_is_rejected(api, monkeypatch):
    """Caps what yaml.safe_load is asked to chew on, since alias expansion can blow up memory."""
    import dev_api

    client, cfg, _ = api
    monkeypatch.setattr(dev_api, "_RESTORE_MAX_MEMBER_BYTES", 200)

    resp = _post(client, _zip({"config/user.yaml": "a: " + "0" * 500 + "\n"}))

    assert resp.status_code == 413
    assert not (cfg / "user.yaml").exists()


def test_successful_restore_leaves_no_temp_files_behind(api):
    client, cfg, _ = api

    _post(client, _zip({"config/user.yaml": "name: x\n", "config/integrations/slack.yaml": "a: 1\n"}))

    assert [p.name for p in cfg.rglob("*") if p.is_file() and "tmp" in p.name] == []


def test_restored_files_are_owner_only(api):
    import os
    import stat

    client, cfg, _ = api

    _post(client, _zip({"config/email.yaml": "host: imap.example.com\n"}))

    assert stat.S_IMODE(os.stat(cfg / "email.yaml").st_mode) == 0o600


def test_too_many_members_is_rejected(api, monkeypatch):
    import dev_api

    client, _, _ = api
    monkeypatch.setattr(dev_api, "_RESTORE_MAX_MEMBERS", 3)

    resp = _post(client, _zip({f"config/f{i}.yaml": "a: 1\n" for i in range(10)}))

    assert resp.status_code == 413


def test_blocked_in_demo_mode(api, monkeypatch):
    import dev_api

    client, cfg, _ = api
    monkeypatch.setattr(dev_api, "IS_DEMO", True)

    resp = _post(client, _zip({"config/user.yaml": "name: x\n"}))

    assert resp.status_code == 403
    assert not (cfg / "user.yaml").exists()


def test_blocked_on_the_hosted_version(api, monkeypatch):
    import dev_api

    client, cfg, _ = api
    monkeypatch.setattr(dev_api, "_CLOUD_MODE", True)

    resp = _post(client, _zip({"config/user.yaml": "name: x\n"}))

    assert resp.status_code == 403
    assert not (cfg / "user.yaml").exists()
