"""Safe outbound networking for the hosted version (peregrine#228, #250).

The hosted API container can reach the internal network, so any request built from an address a
tenant typed has to be unable to land there: not by a private address, not by a name that resolves
to one, not by a name whose answer changes between the check and the connect (DNS rebinding), and
not by a redirect. Self-hosted installs are deliberately unaffected.
"""
import http.server
import io
import socket
import threading
from typing import ClassVar

import pytest
import requests
from urllib3.connection import HTTPConnection

from scripts import safe_net
from scripts.safe_net import (
    BlockedAddress,
    BlockedRedirect,
    SafeSession,
    is_public_ip,
    resolve_public,
)

PUBLIC_V4 = "93.184.216.34"


def _fake_getaddrinfo(answers):
    """getaddrinfo that answers for named hosts from `answers` (a list per call, last repeats) and
    passes IP literals straight through, like the real one. Records the names it was asked for."""
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
        ips = answers[min(len(asked) - 1, len(answers) - 1)]
        return [(socket.AF_INET6 if ":" in ip else socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, port)) for ip in ips]

    fake.asked = asked
    return fake


# ── Which addresses count as public ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("ip", ["8.8.8.8", PUBLIC_V4, "1.1.1.1", "2606:4700:4700::1111", "::ffff:8.8.8.8"])
def test_public_addresses_are_allowed(ip):
    assert is_public_ip(ip)


@pytest.mark.parametrize("ip", [
    "127.0.0.1", "127.255.255.254", "10.0.0.1", "10.255.255.255", "172.16.0.1", "172.31.255.255",
    "192.168.1.1", "169.254.169.254", "169.254.0.1", "100.64.0.1", "100.100.100.200", "0.0.0.0",
    "224.0.0.1", "239.255.255.255", "240.0.0.1", "255.255.255.255", "198.18.0.1", "192.0.0.1",
    "192.0.2.1", "198.51.100.1", "203.0.113.1",
    "::1", "::", "fe80::1", "fc00::1", "fd00::1", "fd00:ec2::254", "fec0::1", "ff02::1", "2001:db8::1",
    "::ffff:10.0.0.1", "::ffff:127.0.0.1", "::ffff:169.254.169.254",
    "2002:0a00:0001::1",        # 6to4 wrapping 10.0.0.1
    "2001:0:4136:e378:8000:63bf:3fff:fdd2",   # Teredo
    "64:ff9b::a00:1",          # NAT64 wrapping 10.0.0.1
    "fe80::1%eth0",            # link-local with a zone id
])
def test_internal_and_special_addresses_are_blocked(ip):
    assert not is_public_ip(ip)


def test_garbage_is_not_public():
    assert not is_public_ip("not-an-ip")
    assert not is_public_ip("")


# ── Resolving a name ───────────────────────────────────────────────────────────────────────────

def test_a_name_with_only_public_answers_is_returned(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo([[PUBLIC_V4, "2606:4700:4700::1111"]]))

    assert resolve_public("api.example.test", 443) == [PUBLIC_V4, "2606:4700:4700::1111"]


def test_one_internal_answer_among_public_ones_blocks_the_whole_name(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo([[PUBLIC_V4, "10.0.0.5"]]))

    with pytest.raises(BlockedAddress):
        resolve_public("mixed.example.test", 443)


def test_an_internal_ipv6_answer_blocks_the_name_even_with_a_public_ipv4(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo([[PUBLIC_V4, "fd00::1"]]))

    with pytest.raises(BlockedAddress):
        resolve_public("dual.example.test", 443)


def test_a_name_that_does_not_resolve_fails_closed(monkeypatch):
    def boom(*args, **kwargs):
        raise socket.gaierror("no such host")

    monkeypatch.setattr(socket, "getaddrinfo", boom)

    with pytest.raises(BlockedAddress):
        resolve_public("nope.example.test", 443)


@pytest.mark.parametrize("host", ["localhost", "127.0.0.1", "::1", "[::1]", "0.0.0.0", "2130706433", "0x7f000001", "127.1"])
def test_loopback_in_any_spelling_is_blocked(host):
    with pytest.raises(BlockedAddress):
        resolve_public(host, 80)


@pytest.mark.parametrize("host", ["", " ", "a b", "evil.test/path", "user@evil.test", "evil.test?x=1", "evil.test#x"])
def test_a_host_that_is_not_a_plain_name_is_refused(host):
    with pytest.raises(BlockedAddress):
        resolve_public(host, 443)


