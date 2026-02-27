# Email Classifier Benchmark Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a benchmark harness that evaluates 9 HuggingFace classifiers against our 6 email labels in two modes: live IMAP visual table (`--compare`) and labeled-JSONL metrics (`--score`).

**Architecture:** Standalone scripts (`benchmark_classifier.py` + `classifier_adapters.py`) in a new isolated conda env (`job-seeker-classifiers`). Three adapter types (ZeroShot NLI, GLiClass, Reranker) normalize each model's output to our 6 labels. IMAP fetching uses stdlib only — no dependency on `imap_sync.py` or LLMRouter.

**Tech Stack:** Python 3.11, `transformers` zero-shot pipeline, `gliclass`, `FlagEmbedding`, `torch` (CUDA auto-select), `pytest`, `unittest.mock`

---

## Labels constant (referenced throughout)

```python
LABELS = [
    "interview_scheduled", "offer_received", "rejected",
    "positive_response", "survey_received", "neutral",
]
```

---

### Task 1: Conda environment

**Files:**
- Create: `scripts/classifier_service/environment.yml`

**Step 1: Create the environment file**

```yaml
name: job-seeker-classifiers
channels:
  - pytorch
  - nvidia
  - conda-forge
  - defaults
dependencies:
  - python=3.11
  - pip
  - pip:
    - torch>=2.1.0
    - transformers>=4.40.0
    - accelerate>=0.26.0
    - sentencepiece>=0.1.99
    - protobuf>=4.25.0
    - gliclass>=0.1.0
    - FlagEmbedding>=1.2.0
    - pyyaml>=6.0
    - tqdm>=4.66.0
    - pytest>=8.0.0
```

**Step 2: Create the environment**

```bash
conda env create -f scripts/classifier_service/environment.yml
```

Expected: env `job-seeker-classifiers` created successfully.

**Step 3: Verify torch + CUDA**

```bash
conda run -n job-seeker-classifiers python -c "import torch; print(torch.cuda.is_available())"
```

Expected: `True` (if GPU available).

**Step 4: Commit**

```bash
git add scripts/classifier_service/environment.yml
git commit -m "feat: add job-seeker-classifiers conda env for HF classifier benchmark"
```

---

### Task 2: Data directory + gitignore + example scoring file

**Files:**
- Modify: `.gitignore`
- Create: `data/email_score.jsonl.example`

**Step 1: Update .gitignore**

Add to `.gitignore`:
```
data/email_score.jsonl
data/email_compare_sample.jsonl
```

**Step 2: Create the example scoring file**

Create `data/email_score.jsonl.example` with fake-but-realistic emails:

```jsonl
{"subject": "Interview Invitation — Senior Engineer", "body": "Hi Alex, we'd love to schedule a 30-min phone screen. Are you available Thursday at 2pm? Please reply to confirm.", "label": "interview_scheduled"}
{"subject": "Your application to Acme Corp", "body": "Thank you for your interest in the Senior Engineer role. After careful consideration, we have decided to move forward with other candidates whose experience more closely matches our current needs.", "label": "rejected"}
{"subject": "Offer Letter — Product Manager at Initech", "body": "Dear Alex, we are thrilled to extend an offer of employment for the Product Manager position. Please find the attached offer letter outlining compensation and start date.", "label": "offer_received"}
{"subject": "Quick question about your background", "body": "Hi Alex, I came across your profile and would love to connect. We have a few roles that seem like a great match. Would you be open to a brief chat this week?", "label": "positive_response"}
{"subject": "Company Culture Survey — Acme Corp", "body": "Alex, as part of our evaluation process, we invite all candidates to complete our culture fit assessment. The survey takes approximately 15 minutes. Please click the link below.", "label": "survey_received"}
{"subject": "Application Received — DataCo", "body": "Thank you for submitting your application for the Data Engineer role at DataCo. We have received your materials and will be in touch if your qualifications match our needs.", "label": "neutral"}
{"subject": "Following up on your application", "body": "Hi Alex, I wanted to follow up on your recent application. Your background looks interesting and we'd like to learn more. Can we set up a quick call?", "label": "positive_response"}
{"subject": "We're moving forward with other candidates", "body": "Dear Alex, thank you for taking the time to interview with us. After thoughtful consideration, we have decided not to move forward with your candidacy at this time.", "label": "rejected"}
```

