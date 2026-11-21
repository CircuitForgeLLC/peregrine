"""The optimize task honours the user's gap selection and only uses backed terms."""

import json
import sqlite3
from typing import ClassVar
from unittest.mock import patch

import pytest
import yaml
from fastapi.testclient import TestClient

from scripts.db import get_resume_draft, insert_job, insert_task
from scripts.db_migrate import migrate_db
from scripts.experience_facts import add_fact

USER_WORDS = "I built the weekly rota for twelve staff."
SUMMARY = "Organised the front desk and kept things running."
CLEAN_REPLY = "Organised the front desk and built the weekly scheduling rota."


@pytest.fixture()
def db_path(tmp_path):
    path = tmp_path / "staging.db"
    migrate_db(path)
    insert_job(path, {
        "title": "Coordinator", "company": "Acme", "url": "https://example.test/job/1",
        "source": "manual", "location": "Remote", "is_remote": True,
        "salary": "", "description": "Needs scheduling and fitness coaching.",
        "date_found": "2026-11-20",
    })
    cfg = tmp_path / "config"
    cfg.mkdir()
    (cfg / "plain_text_resume.yaml").write_text(yaml.safe_dump({
        "career_summary": SUMMARY, "skills": ["Excel"], "experience": [],
    }))
    return path


@pytest.fixture()
def client(db_path, tmp_path, monkeypatch):
    monkeypatch.setattr("dev_api.DB_PATH", db_path)
    monkeypatch.setattr("dev_api._user_yaml_path", lambda: str(tmp_path / "no-profile" / "user.yaml"))
    from dev_api import app
    return TestClient(app)


def _job_id(db_path) -> int:
    con = sqlite3.connect(db_path)
    try:
        return con.execute("SELECT id FROM jobs LIMIT 1").fetchone()[0]
    finally:
        con.close()


class FakeRouter:
    prompts: ClassVar[list[str]] = []
    reply = CLEAN_REPLY

    def complete(self, prompt: str) -> str:
        FakeRouter.prompts.append(prompt)
        return FakeRouter.reply


@pytest.fixture(autouse=True)
def reset_router():
    FakeRouter.prompts = []
    FakeRouter.reply = CLEAN_REPLY
    yield


def _gap(term: str) -> dict:
    return {"term": term, "section": "summary", "priority": 1, "rationale": "x"}


_UNSET = object()


def _run(db_path, gaps, selected=None, approved=_UNSET, extracted=None, real_prioritize=False):
    """Run the resume_optimize task body with a fake router and fixed gap terms.

    gaps is what prioritize_gaps returns, unless real_prioritize is set. extracted is what
    the fresh extraction returns (defaults to the gap terms).
    """
    from contextlib import ExitStack

    from scripts.task_runner import _run_task
    job_id = _job_id(db_path)
    params = {"full_rewrite": True}
    if selected is not None:
        params["selected_gaps"] = selected
    if approved is not _UNSET:
        params["approved_terms"] = approved
    params_json = json.dumps(params)
    task_id, _ = insert_task(db_path, "resume_optimize", job_id, params_json)
    fresh = extracted if extracted is not None else [g["term"] for g in gaps]
    with ExitStack() as stack:
        stack.enter_context(patch("scripts.llm_router.LLMRouter", FakeRouter))
        stack.enter_context(patch("scripts.resume_optimizer.extract_jd_signals",
                                  return_value=fresh))
        if not real_prioritize:
            # Like the real function, only the terms passed in come back.
            stack.enter_context(patch(
                "scripts.resume_optimizer.prioritize_gaps",
                side_effect=lambda terms, _resume: [g for g in gaps if g["term"] in terms],
            ))
        _run_task(db_path, task_id, "resume_optimize", job_id, params_json)
    con = sqlite3.connect(db_path)
    try:
        status = con.execute(
            "SELECT status FROM background_tasks WHERE id=?", (task_id,)
        ).fetchone()[0]
    finally:
        con.close()
    return status, get_resume_draft(db_path, job_id)


def test_generate_passes_selected_gaps_into_the_task_params(client, db_path):
    job_id = _job_id(db_path)
    url = f"/api/jobs/{job_id}/resume_optimizer/generate"
    with patch("scripts.task_runner.submit_task", return_value=(1, True)) as submit:
        client.post(url, json={"full_rewrite": True, "selected_gaps": ["a", "b"]})
        client.post(url, json={"full_rewrite": True})
        client.post(url, json={"full_rewrite": True, "selected_gaps": []})
    with_gaps, without, empty = (json.loads(c.kwargs["params"]) for c in submit.call_args_list)
    assert with_gaps["selected_gaps"] == ["a", "b"]
    assert "selected_gaps" not in without
    assert empty["selected_gaps"] == []


