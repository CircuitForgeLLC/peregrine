# Apply View — Desktop Split-Pane Design

**Date:** 2026-03-19
**Status:** Approved — ready for implementation planning

---

## Goal

Refactor the Apply view for desktop: replace the centered 760px list → full-page-navigation pattern with a persistent master-detail split pane. The left column holds a compact job list; clicking a job expands the cover letter workspace inline to the right. Mobile layout is unchanged.

---

## Decisions Made

| Decision | Choice | Future option |
|---|---|---|
| Split ratio | 28% list / 72% workspace (fixed) | Resizable drag handle |
| Panel open animation | Expand from list divider edge (~200ms) | — |
| URL routing | Local state only — URL stays at `/apply` | URL-synced selection for deep linking |
| List row density | Option A: title + company + score badge, truncated | C (company+score only), D (wrapped/taller) via future layout selector |

---

## Layout

### Desktop (≥ 1024px)

The split pane activates at 1024px — the same breakpoint where the app nav sidebar collapses (`App.vue` `max-width: 1023px`). This ensures the two-column layout never renders without its sidebar, avoiding an uncomfortably narrow list column.

```
┌──────────────────────────────────────────────────────────────────┐
│  [NAV 220px]  │  List (28%)          │  Workspace (72%)          │
│               │  ─────────────────── │  ──────────────────────── │
│               │  25 jobs             │  Sr. Software Engineer     │
│               │  ▶ Sr. SWE  Acme 87% │  Acme Corp                │
│               │    FS Dev  Globex 72% │                            │
│               │    Backend  Init 58%  │  [Cover letter editor]     │
│               │    ...                │  [Actions: Generate / PDF] │
└──────────────────────────────────────────────────────────────────┘
```

- No job selected → right panel shows a warm empty state: `← Select a job to open the workspace` (desktop-only — the empty state element is conditionally rendered only inside the split layout, not the mobile list)
- The `max-width: 760px` constraint on `.apply-list` is removed for desktop

### Mobile (< 1024px)

No changes. Existing full-width list + `RouterLink` navigation to `/apply/:id`. All existing mobile breakpoint styles are preserved.

---

## Component Architecture

### Current

```
ApplyView.vue          → list only, RouterLink to /apply/:id
ApplyWorkspaceView.vue → full page, reads :id from route params
```

### New

```
ApplyView.vue          → split pane (desktop) OR list (mobile)
  ├─ [left]  Narrow job list (inline in ApplyView — not a separate component)
  └─ [right] ApplyWorkspace.vue (new component, :job-id prop)

ApplyWorkspaceView.vue → thin wrapper: <ApplyWorkspace :job-id="Number(route.params.id)" />
ApplyWorkspace.vue     → extracted workspace content; accepts jobId: number prop
```

**Why extract `ApplyWorkspace.vue`?** The workspace now renders in two contexts: the split pane (inline, `jobId` from local state) and the existing `/apply/:id` route (for mobile + future deep links). Extracting it as a prop-driven component avoids duplication.

**`jobId` prop type:** `number`. The wrapper in `ApplyWorkspaceView.vue` does `Number(route.params.id)` before passing it. `ApplyWorkspace.vue` receives a `number` and never touches `route.params` directly.

**`declare module` augmentation:** The `declare module '@/stores/review'` block in the current `ApplyWorkspaceView.vue` (if present) moves into `ApplyWorkspace.vue`, not the thin wrapper.

---

## Narrow Job List (left panel)

**Row layout — Option A:**

```
┌─────────────────────────────────────┐
│ Sr. Software Engineer          [87%]│  ← title truncated, score right-aligned
│ Acme Corp ✓                         │  ← company truncated; ✓ if has_cover_letter
└─────────────────────────────────────┘
```

- The existing `cl-badge` (`✓ Draft` / `○ No draft`) badge row is **removed** from the narrow list. Cover letter status is indicated by a subtle `✓` suffix on the company line only when `has_cover_letter === true`. No badge for "no draft" — the absence of `✓` is sufficient signal at this density.
- **Score badge color thresholds (unified — replaces old 3-tier system in the apply flow):**
  - Green `score-badge--high`: ≥ 70%
  - Blue `score-badge--mid-high`: 50–69%
  - Amber `score-badge--mid`: 30–49%
  - Red `score-badge--low`: < 30%
  - This 4-tier scheme applies in both the narrow list and the workspace header, replacing the previous `≥80 / ≥60 / else` thresholds. The `.score-badge--mid-high` class is new and needs adding to the shared badge CSS.
- Selected row: `border-left: 3px solid var(--app-primary)` accent + tinted background. Use `var(--app-primary-light)` as the primary fallback; `color-mix(in srgb, var(--app-primary) 8%, var(--color-surface-raised))` as the enhancement for browsers that support it (Chrome 111+, Firefox 113+, Safari 16.2+).
- Hover: same border-left treatment at 40% opacity
- `salary`, `location`, `is_remote` badge: shown in the workspace header only — not in the narrow list
- List scrolls independently within its column

---

## Panel Open Animation

CSS Grid column transition on the `.apply-split` root element:

