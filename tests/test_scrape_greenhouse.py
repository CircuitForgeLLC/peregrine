"""Greenhouse job pages (peregrine#248).

The current board pages are client-rendered, so the generic scraper saw the title and nothing else:
no company and a 6 character description. Greenhouse has a public JSON API for the same posting,
which is what these cover. The sample response is modeled on the real shape with invented content.
"""
import sqlite3
from unittest.mock import MagicMock, patch

import pytest

API_RESPONSE = {
    "id": 8000731003,
    "title": "Care Coordinator",
    "company_name": "Acme Health",
    "location": {"name": "Remote"},
    # The API returns the description as HTML that has itself been HTML-escaped.
    "content": (
        "&lt;h2&gt;&lt;strong&gt;About &lt;/strong&gt;&lt;a href=&quot;https://example.test/company/&quot;&gt;"
        "&lt;strong&gt;Acme Health&lt;/strong&gt;&lt;/a&gt;&lt;/h2&gt;\n"
        "&lt;p&gt;We run a virtual clinic &amp;amp; care team.&lt;/p&gt;\n"
        "&lt;h3&gt;What you will do&lt;/h3&gt;\n"
        "&lt;ul&gt;\n&lt;li&gt;Schedule patients&lt;/li&gt;\n&lt;li&gt;Answer questions&lt;/li&gt;\n&lt;/ul&gt;"
    ),
    "pay_input_ranges": [],
}
JOB_URL = "https://job-boards.greenhouse.io/acme/jobs/8000731003"


def _make_db(tmp_path, url=JOB_URL):
    from scripts.db import init_db, insert_job
    db = tmp_path / "test.db"
    init_db(db)
    job_id = insert_job(db, {
        "title": "Importing…", "company": "", "url": url,
        "source": "manual", "location": "", "description": "", "date_found": "2026-11-20",
    })
    return db, job_id


def _response(payload=None, status=200):
    resp = MagicMock()
    resp.status_code = status
    resp.json.return_value = payload
    resp.text = ""
    resp.raise_for_status = MagicMock()
    return resp


@pytest.mark.parametrize("url", [
    "https://job-boards.greenhouse.io/acme/jobs/8000731003",
    "https://job-boards.greenhouse.io/acme/jobs/8000731003/",
    "https://job-boards.greenhouse.io/acme/jobs/8000731003?gh_src=abc&utm_source=x",
    "https://boards.greenhouse.io/acme/jobs/8000731003",
    "https://job-boards.eu.greenhouse.io/acme/jobs/8000731003",
    "https://boards.greenhouse.io/embed/job_app?for=acme&token=8000731003",
])
def test_greenhouse_urls_are_recognised_and_parsed(url):
    from scripts.scrape_url import _detect_board, _parse_greenhouse_url

    assert _detect_board(url) == "greenhouse"
    assert _parse_greenhouse_url(url) == ("acme", "8000731003")


@pytest.mark.parametrize("url", [
    "https://boards.greenhouse.io/",
    "https://job-boards.greenhouse.io/acme",
    "https://www.example.com/careers?gh_jid=8000731003",
    "https://example.com/jobs/8000731003",
])
def test_urls_without_a_board_and_job_id_are_not_parsed(url):
    from scripts.scrape_url import _parse_greenhouse_url

    assert _parse_greenhouse_url(url) is None


def test_a_company_page_that_only_mentions_greenhouse_in_a_query_is_not_a_greenhouse_board():
    from scripts.scrape_url import _detect_board

    assert _detect_board("https://www.example.com/careers?gh_jid=8000731003") == "generic"


def test_scrape_greenhouse_maps_the_api_response_to_job_fields():
    from scripts.scrape_url import _scrape_greenhouse

    with patch("scripts.scrape_url.requests.get", return_value=_response(API_RESPONSE)):
        fields = _scrape_greenhouse(JOB_URL)

    assert fields["title"] == "Care Coordinator"
    assert fields["company"] == "Acme Health"
    assert fields["location"] == "Remote"
    assert fields["is_remote"] is True
    assert fields["source"] == "greenhouse"


