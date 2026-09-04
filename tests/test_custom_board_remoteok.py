# tests/test_custom_board_remoteok.py
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.custom_boards import remoteok


def _fake_response(payload, status=200):
    resp = MagicMock()
    resp.status_code = status
    resp.json.return_value = payload
    resp.raise_for_status = MagicMock()
    if status >= 400:
        import requests
        resp.raise_for_status.side_effect = requests.HTTPError(f"HTTP {status}")
    return resp


def _job(**overrides):
    job = {
        "position": "Senior Backend Engineer",
        "company": "Acme Corp",
        "url": "https://remoteok.com/remote-jobs/12345",
        "apply_url": "https://remoteok.com/remote-jobs/12345",
        "location": "Worldwide",
        "salary_min": 120000,
        "salary_max": 160000,
        "description": "<p>Build things.</p>",
        "epoch": int(time.time()),
    }
    job.update(overrides)
    return job


def test_scrape_returns_matching_jobs():
    payload = [
        {"legal": "...", "last_updated": 123},
        _job(position="Senior Backend Engineer"),
        _job(position="Marketing Manager"),  # should be filtered out
    ]
    profile = {"titles": ["Backend Engineer"], "hours_old": 240}

    with patch("scripts.custom_boards.remoteok.requests.get", return_value=_fake_response(payload)):
        results = remoteok.scrape(profile, "Remote", results_wanted=10)

    assert len(results) == 1
    job = results[0]
    assert job["title"] == "Senior Backend Engineer"
    assert job["company"] == "Acme Corp"
    assert job["url"] == "https://remoteok.com/remote-jobs/12345"
    assert job["source"] == "remoteok"
    assert job["is_remote"] is True
    assert job["salary"] == "$120,000 – $160,000"


def test_scrape_no_title_filter_returns_all():
    payload = [
        {"legal": "...", "last_updated": 123},
        _job(position="A"),
        _job(position="B"),
    ]
    profile = {"titles": [], "hours_old": 240}

    with patch("scripts.custom_boards.remoteok.requests.get", return_value=_fake_response(payload)):
        results = remoteok.scrape(profile, "Remote", results_wanted=10)

    assert len(results) == 2


def test_scrape_respects_hours_old_cutoff():
    stale_epoch = int(time.time()) - (300 * 3600)  # 300 hours old
    payload = [
        {"legal": "...", "last_updated": 123},
        _job(position="Backend Engineer", epoch=stale_epoch),
    ]
    profile = {"titles": ["Backend Engineer"], "hours_old": 240}

    with patch("scripts.custom_boards.remoteok.requests.get", return_value=_fake_response(payload)):
        results = remoteok.scrape(profile, "Remote", results_wanted=10)

    assert results == []


def test_scrape_respects_results_wanted():
    payload = [{"legal": "...", "last_updated": 123}] + [
        _job(position=f"Engineer {i}", url=f"https://remoteok.com/{i}") for i in range(5)
    ]
    profile = {"titles": ["Engineer"], "hours_old": 240}

    with patch("scripts.custom_boards.remoteok.requests.get", return_value=_fake_response(payload)):
        results = remoteok.scrape(profile, "Remote", results_wanted=2)

    assert len(results) == 2


def test_scrape_handles_request_error():
    import requests

    profile = {"titles": ["Engineer"], "hours_old": 240}
    with patch("scripts.custom_boards.remoteok.requests.get", side_effect=requests.RequestException("boom")):
        results = remoteok.scrape(profile, "Remote", results_wanted=10)

    assert results == []


def test_scrape_handles_malformed_response():
    profile = {"titles": ["Engineer"], "hours_old": 240}
    with patch("scripts.custom_boards.remoteok.requests.get", return_value=_fake_response({"not": "a list"})):
        results = remoteok.scrape(profile, "Remote", results_wanted=10)

    assert results == []


def test_scrape_skips_jobs_without_url():
    payload = [
        {"legal": "...", "last_updated": 123},
        _job(position="Backend Engineer", url="", apply_url=""),
    ]
    profile = {"titles": ["Backend Engineer"], "hours_old": 240}

    with patch("scripts.custom_boards.remoteok.requests.get", return_value=_fake_response(payload)):
        results = remoteok.scrape(profile, "Remote", results_wanted=10)

    assert results == []
