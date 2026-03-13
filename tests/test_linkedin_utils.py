# tests/test_linkedin_utils.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

FIXTURE = (Path(__file__).parent / "fixtures" / "linkedin_profile.html").read_text()


def test_parse_html_name():
    from scripts.linkedin_utils import parse_html
    result = parse_html(FIXTURE)
    assert result["name"] == "Alan Weinstock"


def test_parse_html_summary():
    from scripts.linkedin_utils import parse_html
    result = parse_html(FIXTURE)
    assert "embedded systems" in result["career_summary"]


def test_parse_html_experience_count():
    from scripts.linkedin_utils import parse_html
    result = parse_html(FIXTURE)
    assert len(result["experience"]) == 2


def test_parse_html_experience_fields():
    from scripts.linkedin_utils import parse_html
    result = parse_html(FIXTURE)
    first = result["experience"][0]
    assert first["company"] == "Acme Corp"
    assert first["title"] == "Staff Engineer"
    assert "Jan 2022" in first["date_range"]
    assert len(first["bullets"]) >= 2
    assert any("latency" in b for b in first["bullets"])


def test_parse_html_education():
    from scripts.linkedin_utils import parse_html
    result = parse_html(FIXTURE)
    assert len(result["education"]) == 1
    edu = result["education"][0]
    assert edu["school"] == "State University"
    assert "Computer Science" in edu["degree"]


def test_parse_html_skills():
    from scripts.linkedin_utils import parse_html
    result = parse_html(FIXTURE)
    assert "Python" in result["skills"]
    assert "Kubernetes" in result["skills"]


def test_parse_html_achievements():
    from scripts.linkedin_utils import parse_html
    result = parse_html(FIXTURE)
    assert any("AWS" in a for a in result["achievements"])


def test_parse_html_missing_section_returns_empty():
    """A profile with no skills section returns empty skills list, not an error."""
    from scripts.linkedin_utils import parse_html
    html_no_skills = FIXTURE.replace('data-section="skills"', 'data-section="hidden"')
    result = parse_html(html_no_skills)
    assert result["skills"] == []


def test_parse_html_returns_all_keys():
    from scripts.linkedin_utils import parse_html
    result = parse_html(FIXTURE)
    for key in ("name", "email", "phone", "linkedin", "career_summary",
                "experience", "education", "skills", "achievements"):
        assert key in result, f"Missing key: {key}"
