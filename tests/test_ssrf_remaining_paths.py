"""Paths an independent review found still open after the first SSRF fix (peregrine#228, #250).

Each of these sent a request to an address a tenant typed or saved without going through the
guard: the Ollama and vLLM model lists (which return what they read), the Ollama pull, the saved
mail server used by email sync, the CalDAV client's habit of replacing its own session, the
scrapers that still used plain requests, and a browser that resolves and follows links itself.
"""
import http.server
import json
import socket
import sys
import threading
import types
from types import SimpleNamespace
from typing import ClassVar

import pytest
from fastapi.testclient import TestClient

from scripts import safe_net

PUBLIC_V4 = "93.184.216.34"


def _fake_getaddrinfo(table):
    real = socket.getaddrinfo

    def fake(host, port, *args, **kwargs):
        try:
            import ipaddress
            ipaddress.ip_address(host)
            return real(host, port, *args, **kwargs)
        except ValueError:
            pass
        if host not in table:
            raise socket.gaierror("unknown host")
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, port)) for ip in table[host]]

    return fake


class _Services(http.server.BaseHTTPRequestHandler):
    hits: ClassVar[list] = []

    def _reply(self, payload):
        type(self).hits.append((self.command, self.path))
        body = json.dumps(payload).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/api/tags":
            self._reply({"models": [{"name": "internal-model"}]})
        elif self.path == "/v1/models":
            self._reply({"data": [{"id": "internal-id"}]})
        else:
            self._reply({})

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        self.rfile.read(length)
        self._reply({"status": "ok"})

    def log_message(self, *args):
        pass


@pytest.fixture()
def internal():
    _Services.hits = []
    server = http.server.HTTPServer(("127.0.0.1", 0), _Services)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield SimpleNamespace(port=server.server_address[1], base=f"http://127.0.0.1:{server.server_address[1]}")
    server.shutdown()


@pytest.fixture()
def api(monkeypatch, tmp_path):
    import dev_api
    monkeypatch.setattr(dev_api, "IS_DEMO", False)
    monkeypatch.setattr(dev_api, "_config_dir", lambda: tmp_path)
    monkeypatch.setattr(dev_api, "_cred_dir", lambda: tmp_path)
    monkeypatch.setattr(dev_api, "_env_path", lambda: tmp_path / ".env")
    saved = []
    monkeypatch.setattr(dev_api, "_load_wizard_yaml", dict)
    monkeypatch.setattr(dev_api, "_save_wizard_yaml", lambda cfg: saved.append(cfg))
    return SimpleNamespace(client=TestClient(dev_api.app), dev_api=dev_api, saved=saved, dir=tmp_path)


# ── Model lists and the pull: a tenant must not read or poke internal services ─────────────────

def test_self_hosted_model_lists_still_query_a_local_server(api, internal, monkeypatch):
    """The control: the server answers, so the hosted tests below are stopped by the guard."""
    monkeypatch.setattr(api.dev_api, "_CLOUD_MODE", False)

    assert api.client.get(f"/api/settings/llm/ollama-models?host=127.0.0.1&port={internal.port}").json() == {"models": ["internal-model"]}
    assert api.client.get(f"/api/settings/llm/vllm-models?host=127.0.0.1&port={internal.port}").json() == {"models": ["internal-id"]}


def test_hosted_model_lists_cannot_read_an_internal_service(api, internal, monkeypatch):
    monkeypatch.setattr(api.dev_api, "_CLOUD_MODE", True)

    ollama = api.client.get(f"/api/settings/llm/ollama-models?host=127.0.0.1&port={internal.port}").json()
    vllm = api.client.get(f"/api/settings/llm/vllm-models?host=127.0.0.1&port={internal.port}").json()

    assert ollama == {"models": []} and vllm == {"models": []}
    assert _Services.hits == [], "nothing may reach the internal service, and nothing it says may come back"


def test_hosted_model_lists_do_not_follow_the_saved_host_to_an_internal_service(api, internal, monkeypatch):
    monkeypatch.setattr(api.dev_api, "_CLOUD_MODE", True)
    monkeypatch.setattr(api.dev_api, "_configured_ollama_base_url", lambda: internal.base)

    assert api.client.get("/api/settings/llm/ollama-models").json() == {"models": []}
    assert _Services.hits == []


def test_the_hosted_ollama_pull_does_not_post_to_an_internal_service(api, internal, monkeypatch):
    monkeypatch.setattr(api.dev_api, "_CLOUD_MODE", True)
    monkeypatch.setattr(api.dev_api, "_configured_ollama_base_url", lambda: internal.base)

    assert api.client.post("/api/settings/system/ollama-pull", json={"model": "llama3"}).status_code == 200

    assert _Services.hits == []


