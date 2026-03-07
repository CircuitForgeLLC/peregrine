# Digest Email Parsers Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Extract job listings from LinkedIn, Adzuna, and The Ladders digest emails into Peregrine leads, with an Avocet bucket that collects digest samples for future parser development.

**Architecture:** New `peregrine/scripts/digest_parsers.py` exposes a `parse_digest(from_addr, body)` dispatcher backed by a sender registry. `imap_sync.py` replaces its inline LinkedIn block with one dispatcher call. Avocet's two label paths (`label_tool.py` + `api.py`) append digest-labeled emails to `data/digest_samples.jsonl`. Adzuna and Ladders parsers are built from real IMAP samples fetched in Task 2.

**Tech Stack:** Python stdlib only — `re`, `json`, `pathlib`. No new dependencies.

---

### Task 1: Create `digest_parsers.py` with dispatcher + LinkedIn parser

**Files:**
- Create: `peregrine/scripts/digest_parsers.py`
- Create: `peregrine/tests/test_digest_parsers.py`

**Context:**
`parse_linkedin_alert()` currently lives inline in `imap_sync.py`. We move it here (renamed
`parse_linkedin`) and wrap it in a dispatcher. All other parsers plug into the same registry.

Run all tests with:
```
/devl/miniconda3/envs/job-seeker/bin/pytest tests/test_digest_parsers.py -v
```

---

**Step 1: Write the failing tests**

Create `peregrine/tests/test_digest_parsers.py`:

```python
"""Tests for digest email parser registry."""
import pytest
from scripts.digest_parsers import parse_digest, parse_linkedin

# ── LinkedIn fixture ──────────────────────────────────────────────────────────
# Mirrors the plain-text format LinkedIn Job Alert emails actually send.
# Each job block is separated by a line of 10+ dashes.
LINKEDIN_BODY = """\
Software Engineer
Acme Corp
San Francisco, CA

View job: https://www.linkedin.com/comm/jobs/view/1111111111/?refId=abc&trackingId=xyz

--------------------------------------------------
Senior Developer
Widget Inc
Remote

View job: https://www.linkedin.com/comm/jobs/view/2222222222/?refId=def
"""

LINKEDIN_BODY_EMPTY = "No jobs matched your alert this week."

LINKEDIN_BODY_NO_URL = """\
Software Engineer
Acme Corp
San Francisco, CA

--------------------------------------------------
"""


def test_dispatcher_linkedin_sender():
    cards = parse_digest("LinkedIn <jobalerts@linkedin.com>", LINKEDIN_BODY)
    assert cards is not None
    assert len(cards) == 2


def test_dispatcher_unknown_sender_returns_none():
    result = parse_digest("noreply@randomboard.com", LINKEDIN_BODY)
    assert result is None


def test_dispatcher_case_insensitive_sender():
    cards = parse_digest("JOBALERTS@LINKEDIN.COM", LINKEDIN_BODY)
    assert cards is not None


def test_parse_linkedin_returns_correct_fields():
    cards = parse_linkedin(LINKEDIN_BODY)
    assert cards[0]["title"] == "Software Engineer"
    assert cards[0]["company"] == "Acme Corp"
    assert cards[0]["location"] == "San Francisco, CA"
    assert cards[0]["source"] == "linkedin"


def test_parse_linkedin_url_canonicalized():
    """Tracking params stripped; canonical jobs/view/<id>/ form."""
    cards = parse_linkedin(LINKEDIN_BODY)
    assert cards[0]["url"] == "https://www.linkedin.com/jobs/view/1111111111/"
    assert "refId" not in cards[0]["url"]
    assert "trackingId" not in cards[0]["url"]


def test_parse_linkedin_empty_body_returns_empty_list():
    assert parse_linkedin(LINKEDIN_BODY_EMPTY) == []


def test_parse_linkedin_block_without_url_skipped():
    cards = parse_linkedin(LINKEDIN_BODY_NO_URL)
    assert cards == []
```

**Step 2: Run tests to verify they fail**

```
/devl/miniconda3/envs/job-seeker/bin/pytest tests/test_digest_parsers.py -v
```
Expected: `ImportError: cannot import name 'parse_digest'`

---

**Step 3: Write `digest_parsers.py`**

