"""A brand-new cloud tenant must get a working database on first request (peregrine#221).

cloud_session_middleware resolves <CLOUD_DATA_ROOT>/<user_id>/peregrine/staging.db and
runs migrations on first access. Nothing creates the tenant directory beforehand, and
sqlite3.connect cannot create directories, so every call from a new signup used to 500.
"""
import uuid
from pathlib import Path

import jwt
import pytest
from fastapi.testclient import TestClient

SECRET = "test-directus-secret-at-least-32-bytes-long"


def _cookie_for(user_id: str) -> dict[str, str]:
    token = jwt.encode({"id": user_id}, SECRET, algorithm="HS256")
    return {"X-CF-Session": f"cf_session={token}"}


@pytest.fixture
def cloud_client(monkeypatch, tmp_path):
    import dev_api

    monkeypatch.setattr(dev_api, "_CLOUD_MODE", True)
    monkeypatch.setattr(dev_api, "_DIRECTUS_SECRET", SECRET)
    monkeypatch.setattr(dev_api, "_CLOUD_DATA_ROOT", tmp_path)
    monkeypatch.setattr(dev_api, "_migrated_db_paths", set())
    monkeypatch.setattr(dev_api, "_seen_users", set())
    return TestClient(dev_api.app), tmp_path


def test_new_tenant_first_request_creates_directory_and_database(cloud_client):
    client, root = cloud_client
    user_id = str(uuid.uuid4())

    resp = client.get("/api/config/app", headers=_cookie_for(user_id))

    assert resp.status_code == 200
    db_path = root / user_id / "peregrine" / "staging.db"
    assert db_path.is_file(), "tenant database should be created on first access"


def test_existing_tenant_directory_is_left_alone(cloud_client):
    client, root = cloud_client
    user_id = str(uuid.uuid4())
    tenant_dir = root / user_id / "peregrine"
    tenant_dir.mkdir(parents=True)
    marker = tenant_dir / "keep.txt"
    marker.write_text("existing tenant data")

    resp = client.get("/api/config/app", headers=_cookie_for(user_id))

    assert resp.status_code == 200
    assert marker.read_text() == "existing tenant data"


def test_second_request_for_same_tenant_still_succeeds(cloud_client):
    client, _ = cloud_client
    headers = _cookie_for(str(uuid.uuid4()))

    first = client.get("/api/config/app", headers=headers)
    second = client.get("/api/config/app", headers=headers)

    assert first.status_code == 200
    assert second.status_code == 200


def test_tenants_get_separate_databases(cloud_client):
    client, root = cloud_client
    a, b = str(uuid.uuid4()), str(uuid.uuid4())

    client.get("/api/config/app", headers=_cookie_for(a))
    client.get("/api/config/app", headers=_cookie_for(b))

    assert (root / a / "peregrine" / "staging.db").is_file()
    assert (root / b / "peregrine" / "staging.db").is_file()
    assert Path(root / a / "peregrine" / "staging.db") != Path(root / b / "peregrine" / "staging.db")
