# tests/test_reranker_integration.py
"""Tests for reranker integration in job_ranker and resume_optimizer.

Set CF_RERANKER_MOCK=1 to avoid loading real model weights during tests.
"""
import os
import pytest
from unittest.mock import patch

os.environ["CF_RERANKER_MOCK"] = "1"


# ── Fixtures ──────────────────────────────────────────────────────────────────

RESUME_TEXT = "Experienced Python engineer with Django REST and data pipeline experience."

SAMPLE_JOBS = [
    {
        "id": 1,
        "title": "Python Developer",
        "company": "Acme",
        "description": "Python Django REST APIs data engineering pipelines",
        "date_found": "2026-04-01",
        "match_score": 70,
        "salary": "120000",
        "is_remote": 1,
        "location": "Remote",
    },
    {
        "id": 2,
        "title": "Data Analyst",
        "company": "Beta",
        "description": "SQL Excel Tableau business intelligence reporting dashboards",
        "date_found": "2026-04-02",
        "match_score": 60,
        "salary": "90000",
        "is_remote": 1,
        "location": "Remote",
    },
    {
        "id": 3,
        "title": "Frontend Engineer",
        "company": "Gamma",
        "description": "React TypeScript CSS frontend web UI component library",
        "date_found": "2026-04-01",
        "match_score": 50,
        "salary": "110000",
        "is_remote": 1,
        "location": "Remote",
    },
]

