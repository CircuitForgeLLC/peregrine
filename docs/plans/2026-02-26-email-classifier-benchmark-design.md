# Email Classifier Benchmark — Design

**Date:** 2026-02-26
**Status:** Approved

## Problem

The current `classify_stage_signal()` in `scripts/imap_sync.py` uses `llama3.1:8b` via
Ollama for 6-label email classification. This is slow, requires a running Ollama instance,
and accuracy is unverified against alternatives. This design establishes a benchmark harness
to evaluate HuggingFace-native classifiers as potential replacements.

## Labels

```
interview_scheduled  offer_received  rejected
positive_response    survey_received  neutral
```

## Approach: Standalone Benchmark Script (Approach B)

Two new files; nothing in `imap_sync.py` changes until a winner is chosen.

```
scripts/
  benchmark_classifier.py     — CLI entry point
  classifier_adapters.py      — adapter classes (reusable by imap_sync later)

data/
  email_eval.jsonl            — labeled ground truth (gitignored — contains email content)
  email_eval.jsonl.example    — committed example with fake emails

scripts/classifier_service/
  environment.yml             — new conda env: job-seeker-classifiers
```

## Adapter Pattern

```
ClassifierAdapter (ABC)
  .classify(subject, body) → str   # one of the 6 labels
  .name → str
  .model_id → str
  .load() / .unload()              # explicit lifecycle

ZeroShotAdapter(ClassifierAdapter)
  # uses transformers pipeline("zero-shot-classification")
  # candidate_labels = list of 6 labels
  # works for: DeBERTa, BART-MNLI, BGE-M3-ZeroShot, XLM-RoBERTa

GLiClassAdapter(ClassifierAdapter)
  # uses gliclass library (pip install gliclass)
  # GLiClassModel + ZeroShotClassificationPipeline
  # works for: gliclass-instruct-large-v1.0

RerankerAdapter(ClassifierAdapter)
  # uses FlagEmbedding reranker.compute_score()
  # scores (email_text, label_description) pairs; highest = predicted label
  # works for: bge-reranker-v2-m3
```

## Model Registry

| Short name | Model | Params | Adapter | Default |
|------------|-------|--------|---------|---------|
| `deberta-zeroshot` | MoritzLaurer/DeBERTa-v3-large-zeroshot-v2.0 | 400M | ZeroShot | ✅ |
| `deberta-small` | cross-encoder/nli-deberta-v3-small | 100M | ZeroShot | ✅ |
| `gliclass-large` | knowledgator/gliclass-instruct-large-v1.0 | 400M | GLiClass | ✅ |
| `bart-mnli` | facebook/bart-large-mnli | 400M | ZeroShot | ✅ |
| `bge-m3-zeroshot` | MoritzLaurer/bge-m3-zeroshot-v2.0 | 600M | ZeroShot | ✅ |
| `bge-reranker` | BAAI/bge-reranker-v2-m3 | 600M | Reranker | ❌ (`--include-slow`) |
| `deberta-xlarge` | microsoft/deberta-xlarge-mnli | 750M | ZeroShot | ❌ (`--include-slow`) |
| `mdeberta-mnli` | MoritzLaurer/mDeBERTa-v3-base-mnli-xnli | 300M | ZeroShot | ❌ (`--include-slow`) |
| `xlm-roberta-anli` | vicgalle/xlm-roberta-large-xnli-anli | 600M | ZeroShot | ❌ (`--include-slow`) |

## CLI Modes

### `--compare` (live IMAP, visual table)
Extends the pattern of `test_email_classify.py`. Pulls emails via IMAP, shows a table:
```
Subject                                              | Phrase | llama3 | deberta-zs | deberta-sm | gliclass | bart | bge-m3
```
- Phrase-filter column shows BLOCK/pass (same gate as production)
- `llama3` column = current production baseline
- HF model columns follow

### `--eval` (ground-truth evaluation)
Reads `data/email_eval.jsonl`, runs all models, reports per-label and aggregate metrics:
- Per-label: precision, recall, F1
- Aggregate: macro-F1, accuracy
- Latency: ms/email per model

JSONL format:
```jsonl
{"subject": "Interview invitation", "body": "We'd like to schedule...", "label": "interview_scheduled"}
{"subject": "Your application", "body": "We regret to inform you...", "label": "rejected"}
```

### `--list-models`
Prints the registry with sizes, adapter types, and default/slow flags.

## Conda Environment

New env `job-seeker-classifiers` — isolated from `job-seeker` (no torch there).

Key deps:
- `torch` (CUDA-enabled)
- `transformers`
- `gliclass`
- `FlagEmbedding` (for bge-reranker only)
- `sentence-transformers` (optional, for future embedding-based approaches)

## GPU

Auto-select (`device="cuda"` when available, CPU fallback). No GPU pinning — models
load one at a time so VRAM pressure is sequential, not cumulative.

## Error Handling

- Model load failures: skip that column, print warning, continue
- Classification errors: show `ERR` in cell, continue
- IMAP failures: propagate (same as existing harness)
- Missing eval file: clear error message pointing to `data/email_eval.jsonl.example`

## What Does Not Change (Yet)

- `scripts/imap_sync.py` — production classifier unchanged
- `scripts/llm_router.py` — unchanged
- `staging.db` schema — unchanged

After benchmark results are reviewed, a separate PR will wire the winning model
into `classify_stage_signal()` as an opt-in backend in `llm_router.py`.