def test_an_unchecked_gap_is_not_rewritten(db_path):
    add_fact(db_path, kind="experience", requirement="scheduling", text=USER_WORDS)
    add_fact(db_path, kind="experience", requirement="fitness coaching",
             text="I coached the office running club.")
    gaps = [_gap("scheduling"), _gap("fitness coaching")]
    status, _draft = _run(db_path, gaps, selected=["scheduling"])
    assert status == "awaiting_review"
    assert len(FakeRouter.prompts) == 1
    assert "scheduling" in FakeRouter.prompts[0]
    assert "fitness coaching" not in FakeRouter.prompts[0]
    assert "running club" not in FakeRouter.prompts[0]


def test_only_backed_terms_reach_the_rewrite(db_path):
    add_fact(db_path, kind="experience", requirement="scheduling", text=USER_WORDS)
    gaps = [_gap("fitness coaching"), _gap("scheduling")]
    _status, draft = _run(db_path, gaps)
    assert len(FakeRouter.prompts) == 1
    assert "fitness coaching" not in FakeRouter.prompts[0]
    assert USER_WORDS in FakeRouter.prompts[0]
    assert draft["claims_report"]["unused_terms"] == ["fitness coaching"]


def test_the_draft_carries_a_claims_report(db_path):
    add_fact(db_path, kind="experience", requirement="scheduling", text=USER_WORDS)
    FakeRouter.reply = CLEAN_REPLY + " Also zumba."
    _status, draft = _run(db_path, [_gap("scheduling"), _gap("fitness coaching")])
    report = draft["claims_report"]
    assert report["unused_terms"] == ["fitness coaching"]
    assert "zumba" in report["novel_words"]
    assert "rota" not in report["novel_words"]


def test_no_facts_means_an_unchanged_draft_and_the_task_still_reaches_awaiting_review(db_path):
    gaps = [_gap("scheduling"), _gap("fitness coaching")]
    status, draft = _run(db_path, gaps)
    assert status == "awaiting_review"
    assert FakeRouter.prompts == []
    assert draft["claims_report"] == {
        "novel_words": [], "unused_terms": ["scheduling", "fitness coaching"],
    }
    assert draft["rewritten_struct"]["career_summary"] == SUMMARY


# ── Final review fix wave ──────────────────────────────────────────────────────

CLUB_WORDS = "I coached the office running club."
BOTH = ["scheduling", "fitness coaching"]


def test_generate_passes_approved_terms_into_the_task_params(client, db_path):
    job_id = _job_id(db_path)
    url = f"/api/jobs/{job_id}/resume_optimizer/generate"
    with patch("scripts.task_runner.submit_task", return_value=(1, True)) as submit:
        client.post(url, json={"full_rewrite": True, "selected_gaps": ["a", "b"],
                               "approved_terms": ["a"]})
        client.post(url, json={"full_rewrite": True, "selected_gaps": ["a"]})
        client.post(url, json={"full_rewrite": True, "selected_gaps": ["a"], "approved_terms": []})
    present, absent, empty = (json.loads(c.kwargs["params"]) for c in submit.call_args_list)
    assert present == {"full_rewrite": True, "selected_gaps": ["a", "b"], "approved_terms": ["a"]}
    assert "approved_terms" not in absent
    assert empty["approved_terms"] == []


def test_generate_refuses_oversized_selected_gaps_with_422(client, db_path):
    job_id = _job_id(db_path)
    url = f"/api/jobs/{job_id}/resume_optimizer/generate"
    bad_lists = [["x" * 121], [f"t{i}" for i in range(101)], [""]]
    with patch("scripts.task_runner.submit_task", return_value=(1, True)) as submit:
        for bad in bad_lists:
            r = client.post(url, json={"full_rewrite": True, "selected_gaps": bad})
            assert r.status_code == 422, bad
            r = client.post(url, json={"full_rewrite": True, "selected_gaps": ["a"],
                                       "approved_terms": bad})
            assert r.status_code == 422, bad
        ok = client.post(url, json={"full_rewrite": True, "selected_gaps": ["x" * 120],
                                    "approved_terms": [f"t{i}" for i in range(100)]})
        assert ok.status_code == 200
    assert submit.call_count == 1


def test_skip_with_a_saved_matching_fact_is_not_in_the_prompt(db_path):
    add_fact(db_path, kind="experience", requirement="scheduling", text=USER_WORDS)
    add_fact(db_path, kind="experience", requirement="fitness coaching", text=CLUB_WORDS)
    gaps = [_gap(t) for t in BOTH]
    status, draft = _run(db_path, gaps, selected=BOTH, approved=["scheduling"])
    assert status == "awaiting_review"
    assert len(FakeRouter.prompts) == 1
    assert USER_WORDS in FakeRouter.prompts[0]
    assert "fitness coaching" not in FakeRouter.prompts[0]
    assert "running club" not in FakeRouter.prompts[0]
    assert draft["claims_report"]["unused_terms"] == ["fitness coaching"]


