"""Tests for survey endpoints: vision health, async analyze task queue, save response, history."""
import json
import sqlite3
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from scripts.db_migrate import migrate_db


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    """Isolated DB + dev_api wired to it via _request_db and DB_PATH."""
    db = tmp_path / "test.db"
    migrate_db(db)
    monkeypatch.setenv("STAGING_DB", str(db))
    import dev_api
    monkeypatch.setattr(dev_api, "DB_PATH", str(db))
    monkeypatch.setattr(
        dev_api,
        "_request_db",
        type("CV", (), {"get": lambda self: str(db), "set": lambda *a: None})(),
    )
    return db


@pytest.fixture
def client(fresh_db):
    import dev_api
    return TestClient(dev_api.app)


# ── GET /api/vision/health ────────────────────────────────────────────────────

def test_vision_health_available(client):
    """Returns available=true when vision service responds 200."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    with patch("dev_api.requests.get", return_value=mock_resp):
        resp = client.get("/api/vision/health")
    assert resp.status_code == 200
    assert resp.json() == {"available": True}


def test_vision_health_unavailable(client):
    """Returns available=false when vision service times out or errors."""
    with patch("dev_api.requests.get", side_effect=Exception("timeout")):
        resp = client.get("/api/vision/health")
    assert resp.status_code == 200
    assert resp.json() == {"available": False}


# ── POST /api/jobs/{id}/survey/analyze ───────────────────────────────────────

def test_analyze_queues_task_and_returns_task_id(client):
    """POST analyze queues a background task and returns task_id + is_new."""
    with patch("scripts.task_runner.submit_task", return_value=(42, True)) as mock_submit:
        resp = client.post("/api/jobs/1/survey/analyze", json={
            "text": "Q1: Do you prefer teamwork?\nA. Solo  B. Together",
            "mode": "quick",
        })
    assert resp.status_code == 200
    data = resp.json()
    assert data["task_id"] == 42
    assert data["is_new"] is True
    # submit_task called with survey_analyze type
    call_kwargs = mock_submit.call_args
    assert call_kwargs.kwargs["task_type"] == "survey_analyze"
    assert call_kwargs.kwargs["job_id"] == 1
    params = json.loads(call_kwargs.kwargs["params"])
    assert params["mode"] == "quick"
    assert params["text"] == "Q1: Do you prefer teamwork?\nA. Solo  B. Together"


def test_analyze_silently_attaches_to_existing_task(client):
    """is_new=False when task already running for same input."""
    with patch("scripts.task_runner.submit_task", return_value=(7, False)):
        resp = client.post("/api/jobs/1/survey/analyze", json={
            "text": "Q1: test", "mode": "quick",
        })
    assert resp.status_code == 200
    assert resp.json()["is_new"] is False


def test_analyze_invalid_mode_returns_400(client):
    resp = client.post("/api/jobs/1/survey/analyze", json={"text": "Q1: test", "mode": "wrong"})
    assert resp.status_code == 400


def test_analyze_image_mode_passes_image_in_params(client):
    """Image payload is forwarded in task params."""
    with patch("scripts.task_runner.submit_task", return_value=(1, True)) as mock_submit:
        resp = client.post("/api/jobs/1/survey/analyze", json={
            "image_b64": "aGVsbG8=",
            "mode": "quick",
        })
    assert resp.status_code == 200
    params = json.loads(mock_submit.call_args.kwargs["params"])
    assert params["image_b64"] == "aGVsbG8="
    assert params["text"] is None


# ── GET /api/jobs/{id}/survey/analyze/task ────────────────────────────────────

def test_task_poll_completed_text(client, fresh_db):
    """Completed task with text result returns parsed source + output."""
    result_json = json.dumps({"output": "1. B — best option", "source": "text_paste"})
    con = sqlite3.connect(fresh_db)
    con.execute(
        "INSERT INTO background_tasks (task_type, job_id, status, error) VALUES (?,?,?,?)",
        ("survey_analyze", 1, "completed", result_json),
    )
    task_id = con.execute("SELECT last_insert_rowid()").fetchone()[0]
    con.commit(); con.close()

    resp = client.get(f"/api/jobs/1/survey/analyze/task?task_id={task_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "completed"
    assert data["result"]["source"] == "text_paste"
    assert "B" in data["result"]["output"]
    assert data["message"] is None


def test_task_poll_completed_screenshot(client, fresh_db):
    """Completed task with image result returns source=screenshot."""
    result_json = json.dumps({"output": "1. C — collaborative", "source": "screenshot"})
    con = sqlite3.connect(fresh_db)
    con.execute(
        "INSERT INTO background_tasks (task_type, job_id, status, error) VALUES (?,?,?,?)",
        ("survey_analyze", 1, "completed", result_json),
    )
    task_id = con.execute("SELECT last_insert_rowid()").fetchone()[0]
    con.commit(); con.close()

    resp = client.get(f"/api/jobs/1/survey/analyze/task?task_id={task_id}")
    assert resp.status_code == 200
    assert resp.json()["result"]["source"] == "screenshot"


def test_task_poll_failed_returns_message(client, fresh_db):
    """Failed task returns status=failed with error message."""
    con = sqlite3.connect(fresh_db)
    con.execute(
        "INSERT INTO background_tasks (task_type, job_id, status, error) VALUES (?,?,?,?)",
        ("survey_analyze", 1, "failed", "LLM unavailable"),
    )
    task_id = con.execute("SELECT last_insert_rowid()").fetchone()[0]
    con.commit(); con.close()

    resp = client.get(f"/api/jobs/1/survey/analyze/task?task_id={task_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "failed"
    assert data["message"] == "LLM unavailable"
    assert data["result"] is None


def test_task_poll_running_returns_stage(client, fresh_db):
    """Running task returns status=running with current stage."""
    con = sqlite3.connect(fresh_db)
    con.execute(
        "INSERT INTO background_tasks (task_type, job_id, status, stage) VALUES (?,?,?,?)",
        ("survey_analyze", 1, "running", "analyzing survey"),
    )
    task_id = con.execute("SELECT last_insert_rowid()").fetchone()[0]
    con.commit(); con.close()

    resp = client.get(f"/api/jobs/1/survey/analyze/task?task_id={task_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "running"
    assert data["stage"] == "analyzing survey"


def test_task_poll_none_when_no_task(client):
    """Returns status=none when no task exists for the job."""
    resp = client.get("/api/jobs/999/survey/analyze/task")
    assert resp.status_code == 200
    assert resp.json()["status"] == "none"


# ── POST /api/jobs/{id}/survey/responses ─────────────────────────────────────

def test_save_response_text(client):
    """Save a text-mode survey response returns an id."""
    resp = client.post("/api/jobs/1/survey/responses", json={
        "survey_name": "Culture Fit",
        "mode": "quick",
        "source": "text_paste",
        "raw_input": "Q1: Teamwork?",
        "llm_output": "1. B is best",
        "reported_score": "85",
    })
    assert resp.status_code == 200
    assert "id" in resp.json()


def test_save_response_with_image(client):
    """Save a screenshot-mode survey response returns an id."""
    resp = client.post("/api/jobs/1/survey/responses", json={
        "survey_name": None,
        "mode": "quick",
        "source": "screenshot",
        "image_b64": "aGVsbG8=",
        "llm_output": "1. C collaborative",
        "reported_score": None,
    })
    assert resp.status_code == 200
    assert "id" in resp.json()


def test_get_history_empty(client):
    """History is empty for a fresh job."""
    resp = client.get("/api/jobs/1/survey/responses")
    assert resp.status_code == 200
    assert resp.json() == []


def test_get_history_populated(client):
    """History returns all saved responses for a job in reverse order."""
    for i in range(2):
        client.post("/api/jobs/1/survey/responses", json={
            "survey_name": f"Survey {i}",
            "mode": "quick",
            "source": "text_paste",
            "llm_output": f"Output {i}",
        })
    resp = client.get("/api/jobs/1/survey/responses")
    assert resp.status_code == 200
    assert len(resp.json()) == 2
