"""Tests for Craigslist RSS scraper."""
from datetime import datetime, timezone, timedelta
from email.utils import format_datetime
from unittest.mock import patch, MagicMock
import xml.etree.ElementTree as ET

import pytest
import requests


# ── RSS fixture helpers ────────────────────────────────────────────────────────

def _make_rss(items: list[dict]) -> bytes:
    """Build minimal Craigslist-style RSS XML from a list of item dicts."""
    channel = ET.Element("channel")
    for item_data in items:
        item = ET.SubElement(channel, "item")
        for tag, value in item_data.items():
            el = ET.SubElement(item, tag)
            el.text = value
    rss = ET.Element("rss")
    rss.append(channel)
    return ET.tostring(rss, encoding="utf-8", xml_declaration=True)


def _pubdate(hours_ago: float = 1.0) -> str:
    """Return an RFC 2822 pubDate string for N hours ago."""
    dt = datetime.now(tz=timezone.utc) - timedelta(hours=hours_ago)
    return format_datetime(dt)


def _mock_resp(content: bytes, status_code: int = 200) -> MagicMock:
    mock = MagicMock()
    mock.status_code = status_code
    mock.content = content
    mock.raise_for_status = MagicMock()
    if status_code >= 400:
        mock.raise_for_status.side_effect = requests.HTTPError(f"HTTP {status_code}")
    return mock


# ── Fixtures ──────────────────────────────────────────────────────────────────

_SAMPLE_RSS = _make_rss([{
    "title": "Customer Success Manager",
    "link": "https://sfbay.craigslist.org/jjj/d/csm-role/1234567890.html",
    "description": "Great CSM role at Acme Corp. Salary $120k.",
    "pubDate": _pubdate(1),
}])

_TWO_ITEM_RSS = _make_rss([
    {
        "title": "Customer Success Manager",
        "link": "https://sfbay.craigslist.org/jjj/d/csm-role/1111111111.html",
        "description": "CSM role 1.",
        "pubDate": _pubdate(1),
    },
    {
        "title": "Account Manager",
        "link": "https://sfbay.craigslist.org/jjj/d/am-role/2222222222.html",
        "description": "AM role.",
        "pubDate": _pubdate(2),
    },
])

_OLD_ITEM_RSS = _make_rss([{
    "title": "Old Job",
    "link": "https://sfbay.craigslist.org/jjj/d/old-job/9999999999.html",
    "description": "Very old posting.",
    "pubDate": _pubdate(hours_ago=500),
}])

_TWO_METRO_CONFIG = {
    "metros": ["sfbay", "newyork"],
    "location_map": {
        "San Francisco Bay Area, CA": "sfbay",
        "New York, NY": "newyork",
    },
    "category": "jjj",
}

_SINGLE_METRO_CONFIG = {
    "metros": ["sfbay"],
    "location_map": {"San Francisco Bay Area, CA": "sfbay"},
}

_PROFILE = {"titles": ["Customer Success Manager"], "hours_old": 240}


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_scrape_returns_empty_on_missing_config():
    """Missing craigslist.yaml → returns [] without raising."""
    from scripts.custom_boards import craigslist
    with patch("scripts.custom_boards.craigslist._load_config",
               side_effect=FileNotFoundError("config not found")):
        result = craigslist.scrape(_PROFILE, "San Francisco Bay Area, CA")
    assert result == []


def test_scrape_remote_hits_all_metros():
    """location='Remote' triggers one RSS fetch per configured metro."""
    with patch("scripts.custom_boards.craigslist._load_config",
               return_value=_TWO_METRO_CONFIG):
        with patch("scripts.custom_boards.craigslist.requests.get",
                   return_value=_mock_resp(_SAMPLE_RSS)) as mock_get:
            from scripts.custom_boards import craigslist
            result = craigslist.scrape(_PROFILE, "Remote")

    assert mock_get.call_count == 2
    fetched_urls = [call.args[0] for call in mock_get.call_args_list]
    assert any("sfbay" in u for u in fetched_urls)
    assert any("newyork" in u for u in fetched_urls)
    assert all(r["is_remote"] for r in result)


