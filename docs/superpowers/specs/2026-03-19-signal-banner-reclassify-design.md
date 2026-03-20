# Signal Banner Redesign — Expandable Email + Re-classification

**Date:** 2026-03-19
**Status:** Approved — ready for implementation planning

---

## Goal

Improve the stage signal banners added in the interviews improvements feature by:

1. Allowing users to expand a banner to read the full email body before acting
2. Providing inline re-classification chips to correct inaccurate classifier labels
3. Removing the implicit one-click stage advancement risk — `[→ Move]` remains but always routes through MoveToSheet confirmation

---

## Decisions Made

| Decision | Choice |
|---|---|
| Email body loading | Eager — add `body` and `from_addr` to `GET /api/interviews` signal query |
| Neutral/excluded re-classification | Optimistic dismiss (same path as ✕) |
| Re-classification persistence | Update `job_contacts.stage_signal` in place; no separate correction record |
| Avocet training integration | Deferred — reclassify endpoint is the hook; export logic added later |
| Expand state persistence | None — local component state only, resets on page reload |
| `[→ Move]` button rename | No rename — pre-selection hint is still useful; MoveToSheet confirm is the safeguard |

---

## Data Model Changes

### `StageSignal` interface (add two fields)

```typescript
export interface StageSignal {
  id: number
  subject: string
  received_at: string
  stage_signal: 'interview_scheduled' | 'positive_response' | 'offer_received' | 'survey_received' | 'rejected'
  body: string | null        // NEW — email body text
  from_addr: string | null   // NEW — sender address
}
```

### `GET /api/interviews` — signal query additions

Add `body, from_addr` to the SELECT clause of the second query in `list_interviews()`:

```sql
SELECT id, job_id, subject, received_at, stage_signal, body, from_addr
FROM job_contacts
WHERE job_id IN (:job_ids)
  AND suggestion_dismissed = 0
  AND stage_signal NOT IN ('neutral', 'unrelated', 'digest', 'event_rescheduled')
  AND stage_signal IS NOT NULL
ORDER BY received_at DESC
```

The Python grouping dict append also includes the new fields:
```python
signals_by_job[sr["job_id"]].append({
    "id":           sr["id"],
    "subject":      sr["subject"],
    "received_at":  sr["received_at"],
    "stage_signal": sr["stage_signal"],
    "body":         sr["body"],
    "from_addr":    sr["from_addr"],
})
```

---

## New Endpoint

### `POST /api/stage-signals/{id}/reclassify`

```
POST /api/stage-signals/{id}/reclassify
Body: { stage_signal: string }
→ 200 { ok: true }
→ 400 if stage_signal is not a valid label
→ 404 if signal not found
```

Updates `job_contacts.stage_signal` for the given row. Valid labels are the nine classifier labels: `interview_scheduled`, `offer_received`, `rejected`, `positive_response`, `survey_received`, `neutral`, `event_rescheduled`, `unrelated`, `digest`.

Implementation:
```python
VALID_SIGNAL_LABELS = {
    'interview_scheduled', 'offer_received', 'rejected',
    'positive_response', 'survey_received', 'neutral',
    'event_rescheduled', 'unrelated', 'digest',
}

@app.post("/api/stage-signals/{signal_id}/reclassify")
def reclassify_signal(signal_id: int, body: ReclassifyBody):
    if body.stage_signal not in VALID_SIGNAL_LABELS:
        raise HTTPException(400, f"Invalid label: {body.stage_signal}")
    db = _get_db()
    result = db.execute(
        "UPDATE job_contacts SET stage_signal = ? WHERE id = ?",
        (body.stage_signal, signal_id),
    )
    rowcount = result.rowcount
    db.commit()
    db.close()
    if rowcount == 0:
        raise HTTPException(404, "Signal not found")
    return {"ok": True}
```

With Pydantic model:
```python
class ReclassifyBody(BaseModel):
    stage_signal: str
```

---

## Banner UI Redesign

### Layout — collapsed (default)

```
┌──────────────────────────────────────────────────┐
│ [existing card / row content]                     │
│──────────────────────────────────────────────────│  ← colored top border
│ 📧 Interview scheduled  "Interview confirmed…"   │
│                        [▸ Read] [→ Move] [✕]     │
└──────────────────────────────────────────────────┘
```