**Step 3: Commit**

```bash
git add .gitignore data/email_score.jsonl.example
git commit -m "feat: add scoring JSONL example and gitignore for benchmark data files"
```

---

### Task 3: ClassifierAdapter ABC + compute_metrics()

**Files:**
- Create: `scripts/classifier_adapters.py`
- Create: `tests/test_classifier_adapters.py`

**Step 1: Write the failing tests**

Create `tests/test_classifier_adapters.py`:

```python
"""Tests for classifier_adapters — no model downloads required."""
import pytest


def test_labels_constant_has_six_items():
    from scripts.classifier_adapters import LABELS
    assert len(LABELS) == 6
    assert "interview_scheduled" in LABELS
    assert "neutral" in LABELS


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
```

**Step 2: Run tests — expect FAIL**

```bash
/devl/miniconda3/envs/job-seeker/bin/pytest tests/test_classifier_adapters.py -v
```

Expected: `ModuleNotFoundError: No module named 'scripts.classifier_adapters'`

**Step 3: Create scripts/classifier_adapters.py with ABC + metrics**

```python
"""Classifier adapters for email classification benchmark.

Each adapter wraps a HuggingFace model and normalizes output to LABELS.
Models load lazily on first classify() call; call unload() to free VRAM.
"""
from __future__ import annotations

import abc
from collections import defaultdict
from typing import Any

LABELS: list[str] = [
    "interview_scheduled",
    "offer_received",
    "rejected",
    "positive_response",
    "survey_received",
    "neutral",
]

# Natural-language descriptions used by the RerankerAdapter.
LABEL_DESCRIPTIONS: dict[str, str] = {
    "interview_scheduled": "scheduling an interview, phone screen, or video call",
    "offer_received": "a formal job offer or employment offer letter",
    "rejected": "application rejected or not moving forward with candidacy",
    "positive_response": "positive recruiter interest or request to connect",
    "survey_received": "invitation to complete a culture-fit survey or assessment",
    "neutral": "automated ATS confirmation or unrelated email",
}


def _cuda_available() -> bool:
    try:
        import torch
        return torch.cuda.is_available()
    except ImportError:
        return False


def compute_metrics(
    predictions: list[str],
    gold: list[str],
    labels: list[str],
) -> dict[str, Any]:
    """Return per-label precision/recall/F1 + macro_f1 + accuracy."""
    tp: dict[str, int] = defaultdict(int)
    fp: dict[str, int] = defaultdict(int)
    fn: dict[str, int] = defaultdict(int)

    for pred, true in zip(predictions, gold):
        if pred == true:
            tp[pred] += 1
        else:
            fp[pred] += 1
            fn[true] += 1

    result: dict[str, Any] = {}
    for label in labels:
        denom_p = tp[label] + fp[label]
        denom_r = tp[label] + fn[label]
        p = tp[label] / denom_p if denom_p else 0.0
        r = tp[label] / denom_r if denom_r else 0.0
        f1 = 2 * p * r / (p + r) if (p + r) else 0.0
        result[label] = {
            "precision": p,
            "recall": r,
            "f1": f1,
            "support": denom_r,
        }

    result["__macro_f1__"] = (
        sum(v["f1"] for v in result.values() if isinstance(v, dict)) / len(labels)
    )
    result["__accuracy__"] = sum(tp.values()) / len(predictions) if predictions else 0.0
    return result


class ClassifierAdapter(abc.ABC):
    """Abstract base for all email classifier adapters."""

    @property
    @abc.abstractmethod
    def name(self) -> str: ...

    @property
    @abc.abstractmethod
    def model_id(self) -> str: ...

    @abc.abstractmethod
    def load(self) -> None:
        """Download/load the model into memory."""

    @abc.abstractmethod
    def unload(self) -> None:
        """Release model from memory."""

    @abc.abstractmethod
    def classify(self, subject: str, body: str) -> str:
        """Return one of LABELS for the given email."""
```

**Step 4: Run tests — expect PASS**

```bash
/devl/miniconda3/envs/job-seeker/bin/pytest tests/test_classifier_adapters.py -v
```

Expected: 6 tests pass.

**Step 5: Commit**