# ── Connecting: one lookup, and the vetted address is what gets used ───────────────────────────

def test_create_connection_connects_to_the_vetted_address_after_a_single_lookup(monkeypatch):
    fake = _fake_getaddrinfo([[PUBLIC_V4]])
    monkeypatch.setattr(socket, "getaddrinfo", fake)
    connected = []
    sentinel = object()
    monkeypatch.setattr(socket, "create_connection", lambda address, timeout=None, **kw: connected.append(address) or sentinel)

    assert safe_net.create_connection(("api.example.test", 443), 5) is sentinel

    assert connected == [(PUBLIC_V4, 443)]
    assert fake.asked == ["api.example.test"]


def test_dns_rebinding_cannot_swap_in_an_internal_address_between_check_and_connect(monkeypatch):
    """The first answer is public, any later answer is loopback. Only one lookup is made, so the
    connection can only go to the public address that was checked."""
    fake = _fake_getaddrinfo([[PUBLIC_V4], ["127.0.0.1"]])
    monkeypatch.setattr(socket, "getaddrinfo", fake)
    connected = []
    monkeypatch.setattr(socket, "create_connection", lambda address, timeout=None, **kw: connected.append(address) or object())

    safe_net.create_connection(("rebind.example.test", 443), 5)

    assert connected == [(PUBLIC_V4, 443)]
    assert len(fake.asked) == 1


def test_create_connection_refuses_an_internal_name_without_connecting(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo([["10.1.2.3"]]))
    monkeypatch.setattr(socket, "create_connection", lambda *a, **k: pytest.fail("must not connect"))

    with pytest.raises(BlockedAddress):
        safe_net.create_connection(("internal.example.test", 443), 5)


# ── requests sessions ──────────────────────────────────────────────────────────────────────────

class _Recorder(http.server.BaseHTTPRequestHandler):
    hits: ClassVar[list] = []

    def do_GET(self):
        type(self).hits.append(self.path)
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"internal secret")

    def log_message(self, *args):
        pass


@pytest.fixture()
def loopback_server():
    _Recorder.hits = []
    server = http.server.HTTPServer(("127.0.0.1", 0), _Recorder)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server
    server.shutdown()


def test_a_safe_session_cannot_reach_a_loopback_server_by_address(loopback_server):
    port = loopback_server.server_address[1]

    with pytest.raises(requests.ConnectionError):
        SafeSession().get(f"http://127.0.0.1:{port}/admin", timeout=3)

    assert _Recorder.hits == []


def test_a_safe_session_cannot_reach_a_loopback_server_through_a_name(loopback_server, monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo([["127.0.0.1"]]))
    port = loopback_server.server_address[1]

    with pytest.raises(requests.ConnectionError):
        SafeSession().get(f"http://sneaky.example.test:{port}/admin", timeout=3)

    assert _Recorder.hits == []


def test_a_plain_session_still_reaches_a_loopback_server(loopback_server):
    """The control: the server really is reachable, so the two tests above are blocked by the
    guard and not by a broken fixture."""
    port = loopback_server.server_address[1]

    assert requests.get(f"http://127.0.0.1:{port}/", timeout=3).text == "internal secret"


def test_the_pinned_connection_uses_the_checked_address_not_a_second_lookup(monkeypatch):
    """Watch the socket itself, so this holds for any urllib3 internals. The first answer is public
    and any later answer would be loopback: the name is looked up once and only the public address
    is ever connected to."""
    fake = _fake_getaddrinfo([[PUBLIC_V4], ["127.0.0.1"]])
    monkeypatch.setattr(socket, "getaddrinfo", fake)
    seen = []

    def refuse_connect(self, address, *args):
        seen.append(address)
        raise OSError("no network in tests")

    def refuse_connect_ex(self, address, *args):
        seen.append(address)
        return 111

    monkeypatch.setattr(socket.socket, "connect", refuse_connect)
    monkeypatch.setattr(socket.socket, "connect_ex", refuse_connect_ex)

    with pytest.raises(requests.ConnectionError):
        SafeSession().get("https://rebind.example.test/hook", timeout=3)

    assert seen, "the request never tried to connect, so this test proves nothing"
    assert {address[:2] for address in seen} == {(PUBLIC_V4, 443)}
    assert fake.asked == ["rebind.example.test"]


