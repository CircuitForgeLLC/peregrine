from unittest.mock import patch

from scripts.resume_scorer import apply_suggestion, score_ats_hygiene, score_resume

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


def test_apply_suggestion_replaces_matching_experience_bullet():
    struct = {
        "career_summary": "A developer.",
        "experience": [{"title": "Senior Developer", "company": "Acme Corp",
                         "bullets": ["Responsible for managing a team", "Other bullet"]}],
        "education": [], "skills": [], "achievements": [],
    }
    suggestion = {
        "section": "experience", "target": "Acme Corp|Senior Developer",
        "before": "Responsible for managing a team",
        "after": "Led a team of 6 engineers",
    }
    result = apply_suggestion(struct, suggestion)
    assert result["experience"][0]["bullets"] == ["Led a team of 6 engineers", "Other bullet"]
    # Original struct must be untouched (apply_suggestion returns a copy).
    assert struct["experience"][0]["bullets"][0] == "Responsible for managing a team"


def test_apply_suggestion_no_match_is_a_no_op():
    struct = {"career_summary": "x", "experience": [], "education": [], "skills": [], "achievements": []}
    suggestion = {"section": "summary", "before": "does not match", "after": "new text"}
    result = apply_suggestion(struct, suggestion)
    assert result["career_summary"] == "x"


# ── peregrine: apply-suggestion 422 on live cloud (found 2026-09-24) ──────────
# LLM-generated "before" text routinely differs from the live struct by
# whitespace alone even when asked to quote verbatim -- an exact `==` match
# treats that as "not found" and the caller (dev-api.py's apply-suggestion
# endpoint) turns that into a 422 telling the user to re-score, even though
# the target text genuinely IS present. These cover the specific classes of
# whitespace drift that a real LLM round-trip produces.

def test_apply_suggestion_summary_tolerates_trailing_whitespace():
    struct = {"career_summary": "A developer.  ", "experience": [], "education": [], "skills": [], "achievements": []}
    suggestion = {"section": "summary", "before": "A developer.", "after": "An experienced developer."}
    result = apply_suggestion(struct, suggestion)
    assert result["career_summary"] == "An experienced developer."


def test_apply_suggestion_bullet_tolerates_double_spaces():
    struct = {
        "career_summary": "x",
        "experience": [{"title": "Senior Developer", "company": "Acme Corp",
                         "bullets": ["Responsible for  managing a team"]}],
        "education": [], "skills": [], "achievements": [],
    }
    suggestion = {
        "section": "experience", "target": "Acme Corp|Senior Developer",
        "before": "Responsible for managing a team",  # single space, struct has double
        "after": "Led a team of 6 engineers",
    }
    result = apply_suggestion(struct, suggestion)
    assert result["experience"][0]["bullets"] == ["Led a team of 6 engineers"]


def test_apply_suggestion_bullet_tolerates_newline_vs_space():
    struct = {
        "career_summary": "x",
        "experience": [{"title": "Senior Developer", "company": "Acme Corp",
                         "bullets": ["Responsible for\nmanaging a team"]}],
        "education": [], "skills": [], "achievements": [],
    }
    suggestion = {
        "section": "experience", "target": "Acme Corp|Senior Developer",
        "before": "Responsible for managing a team",
        "after": "Led a team of 6 engineers",
    }
    result = apply_suggestion(struct, suggestion)
    assert result["experience"][0]["bullets"] == ["Led a team of 6 engineers"]


def test_apply_suggestion_skills_tolerates_leading_whitespace():
    struct = {"career_summary": "x", "experience": [], "education": [], "skills": [" Python", "SQL"], "achievements": []}
    suggestion = {"section": "skills", "before": "Python", "after": "Python (Django, FastAPI)"}
    result = apply_suggestion(struct, suggestion)
    assert result["skills"] == ["Python (Django, FastAPI)", "SQL"]


def test_apply_suggestion_still_no_op_when_text_genuinely_differs():
    """Whitespace-only tolerance must not become a fuzzy match -- a real
    content difference (not just whitespace) still correctly misses."""
    struct = {"career_summary": "A developer with 5 years experience.", "experience": [], "education": [], "skills": [], "achievements": []}
    suggestion = {"section": "summary", "before": "A developer with 10 years experience.", "after": "new text"}
    result = apply_suggestion(struct, suggestion)
    assert result["career_summary"] == "A developer with 5 years experience."
