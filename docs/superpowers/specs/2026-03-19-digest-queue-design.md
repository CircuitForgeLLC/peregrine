# Digest Scrape Queue — Design Spec

**Date:** 2026-03-19
**Status:** Approved — ready for implementation planning

---

## Goal

When a user clicks the 📰 Digest chip on a signal banner, the email is added to a persistent digest queue accessible via a dedicated nav tab. The user browses queued digest emails, selects extracted job links to process, and queues them through the existing discovery pipeline as `status='pending'` jobs in `staging.db`.

---

## Decisions Made

| Decision | Choice |
|---|---|
| Digest tab placement | Separate top-level nav tab "📰 Digest", between Interviews and Apply |
| Storage | New `digest_queue` table in `staging.db`; unique on `job_contact_id` |
| Table creation | In `scripts/db.py` `init_db()` — canonical schema location, not `dev-api.py` |
| Link extraction | On-demand, backend regex against HTML-stripped plain-text body — no background task needed |
| Extraction UX | Show ranked link list; job-likely pre-checked, others unchecked; user ticks and submits |
| After queueing | Entry stays in digest list for reference; `[✕]` removes explicitly |
| Failure handling | Digest chip dismisses signal optimistically regardless of `POST /api/digest-queue` success |
| Duplicate protection | `UNIQUE(job_contact_id)` in table; `POST /api/digest-queue` returns `{ created: false }` on duplicate (no 409) |
| Mobile nav | Digest tab does NOT appear in mobile bottom tab bar (all 5 slots occupied; deferred) |
| URL validation | Non-http/https schemes and blank URLs skipped silently in `queue-jobs`; validation deferred to pipeline |

---

## Data Model

### New table: `digest_queue`

Added to `scripts/db.py` `init_db()`:

```sql
CREATE TABLE IF NOT EXISTS digest_queue (
  id             INTEGER PRIMARY KEY,
  job_contact_id INTEGER NOT NULL REFERENCES job_contacts(id),
  created_at     TEXT DEFAULT (datetime('now')),
  UNIQUE(job_contact_id)
)
```

`init_db()` is called at app startup and by `dev-api.py` startup — adding the `CREATE TABLE IF NOT EXISTS` there is safe and idempotent.

---

## Backend

### New endpoints in `dev-api.py`

#### `GET /api/digest-queue`

Returns all queued entries joined with `job_contacts`. `body` is HTML-stripped via `_strip_html()` before returning (display only — extraction uses a separate raw read, see `extract-links`):

```python
SELECT dq.id, dq.job_contact_id, dq.created_at,
       jc.subject, jc.from_addr, jc.received_at, jc.body
FROM digest_queue dq
JOIN job_contacts jc ON jc.id = dq.job_contact_id
ORDER BY dq.created_at DESC
```

Response: array of `{ id, job_contact_id, created_at, subject, from_addr, received_at, body }`.

---

#### `POST /api/digest-queue`

Body: `{ job_contact_id: int }`

- Verify `job_contact_id` exists in `job_contacts` → 404 if not found
- `INSERT OR IGNORE INTO digest_queue (job_contact_id) VALUES (?)`
- Returns `{ ok: true, created: true }` on insert, `{ ok: true, created: false }` if already present
- Never returns 409 — the `created` field is the duplicate signal

---

#### `POST /api/digest-queue/{id}/extract-links`

Extracts and ranks URLs from the entry's email body. No request body.

**Important:** this endpoint reads the **raw** `body` from `job_contacts` directly and runs `URL_RE` against it **before** any HTML stripping. `_strip_html()` calls `BeautifulSoup.get_text()`, which extracts visible text only — it does not preserve `href` attribute values. A URL that appears only as an `href` target (e.g., `<a href="https://greenhouse.io/acme/1">Click here</a>`) would be lost after stripping. Running the regex on raw HTML captures those URLs correctly because `URL_RE`'s character exclusion class (`[^\s<>"')\]]`) stops at `"`, so it cleanly extracts href values without matching surrounding markup.