def test_a_no_answer_with_a_related_saved_fact_is_not_in_the_prompt(db_path):
    add_fact(db_path, kind="experience", requirement="scheduling", text=USER_WORDS)
    add_fact(db_path, kind="adjacent", requirement="fitness coaching classes", text=CLUB_WORDS)
    add_fact(db_path, kind="none", requirement="fitness coaching")
    gaps = [_gap(t) for t in BOTH]
    for approved in (["scheduling"], _UNSET):
        FakeRouter.prompts = []
        _status, draft = _run(db_path, gaps, selected=BOTH, approved=approved)
        assert len(FakeRouter.prompts) == 1
        assert "running club" not in FakeRouter.prompts[0]
        assert "fitness coaching" not in FakeRouter.prompts[0]
        assert draft["claims_report"]["unused_terms"] == ["fitness coaching"]


def test_a_private_answer_with_a_related_saved_fact_is_not_in_the_prompt(db_path):
    add_fact(db_path, kind="experience", requirement="scheduling", text=USER_WORDS)
    add_fact(db_path, kind="adjacent", requirement="fitness coaching classes", text=CLUB_WORDS)
    add_fact(db_path, kind="experience", requirement="fitness coaching",
             text="PRIVATE words", visibility="private")
    gaps = [_gap(t) for t in BOTH]
    for approved in (["scheduling"], _UNSET):
        FakeRouter.prompts = []
        _status, draft = _run(db_path, gaps, selected=BOTH, approved=approved)
        assert len(FakeRouter.prompts) == 1
        assert "running club" not in FakeRouter.prompts[0]
        assert "PRIVATE words" not in FakeRouter.prompts[0]
        assert draft["claims_report"]["unused_terms"] == ["fitness coaching"]


def test_empty_approved_terms_means_no_facts_and_no_model_call(db_path):
    add_fact(db_path, kind="experience", requirement="scheduling", text=USER_WORDS)
    add_fact(db_path, kind="experience", requirement="fitness coaching", text=CLUB_WORDS)
    status, draft = _run(db_path, [_gap(t) for t in BOTH], selected=BOTH, approved=[])
    assert status == "awaiting_review"
    assert FakeRouter.prompts == []
    assert draft["claims_report"] == {"novel_words": [], "unused_terms": BOTH}
    assert draft["rewritten_struct"]["career_summary"] == SUMMARY


def test_missing_approved_terms_keeps_the_old_behaviour(db_path):
    add_fact(db_path, kind="experience", requirement="scheduling", text=USER_WORDS)
    add_fact(db_path, kind="experience", requirement="fitness coaching", text=CLUB_WORDS)
    status, draft = _run(db_path, [_gap(t) for t in BOTH], selected=BOTH)
    assert status == "awaiting_review"
    assert len(FakeRouter.prompts) == 1
    assert USER_WORDS in FakeRouter.prompts[0]
    assert CLUB_WORDS in FakeRouter.prompts[0]
    assert draft["claims_report"]["unused_terms"] == []


def test_approved_terms_match_after_normalisation(db_path):
    add_fact(db_path, kind="experience", requirement="scheduling", text=USER_WORDS)
    _status, draft = _run(db_path, [_gap("Scheduling")], selected=["Scheduling"],
                          approved=["  SCHEDULING "])
    assert len(FakeRouter.prompts) == 1
    assert USER_WORDS in FakeRouter.prompts[0]
    assert draft["claims_report"]["unused_terms"] == []


def test_the_users_selected_terms_are_used_even_if_the_fresh_extraction_differs(db_path):
    add_fact(db_path, kind="experience", requirement="Kubernetes", text="Ran clusters for the clinic.")
    _status, draft = _run(db_path, [], selected=["Kubernetes", "payroll"],
                          approved=["Kubernetes"], extracted=["Kubernetes (K8s)"],
                          real_prioritize=True)
    assert len(FakeRouter.prompts) == 1
    assert "Ran clusters for the clinic." in FakeRouter.prompts[0]
    assert draft["claims_report"]["unused_terms"] == ["payroll"]


def test_selected_gaps_empty_list_means_no_gaps_no_prompt_and_awaiting_review(db_path):
    add_fact(db_path, kind="experience", requirement="scheduling", text=USER_WORDS)
    status, draft = _run(db_path, [_gap(t) for t in BOTH], selected=[])
    assert status == "awaiting_review"
    assert FakeRouter.prompts == []
    assert draft["claims_report"] == {"novel_words": [], "unused_terms": []}
    assert draft["rewritten_struct"]["career_summary"] == SUMMARY


def test_the_task_watches_unticked_keywords_for_the_revert_check(db_path):
    add_fact(db_path, kind="experience", requirement="scheduling", text=USER_WORDS)
    FakeRouter.reply = CLEAN_REPLY + " Also fitness coaching."
    _status, draft = _run(db_path, [_gap(t) for t in BOTH], selected=["scheduling"],
                          approved=["scheduling"])
    assert len(FakeRouter.prompts) == 1
    assert draft["rewritten_struct"]["career_summary"] == SUMMARY
