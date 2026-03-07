# Feedback Button — Design

**Date:** 2026-03-03
**Status:** Approved
**Product:** Peregrine (`PRNG`)

---

## Overview

A floating feedback button visible on every Peregrine page that lets beta testers file
Forgejo issues directly from the UI. Supports optional attachment of diagnostic data
(logs, recent listings) and screenshots — all with explicit per-item user consent and
PII masking before anything leaves the app.

The backend is intentionally decoupled from Streamlit so it can be wrapped in a
FastAPI route when Peregrine moves to a proper Vue/Nuxt frontend.

---

## Goals

- Zero-friction bug reporting for beta testers
- Privacy-first: nothing is sent without explicit consent + PII preview
- Future-proof: backend callable from Streamlit now, FastAPI/Vue later
- GitHub support as a config option once public mirrors are active

---

## Architecture

### Files

| File | Role |
|---|---|
| `scripts/feedback_api.py` | Pure Python backend — no Streamlit imports |
| `app/feedback.py` | Thin Streamlit UI shell — floating button + dialog |
| `app/components/screenshot_capture.py` | Custom Streamlit component using `html2canvas` |
| `app/app.py` | One-line addition: inject feedback button in sidebar block |
| `.env` / `.env.example` | Add `FORGEJO_API_TOKEN`, `FORGEJO_REPO` |

### Config additions (`.env`)

```
FORGEJO_API_TOKEN=...
FORGEJO_REPO=pyr0ball/peregrine
# GITHUB_TOKEN=          # future — filed when public mirror is active
# GITHUB_REPO=           # future
```

---

## Backend (`scripts/feedback_api.py`)

Pure Python. No Streamlit dependency. All functions return plain dicts or bytes.

### Functions

| Function | Signature | Purpose |
|---|---|---|
| `collect_context` | `(page: str) → dict` | Page name, app version (git describe), tier, LLM backend, OS, timestamp |
| `collect_logs` | `(n: int = 100) → str` | Tail of `.streamlit.log`; `mask_pii()` applied before return |
| `collect_listings` | `(n: int = 5) → list[dict]` | Recent jobs from DB — `title`, `company`, `url` only |
| `mask_pii` | `(text: str) → str` | Regex: emails → `[email redacted]`, phones → `[phone redacted]` |
| `build_issue_body` | `(form, context, attachments) → str` | Assembles final markdown issue body |
| `create_forgejo_issue` | `(title, body, labels) → dict` | POST to Forgejo API; returns `{number, url}` |
| `upload_attachment` | `(issue_number, image_bytes, filename) → str` | POST screenshot to issue assets; returns attachment URL |
| `screenshot_page` | `(port: int) → bytes` | Server-side Playwright fallback screenshot; returns PNG bytes |

### Issue creation — two-step

1. `create_forgejo_issue()` → issue number
2. `upload_attachment(issue_number, ...)` → attachment auto-linked by Forgejo

### Labels

Always applied: `beta-feedback`, `needs-triage`
Type-based: `bug` / `feature-request` / `question`

### Future multi-destination

`feedback_api.py` checks both `FORGEJO_API_TOKEN` and `GITHUB_TOKEN` (when present)
and files to whichever destinations are configured. No structural changes needed when
GitHub support is added.

---

## UI Flow (`app/feedback.py`)

### Floating button

A real Streamlit button inside a keyed container. CSS injected via
`st.markdown(unsafe_allow_html=True)` applies `position: fixed; bottom: 2rem;
right: 2rem; z-index: 9999` to the container. Hidden entirely when `IS_DEMO=true`.

### Dialog — Step 1: Form

- **Type selector:** Bug / Feature Request / Other
- **Title:** short text input
- **Description:** free-text area
- **Reproduction steps:** appears only when Bug is selected (adaptive)

### Dialog — Step 2: Consent + Attachments

```
┌─ Include diagnostic data? ─────────────────────────────┐
│  [toggle]                                               │
│  └─ if on → expandable preview of exactly what's sent  │
│     (logs tailed + masked, listings title/company/url) │
├─ Screenshot ───────────────────────────────────────────┤
│  [📸 Capture current view]  → inline thumbnail preview │
│  [📎 Upload screenshot]     → inline thumbnail preview │
├─ Attribution ──────────────────────────────────────────┤
│  [ ] Include my name & email   (shown from user.yaml)  │
└────────────────────────────────────────────────────────┘
[Submit]
```

### Post-submit

- Success: "Issue filed → [view on Forgejo]" with clickable link
- Error: friendly message + copy-to-clipboard fallback (issue body as text)

---

## Screenshot Component (`app/components/screenshot_capture.py`)

Uses `st.components.v1.html()` with `html2canvas` loaded from CDN (no build step).
On capture, JS renders the visible viewport to a canvas, encodes as base64 PNG, and
returns it to Python via the component value.

Server-side Playwright (`screenshot_page()`) is the fallback when the JS component
can't return data (e.g., cross-origin iframe restrictions). It screenshots
`localhost:<port>` from the server — captures layout/UI state but not user session
state.

Both paths return `bytes`. The UI shows an inline thumbnail so the user can review
before submitting.

---

## Privacy & PII Rules

| Data | Included? | Condition |
|---|---|---|
| App logs | Optional | User toggles on + sees masked preview |
| Job listings | Optional (title/company/url only) | User toggles on |
| Cover letters / notes | Never | — |
| Resume content | Never | — |
| Name + email | Optional | User checks attribution checkbox |
| Screenshots | Optional | User captures or uploads |

`mask_pii()` is applied to all text before it appears in the preview and before
submission. Users see exactly what will be sent.

---

## Future: FastAPI wrapper

When Peregrine moves to Vue/Nuxt:

```python
# server.py (FastAPI)
from scripts.feedback_api import build_issue_body, create_forgejo_issue, upload_attachment

@app.post("/api/feedback")
async def submit_feedback(payload: FeedbackPayload):
    body = build_issue_body(payload.form, payload.context, payload.attachments)
    result = create_forgejo_issue(payload.title, body, payload.labels)
    if payload.screenshot:
        upload_attachment(result["number"], payload.screenshot, "screenshot.png")
    return {"url": result["url"]}
```

The Streamlit layer is replaced by a Vue `<FeedbackButton>` component that POSTs
to this endpoint. Backend unchanged.

---

## Out of Scope

- Rate limiting (beta testers are trusted; add later if abused)
- Issue deduplication
- In-app issue status tracking
- Video / screen recording
