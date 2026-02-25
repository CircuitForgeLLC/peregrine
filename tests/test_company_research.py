import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.company_research import _score_experiences, _build_resume_context, _load_resume_and_keywords


RESUME = {
    "experience_details": [
        {
            "position": "Lead Technical Account Manager",
            "company": "UpGuard",
            "employment_period": "10/2022 - 05/2023",
            "key_responsibilities": [
                {"r1": "Managed enterprise security accounts worth $2M ARR"},
                {"r2": "Led QBR cadence with C-suite stakeholders"},
            ],
        },
        {
            "position": "Founder and Principal Consultant",
            "company": "M3 Consulting Services",
            "employment_period": "07/2023 - Present",
            "key_responsibilities": [
                {"r1": "Revenue operations consulting for SaaS clients"},
                {"r2": "Built customer success frameworks"},
            ],
        },
        {
            "position": "Customer Success Manager",
            "company": "Generic Co",
            "employment_period": "01/2020 - 09/2022",
            "key_responsibilities": [
                {"r1": "Managed SMB portfolio"},
            ],
        },
    ]
}

KEYWORDS = ["ARR", "QBR", "enterprise", "security", "stakeholder"]
JD = "Looking for a TAM with enterprise ARR experience and QBR facilitation skills."


def test_score_experiences_returns_sorted():
    """UpGuard entry should score highest — most keywords present in text and JD."""
    scored = _score_experiences(RESUME["experience_details"], KEYWORDS, JD)
    assert scored[0]["company"] == "UpGuard"


def test_score_experiences_adds_score_key():
    """Each returned entry has a 'score' integer key."""
    scored = _score_experiences(RESUME["experience_details"], KEYWORDS, JD)
    for e in scored:
        assert isinstance(e["score"], int)


def test_build_resume_context_top2_in_full():
    """Top 2 experiences appear with full bullet detail."""
    ctx = _build_resume_context(RESUME, KEYWORDS, JD)
    assert "Lead Technical Account Manager" in ctx
    assert "Managed enterprise security accounts" in ctx
    assert "Founder and Principal Consultant" in ctx


def test_build_resume_context_rest_condensed():
    """Remaining experiences appear as condensed one-liners, not full bullets."""
    ctx = _build_resume_context(RESUME, KEYWORDS, JD)
    assert "Also in Alex" in ctx
    assert "Generic Co" in ctx
    # Generic Co bullets should NOT appear in full
    assert "Managed SMB portfolio" not in ctx


def test_upguard_nda_low_score():
    """UpGuard name replaced with 'enterprise security vendor' when score < 3."""
    ctx = _build_resume_context(RESUME, ["python", "kubernetes"], "python kubernetes devops")
    assert "enterprise security vendor" in ctx


def test_load_resume_and_keywords_returns_lists():
    """_load_resume_and_keywords returns a tuple of (dict, list[str])."""
    resume, keywords = _load_resume_and_keywords()
    assert isinstance(resume, dict)
    assert isinstance(keywords, list)
    assert all(isinstance(k, str) for k in keywords)