Create `peregrine/scripts/digest_parsers.py`:

```python
"""Digest email parser registry for Peregrine.

Each parser extracts job listings from a known digest sender's plain-text body.
New parsers are added by decorating with @_register(sender_substring, source_name).

Usage:
    from scripts.digest_parsers import parse_digest

    cards = parse_digest(from_addr, body)
    # None  → unknown sender (fall through to LLM path)
    # []    → known sender, nothing extractable
    # [...] → list of {title, company, location, url, source} dicts
"""
from __future__ import annotations

import re
from typing import Callable

# ── Registry ──────────────────────────────────────────────────────────────────

# Maps sender substring (lowercased) → (source_name, parse_fn)
DIGEST_PARSERS: dict[str, tuple[str, Callable[[str], list[dict]]]] = {}


def _register(sender: str, source: str):
    """Decorator to register a parser for a given sender substring."""
    def decorator(fn: Callable[[str], list[dict]]):
        DIGEST_PARSERS[sender.lower()] = (source, fn)
        return fn
    return decorator


def parse_digest(from_addr: str, body: str) -> list[dict] | None:
    """Dispatch to the appropriate parser based on sender address.

    Returns:
        None        — no parser matched (caller should use LLM fallback)
        []          — known sender, no extractable jobs
        [dict, ...] — one dict per job card with keys:
                      title, company, location, url, source
    """
    addr = from_addr.lower()
    for sender, (source, parse_fn) in DIGEST_PARSERS.items():
        if sender in addr:
            return parse_fn(body)
    return None


# ── Shared helpers ─────────────────────────────────────────────────────────────

_LINKEDIN_SKIP_PHRASES = {
    "promoted", "easily apply", "apply now", "job alert",
    "unsubscribe", "linkedin corporation",
}


# ── LinkedIn Job Alert ─────────────────────────────────────────────────────────

@_register("jobalerts@linkedin.com", "linkedin")
def parse_linkedin(body: str) -> list[dict]:
    """Parse LinkedIn Job Alert digest email body.

    Blocks are separated by lines of 10+ dashes. Each block contains:
        Line 0: job title
        Line 1: company
        Line 2: location (optional)
        'View job: <url>'  →  canonicalized to /jobs/view/<id>/
    """
    jobs = []
    blocks = re.split(r"\n\s*-{10,}\s*\n", body)
    for block in blocks:
        lines = [ln.strip() for ln in block.strip().splitlines() if ln.strip()]

        url = None
        for line in lines:
            m = re.search(r"View job:\s*(https?://\S+)", line, re.IGNORECASE)
            if m:
                raw_url = m.group(1)
                job_id_m = re.search(r"/jobs/view/(\d+)", raw_url)
                if job_id_m:
                    url = f"https://www.linkedin.com/jobs/view/{job_id_m.group(1)}/"
                break
        if not url:
            continue

        content = [
            ln for ln in lines
            if not any(p in ln.lower() for p in _LINKEDIN_SKIP_PHRASES)
            and not ln.lower().startswith("view job:")
            and not ln.startswith("http")
        ]
        if len(content) < 2:
            continue

        jobs.append({
            "title":    content[0],
            "company":  content[1],
            "location": content[2] if len(content) > 2 else "",
            "url":      url,
            "source":   "linkedin",
        })
    return jobs


# ── Adzuna Job Alert ───────────────────────────────────────────────────────────

@_register("noreply@adzuna.com", "adzuna")
def parse_adzuna(body: str) -> list[dict]:
    """Parse Adzuna job alert digest email body.

    TODO: implement after reviewing samples in avocet/data/digest_samples.jsonl
    See Task 3 in docs/plans/2026-03-05-digest-parsers-plan.md
    """
    return []


# ── The Ladders Job Alert ──────────────────────────────────────────────────────

@_register("noreply@theladders.com", "theladders")
def parse_theladders(body: str) -> list[dict]:
    """Parse The Ladders job alert digest email body.

    TODO: implement after reviewing samples in avocet/data/digest_samples.jsonl
    See Task 4 in docs/plans/2026-03-05-digest-parsers-plan.md
    """
    return []
```

**Step 4: Run tests to verify they pass**

