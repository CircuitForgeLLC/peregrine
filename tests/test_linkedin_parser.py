# tests/test_linkedin_parser.py
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

FIXTURE_HTML = (Path(__file__).parent / "fixtures" / "linkedin_profile.html").read_text()


def _write_url_stage(path: Path) -> None:
    """Write a minimal url_scrape staging file with intentionally stale extracted data."""
    path.write_text(json.dumps({
        "url": "https://linkedin.com/in/alanw",
        "scraped_at": "2026-03-12T14:30:00+00:00",
        "source": "url_scrape",
        "raw_html": FIXTURE_HTML,
        "extracted": {
            "name": "Alan Weinstock (stale)",   # stale — re-parse should update this
            "career_summary": "",
            "experience": [], "education": [], "skills": [], "achievements": [],
            "email": "", "phone": "", "linkedin": "",
        },
    }))


def _write_zip_stage(path: Path) -> None:
    """Write a minimal export_zip staging file (no raw_html)."""
    path.write_text(json.dumps({
        "url": None,
        "scraped_at": "2026-03-12T14:30:00+00:00",
        "source": "export_zip",
        "raw_html": None,
        "extracted": {
            "name": "Alan Weinstock",
            "career_summary": "Engineer",
            "experience": [{"company": "Acme", "title": "SE", "date_range": "", "bullets": []}],
            "education": [], "skills": ["Python"], "achievements": [],
            "email": "alan@example.com", "phone": "", "linkedin": "",
        },
    }))


def test_parse_stage_reruns_parser_on_url_scrape():
    """parse_stage re-runs parse_html from raw_html, ignoring stale extracted data."""
    from scripts.linkedin_parser import parse_stage
    with tempfile.TemporaryDirectory() as tmp:
        stage = Path(tmp) / "stage.json"
        _write_url_stage(stage)
        result, err = parse_stage(stage)
    assert err == ""
    assert result["name"] == "Alan Weinstock"   # fresh parse, not "(stale)"
    assert len(result["experience"]) == 2


def test_parse_stage_returns_stored_data_for_zip():
    """parse_stage returns stored extracted dict for export_zip (no raw_html to re-parse)."""
    from scripts.linkedin_parser import parse_stage
    with tempfile.TemporaryDirectory() as tmp:
        stage = Path(tmp) / "stage.json"
        _write_zip_stage(stage)
        result, err = parse_stage(stage)
    assert err == ""
    assert result["name"] == "Alan Weinstock"
    assert result["email"] == "alan@example.com"
    assert "Python" in result["skills"]


def test_parse_stage_missing_file_returns_error():
    from scripts.linkedin_parser import parse_stage
    result, err = parse_stage(Path("/nonexistent/stage.json"))
    assert result == {}
    assert err != ""


def test_parse_stage_corrupted_file_returns_error():
    from scripts.linkedin_parser import parse_stage
    with tempfile.TemporaryDirectory() as tmp:
        stage = Path(tmp) / "stage.json"
        stage.write_text("not valid json {{{{")
        result, err = parse_stage(stage)
    assert result == {}
    assert err != ""


def test_parse_stage_updates_staging_file_after_reparse():
    """After re-parsing, the staging file's extracted dict is updated."""
    from scripts.linkedin_parser import parse_stage
    with tempfile.TemporaryDirectory() as tmp:
        stage = Path(tmp) / "stage.json"
        _write_url_stage(stage)
        parse_stage(stage)
        updated = json.loads(stage.read_text())
    assert updated["extracted"]["name"] == "Alan Weinstock"
    assert len(updated["extracted"]["experience"]) == 2
