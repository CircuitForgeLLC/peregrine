"""Integration and connection tests must not be aimable at the internal network (peregrine#228).

The address check done when a URL is saved is not enough: the name can resolve somewhere else when
the request is made (DNS rebinding), a redirect can lead somewhere internal, and AAAA records and
multi-record hosts were never looked at. These cover the request side, for every integration that
sends to an address the user typed, plus the mail and connectivity tests.
"""
import http.server
import socket
import sys
import threading
import types
from typing import ClassVar

import pytest
from fastapi.testclient import TestClient

from scripts import safe_net

PUBLIC_V4 = "93.184.216.34"


def _fake_getaddrinfo(table):
    real = socket.getaddrinfo
    asked = []

    def fake(host, port, *args, **kwargs):
        try:
            import ipaddress
            ipaddress.ip_address(host)
            return real(host, port, *args, **kwargs)
        except ValueError:
            pass
        asked.append(host)
        if host not in table:
            raise socket.gaierror("unknown host")
        return [(socket.AF_INET6 if ":" in ip else socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, port)) for ip in table[host]]

    fake.asked = asked
    return fake


# ── The resolver behind dev_api._is_ssrf_host ──────────────────────────────────────────────────

def test_is_ssrf_host_blocks_a_name_with_an_internal_ipv6_record(monkeypatch):
    import dev_api
    monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo({"dual.example.test": [PUBLIC_V4, "fd00::5"]}))

    assert dev_api._is_ssrf_host("dual.example.test") is True


def test_is_ssrf_host_blocks_a_name_with_any_internal_record(monkeypatch):
    import dev_api
    monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo({"multi.example.test": [PUBLIC_V4, "10.0.0.8"]}))

    assert dev_api._is_ssrf_host("multi.example.test") is True


@pytest.mark.parametrize("host", ["localhost", "127.0.0.1", "::1", "169.254.169.254", "100.64.0.1", "0.0.0.0", "2130706433"])
def test_is_ssrf_host_blocks_internal_addresses_in_any_spelling(host):
    import dev_api

    assert dev_api._is_ssrf_host(host) is True


def test_is_ssrf_host_fails_closed_when_the_name_does_not_resolve(monkeypatch):
    import dev_api
    monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo({}))

    assert dev_api._is_ssrf_host("nothing.example.test") is True


def test_is_ssrf_host_allows_a_public_name(monkeypatch):
    import dev_api
    monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo({"hooks.example.test": [PUBLIC_V4]}))

    assert dev_api._is_ssrf_host("hooks.example.test") is False


# ── Integrations that send to an address the user typed ────────────────────────────────────────

class _Internal(http.server.BaseHTTPRequestHandler):
    hits: ClassVar[list] = []

    def _answer(self, status):
        type(self).hits.append((self.command, self.path))
        self.send_response(status)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_POST(self):
        self._answer(200)  # Slack wants exactly 200, Discord accepts 200 or 204

    def do_GET(self):
        self._answer(200)

    def do_PROPFIND(self):
        self._answer(207)

    def log_message(self, *args):
        pass


@pytest.fixture()
def internal_server():
    _Internal.hits = []
    server = http.server.HTTPServer(("127.0.0.1", 0), _Internal)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


def _discord(base):
    from scripts.integrations.discord import DiscordIntegration
    integration = DiscordIntegration()
    integration.connect({"webhook_url": base + "/api/webhooks/1/abc"})
    return integration


def _slack(base):
    from scripts.integrations.slack import SlackIntegration
    integration = SlackIntegration()
    integration.connect({"webhook_url": base + "/services/T/B/x"})
    return integration


def _home_assistant(base):
    from scripts.integrations.home_assistant import HomeAssistantIntegration
    integration = HomeAssistantIntegration()
    integration.connect({"base_url": base, "token": "t"})
    return integration


def _nextcloud(base):
    from scripts.integrations.nextcloud import NextcloudIntegration
    integration = NextcloudIntegration()
    integration.connect({"host": base, "username": "u", "password": "p", "folder_path": ""})
    return integration


BUILDERS = [_discord, _slack, _home_assistant, _nextcloud]


@pytest.mark.parametrize("build", BUILDERS, ids=lambda b: b.__name__)
def test_self_hosted_integrations_still_reach_a_local_address(build, internal_server, monkeypatch):
    """The control: the server really answers, so the hosted tests below are blocked by the guard."""
    monkeypatch.delenv("CLOUD_MODE", raising=False)

    assert build(internal_server).test() is True
    assert _Internal.hits


@pytest.mark.parametrize("build", BUILDERS, ids=lambda b: b.__name__)
def test_hosted_integrations_cannot_reach_an_internal_address(build, internal_server, monkeypatch):
    monkeypatch.setenv("CLOUD_MODE", "true")

    assert build(internal_server).test() is False
    assert _Internal.hits == [], "the internal server must never see a request"