```bash
git add scripts/classifier_adapters.py tests/test_classifier_adapters.py
git commit -m "feat: ClassifierAdapter ABC + compute_metrics() with full test coverage"
```

---

### Task 4: ZeroShotAdapter

**Files:**
- Modify: `scripts/classifier_adapters.py`
- Modify: `tests/test_classifier_adapters.py`

**Step 1: Add failing tests**

Append to `tests/test_classifier_adapters.py`:

```python
def test_zeroshot_adapter_classify_mocked():
    from unittest.mock import MagicMock, patch
    from scripts.classifier_adapters import ZeroShotAdapter

    mock_pipeline = MagicMock()
    mock_pipeline.return_value = {
        "labels": ["rejected", "neutral", "interview_scheduled"],
        "scores": [0.85, 0.10, 0.05],
    }

    with patch("scripts.classifier_adapters.pipeline", mock_pipeline):
        adapter = ZeroShotAdapter("test-zs", "some/model")
        adapter.load()
        result = adapter.classify("We went with another candidate", "Thank you for applying.")

    assert result == "rejected"
    call_args = mock_pipeline.return_value.call_args
    assert "We went with another candidate" in call_args[0][0]


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
    """classify() loads the model automatically if not already loaded."""
    from unittest.mock import MagicMock, patch
    from scripts.classifier_adapters import ZeroShotAdapter

    mock_pipe_factory = MagicMock()
    mock_pipe_factory.return_value = MagicMock(return_value={
        "labels": ["neutral"], "scores": [1.0]
    })

    with patch("scripts.classifier_adapters.pipeline", mock_pipe_factory):
        adapter = ZeroShotAdapter("test-zs", "some/model")
        adapter.classify("subject", "body")  # no explicit load() call

    mock_pipe_factory.assert_called_once()
```

**Step 2: Run tests — expect FAIL**

```bash
/devl/miniconda3/envs/job-seeker/bin/pytest tests/test_classifier_adapters.py::test_zeroshot_adapter_classify_mocked -v
```

Expected: `AttributeError` — ZeroShotAdapter not defined.

**Step 3: Add import shim + ZeroShotAdapter to classifier_adapters.py**

Add after the `_cuda_available()` helper:

```python
# Lazy import shim — lets tests patch 'scripts.classifier_adapters.pipeline'
try:
    from transformers import pipeline  # type: ignore[assignment]
except ImportError:
    pipeline = None  # type: ignore[assignment]
```

Add after `ClassifierAdapter`:

```python
class ZeroShotAdapter(ClassifierAdapter):
    """Wraps any transformers zero-shot-classification pipeline."""

    def __init__(self, name: str, model_id: str) -> None:
        self._name = name
        self._model_id = model_id
        self._pipeline: Any = None

    @property
    def name(self) -> str:
        return self._name

    @property
    def model_id(self) -> str:
        return self._model_id

    def load(self) -> None:
        from transformers import pipeline as _pipeline  # noqa: PLC0415
        device = 0 if _cuda_available() else -1  # 0 = first GPU, -1 = CPU
        self._pipeline = _pipeline(
            "zero-shot-classification",
            model=self._model_id,
            device=device,
        )

    def unload(self) -> None:
        self._pipeline = None

    def classify(self, subject: str, body: str) -> str:
        if self._pipeline is None:
            self.load()
        text = f"Subject: {subject}\n\n{body[:600]}"
        result = self._pipeline(text, LABELS, multi_label=False)
        return result["labels"][0]
```

**Step 4: Run tests — expect PASS**

```bash
/devl/miniconda3/envs/job-seeker/bin/pytest tests/test_classifier_adapters.py -v
```

Expected: 9 tests pass.

**Step 5: Commit**

```bash
git add scripts/classifier_adapters.py tests/test_classifier_adapters.py
git commit -m "feat: ZeroShotAdapter — wraps transformers zero-shot-classification pipeline"
```

---

### Task 5: GLiClassAdapter

**Files:**
- Modify: `scripts/classifier_adapters.py`
- Modify: `tests/test_classifier_adapters.py`

**Step 1: Add failing tests**

Append to `tests/test_classifier_adapters.py`:

```python
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
```

**Step 2: Run tests — expect FAIL**

