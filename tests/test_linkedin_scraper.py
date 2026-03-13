# tests/test_linkedin_scraper.py
import io
import json
import sys
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch
import tempfile

sys.path.insert(0, str(Path(__file__).parent.parent))


def test_invalid_url_raises():
    from scripts.linkedin_scraper import scrape_profile
    with tempfile.TemporaryDirectory() as tmp:
        stage = Path(tmp) / "stage.json"
        try:
            scrape_profile("https://linkedin.com/company/acme", stage)
            assert False, "should have raised"
        except ValueError as e:
            assert "linkedin.com/in/" in str(e)


def test_non_linkedin_url_raises():
    from scripts.linkedin_scraper import scrape_profile
    with tempfile.TemporaryDirectory() as tmp:
        stage = Path(tmp) / "stage.json"
        try:
            scrape_profile("https://example.com/profile", stage)
            assert False, "should have raised"
        except ValueError:
            pass


def test_valid_linkedin_url_accepted():
    from scripts.linkedin_scraper import scrape_profile
    with tempfile.TemporaryDirectory() as tmp:
        stage = Path(tmp) / "stage.json"
        fixture_html = (Path(__file__).parent / "fixtures" / "linkedin_profile.html").read_text()

        mock_page = MagicMock()
        mock_page.content.return_value = fixture_html
        mock_browser = MagicMock()
        mock_browser.new_page.return_value = mock_page
        mock_playwright = MagicMock()
        mock_playwright.chromium.launch.return_value = mock_browser

        with patch("scripts.linkedin_scraper.sync_playwright") as mock_sync_pw:
            mock_sync_pw.return_value.__enter__ = MagicMock(return_value=mock_playwright)
            mock_sync_pw.return_value.__exit__ = MagicMock(return_value=False)
            result = scrape_profile("https://linkedin.com/in/alanw", stage)

        assert result["name"] == "Alan Weinstock"
        assert stage.exists()


def test_scrape_profile_writes_staging_file():
    from scripts.linkedin_scraper import scrape_profile
    with tempfile.TemporaryDirectory() as tmp:
        stage = Path(tmp) / "stage.json"
        fixture_html = (Path(__file__).parent / "fixtures" / "linkedin_profile.html").read_text()

        mock_page = MagicMock()
        mock_page.content.return_value = fixture_html
        mock_browser = MagicMock()
        mock_browser.new_page.return_value = mock_page
        mock_playwright = MagicMock()
        mock_playwright.chromium.launch.return_value = mock_browser

        with patch("scripts.linkedin_scraper.sync_playwright") as mock_sync_pw:
            mock_sync_pw.return_value.__enter__ = MagicMock(return_value=mock_playwright)
            mock_sync_pw.return_value.__exit__ = MagicMock(return_value=False)
            scrape_profile("https://linkedin.com/in/alanw", stage)

        data = json.loads(stage.read_text())
        assert data["source"] == "url_scrape"
        assert data["url"] == "https://linkedin.com/in/alanw"
        assert "raw_html" in data
        assert "extracted" in data
        assert data["extracted"]["name"] == "Alan Weinstock"


def _make_export_zip() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("Position.csv",
            "Company Name,Title,Description,Started On,Finished On\n"
            "Acme Corp,Staff Engineer,Led migration. Built CI/CD.,Jan 2022,\n"
            "Beta Industries,Senior Engineer,Maintained clusters.,Mar 2019,Dec 2021\n"
        )
        zf.writestr("Education.csv",
            "School Name,Degree Name,Field Of Study,Start Date,End Date\n"
            "State University,Bachelor of Science,Computer Science,2010,2014\n"
        )
        zf.writestr("Skills.csv",
            "Name,Description\n"
            "Python,\n"
            "Kubernetes,\n"
        )
        zf.writestr("Profile.csv",
            "First Name,Last Name,Headline,Summary,Email Address\n"
            "Alan,Weinstock,Staff Engineer,Experienced engineer.,alan@example.com\n"
        )
    return buf.getvalue()


def test_parse_export_zip_experience():
    from scripts.linkedin_scraper import parse_export_zip
    with tempfile.TemporaryDirectory() as tmp:
        stage = Path(tmp) / "stage.json"
        result = parse_export_zip(_make_export_zip(), stage)
    assert len(result["experience"]) == 2
    assert result["experience"][0]["company"] == "Acme Corp"
    assert result["experience"][0]["title"] == "Staff Engineer"


def test_parse_export_zip_education():
    from scripts.linkedin_scraper import parse_export_zip
    with tempfile.TemporaryDirectory() as tmp:
        stage = Path(tmp) / "stage.json"
        result = parse_export_zip(_make_export_zip(), stage)
    assert result["education"][0]["school"] == "State University"
    assert result["education"][0]["field"] == "Computer Science"


def test_parse_export_zip_skills():
    from scripts.linkedin_scraper import parse_export_zip
    with tempfile.TemporaryDirectory() as tmp:
        stage = Path(tmp) / "stage.json"
        result = parse_export_zip(_make_export_zip(), stage)
    assert "Python" in result["skills"]


def test_parse_export_zip_name_and_email():
    from scripts.linkedin_scraper import parse_export_zip
    with tempfile.TemporaryDirectory() as tmp:
        stage = Path(tmp) / "stage.json"
        result = parse_export_zip(_make_export_zip(), stage)
    assert result["name"] == "Alan Weinstock"
    assert result["email"] == "alan@example.com"


def test_parse_export_zip_missing_csv_does_not_raise():
    from scripts.linkedin_scraper import parse_export_zip
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("Profile.csv",
            "First Name,Last Name,Headline,Summary,Email Address\n"
            "Alan,Weinstock,Engineer,Summary here.,alan@example.com\n"
        )
    with tempfile.TemporaryDirectory() as tmp:
        stage = Path(tmp) / "stage.json"
        result = parse_export_zip(buf.getvalue(), stage)
    assert result["name"] == "Alan Weinstock"
    assert result["experience"] == []


def test_parse_export_zip_writes_staging_file():
    from scripts.linkedin_scraper import parse_export_zip
    with tempfile.TemporaryDirectory() as tmp:
        stage = Path(tmp) / "stage.json"
        parse_export_zip(_make_export_zip(), stage)
        data = json.loads(stage.read_text())
    assert data["source"] == "export_zip"
    assert data["raw_html"] is None
