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
import email as _email_lib
import imaplib
import json
import sys
import time
from datetime import datetime, timedelta
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


def run_scoring(
    adapters: list[ClassifierAdapter],
    score_file: str,
) -> dict[str, Any]:
    """Run all adapters against a labeled JSONL. Returns per-adapter metrics."""
    rows = load_scoring_jsonl(score_file)
    gold = [r["label"] for r in rows]
    results: dict[str, Any] = {}

    for adapter in adapters:
        preds: list[str] = []
        t0 = time.monotonic()
        for row in rows:
            try:
                pred = adapter.classify(row["subject"], row["body"])
            except Exception as exc:  # noqa: BLE001 -- adapter.classify() runs arbitrary
                # HuggingFace model inference (tokenization, forward pass, GPU/CPU
                # tensor ops); different adapters (zero-shot, GLiClass, reranker) can
                # each raise different library-specific exceptions, and this benchmark's
                # whole point is to keep scoring the rest of the dataset rather than
                # abort the run when one model chokes on one row.
                print(f"  [{adapter.name}] ERROR on '{row['subject'][:40]}': {exc}", flush=True)
                pred = "neutral"
            preds.append(pred)
        elapsed_ms = (time.monotonic() - t0) * 1000
        metrics = compute_metrics(preds, gold, LABELS)
        metrics["latency_ms"] = round(elapsed_ms / len(rows), 1)
        results[adapter.name] = metrics
        adapter.unload()

    return results


# ---------------------------------------------------------------------------
# IMAP helpers (stdlib only — no imap_sync dependency)
# ---------------------------------------------------------------------------

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
    except (AttributeError, LookupError):
        # AttributeError: get_payload(decode=True) returns None for a part with no
        # payload; LookupError: charset is an unrecognized/bogus codec name taken
        # from an untrusted email header (errors="replace" already covers bad bytes).
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
    except Exception:  # noqa: BLE001 -- this block spans an IMAP network fetch
        # (`conn.uid("fetch", ...)`, which can raise `imaplib.IMAP4.error`/abort on
        # connection issues), indexing into the IMAP response tuple (IndexError/TypeError
        # if the server returns an unexpected shape), and parsing arbitrary/untrusted
        # email bytes via `email.message_from_bytes` (can raise various email-package
        # errors on malformed messages). One bad UID must be skipped, not abort the
        # whole sample fetch.
        return None


def _fetch_imap_sample(limit: int, days: int) -> list[dict[str, str]]:
    cfg = _load_imap_config()
    conn = _imap_connect(cfg)
    since = (datetime.now() - timedelta(days=days)).strftime("%d-%b-%Y")  # noqa: DTZ005 -- intentionally naive; all stored timestamps in this app use naive local/UTC-by-convention isoformat strings, never compared against tz-aware values (see peregrine#179)
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
    except (imaplib.IMAP4.error, OSError) as exc:
        # Best-effort cleanup: the connection may already be closed/half-broken by the
        # time we get here, and a logout failure shouldn't affect the emails already
        # fetched — but it's worth a warning rather than a silent pass.
        print(f"[benchmark_classifier] IMAP logout failed (non-fatal): {exc}", flush=True)
    return emails


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
            except Exception as exc:  # noqa: BLE001 -- same reasoning as run_scoring
                # above: adapter.classify() runs arbitrary model inference and this
                # visual-comparison table must keep going across all rows/models even
                # if one model errors on one email.
                label = f"ERR:{str(exc)[:8]}"
            line += f"{label:<{col}}"
        print(line, flush=True)

    for adapter in adapters:
        adapter.unload()
    print()


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