```bash
/devl/miniconda3/envs/job-seeker/bin/pytest tests/test_classifier_adapters.py::test_gliclass_adapter_classify_mocked -v
```

Expected: `AttributeError` — GLiClassAdapter not defined.

**Step 3: Add gliclass import shims + GLiClassAdapter**

Add import shims near top of `scripts/classifier_adapters.py` (after the pipeline shim):

```python
try:
    from gliclass import GLiClassModel, ZeroShotClassificationPipeline  # type: ignore
    from transformers import AutoTokenizer
except ImportError:
    GLiClassModel = None  # type: ignore
    ZeroShotClassificationPipeline = None  # type: ignore
    AutoTokenizer = None  # type: ignore
```

Add class after `ZeroShotAdapter`:

```python
class GLiClassAdapter(ClassifierAdapter):
    """Wraps knowledgator GLiClass models via the gliclass library."""

    def __init__(self, name: str, model_id: str) -> None:
        self._name = name
        self._model_id = model_id
        self._pipeline: Any = None

    @property
    def name(self) -> str:
        return self._name

    @property
    def model_id(self) -> str:
        return self._model_id

    def load(self) -> None:
        if GLiClassModel is None:
            raise ImportError("gliclass not installed — run: pip install gliclass")
        device = "cuda:0" if _cuda_available() else "cpu"
        model = GLiClassModel.from_pretrained(self._model_id)
        tokenizer = AutoTokenizer.from_pretrained(self._model_id)
        self._pipeline = ZeroShotClassificationPipeline(
            model,
            tokenizer,
            classification_type="single-label",
            device=device,
        )

    def unload(self) -> None:
        self._pipeline = None

    def classify(self, subject: str, body: str) -> str:
        if self._pipeline is None:
            self.load()
        text = f"Subject: {subject}\n\n{body[:600]}"
        # threshold=0.0 ensures all labels are scored; we pick the max.
        results = self._pipeline(text, LABELS, threshold=0.0)[0]
        return max(results, key=lambda r: r["score"])["label"]
```

**Step 4: Run tests — expect PASS**

```bash
/devl/miniconda3/envs/job-seeker/bin/pytest tests/test_classifier_adapters.py -v
```

Expected: 11 tests pass.

**Step 5: Commit**

```bash
git add scripts/classifier_adapters.py tests/test_classifier_adapters.py
git commit -m "feat: GLiClassAdapter — wraps gliclass zero-shot pipeline"
```

---

### Task 6: RerankerAdapter

**Files:**
- Modify: `scripts/classifier_adapters.py`
- Modify: `tests/test_classifier_adapters.py`

**Step 1: Add failing tests**

Append to `tests/test_classifier_adapters.py`:

```python
def test_reranker_adapter_picks_highest_score():
    from unittest.mock import MagicMock, patch
    from scripts.classifier_adapters import RerankerAdapter, LABELS

    mock_reranker = MagicMock()
    # Scores for each label pair — "rejected" (index 2) gets the highest
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
```

**Step 2: Run tests — expect FAIL**

```bash
/devl/miniconda3/envs/job-seeker/bin/pytest tests/test_classifier_adapters.py::test_reranker_adapter_picks_highest_score -v
```

Expected: `AttributeError` — RerankerAdapter not defined.

**Step 3: Add FlagEmbedding import shim + RerankerAdapter**

Add import shim in `scripts/classifier_adapters.py`:

```python
try:
    from FlagEmbedding import FlagReranker  # type: ignore
except ImportError:
    FlagReranker = None  # type: ignore
```

Add class after `GLiClassAdapter`:

```python
class RerankerAdapter(ClassifierAdapter):
    """Uses a BGE reranker to score (email, label_description) pairs."""

    def __init__(self, name: str, model_id: str) -> None:
        self._name = name
        self._model_id = model_id
        self._reranker: Any = None

    @property
    def name(self) -> str:
        return self._name

    @property
    def model_id(self) -> str:
        return self._model_id

    def load(self) -> None:
        if FlagReranker is None:
            raise ImportError("FlagEmbedding not installed — run: pip install FlagEmbedding")
        self._reranker = FlagReranker(self._model_id, use_fp16=_cuda_available())

    def unload(self) -> None:
        self._reranker = None

    def classify(self, subject: str, body: str) -> str:
        if self._reranker is None:
            self.load()
        text = f"Subject: {subject}\n\n{body[:600]}"
        pairs = [[text, LABEL_DESCRIPTIONS[label]] for label in LABELS]
        scores: list[float] = self._reranker.compute_score(pairs, normalize=True)
        return LABELS[scores.index(max(scores))]
```