def test_the_urllib3_internal_the_pinning_relies_on_still_exists():
    """If a urllib3 upgrade removes this, fail loudly here instead of silently connecting unpinned."""
    assert HTTPConnection("example.test", 80)._dns_host == "example.test"


# ── Redirects ──────────────────────────────────────────────────────────────────────────────────

class _Script(requests.adapters.BaseAdapter):
    """Answers each URL from a table, so redirect handling is tested without any network."""

    def __init__(self, table):
        super().__init__()
        self.table = table
        self.requested = []

    def send(self, request, **kwargs):
        self.requested.append(request.url)
        status, location = self.table[request.url]
        response = requests.Response()
        response.status_code = status
        response.url = request.url
        response.request = request
        response.raw = io.BytesIO(b"")
        response._content = b""
        if location:
            response.headers["Location"] = location
        return response

    def close(self):
        pass


def _scripted_session(table):
    session = SafeSession()
    adapter = _Script(table)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session, adapter


def test_an_https_redirect_to_another_https_address_is_followed():
    session, adapter = _scripted_session({
        "https://a.example.test/start": (302, "https://b.example.test/next"),
        "https://b.example.test/next": (200, None),
    })

    assert session.get("https://a.example.test/start").status_code == 200
    assert adapter.requested == ["https://a.example.test/start", "https://b.example.test/next"]


def test_a_redirect_down_to_http_is_refused_before_it_is_requested():
    session, adapter = _scripted_session({"https://a.example.test/start": (302, "http://10.0.0.5/internal")})

    with pytest.raises(BlockedRedirect):
        session.get("https://a.example.test/start")

    assert adapter.requested == ["https://a.example.test/start"]


def test_a_relative_redirect_is_resolved_against_the_current_address():
    session, _ = _scripted_session({
        "https://a.example.test/dav/folder": (301, "/dav/folder/"),
        "https://a.example.test/dav/folder/": (207, None),
    })

    assert session.get("https://a.example.test/dav/folder").status_code == 207


def test_a_long_redirect_chain_is_cut_off():
    table = {f"https://a.example.test/{i}": (302, f"https://a.example.test/{i + 1}") for i in range(10)}
    table["https://a.example.test/10"] = (200, None)
    session, _ = _scripted_session(table)

    with pytest.raises(requests.TooManyRedirects):
        session.get("https://a.example.test/0")


# ── When it applies ────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("value", ["1", "true", "TRUE", "yes"])
def test_the_hosted_version_gets_the_safe_session(monkeypatch, value):
    monkeypatch.setenv("CLOUD_MODE", value)

    assert isinstance(safe_net.http_session(), SafeSession)


@pytest.mark.parametrize("value", ["", "0", "false", "no"])
def test_a_self_hosted_install_gets_a_plain_session_that_can_reach_the_lan(monkeypatch, value):
    monkeypatch.setenv("CLOUD_MODE", value)

    session = safe_net.http_session()
    assert type(session) is requests.Session


def test_a_safe_session_ignores_proxy_environment_variables(monkeypatch):
    monkeypatch.setenv("HTTPS_PROXY", "http://proxy.internal:3128")

    assert SafeSession().trust_env is False


# ── Checking an address when it is typed ───────────────────────────────────────────────────────

def test_a_public_https_address_passes(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo([[PUBLIC_V4]]))

    assert safe_net.public_url_error("https://hooks.example.test/services/abc") is None


@pytest.mark.parametrize("url", [
    "", "   ", "not a url", "https://", "ftp://example.test/x", "javascript:alert(1)",
    "http://hooks.example.test/x",          # https only by default
    "https://user:pw@hooks.example.test/x",  # userinfo is never needed and confuses parsers
    "https://localhost/x", "https://127.0.0.1/x", "https://[::1]/x", "https://10.0.0.5/x",
    "https://169.254.169.254/latest/meta-data/",
])
def test_unsafe_or_malformed_addresses_are_rejected(url):
    assert safe_net.public_url_error(url) is not None


def test_a_name_that_resolves_to_an_internal_address_is_rejected(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo([["192.168.0.10"]]))

    assert safe_net.public_url_error("https://innocent.example.test/") is not None


def test_http_can_be_allowed_for_job_links(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo([[PUBLIC_V4]]))

    assert safe_net.public_url_error("http://jobs.example.test/post/1", schemes=("http", "https")) is None
