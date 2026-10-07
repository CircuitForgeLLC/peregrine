"""Settings > Connections integration endpoints (peregrine#223).

The routes used to iterate REGISTRY (a dict of name -> class) as if it were a list of
instances, so list, test, connect and disconnect all failed. These tests pin the contract
the Vue store expects: {id, name, connected, tier_required, fields} on list, and
{ok, error?} on test and connect.
"""
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from scripts.integrations.base import IntegrationBase


class _GoodIntegration(IntegrationBase):
    name = "fake_good"
    label = "Fake Good"
    tier = "paid"

    def __init__(self):
        self._config: dict = {}

    def fields(self) -> list[dict]:
        return [
            {"key": "token", "label": "Token", "type": "password", "placeholder": "", "required": True, "help": ""},
            {"key": "note", "label": "Note", "type": "text", "placeholder": "", "required": False, "help": ""},
        ]

    def connect(self, config: dict) -> bool:
        self._config = config
        return bool(config.get("token"))

    def test(self) -> bool:
        return True


class _BadIntegration(_GoodIntegration):
    name = "fake_bad"
    label = "Fake Bad"
    tier = "free"

    def test(self) -> bool:
        return False


@pytest.fixture
def api(monkeypatch, tmp_path):
    import dev_api

    monkeypatch.setattr("scripts.integrations.REGISTRY", {
        _GoodIntegration.name: _GoodIntegration,
        _BadIntegration.name: _BadIntegration,
    })
    monkeypatch.setattr(dev_api, "_config_dir", lambda: tmp_path)
    monkeypatch.setattr(dev_api, "IS_DEMO", False)  # other test modules reload dev_api in demo mode
    monkeypatch.setattr(dev_api, "_get_effective_tier", lambda: "premium")  # tier gating has its own tests
    return TestClient(dev_api.app), tmp_path


def _config_file(tmp_path: Path, name: str) -> Path:
    return tmp_path / "integrations" / f"{name}.yaml"


def test_list_returns_the_shape_the_settings_page_expects(api):
    client, _ = api

    resp = client.get("/api/settings/system/integrations")

    assert resp.status_code == 200
    by_id = {row["id"]: row for row in resp.json()}
    good = by_id["fake_good"]
    assert good["name"] == "Fake Good"
    assert good["connected"] is False
    assert good["tier_required"] == "paid"
    assert good["fields"] == [
        {"key": "token", "label": "Token", "type": "password"},
        {"key": "note", "label": "Note", "type": "text"},
    ]
    assert by_id["fake_bad"]["tier_required"] == "free"


def test_list_marks_an_integration_connected_once_its_config_exists(api):
    client, tmp_path = api
    path = _config_file(tmp_path, "fake_good")
    path.parent.mkdir(parents=True)
    path.write_text(yaml.dump({"token": "x"}))

    rows = {r["id"]: r for r in client.get("/api/settings/system/integrations").json()}

    assert rows["fake_good"]["connected"] is True
    assert rows["fake_bad"]["connected"] is False


def test_list_never_exposes_stored_secrets(api):
    client, tmp_path = api
    path = _config_file(tmp_path, "fake_good")
    path.parent.mkdir(parents=True)
    path.write_text(yaml.dump({"token": "super-secret-value"}))

    assert "super-secret-value" not in client.get("/api/settings/system/integrations").text


def test_list_works_against_the_real_registry(monkeypatch, tmp_path):
    import dev_api

    monkeypatch.setattr(dev_api, "_config_dir", lambda: tmp_path)
    resp = TestClient(dev_api.app).get("/api/settings/system/integrations")

    assert resp.status_code == 200
    rows = resp.json()
    assert rows, "real registry should list at least one integration"
    for row in rows:
        assert row["tier_required"] in {"free", "paid", "premium"}
        assert row["fields"], f"{row['id']} should declare form fields"


def test_test_succeeds_without_saving_anything(api):
    client, tmp_path = api

    resp = client.post("/api/settings/system/integrations/fake_good/test", json={"token": "abc"})

    assert resp.json() == {"ok": True, "error": None}
    assert not _config_file(tmp_path, "fake_good").exists()


def test_test_reports_missing_required_fields(api):
    client, _ = api

    resp = client.post("/api/settings/system/integrations/fake_good/test", json={"note": "hi"})

    body = resp.json()
    assert body["ok"] is False
    assert "required" in body["error"].lower()


def test_test_reports_failed_connection_in_plain_words(api):
    client, _ = api

    body = client.post("/api/settings/system/integrations/fake_bad/test", json={"token": "abc"}).json()

    assert body["ok"] is False
    assert body["error"]


def test_connect_saves_only_declared_fields(api):
    client, tmp_path = api

    resp = client.post(
        "/api/settings/system/integrations/fake_good/connect",
        json={"token": "abc", "note": "n", "unexpected": "drop me"},
    )

    assert resp.json() == {"ok": True}
    assert yaml.safe_load(_config_file(tmp_path, "fake_good").read_text()) == {"token": "abc", "note": "n"}


def test_connect_does_not_save_when_the_test_fails(api):
    client, tmp_path = api

    body = client.post("/api/settings/system/integrations/fake_bad/connect", json={"token": "abc"}).json()

    assert body["ok"] is False
    assert not _config_file(tmp_path, "fake_bad").exists()


def test_disconnect_removes_the_config_and_is_repeatable(api):
    client, tmp_path = api
    client.post("/api/settings/system/integrations/fake_good/connect", json={"token": "abc"})
    assert _config_file(tmp_path, "fake_good").exists()

    first = client.post("/api/settings/system/integrations/fake_good/disconnect")
    second = client.post("/api/settings/system/integrations/fake_good/disconnect")

    assert first.json() == {"ok": True}
    assert second.json() == {"ok": True}
    assert not _config_file(tmp_path, "fake_good").exists()


@pytest.mark.parametrize("action", ["test", "connect", "disconnect"])
def test_unknown_integration_is_a_404(api, action):
    client, _ = api

    resp = client.post(f"/api/settings/system/integrations/nope/{action}", json={})

    assert resp.status_code == 404


@pytest.mark.parametrize("action", ["connect", "disconnect"])
def test_writes_are_blocked_in_demo_mode(api, monkeypatch, action):
    import dev_api

    client, tmp_path = api
    monkeypatch.setattr(dev_api, "IS_DEMO", True)

    resp = client.post(f"/api/settings/system/integrations/fake_good/{action}", json={"token": "abc"})

    assert resp.status_code == 403
    assert not _config_file(tmp_path, "fake_good").exists()