**Step 4: Run tests — expect PASS**

```bash
/devl/miniconda3/envs/job-seeker/bin/pytest tests/test_classifier_adapters.py -v
```

Expected: 13 tests pass.

**Step 5: Commit**

```bash
git add scripts/classifier_adapters.py tests/test_classifier_adapters.py
git commit -m "feat: RerankerAdapter — scores (email, label_description) pairs via BGE reranker"
```

---

### Task 7: MODEL_REGISTRY + --list-models + CLI skeleton

**Files:**
- Create: `scripts/benchmark_classifier.py`
- Create: `tests/test_benchmark_classifier.py`

**Step 1: Write failing tests**

Create `tests/test_benchmark_classifier.py`:

```python
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
```

**Step 2: Run tests — expect FAIL**

```bash
/devl/miniconda3/envs/job-seeker/bin/pytest tests/test_benchmark_classifier.py -v
```

Expected: `ModuleNotFoundError: No module named 'scripts.benchmark_classifier'`

**Step 3: Create benchmark_classifier.py with registry + skeleton**

```python
#!/usr/bin/env python
"""
Email classifier benchmark — compare HuggingFace models against our 6 labels.

Usage:
    # List available models
    conda run -n job-seeker-classifiers python scripts/benchmark_classifier.py --list-models

    # Score against labeled JSONL
    conda run -n job-seeker-classifiers python scripts/benchmark_classifier.py --score

    # Visual comparison on live IMAP emails
    conda run -n job-seeker-classifiers python scripts/benchmark_classifier.py --compare --limit 20

    # Include slow/large models
    conda run -n job-seeker-classifiers python scripts/benchmark_classifier.py --score --include-slow
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.classifier_adapters import (
    LABELS,
    ClassifierAdapter,
    GLiClassAdapter,
    RerankerAdapter,
    ZeroShotAdapter,
    compute_metrics,
)

# ---------------------------------------------------------------------------
# Model registry
# ---------------------------------------------------------------------------

MODEL_REGISTRY: dict[str, dict[str, Any]] = {
    "deberta-zeroshot": {
        "adapter": ZeroShotAdapter,
        "model_id": "MoritzLaurer/DeBERTa-v3-large-zeroshot-v2.0",
        "params": "400M",
        "default": True,
    },
    "deberta-small": {
        "adapter": ZeroShotAdapter,
        "model_id": "cross-encoder/nli-deberta-v3-small",
        "params": "100M",
        "default": True,
    },
    "gliclass-large": {
        "adapter": GLiClassAdapter,
        "model_id": "knowledgator/gliclass-instruct-large-v1.0",
        "params": "400M",
        "default": True,
    },
    "bart-mnli": {
        "adapter": ZeroShotAdapter,
        "model_id": "facebook/bart-large-mnli",
        "params": "400M",
        "default": True,
    },
    "bge-m3-zeroshot": {
        "adapter": ZeroShotAdapter,
        "model_id": "MoritzLaurer/bge-m3-zeroshot-v2.0",
        "params": "600M",
        "default": True,
    },
    "bge-reranker": {
        "adapter": RerankerAdapter,
        "model_id": "BAAI/bge-reranker-v2-m3",
        "params": "600M",
        "default": False,
    },
    "deberta-xlarge": {
        "adapter": ZeroShotAdapter,
        "model_id": "microsoft/deberta-xlarge-mnli",
        "params": "750M",
        "default": False,
    },
    "mdeberta-mnli": {
        "adapter": ZeroShotAdapter,
        "model_id": "MoritzLaurer/mDeBERTa-v3-base-mnli-xnli",
        "params": "300M",
        "default": False,
    },
    "xlm-roberta-anli": {
        "adapter": ZeroShotAdapter,
        "model_id": "vicgalle/xlm-roberta-large-xnli-anli",
        "params": "600M",
        "default": False,
    },
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_scoring_jsonl(path: str) -> list[dict[str, str]]:
    """Load labeled examples from a JSONL file for benchmark scoring."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(
            f"Scoring file not found: {path}\n"
            f"Copy data/email_score.jsonl.example → data/email_score.jsonl and label your emails."
        )
    rows = []
    with p.open() as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _active_models(include_slow: bool) -> dict[str, dict[str, Any]]:
    return {k: v for k, v in MODEL_REGISTRY.items() if v["default"] or include_slow}


# ---------------------------------------------------------------------------
# Subcommands
# ---------------------------------------------------------------------------

def cmd_list_models(_args: argparse.Namespace) -> None:
    print(f"\n{'Name':<20} {'Params':<8} {'Default':<20} {'Adapter':<15} Model ID")
    print("-" * 100)
    for name, entry in MODEL_REGISTRY.items():
        adapter_name = entry["adapter"].__name__
        default_flag = "yes" if entry["default"] else "(--include-slow)"
        print(f"{name:<20} {entry['params']:<8} {default_flag:<20} {adapter_name:<15} {entry['model_id']}")
    print()


def cmd_score(_args: argparse.Namespace) -> None:
    raise NotImplementedError("--score implemented in Task 8")


def cmd_compare(_args: argparse.Namespace) -> None:
    raise NotImplementedError("--compare implemented in Task 9")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Benchmark HuggingFace email classifiers against our 6 labels."
    )
    parser.add_argument("--list-models", action="store_true", help="Show model registry and exit")
    parser.add_argument("--score", action="store_true", help="Score against labeled JSONL")
    parser.add_argument("--compare", action="store_true", help="Visual table on live IMAP emails")
    parser.add_argument("--score-file", default="data/email_score.jsonl", help="Path to labeled JSONL")
    parser.add_argument("--limit", type=int, default=20, help="Max emails for --compare")
    parser.add_argument("--days", type=int, default=90, help="Days back for IMAP search")
    parser.add_argument("--include-slow", action="store_true", help="Include non-default heavy models")
    parser.add_argument("--models", nargs="+", help="Override: run only these model names")

    args = parser.parse_args()

    if args.list_models:
        cmd_list_models(args)
    elif args.score:
        cmd_score(args)
    elif args.compare:
        cmd_compare(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
```