```python
# Fetch raw body from DB — do NOT strip before extraction
row = db.execute(
    "SELECT jc.body FROM digest_queue dq JOIN job_contacts jc ON jc.id = dq.job_contact_id WHERE dq.id = ?",
    (digest_id,)
).fetchone()
if not row:
    raise HTTPException(404, "Digest entry not found")
return {"links": extract_links(row["body"] or "")}
```

**Extraction algorithm:**

```python
import re
from urllib.parse import urlparse

JOB_DOMAINS = {
    'greenhouse.io', 'lever.co', 'workday.com', 'linkedin.com',
    'ashbyhq.com', 'smartrecruiters.com', 'icims.com', 'taleo.net',
    'jobvite.com', 'breezy.hr', 'recruitee.com', 'bamboohr.com',
    'myworkdayjobs.com', 'careers.', 'jobs.',
}

FILTER_PATTERNS = re.compile(
    r'(unsubscribe|mailto:|/track/|pixel\.|\.gif|\.png|\.jpg'
    r'|/open\?|/click\?|list-unsubscribe)',
    re.I
)

URL_RE = re.compile(r'https?://[^\s<>"\')\]]+', re.I)

def _score_url(url: str) -> int:
    parsed = urlparse(url)
    hostname = parsed.hostname or ''
    path = parsed.path.lower()
    if FILTER_PATTERNS.search(url):
        return -1  # exclude
    for domain in JOB_DOMAINS:
        if domain in hostname or domain in path:
            return 2  # job-likely
    return 1  # other

def extract_links(body: str) -> list[dict]:
    if not body:
        return []
    seen = set()
    results = []
    for m in URL_RE.finditer(body):
        url = m.group(0).rstrip('.,;)')
        if url in seen:
            continue
        seen.add(url)
        score = _score_url(url)
        if score < 0:
            continue
        # Title hint: last line of text immediately before the URL (up to 60 chars)
        start = max(0, m.start() - 60)
        hint = body[start:m.start()].strip().split('\n')[-1].strip()
        results.append({'url': url, 'score': score, 'hint': hint})
    results.sort(key=lambda x: -x['score'])
    return results
```

Response: `{ links: [{ url, score, hint }] }` — `score=2` means job-likely (pre-check in UI), `score=1` means other (unchecked).

---

#### `POST /api/digest-queue/{id}/queue-jobs`

Body: `{ urls: [string] }`

- 404 if digest entry not found
- 400 if `urls` is empty
- Non-http/https URLs and blank strings are skipped silently (counted as `skipped`)

Calls `insert_job` from `scripts/db.py`. The actual signature is `insert_job(db_path, job)` where `job` is a dict. The `status` field is **not** passed — the schema default of `'pending'` handles it:

```python
from scripts.db import insert_job
from datetime import datetime

queued = 0
skipped = 0
for url in body.urls:
    if not url or not url.startswith(('http://', 'https://')):
        skipped += 1
        continue
    result = insert_job(DB_PATH, {
        'url': url,
        'title': '',
        'company': '',
        'source': 'digest',
        'date_found': datetime.utcnow().isoformat(),
    })
    if result:
        queued += 1
    else:
        skipped += 1  # duplicate URL — insert_job returns None on UNIQUE conflict
return {'ok': True, 'queued': queued, 'skipped': skipped}
```

---

#### `DELETE /api/digest-queue/{id}`

Removes entry from `digest_queue`. Does not affect `job_contacts`.
Returns `{ ok: true }`. 404 if not found.

---

## Frontend Changes

### Chip handler update (`InterviewCard.vue` + `InterviewsView.vue`)

When `newLabel === 'digest'`, the handler fires a **third call** after the existing reclassify + dismiss calls. Note: `sig.id` is `job_contacts.id` — this is the correct value for `job_contact_id` (the `StageSignal.id` field maps directly to the `job_contacts` primary key):

```typescript
// After existing reclassify + dismiss calls:
if (newLabel === 'digest') {
  fetch('/api/digest-queue', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ job_contact_id: sig.id }),  // sig.id === job_contacts.id
  }).catch(() => {})  // best-effort; signal already dismissed optimistically
}
```

Signal is removed from local array optimistically before this call (same as current dismiss behavior).

---

### New store: `web/src/stores/digest.ts`

