"""GET /api/tasks/{task_id}: read-only status of one background task, so the
Home page can report whether a finished task completed or failed (peregrine#264)."""
import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def tmp_db(tmp_path):
    from scripts.db import init_db
    db_path = tmp_path / "staging.db"
    init_db(db_path)
    return db_path


@pytest.fixture()
def client(tmp_db, monkeypatch):
    monkeypatch.setattr("dev_api.DB_PATH", tmp_db)
    from dev_api import app
    return TestClient(app)


def test_task_status_reports_running(client, tmp_db):
    from scripts.db import insert_task, update_task_status
    task_id, _ = insert_task(tmp_db, "discovery", 0)
    update_task_status(tmp_db, task_id, "running")
    resp = client.get(f"/api/tasks/{task_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == task_id
    assert body["task_type"] == "discovery"
    assert body["status"] == "running"


def test_task_status_reports_failure_with_error(client, tmp_db):
    from scripts.db import insert_task, update_task_status
    task_id, _ = insert_task(tmp_db, "discovery", 0)
    update_task_status(tmp_db, task_id, "failed", error="boom")
    body = client.get(f"/api/tasks/{task_id}").json()
    assert body["status"] == "failed"
    assert body["error"] == "boom"


def test_task_status_unknown_id_is_404(client):
    assert client.get("/api/tasks/9999").status_code == 404