def test_a_self_hosted_ollama_pull_still_reaches_the_configured_server(api, internal, monkeypatch):
    monkeypatch.setattr(api.dev_api, "_CLOUD_MODE", False)
    monkeypatch.setattr(api.dev_api, "_configured_ollama_base_url", lambda: internal.base)

    api.client.post("/api/settings/system/ollama-pull", json={"model": "llama3"})

    assert _Services.hits == [("POST", "/api/pull")]


# ── Saving an address: refused up front on the hosted version ──────────────────────────────────

@pytest.mark.parametrize("field", ["ollama_host", "vllm_host", "searxng_host"])
def test_hosted_service_hosts_that_are_internal_are_not_saved(api, monkeypatch, field):
    monkeypatch.setattr(api.dev_api, "_CLOUD_MODE", True)
    monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo({}))

    resp = api.client.post("/api/settings/system/llm-backend", json={field: "127.0.0.1"})

    assert resp.status_code == 400
    assert "public" in resp.json()["detail"].lower()
    assert api.saved == [] and not (api.dir / ".env").exists()


def test_hosted_service_hosts_that_are_public_are_saved(api, monkeypatch):
    monkeypatch.setattr(api.dev_api, "_CLOUD_MODE", True)
    monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo({"ollama.example.test": [PUBLIC_V4]}))

    resp = api.client.post("/api/settings/system/llm-backend", json={"ollama_host": "ollama.example.test"})

    assert resp.status_code == 200
    assert api.saved and api.saved[-1]["services"]["ollama_host"] == "ollama.example.test"


def test_self_hosted_service_hosts_on_the_local_network_are_still_saved(api, monkeypatch):
    monkeypatch.setattr(api.dev_api, "_CLOUD_MODE", False)

    resp = api.client.post("/api/settings/system/llm-backend", json={"ollama_host": "192.168.1.50"})

    assert resp.status_code == 200
    assert api.saved[-1]["services"]["ollama_host"] == "192.168.1.50"


def test_a_hosted_orchard_url_that_is_internal_is_not_saved(api, monkeypatch):
    monkeypatch.setattr(api.dev_api, "_CLOUD_MODE", True)

    resp = api.client.post("/api/settings/system/orch-url", json={"orch_url": "http://10.0.0.5:7700"})

    assert resp.status_code == 400
    assert api.saved == []


def test_a_hosted_mail_server_that_is_internal_is_not_saved(api, monkeypatch):
    monkeypatch.setattr(api.dev_api, "_CLOUD_MODE", True)

    resp = api.client.put("/api/settings/system/email", json={"host": "10.0.0.9", "port": 993, "username": "u"})

    assert resp.json()["ok"] is False
    assert not (api.dir / "email.yaml").exists()


# ── Email sync connects with the saved host ────────────────────────────────────────────────────

def test_hosted_email_sync_will_not_connect_to_an_internal_host(monkeypatch):
    monkeypatch.setenv("CLOUD_MODE", "true")
    monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo({"mail.example.test": ["10.0.0.9"]}))
    monkeypatch.setattr(socket, "create_connection", lambda *a, **k: pytest.fail("must not connect"))
    from scripts import imap_sync

    with pytest.raises(safe_net.BlockedAddress):
        imap_sync.connect({"host": "mail.example.test", "port": 993, "username": "u", "password": "p"})


def test_hosted_email_sync_uses_the_pinned_classes(monkeypatch):
    monkeypatch.setenv("CLOUD_MODE", "true")
    made = []

    class FakePinned:
        def __init__(self, host, port, **kwargs):
            made.append((host, port, kwargs.get("timeout")))

        def login(self, user, password):
            return ("OK", [])

    monkeypatch.setattr(safe_net, "PinnedIMAP4_SSL", FakePinned)
    from scripts import imap_sync

    imap_sync.connect({"host": "mail.example.test", "port": 993, "username": "u", "password": "p"})

    assert made == [("mail.example.test", 993, imap_sync._IMAP_CONNECT_TIMEOUT_SECONDS)]


# ── CalDAV: its client replaces its own session, so the hosted version does not use it ─────────

def test_hosted_caldav_is_refused_and_never_creates_a_client(monkeypatch):
    """caldav swaps in an unguarded session of its own after repeated 401 answers, so replacing the
    session is not a guard. It also is not installed in the hosted image, so nothing is lost."""
    monkeypatch.setenv("CLOUD_MODE", "true")
    created = []

    class DAVClient:
        def __init__(self, **kwargs):
            created.append(kwargs)

    module = types.ModuleType("caldav")
    module.DAVClient = DAVClient
    monkeypatch.setitem(sys.modules, "caldav", module)
    from scripts.integrations.apple_calendar import AppleCalendarIntegration
    integration = AppleCalendarIntegration()
    integration.connect({"caldav_url": "https://caldav.example.test/", "username": "u", "app_password": "p"})

    assert integration.test() is False
    assert created == []


