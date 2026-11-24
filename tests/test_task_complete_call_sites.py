from unittest.mock import MagicMock, patch

import yaml
from fastapi.testclient import TestClient

import dev_api


def _cfg_dir(tmp_path):
    cfg = tmp_path / "config"
    cfg.mkdir()
    return cfg


def _redirect_llm_router_config(monkeypatch, cfg):
    """Make LLMRouter() inside the endpoints load `cfg/llm.yaml`.

    LLMRouter() with no explicit config_path resolves against its own search
    path (<repo>/config/llm.yaml, then ~/.config/circuitforge/llm.yaml). The
    task-models endpoints deliberately read/write that same file (see
    dev_api.LLM_ROUTER_CONFIG_PATH) -- it is NOT dev_api._config_dir(), which
    is the per-user data directory and a genuinely different path in the
    Docker deployment.

    Tests still need this redirect for isolation: without it the endpoints
    under test would load the developer's real repo config/llm.yaml, whose
    backends and fallback chains would change the outcome (complete_task()
    degrades gracefully to those chains when nothing is assigned).
    """
    import scripts.llm_router as llm_router_module
    real_cls = llm_router_module.LLMRouter

    def _factory(config_path=None):
        return real_cls(config_path or (cfg / "llm.yaml"))

    monkeypatch.setattr(llm_router_module, "LLMRouter", _factory)
    monkeypatch.setattr(dev_api, "LLM_ROUTER_CONFIG_PATH", cfg / "llm.yaml")


# A config with no backends and no fallback chains: the only shape in which
# complete_task() still raises TaskModelNotAssignedError.
_NO_USABLE_MODEL_CONFIG = yaml.dump({
    "backends": {},
    "fallback_order": [],
    "research_fallback_order": [],
})


def test_generate_summary_returns_400_when_no_research_model_assigned(tmp_path, monkeypatch):
    cfg = _cfg_dir(tmp_path)
    (cfg / "plain_text_resume.yaml").write_text(yaml.dump({"skills": ["Python"], "experience": [{"title": "Engineer"}]}))
    (cfg / "llm.yaml").write_text(_NO_USABLE_MODEL_CONFIG)
    monkeypatch.setattr(dev_api, "_config_dir", lambda: cfg)
    monkeypatch.setattr(dev_api, "_resume_path", lambda: cfg / "plain_text_resume.yaml")
    _redirect_llm_router_config(monkeypatch, cfg)
    client = TestClient(dev_api.app)
    resp = client.post("/api/settings/profile/generate-summary")
    assert resp.status_code == 400
    assert "Research" in resp.json()["detail"]


def test_generate_summary_returns_502_when_research_backend_unreachable(tmp_path, monkeypatch):
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
    cfg = _cfg_dir(tmp_path)
    (cfg / "llm.yaml").write_text(_NO_USABLE_MODEL_CONFIG)
    monkeypatch.setattr(dev_api, "_config_dir", lambda: cfg)
    monkeypatch.setattr(dev_api, "_resume_path", lambda: cfg / "plain_text_resume.yaml")
    _redirect_llm_router_config(monkeypatch, cfg)
    mock_db = MagicMock()
    mock_db.execute.return_value.fetchone.return_value = _mock_job_row()
    monkeypatch.setattr(dev_api, "_get_db", lambda: mock_db)
    client = TestClient(dev_api.app)
    resp = client.post("/api/jobs/1/qa/suggest", json={"question": "Why do you want this job?"})
    assert resp.status_code == 400
    assert "Chat" in resp.json()["detail"]


def test_suggest_qa_answer_returns_502_when_chat_backend_unreachable(tmp_path, monkeypatch):
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


# -- Graceful degradation at the call sites (no task_models anywhere) --------


