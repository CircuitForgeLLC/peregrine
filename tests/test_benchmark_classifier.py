"""Tests for benchmark_classifier — no model downloads required."""
import pytest


def test_registry_has_nine_models():
    from scripts.benchmark_classifier import MODEL_REGISTRY
    assert len(MODEL_REGISTRY) == 9


def test_registry_default_count():
    from scripts.benchmark_classifier import MODEL_REGISTRY
    defaults = [k for k, v in MODEL_REGISTRY.items() if v["default"]]
    assert len(defaults) == 5


def test_registry_entries_have_required_keys():
    from scripts.benchmark_classifier import MODEL_REGISTRY
    from scripts.classifier_adapters import ClassifierAdapter
    for name, entry in MODEL_REGISTRY.items():
        assert "adapter" in entry, f"{name} missing 'adapter'"
        assert "model_id" in entry, f"{name} missing 'model_id'"
        assert "params" in entry, f"{name} missing 'params'"
        assert "default" in entry, f"{name} missing 'default'"
        assert issubclass(entry["adapter"], ClassifierAdapter), \
            f"{name} adapter must be a ClassifierAdapter subclass"


def test_load_scoring_jsonl(tmp_path):
    from scripts.benchmark_classifier import load_scoring_jsonl
    import json
    f = tmp_path / "score.jsonl"
    rows = [
        {"subject": "Hi", "body": "Body text", "label": "neutral"},
        {"subject": "Interview", "body": "Schedule a call", "label": "interview_scheduled"},
    ]
    f.write_text("\n".join(json.dumps(r) for r in rows))
    result = load_scoring_jsonl(str(f))
    assert len(result) == 2
    assert result[0]["label"] == "neutral"


def test_load_scoring_jsonl_missing_file():
    from scripts.benchmark_classifier import load_scoring_jsonl
    with pytest.raises(FileNotFoundError):
        load_scoring_jsonl("/nonexistent/path.jsonl")


def test_run_scoring_with_mock_adapters(tmp_path):
    """run_scoring() returns per-model metrics using mock adapters."""
    import json
    from unittest.mock import MagicMock
    from scripts.benchmark_classifier import run_scoring

    score_file = tmp_path / "score.jsonl"
    rows = [
        {"subject": "Interview", "body": "Let's schedule", "label": "interview_scheduled"},
        {"subject": "Sorry", "body": "We went with others", "label": "rejected"},
        {"subject": "Offer", "body": "We are pleased", "label": "offer_received"},
    ]
    score_file.write_text("\n".join(json.dumps(r) for r in rows))

    perfect = MagicMock()
    perfect.name = "perfect"
    perfect.classify.side_effect = lambda s, b: (
        "interview_scheduled" if "Interview" in s else
        "rejected" if "Sorry" in s else "offer_received"
    )

    bad = MagicMock()
    bad.name = "bad"
    bad.classify.return_value = "neutral"

    results = run_scoring([perfect, bad], str(score_file))

    assert results["perfect"]["__accuracy__"] == pytest.approx(1.0)
    assert results["bad"]["__accuracy__"] == pytest.approx(0.0)
    assert "latency_ms" in results["perfect"]


def test_run_scoring_handles_classify_error(tmp_path):
    """run_scoring() falls back to 'neutral' on exception and continues."""
    import json
    from unittest.mock import MagicMock
    from scripts.benchmark_classifier import run_scoring

    score_file = tmp_path / "score.jsonl"
    score_file.write_text(json.dumps({"subject": "Hi", "body": "Body", "label": "neutral"}))

    broken = MagicMock()
    broken.name = "broken"
    broken.classify.side_effect = RuntimeError("model crashed")

    results = run_scoring([broken], str(score_file))
    assert "broken" in results
