"""Job links must not be able to aim the server at its own network (peregrine#250).

Add-by-URL and CSV import accepted anything starting with http, the scraper fetched it from inside
the hosted API container, and `_detect_board` chose a browser-driven scraper by finding a board's
name anywhere in the URL, so another host could be routed to one by putting that name in its path.
"""
import http.server
import socket
import sqlite3
import threading
from types import SimpleNamespace
from typing import ClassVar

import pytest
from fastapi.testclient import TestClient

PUBLIC_V4 = "93.184.216.34"
JSON_LD_PAGE = (
    b'<html><head><script type="application/ld+json">'
    b'{"@type": "JobPosting", "title": "Internal Admin", "description": "secret internal page",'
    b' "hiringOrganization": {"name": "Internal"}}</script></head></html>'
)


def _fake_getaddrinfo(table):
    """Names in `table` resolve as listed, IP literals pass through, anything else does not resolve."""
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


# ── Board detection looks at the host, not the whole URL ───────────────────────────────────────

@pytest.mark.parametrize("url,board", [
    ("https://www.linkedin.com/jobs/view/123456/", "linkedin"),
    ("https://uk.linkedin.com/jobs/view/123456/", "linkedin"),
    ("https://www.indeed.com/viewjob?jk=abc", "indeed"),
    ("https://ca.indeed.com/viewjob?jk=abc", "indeed"),
    ("https://www.glassdoor.com/job-listing/x", "glassdoor"),
    ("https://jobgether.com/offer/abc-title---acme", "jobgether"),
    ("https://www.theladders.com/job/x", "theladders"),
    ("https://acme.fa.us2.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX/job/1", "oracle_hcm"),
    ("https://job-boards.greenhouse.io/acme/jobs/123", "greenhouse"),
])
def test_real_board_hosts_are_still_recognised(url, board):
    from scripts.scrape_url import _detect_board

    assert _detect_board(url) == board


@pytest.mark.parametrize("url", [
    "http://169.254.169.254/?x=jobgether.com",
    "https://evil.test/linkedin.com/jobs/view/123456/",
    "https://evil.test/?next=indeed.com",
    "https://notlinkedin.com/jobs/view/123456/",
    "https://linkedin.com.evil.test/jobs/view/123456/",
    "https://evil.test/hcmUI/oraclecloud.com",
    "https://evil.test/#theladders.com",
    "https://user@linkedin.com@evil.test/",
])
def test_another_host_that_merely_contains_a_board_name_is_not_that_board(url):
    from scripts.scrape_url import _detect_board

    assert _detect_board(url) == "generic"


# ── Scraping ───────────────────────────────────────────────────────────────────────────────────

class _Page(http.server.BaseHTTPRequestHandler):
    hits: ClassVar[list] = []

    def do_GET(self):
        type(self).hits.append(self.path)
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(JSON_LD_PAGE)

    def log_message(self, *args):
        pass


@pytest.fixture()
def internal_page():
    _Page.hits = []
    server = http.server.HTTPServer(("127.0.0.1", 0), _Page)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}/admin"
    server.shutdown()


def _job_db(tmp_path, url):
    from scripts.db import init_db, insert_job
    db = tmp_path / "scrape.db"
    init_db(db)
    job_id = insert_job(db, {
        "title": "Importing...", "company": "", "url": url, "source": "manual",
        "location": "", "description": "", "date_found": "2026-11-20",
    })
    return db, job_id


def test_self_hosted_still_fetches_an_address_on_the_local_network(tmp_path, internal_page, monkeypatch):
    """The control: with the hosted restriction off, the page really is reachable and is scraped."""
    monkeypatch.delenv("CLOUD_MODE", raising=False)
    from scripts.scrape_url import scrape_job_url
    db, job_id = _job_db(tmp_path, internal_page)

    fields = scrape_job_url(db, job_id)

    assert fields.get("title") == "Internal Admin"
    assert _Page.hits == ["/admin"]


def test_the_hosted_scraper_does_not_fetch_an_internal_address(tmp_path, internal_page, monkeypatch):
    monkeypatch.setenv("CLOUD_MODE", "true")
    from scripts.scrape_url import scrape_job_url
    db, job_id = _job_db(tmp_path, internal_page)

    assert scrape_job_url(db, job_id) == {}

    assert _Page.hits == []
    row = sqlite3.connect(db).execute("SELECT title, description FROM jobs WHERE id=?", (job_id,)).fetchone()
    assert row == ("Importing...", ""), "nothing from the internal page may be saved into the job"