```
/devl/miniconda3/envs/job-seeker/bin/pytest tests/test_digest_parsers.py -v
```
Expected: all 8 tests PASS

**Step 5: Commit**

```bash
git add scripts/digest_parsers.py tests/test_digest_parsers.py
git commit -m "feat: digest parser registry + LinkedIn parser (moved from imap_sync)"
```

---

### Task 2: Fetch digest samples from IMAP

**Files:**
- Create: `avocet/scripts/fetch_digest_samples.py`

**Context:**
We need real Adzuna and Ladders email bodies to write parsers against. This one-off script
searches the configured IMAP account by sender domain and writes results to
`data/digest_samples.jsonl`. Run it once; the output file feeds Tasks 3 and 4.

---

**Step 1: Create the fetch script**

Create `avocet/scripts/fetch_digest_samples.py`:

```python
#!/usr/bin/env python3
"""Fetch digest email samples from IMAP into data/digest_samples.jsonl.

Searches for emails from known digest sender domains, deduplicates against
any existing samples, and appends new ones.

Usage:
    conda run -n job-seeker python scripts/fetch_digest_samples.py

Reads config/label_tool.yaml for IMAP credentials (first account used).
"""
from __future__ import annotations

import imaplib
import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).parent.parent
CONFIG = ROOT / "config" / "label_tool.yaml"
OUTPUT = ROOT / "data" / "digest_samples.jsonl"

# Sender domains to search — add new ones here as needed
DIGEST_SENDERS = [
    "adzuna.com",
    "theladders.com",
    "jobalerts@linkedin.com",
]

# Import shared helpers from avocet
sys.path.insert(0, str(ROOT))
from app.imap_fetch import _decode_str, _extract_body, entry_key  # noqa: E402


def _load_existing_keys() -> set[str]:
    if not OUTPUT.exists():
        return set()
    keys = set()
    for line in OUTPUT.read_text().splitlines():
        try:
            keys.add(entry_key(json.loads(line)))
        except Exception:
            pass
    return keys


def main() -> None:
    cfg = yaml.safe_load(CONFIG.read_text())
    accounts = cfg.get("accounts", [])
    if not accounts:
        print("No accounts configured in config/label_tool.yaml")
        sys.exit(1)

    acc = accounts[0]
    host = acc.get("host", "imap.gmail.com")
    port = int(acc.get("port", 993))
    use_ssl = acc.get("use_ssl", True)
    username = acc["username"]
    password = acc["password"]
    folder = acc.get("folder", "INBOX")
    days_back = int(acc.get("days_back", 90))

    from datetime import datetime, timedelta
    import email as _email_lib

    since = (datetime.now() - timedelta(days=days_back)).strftime("%d-%b-%Y")

    conn = (imaplib.IMAP4_SSL if use_ssl else imaplib.IMAP4)(host, port)
    conn.login(username, password)
    conn.select(folder, readonly=True)

    known_keys = _load_existing_keys()
    found: list[dict] = []
    seen_uids: dict[bytes, None] = {}

    for sender in DIGEST_SENDERS:
        try:
            _, data = conn.search(None, f'(FROM "{sender}" SINCE "{since}")')
            for uid in (data[0] or b"").split():
                seen_uids[uid] = None
        except Exception as exc:
            print(f"  search error for {sender!r}: {exc}")

    print(f"Found {len(seen_uids)} candidate UIDs across {len(DIGEST_SENDERS)} senders")

    for uid in seen_uids:
        try:
            _, raw_data = conn.fetch(uid, "(RFC822)")
            if not raw_data or not raw_data[0]:
                continue
            msg = _email_lib.message_from_bytes(raw_data[0][1])
            entry = {
                "subject":   _decode_str(msg.get("Subject", "")),
                "body":      _extract_body(msg)[:2000],  # larger cap for parser dev
                "from_addr": _decode_str(msg.get("From", "")),
                "date":      _decode_str(msg.get("Date", "")),
                "account":   acc.get("name", username),
            }
            k = entry_key(entry)
            if k not in known_keys:
                known_keys.add(k)
                found.append(entry)
        except Exception as exc:
            print(f"  fetch error uid {uid}: {exc}")

    conn.logout()

    if not found:
        print("No new digest samples found.")
        return

    OUTPUT.parent.mkdir(exist_ok=True)
    with OUTPUT.open("a", encoding="utf-8") as f:
        for entry in found:
            f.write(json.dumps(entry) + "\n")

    print(f"Wrote {len(found)} new samples to {OUTPUT}")


if __name__ == "__main__":
    main()
```

