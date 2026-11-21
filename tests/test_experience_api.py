"""API tests for experience facts and gap cards."""

import sqlite3

import pytest
from fastapi.testclient import TestClient

from scripts.db_migrate import migrate_db


def _wire(monkeypatch, holder):
    import dev_api

    monkeypatch.setattr(
        dev_api,
        "_request_db",
        type("CV", (), {"get": lambda self: holder["db"], "set": lambda *a: None})(),
    )


@pytest.fixture
def client(tmp_path, monkeypatch):
    db = tmp_path / "test.db"
    migrate_db(db)
    import dev_api

    monkeypatch.setattr(dev_api, "DB_PATH", str(db))
    _wire(monkeypatch, {"db": str(db)})
    c = TestClient(dev_api.app)
    c.db = db
    return c


def _add_job(db, description):
    conn = sqlite3.connect(db)
    cur = conn.execute(
        "INSERT INTO jobs (title, company, url, description) VALUES (?, ?, ?, ?)",
        ("Eng", "Acme", f"http://x/{description[:5]}", description),
    )
    conn.commit()
    conn.close()
    return cur.lastrowid


def test_crud_round_trip(client):
    r = client.post("/api/experience-facts", json={
        "kind": "experience", "requirement": "Go", "text": "Built", "visibility": "document",
    })
    assert r.status_code == 200, r.text
    fact = r.json()
    assert set(fact) == {
        "id", "kind", "requirement", "text", "visibility", "status",
        "source", "origin_job_id", "created_at", "updated_at",
    }
    fid = fact["id"]
    assert [f["id"] for f in client.get("/api/experience-facts").json()] == [fid]
    r = client.patch(f"/api/experience-facts/{fid}", json={"text": "Built more"})
    assert r.status_code == 200 and r.json()["text"] == "Built more"
    assert client.delete(f"/api/experience-facts/{fid}").status_code == 200
    assert client.get("/api/experience-facts").json() == []


def test_unknown_id_is_404(client):
    assert client.patch("/api/experience-facts/999", json={"text": "x"}).status_code == 404
    assert client.delete("/api/experience-facts/999").status_code == 404


def test_bad_input_is_422(client):
    r = client.post("/api/experience-facts", json={
        "kind": "experience", "requirement": "Go", "text": "   ",
    })
    assert r.status_code == 422
    r = client.post("/api/experience-facts", json={
        "kind": "bogus", "requirement": "Go", "text": "x",
    })
    assert r.status_code == 422
    r = client.post("/api/experience-facts", json={
        "kind": "experience", "requirement": "Go", "text": "x" * 2001,
    })
    assert r.status_code == 422
    fid = client.post("/api/experience-facts", json={
        "kind": "experience", "requirement": "Go", "text": "ok",
    }).json()["id"]
    assert client.patch(f"/api/experience-facts/{fid}", json={"text": " "}).status_code == 422


def test_gap_cards_endpoint_returns_a_card_per_term(client):
    job = _add_job(client.db, "You will use Kubernetes daily.")
    r = client.post(f"/api/jobs/{job}/gap_cards", json={"terms": ["Kubernetes", "Rust"]})
    assert r.status_code == 200, r.text
    cards = r.json()["cards"]
    assert [c["term"] for c in cards] == ["Kubernetes", "Rust"]
    assert cards[0]["snippet"] == "You will use Kubernetes daily."
    assert client.post("/api/jobs/9999/gap_cards", json={"terms": ["x"]}).status_code == 404


def test_answers_endpoint_returns_approved_terms(client):
    job = _add_job(client.db, "Go role.")
    r = client.post(f"/api/jobs/{job}/gap_cards/answers", json={"answers": [
        {"term": "Go", "choice": "yes", "text": "Built services"},
        {"term": "Rust", "choice": "no"},
    ]})
    assert r.status_code == 200, r.text
    assert r.json() == {"approved_terms": ["Go"], "saved": 2}
    r = client.post(f"/api/jobs/{job}/gap_cards/answers", json={"answers": [
        {"term": "Go", "choice": "yes", "text": "  "},
    ]})
    assert r.status_code == 422


def test_retiring_a_fact_stops_it_being_usable(client):
    from scripts.experience_facts import usable_facts_for_prompt

    fid = client.post("/api/experience-facts", json={
        "kind": "experience", "requirement": "Go", "text": "Built",
    }).json()["id"]
    assert "Go" in usable_facts_for_prompt(client.db, ["Go"])
    r = client.patch(f"/api/experience-facts/{fid}", json={"status": "retired"})
    assert r.status_code == 200
    assert usable_facts_for_prompt(client.db, ["Go"]) == {}
    assert client.get("/api/experience-facts").json() == []
    assert len(client.get("/api/experience-facts", params={"status": "retired"}).json()) == 1