**Step 4: Run tests — expect PASS**

```bash
/devl/miniconda3/envs/job-seeker/bin/pytest tests/test_benchmark_classifier.py -v
```

Expected: 5 tests pass.

**Step 5: Smoke-test --list-models**

```bash
conda run -n job-seeker-classifiers python scripts/benchmark_classifier.py --list-models
```

Expected: table of 9 models printed without error.

**Step 6: Commit**

```bash
git add scripts/benchmark_classifier.py tests/test_benchmark_classifier.py
git commit -m "feat: benchmark_classifier skeleton — MODEL_REGISTRY, --list-models, CLI"
```

---

### Task 8: --score mode

**Files:**
- Modify: `scripts/benchmark_classifier.py`
- Modify: `tests/test_benchmark_classifier.py`

**Step 1: Add failing tests**

Append to `tests/test_benchmark_classifier.py`:

```python
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
```

**Step 2: Run tests — expect FAIL**

```bash
/devl/miniconda3/envs/job-seeker/bin/pytest tests/test_benchmark_classifier.py::test_run_scoring_with_mock_adapters -v
```

Expected: `ImportError` — `run_scoring` not defined.

**Step 3: Implement run_scoring() and cmd_score()**

Add `import time` at the top of `benchmark_classifier.py`. Then add `run_scoring()`:

```python
def run_scoring(
    adapters: list[ClassifierAdapter],
    score_file: str,
) -> dict[str, Any]:
    """Run all adapters against a labeled JSONL. Returns per-adapter metrics."""
    import time
    rows = load_scoring_jsonl(score_file)
    gold = [r["label"] for r in rows]
    results: dict[str, Any] = {}

    for adapter in adapters:
        preds: list[str] = []
        t0 = time.monotonic()
        for row in rows:
            try:
                pred = adapter.classify(row["subject"], row["body"])
            except Exception as exc:
                print(f"  [{adapter.name}] ERROR on '{row['subject'][:40]}': {exc}", flush=True)
                pred = "neutral"
            preds.append(pred)
        elapsed_ms = (time.monotonic() - t0) * 1000
        metrics = compute_metrics(preds, gold, LABELS)
        metrics["latency_ms"] = round(elapsed_ms / len(rows), 1)
        results[adapter.name] = metrics
        adapter.unload()

    return results
```

