from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
import yaml


def _cfg_dir(tmp_path):
    cfg = tmp_path / "config"
    cfg.mkdir()
    return cfg


def _redirect_llm_router_config(monkeypatch, cfg):
    """LLMRouter() with no explicit config_path resolves against its own
    search path (<repo>/config/llm.yaml, then ~/.config/circuitforge/llm.yaml)
    -- independent of dev_api._config_dir(). In production those two happen
    to be the same directory (the repo's install dir doubles as STAGING_DB's
    parent), but in a test with an isolated tmp_path they diverge, so
    complete_task() would never see the task_models this test writes into
    cfg/llm.yaml. Redirect LLMRouter()'s default resolution to cfg for the
    duration of the test so it matches dev_api._config_dir(), same as
    production."""
    import scripts.llm_router as llm_router_module
    real_cls = llm_router_module.LLMRouter

    def _factory(config_path=None):
        return real_cls(config_path or (cfg / "llm.yaml"))

    monkeypatch.setattr(llm_router_module, "LLMRouter", _factory)


def test_generate_summary_returns_400_when_no_research_model_assigned(tmp_path, monkeypatch):
    import dev_api
    cfg = _cfg_dir(tmp_path)
    (cfg / "plain_text_resume.yaml").write_text(yaml.dump({"skills": ["Python"], "experience": [{"title": "Engineer"}]}))
    monkeypatch.setattr(dev_api, "_config_dir", lambda: cfg)
    monkeypatch.setattr(dev_api, "_resume_path", lambda: cfg / "plain_text_resume.yaml")
    client = TestClient(dev_api.app)
    resp = client.post("/api/settings/profile/generate-summary")
    assert resp.status_code == 400
    assert "Research" in resp.json()["detail"]


def test_generate_summary_returns_502_when_research_backend_unreachable(tmp_path, monkeypatch):
    import dev_api
    from scripts.llm_router import LLMRouter as RealLLMRouter
    cfg = _cfg_dir(tmp_path)
    (cfg / "plain_text_resume.yaml").write_text(yaml.dump({"skills": ["Python"], "experience": [{"title": "Engineer"}]}))
    (cfg / "llm.yaml").write_text(yaml.dump({
        "backends": {"ollama": {"type": "openai_compat", "model": "m", "enabled": True}},
        "task_models": {"research": {"backend": "ollama", "model": "llama3.1:8b"}},
    }))
    monkeypatch.setattr(dev_api, "_config_dir", lambda: cfg)
    monkeypatch.setattr(dev_api, "_resume_path", lambda: cfg / "plain_text_resume.yaml")
    _redirect_llm_router_config(monkeypatch, cfg)
    client = TestClient(dev_api.app)
    with patch.object(RealLLMRouter, "complete", side_effect=RuntimeError("down")):
        resp = client.post("/api/settings/profile/generate-summary")
    assert resp.status_code == 502
    assert "ollama" in resp.json()["detail"]


def test_generate_summary_succeeds_with_assigned_research_model(tmp_path, monkeypatch):
    import dev_api
    from scripts.llm_router import LLMRouter as RealLLMRouter
    cfg = _cfg_dir(tmp_path)
    (cfg / "plain_text_resume.yaml").write_text(yaml.dump({"skills": ["Python"], "experience": [{"title": "Engineer"}]}))
    (cfg / "llm.yaml").write_text(yaml.dump({
        "backends": {"ollama": {"type": "openai_compat", "model": "m", "enabled": True}},
        "task_models": {"research": {"backend": "ollama", "model": "llama3.1:8b"}},
    }))
    monkeypatch.setattr(dev_api, "_config_dir", lambda: cfg)
    monkeypatch.setattr(dev_api, "_resume_path", lambda: cfg / "plain_text_resume.yaml")
    _redirect_llm_router_config(monkeypatch, cfg)
    client = TestClient(dev_api.app)
    with patch.object(RealLLMRouter, "complete", return_value="A concise summary."):
        resp = client.post("/api/settings/profile/generate-summary")
    assert resp.status_code == 200
    assert resp.json()["summary"] == "A concise summary."


