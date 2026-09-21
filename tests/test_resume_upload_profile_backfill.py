"""POST /api/settings/resume/upload should backfill empty My Profile fields
from the parsed resume (name, email, phone, career_summary) -- without ever
overwriting a value the user already entered.
"""
from unittest.mock import patch

import pytest
import yaml
from fastapi.testclient import TestClient

from scripts.db_migrate import migrate_db

PARSED_RESUME = {
    "name": "Alex",
    "surname": "Rivera",
    "email": "alex@example.com",
    "phone": "555-0100",
    "career_summary": "Senior UX Designer.",
    "experience": [],
    "education": [],
    "skills": [],
    "achievements": [],
}


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    db = tmp_path / "test.db"
    cfg = tmp_path / "config"
    cfg.mkdir()
    monkeypatch.setenv("STAGING_DB", str(db))
    migrate_db(db)
    import dev_api
    monkeypatch.setattr(
        dev_api,
        "_request_db",
        type("CV", (), {"get": lambda self: str(db), "set": lambda *a: None})(),
    )
    return db, cfg


def _upload(client):
    with patch("scripts.resume_parser.extract_text_from_docx", return_value="Alex Rivera\nalex@example.com"), \
         patch("scripts.resume_parser.structure_resume", return_value=(dict(PARSED_RESUME), "")):
        return client.post(
            "/api/settings/resume/upload",
            files={"file": ("resume.docx", b"fake docx bytes", "application/octet-stream")},
        )


def test_upload_backfills_empty_profile_fields(fresh_db, monkeypatch):
    _db, cfg = fresh_db
    import dev_api
    client = TestClient(dev_api.app)

    resp = _upload(client)
    assert resp.status_code == 200
    assert resp.json()["ok"] is True

    profile = yaml.safe_load((cfg / "user.yaml").read_text())
    assert profile["name"] == "Alex Rivera"
    assert profile["email"] == "alex@example.com"
    assert profile["phone"] == "555-0100"
    assert profile["career_summary"] == "Senior UX Designer."


def test_upload_never_overwrites_existing_profile_fields(fresh_db, monkeypatch):
    _db, cfg = fresh_db
    (cfg / "user.yaml").write_text(yaml.dump({
        "name": "Existing Name",
        "email": "existing@example.com",
        "phone": "",  # blank -- should still get backfilled
        "career_summary": "Already written summary.",
    }, allow_unicode=True, default_flow_style=False))

    import dev_api
    client = TestClient(dev_api.app)
    resp = _upload(client)
    assert resp.status_code == 200

    profile = yaml.safe_load((cfg / "user.yaml").read_text())
    assert profile["name"] == "Existing Name"
    assert profile["email"] == "existing@example.com"
    assert profile["career_summary"] == "Already written summary."
    # ...but the genuinely blank field still gets filled in.
    assert profile["phone"] == "555-0100"