Replace the `cmd_score` stub:

```python
def cmd_score(args: argparse.Namespace) -> None:
    active = _active_models(args.include_slow)
    if args.models:
        active = {k: v for k, v in active.items() if k in args.models}

    adapters = [
        entry["adapter"](name, entry["model_id"])
        for name, entry in active.items()
    ]

    print(f"\nScoring {len(adapters)} model(s) against {args.score_file} …\n")
    results = run_scoring(adapters, args.score_file)

    # Summary table
    col = 12
    print(f"{'Model':<22}" + f"{'macro-F1':>{col}} {'Accuracy':>{col}} {'ms/email':>{col}}")
    print("-" * (22 + col * 3 + 2))
    for name, m in results.items():
        print(
            f"{name:<22}"
            f"{m['__macro_f1__']:>{col}.3f}"
            f"{m['__accuracy__']:>{col}.3f}"
            f"{m['latency_ms']:>{col}.1f}"
        )

    # Per-label F1 breakdown
    print("\nPer-label F1:")
    names = list(results.keys())
    print(f"{'Label':<25}" + "".join(f"{n[:11]:>{col}}" for n in names))
    print("-" * (25 + col * len(names)))
    for label in LABELS:
        row_str = f"{label:<25}"
        for m in results.values():
            row_str += f"{m[label]['f1']:>{col}.3f}"
        print(row_str)
    print()
```

**Step 4: Run tests — expect PASS**

```bash
/devl/miniconda3/envs/job-seeker/bin/pytest tests/test_benchmark_classifier.py -v
```

Expected: 7 tests pass.

**Step 5: Commit**

```bash
git add scripts/benchmark_classifier.py tests/test_benchmark_classifier.py
git commit -m "feat: --score mode with macro-F1, accuracy, latency, and per-label F1 table"
```

---

### Task 9: --compare mode (stdlib IMAP + table output)

**Files:**
- Modify: `scripts/benchmark_classifier.py`

**Step 1: Add IMAP fetch helpers**

Add after the `_active_models()` helper in `benchmark_classifier.py`:

```python
import email as _email_lib
import imaplib
from datetime import datetime, timedelta

_BROAD_TERMS = [
    "interview", "opportunity", "offer letter",
    "job offer", "application", "recruiting",
]


def _load_imap_config() -> dict[str, Any]:
    import yaml
    cfg_path = Path(__file__).parent.parent / "config" / "email.yaml"
    with cfg_path.open() as f:
        return yaml.safe_load(f)


def _imap_connect(cfg: dict[str, Any]) -> imaplib.IMAP4_SSL:
    conn = imaplib.IMAP4_SSL(cfg["host"], cfg.get("port", 993))
    conn.login(cfg["username"], cfg["password"])
    return conn


def _decode_part(part: Any) -> str:
    charset = part.get_content_charset() or "utf-8"
    try:
        return part.get_payload(decode=True).decode(charset, errors="replace")
    except Exception:
        return ""


def _parse_uid(conn: imaplib.IMAP4_SSL, uid: bytes) -> dict[str, str] | None:
    try:
        _, data = conn.uid("fetch", uid, "(RFC822)")
        raw = data[0][1]
        msg = _email_lib.message_from_bytes(raw)
        subject = str(msg.get("subject", "")).strip()
        body = ""
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_type() == "text/plain":
                    body = _decode_part(part)
                    break
        else:
            body = _decode_part(msg)
        return {"subject": subject, "body": body}
    except Exception:
        return None


def _fetch_imap_sample(limit: int, days: int) -> list[dict[str, str]]:
    cfg = _load_imap_config()
    conn = _imap_connect(cfg)
    since = (datetime.now() - timedelta(days=days)).strftime("%d-%b-%Y")
    conn.select("INBOX")

    seen_uids: dict[bytes, None] = {}
    for term in _BROAD_TERMS:
        _, data = conn.uid("search", None, f'(SUBJECT "{term}" SINCE {since})')
        for uid in (data[0] or b"").split():
            seen_uids[uid] = None

    sample = list(seen_uids.keys())[:limit]
    emails = []
    for uid in sample:
        parsed = _parse_uid(conn, uid)
        if parsed:
            emails.append(parsed)
    try:
        conn.logout()
    except Exception:
        pass
    return emails
```