def _mock_job_row():
    """suggest_qa_answer reads job_row['title']/['company']/['description'] --
    a plain dict satisfies that (sqlite3.Row and dict both support __getitem__)."""
    return {"title": "Backend Engineer", "company": "Acme Corp", "description": "Build things."}


def test_suggest_qa_answer_returns_400_when_no_chat_model_assigned(tmp_path, monkeypatch):
    import dev_api
    cfg = _cfg_dir(tmp_path)
    monkeypatch.setattr(dev_api, "_config_dir", lambda: cfg)
    monkeypatch.setattr(dev_api, "_resume_path", lambda: cfg / "plain_text_resume.yaml")
    mock_db = MagicMock()
    mock_db.execute.return_value.fetchone.return_value = _mock_job_row()
    monkeypatch.setattr(dev_api, "_get_db", lambda: mock_db)
    client = TestClient(dev_api.app)
    resp = client.post("/api/jobs/1/qa/suggest", json={"question": "Why do you want this job?"})
    assert resp.status_code == 400
    assert "Chat" in resp.json()["detail"]


def test_suggest_qa_answer_returns_502_when_chat_backend_unreachable(tmp_path, monkeypatch):
    import dev_api
    from scripts.llm_router import LLMRouter as RealLLMRouter
    cfg = _cfg_dir(tmp_path)
    (cfg / "llm.yaml").write_text(yaml.dump({
        "backends": {"ollama": {"type": "openai_compat", "model": "m", "enabled": True}},
        "task_models": {"chat": {"backend": "ollama", "model": "llama3.1:8b"}},
    }))
    monkeypatch.setattr(dev_api, "_config_dir", lambda: cfg)
    monkeypatch.setattr(dev_api, "_resume_path", lambda: cfg / "plain_text_resume.yaml")
    _redirect_llm_router_config(monkeypatch, cfg)
    mock_db = MagicMock()
    mock_db.execute.return_value.fetchone.return_value = _mock_job_row()
    monkeypatch.setattr(dev_api, "_get_db", lambda: mock_db)
    client = TestClient(dev_api.app)
    with patch.object(RealLLMRouter, "complete", side_effect=RuntimeError("down")):
        resp = client.post("/api/jobs/1/qa/suggest", json={"question": "Why do you want this job?"})
    assert resp.status_code == 502
    assert "ollama" in resp.json()["detail"]


def test_suggest_qa_answer_succeeds_with_assigned_chat_model(tmp_path, monkeypatch):
    import dev_api
    from scripts.llm_router import LLMRouter as RealLLMRouter
    cfg = _cfg_dir(tmp_path)
    (cfg / "llm.yaml").write_text(yaml.dump({
        "backends": {"ollama": {"type": "openai_compat", "model": "m", "enabled": True}},
        "task_models": {"chat": {"backend": "ollama", "model": "llama3.1:8b"}},
    }))
    monkeypatch.setattr(dev_api, "_config_dir", lambda: cfg)
    monkeypatch.setattr(dev_api, "_resume_path", lambda: cfg / "plain_text_resume.yaml")
    _redirect_llm_router_config(monkeypatch, cfg)
    mock_db = MagicMock()
    mock_db.execute.return_value.fetchone.return_value = _mock_job_row()
    monkeypatch.setattr(dev_api, "_get_db", lambda: mock_db)
    client = TestClient(dev_api.app)
    with patch.object(RealLLMRouter, "complete", return_value="I'm excited about this role."):
        resp = client.post("/api/jobs/1/qa/suggest", json={"question": "Why do you want this job?"})
    assert resp.status_code == 200
    assert resp.json()["answer"] == "I'm excited about this role."
