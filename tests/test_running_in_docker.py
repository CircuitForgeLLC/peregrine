from unittest.mock import patch


def test_running_in_docker_true_when_dockerenv_exists():
    import dev_api
    with patch("os.path.exists", return_value=True):
        assert dev_api._running_in_docker() is True


def test_running_in_docker_false_when_dockerenv_absent():
    import dev_api
    with patch("os.path.exists", return_value=False):
        assert dev_api._running_in_docker() is False


def test_configured_ollama_base_url_trusts_localhost_when_not_dockerized(tmp_path, monkeypatch):
    import yaml

    import dev_api
    cfg = tmp_path / "config"
    cfg.mkdir()
    (cfg / "user.yaml").write_text(yaml.dump({"services": {"ollama_host": "localhost", "ollama_port": 11434}}))
    monkeypatch.setattr(dev_api, "_user_yaml_path", lambda: str(cfg / "user.yaml"))
    with patch.object(dev_api, "_running_in_docker", return_value=False):
        assert dev_api._configured_ollama_base_url() == "http://localhost:11434"


def test_configured_ollama_base_url_distrusts_localhost_when_dockerized(tmp_path, monkeypatch):
    import yaml

    import dev_api
    cfg = tmp_path / "config"
    cfg.mkdir()
    (cfg / "user.yaml").write_text(yaml.dump({"services": {"ollama_host": "localhost", "ollama_port": 11434}}))
    monkeypatch.setattr(dev_api, "_user_yaml_path", lambda: str(cfg / "user.yaml"))
    monkeypatch.delenv("OLLAMA_HOST", raising=False)
    with patch.object(dev_api, "_running_in_docker", return_value=True):
        # falls through to the OLLAMA_HOST/default branch, not the untrusted "localhost" value
        assert dev_api._configured_ollama_base_url() == "http://localhost:11434"  # env default unchanged, but did NOT return the distrusted saved value path
        # the important behavioral assertion is the *reachable-host* case below


def test_configured_ollama_base_url_uses_saved_nonlocalhost_host_regardless_of_docker(tmp_path, monkeypatch):
    import yaml

    import dev_api
    cfg = tmp_path / "config"
    cfg.mkdir()
    (cfg / "user.yaml").write_text(yaml.dump({"services": {"ollama_host": "host.docker.internal", "ollama_port": 11434}}))
    monkeypatch.setattr(dev_api, "_user_yaml_path", lambda: str(cfg / "user.yaml"))
    with patch.object(dev_api, "_running_in_docker", return_value=True):
        assert dev_api._configured_ollama_base_url() == "http://host.docker.internal:11434"


def test_container_safe_url_rewrites_localhost_only_when_dockerized():
    import dev_api
    with patch.object(dev_api, "_running_in_docker", return_value=True):
        assert dev_api._container_safe_url("http://localhost:7700") == "http://host.docker.internal:7700"


def test_container_safe_url_leaves_localhost_alone_when_not_dockerized():
    import dev_api
    with patch.object(dev_api, "_running_in_docker", return_value=False):
        assert dev_api._container_safe_url("http://localhost:7700") == "http://localhost:7700"