def test_scrape_greenhouse_turns_the_escaped_html_into_readable_text():
    from scripts.scrape_url import _scrape_greenhouse

    with patch("scripts.scrape_url.requests.get", return_value=_response(API_RESPONSE)):
        description = _scrape_greenhouse(JOB_URL)["description"]

    assert "We run a virtual clinic & care team." in description
    assert "- Schedule patients" in description and "- Answer questions" in description
    assert "What you will do" in description
    for leftover in ("<", ">", "&lt;", "&amp;", "&quot;"):
        assert leftover not in description, f"{leftover!r} left in the description"
    # Headings and list items sit on their own lines.
    assert "Schedule patients\n" in description + "\n"


def test_scrape_greenhouse_asks_the_public_api_for_the_board_and_job_with_pay_ranges():
    from scripts.scrape_url import _scrape_greenhouse

    with patch("scripts.scrape_url.requests.get", return_value=_response(API_RESPONSE)) as get:
        _scrape_greenhouse(JOB_URL)

    args, kwargs = get.call_args
    assert args[0] == "https://boards-api.greenhouse.io/v1/boards/acme/jobs/8000731003"
    assert kwargs["params"] == {"pay_transparency": "true"}


def _scrape_greenhouse_fields(payload):
    from scripts.scrape_url import _scrape_greenhouse

    with patch("scripts.scrape_url.requests.get", return_value=_response(payload)):
        return _scrape_greenhouse(JOB_URL)


def test_published_pay_ranges_become_the_salary():
    payload = {**API_RESPONSE, "pay_input_ranges": [
        {"min_cents": 9500000, "max_cents": 11000000, "currency_type": "USD", "title": "US base", "blurb": ""},
    ]}

    assert _scrape_greenhouse_fields(payload)["salary"] == "$95,000 - $110,000 USD"


def test_a_non_dollar_pay_range_keeps_its_currency_code():
    payload = {**API_RESPONSE, "pay_input_ranges": [
        {"min_cents": 6000000, "max_cents": 7000000, "currency_type": "EUR", "title": "", "blurb": ""},
    ]}

    assert _scrape_greenhouse_fields(payload)["salary"] == "EUR 60,000 - 70,000"


def test_no_published_pay_range_means_no_salary_field():
    assert "salary" not in _scrape_greenhouse_fields(API_RESPONSE)


def test_an_office_location_is_not_marked_remote():
    payload = {**API_RESPONSE, "location": {"name": "San Francisco, CA"}}

    fields = _scrape_greenhouse_fields(payload)

    assert fields["location"] == "San Francisco, CA"
    assert fields["is_remote"] is False


def test_scrape_job_url_saves_the_greenhouse_fields(tmp_path):
    db, job_id = _make_db(tmp_path)

    with patch("scripts.scrape_url.requests.get", return_value=_response(API_RESPONSE)):
        from scripts.scrape_url import scrape_job_url
        scrape_job_url(db, job_id)

    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    row = dict(conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone())
    conn.close()
    assert row["title"] == "Care Coordinator"
    assert row["company"] == "Acme Health"
    assert row["location"] == "Remote"
    assert row["is_remote"] == 1
    assert "Schedule patients" in row["description"]


def test_a_closed_job_falls_back_to_the_generic_scrape_instead_of_failing(tmp_path):
    db, job_id = _make_db(tmp_path)
    page = _response(status=200)
    page.text = (
        '<html><head><script type="application/ld+json">'
        '{"@type": "JobPosting", "title": "Care Coordinator", "description": "From the page.", '
        '"hiringOrganization": {"name": "Acme Health"}}</script></head></html>'
    )

    def fake_get(url, **kwargs):
        return _response(status=404) if "boards-api" in url else page

    with patch("scripts.scrape_url.requests.get", side_effect=fake_get):
        from scripts.scrape_url import scrape_job_url
        fields = scrape_job_url(db, job_id)

    assert fields.get("title") == "Care Coordinator"
    assert fields.get("company") == "Acme Health"