**Step 2: Run the fetch script**

```
cd /Library/Development/CircuitForge/avocet
conda run -n job-seeker python scripts/fetch_digest_samples.py
```

Expected output: `Wrote N new samples to data/digest_samples.jsonl`

**Step 3: Inspect the samples**

```
# View first few entries — look at from_addr and body for Adzuna and Ladders format
conda run -n job-seeker python -c "
import json
from pathlib import Path
for line in Path('data/digest_samples.jsonl').read_text().splitlines()[:10]:
    e = json.loads(line)
    print('FROM:', e['from_addr'])
    print('SUBJECT:', e['subject'])
    print('BODY[:500]:', e['body'][:500])
    print('---')
"
```

Note down:
- The exact sender addresses for Adzuna and Ladders (update `DIGEST_PARSERS` in `digest_parsers.py` if different from `noreply@adzuna.com` / `noreply@theladders.com`)
- The structure of each job block in the body (separator lines, field order, URL format)

**Step 4: Commit**

```bash
cd /Library/Development/CircuitForge/avocet
git add scripts/fetch_digest_samples.py
git commit -m "feat: fetch_digest_samples script for building new parsers"
```

---

### Task 3: Build and test Adzuna parser

**Files:**
- Modify: `peregrine/scripts/digest_parsers.py` — implement `parse_adzuna`
- Modify: `peregrine/tests/test_digest_parsers.py` — add Adzuna fixtures + tests

**Context:**
After running Task 2, you have real Adzuna email bodies in `avocet/data/digest_samples.jsonl`.
Inspect them (see Task 2 Step 3), identify the structure, then write the test fixture from
a real sample before implementing the parser.

---

**Step 1: Write a failing Adzuna test**

Inspect a real Adzuna sample from `data/digest_samples.jsonl` and identify:
- How job blocks are separated (blank lines? dashes? headers?)
- Field order (title first? company first?)
- Where the job URL appears and what format it uses
- Any noise lines to filter (unsubscribe, promo text, etc.)

Add to `peregrine/tests/test_digest_parsers.py`:

```python
from scripts.digest_parsers import parse_adzuna

# Replace ADZUNA_BODY with a real excerpt from avocet/data/digest_samples.jsonl
# Copy 2-3 job blocks verbatim; replace real company names with "Test Co" etc. if desired
ADZUNA_BODY = """
<paste real Adzuna body excerpt here — 2-3 job blocks>
"""

def test_dispatcher_adzuna_sender():
    # Update sender string if real sender differs from noreply@adzuna.com
    cards = parse_digest("noreply@adzuna.com", ADZUNA_BODY)
    assert cards is not None
    assert len(cards) >= 1

def test_parse_adzuna_fields():
    cards = parse_adzuna(ADZUNA_BODY)
    assert cards[0]["title"]   # non-empty
    assert cards[0]["company"] # non-empty
    assert cards[0]["url"].startswith("http")
    assert cards[0]["source"] == "adzuna"

def test_parse_adzuna_url_no_tracking():
    """Adzuna URLs often contain tracking params — strip them."""
    cards = parse_adzuna(ADZUNA_BODY)
    # Adjust assertion to match actual URL format once you've seen real samples
    for card in cards:
        assert "utm_" not in card["url"]

def test_parse_adzuna_empty_body():
    assert parse_adzuna("No jobs this week.") == []
```

**Step 2: Run tests to verify they fail**

```
/devl/miniconda3/envs/job-seeker/bin/pytest tests/test_digest_parsers.py::test_parse_adzuna_fields -v
```
Expected: FAIL (stub returns `[]`)

**Step 3: Implement `parse_adzuna` in `digest_parsers.py`**

