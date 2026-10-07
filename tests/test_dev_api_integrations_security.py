"""Security properties of the Settings > Connections integration endpoints.

Once the endpoints work (peregrine#223), test() makes real outbound requests to
addresses a user typed in. On the hosted version that is a server-side request forgery
risk, so address fields must be public https URLs there. Logs and error responses must
never carry exception messages, which can embed webhook tokens.
"""
import os
import stat
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from scripts.integrations.base import IntegrationBase

CALLS: list[dict] = []


class _UrlIntegration(IntegrationBase):
    name = "fake_url"
    label = "Fake URL"
    tier = "paid"

    def __init__(self):
        self._config: dict = {}

    def fields(self) -> list[dict]:
        return [{"key": "webhook_url", "label": "Webhook", "type": "url", "placeholder": "", "required": True, "help": ""}]

    def connect(self, config: dict) -> bool:
        self._config = config
        return bool(config.get("webhook_url"))

    def test(self) -> bool:
        CALLS.append(dict(self._config))
        return True


class _ExplodingIntegration(_UrlIntegration):
    name = "fake_boom"
    label = "Fake Boom"

    def test(self) -> bool:
        raise RuntimeError("connection to https://hooks.example.com/TOKEN-abc123 failed")


@pytest.fixture
def api(monkeypatch, tmp_path):
    import dev_api

    CALLS.clear()
    monkeypatch.setattr("scripts.integrations.REGISTRY", {
        _UrlIntegration.name: _UrlIntegration,
        _ExplodingIntegration.name: _ExplodingIntegration,
    })
    monkeypatch.setattr(dev_api, "_config_dir", lambda: tmp_path)
    monkeypatch.setattr(dev_api, "IS_DEMO", False)
    monkeypatch.setattr(dev_api, "_CLOUD_MODE", False)
    blocked = {"127.0.0.1", "169.254.169.254", "internal.local"}
    monkeypatch.setattr(dev_api, "_is_ssrf_host", lambda host: host in blocked)
    return TestClient(dev_api.app), dev_api, tmp_path


def _go(client, action: str, url: str, integration: str = "fake_url"):
    return client.post(f"/api/settings/system/integrations/{integration}/{action}", json={"webhook_url": url})


@pytest.mark.parametrize("action", ["test", "connect"])
@pytest.mark.parametrize("url", [
    "https://169.254.169.254/latest/meta-data",
    "https://127.0.0.1:8080/hook",
    "https://internal.local/hook",
    "http://hooks.example.com/hook",
    "ftp://hooks.example.com/hook",
    "not a url at all",
])
def test_hosted_version_refuses_internal_and_non_https_addresses(api, monkeypatch, action, url):
    client, dev_api, tmp_path = api
    monkeypatch.setattr(dev_api, "_CLOUD_MODE", True)

    body = _go(client, action, url).json()

    assert body["ok"] is False
    assert "public" in body["error"].lower()
    assert CALLS == [], "nothing may be requested before the address is vetted"
    assert not (tmp_path / "integrations").exists()


def test_hosted_version_allows_a_public_https_address(api, monkeypatch):
    client, dev_api, _ = api
    monkeypatch.setattr(dev_api, "_CLOUD_MODE", True)

    body = _go(client, "test", "https://hooks.example.com/services/abc").json()

    assert body["ok"] is True
    assert len(CALLS) == 1


def test_self_hosted_may_use_lan_addresses(api):
    client, _, _ = api

    body = _go(client, "test", "http://internal.local:8123").json()

    assert body["ok"] is True


def test_test_endpoint_is_blocked_in_demo_mode(api, monkeypatch):
    client, dev_api, _ = api
    monkeypatch.setattr(dev_api, "IS_DEMO", True)

    resp = _go(client, "test", "https://hooks.example.com/x")

    assert resp.status_code == 403
    assert CALLS == []


def test_non_text_values_are_a_400_not_a_crash(api):
    client, _, _ = api

    resp = client.post("/api/settings/system/integrations/fake_url/test", json={"webhook_url": {"a": 1}})

    assert resp.status_code == 400


def test_failures_do_not_leak_exception_text_to_the_client_or_the_log(api):
    client, dev_api, _ = api
    fake_log = MagicMock()

    with patch.object(dev_api, "_log", fake_log):
        resp = _go(client, "test", "https://hooks.example.com/x", integration="fake_boom")

    assert resp.status_code == 500
    assert "TOKEN-abc123" not in resp.text
    logged = str(fake_log.mock_calls)
    assert "TOKEN-abc123" not in logged
    assert "RuntimeError" in logged
    assert "test_integration" in logged


def test_saved_integration_config_is_owner_only(tmp_path):
    _UrlIntegration().save_config({"webhook_url": "https://hooks.example.com/TOKEN"}, tmp_path)

    mode = stat.S_IMODE(os.stat(_UrlIntegration.config_path(tmp_path)).st_mode)

    assert mode == 0o600
