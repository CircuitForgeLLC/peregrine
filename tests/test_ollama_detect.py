from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient


def test_ollama_detect_tries_docker_candidates_first_when_dockerized():
    import dev_api
    client = TestClient(dev_api.app)
    calls = []

    def fake_get(url, **kw):
        calls.append(url)
        resp = MagicMock()
        resp.status_code = 200 if "host.docker.internal" in url else 599
        return resp

    with patch.object(dev_api, "_running_in_docker", return_value=True), \
         patch("requests.get", side_effect=fake_get):
        resp = client.post("/api/settings/system/ollama-detect", json={"port": 11434})

    assert resp.status_code == 200
    body = resp.json()
    assert body["found"] is True
    assert body["host"] == "host.docker.internal"
    assert calls[0].startswith("http://host.docker.internal")


def test_ollama_detect_tries_localhost_first_when_not_dockerized():
    import dev_api
    client = TestClient(dev_api.app)

    def fake_get(url, **kw):
        resp = MagicMock()
        resp.status_code = 200 if ("localhost" in url or "127.0.0.1" in url) else 599
        return resp

    with patch.object(dev_api, "_running_in_docker", return_value=False), \
         patch("requests.get", side_effect=fake_get):
        resp = client.post("/api/settings/system/ollama-detect", json={"port": 11434})

    body = resp.json()
    assert body["found"] is True
    assert body["host"] in ("localhost", "127.0.0.1")


def test_ollama_detect_reports_not_found_when_nothing_reachable():
    import dev_api
    client = TestClient(dev_api.app)
    with patch.object(dev_api, "_running_in_docker", return_value=True), \
         patch("requests.get", side_effect=Exception("connection refused")):
        resp = client.post("/api/settings/system/ollama-detect", json={"port": 11434})
    body = resp.json()
    assert body["found"] is False
    assert len(body["tried"]) >= 2