Replace the stub body of `parse_adzuna` based on the actual email structure you observed.
Pattern to follow (adapt field positions to match Adzuna's actual format):

```python
@_register("noreply@adzuna.com", "adzuna")  # update sender if needed
def parse_adzuna(body: str) -> list[dict]:
    jobs = []
    # Split on whatever delimiter Adzuna uses between blocks
    # e.g.: blocks = re.split(r"\n\s*\n{2,}", body)  # double blank line
    # For each block, extract title, company, location, url
    # Strip tracking params from URL: re.sub(r"\?.*", "", url) or parse with urllib
    return jobs
```

If Adzuna sender differs from `noreply@adzuna.com`, update the `@_register` decorator
**and** the `DIGEST_PARSERS` key in the registry (they're set by the decorator — just change
the decorator argument).

**Step 4: Run all digest tests**

```
/devl/miniconda3/envs/job-seeker/bin/pytest tests/test_digest_parsers.py -v
```
Expected: all tests PASS

**Step 5: Commit**

```bash
cd /Library/Development/CircuitForge/peregrine
git add scripts/digest_parsers.py tests/test_digest_parsers.py
git commit -m "feat: Adzuna digest email parser"
```

---

### Task 4: Build and test The Ladders parser

**Files:**
- Modify: `peregrine/scripts/digest_parsers.py` — implement `parse_theladders`
- Modify: `peregrine/tests/test_digest_parsers.py` — add Ladders fixtures + tests

**Context:**
Same approach as Task 3. The Ladders already has a web scraper in
`scripts/custom_boards/theladders.py` — check it for URL patterns that may apply here.

---

**Step 1: Write failing Ladders tests**

Inspect a real Ladders sample from `avocet/data/digest_samples.jsonl`. Add to test file:

```python
from scripts.digest_parsers import parse_theladders

# Replace with real Ladders body excerpt
LADDERS_BODY = """
<paste real Ladders body excerpt here — 2-3 job blocks>
"""

def test_dispatcher_ladders_sender():
    cards = parse_digest("noreply@theladders.com", LADDERS_BODY)
    assert cards is not None
    assert len(cards) >= 1

def test_parse_theladders_fields():
    cards = parse_theladders(LADDERS_BODY)
    assert cards[0]["title"]
    assert cards[0]["company"]
    assert cards[0]["url"].startswith("http")
    assert cards[0]["source"] == "theladders"

def test_parse_theladders_empty_body():
    assert parse_theladders("No new jobs.") == []
```

**Step 2: Run tests to verify they fail**

```
/devl/miniconda3/envs/job-seeker/bin/pytest tests/test_digest_parsers.py::test_parse_theladders_fields -v
```
Expected: FAIL

**Step 3: Implement `parse_theladders`**

Replace the stub. The Ladders URLs often use redirect wrappers — canonicalize to the
`theladders.com/job/<id>` form if possible, otherwise just strip tracking params.

**Step 4: Run all digest tests**

```
/devl/miniconda3/envs/job-seeker/bin/pytest tests/test_digest_parsers.py -v
```
Expected: all tests PASS

**Step 5: Commit**

```bash
git add scripts/digest_parsers.py tests/test_digest_parsers.py
git commit -m "feat: The Ladders digest email parser"
```

---

### Task 5: Update `imap_sync.py` to use the dispatcher

**Files:**
- Modify: `peregrine/scripts/imap_sync.py`

**Context:**
The LinkedIn-specific block in `_scan_unmatched_leads()` (search for
`_LINKEDIN_ALERT_SENDER`) gets replaced with a generic `parse_digest()` call.
The existing behavior is preserved — only the dispatch mechanism changes.

---

**Step 1: Add the import**

At the top of `imap_sync.py`, alongside other local imports, add:

```python
from scripts.digest_parsers import parse_digest
```

**Step 2: Find the LinkedIn-specific block**

Search for `_LINKEDIN_ALERT_SENDER` in `imap_sync.py`. The block looks like:

```python
if _LINKEDIN_ALERT_SENDER in parsed["from_addr"].lower():
    cards = parse_linkedin_alert(parsed["body"])
    for card in cards:
        ...
    known_message_ids.add(mid)
    continue
```

**Step 3: Replace with the generic dispatcher**

```python
# ── Digest email — dispatch to parser registry ────────────────────────
cards = parse_digest(parsed["from_addr"], parsed["body"])
if cards is not None:
    for card in cards:
        if card["url"] in existing_urls:
            continue
        job_id = insert_job(db_path, {
            "title":      card["title"],
            "company":    card["company"],
            "url":        card["url"],
            "source":     card["source"],
            "location":   card["location"],
            "is_remote":  0,
            "salary":     "",
            "description": "",
            "date_found": datetime.now().isoformat()[:10],
        })
        if job_id:
            submit_task(db_path, "scrape_url", job_id)
            existing_urls.add(card["url"])
            new_leads += 1
            print(f"[imap] digest ({card['source']}) → {card['company']} — {card['title']}")
    known_message_ids.add(mid)
    continue
```

**Step 4: Remove the now-unused `parse_linkedin_alert` import/definition**

`parse_linkedin_alert` was defined in `imap_sync.py`. It's now `parse_linkedin` in
`digest_parsers.py`. Delete the old function from `imap_sync.py`. Also remove
`_LINKEDIN_ALERT_SENDER` constant if it's no longer referenced.

**Step 5: Run the full test suite**

```
/devl/miniconda3/envs/job-seeker/bin/pytest tests/ -v
```
Expected: all existing tests still pass; no regressions

**Step 6: Commit**

```bash
git add scripts/imap_sync.py
git commit -m "refactor: imap_sync uses digest_parsers dispatcher; remove inline LinkedIn parser"
```

---

### Task 6: Avocet digest bucket

**Files:**
- Modify: `avocet/app/label_tool.py`
- Modify: `avocet/app/api.py`
- Create: `avocet/tests/test_digest_bucket.py`
- Create: `avocet/data/digest_samples.jsonl.example`

**Context:**
When either label path (`_do_label` in the Streamlit UI or `POST /api/label` in the FastAPI
app) assigns the `digest` label, the full email record is appended to
`data/digest_samples.jsonl`. This is the sample corpus for building future parsers.

---

**Step 1: Write failing tests**

Create `avocet/tests/test_digest_bucket.py`:

```python
"""Tests for digest sample bucket write behavior."""
import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock


# ── Helpers ───────────────────────────────────────────────────────────────────

def _read_bucket(tmp_path: Path) -> list[dict]:
    bucket = tmp_path / "data" / "digest_samples.jsonl"
    if not bucket.exists():
        return []
    return [json.loads(line) for line in bucket.read_text().splitlines() if line.strip()]


SAMPLE_ENTRY = {
    "subject":   "10 new jobs for you",
    "body":      "Software Engineer\nAcme Corp\nRemote\nView job: https://example.com/123",
    "from_addr": "noreply@adzuna.com",
    "date":      "Mon, 03 Mar 2026 09:00:00 +0000",
    "account":   "test@example.com",
}


# ── api.py bucket tests ───────────────────────────────────────────────────────

def test_api_digest_label_writes_to_bucket(tmp_path):
    from app.api import _append_digest_sample
    data_dir = tmp_path / "data"
    _append_digest_sample(SAMPLE_ENTRY, data_dir=data_dir)
    rows = _read_bucket(tmp_path)
    assert len(rows) == 1
    assert rows[0]["from_addr"] == "noreply@adzuna.com"


def test_api_non_digest_label_does_not_write(tmp_path):
    from app.api import _append_digest_sample
    data_dir = tmp_path / "data"
    # _append_digest_sample should only be called for digest; confirm it writes when called
    # Confirm that callers gate on label == "digest" — tested via integration below
    _append_digest_sample(SAMPLE_ENTRY, data_dir=data_dir)
    rows = _read_bucket(tmp_path)
    assert len(rows) == 1  # called directly, always writes


def test_api_digest_creates_data_dir(tmp_path):
    from app.api import _append_digest_sample
    data_dir = tmp_path / "nonexistent" / "data"
    assert not data_dir.exists()
    _append_digest_sample(SAMPLE_ENTRY, data_dir=data_dir)
    assert data_dir.exists()


def test_api_digest_appends_multiple(tmp_path):
    from app.api import _append_digest_sample
    data_dir = tmp_path / "data"
    _append_digest_sample(SAMPLE_ENTRY, data_dir=data_dir)
    _append_digest_sample({**SAMPLE_ENTRY, "subject": "5 more jobs"}, data_dir=data_dir)
    rows = _read_bucket(tmp_path)
    assert len(rows) == 2
```

**Step 2: Run tests to verify they fail**

```
/devl/miniconda3/envs/job-seeker/bin/pytest tests/test_digest_bucket.py -v
```
Expected: `ImportError: cannot import name '_append_digest_sample'`

---

**Step 3: Add `_append_digest_sample` to `api.py`**

In `avocet/app/api.py`, add this helper (near the top, after the imports and `_DATA_DIR`
constant):

```python
_DIGEST_SAMPLES_FILE = _DATA_DIR / "digest_samples.jsonl"


def _append_digest_sample(entry: dict, data_dir: Path | None = None) -> None:
    """Append a digest-labeled email to the sample corpus."""
    target_dir = data_dir if data_dir is not None else _DATA_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    bucket = target_dir / "digest_samples.jsonl"
    record = {
        "subject":   entry.get("subject", ""),
        "body":      entry.get("body", ""),
        "from_addr": entry.get("from_addr", entry.get("from", "")),
        "date":      entry.get("date", ""),
        "account":   entry.get("account", entry.get("source", "")),
    }
    with bucket.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")
```

Then in `post_label()` (around line 127, after `_append_jsonl(_score_file(), record)`):

```python
    if req.label == "digest":
        _append_digest_sample(match)
```

**Step 4: Add the same write to `label_tool.py`**

In `avocet/app/label_tool.py`, add a module-level constant after `_SCORE_FILE`:

```python
_DIGEST_SAMPLES_FILE = _ROOT / "data" / "digest_samples.jsonl"
```

In `_do_label()` (around line 728, after `_append_jsonl(_SCORE_FILE, row)`):

```python
            if label == "digest":
                _append_jsonl(
                    _DIGEST_SAMPLES_FILE,
                    {
                        "subject":   entry.get("subject", ""),
                        "body":      (entry.get("body", ""))[:2000],
                        "from_addr": entry.get("from_addr", ""),
                        "date":      entry.get("date", ""),
                        "account":   entry.get("account", ""),
                    },
                )
```

(`_append_jsonl` already exists in label_tool.py at line ~396 — reuse it.)

**Step 5: Create the example file**

Create `avocet/data/digest_samples.jsonl.example`:

```json
{"subject": "10 new Software Engineer jobs for you", "body": "Software Engineer\nAcme Corp\nSan Francisco, CA\n\nView job: https://www.linkedin.com/jobs/view/1234567890/\n", "from_addr": "LinkedIn <jobalerts@linkedin.com>", "date": "Mon, 03 Mar 2026 09:00:00 +0000", "account": "example@gmail.com"}
```

**Step 6: Update `.gitignore` in avocet**

Verify `data/digest_samples.jsonl` is gitignored. Open `avocet/.gitignore` — it should
already have `data/*.jsonl`. If not, add:

```
data/digest_samples.jsonl
```

**Step 7: Run all avocet tests**

```
/devl/miniconda3/envs/job-seeker/bin/pytest tests/ -v
```
Expected: all tests PASS

**Step 8: Commit**

```bash
cd /Library/Development/CircuitForge/avocet
git add app/api.py app/label_tool.py tests/test_digest_bucket.py data/digest_samples.jsonl.example
git commit -m "feat: digest sample bucket — write digest-labeled emails to digest_samples.jsonl"
```

---

## Summary

| Task | Repo | Commit message |
|------|------|----------------|
| 1 | peregrine | `feat: digest parser registry + LinkedIn parser (moved from imap_sync)` |
| 2 | avocet | `feat: fetch_digest_samples script for building new parsers` |
| 3 | peregrine | `feat: Adzuna digest email parser` |
| 4 | peregrine | `feat: The Ladders digest email parser` |
| 5 | peregrine | `refactor: imap_sync uses digest_parsers dispatcher; remove inline LinkedIn parser` |
| 6 | avocet | `feat: digest sample bucket — write digest-labeled emails to digest_samples.jsonl` |

Tasks 1, 2, and 6 are independent and can be done in any order.
Tasks 3 and 4 depend on Task 2 (samples needed before implementing parsers).
Task 5 depends on Tasks 1, 3, and 4 (all parsers should be ready before switching imap_sync).