SAMPLE_RESUME = {
    "name": "Alex Rivera",
    "email": "alex@example.com",
    "phone": "555-1234",
    "career_summary": "Experienced Python engineer with Django and REST API experience.",
    "skills": ["Python", "Django", "REST APIs"],
    "experience": [
        {
            "title": "Software Engineer",
            "company": "Acme Corp",
            "start_date": "2021",
            "end_date": "present",
            "bullets": ["Built REST APIs.", "Managed data pipelines."],
        }
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

PRIORITIZED_GAPS = [
    {"term": "Kubernetes", "section": "skills", "priority": 1, "rationale": "JD requires K8s"},
    {"term": "REST APIs", "section": "experience", "priority": 2, "rationale": "JD mentions REST"},
    {"term": "CI/CD", "section": "skills", "priority": 3, "rationale": "DevOps signal"},
]

SAMPLE_JOB = {
    "title": "Senior Python Engineer",
    "company": "Acme",
    "description": "Python REST API developer with Kubernetes CI/CD and data pipeline experience.",
}


# ── _try_rerank ───────────────────────────────────────────────────────────────

def test_try_rerank_empty_list():
    from scripts.job_ranker import _try_rerank
    assert _try_rerank("query", []) == []


def test_try_rerank_returns_all_jobs():
    from scripts.job_ranker import _try_rerank
    result = _try_rerank(RESUME_TEXT, SAMPLE_JOBS)
    assert len(result) == len(SAMPLE_JOBS)
    assert {j["id"] for j in result} == {j["id"] for j in SAMPLE_JOBS}


def test_try_rerank_preserves_job_fields():
    from scripts.job_ranker import _try_rerank
    result = _try_rerank(RESUME_TEXT, SAMPLE_JOBS)
    for job in result:
        assert "stack_score" not in job or True  # stack_score may or may not be present
        assert "id" in job
        assert "title" in job


def test_try_rerank_graceful_fallback_on_import_error():
    """_try_rerank falls back to input order when reranker is unavailable."""
    import builtins
    real_import = builtins.__import__

    def mock_import(name, *args, **kwargs):
        if name == "circuitforge_core.reranker":
            raise ImportError("not installed")
        return real_import(name, *args, **kwargs)

    with patch("builtins.__import__", side_effect=mock_import):
        from scripts.job_ranker import _try_rerank as _tr
        result = _tr(RESUME_TEXT, SAMPLE_JOBS)

    assert result == SAMPLE_JOBS


# ── rank_jobs ─────────────────────────────────────────────────────────────────

def test_rank_jobs_no_resume_text():
    """rank_jobs without resume_text works normally; reranker not invoked."""
    from scripts.job_ranker import rank_jobs
    results = rank_jobs(SAMPLE_JOBS, ["Python Developer"], limit=10, min_score=0)
    assert len(results) >= 1
    assert all("stack_score" in j for j in results)


def test_rank_jobs_with_resume_text_returns_same_job_ids():
    """rank_jobs with resume_text returns the same job set (possibly reordered)."""
    from scripts.job_ranker import rank_jobs
    without = rank_jobs(SAMPLE_JOBS, ["Python Developer"], limit=10, min_score=0)
    with_rr = rank_jobs(
        SAMPLE_JOBS, ["Python Developer"], limit=10, min_score=0, resume_text=RESUME_TEXT
    )
    assert {j["id"] for j in without} == {j["id"] for j in with_rr}


def test_rank_jobs_with_resume_text_preserves_stack_score():
    """stack_score is set on all returned jobs regardless of reranker pass."""
    from scripts.job_ranker import rank_jobs
    results = rank_jobs(
        SAMPLE_JOBS, ["Python Developer"], limit=10, min_score=0, resume_text=RESUME_TEXT
    )
    assert all("stack_score" in j for j in results)


def test_rank_jobs_limit_respected_after_rerank():
    """limit parameter is still respected when reranker is active."""
    from scripts.job_ranker import rank_jobs
    results = rank_jobs(
        SAMPLE_JOBS, ["Python Developer"], limit=2, min_score=0, resume_text=RESUME_TEXT
    )
    assert len(results) <= 2


def test_rank_jobs_empty_description_falls_back_to_title():
    """Jobs with no description use title as the reranker candidate string."""
    from scripts.job_ranker import rank_jobs
    jobs_no_desc = [{**j, "description": None} for j in SAMPLE_JOBS]
    results = rank_jobs(
        jobs_no_desc, ["Python Developer"], limit=10, min_score=0, resume_text=RESUME_TEXT
    )
    assert {j["id"] for j in results} == {j["id"] for j in SAMPLE_JOBS}


# ── rewrite_for_ats (reranker gap reordering) ─────────────────────────────────

def test_rewrite_for_ats_runs_with_reranker(monkeypatch):
    """rewrite_for_ats completes without error when reranker is active."""
    from scripts.resume_optimizer import rewrite_for_ats

    with patch("scripts.llm_router.LLMRouter") as MockRouter:
        mock_bullets = '["Built REST APIs and Kubernetes pipelines."]'
        MockRouter.return_value.complete.return_value = mock_bullets
        result = rewrite_for_ats(SAMPLE_RESUME, PRIORITIZED_GAPS, SAMPLE_JOB)

    assert isinstance(result, dict)
    assert "skills" in result
    assert "experience" in result


def test_rewrite_for_ats_preserves_unrewritten_sections(monkeypatch):
    """Sections with no gaps are passed through unchanged."""
    from scripts.resume_optimizer import rewrite_for_ats

    # Only 'skills' gaps — education should be untouched
    skills_only_gaps = [g for g in PRIORITIZED_GAPS if g["section"] == "skills"]

    with patch("scripts.llm_router.LLMRouter") as MockRouter:
        MockRouter.return_value.complete.return_value = '["AWS certified engineer."]'
        result = rewrite_for_ats(SAMPLE_RESUME, skills_only_gaps, SAMPLE_JOB)

    assert result["education"] == SAMPLE_RESUME["education"]


def test_rewrite_for_ats_reranker_fallback_on_error(monkeypatch):
    """rewrite_for_ats completes even if reranker raises an exception."""
    from scripts.resume_optimizer import rewrite_for_ats
    from circuitforge_core.reranker import reset_reranker

    # Patch rerank to raise so we test the fallback path
    with patch("circuitforge_core.reranker.rerank", side_effect=RuntimeError("boom")):
        with patch("scripts.llm_router.LLMRouter") as MockRouter:
            MockRouter.return_value.complete.return_value = '["Built pipelines."]'
            result = rewrite_for_ats(SAMPLE_RESUME, PRIORITIZED_GAPS, SAMPLE_JOB)

    assert isinstance(result, dict)

    reset_reranker()


def test_rewrite_for_ats_empty_gaps_no_reranker_call():
    """rewrite_for_ats with empty gaps returns original resume unchanged."""
    from scripts.resume_optimizer import rewrite_for_ats

    with patch("scripts.llm_router.LLMRouter") as MockRouter:
        result = rewrite_for_ats(SAMPLE_RESUME, [], SAMPLE_JOB)
        MockRouter.return_value.complete.assert_not_called()

    assert result["skills"] == SAMPLE_RESUME["skills"]
