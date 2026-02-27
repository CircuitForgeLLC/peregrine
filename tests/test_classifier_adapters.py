"""Tests for classifier_adapters — no model downloads required."""
import pytest


def test_labels_constant_has_nine_items():
    from scripts.classifier_adapters import LABELS
    assert len(LABELS) == 9
    assert "interview_scheduled" in LABELS
    assert "neutral" in LABELS
    assert "event_rescheduled" in LABELS
    assert "unrelated" in LABELS
    assert "digest" in LABELS


def test_compute_metrics_perfect_predictions():
    from scripts.classifier_adapters import compute_metrics, LABELS
    gold  = ["rejected", "interview_scheduled", "neutral"]
    preds = ["rejected", "interview_scheduled", "neutral"]
    m = compute_metrics(preds, gold, LABELS)
    assert m["rejected"]["f1"] == pytest.approx(1.0)
    assert m["__accuracy__"] == pytest.approx(1.0)
    assert m["__macro_f1__"] == pytest.approx(1.0)


def test_compute_metrics_all_wrong():
    from scripts.classifier_adapters import compute_metrics, LABELS
    gold  = ["rejected",  "rejected"]
    preds = ["neutral",   "interview_scheduled"]
    m = compute_metrics(preds, gold, LABELS)
    assert m["rejected"]["recall"] == pytest.approx(0.0)
    assert m["__accuracy__"] == pytest.approx(0.0)


def test_compute_metrics_partial():
    from scripts.classifier_adapters import compute_metrics, LABELS
    gold  = ["rejected", "neutral", "rejected"]
    preds = ["rejected", "neutral", "interview_scheduled"]
    m = compute_metrics(preds, gold, LABELS)
    assert m["rejected"]["precision"] == pytest.approx(1.0)
    assert m["rejected"]["recall"]    == pytest.approx(0.5)
    assert m["neutral"]["f1"]         == pytest.approx(1.0)
    assert m["__accuracy__"]          == pytest.approx(2 / 3)


def test_compute_metrics_empty():
    from scripts.classifier_adapters import compute_metrics, LABELS
    m = compute_metrics([], [], LABELS)
    assert m["__accuracy__"] == pytest.approx(0.0)


def test_classifier_adapter_is_abstract():
    from scripts.classifier_adapters import ClassifierAdapter
    with pytest.raises(TypeError):
        ClassifierAdapter()


# ---- ZeroShotAdapter tests ----

def test_zeroshot_adapter_classify_mocked():
    from unittest.mock import MagicMock, patch
    from scripts.classifier_adapters import ZeroShotAdapter

    # Two-level mock: factory call returns pipeline instance; instance call returns inference result.
    mock_pipe_factory = MagicMock()
    mock_pipe_factory.return_value = MagicMock(return_value={
        "labels": ["rejected", "neutral", "interview_scheduled"],
        "scores": [0.85, 0.10, 0.05],
    })

    with patch("scripts.classifier_adapters.pipeline", mock_pipe_factory):
        adapter = ZeroShotAdapter("test-zs", "some/model")
        adapter.load()
        result = adapter.classify("We went with another candidate", "Thank you for applying.")

    assert result == "rejected"
    # Factory was called with the correct task type
    assert mock_pipe_factory.call_args[0][0] == "zero-shot-classification"
    # Pipeline instance was called with the email text
    assert "We went with another candidate" in mock_pipe_factory.return_value.call_args[0][0]


def test_zeroshot_adapter_unload_clears_pipeline():
    from unittest.mock import MagicMock, patch
    from scripts.classifier_adapters import ZeroShotAdapter

    with patch("scripts.classifier_adapters.pipeline", MagicMock()):
        adapter = ZeroShotAdapter("test-zs", "some/model")
        adapter.load()
        assert adapter._pipeline is not None
        adapter.unload()
        assert adapter._pipeline is None


def test_zeroshot_adapter_lazy_loads():
    from unittest.mock import MagicMock, patch
    from scripts.classifier_adapters import ZeroShotAdapter

    mock_pipe_factory = MagicMock()
    mock_pipe_factory.return_value = MagicMock(return_value={
        "labels": ["neutral"], "scores": [1.0]
    })

    with patch("scripts.classifier_adapters.pipeline", mock_pipe_factory):
        adapter = ZeroShotAdapter("test-zs", "some/model")
        adapter.classify("subject", "body")

    mock_pipe_factory.assert_called_once()


# ---- GLiClassAdapter tests ----

def test_gliclass_adapter_classify_mocked():
    from unittest.mock import MagicMock, patch
    from scripts.classifier_adapters import GLiClassAdapter

    mock_pipeline_instance = MagicMock()
    mock_pipeline_instance.return_value = [[
        {"label": "interview_scheduled", "score": 0.91},
        {"label": "neutral", "score": 0.05},
        {"label": "rejected", "score": 0.04},
    ]]

    with patch("scripts.classifier_adapters.GLiClassModel") as _mc, \
         patch("scripts.classifier_adapters.AutoTokenizer") as _mt, \
         patch("scripts.classifier_adapters.ZeroShotClassificationPipeline",
               return_value=mock_pipeline_instance):
        adapter = GLiClassAdapter("test-gli", "some/gliclass-model")
        adapter.load()
        result = adapter.classify("Interview invitation", "Let's schedule a call.")

    assert result == "interview_scheduled"


def test_gliclass_adapter_returns_highest_score():
    from unittest.mock import MagicMock, patch
    from scripts.classifier_adapters import GLiClassAdapter

    mock_pipeline_instance = MagicMock()
    mock_pipeline_instance.return_value = [[
        {"label": "neutral", "score": 0.02},
        {"label": "offer_received", "score": 0.88},
        {"label": "rejected", "score": 0.10},
    ]]

    with patch("scripts.classifier_adapters.GLiClassModel"), \
         patch("scripts.classifier_adapters.AutoTokenizer"), \
         patch("scripts.classifier_adapters.ZeroShotClassificationPipeline",
               return_value=mock_pipeline_instance):
        adapter = GLiClassAdapter("test-gli", "some/model")
        adapter.load()
        result = adapter.classify("Offer letter enclosed", "Dear Alex, we are pleased to offer...")

    assert result == "offer_received"


# ---- RerankerAdapter tests ----

def test_reranker_adapter_picks_highest_score():
    from unittest.mock import MagicMock, patch
    from scripts.classifier_adapters import RerankerAdapter, LABELS

    mock_reranker = MagicMock()
    mock_reranker.compute_score.return_value = [0.1, 0.05, 0.85, 0.05, 0.02, 0.03]

    with patch("scripts.classifier_adapters.FlagReranker", return_value=mock_reranker):
        adapter = RerankerAdapter("test-rr", "BAAI/bge-reranker-v2-m3")
        adapter.load()
        result = adapter.classify(
            "We regret to inform you",
            "After careful consideration we are moving forward with other candidates.",
        )

    assert result == "rejected"
    pairs = mock_reranker.compute_score.call_args[0][0]
    assert len(pairs) == len(LABELS)


def test_reranker_adapter_descriptions_cover_all_labels():
    from scripts.classifier_adapters import LABEL_DESCRIPTIONS, LABELS
    assert set(LABEL_DESCRIPTIONS.keys()) == set(LABELS)