def test_a_hosted_integration_cannot_be_rebound_to_an_internal_address(internal_server, monkeypatch):
    """The name looks public when it is checked and internal on any later lookup."""
    monkeypatch.setenv("CLOUD_MODE", "true")
    fake = _fake_getaddrinfo({"rebind.example.test": [PUBLIC_V4]})
    flips = {"count": 0}

    def rebinding(host, port, *args, **kwargs):
        if host == "rebind.example.test":
            flips["count"] += 1
            return fake(host, port, *args, **kwargs) if flips["count"] == 1 else [
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", port))]
        return fake(host, port, *args, **kwargs)

    monkeypatch.setattr(socket, "getaddrinfo", rebinding)
    port = int(internal_server.rsplit(":", 1)[1])

    result = _discord(f"http://rebind.example.test:{port}").test()

    assert result is False
    assert _Internal.hits == []
    assert flips["count"] == 1, "the name must be looked up once, not again at connect time"


# ── CalDAV (its client keeps its own session) ──────────────────────────────────────────────────

@pytest.fixture()
def fake_caldav(monkeypatch):
    made = []

    class DAVClient:
        def __init__(self, url, username, password):
            self.session = object()
            self.original_session = self.session
            made.append(self)

        def principal(self):
            return object()

    module = types.ModuleType("caldav")
    module.DAVClient = DAVClient
    monkeypatch.setitem(sys.modules, "caldav", module)
    return made


def _apple():
    from scripts.integrations.apple_calendar import AppleCalendarIntegration
    integration = AppleCalendarIntegration()
    integration.connect({"caldav_url": "https://caldav.example.test/", "username": "u", "app_password": "p"})
    return integration


def test_self_hosted_caldav_keeps_its_own_session(fake_caldav, monkeypatch):
    """Self-hosted CalDAV is untouched. The hosted version refuses CalDAV outright (see
    test_ssrf_remaining_paths.py): the client replaces its own session after repeated 401 answers,
    so swapping in a guarded session is not a guard."""
    monkeypatch.delenv("CLOUD_MODE", raising=False)

    assert _apple().test() is True
    assert fake_caldav[0].session is fake_caldav[0].original_session


# ── Mail server test ───────────────────────────────────────────────────────────────────────────

def test_the_imap_test_connects_to_the_address_it_checked_after_one_lookup(monkeypatch):
    from scripts.safe_net import PinnedIMAP4_SSL
    fake = _fake_getaddrinfo({"mail.example.test": [PUBLIC_V4]})
    monkeypatch.setattr(socket, "getaddrinfo", fake)
    seen = []

    def refuse(address, timeout=None, *args, **kwargs):
        seen.append(address)
        raise OSError("no network in tests")

    monkeypatch.setattr(socket, "create_connection", refuse)

    with pytest.raises(OSError):
        PinnedIMAP4_SSL("mail.example.test", 993, timeout=5)

    assert seen == [(PUBLIC_V4, 993)]
    assert fake.asked == ["mail.example.test"]


def test_the_imap_test_will_not_connect_to_a_name_that_resolves_internally(monkeypatch):
    from scripts.safe_net import PinnedIMAP4_SSL
    monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo({"mail.example.test": ["10.0.0.9"]}))
    monkeypatch.setattr(socket, "create_connection", lambda *a, **k: pytest.fail("must not connect"))

    with pytest.raises(safe_net.BlockedAddress):
        PinnedIMAP4_SSL("mail.example.test", 993, timeout=5)


# ── Saving an address (the check made when it is typed) ────────────────────────────────────────

class _UrlOnly:
    def fields(self):
        return [{"key": "webhook_url", "type": "url"}]


def test_a_hosted_address_with_credentials_in_it_is_refused(monkeypatch):
    import dev_api
    monkeypatch.setattr(dev_api, "_CLOUD_MODE", True)
    monkeypatch.setattr(dev_api, "_is_ssrf_host", lambda host: False)

    message = dev_api._vet_integration_payload(_UrlOnly(), {"webhook_url": "https://user:pw@hooks.example.test/x"})

    assert message and "public" in message.lower()


def test_a_plain_public_https_address_still_passes(monkeypatch):
    import dev_api
    monkeypatch.setattr(dev_api, "_CLOUD_MODE", True)
    monkeypatch.setattr(dev_api, "_is_ssrf_host", lambda host: False)

    assert dev_api._vet_integration_payload(_UrlOnly(), {"webhook_url": "https://hooks.example.test/x"}) is None


# ── Orchard and Ollama connection tests ────────────────────────────────────────────────────────

@pytest.fixture()
def wizard_client(monkeypatch):
    import dev_api
    monkeypatch.setattr(dev_api, "_CLOUD_MODE", True)
    monkeypatch.setattr(dev_api, "_is_ssrf_host", lambda host: False)
    return TestClient(dev_api.app)


def test_hosted_orchard_and_ollama_tests_go_through_the_safe_session(wizard_client, monkeypatch):
    import dev_api
    used = []

    class FakeSafeSession:
        def get(self, url, **kwargs):
            used.append(url)
            return types.SimpleNamespace(status_code=200, json=lambda: {"nodes": []})

    monkeypatch.setattr(dev_api.safe_net, "SafeSession", FakeSafeSession)
    monkeypatch.setattr(dev_api.requests, "get", lambda *a, **k: pytest.fail("hosted requests must not use plain requests.get"))

    orch = wizard_client.post("/api/wizard/inference/test", json={"profile": "cf-orch", "orch_url": "https://orch.example.test"})
    ollama = wizard_client.post("/api/wizard/inference/test", json={"profile": "cpu", "ollama_host": "ollama.example.test", "ollama_port": 11434})

    assert orch.json()["ok"] is True and ollama.json()["ok"] is True
    assert len(used) == 2
