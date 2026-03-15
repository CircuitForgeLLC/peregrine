"""Tests for URL-based job scraping."""
from unittest.mock import patch, MagicMock


def _make_db(tmp_path, url="https://www.linkedin.com/jobs/view/99999/"):
    from scripts.db import init_db, insert_job
    db = tmp_path / "test.db"
    init_db(db)
    job_id = insert_job(db, {
        "title": "Importing…", "company": "", "url": url,
        "source": "manual", "location": "", "description": "", "date_found": "2026-02-24",
    })
    return db, job_id


def test_canonicalize_url_linkedin():
    from scripts.scrape_url import canonicalize_url
    messy = (
        "https://www.linkedin.com/jobs/view/4376518925/"
        "?trk=eml-email_job_alert&refId=abc%3D%3D&trackingId=xyz"
    )
    assert canonicalize_url(messy) == "https://www.linkedin.com/jobs/view/4376518925/"


def test_canonicalize_url_linkedin_comm():
    from scripts.scrape_url import canonicalize_url
    comm = "https://www.linkedin.com/comm/jobs/view/4376518925/?trackingId=abc"
    assert canonicalize_url(comm) == "https://www.linkedin.com/jobs/view/4376518925/"


def test_canonicalize_url_generic_strips_utm():
    from scripts.scrape_url import canonicalize_url
    url = "https://jobs.example.com/post/42?utm_source=linkedin&utm_medium=email&jk=real_param"
    result = canonicalize_url(url)
    assert "utm_source" not in result
    assert "real_param" in result


def test_detect_board_linkedin():
    from scripts.scrape_url import _detect_board
    assert _detect_board("https://www.linkedin.com/jobs/view/12345/") == "linkedin"
    assert _detect_board("https://linkedin.com/jobs/view/12345/?tracking=abc") == "linkedin"


def test_detect_board_indeed():
    from scripts.scrape_url import _detect_board
    assert _detect_board("https://www.indeed.com/viewjob?jk=abc123") == "indeed"


def test_detect_board_glassdoor():
    from scripts.scrape_url import _detect_board
    assert _detect_board("https://www.glassdoor.com/job-listing/foo-bar-123.htm") == "glassdoor"


def test_detect_board_generic():
    from scripts.scrape_url import _detect_board
    assert _detect_board("https://jobs.example.com/posting/42") == "generic"


def test_extract_linkedin_job_id():
    from scripts.scrape_url import _extract_linkedin_job_id
    assert _extract_linkedin_job_id("https://www.linkedin.com/jobs/view/4376518925/") == "4376518925"
    assert _extract_linkedin_job_id("https://www.linkedin.com/comm/jobs/view/4376518925/?tracking=x") == "4376518925"
    assert _extract_linkedin_job_id("https://example.com/no-id") is None


def test_scrape_linkedin_updates_job(tmp_path):
    db, job_id = _make_db(tmp_path)

    linkedin_html = """<html><head></head><body>
        <h2 class="top-card-layout__title">Customer Success Manager</h2>
        <a class="topcard__org-name-link">Acme Corp</a>
        <span class="topcard__flavor--bullet">San Francisco, CA</span>
        <div class="show-more-less-html__markup">Exciting CSM role with great benefits.</div>
    </body></html>"""

    mock_resp = MagicMock()
    mock_resp.text = linkedin_html
    mock_resp.raise_for_status = MagicMock()

    with patch("scripts.scrape_url.requests.get", return_value=mock_resp):
        from scripts.scrape_url import scrape_job_url
        result = scrape_job_url(db, job_id)

    assert result.get("title") == "Customer Success Manager"
    assert result.get("company") == "Acme Corp"
    assert "CSM role" in result.get("description", "")

    import sqlite3
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    row = dict(conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone())
    conn.close()
    assert row["title"] == "Customer Success Manager"
    assert row["company"] == "Acme Corp"


def test_scrape_url_generic_json_ld(tmp_path):
    db, job_id = _make_db(tmp_path, url="https://jobs.example.com/post/42")

    json_ld_html = """<html><head>
        <script type="application/ld+json">
        {"@type": "JobPosting", "title": "TAM Role", "description": "Tech account mgmt.",
         "hiringOrganization": {"name": "TechCo"},
         "jobLocation": {"address": {"addressLocality": "Austin, TX"}}}
        </script>
    </head><body></body></html>"""

    mock_resp = MagicMock()
    mock_resp.text = json_ld_html
    mock_resp.raise_for_status = MagicMock()

    with patch("scripts.scrape_url.requests.get", return_value=mock_resp):
        from scripts.scrape_url import scrape_job_url
        result = scrape_job_url(db, job_id)

    assert result.get("title") == "TAM Role"
    assert result.get("company") == "TechCo"


def test_scrape_url_graceful_on_http_error(tmp_path):
    db, job_id = _make_db(tmp_path)
    import requests as req

    with patch("scripts.scrape_url.requests.get", side_effect=req.RequestException("timeout")):
        from scripts.scrape_url import scrape_job_url
        result = scrape_job_url(db, job_id)

    # Should return empty dict and not raise; job row still exists
    assert isinstance(result, dict)
    import sqlite3
    conn = sqlite3.connect(db)
    row = conn.execute("SELECT id FROM jobs WHERE id=?", (job_id,)).fetchone()
    conn.close()
    assert row is not None


def test_detect_board_jobgether():
    from scripts.scrape_url import _detect_board
    assert _detect_board("https://jobgether.com/offer/69b42d9d24d79271ee0618e8-csm---resware") == "jobgether"
    assert _detect_board("https://www.jobgether.com/offer/abc-role---company") == "jobgether"


def test_jobgether_slug_company_extraction():
    from scripts.scrape_url import _company_from_jobgether_url
    assert _company_from_jobgether_url(
        "https://jobgether.com/offer/69b42d9d24d79271ee0618e8-customer-success-manager---resware"
    ) == "Resware"
    assert _company_from_jobgether_url(
        "https://jobgether.com/offer/abc123-director-of-cs---acme-corp"
    ) == "Acme Corp"
    assert _company_from_jobgether_url(
        "https://jobgether.com/offer/abc123-no-separator-here"
    ) == ""


def test_scrape_jobgether_no_playwright(tmp_path):
    """When Playwright is unavailable, _scrape_jobgether falls back to URL slug for company."""
    import sys
    import unittest.mock as mock

    url = "https://jobgether.com/offer/69b42d9d24d79271ee0618e8-customer-success-manager---resware"
    with mock.patch.dict(sys.modules, {"playwright": None, "playwright.sync_api": None}):
        from scripts.scrape_url import _scrape_jobgether
        result = _scrape_jobgether(url)

    assert result.get("company") == "Resware"
    assert result.get("source") == "jobgether"