def test_two_tenants_never_see_each_others_facts(tmp_path, monkeypatch):
    import dev_api

    db_a, db_b = tmp_path / "a.db", tmp_path / "b.db"
    migrate_db(db_a)
    migrate_db(db_b)
    monkeypatch.setattr(dev_api, "DB_PATH", str(tmp_path / "staging.db"))
    holder = {"db": str(db_a)}
    _wire(monkeypatch, holder)
    c = TestClient(dev_api.app)
    c.post("/api/experience-facts", json={"kind": "experience", "requirement": "Go", "text": "A's"})
    assert len(c.get("/api/experience-facts").json()) == 1
    holder["db"] = str(db_b)
    assert c.get("/api/experience-facts").json() == []
    holder["db"] = str(db_a)
    assert len(c.get("/api/experience-facts").json()) == 1


def test_a_punctuation_only_term_is_refused_by_the_service_and_the_route_with_422_and_saves_nothing(client):
    job = _add_job(client.db, "Role.")
    r = client.post(f"/api/jobs/{job}/gap_cards/answers", json={"answers": [
        {"term": "???", "choice": "yes", "text": "x"},
    ]})
    assert r.status_code == 422
    r = client.post("/api/experience-facts", json={
        "kind": "experience", "requirement": "...", "text": "x",
    })
    assert r.status_code == 422
    assert client.get("/api/experience-facts", params={"status": "all"}).json() == []


def test_cards_route_refuses_an_oversized_term_with_422(client):
    job = _add_job(client.db, "Role.")
    r = client.post(f"/api/jobs/{job}/gap_cards", json={"terms": ["x" * 121]})
    assert r.status_code == 422
    r = client.post(f"/api/jobs/{job}/gap_cards", json={"terms": [""]})
    assert r.status_code == 422


def test_cards_route_skips_unusable_terms_instead_of_failing(client):
    job = _add_job(client.db, "You will use Kubernetes daily.")
    r = client.post(f"/api/jobs/{job}/gap_cards", json={"terms": ["Kubernetes", "???", "   ", "-"]})
    assert r.status_code == 200, r.text
    assert [c["term"] for c in r.json()["cards"]] == ["Kubernetes"]
    r = client.post(f"/api/jobs/{job}/gap_cards/answers", json={"answers": [
        {"term": "???", "choice": "skip"},
        {"term": "Kubernetes", "choice": "yes", "text": "Ran clusters"},
    ]})
    assert r.status_code == 200, r.text
    assert r.json() == {"approved_terms": ["Kubernetes"], "saved": 1}


def test_write_routes_are_refused_in_demo_mode_and_read_routes_still_work(client, monkeypatch):
    import dev_api

    job = _add_job(client.db, "You use Go.")
    fid = client.post("/api/experience-facts", json={
        "kind": "experience", "requirement": "Go", "text": "keep",
    }).json()["id"]
    monkeypatch.setattr(dev_api, "IS_DEMO", True)
    body = {"kind": "experience", "requirement": "Rust", "text": "x"}
    assert client.post("/api/experience-facts", json=body).status_code == 403
    assert client.patch(f"/api/experience-facts/{fid}", json={"text": "y"}).status_code == 403
    assert client.delete(f"/api/experience-facts/{fid}").status_code == 403
    r = client.post(f"/api/jobs/{job}/gap_cards/answers", json={"answers": [
        {"term": "Rust", "choice": "yes", "text": "x"},
    ]})
    assert r.status_code == 403
    listed = client.get("/api/experience-facts").json()
    assert [(f["id"], f["text"]) for f in listed] == [(fid, "keep")]
    assert client.post(f"/api/jobs/{job}/gap_cards", json={"terms": ["Go"]}).status_code == 200


def test_tenant_b_cannot_patch_delete_or_read_tenant_as_job_or_facts(tmp_path, monkeypatch):
    import dev_api

    db_a, db_b = tmp_path / "a.db", tmp_path / "b.db"
    migrate_db(db_a)
    migrate_db(db_b)
    monkeypatch.setattr(dev_api, "DB_PATH", str(tmp_path / "staging.db"))
    holder = {"db": str(db_a)}
    _wire(monkeypatch, holder)
    c = TestClient(dev_api.app)
    fid = c.post("/api/experience-facts", json={
        "kind": "experience", "requirement": "Go", "text": "A's",
    }).json()["id"]
    job_a = _add_job(db_a, "Only A has this job.")
    holder["db"] = str(db_b)
    assert c.patch(f"/api/experience-facts/{fid}", json={"text": "hacked"}).status_code == 404
    assert c.delete(f"/api/experience-facts/{fid}").status_code == 404
    assert c.post(f"/api/jobs/{job_a}/gap_cards", json={"terms": ["Go"]}).status_code == 404
    r = c.post(f"/api/jobs/{job_a}/gap_cards/answers", json={"answers": [
        {"term": "Rust", "choice": "yes", "text": "B's"},
    ]})
    assert r.status_code == 200
    assert [f["requirement"] for f in c.get("/api/experience-facts").json()] == ["Rust"]
    holder["db"] = str(db_a)
    facts = c.get("/api/experience-facts").json()
    assert [(f["requirement"], f["text"]) for f in facts] == [("Go", "A's")]
