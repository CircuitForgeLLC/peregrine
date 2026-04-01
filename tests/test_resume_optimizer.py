# tests/test_resume_optimizer.py
"""Tests for scripts/resume_optimizer.py"""
import json
import pytest
from unittest.mock import MagicMock, patch


# ── Fixtures ─────────────────────────────────────────────────────────────────

SAMPLE_RESUME = {
    "name": "Alex Rivera",
    "email": "alex@example.com",
    "phone": "555-1234",
    "career_summary": "Experienced Customer Success Manager with a track record of growth.",
    "skills": ["Salesforce", "Python", "customer success"],
    "experience": [
        {
            "title": "Customer Success Manager",
            "company": "Acme Corp",
            "start_date": "2021",
            "end_date": "present",
            "bullets": [
                "Managed a portfolio of 120 enterprise accounts.",
                "Reduced churn by 18% through proactive outreach.",
            ],
        },
        {
            "title": "Support Engineer",
            "company": "Beta Inc",
            "start_date": "2018",
            "end_date": "2021",
            "bullets": ["Resolved escalations for top-tier clients."],
        },
    ],
    "education": [
        {
            "degree": "B.S.",
            "field": "Computer Science",
            "institution": "State University",
            "graduation_year": "2018",
        }
    ],
    "achievements": [],
}

SAMPLE_JD = (
    "We are looking for a Customer Success Manager with Gainsight, cross-functional "
    "leadership experience, and strong stakeholder management skills. AWS knowledge a plus."
)


# ── extract_jd_signals ────────────────────────────────────────────────────────

def test_extract_jd_signals_returns_list():
    """extract_jd_signals returns a list even when LLM and TF-IDF both fail."""
    from scripts.resume_optimizer import extract_jd_signals

    with patch("scripts.llm_router.LLMRouter") as MockRouter:
        MockRouter.return_value.complete.side_effect = Exception("no LLM")
        result = extract_jd_signals(SAMPLE_JD, resume_text="Python developer")

    assert isinstance(result, list)


def test_extract_jd_signals_llm_path_parses_json_array():
    """extract_jd_signals merges LLM-extracted signals with TF-IDF gaps."""
    from scripts.resume_optimizer import extract_jd_signals

    llm_response = '["Gainsight", "cross-functional leadership", "stakeholder management"]'

    with patch("scripts.llm_router.LLMRouter") as MockRouter:
        MockRouter.return_value.complete.return_value = llm_response
        result = extract_jd_signals(SAMPLE_JD)

    assert "Gainsight" in result
    assert "cross-functional leadership" in result


def test_extract_jd_signals_deduplicates():
    """extract_jd_signals deduplicates terms across LLM and TF-IDF sources."""
    from scripts.resume_optimizer import extract_jd_signals

    llm_response = '["Python", "AWS", "Python"]'

    with patch("scripts.llm_router.LLMRouter") as MockRouter:
        MockRouter.return_value.complete.return_value = llm_response
        result = extract_jd_signals(SAMPLE_JD)

    assert result.count("Python") == 1


def test_extract_jd_signals_handles_malformed_llm_json():
    """extract_jd_signals falls back gracefully when LLM returns non-JSON."""
    from scripts.resume_optimizer import extract_jd_signals

    with patch("scripts.llm_router.LLMRouter") as MockRouter:
        MockRouter.return_value.complete.return_value = "Here are some keywords: Gainsight, AWS"
        result = extract_jd_signals(SAMPLE_JD)

    # Should still return a list (may be empty if TF-IDF also silent)
    assert isinstance(result, list)


# ── prioritize_gaps ───────────────────────────────────────────────────────────

def test_prioritize_gaps_skips_existing_terms():
    """prioritize_gaps excludes terms already present in the resume."""
    from scripts.resume_optimizer import prioritize_gaps

    # "Salesforce" is already in SAMPLE_RESUME skills
    result = prioritize_gaps(["Salesforce", "Gainsight"], SAMPLE_RESUME)
    terms = [r["term"] for r in result]

    assert "Salesforce" not in terms
    assert "Gainsight" in terms


def test_prioritize_gaps_routes_tech_terms_to_skills():
    """prioritize_gaps maps known tech keywords to the skills section at priority 1."""
    from scripts.resume_optimizer import prioritize_gaps

    result = prioritize_gaps(["AWS", "Docker"], SAMPLE_RESUME)
    by_term = {r["term"]: r for r in result}

    assert by_term["AWS"]["section"] == "skills"
    assert by_term["AWS"]["priority"] == 1
    assert by_term["Docker"]["section"] == "skills"


def test_prioritize_gaps_routes_leadership_terms_to_summary():
    """prioritize_gaps maps leadership/executive signals to the summary section."""
    from scripts.resume_optimizer import prioritize_gaps

    result = prioritize_gaps(["cross-functional", "stakeholder"], SAMPLE_RESUME)
    by_term = {r["term"]: r for r in result}

    assert by_term["cross-functional"]["section"] == "summary"
    assert by_term["stakeholder"]["section"] == "summary"


