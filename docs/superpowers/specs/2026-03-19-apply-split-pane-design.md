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
| Split ratio | 28% list / 72% workspace (fixed) | Resizable drag handle (Option C) |
| Panel open animation | Expand from list divider edge (~200ms) | — |
| URL routing | Local state only — URL stays at `/apply` | URL-synced selection for deep linking |
| List row density | Option A: title + company + score badge, truncated | C (company+score only), D (wrapped/taller) via future layout selector |

---

## Layout

### Desktop (≥ 768px)

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

- App nav sidebar (220px fixed, existing) + split pane fills the remainder
- No job selected → right panel shows a warm empty state: `← Select a job to open the workspace`
- The `max-width: 760px` constraint on `.apply-list` is removed for desktop; it remains (full-width) on mobile

### Mobile (< 768px)

No changes. Existing styles, full-width list, `RouterLink` navigation to `/apply/:id`.

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
  ├─ [left]  NarrowJobList (inline, not a separate component — kept in ApplyView)
  └─ [right] ApplyWorkspace.vue (new component, accepts :jobId prop)

ApplyWorkspaceView.vue → unchanged route wrapper; renders <ApplyWorkspace :job-id="route.params.id" />
```

**Why extract `ApplyWorkspace.vue`?** The workspace is now rendered in two contexts: the split pane (inline) and the existing `/apply/:id` route (for mobile and any future deep-link support). Extracting it as a prop-driven component avoids duplication.

---

## Narrow Job List (left panel)

**Row layout — Option A:**

```
┌─────────────────────────────────────┐
│ Sr. Software Engineer          [87%]│  ← title truncated, score right-aligned
│ Acme Corp                           │  ← company truncated
└─────────────────────────────────────┘
```

- Score badge color-coded: green ≥ 70%, blue 50–69%, yellow 30–49%, red < 30%
- `has_cover_letter` shown as a subtle `✓` prefix on the company line (no separate badge — space is tight)
- Selected row: `border-left: 3px solid var(--app-primary)` accent + tinted background (`color-mix(in srgb, var(--app-primary) 8%, var(--color-surface-raised))`)
- Hover: same border-left treatment at lower opacity
- `salary`, `location`, `is_remote` badge moved to the workspace header — not shown in the narrow list
- List scrolls independently; workspace panel is sticky

---

## Panel Open Animation

CSS Grid column transition — most reliable cross-browser approach for "grow from divider" effect:

```css
.apply-split {
  display: grid;
  grid-template-columns: 28% 0fr;        /* collapsed: panel has 0 width */
  transition: grid-template-columns 200ms ease-out;
}
.apply-split.has-selection {
  grid-template-columns: 28% 1fr;        /* expanded */
}
```

The panel column itself has `overflow: hidden`, so content is clipped during expansion. A `opacity: 0 → 1` fade on the panel content (100ms delay, 150ms duration) layers on top so content doesn't flash half-rendered mid-expand.

`prefers-reduced-motion`: skip the grid transition and opacity fade; panel appears instantly.

---

## Empty State (no job selected)

Shown in the right panel when `selectedJobId === null`:

```
        🦅
  Select a job to open
    the workspace
```

Centered vertically, subdued text color, small bird emoji. Disappears the moment a job is selected (no transition needed — the panel content crossfades in).

---

## Easter Eggs

All four easter eggs are scoped to `ApplyView.vue` / `ApplyWorkspace.vue`:

### 1. Speed Demon 🦅
- **Trigger:** User clicks 5+ different jobs in under 3 seconds
- **Effect:** A `<canvas>`-based 🦅 streaks horizontally across the panel area (left → right, 600ms), followed by a brief "you're on the hunt" toast (2s, bottom-right)
- **`prefers-reduced-motion`:** Toast only, no canvas animation

### 2. Perfect Match ✨
- **Trigger:** A job with `match_score ≥ 70` is opened in the workspace
- **Effect:** The score badge in the workspace header plays a golden shimmer (`box-shadow` + `background` keyframe, 800ms, runs once per job open)
- **Threshold:** Stored as `const PERFECT_MATCH_THRESHOLD = 70` — easy to tune when scoring improves
- **Note:** Current scoring rarely exceeds 40%; this easter egg may be dormant until the scoring algorithm is tuned. That's fine — it's a delight for when it does fire.

### 3. Cover Letter Marathon 📬
- **Trigger:** 5th cover letter generated in a single session (session-scoped counter in the Pinia store or component ref)
- **Effect:** A subtle streak badge appears in the list panel header: `📬 5 today` with a warm amber glow. Increments with each subsequent generation. Disappears on page refresh.
- **Tooltip:** "You're on a roll!" on hover

### 4. Konami Code 🎮
- **Trigger:** ↑↑↓↓←→←→BA (standard Konami sequence), detected anywhere on the Apply view
- **Effect:** Activates hacker mode (`document.documentElement.setAttribute('data-theme', 'hacker')`) — consistent with the cross-product Konami standard
- **Implementation:** `useKonami()` composable (shared if it exists, else add to `composables/`)

---

## What Stays the Same

- `/apply/:id` route — still exists, still works (used by mobile nav and future deep links)
- `ApplyWorkspaceView.vue` — becomes a thin wrapper around `<ApplyWorkspace :job-id="id" />`
- All existing mobile breakpoint styles in `ApplyView.vue`
- The `useApiFetch` data fetching pattern
- The `scoreBadgeClass()` utility

---

## Future Options (do not implement now)

- **Resizable split:** drag handle between panels, persisted in `localStorage` as `apply.splitRatio`
- **URL-synced selection:** update route to `/apply/:id` on selection; back button closes panel
- **Layout selector:** density toggle (icon buttons in list header) offering Option C (company+score only) and Option D (wrapped/taller cards). Persisted in `localStorage` as `apply.listDensity`.

---

## Files

| File | Action |
|---|---|
| `web/src/views/ApplyView.vue` | Replace: split-pane layout, narrow list, easter eggs |
| `web/src/components/ApplyWorkspace.vue` | Create: extracted from `ApplyWorkspaceView.vue`, accepts `jobId` prop |
| `web/src/views/ApplyWorkspaceView.vue` | Modify: thin wrapper — `<ApplyWorkspace :job-id="route.params.id" />` |
| `web/src/composables/useKonami.ts` | Create (if not exists): Konami sequence detector composable |
