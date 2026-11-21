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


def _run(db_path, gaps, selected=None):
    """Run the resume_optimize task body with a fake router and fixed gap terms."""
    from scripts.task_runner import _run_task
    job_id = _job_id(db_path)
    params = {"full_rewrite": True}
    if selected is not None:
        params["selected_gaps"] = selected
    params_json = json.dumps(params)
    task_id, _ = insert_task(db_path, "resume_optimize", job_id, params_json)
    with patch("scripts.llm_router.LLMRouter", FakeRouter), \
         patch("scripts.resume_optimizer.extract_jd_signals",
               return_value=[g["term"] for g in gaps]), \
         patch("scripts.resume_optimizer.prioritize_gaps", return_value=gaps):
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
