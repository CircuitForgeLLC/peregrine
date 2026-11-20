"""The hosted browser scrapers against a real Chromium (peregrine#228, #250).

An independent review showed that checking each request the page starts is not enough: Chromium
follows redirects on its own without asking again, and WebSockets never reach the request handler.
A page on a board's host could therefore be redirected, or script itself, into an internal service.
These start two local servers, one standing in for the public site and one for an internal service
that must never be reached, and drive the real browser through the guard.
"""
import contextlib
import http.server
import socket
import threading
import time
from typing import ClassVar

import pytest

pytest.importorskip("playwright.sync_api")

from scripts import safe_net
from scripts import scrape_url as scrape

PUBLIC_HOST = "127.0.0.2"  # stands in for a public address, the guard is told it is one below


def _can_bind(host):
    try:
        probe = socket.socket()
        probe.bind((host, 0))
        probe.close()
        return True
    except OSError:
        return False


pytestmark = pytest.mark.skipif(not _can_bind(PUBLIC_HOST), reason="needs a second loopback address")


class _Internal(http.server.BaseHTTPRequestHandler):
    hits: ClassVar[list] = []

    def do_GET(self):
        type(self).hits.append(self.path)
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(b"INTERNAL SECRET")

    def log_message(self, *args):
        pass


@pytest.fixture()
def world(monkeypatch):
    monkeypatch.setenv("CLOUD_MODE", "true")
    real = safe_net.is_public_ip
    monkeypatch.setattr(safe_net, "is_public_ip", lambda value: str(value) == PUBLIC_HOST or (str(value) != "127.0.0.1" and real(value)))

    _Internal.hits = []
    internal = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Internal)
    internal_port = internal.server_address[1]
    threading.Thread(target=internal.serve_forever, daemon=True).start()

    websocket_attempts = []
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(5)
    ws_port = listener.getsockname()[1]

    def accept():
        while True:
            try:
                conn, _ = listener.accept()
            except OSError:
                return
            websocket_attempts.append("connected")
            conn.close()

    threading.Thread(target=accept, daemon=True).start()

    page_html = (
        "<html><body><script>"
        f"fetch('http://127.0.0.1:{internal_port}/fetch').catch(e=>{{}});"
        f"try{{new WebSocket('ws://127.0.0.1:{ws_port}/')}}catch(e){{}};"
        "</script>PUBLIC PAGE</body></html>"
    ).encode()

    class Public(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/redir":
                self.send_response(302)
                self.send_header("Location", f"http://127.0.0.1:{internal_port}/redir-hit")
                self.end_headers()
            elif self.path == "/hop":
                self.send_response(302)
                self.send_header("Location", "/ok")
                self.end_headers()
            elif self.path == "/ok":
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.end_headers()
                self.wfile.write(b"<html><body>OK-PAGE</body></html>")
            else:
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.end_headers()
                self.wfile.write(page_html)

        def log_message(self, *args):
            pass

    public = http.server.ThreadingHTTPServer((PUBLIC_HOST, 0), Public)
    threading.Thread(target=public.serve_forever, daemon=True).start()
    yield type("World", (), {"public": f"http://{PUBLIC_HOST}:{public.server_address[1]}", "ws": websocket_attempts})
    public.shutdown()
    internal.shutdown()
    listener.close()


@pytest.fixture()
def guarded_page():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch()
        except Exception as exc:  # noqa: BLE001 - no browser installed here means these cannot run
            pytest.skip(f"Chromium is not available: {exc}")
        context = browser.new_context()
        scrape._guard_browser_context(context)
        yield context.new_page()
        browser.close()


def test_a_redirect_from_a_public_page_to_an_internal_address_is_not_followed(world, guarded_page):
    # An aborted navigation raising is the expected outcome, so it is suppressed.
    with contextlib.suppress(Exception):
        guarded_page.goto(world.public + "/redir", timeout=8000)
    time.sleep(0.5)

    assert _Internal.hits == [], "the internal server must never receive the redirected request"
    assert "INTERNAL SECRET" not in guarded_page.content()
    assert "127.0.0.1" not in guarded_page.url


def test_a_redirect_between_public_addresses_still_works(world, guarded_page):
    guarded_page.goto(world.public + "/hop", timeout=8000)

    assert "OK-PAGE" in guarded_page.content()


def test_a_page_script_cannot_open_a_websocket_to_an_internal_address(world, guarded_page):
    guarded_page.goto(world.public + "/", timeout=8000)
    time.sleep(1.5)

    assert world.ws == [], "the internal listener must never see a WebSocket connection"


def test_a_page_script_cannot_fetch_an_internal_address(world, guarded_page):
    guarded_page.goto(world.public + "/", timeout=8000)
    time.sleep(1.0)

    assert "/fetch" not in _Internal.hits


def test_an_ordinary_public_page_loads(world, guarded_page):
    guarded_page.goto(world.public + "/", timeout=8000)

    assert "PUBLIC PAGE" in guarded_page.content()


def test_the_final_url_check_catches_a_page_that_ended_up_somewhere_internal(monkeypatch):
    monkeypatch.setenv("CLOUD_MODE", "true")
    monkeypatch.setattr(socket, "getaddrinfo", lambda host, port, *a, **k: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.5", port))])

    assert scrape._page_left_public_web(type("Page", (), {"url": "https://evil.example.test/x"})()) is True
    assert scrape._page_left_public_web(type("Page", (), {"url": "http://127.0.0.1:8601/x"})()) is True


def test_the_final_url_check_does_nothing_self_hosted(monkeypatch):
    monkeypatch.delenv("CLOUD_MODE", raising=False)

    assert scrape._page_left_public_web(type("Page", (), {"url": "http://192.168.1.5/x"})()) is False
