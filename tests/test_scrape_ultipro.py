"""UltiPro (UKG) job pages (peregrine#253).

The generic scraper reads JSON-LD and meta tags, and these pages have neither, so an add-by-URL saved
a placeholder title and nothing else. The page is not JavaScript-gated though: the whole posting is
embedded in the HTML as JSON inside a CandidateOpportunityDetail({...}); call. The sample page here is
modeled on the real shape with invented content.
"""
import json
from unittest.mock import MagicMock, patch

import pytest

JOB_URL = (
    "https://recruiting2.ultipro.com/ACM1000ACME/JobBoard/11111111-2222-3333-4444-555555555555"
    "/OpportunityDetail?opportunityId=99999999-8888-7777-6666-555555555555"
)

PAYLOAD = {
    "Id": "99999999-8888-7777-6666-555555555555",
    "Title": "Front Desk Associate",
    "JobCategoryName": "Branches",
    "FullTime": False,
    "RequisitionNumber": "FRONT000123",
    "PostedDate": "2026-11-03T18:11:35.152Z",
    "Locations": [{
        "Id": "aaaa",
        "LocalizedName": "Riverside Branch",
        "Address": {"City": "Riverside", "State": {"Code": "CA", "Name": "California"}},
    }],
    "Description": (
        "<p>We are hiring for our <b>front desk</b> team &amp; more.</p>"
        "<h3>What you will do</h3><ul><li>Greet members</li><li>Answer questions</li></ul>"
        "<p>Line one<br/>Line two</p>"
    ),
    "EqualOpportunityEmployerDescription": "<p>We are an equal opportunity employer.</p>",
    "PayRangeVisible": False,
    "PayRange": {"PayRangeMinimum": None, "PayRangeMaximum": None},
    "PayRangeCurrencyCode": "USD",
}


def _page(payload=PAYLOAD):
    # The real page puts the object in a script call and carries plenty of other script around it.
    blob = json.dumps(payload).replace("&", "\\u0026")
    return (
        "<html><head><title>Job Board</title></head><body>"
        "<script>var other = {a: 1};</script>"
        f"<script>new US.Opportunity.CandidateOpportunityDetail({blob});</script>"
        "<script>init();</script></body></html>"
    )


def _response(text, status=200):
    resp = MagicMock()
    resp.status_code = status
    resp.text = text
    resp.raise_for_status = MagicMock()
    return resp


@pytest.mark.parametrize("url", [
    JOB_URL,
    JOB_URL.replace("recruiting2", "recruiting"),
    JOB_URL + "&lang=en",
    "https://RECRUITING2.ULTIPRO.COM/ACM1000ACME/JobBoard/11111111-2222-3333-4444-555555555555/OpportunityDetail?opportunityId=1",
])
def test_ultipro_job_urls_are_recognised(url):
    from scripts.scrape_url import _detect_board

    assert _detect_board(url) == "ultipro"


@pytest.mark.parametrize("url", [
    "https://recruiting2.ultipro.com/ACM1000ACME/JobBoard/11111111-2222-3333-4444-555555555555",
    "https://recruiting2.ultipro.com/",
    "https://www.example.com/careers?next=recruiting2.ultipro.com/x/JobBoard/y/OpportunityDetail",
    "https://ultipro.com.evil.example/ACM1000ACME/JobBoard/1/OpportunityDetail?opportunityId=1",
])
def test_other_ultipro_pages_and_lookalike_hosts_are_not_matched(url):
    from scripts.scrape_url import _detect_board

    assert _detect_board(url) == "generic"


def test_scrape_ultipro_maps_the_embedded_posting_to_job_fields():
    from scripts.scrape_url import _scrape_ultipro

    with patch("scripts.scrape_url.requests.get", return_value=_response(_page())):
        fields = _scrape_ultipro(JOB_URL)

    assert fields["title"] == "Front Desk Associate"
    assert fields["company"] == "Riverside Branch"
    assert fields["location"] == "Riverside, CA"
    assert fields["source"] == "ultipro"