def test_generate_summary_falls_back_to_configured_chain_when_unassigned(tmp_path, monkeypatch):
    """A fresh install (or a cloud tenant with no Model Assignments UI) has no
    task_models at all -- the endpoint must still work off the existing
    fallback chain instead of hard-failing with 400."""
    from scripts.llm_router import LLMRouter as RealLLMRouter
    cfg = _cfg_dir(tmp_path)
    (cfg / "plain_text_resume.yaml").write_text(yaml.dump({"skills": ["Python"], "experience": [{"title": "Engineer"}]}))
    (cfg / "llm.yaml").write_text(yaml.dump({
        "backends": {"ollama": {"type": "openai_compat", "model": "llama3.2:3b", "enabled": True}},
        "fallback_order": ["ollama"],
    }))
    monkeypatch.setattr(dev_api, "_config_dir", lambda: cfg)
    monkeypatch.setattr(dev_api, "_resume_path", lambda: cfg / "plain_text_resume.yaml")
    _redirect_llm_router_config(monkeypatch, cfg)
    client = TestClient(dev_api.app)
    with patch.object(RealLLMRouter, "complete", return_value="A concise summary."):
        resp = client.post("/api/settings/profile/generate-summary")
    assert resp.status_code == 200
    assert resp.json()["summary"] == "A concise summary."


# -- generate_mission_preferences: no generic "LLM generation failed" --------


def _mission_cfg(tmp_path, monkeypatch):
    cfg = _cfg_dir(tmp_path)
    (cfg / "plain_text_resume.yaml").write_text(yaml.dump({"skills": ["Python"], "experience": [{"title": "Engineer"}]}))
    (cfg / "llm.yaml").write_text(yaml.dump({
        "backends": {"ollama": {"type": "openai_compat", "model": "m", "enabled": True}},
        "task_models": {"research": {"backend": "ollama", "model": "llama3.1:8b"}},
    }))
    monkeypatch.setattr(dev_api, "_config_dir", lambda: cfg)
    monkeypatch.setattr(dev_api, "_resume_path", lambda: cfg / "plain_text_resume.yaml")
    _redirect_llm_router_config(monkeypatch, cfg)
    return cfg


def test_generate_missions_classifies_unparsable_output_not_generic_500(tmp_path, monkeypatch):
    from scripts.llm_router import LLMRouter as RealLLMRouter
    _mission_cfg(tmp_path, monkeypatch)
    client = TestClient(dev_api.app)
    with patch.object(RealLLMRouter, "complete", return_value="I am afraid I cannot do that."):
        resp = client.post("/api/settings/profile/generate-missions")
    assert resp.status_code == 502
    detail = resp.json()["detail"]
    assert "LLM generation failed" not in detail
    assert "Research" in detail
    assert "usable output" in detail


def test_generate_missions_succeeds_on_valid_json_array(tmp_path, monkeypatch):
    from scripts.llm_router import LLMRouter as RealLLMRouter
    _mission_cfg(tmp_path, monkeypatch)
    client = TestClient(dev_api.app)
    raw = '[{"tag": "climate", "label": "Climate tech", "note": "Fits their systems work."}]'
    with patch.object(RealLLMRouter, "complete", return_value=raw):
        resp = client.post("/api/settings/profile/generate-missions")
    assert resp.status_code == 200
    assert resp.json()["mission_preferences"] == [
        {"industry": "Climate tech", "note": "Fits their systems work."}
    ]


# -- #288: calm message in cloud mode, whole-chain walk for unassigned tasks --

_CHAIN_CONFIG = {
    "backends": {
        "cf_text": {"type": "openai_compat", "base_url": "http://cf", "model": "cf-model", "enabled": True},
        "ollama_research": {"type": "openai_compat", "base_url": "http://ol", "model": "llama-own", "enabled": True},
    },
    "research_fallback_order": ["cf_text", "ollama_research"],
    "fallback_order": ["ollama_research"],
}


