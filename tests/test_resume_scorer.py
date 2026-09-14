from unittest.mock import patch, MagicMock
from scripts.resume_scorer import score_resume, score_ats_hygiene

SAMPLE_STRUCT = {
    "name": "Jane Doe",
    "career_summary": "Experienced developer.",
    "experience": [
        {"title": "Senior Developer", "company": "Acme Corp",
         "start_date": "2020", "end_date": "Present",
         "bullets": ["Responsible for managing a team"]},
    ],
    "education": [{"institution": "State University", "degree": "BS", "field": "CS"}],
    "skills": ["Python", "SQL"],
    "achievements": [],
}


def test_score_resume_returns_expected_shape():
    fake_llm_json = (
        '{"overall_score": 7, "summary": "Solid resume with room to grow.", '
        '"strengths": ["Clear job history"], '
        '"improvements": ["Summary is generic"], '
        '"suggestions": [{"id": "sugg-1", "section": "experience", '
        '"target": "Acme Corp|Senior Developer", '
        '"before": "Responsible for managing a team", '
        '"after": "Led a team of 6 engineers, cutting deploy time 40%", '
        '"rationale": "Quantifies impact."}]}'
    )
    with patch("scripts.resume_scorer.LLMRouter") as mock_router_cls:
        mock_router_cls.return_value.complete.return_value = fake_llm_json
        result = score_resume(SAMPLE_STRUCT)

    assert result["overall_score"] == 7
    assert result["summary"] == "Solid resume with room to grow."
    assert result["strengths"] == ["Clear job history"]
    assert result["improvements"] == ["Summary is generic"]
    assert len(result["suggestions"]) == 1
    sugg = result["suggestions"][0]
    assert sugg["before"] == "Responsible for managing a team"
    assert sugg["after"] == "Led a team of 6 engineers, cutting deploy time 40%"
    assert sugg["appliable"] is True


def test_score_resume_marks_hallucinated_suggestion_not_appliable():
    fake_llm_json = (
        '{"overall_score": 5, "summary": "x", "strengths": [], "improvements": [], '
        '"suggestions": [{"id": "sugg-1", "section": "experience", '
        '"target": "Globex Inc|CTO", '
        '"before": "Responsible for managing a team", '
        '"after": "Served as CTO of Globex Inc", "rationale": "x"}]}'
    )
    with patch("scripts.resume_scorer.LLMRouter") as mock_router_cls:
        mock_router_cls.return_value.complete.return_value = fake_llm_json
        result = score_resume(SAMPLE_STRUCT)

    assert result["suggestions"][0]["appliable"] is False


def test_score_ats_hygiene_with_recent_jobs_states_basis():
    recent = ["We need a Python developer with SQL experience.", "Looking for a backend engineer."]
    result = score_ats_hygiene(SAMPLE_STRUCT, recent)
    assert result["ats_basis"] == "based on your 2 most recently saved jobs"
    assert isinstance(result["ats_score"], int)
    assert isinstance(result["ats_issues"], list)


def test_score_ats_hygiene_with_no_history_uses_fallback_basis():
    result = score_ats_hygiene(SAMPLE_STRUCT, [])
    assert result["ats_basis"] == "general ATS best practices — save some jobs to sharpen this"
    assert isinstance(result["ats_score"], int)