def test_scrape_ultipro_turns_the_html_description_into_readable_text():
    from scripts.scrape_url import _scrape_ultipro

    with patch("scripts.scrape_url.requests.get", return_value=_response(_page())):
        description = _scrape_ultipro(JOB_URL)["description"]

    assert "We are hiring for our front desk team & more." in description
    assert "- Greet members" in description and "- Answer questions" in description
    assert "Line one\nLine two" in description
    assert "We are an equal opportunity employer." in description
    for leftover in ("<", ">", "&amp;", "&lt;"):
        assert leftover not in description, f"{leftover!r} left in the description"


def test_scrape_ultipro_requests_the_page_it_was_given():
    from scripts.scrape_url import _scrape_ultipro

    with patch("scripts.scrape_url.requests.get", return_value=_response(_page())) as get:
        _scrape_ultipro(JOB_URL)

    assert get.call_args.args[0] == JOB_URL


def test_pay_is_included_only_when_the_posting_publishes_it():
    from scripts.scrape_url import _scrape_ultipro

    paid = {**PAYLOAD, "PayRangeVisible": True, "PayRange": {"PayRangeMinimum": 18.5, "PayRangeMaximum": 22}}
    with patch("scripts.scrape_url.requests.get", return_value=_response(_page(paid))):
        assert _scrape_ultipro(JOB_URL)["salary"] == "$18.50 - $22.00 USD"

    hidden = {**paid, "PayRangeVisible": False}
    with patch("scripts.scrape_url.requests.get", return_value=_response(_page(hidden))):
        assert "salary" not in _scrape_ultipro(JOB_URL)

    with patch("scripts.scrape_url.requests.get", return_value=_response(_page())):
        assert "salary" not in _scrape_ultipro(JOB_URL)


def test_a_posting_without_a_location_still_saves_title_and_description():
    from scripts.scrape_url import _scrape_ultipro

    with patch("scripts.scrape_url.requests.get", return_value=_response(_page({**PAYLOAD, "Locations": []}))):
        fields = _scrape_ultipro(JOB_URL)

    assert fields["title"] == "Front Desk Associate"
    assert "company" not in fields and "location" not in fields
    assert fields["description"]


@pytest.mark.parametrize("text", [
    "<html><body>no payload here</body></html>",
    "<script>new US.Opportunity.CandidateOpportunityDetail({not json);</script>",
    "",
])
def test_a_page_without_a_readable_payload_falls_back_to_the_generic_scraper(text):
    from scripts.scrape_url import _scrape_ultipro

    with patch("scripts.scrape_url.requests.get", return_value=_response(text)), \
         patch("scripts.scrape_url._scrape_generic", return_value={"title": "fallback"}) as generic:
        fields = _scrape_ultipro(JOB_URL)

    generic.assert_called_once_with(JOB_URL)
    assert fields == {"title": "fallback"}


def test_a_closed_posting_falls_back_to_the_generic_scraper():
    from scripts.scrape_url import _scrape_ultipro

    with patch("scripts.scrape_url.requests.get", return_value=_response("gone", status=404)), \
         patch("scripts.scrape_url._scrape_generic", return_value={}) as generic:
        _scrape_ultipro(JOB_URL)

    generic.assert_called_once_with(JOB_URL)


def test_scrape_job_url_saves_the_ultipro_fields_over_the_placeholder(tmp_path):
    from scripts.db import init_db, insert_job
    from scripts.scrape_url import scrape_job_url

    db = tmp_path / "test.db"
    init_db(db)
    job_id = insert_job(db, {
        "title": "Importing…", "company": "", "url": JOB_URL,
        "source": "manual", "location": "", "description": "", "date_found": "2026-11-20",
    })

    with patch("scripts.scrape_url.requests.get", return_value=_response(_page())):
        scrape_job_url(db, job_id)

    import sqlite3
    row = sqlite3.connect(db).execute("select title, company, location, description from jobs where id=?", (job_id,)).fetchone()
    assert row[0] == "Front Desk Associate"
    assert row[1] == "Riverside Branch"
    assert row[2] == "Riverside, CA"
    assert "front desk" in row[3]