**Step 2: Replace cmd_compare stub**

```python
def cmd_compare(args: argparse.Namespace) -> None:
    active = _active_models(args.include_slow)
    if args.models:
        active = {k: v for k, v in active.items() if k in args.models}

    print(f"Fetching up to {args.limit} emails from IMAP …")
    emails = _fetch_imap_sample(args.limit, args.days)
    print(f"Fetched {len(emails)} emails. Loading {len(active)} model(s) …\n")

    adapters = [
        entry["adapter"](name, entry["model_id"])
        for name, entry in active.items()
    ]
    model_names = [a.name for a in adapters]

    col = 22
    subj_w = 50
    print(f"{'Subject':<{subj_w}}" + "".join(f"{n:<{col}}" for n in model_names))
    print("-" * (subj_w + col * len(model_names)))

    for row in emails:
        short_subj = row["subject"][:subj_w - 1] if len(row["subject"]) > subj_w else row["subject"]
        line = f"{short_subj:<{subj_w}}"
        for adapter in adapters:
            try:
                label = adapter.classify(row["subject"], row["body"])
            except Exception as exc:
                label = f"ERR:{str(exc)[:8]}"
            line += f"{label:<{col}}"
        print(line, flush=True)

    for adapter in adapters:
        adapter.unload()
    print()
```

**Step 3: Run full test suite**

```bash
/devl/miniconda3/envs/job-seeker/bin/pytest tests/test_benchmark_classifier.py tests/test_classifier_adapters.py -v
```

Expected: all 13 tests pass.

**Step 4: Commit**

```bash
git add scripts/benchmark_classifier.py
git commit -m "feat: --compare mode — stdlib IMAP fetch + side-by-side model label table"
```

---

### Task 10: First real benchmark run

No code changes — first live execution.

**Step 1: Create your labeled scoring file**

```bash
cp data/email_score.jsonl.example data/email_score.jsonl
```

Open `data/email_score.jsonl` and replace the fake examples with at least 10 real emails from your inbox. Format per line:

```json
{"subject": "actual subject", "body": "first 600 chars of body", "label": "one_of_six_labels"}
```

Valid labels: `interview_scheduled`, `offer_received`, `rejected`, `positive_response`, `survey_received`, `neutral`

**Step 2: Run --score with default models**

```bash
conda run -n job-seeker-classifiers python scripts/benchmark_classifier.py --score
```

Models download on first run (~400–600MB each) — allow a few minutes.

**Step 3: Run --compare on live IMAP**

```bash
conda run -n job-seeker-classifiers python scripts/benchmark_classifier.py --compare --limit 15
```

**Step 4: Run slow models (optional)**

```bash
conda run -n job-seeker-classifiers python scripts/benchmark_classifier.py --score --include-slow
```

**Step 5: Capture results (optional)**

```bash
conda run -n job-seeker-classifiers python scripts/benchmark_classifier.py --score \
  > docs/plans/2026-02-26-benchmark-results.txt 2>&1
git add docs/plans/2026-02-26-benchmark-results.txt
git commit -m "docs: initial HF classifier benchmark results"
```

---

## Quick Reference

```bash
# Create env (once)
conda env create -f scripts/classifier_service/environment.yml

# List models
conda run -n job-seeker-classifiers python scripts/benchmark_classifier.py --list-models

# Score against labeled data (5 default models)
conda run -n job-seeker-classifiers python scripts/benchmark_classifier.py --score

# Live IMAP visual table
conda run -n job-seeker-classifiers python scripts/benchmark_classifier.py --compare --limit 20

# Single model only
conda run -n job-seeker-classifiers python scripts/benchmark_classifier.py --score --models deberta-zeroshot

# Run all tests (job-seeker env — mocks only, no downloads)
/devl/miniconda3/envs/job-seeker/bin/pytest tests/test_classifier_adapters.py tests/test_benchmark_classifier.py -v
```