```typescript
import { defineStore } from 'pinia'
import { ref } from 'vue'

export interface DigestEntry {
  id: number
  job_contact_id: number
  created_at: string
  subject: string
  from_addr: string | null
  received_at: string
  body: string | null
}

export interface DigestLink {
  url: string
  score: number   // 2 = job-likely, 1 = other
  hint: string
}

export const useDigestStore = defineStore('digest', () => {
  const entries = ref<DigestEntry[]>([])

  async function fetchAll() {
    const res = await fetch('/api/digest-queue')
    entries.value = await res.json()
  }

  async function remove(id: number) {
    entries.value = entries.value.filter(e => e.id !== id)
    await fetch(`/api/digest-queue/${id}`, { method: 'DELETE' })
  }

  return { entries, fetchAll, remove }
})
```

---

### New page: `web/src/views/DigestView.vue`

**Layout — collapsed entry (default):**

```
┌─────────────────────────────────────────────┐
│ ▸ TechCrunch Jobs Weekly                    │
│   From: digest@techcrunch.com · Mar 19      │
│                              [Extract] [✕]  │
└─────────────────────────────────────────────┘
```

**Layout — expanded entry (after Extract):**

```
┌─────────────────────────────────────────────┐
│ ▾ LinkedIn Job Digest                       │
│   From: jobs@linkedin.com · Mar 18          │
│                          [Re-extract] [✕]   │
│  ┌──────────────────────────────────────┐   │
│  │ ☑ Senior Engineer — Acme Corp        │   │  ← score=2, pre-checked
│  │   greenhouse.io/acme/jobs/456        │   │
│  │ ☑ Staff Designer — Globex           │   │
│  │   lever.co/globex/staff-designer    │   │
│  │ ─── Other links ──────────────────  │   │
│  │ ☐ acme.com/blog/engineering         │   │  ← score=1, unchecked
│  │ ☐ linkedin.com/company/acme         │   │
│  └──────────────────────────────────────┘   │
│                  [Queue 2 selected →]        │
└─────────────────────────────────────────────┘
```

**After queueing:**

Inline confirmation replaces the link list:
```
✅ 2 jobs queued for review, 1 skipped (already in pipeline)
```

Entry remains in the list. `[✕]` removes it.

**Empty state:**
```
🦅 No digest emails queued.
   When you mark an email as 📰 Digest, it appears here.
```

**Component state (per entry, keyed by `DigestEntry.id`):**

```typescript
const expandedIds  = ref<Record<number, boolean>>({})
const linkResults  = ref<Record<number, DigestLink[]>>({})
const selectedUrls = ref<Record<number, Set<string>>>({})
const queueResult  = ref<Record<number, { queued: number; skipped: number } | null>>({})
const extracting   = ref<Record<number, boolean>>({})
const queuing      = ref<Record<number, boolean>>({})
```

`selectedUrls` uses `Set<string>`. Toggling a URL uses the spread-copy pattern to trigger Vue 3 reactivity — same pattern as `expandedSignalIds` in `InterviewCard.vue`:

```typescript
function toggleUrl(entryId: number, url: string) {
  const prev = selectedUrls.value[entryId] ?? new Set()
  const next = new Set(prev)
  next.has(url) ? next.delete(url) : next.add(url)
  selectedUrls.value = { ...selectedUrls.value, [entryId]: next }
}
```

---

### Router + Nav

Add to `web/src/router/index.ts`:
```typescript
{ path: '/digest', component: () => import('../views/DigestView.vue') }
```

**AppNav.vue changes:**

Add `NewspaperIcon` to the Heroicons import (already imported from `@heroicons/vue/24/outline`), then append to `navLinks` after `Interviews`:

```typescript
import { NewspaperIcon } from '@heroicons/vue/24/outline'

const navLinks = [
  { to: '/',           icon: HomeIcon,                  label: 'Home' },
  { to: '/review',     icon: ClipboardDocumentListIcon, label: 'Job Review' },
  { to: '/apply',      icon: PencilSquareIcon,          label: 'Apply' },
  { to: '/interviews', icon: CalendarDaysIcon,          label: 'Interviews' },
  { to: '/digest',     icon: NewspaperIcon,             label: 'Digest' },  // NEW
  { to: '/prep',       icon: LightBulbIcon,             label: 'Interview Prep' },
  { to: '/survey',     icon: MagnifyingGlassIcon,       label: 'Survey' },
]
```

