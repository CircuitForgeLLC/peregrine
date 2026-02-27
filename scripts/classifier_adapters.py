"""Classifier adapters for email classification benchmark.

Each adapter wraps a HuggingFace model and normalizes output to LABELS.
Models load lazily on first classify() call; call unload() to free VRAM.
"""
from __future__ import annotations

import abc
from collections import defaultdict
from typing import Any

__all__ = [
    "LABELS",
    "LABEL_DESCRIPTIONS",
    "compute_metrics",
    "ClassifierAdapter",
    "ZeroShotAdapter",
    "GLiClassAdapter",
    "RerankerAdapter",
]

LABELS: list[str] = [
    "interview_scheduled",
    "offer_received",
    "rejected",
    "positive_response",
    "survey_received",
    "neutral",
    "event_rescheduled",
    "unrelated",
    "digest",
]

# Natural-language descriptions used by the RerankerAdapter.
LABEL_DESCRIPTIONS: dict[str, str] = {
    "interview_scheduled": "scheduling an interview, phone screen, or video call",
    "offer_received": "a formal job offer or employment offer letter",
    "rejected": "application rejected or not moving forward with candidacy",
    "positive_response": "positive recruiter interest or request to connect",
    "survey_received": "invitation to complete a culture-fit survey or assessment",
    "neutral": "automated ATS confirmation such as application received",
    "event_rescheduled": "an interview or scheduled event moved to a new time",
    "unrelated": "non-job-search email unrelated to any application or recruiter",
    "digest": "job digest or multi-listing email with multiple job postings",
}

# Lazy import shims — allow tests to patch without requiring the libs installed.
try:
    from transformers import pipeline  # type: ignore[assignment]
except ImportError:
    pipeline = None  # type: ignore[assignment]

try:
    from gliclass import GLiClassModel, ZeroShotClassificationPipeline  # type: ignore
    from transformers import AutoTokenizer
except ImportError:
    GLiClassModel = None  # type: ignore
    ZeroShotClassificationPipeline = None  # type: ignore
    AutoTokenizer = None  # type: ignore

try:
    from FlagEmbedding import FlagReranker  # type: ignore
except ImportError:
    FlagReranker = None  # type: ignore


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

    labels_with_support = [label for label in labels if result[label]["support"] > 0]
    if labels_with_support:
        result["__macro_f1__"] = (
            sum(result[label]["f1"] for label in labels_with_support) / len(labels_with_support)
        )
    else:
        result["__macro_f1__"] = 0.0
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


class ZeroShotAdapter(ClassifierAdapter):
    """Wraps any transformers zero-shot-classification pipeline.

    load() calls pipeline("zero-shot-classification", model=..., device=...) to get
    an inference callable, stored as self._pipeline.  classify() then calls
    self._pipeline(text, LABELS, multi_label=False).  In tests, patch
    'scripts.classifier_adapters.pipeline' with a MagicMock whose .return_value is
    itself a MagicMock(return_value={...}) to simulate both the factory call and the
    inference call.

    two_pass: if True, classify() runs a second pass restricted to the top-2 labels
    from the first pass, forcing a binary choice.  This typically improves confidence
    without the accuracy cost of a full 6-label second run.
    """

    def __init__(self, name: str, model_id: str, two_pass: bool = False) -> None:
        self._name = name
        self._model_id = model_id
        self._pipeline: Any = None
        self._two_pass = two_pass

    @property
    def name(self) -> str:
        return self._name

    @property
    def model_id(self) -> str:
        return self._model_id

    def load(self) -> None:
        import scripts.classifier_adapters as _mod  # noqa: PLC0415
        _pipe_fn = _mod.pipeline
        if _pipe_fn is None:
            raise ImportError("transformers not installed — run: pip install transformers")
        device = 0 if _cuda_available() else -1
        # Instantiate the pipeline once; classify() calls the resulting object on each text.
        self._pipeline = _pipe_fn("zero-shot-classification", model=self._model_id, device=device)

    def unload(self) -> None:
        self._pipeline = None

    def classify(self, subject: str, body: str) -> str:
        if self._pipeline is None:
            self.load()
        text = f"Subject: {subject}\n\n{body[:600]}"
        result = self._pipeline(text, LABELS, multi_label=False)
        if self._two_pass and len(result["labels"]) >= 2:
            top2 = result["labels"][:2]
            result = self._pipeline(text, top2, multi_label=False)
        return result["labels"][0]


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
        results = self._pipeline(text, LABELS, threshold=0.0)[0]
        return max(results, key=lambda r: r["score"])["label"]


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
