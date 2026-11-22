"""An add-by-URL scrape that finds nothing is a visible, explained state (peregrine#254)."""
import sqlite3
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

URL = "https://secret-board.example.com/jobs/12345?token=abc"


@pytest.fixture()
def db(tmp_path):
    from scripts.db import init_db, insert_job
    path = tmp_path / "staging.db"
    init_db(path)
    job_id = insert_job(path, {
        "title": "Importing...", "company": "", "url": URL, "source": "manual",
        "location": "", "description": "", "date_found": "2026-11-22",
    })
    return path, job_id


def _run(path, job_id, fields):
    from scripts.db import insert_task
    from scripts.task_runner import _run_task
    task_id, _ = insert_task(path, "scrape_url", job_id)
    with patch("scripts.scrape_url.scrape_job_url", return_value=fields):
        _run_task(path, task_id, "scrape_url", job_id)
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    row = con.execute("SELECT status, error FROM background_tasks WHERE id=?", (task_id,)).fetchone()
    con.close()
    return dict(row)


def test_empty_scrape_ends_with_distinct_outcome(db):
    path, job_id = db
    task = _run(path, job_id, {})
    assert task["status"] == "completed"
    assert task["error"] == "empty_result"


def test_title_without_description_is_still_empty(db):
    path, job_id = db
    assert _run(path, job_id, {"title": "Engineer"})["error"] == "empty_result"


def test_successful_scrape_is_unchanged(db):
    path, job_id = db
    task = _run(path, job_id, {"title": "Engineer", "company": "Acme", "description": "Does things."})
    assert task == {"status": "completed", "error": "Engineer @ Acme"}


def test_empty_scrape_logs_one_line_with_board_and_no_url(db, capsys):
    from scripts import scrape_url
    path, job_id = db
    with patch.object(scrape_url, "_scrape_generic", return_value={}):
        scrape_url.scrape_job_url(path, job_id)
    lines = [ln for ln in capsys.readouterr().out.splitlines() if ln.strip()]
    assert len(lines) == 1
    assert "generic" in lines[0] and str(job_id) in lines[0]
    assert "secret-board" not in lines[0] and "token" not in lines[0]


@pytest.fixture()
def client(db, monkeypatch):
    monkeypatch.setattr("dev_api.DB_PATH", db[0])
    from dev_api import app
    return TestClient(app)


def _state(client, job_id):
    return client.get(f"/api/jobs/{job_id}").json()["import_state"]


def test_job_reports_importing_while_scrape_runs(db, client):
    from scripts.db import insert_task
    path, job_id = db
    insert_task(path, "scrape_url", job_id)
    assert _state(client, job_id) == "importing"


def test_job_reports_needs_manual_entry_after_empty_scrape(db, client):
    path, job_id = db
    _run(path, job_id, {})
    assert _state(client, job_id) == "needs_manual_entry"


def test_title_only_scrape_needs_manual_entry_until_description_added(db, client):
    from scripts.db import update_job_fields
    path, job_id = db
    _run(path, job_id, {"title": "Engineer"})
    update_job_fields(path, job_id, {"title": "Engineer"})
    assert _state(client, job_id) == "needs_manual_entry"
    update_job_fields(path, job_id, {"description": "x" * 80})
    assert _state(client, job_id) is None


def test_successful_job_has_no_import_state(db, client):
    from scripts.db import update_job_fields
    path, job_id = db
    update_job_fields(path, job_id, {"title": "Engineer", "description": "Does things."})
    _run(path, job_id, {"title": "Engineer", "description": "Does things."})
    assert _state(client, job_id) is None


def test_manual_details_fill_the_job_and_clear_the_state(db, client):
    path, job_id = db
    _run(path, job_id, {})
    resp = client.patch(f"/api/jobs/{job_id}/details", json={
        "title": "  Engineer ", "company": "Acme", "description": "Pasted text."})
    assert resp.status_code == 200
    body = resp.json()
    assert (body["title"], body["company"], body["description"]) == ("Engineer", "Acme", "Pasted text.")
    assert body["import_state"] is None


def test_manual_details_require_title_and_description(db, client):
    _, job_id = db
    assert client.patch(f"/api/jobs/{job_id}/details",
                        json={"title": " ", "company": "", "description": "x"}).status_code == 422
    assert client.patch(f"/api/jobs/{job_id}/details",
                        json={"title": "T", "company": "", "description": " "}).status_code == 422
    assert client.patch("/api/jobs/9999/details",
                        json={"title": "T", "company": "", "description": "d"}).status_code == 404