`navLinks` remains a static array. The badge count is rendered as a separate reactive expression in the template alongside the Digest link — keep `navLinks` as-is and add the digest store separately:

```typescript
// In AppNav.vue <script setup>
import { useDigestStore } from '@/stores/digest'
const digestStore = useDigestStore()
```

In the template, inside the `v-for="link in navLinks"` loop, add a badge overlay for the Digest entry:
```html
<span v-if="link.to === '/digest' && digestStore.entries.length > 0" class="nav-badge">
  {{ digestStore.entries.length }}
</span>
```

The Digest nav item does **not** appear in the mobile bottom tab bar (`mobileLinks` array) — all 5 slots are occupied. Deferred to a future pass.

`DigestView.vue` calls `digestStore.fetchAll()` on `onMounted`.

---

## Required Tests (`tests/test_dev_api_digest.py`)

All tests follow the same isolated DB pattern as `test_dev_api_interviews.py`: use `importlib.reload` + FastAPI `TestClient`, seed fixtures directly into the test DB.

| Test | Setup + assertion |
|---|---|
| `test_digest_queue_add` | Seed a `job_contacts` row; POST `{ job_contact_id }` → 200, `created: true`, row in DB |
| `test_digest_queue_add_duplicate` | Seed + POST twice → second returns `created: false`, no error, only one row in DB |
| `test_digest_queue_add_missing_contact` | POST nonexistent `job_contact_id` → 404 |
| `test_digest_queue_list` | Seed `job_contacts` + `digest_queue`; GET → entries include `subject`, `from_addr`, `body` |
| `test_digest_extract_links` | Seed `job_contacts` with body containing a `greenhouse.io` URL and a tracker URL; seed `digest_queue`; POST to `/extract-links` → greenhouse URL present with `score=2`, tracker URL absent |
| `test_digest_extract_links_filters_trackers` | Same setup; assert unsubscribe and pixel URLs excluded from results |
| `test_digest_queue_jobs` | Seed `digest_queue`; POST `{ urls: ["https://greenhouse.io/acme/1"] }` → `queued: 1, skipped: 0`; row exists in `jobs` with `source='digest'` and `status='pending'` |
| `test_digest_queue_jobs_skips_duplicates` | POST `{ urls: ["https://greenhouse.io/acme/1", "https://greenhouse.io/acme/1"] }` — same URL twice in a single call → `queued: 1, skipped: 1`; one row in DB |
| `test_digest_queue_jobs_skips_invalid_urls` | POST `{ urls: ["", "ftp://bad", "https://good.com/job"] }` → `queued: 1, skipped: 2` |
| `test_digest_queue_jobs_empty_urls` | POST `{ urls: [] }` → 400 |
| `test_digest_delete` | Seed + DELETE → 200; second DELETE → 404 |

---

## Files

| File | Action |
|---|---|
| `scripts/db.py` | Add `digest_queue` table to `init_db()` |
| `dev-api.py` | Add 4 new endpoints; add `extract_links()` + `_score_url()` helpers |
| `web/src/stores/digest.ts` | New Pinia store |
| `web/src/views/DigestView.vue` | New page |
| `web/src/router/index.ts` | Add `/digest` route |
| `web/src/components/AppNav.vue` | Import digest store; add Digest nav item + reactive badge; desktop nav only |
| `web/src/components/InterviewCard.vue` | Third call in digest chip handler |
| `web/src/views/InterviewsView.vue` | Third call in digest chip handler |
| `tests/test_dev_api_digest.py` | New test file — 11 tests |

---

## What Stays the Same

- Existing reclassify + dismiss two-call path for digest chip — unchanged
- `insert_job` in `scripts/db.py` — called as-is, no modification needed
- Job Review UI — queued jobs appear there as `status='pending'` automatically
- Signal banner dismiss behavior — optimistic, unchanged
- `_strip_html()` helper in `dev-api.py` — reused for `GET /api/digest-queue` response body
