# Digest Email Parsers — Design

**Date:** 2026-03-05
**Products:** Peregrine (primary), Avocet (bucket)
**Status:** Design approved, ready for implementation planning

---

## Problem

Peregrine's `imap_sync.py` can extract leads from digest emails, but only for LinkedIn — the
parser is hardcoded inline with no extension point. Adzuna and The Ladders digest emails are
unhandled. Additionally, any digest email from an unknown sender is silently dropped with no
way to collect samples for building new parsers.

---

## Solution Overview

Two complementary changes:

1. **`peregrine/scripts/digest_parsers.py`** — a standalone parser module with a sender registry
   and dispatcher. `imap_sync.py` calls a single function; the registry handles dispatch.
   LinkedIn parser moves here; Adzuna and Ladders parsers are built against real IMAP samples.

2. **Avocet digest bucket** — when a user labels an email as `digest` in the Avocet label UI,
   the email is appended to `data/digest_samples.jsonl`. This file is the corpus for building
   and testing new parsers for senders not yet in the registry.

---

## Architecture

### Production path (Peregrine)

```
imap_sync._scan_unmatched_leads()
    │
    ├─ parse_digest(from_addr, body)
    │       │
    │       ├─ None  → unknown sender → fall through to LLM extraction (unchanged)
    │       ├─ []    → known sender, nothing found → skip
    │       └─ [...] → jobs found → insert_job() + submit_task("scrape_url")
    │
    └─ continue  (digest email consumed; does not reach LLM path)
```

### Sample collection path (Avocet)

```
Avocet label UI
    │
    └─ label == "digest"
            │
            └─ append to data/digest_samples.jsonl
                    │
                    └─ used as reference for building new parsers
```

---

## Module: `peregrine/scripts/digest_parsers.py`

### Parser interface

Each parser function:

```python
def parse_<source>(body: str) -> list[dict]
```

Returns zero or more job dicts:

```python
{
    "title":    str,   # job title
    "company":  str,   # company name
    "location": str,   # location string (may be empty)
    "url":      str,   # canonical URL, tracking params stripped
    "source":   str,   # "linkedin" | "adzuna" | "theladders"
}
```

### Dispatcher

```python
DIGEST_PARSERS: dict[str, tuple[str, Callable[[str], list[dict]]]] = {
    "jobalerts@linkedin.com":  ("linkedin",   parse_linkedin),
    "noreply@adzuna.com":      ("adzuna",     parse_adzuna),
    "noreply@theladders.com":  ("theladders", parse_theladders),
}

def parse_digest(from_addr: str, body: str) -> list[dict] | None:
    """
    Dispatch to the appropriate parser based on sender address.

    Returns:
        None        — no parser matched (not a known digest sender)
        []          — parser matched, no extractable jobs found
        [dict, ...] — one dict per job card extracted
    """
    addr = from_addr.lower()
    for sender, (source, parse_fn) in DIGEST_PARSERS.items():
        if sender in addr:
            return parse_fn(body)
    return None
```

Sender matching is a substring check, tolerant of display-name wrappers
(`"LinkedIn <jobalerts@linkedin.com>"` matches correctly).

### Parsers

**`parse_linkedin`** — moved verbatim from `imap_sync.parse_linkedin_alert()`, renamed.
No behavior change.

**`parse_adzuna`** — built against real Adzuna digest email bodies pulled from the
configured IMAP account during implementation. Expected format: job blocks separated
by consistent delimiters with title, company, location, and a trackable URL per block.

**`parse_theladders`** — same approach. The Ladders already has a web scraper in
`scripts/custom_boards/theladders.py`; URL canonicalization patterns from there apply here.

---

## Changes to `imap_sync.py`

Replace the LinkedIn-specific block in `_scan_unmatched_leads()` (~lines 561–585):

**Before:**
```python
if _LINKEDIN_ALERT_SENDER in parsed["from_addr"].lower():
    cards = parse_linkedin_alert(parsed["body"])
    for card in cards:
        # ... LinkedIn-specific insert ...
    known_message_ids.add(mid)
    continue
```

**After:**
```python
from scripts.digest_parsers import parse_digest  # top of file

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

`parse_digest` returning `None` falls through to the existing LLM extraction path — all
non-digest recruitment emails are completely unaffected.

---

## Avocet: Digest Bucket

### File

`avocet/data/digest_samples.jsonl` — gitignored. An `.example` entry is committed.

Schema matches the existing label queue (JSONL on-disk schema):

```json
{"subject": "...", "body": "...", "from_addr": "...", "date": "...", "account": "..."}
```

### Trigger

In `app/label_tool.py` and `app/api.py`: when a `digest` label is applied, append the
email to `digest_samples.jsonl` alongside the normal write to `email_score.jsonl`.

No Peregrine dependency — if the file path doesn't exist the `data/` directory is created
automatically. Avocet remains fully standalone.

### Usage

When a new digest sender appears in the wild:
1. Label representative emails as `digest` in Avocet → samples land in `digest_samples.jsonl`
2. Inspect samples, write `parse_<source>(body)` in `digest_parsers.py`
3. Add the sender string to `DIGEST_PARSERS`
4. Add fixture test in `peregrine/tests/test_digest_parsers.py`

---

## Testing

### `peregrine/tests/test_digest_parsers.py`

- Fixture bodies sourced from real IMAP samples (anonymized company names / URLs acceptable)
- Each parser: valid body → expected cards returned
- Each parser: empty / malformed body → `[]`, no exception
- Dispatcher: known sender → correct parser invoked
- Dispatcher: unknown sender → `None`
- URL canonicalization: tracking params stripped, canonical form asserted
- Dedup within digest: same URL appearing twice in one email → one card

### `avocet/tests/test_digest_bucket.py`

- `digest` label → row appended to `digest_samples.jsonl`
- Any other label → `digest_samples.jsonl` not touched
- First write creates `data/` directory if absent

---

## Files Changed / Created

| File | Change |
|------|--------|
| `peregrine/scripts/digest_parsers.py` | **New** — parser module |
| `peregrine/scripts/imap_sync.py` | Replace inline LinkedIn block with `parse_digest()` call |
| `peregrine/tests/test_digest_parsers.py` | **New** — parser unit tests |
| `avocet/app/label_tool.py` | Append to `digest_samples.jsonl` on `digest` label |
| `avocet/app/api.py` | Same — digest bucket write in label endpoint |
| `avocet/tests/test_digest_bucket.py` | **New** — bucket write tests |
| `avocet/data/digest_samples.jsonl.example` | **New** — committed sample for reference |

---

## Out of Scope

- Avocet → Peregrine direct import trigger (deferred; bucket is sufficient for now)
- `background_tasks` integration for digest re-processing (not needed with bucket approach)
- HTML digest parsing (all three senders send plain-text alerts; revisit if needed)