def test_prioritize_gaps_multi_word_routes_to_experience():
    """Multi-word phrases not in skills/summary lists go to experience at priority 2."""
    from scripts.resume_optimizer import prioritize_gaps

    result = prioritize_gaps(["proactive client engagement"], SAMPLE_RESUME)
    assert result[0]["section"] == "experience"
    assert result[0]["priority"] == 2


def test_prioritize_gaps_single_word_is_lowest_priority():
    """Single generic words not in any list go to experience at priority 3."""
    from scripts.resume_optimizer import prioritize_gaps

    result = prioritize_gaps(["innovation"], SAMPLE_RESUME)
    assert result[0]["priority"] == 3


def test_prioritize_gaps_sorted_by_priority():
    """prioritize_gaps output is sorted ascending by priority (1 first)."""
    from scripts.resume_optimizer import prioritize_gaps

    gaps = ["innovation", "AWS", "cross-functional", "managed service contracts"]
    result = prioritize_gaps(gaps, SAMPLE_RESUME)
    priorities = [r["priority"] for r in result]

    assert priorities == sorted(priorities)


# ── hallucination_check ───────────────────────────────────────────────────────

def test_hallucination_check_passes_unchanged_resume():
    """hallucination_check returns True when rewrite has no new employers or institutions."""
    from scripts.resume_optimizer import hallucination_check

    # Shallow rewrite: same structure
    rewritten = {
        **SAMPLE_RESUME,
        "career_summary": "Dynamic CSM with cross-functional stakeholder management experience.",
    }
    assert hallucination_check(SAMPLE_RESUME, rewritten) is True


def test_hallucination_check_fails_on_new_employer():
    """hallucination_check returns False when a new company is introduced."""
    from scripts.resume_optimizer import hallucination_check

    fabricated_entry = {
        "title": "VP of Customer Success",
        "company": "Fabricated Corp",
        "start_date": "2019",
        "end_date": "2021",
        "bullets": ["Led a team of 30."],
    }
    rewritten = dict(SAMPLE_RESUME)
    rewritten["experience"] = SAMPLE_RESUME["experience"] + [fabricated_entry]

    assert hallucination_check(SAMPLE_RESUME, rewritten) is False


def test_hallucination_check_fails_on_new_institution():
    """hallucination_check returns False when a new educational institution appears."""
    from scripts.resume_optimizer import hallucination_check

    rewritten = dict(SAMPLE_RESUME)
    rewritten["education"] = [
        *SAMPLE_RESUME["education"],
        {"degree": "M.S.", "field": "Data Science", "institution": "MIT", "graduation_year": "2020"},
    ]

    assert hallucination_check(SAMPLE_RESUME, rewritten) is False


# ── render_resume_text ────────────────────────────────────────────────────────

def test_render_resume_text_contains_all_sections():
    """render_resume_text produces plain text containing all resume sections."""
    from scripts.resume_optimizer import render_resume_text

    text = render_resume_text(SAMPLE_RESUME)

    assert "Alex Rivera" in text
    assert "SUMMARY" in text
    assert "EXPERIENCE" in text
    assert "Customer Success Manager" in text
    assert "Acme Corp" in text
    assert "EDUCATION" in text
    assert "State University" in text
    assert "SKILLS" in text
    assert "Salesforce" in text


def test_render_resume_text_omits_empty_sections():
    """render_resume_text skips sections that have no content."""
    from scripts.resume_optimizer import render_resume_text

    sparse = {
        "name": "Jordan Lee",
        "email": "",
        "phone": "",
        "career_summary": "",
        "skills": [],
        "experience": [],
        "education": [],
        "achievements": [],
    }
    text = render_resume_text(sparse)

    assert "EXPERIENCE" not in text
    assert "SKILLS" not in text


# ── db integration ────────────────────────────────────────────────────────────

def test_save_and_get_optimized_resume(tmp_path):
    """save_optimized_resume persists and get_optimized_resume retrieves the data."""
    from scripts.db import init_db, save_optimized_resume, get_optimized_resume

    db_path = tmp_path / "test.db"
    init_db(db_path)

    # Insert a minimal job to satisfy FK
    import sqlite3
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO jobs (id, title, company, url, source, status) VALUES (1, 'CSM', 'Acme', 'http://x.com', 'test', 'approved')"
    )
    conn.commit()
    conn.close()

    gap_report = json.dumps([{"term": "Gainsight", "section": "skills", "priority": 1, "rationale": "test"}])
    save_optimized_resume(db_path, job_id=1, text="Rewritten resume text.", gap_report=gap_report)

    result = get_optimized_resume(db_path, job_id=1)
    assert result["optimized_resume"] == "Rewritten resume text."
    parsed = json.loads(result["ats_gap_report"])
    assert parsed[0]["term"] == "Gainsight"


def test_get_optimized_resume_returns_empty_for_missing(tmp_path):
    """get_optimized_resume returns empty strings when no record exists."""
    from scripts.db import init_db, get_optimized_resume

    db_path = tmp_path / "test.db"
    init_db(db_path)

    result = get_optimized_resume(db_path, job_id=999)
    assert result["optimized_resume"] == ""
    assert result["ats_gap_report"] == ""
