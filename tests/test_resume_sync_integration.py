"""Integration tests for resume library<->profile sync endpoints."""
import json
import os
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from scripts.db import create_resume, get_resume, list_resumes
from scripts.db_migrate import migrate_db

STRUCT_JSON = {
    "name": "Alex Rivera",
    "email": "alex@example.com",
    "phone": "555-0100",
    "career_summary": "Senior UX Designer.",
    "experience": [{"title": "Designer", "company": "Acme", "start_date": "2022",
                    "end_date": "present", "location": "Remote", "bullets": ["Led redesign"]}],
    "education": [{"institution": "State U", "degree": "B.A.", "field": "Design",
                   "start_date": "2016", "end_date": "2020"}],
    "skills": ["Figma"],
    "achievements": ["Design award"],
}


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    """Set up a fresh isolated DB + config dir, wired to dev_api._request_db."""
    db = tmp_path / "test.db"
    cfg = tmp_path / "config"
    cfg.mkdir()
    # STAGING_DB drives _user_yaml_path() -> dirname(db)/config/user.yaml
    monkeypatch.setenv("STAGING_DB", str(db))
    migrate_db(db)
    import dev_api
    monkeypatch.setattr(
        dev_api,
        "_request_db",
        type("CV", (), {"get": lambda self: str(db), "set": lambda *a: None})(),
    )
    return db, cfg


def test_apply_to_profile_updates_yaml(fresh_db, monkeypatch):
    db, cfg = fresh_db
    import dev_api
    client = TestClient(dev_api.app)
    entry = create_resume(db, name="Test Resume",
                          text="Alex Rivera\n", source="uploaded",
                          struct_json=json.dumps(STRUCT_JSON))
    resp = client.post(f"/api/resumes/{entry['id']}/apply-to-profile")
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert "backup_id" in data
    assert "Auto-backup before Test Resume" in data["backup_name"]
    profile_yaml = cfg / "plain_text_resume.yaml"
    assert profile_yaml.exists()
    profile = yaml.safe_load(profile_yaml.read_text())
    assert profile["career_summary"] == "Senior UX Designer."
    # Name split: "Alex Rivera" -> name="Alex", surname="Rivera"
    assert profile["name"] == "Alex"
    assert profile["surname"] == "Rivera"
    assert profile["education"][0]["institution"] == "State U"


def test_apply_to_profile_creates_backup(fresh_db, monkeypatch):
    db, cfg = fresh_db
    profile_path = cfg / "plain_text_resume.yaml"
    profile_path.write_text(yaml.dump({"name": "Old Name", "career_summary": "Old summary"}))
    entry = create_resume(db, name="New Resume",
                          text="Alex Rivera\n", source="uploaded",
                          struct_json=json.dumps(STRUCT_JSON))
    import dev_api
    client = TestClient(dev_api.app)
    client.post(f"/api/resumes/{entry['id']}/apply-to-profile")
    resumes = list_resumes(db_path=db)
    backup = next((r for r in resumes if r["source"] == "auto_backup"), None)
    assert backup is not None


def test_apply_to_profile_preserves_metadata(fresh_db, monkeypatch):
    db, cfg = fresh_db
    profile_path = cfg / "plain_text_resume.yaml"
    profile_path.write_text(yaml.dump({
        "name": "Old", "salary_min": 80000, "salary_max": 120000,
        "remote": True, "gender": "non-binary",
    }))
    entry = create_resume(db, name="New",
                          text="Alex\n", source="uploaded",
                          struct_json=json.dumps(STRUCT_JSON))
    import dev_api
    client = TestClient(dev_api.app)
    client.post(f"/api/resumes/{entry['id']}/apply-to-profile")
    profile = yaml.safe_load(profile_path.read_text())
    assert profile["salary_min"] == 80000
    assert profile["remote"] is True
    assert profile["gender"] == "non-binary"


def test_save_resume_syncs_to_default_library_entry(fresh_db, monkeypatch):
    db, cfg = fresh_db
    entry = create_resume(db, name="My Resume",
                          text="Original", source="manual")
    user_yaml = cfg / "user.yaml"
    user_yaml.write_text(yaml.dump({"default_resume_id": entry["id"], "wizard_complete": True}))
    import dev_api
    client = TestClient(dev_api.app)
    resp = client.put("/api/settings/resume", json={
        "name": "Alex", "career_summary": "Updated summary",
        "experience": [], "education": [], "achievements": [], "skills": [],
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["synced_library_entry_id"] == entry["id"]
    updated = get_resume(db_path=db, resume_id=entry["id"])
    assert updated["synced_at"] is not None
    struct = json.loads(updated["struct_json"])
    assert struct["career_summary"] == "Updated summary"


def test_save_resume_no_default_no_crash(fresh_db, monkeypatch):
    db, cfg = fresh_db
    user_yaml = cfg / "user.yaml"
    user_yaml.write_text(yaml.dump({"wizard_complete": True}))
    import dev_api
    client = TestClient(dev_api.app)
    resp = client.put("/api/settings/resume", json={
        "name": "Alex", "career_summary": "", "experience": [],
        "education": [], "achievements": [], "skills": [],
    })
    assert resp.status_code == 200
    assert resp.json()["synced_library_entry_id"] is None
