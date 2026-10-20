"""The shipped cloud LLM config must keep the safe, intended defaults.

config/llm.cloud.yaml is bind-mounted into every cloud container, so a wrong model here
reaches every tenant at once. alex-cover-writer was once the default for cover letters:
a personal fine-tune trained on donated letters that were meant to be sanitized first and
were not, which put a real donor's name into another tenant's letter (peregrine#219).
"""
from pathlib import Path

import pytest
import yaml

CLOUD_CONFIG = Path(__file__).parent.parent / "config" / "llm.cloud.yaml"


@pytest.fixture(scope="module")
def cloud_config() -> dict:
    return yaml.safe_load(CLOUD_CONFIG.read_text())


def test_no_backend_runs_a_per_person_cover_writer_model(cloud_config):
    models = {name: str(b.get("model", "")) for name, b in cloud_config["backends"].items()}
    offenders = {name: m for name, m in models.items() if "cover-writer" in m}
    assert not offenders, f"per-person fine-tune in the cloud config: {offenders}"


def test_default_cover_letter_model_is_granite_4_1_via_cf_text(cloud_config):
    from scripts.llm_router import LLMRouter

    backend_id, _model, backend = LLMRouter(cloud_config)._default_task_model("primary")

    assert backend_id == "cf_text"
    assert backend["cf_orch"]["model_candidates"] == ["granite-4.1-8b"]


def test_every_cloud_default_task_resolves_to_a_real_backend(cloud_config):
    from scripts.llm_router import LLMRouter

    router = LLMRouter(cloud_config)
    for task in ("primary", "research", "chat"):
        resolved = router._default_task_model(task)
        assert resolved is not None, f"no default model resolves for task {task!r}"
        assert resolved[2].get("enabled", True), f"default for {task!r} is a disabled backend"
