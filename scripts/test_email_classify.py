#!/usr/bin/env python
"""
Compare email classifiers across models on a live sample from IMAP.

Usage:
    conda run -n job-seeker python scripts/test_email_classify.py
    conda run -n job-seeker python scripts/test_email_classify.py --limit 30
    conda run -n job-seeker python scripts/test_email_classify.py --dry-run  # phrase filter only, no LLM

Outputs a table: subject | phrase_blocked | phi3 | llama3.1 | vllm
"""
import argparse
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.imap_sync import (
    load_config, connect, _search_folder, _parse_message,
    _has_recruitment_keyword, _has_rejection_or_ats_signal,
    _CLASSIFY_SYSTEM, _CLASSIFY_LABELS,
    _REJECTION_PHRASES, _SPAM_PHRASES, _ATS_CONFIRM_SUBJECTS, _SPAM_SUBJECT_PREFIXES,
)
from scripts.llm_router import LLMRouter

_ROUTER = LLMRouter()

MODELS = {
    "phi3":    ("phi3:mini",     ["ollama_research"]),
    "llama3":  ("llama3.1:8b",  ["ollama_research"]),
    "vllm":    ("__auto__",     ["vllm"]),
}

BROAD_TERMS = ["interview", "opportunity", "offer letter", "job offer", "application", "recruiting"]


def _classify(subject: str, body: str, model_override: str, fallback_order: list) -> str:
    try:
        prompt = f"Subject: {subject}\n\nEmail: {body[:600]}"
        raw = _ROUTER.complete(
            prompt,
            system=_CLASSIFY_SYSTEM,
            model_override=model_override,
            fallback_order=fallback_order,
        )
        text = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).lower().strip()
        for label in _CLASSIFY_LABELS:
            if text.startswith(label) or label in text:
                return label
        return f"? ({text[:30]})"
    except Exception as e:
        return f"ERR: {e!s:.20}"


def _short(s: str, n: int = 55) -> str:
    return s if len(s) <= n else s[:n - 1] + "…"


def _explain_block(subject: str, body: str) -> str:
    """Return the first phrase/rule that triggered a block."""
    subject_lower = subject.lower().strip()
    for p in _SPAM_SUBJECT_PREFIXES:
        if subject_lower.startswith(p):
            return f"subject prefix: {p!r}"
    for p in _ATS_CONFIRM_SUBJECTS:
        if p in subject_lower:
            return f"ATS subject: {p!r}"
    haystack = subject_lower + " " + body[:800].lower()
    for p in _REJECTION_PHRASES + _SPAM_PHRASES:
        if p in haystack:
            return f"phrase: {p!r}"
    return "unknown"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=20, help="Max emails to test")
    parser.add_argument("--days", type=int, default=90)
    parser.add_argument("--dry-run", action="store_true",
                        help="Skip LLM calls — show phrase filter only")
    parser.add_argument("--verbose", action="store_true",
                        help="Show which phrase triggered each BLOCK")
    args = parser.parse_args()

    cfg = load_config()
    since = (datetime.now() - timedelta(days=args.days)).strftime("%d-%b-%Y")

    print(f"Connecting to {cfg.get('host')} …")
    conn = connect(cfg)

    # Collect unique UIDs across broad terms
    all_uids: dict[bytes, None] = {}
    for term in BROAD_TERMS:
        for uid in _search_folder(conn, "INBOX", f'(SUBJECT "{term}")', since):
            all_uids[uid] = None

    sample = list(all_uids.keys())[: args.limit]
    print(f"Fetched {len(all_uids)} matching UIDs, testing {len(sample)}\n")

    # Header
    if args.dry_run:
        print(f"{'Subject':<56}  {'RK':3}  {'Phrase':7}")
        print("-" * 72)
    else:
        print(f"{'Subject':<56}  {'RK':3}  {'Phrase':7}  {'phi3':<20}  {'llama3':<20}  {'vllm':<20}")
        print("-" * 130)

    passed = skipped = 0
    rows = []

    for uid in sample:
        parsed = _parse_message(conn, uid)
        if not parsed:
            continue
        subj = parsed["subject"]
        body = parsed["body"]

        has_rk      = _has_recruitment_keyword(subj)
        phrase_block = _has_rejection_or_ats_signal(subj, body)

        if args.dry_run:
            rk_mark = "✓" if has_rk else "✗"
            pb_mark = "BLOCK" if phrase_block else "pass"
            line = f"{_short(subj):<56}  {rk_mark:3}  {pb_mark:7}"
            if phrase_block and args.verbose:
                reason = _explain_block(subj, body)
                line += f"  [{reason}]"
            print(line)
            continue

        if phrase_block or not has_rk:
            skipped += 1
            rk_mark = "✓" if has_rk else "✗"
            pb_mark = "BLOCK" if phrase_block else "pass"
            print(f"{_short(subj):<56}  {rk_mark:3}  {pb_mark:7}  {'—':<20}  {'—':<20}  {'—':<20}")
            continue

        passed += 1
        results = {}
        for name, (model, fallback) in MODELS.items():
            results[name] = _classify(subj, body, model, fallback)

        pb_mark = "pass"
        print(f"{_short(subj):<56}  {'✓':3}  {pb_mark:7}  "
              f"{results['phi3']:<20}  {results['llama3']:<20}  {results['vllm']:<20}")

    if not args.dry_run:
        print(f"\nPhrase-blocked or no-keyword: {skipped}  |  Reached LLMs: {passed}")

    try:
        conn.logout()
    except Exception:
        pass


if __name__ == "__main__":
    main()