def test_task_unavailable_detail_self_hosted_wording_is_unchanged():
    assert dev_api._task_unavailable_detail("Research", "cf_text", cloud=False) == (
        "Can't reach the Research model (cf_text) — check it's running, or reassign in Settings → System."
    )
    assert dev_api._task_unavailable_detail("Chat", None, cloud=False) == (
        "No model is assigned to the Chat task yet — set one in Settings → System → Model Assignments."
    )


def test_task_unavailable_detail_cloud_has_no_settings_or_backend_name():
    for backend in ("cf_text", None):
        msg = dev_api._task_unavailable_detail("Research", backend, cloud=True)
        assert msg == "This feature is not available right now. Please try again in a few minutes."
        assert "Settings" not in msg and "cf_text" not in msg


def _suggest_tags_client(tmp_path, monkeypatch, cloud):
    from scripts import llm_router as llm_router_module
    cfg = _cfg_dir(tmp_path)
    (cfg / "plain_text_resume.yaml").write_text(yaml.dump({"skills": ["Python"], "experience": [{"title": "Engineer"}]}))
    (cfg / "llm.yaml").write_text(yaml.dump(_CHAIN_CONFIG))
    monkeypatch.setattr(dev_api, "_config_dir", lambda: cfg)
    monkeypatch.setattr(dev_api, "_resume_path", lambda: cfg / "plain_text_resume.yaml")
    _redirect_llm_router_config(monkeypatch, cfg)
    monkeypatch.setattr(llm_router_module, "CONFIG_PATH", cfg / "llm.yaml")
    monkeypatch.setattr(dev_api, "_CLOUD_MODE", cloud)
    monkeypatch.setattr(dev_api, "DB_PATH", tmp_path / "staging.db")
    return TestClient(dev_api.app)


def test_suggest_tags_cloud_first_backend_down_later_backend_answers(tmp_path, monkeypatch):
    from scripts.llm_router import LLMRouter as RealLLMRouter
    client = _suggest_tags_client(tmp_path, monkeypatch, cloud=True)
    seen = []

    def fake_complete(self, prompt, system=None, **kw):
        # Emulate core: the dead first backend is skipped, the next one answers.
        seen.append((kw.get("fallback_order"), kw.get("model_override")))
        if "ollama_research" in (kw.get("fallback_order") or []):
            return '["Python", "Docker"]'
        raise RuntimeError("All LLM backends exhausted. Tried: cf_text: refused")

    with patch.object(RealLLMRouter, "complete", fake_complete):
        resp = client.post("/api/settings/resume/suggest-tags", json={"type": "skills"})
    assert resp.status_code == 200
    assert resp.json()["suggestions"] == ["Python", "Docker"]
    assert seen[0] == (["cf_text", "ollama_research"], None)


def test_suggest_tags_cloud_whole_chain_down_is_calm_502(tmp_path, monkeypatch):
    from scripts.llm_router import LLMRouter as RealLLMRouter
    client = _suggest_tags_client(tmp_path, monkeypatch, cloud=True)
    with patch.object(RealLLMRouter, "complete", side_effect=RuntimeError("down")):
        resp = client.post("/api/settings/resume/suggest-tags", json={"type": "skills"})
    assert resp.status_code == 502
    detail = resp.json()["detail"]
    assert "Settings" not in detail and "cf_text" not in detail
    assert "try again" in detail


def test_generate_missions_unusable_output_cloud_is_calm(tmp_path, monkeypatch):
    from scripts.llm_router import LLMRouter as RealLLMRouter
    _mission_cfg(tmp_path, monkeypatch)
    monkeypatch.setattr(dev_api, "_CLOUD_MODE", True)
    client = TestClient(dev_api.app)
    with patch.object(RealLLMRouter, "complete", return_value="I am afraid I cannot do that."):
        resp = client.post("/api/settings/profile/generate-missions")
    assert resp.status_code == 502
    detail = resp.json()["detail"]
    assert "Settings" not in detail
    assert "try again" in detail
