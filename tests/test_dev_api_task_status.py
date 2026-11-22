"""GET /api/tasks/{task_id}: read-only status of one background task, so the
Home page can report whether a finished task completed or failed (peregrine#264).

The raw stored error text never leaves the server: it can hold file paths, SQL
errors and URLs with keys, so the endpoint returns a calm `message` instead."""
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


def _task(db, task_type, status, error=None):
    from scripts.db import insert_task, update_task_status
    task_id, _ = insert_task(db, task_type, 0)
    update_task_status(db, task_id, status, error=error)
    return task_id


def test_task_status_reports_running(client, tmp_db):
    task_id = _task(tmp_db, "discovery", "running")
    resp = client.get(f"/api/tasks/{task_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body == {"id": task_id, "task_type": "discovery", "status": "running", "message": None}


def test_task_status_exposes_only_the_safe_fields(client, tmp_db):
    task_id = _task(tmp_db, "discovery", "completed")
    assert set(client.get(f"/api/tasks/{task_id}").json()) == {"id", "task_type", "status", "message"}


def test_failed_task_never_returns_raw_error_text(client, tmp_db):
    raw = ("OperationalError: no such table jobs at /devl/user-data/alice/staging.db "
           "SELECT * FROM jobs WHERE id=3 fetching https://api.example.com/v1?api_key=SECRET123")
    task_id = _task(tmp_db, "discovery", "failed", error=raw)
    resp = client.get(f"/api/tasks/{task_id}")
    body = resp.json()
    assert body["status"] == "failed"
    assert body["message"] == "Discovery did not finish. You can run it again."
    text = resp.text
    for leaked in ("/devl/", "alice", "SELECT", "OperationalError", "SECRET123", "api_key", "https://"):
        assert leaked not in text


@pytest.mark.parametrize("task_type,error,expected", [
    ("discovery", "Cancelled by user", "Discovery was stopped."),
    ("email_sync", "Cancelled by user", "Email sync was stopped."),
    ("discovery",
     "Discovery is disabled in the public demo. Run your own instance to use this feature.",
     "Discovery is turned off in the demo."),
    ("email_sync", "Email not configured — go to Settings → Email",
     "Email is not set up yet. You can add it in Settings."),
    ("enrich_descriptions", "something unexpected", "Description fill did not finish. You can run it again."),
    ("some_other_type", None, "The task did not finish. You can run it again."),
])
def test_failed_task_message_allowlist(client, tmp_db, task_type, error, expected):
    task_id = _task(tmp_db, task_type, "failed", error=error)
    assert client.get(f"/api/tasks/{task_id}").json()["message"] == expected


def test_completed_task_message_uses_only_the_known_summary(client, tmp_db):
    one = _task(tmp_db, "discovery", "completed", error="1 new listing added")
    many = client.get(f"/api/tasks/{_task(tmp_db, 'discovery', 'completed', error='12 new listings added')}")
    assert client.get(f"/api/tasks/{one}").json()["message"] == "Discovery finished. 1 new listing added."
    assert many.json()["message"] == "Discovery finished. 12 new listings added."


def test_completed_task_ignores_unexpected_summary_text(client, tmp_db):
    task_id = _task(tmp_db, "discovery", "completed", error="done, see /devl/user-data/x?key=abc")
    body = client.get(f"/api/tasks/{task_id}").json()
    assert body["message"] == "Discovery finished."
    assert "/devl/" not in client.get(f"/api/tasks/{task_id}").text


def test_task_status_unknown_id_is_404(client):
    assert client.get("/api/tasks/9999").status_code == 404


def test_task_status_is_scoped_to_the_request_database(tmp_path, tmp_db, monkeypatch):
    """A task id that exists only in one user's database is a 404 from another's."""
    from scripts.db import init_db
    other_db = tmp_path / "other.db"
    init_db(other_db)
    task_id = _task(tmp_db, "discovery", "running")

    import dev_api
    monkeypatch.setattr(dev_api, "DB_PATH", tmp_db)
    monkeypatch.setattr(dev_api, "_request_db",
                        type("CV", (), {"get": lambda self: str(other_db), "set": lambda *a: None})())
    c = TestClient(dev_api.app)
    assert c.get(f"/api/tasks/{task_id}").status_code == 404

    monkeypatch.setattr(dev_api, "_request_db",
                        type("CV", (), {"get": lambda self: str(tmp_db), "set": lambda *a: None})())
    assert TestClient(dev_api.app).get(f"/api/tasks/{task_id}").status_code == 200