def test_scrape_location_map_resolves():
    """Known location string maps to exactly one metro."""
    with patch("scripts.custom_boards.craigslist._load_config",
               return_value=_TWO_METRO_CONFIG):
        with patch("scripts.custom_boards.craigslist.requests.get",
                   return_value=_mock_resp(_SAMPLE_RSS)) as mock_get:
            from scripts.custom_boards import craigslist
            result = craigslist.scrape(_PROFILE, "San Francisco Bay Area, CA")

    assert mock_get.call_count == 1
    assert "sfbay" in mock_get.call_args.args[0]
    assert len(result) == 1
    assert result[0]["is_remote"] is False


def test_scrape_location_not_in_map_returns_empty():
    """Location not in location_map → [] without raising."""
    with patch("scripts.custom_boards.craigslist._load_config",
               return_value=_SINGLE_METRO_CONFIG):
        with patch("scripts.custom_boards.craigslist.requests.get") as mock_get:
            from scripts.custom_boards import craigslist
            result = craigslist.scrape(_PROFILE, "Portland, OR")

    assert result == []
    mock_get.assert_not_called()


def test_hours_old_filter():
    """Items older than hours_old are excluded."""
    profile = {"titles": ["Customer Success Manager"], "hours_old": 48}
    with patch("scripts.custom_boards.craigslist._load_config",
               return_value=_SINGLE_METRO_CONFIG):
        with patch("scripts.custom_boards.craigslist.requests.get",
                   return_value=_mock_resp(_OLD_ITEM_RSS)):
            from scripts.custom_boards import craigslist
            result = craigslist.scrape(profile, "San Francisco Bay Area, CA")

    assert result == []


def test_dedup_within_run():
    """Same URL from two different metros is only returned once."""
    same_url_rss = _make_rss([{
        "title": "CSM Role",
        "link": "https://sfbay.craigslist.org/jjj/d/csm/1234.html",
        "description": "Same job.",
        "pubDate": _pubdate(1),
    }])
    with patch("scripts.custom_boards.craigslist._load_config",
               return_value=_TWO_METRO_CONFIG):
        with patch("scripts.custom_boards.craigslist.requests.get",
                   return_value=_mock_resp(same_url_rss)):
            from scripts.custom_boards import craigslist
            result = craigslist.scrape(_PROFILE, "Remote")

    urls = [r["url"] for r in result]
    assert len(urls) == len(set(urls))


def test_http_error_graceful():
    """HTTP error → [] without raising."""
    with patch("scripts.custom_boards.craigslist._load_config",
               return_value=_SINGLE_METRO_CONFIG):
        with patch("scripts.custom_boards.craigslist.requests.get",
                   side_effect=requests.RequestException("timeout")):
            from scripts.custom_boards import craigslist
            result = craigslist.scrape(_PROFILE, "San Francisco Bay Area, CA")

    assert result == []


def test_malformed_xml_graceful():
    """Malformed RSS XML → [] without raising."""
    bad_resp = MagicMock()
    bad_resp.content = b"this is not xml <<<<"
    bad_resp.raise_for_status = MagicMock()
    with patch("scripts.custom_boards.craigslist._load_config",
               return_value=_SINGLE_METRO_CONFIG):
        with patch("scripts.custom_boards.craigslist.requests.get",
                   return_value=bad_resp):
            from scripts.custom_boards import craigslist
            result = craigslist.scrape(_PROFILE, "San Francisco Bay Area, CA")
    assert result == []


def test_results_wanted_cap():
    """Never returns more than results_wanted items."""
    with patch("scripts.custom_boards.craigslist._load_config",
               return_value=_TWO_METRO_CONFIG):
        with patch("scripts.custom_boards.craigslist.requests.get",
                   return_value=_mock_resp(_TWO_ITEM_RSS)):
            from scripts.custom_boards import craigslist
            result = craigslist.scrape(_PROFILE, "Remote", results_wanted=1)

    assert len(result) <= 1