```css
.apply-split {
  display: grid;
  grid-template-columns: 28% 0fr;
  transition: grid-template-columns 200ms ease-out;
}
.apply-split.has-selection {
  grid-template-columns: 28% 1fr;
}

/* Required: prevent intrinsic min-content from blocking collapse */
.apply-split__panel {
  min-width: 0;
  overflow: clip; /* clip (not hidden) — hidden creates a new stacking context
                     and blocks position:sticky children inside the workspace */
}
```

`min-width: 0` on `.apply-split__panel` is required — without it, the panel's intrinsic content width prevents the `0fr` column from collapsing to zero.

Panel content fades in on top of the expand: `opacity: 0 → 1` with a 100ms delay and 150ms duration, so content doesn't flash half-rendered mid-expand.

**Panel height:** The right panel uses `height: calc(100vh - var(--app-header-height, 4rem))` with `overflow-y: auto` so the workspace scrolls independently within the column. Use a CSS variable rather than a bare literal so height stays correct if the nav height changes.

**`prefers-reduced-motion`:** Skip the grid transition and opacity fade; panel appears and content shows instantly.

---

## Post-Action Behavior (Mark Applied / Reject)

In the current `ApplyWorkspaceView.vue`, both `markApplied()` and `rejectListing()` call `router.push('/apply')` after success — fine for a full-page route.

In the embedded split-pane context, `router.push('/apply')` is a no-op (already there), but `selectedJobId` must also be cleared and the job list refreshed. `ApplyWorkspace.vue` emits a `job-removed` event when either action completes. `ApplyView.vue` handles it:

```
@job-removed="onJobRemoved()"  →  selectedJobId = null + re-fetch job list
```

The thin `ApplyWorkspaceView.vue` wrapper can handle `@job-removed` by calling `router.push('/apply')` as before (same behavior, different mechanism).

---

## Empty State (no job selected)

Shown in the right panel when `selectedJobId === null` on desktop only:

```
        🦅
  Select a job to open
    the workspace
```

Centered vertically, subdued text color. Disappears when a job is selected.

---

## Easter Eggs

### 1. Speed Demon 🦅
- **Trigger:** User clicks 5+ different jobs in under 3 seconds
- **Effect:** A `<canvas>` element, absolutely positioned inside the split-pane container (`.apply-split` has `position: relative`), renders a 🦅 streaking left → right across the panel area (600ms). Followed by a "you're on the hunt" toast (2s, bottom-right).
- **`prefers-reduced-motion`:** Toast only, no canvas

### 2. Perfect Match ✨
- **Trigger:** A job with `match_score ≥ 70` is opened in the workspace
- **Effect:** The score badge in the workspace header plays a golden shimmer (`box-shadow` + `background` keyframe, 800ms, once per open)
- **Threshold constant:** `const PERFECT_MATCH_THRESHOLD = 70` at top of `ApplyWorkspace.vue` — intentionally matches the `score-badge--high` boundary (≥ 70%). If badge thresholds are tuned later, update this constant in sync.
- **Note:** Current scoring rarely exceeds 40% — this easter egg may be dormant until the scoring algorithm is tuned. The constant makes it easy to adjust.

### 3. Cover Letter Marathon 📬
- **Trigger:** 5th cover letter generated in a single session
- **Counter:** Component-level `ref<number>` in `ApplyView.vue` (not Pinia) — resets on page refresh, persists across job selections within the session
- **Effect:** A `📬 N today` streak badge appears in the list panel header with a warm amber glow. Increments with each subsequent generation.
- **Tooltip:** "You're on a roll!" on hover

### 4. Konami Code 🎮
- **Trigger:** ↑↑↓↓←→←→BA anywhere on the Apply view
- **Implementation:** Use the **existing** `useKonamiCode(callback)` + `useHackerMode()` from `web/src/composables/useEasterEgg.ts`. Do **not** create a new `useKonami.ts` composable — one already exists. Do **not** add a new global `keydown` listener (one is already registered in `App.vue`); wire up via the composable's callback pattern instead.

---

## What Stays the Same

- `/apply/:id` route — still exists, still works (used by mobile nav)
- All existing mobile breakpoint styles in `ApplyView.vue`
- The `useApiFetch` data fetching pattern
- The `remote-badge` and `salary` display — moved to workspace header, same markup

---

## Future Options (do not implement now)

- **Resizable split:** drag handle between panels, persisted in `localStorage` as `apply.splitRatio`
- **URL-synced selection:** update route to `/apply/:id` on selection; back button closes panel
- **Layout selector:** density toggle in list header offering Option C (company+score only) and Option D (wrapped/taller cards), persisted in `localStorage` as `apply.listDensity`

---

## Files

| File | Action |
|---|---|
| `web/src/views/ApplyView.vue` | Replace: split-pane layout (desktop), narrow list, easter eggs 1 + 3 + 4 |
| `web/src/components/ApplyWorkspace.vue` | Create: workspace content extracted from `ApplyWorkspaceView.vue`; `jobId: number` prop; emits `job-removed` |
| `web/src/views/ApplyWorkspaceView.vue` | Modify: thin wrapper → `<ApplyWorkspace :job-id="Number(route.params.id)" @job-removed="router.push('/apply')" />` |
| `web/src/assets/theme.css` or `peregrine.css` | Add `.score-badge--mid-high` (blue, 50–69%) to badge CSS |