# ── Scrapers that still used plain requests ────────────────────────────────────────────────────

class _FakeSafeSession:
    used: ClassVar[list] = []

    def get(self, url, **kwargs):
        type(self).used.append(url)
        return SimpleNamespace(
            text="<html></html>", status_code=200, raise_for_status=lambda: None,
            json=lambda: {"title": "T", "company_name": "C", "location": {"name": "Remote"}, "content": "&lt;p&gt;hi&lt;/p&gt;"},
        )


@pytest.fixture()
def hosted_scraper(monkeypatch):
    import scripts.scrape_url as scrape
    monkeypatch.setenv("CLOUD_MODE", "true")
    _FakeSafeSession.used = []
    monkeypatch.setattr(scrape.safe_net, "SafeSession", _FakeSafeSession)
    monkeypatch.setattr(scrape.requests, "get", lambda *a, **k: pytest.fail("the hosted version must not use plain requests.get"))
    return scrape


@pytest.mark.parametrize("function,url", [
    ("_scrape_indeed", "https://www.indeed.com/viewjob?jk=abc"),
    ("_scrape_linkedin", "https://www.linkedin.com/jobs/view/123456/"),
    ("_scrape_greenhouse", "https://job-boards.greenhouse.io/acme/jobs/123"),
])
def test_the_hosted_board_scrapers_fetch_through_the_safe_session(hosted_scraper, function, url):
    getattr(hosted_scraper, function)(url)

    assert _FakeSafeSession.used, f"{function} made no request through the safe session"


def test_oracle_hcm_needs_the_hcmui_path_not_just_the_word_in_the_query():
    from scripts.scrape_url import _detect_board

    assert _detect_board("https://bucket.objectstorage.oraclecloud.com/page.html?hcmui=1") == "generic"
    assert _detect_board("https://acme.fa.us2.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX/job/1") == "oracle_hcm"


# ── The browser resolves names and follows links itself ────────────────────────────────────────

class _FakeContext:
    def __init__(self):
        self.routes = []

    def route(self, pattern, handler):
        self.routes.append((pattern, handler))

    def route_web_socket(self, pattern, handler):
        self.web_socket_routes = [*getattr(self, "web_socket_routes", []), (pattern, handler)]


class _FakeRoute:
    def __init__(self, url):
        # Sub-resource requests only. Navigation redirects are covered against a real browser in
        # test_scrape_browser_guard.py.
        self.request = SimpleNamespace(url=url, is_navigation_request=lambda: False)
        self.outcome = None

    def abort(self, *args):
        self.outcome = "abort"

    def continue_(self, *args, **kwargs):
        self.outcome = "continue"


def test_the_hosted_browser_aborts_requests_to_non_public_addresses(monkeypatch):
    monkeypatch.setenv("CLOUD_MODE", "true")
    monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo({"jobs.example.test": [PUBLIC_V4], "evil.example.test": ["10.0.0.5"]}))
    from scripts.scrape_url import _guard_browser_context
    context = _FakeContext()

    _guard_browser_context(context)

    assert [pattern for pattern, _ in context.routes] == ["**/*"]
    handler = context.routes[0][1]
    outcomes = {}
    for url in ("https://jobs.example.test/a", "https://evil.example.test/b", "http://169.254.169.254/latest", "http://127.0.0.1:8601/x", "file:///etc/passwd"):
        route = _FakeRoute(url)
        handler(route)
        outcomes[url] = route.outcome
    assert outcomes == {
        "https://jobs.example.test/a": "continue",
        "https://evil.example.test/b": "abort",
        "http://169.254.169.254/latest": "abort",
        "http://127.0.0.1:8601/x": "abort",
        "file:///etc/passwd": "abort",
    }


def test_the_self_hosted_browser_is_left_alone(monkeypatch):
    monkeypatch.delenv("CLOUD_MODE", raising=False)
    from scripts.scrape_url import _guard_browser_context
    context = _FakeContext()

    _guard_browser_context(context)

    assert context.routes == []


# ── One definition of "hosted" ─────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("value,expected", [("true", True), ("TRUE", True), ("1", True), ("yes", True), (" true ", True), ("", False), ("0", False), ("false", False), ("no", False)])
def test_the_hosted_flag_is_read_one_way_everywhere(monkeypatch, value, expected):
    monkeypatch.setenv("CLOUD_MODE", value)

    assert safe_net.cloud_mode() is expected
    import dev_api
    assert dev_api._cloud_mode_from_env() is expected