- Subject line: signal type label + subject snippet (truncated to ~60 chars)
- `[▸ Read]` — expand toggle (text button, no border)
- `[→ Move]` — opens MoveToSheet with `preSelectedStage` based on current signal type (unchanged from previous implementation)
- `[✕]` — dismiss

### Layout — expanded

```
┌──────────────────────────────────────────────────┐
│ [existing card / row content]                     │
│──────────────────────────────────────────────────│
│ 📧 Interview scheduled  "Interview confirmed…"   │
│                        [▾ Hide] [→ Move] [✕]     │
│  From: recruiter@acme.com                         │
│  "Hi, we'd like to schedule an interview          │
│   for Tuesday at 2pm…"                            │
│  Re-classify: [🟡 Interview ✓] [🟢 Offer]        │
│               [✅ Positive] [📋 Survey]           │
│               [✖ Rejected]  [— Neutral]           │
└──────────────────────────────────────────────────┘
```

- `[▾ Hide]` — collapses back to default
- Email body: full text, not truncated, in a `pre-wrap` style block
- `From:` line shown if `from_addr` is non-null
- Re-classify chips: one per actionable type + neutral (see chip spec below)

### Re-classify chips

| Label | Display | Action on click |
|---|---|---|
| `interview_scheduled` | 🟡 Interview | Set as active label |
| `positive_response` | ✅ Positive | Set as active label |
| `offer_received` | 🟢 Offer | Set as active label |
| `survey_received` | 📋 Survey | Set as active label |
| `rejected` | ✖ Rejected | Set as active label |
| `neutral` | — Neutral | Optimistic dismiss (remove from local array) |

The chip matching the current `stage_signal` is highlighted (active state). Clicking a non-neutral chip:
1. Optimistically updates `sig.stage_signal` on the local signal object
2. Banner accent color, action label, and `[→ Move]` preSelectedStage update reactively
3. `POST /api/stage-signals/{id}/reclassify` fires in background

Clicking **Neutral**:
1. Optimistically removes the signal from the local `stage_signals` array (same as dismiss)
2. `POST /api/stage-signals/{id}/dismiss` fires in background (reuses existing dismiss endpoint — no need to store a "neutral" label, since dismissed = no longer shown)

### Reactive re-labeling

When `sig.stage_signal` changes locally (after a chip click), the banner updates immediately:
- Accent color (`amber` / `green` / `red`) from `SIGNAL_META[sig.stage_signal].color`
- Action label in `[→ Move]` pre-selection from `SIGNAL_META[sig.stage_signal].stage`
- Active chip highlight moves to the new label

This works because `sig` is a reactive object from the Pinia store — property mutations trigger re-render.

### Expand state

`sigBodyExpanded: boolean` — local `ref` per banner instance (per `sig.id`). Not persisted.

In `InterviewCard.vue`: one `ref` per card instance (`bodyExpanded = ref(false)`), since each card shows at most one visible signal at a time (the others behind `+N more`).

In `InterviewsView.vue` pre-list: keyed by signal id using a `Map<number, boolean>` ref, since multiple jobs × multiple signals can be expanded simultaneously.

---

## Files

| File | Action |
|---|---|
| `dev-api.py` | Add `body, from_addr` to signal SELECT; add `POST /api/stage-signals/{id}/reclassify` |
| `tests/test_dev_api_interviews.py` | Add tests for reclassify endpoint; verify body/from_addr in interviews response |
| `web/src/stores/interviews.ts` | Add `body: string \| null`, `from_addr: string \| null` to `StageSignal` |
| `web/src/components/InterviewCard.vue` | Expand toggle; body/from display; re-classify chips; reactive local re-label |
| `web/src/views/InterviewsView.vue` | Same for pre-list banner rows (keyed expand map) |

---

## What Stays the Same

- Dismiss endpoint and optimistic removal — unchanged
- `[→ Move]` button routing through MoveToSheet with preSelectedStage — unchanged
- `+N more` / `− less` multi-signal expand — unchanged
- Signal banner placement (InterviewCard kanban + InterviewsView pre-list) — unchanged
- Signal → stage → color mapping (`SIGNAL_META` / `SIGNAL_META_PRE`) — unchanged (but now reactive to re-classification)
- `⚡ N signals` count in Applied section header — unchanged