def test_the_hosted_scraper_does_not_launch_a_browser_scraper_for_a_spoofed_board_url(tmp_path, monkeypatch):
    monkeypatch.setenv("CLOUD_MODE", "true")
    import scripts.scrape_url as scrape
    called = []
    monkeypatch.setattr(scrape, "_scrape_jobgether", lambda url: called.append(url) or {"title": "x"})
    db, job_id = _job_db(tmp_path, "http://169.254.169.254/latest/meta-data/?x=jobgether.com")

    assert scrape.scrape_job_url(db, job_id) == {}
    assert called == []


def test_the_hosted_scraper_fetches_a_public_page_through_the_safe_session(tmp_path, monkeypatch):
    monkeypatch.setenv("CLOUD_MODE", "true")
    monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo({"jobs.example.test": [PUBLIC_V4]}))
    import scripts.scrape_url as scrape

    class FakeSafeSession:
        used: ClassVar[list] = []

        def get(self, url, **kwargs):
            type(self).used.append(url)
            return SimpleNamespace(text=JSON_LD_PAGE.decode(), raise_for_status=lambda: None)

    monkeypatch.setattr(scrape.safe_net, "SafeSession", FakeSafeSession)
    monkeypatch.setattr(scrape.requests, "get", lambda *a, **k: pytest.fail("the hosted version must not use plain requests.get"))
    db, job_id = _job_db(tmp_path, "https://jobs.example.test/post/1")

    fields = scrape.scrape_job_url(db, job_id)

    assert FakeSafeSession.used == ["https://jobs.example.test/post/1"]
    assert fields.get("title") == "Internal Admin"


# ── Adding links ───────────────────────────────────────────────────────────────────────────────

@pytest.fixture()
def add_client(tmp_path, monkeypatch):
    from scripts.db import (
        insert_job,  # noqa: F401 - imported to fail early if the module moves
    )
    from scripts.db_migrate import migrate_db

    db = tmp_path / "staging.db"
    migrate_db(db)
    monkeypatch.setattr("dev_api.DB_PATH", db)
    queued = []
    monkeypatch.setattr("scripts.task_runner.submit_task", lambda db_path, kind, job_id: queued.append(job_id) or 1)
    monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo({"jobs.example.test": [PUBLIC_V4], "evil.example.test": ["10.0.0.7"]}))
    from dev_api import app
    return SimpleNamespace(client=TestClient(app), db=db, queued=queued)


def _saved_urls(db):
    return [row[0] for row in sqlite3.connect(db).execute("SELECT url FROM jobs ORDER BY id")]


def test_hosted_add_by_url_keeps_public_links_and_rejects_internal_ones(add_client, monkeypatch):
    monkeypatch.setattr("dev_api._CLOUD_MODE", True)

    resp = add_client.client.post("/api/jobs/add", json={"urls": [
        "http://127.0.0.1:8601/api/settings/profile",
        "http://169.254.169.254/latest/meta-data/",
        "https://evil.example.test/job/1",
        "https://jobs.example.test/job/1",
        "file:///etc/passwd",
    ]})

    assert resp.status_code == 202
    assert resp.json() == {"queued": 1, "rejected": 4}
    assert _saved_urls(add_client.db) == ["https://jobs.example.test/job/1"]
    assert len(add_client.queued) == 1


def test_self_hosted_add_by_url_still_accepts_a_local_network_link(add_client, monkeypatch):
    monkeypatch.setattr("dev_api._CLOUD_MODE", False)

    resp = add_client.client.post("/api/jobs/add", json={"urls": ["http://192.168.1.20:8080/job/1"]})

    assert resp.json()["queued"] == 1
    assert _saved_urls(add_client.db) == ["http://192.168.1.20:8080/job/1"]


def test_hosted_csv_import_filters_the_same_way(add_client, monkeypatch):
    monkeypatch.setattr("dev_api._CLOUD_MODE", True)
    csv_bytes = b"link\nhttp://127.0.0.1:8601/x\nhttps://jobs.example.test/job/2\nhttp://10.0.0.9/y\n"

    resp = add_client.client.post("/api/jobs/upload-csv", files={"file": ("links.csv", csv_bytes, "text/csv")})

    assert resp.status_code == 202
    body = resp.json()
    assert body["queued"] == 1 and body["rejected"] == 2 and body["total"] == 3
    assert _saved_urls(add_client.db) == ["https://jobs.example.test/job/2"]
