# tests/test_custom_board_weworkremotely.py
import sys
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.custom_boards import weworkremotely


def _rss(items: list[dict]) -> bytes:
    item_xml = "".join(
        f"""<item>
            <title>{it['title']}</title>
            <link>{it['link']}</link>
            <region>{it.get('region', 'Anywhere in the World')}</region>
            <description>{it.get('description', '')}</description>
            <pubDate>{it['pubDate']}</pubDate>
        </item>"""
        for it in items
    )
    return f"""<?xml version="1.0" encoding="UTF-8"?>
    <rss version="2.0"><channel>{item_xml}</channel></rss>""".encode()


def _fake_response(content: bytes, status=200):
    resp = MagicMock()
    resp.status_code = status
    resp.content = content
    resp.raise_for_status = MagicMock()
    if status >= 400:
        import requests
        resp.raise_for_status.side_effect = requests.HTTPError(f"HTTP {status}")
    return resp


def _pubdate(hours_ago: int = 1) -> str:
    return format_datetime(datetime.now(tz=timezone.utc) - timedelta(hours=hours_ago))


def test_scrape_returns_matching_jobs():
    content = _rss([
        {
            "title": "Acme Corp: Senior Backend Engineer",
            "link": "https://weworkremotely.com/remote-jobs/acme-backend-engineer",
            "pubDate": _pubdate(1),
        },
        {
            "title": "Widgets Inc: Marketing Manager",
            "link": "https://weworkremotely.com/remote-jobs/widgets-marketing",
            "pubDate": _pubdate(1),
        },
    ])
    profile = {"titles": ["Backend Engineer"], "hours_old": 240}

    with patch("scripts.custom_boards.weworkremotely.requests.get", return_value=_fake_response(content)):
        results = weworkremotely.scrape(profile, "Remote", results_wanted=10)

    assert len(results) == 1
    job = results[0]
    assert job["title"] == "Senior Backend Engineer"
    assert job["company"] == "Acme Corp"
    assert job["url"] == "https://weworkremotely.com/remote-jobs/acme-backend-engineer"
    assert job["source"] == "weworkremotely"
    assert job["is_remote"] is True
    assert job["salary"] == ""


def test_scrape_no_title_filter_returns_all():
    content = _rss([
        {"title": "Acme Corp: A", "link": "https://weworkremotely.com/1", "pubDate": _pubdate(1)},
        {"title": "Acme Corp: B", "link": "https://weworkremotely.com/2", "pubDate": _pubdate(1)},
    ])
    profile = {"titles": [], "hours_old": 240}

    with patch("scripts.custom_boards.weworkremotely.requests.get", return_value=_fake_response(content)):
        results = weworkremotely.scrape(profile, "Remote", results_wanted=10)

    assert len(results) == 2


def test_scrape_respects_hours_old_cutoff():
    content = _rss([
        {"title": "Acme Corp: Backend Engineer", "link": "https://weworkremotely.com/1", "pubDate": _pubdate(300)},
    ])
    profile = {"titles": ["Backend Engineer"], "hours_old": 240}

    with patch("scripts.custom_boards.weworkremotely.requests.get", return_value=_fake_response(content)):
        results = weworkremotely.scrape(profile, "Remote", results_wanted=10)

    assert results == []


def test_scrape_dedupes_by_url():
    content = _rss([
        {"title": "Acme Corp: Backend Engineer", "link": "https://weworkremotely.com/1", "pubDate": _pubdate(1)},
        {"title": "Acme Corp: Backend Engineer", "link": "https://weworkremotely.com/1", "pubDate": _pubdate(1)},
    ])
    profile = {"titles": ["Backend Engineer"], "hours_old": 240}

    with patch("scripts.custom_boards.weworkremotely.requests.get", return_value=_fake_response(content)):
        results = weworkremotely.scrape(profile, "Remote", results_wanted=10)

    assert len(results) == 1


def test_scrape_handles_title_without_company_separator():
    content = _rss([
        {"title": "Just A Title No Colon", "link": "https://weworkremotely.com/1", "pubDate": _pubdate(1)},
    ])
    profile = {"titles": [], "hours_old": 240}

    with patch("scripts.custom_boards.weworkremotely.requests.get", return_value=_fake_response(content)):
        results = weworkremotely.scrape(profile, "Remote", results_wanted=10)

    assert len(results) == 1
    assert results[0]["title"] == "Just A Title No Colon"
    assert results[0]["company"] == ""


def test_scrape_handles_request_error():
    import requests

    profile = {"titles": ["Engineer"], "hours_old": 240}
    with patch("scripts.custom_boards.weworkremotely.requests.get", side_effect=requests.RequestException("boom")):
        results = weworkremotely.scrape(profile, "Remote", results_wanted=10)

    assert results == []


def test_scrape_handles_malformed_xml():
    profile = {"titles": ["Engineer"], "hours_old": 240}
    with patch(
        "scripts.custom_boards.weworkremotely.requests.get",
        return_value=_fake_response(b"<not valid xml"),
    ):
        results = weworkremotely.scrape(profile, "Remote", results_wanted=10)

    assert results == []


def test_scrape_respects_results_wanted():
    content = _rss([
        {"title": f"Acme: Engineer {i}", "link": f"https://weworkremotely.com/{i}", "pubDate": _pubdate(1)}
        for i in range(5)
    ])
    profile = {"titles": ["Engineer"], "hours_old": 240}

    with patch("scripts.custom_boards.weworkremotely.requests.get", return_value=_fake_response(content)):
        results = weworkremotely.scrape(profile, "Remote", results_wanted=2)

    assert len(results) == 2
