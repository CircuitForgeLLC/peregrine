# Peregrine Vue 3 SPA Migration

**Branch:** `feature/vue-spa`
**Issue:** #8 — Vue 3 SPA frontend (Paid Tier GA milestone)
**Worktree:** `.worktrees/feature-vue-spa/`
**Reference:** `avocet/docs/vue-port-gotchas.md` (15 battle-tested gotchas)

---

## What We're Replacing

The current Streamlit UI (`app/app.py` + `app/pages/`) is an internal tool built for speed of development. The Vue SPA replaces it with a proper frontend — faster, more accessible, and extensible for the Paid Tier. The FastAPI already exists (partially, from the cloud managed instance work); the Vue SPA will consume it.

### Pages to Port

| Streamlit file | Vue view | Route | Notes |
|---|---|---|---|
| `app/Home.py` | `HomeView.vue` | `/` | Dashboard, discovery trigger, sync status |
| `app/pages/1_Job_Review.py` | `JobReviewView.vue` | `/review` | Batch approve/reject; primary daily-driver view |
| `app/pages/4_Apply.py` | `ApplyView.vue` | `/apply` | Cover letter gen + PDF + mark applied |
| `app/pages/5_Interviews.py` | `InterviewsView.vue` | `/interviews` | Kanban: phone_screen → offer → hired |
| `app/pages/6_Interview_Prep.py` | `InterviewPrepView.vue` | `/prep` | Live reference sheet + practice Q&A |
| `app/pages/7_Survey.py` | `SurveyView.vue` | `/survey` | Culture-fit survey assist + screenshot |
| `app/pages/2_Settings.py` | `SettingsView.vue` | `/settings` | 6 tabs: Profile, Resume, Search, System, Fine-Tune, License |

---

## Avocet Lessons Applied — What We Fixed Before Starting

The avocet SPA was the testbed. These bugs were found and fixed there; Peregrine's scaffold already incorporates all fixes. See `avocet/docs/vue-port-gotchas.md` for the full writeup.

### Applied at scaffold level (baked in — you don't need to think about these)

| # | Gotcha | How it's fixed in this scaffold |
|---|--------|----------------------------------|
| 1 | `id="app"` on App.vue root → nested `#app` elements, broken CSS specificity | `App.vue` root uses `class="app-root"`. `#app` in `index.html` is mount target only. |
| 3 | `overflow-x: hidden` on html → creates scroll container → 15px scrollbar jitter on Linux | `peregrine.css`: `html { overflow-x: clip }` |
| 4 | UnoCSS `presetAttributify` generates CSS for bare attribute names like `h2` | `uno.config.ts`: `presetAttributify({ prefix: 'un-', prefixedOnly: true })` |
| 5 | Theme variable name mismatches cause dark mode to silently fall back to hardcoded colors | `peregrine.css` alias map: `--color-bg → var(--color-surface)`, `--color-text-secondary → var(--color-text-muted)` |
| 7 | SPA cache: browser caches `index.html` indefinitely → old asset hashes → 404 on rebuild | FastAPI must register explicit `GET /` with no-cache headers before `StaticFiles` mount (see FastAPI section below) |
| 9 | `navigator.vibrate()` not supported on desktop/Safari — throws on call | `useHaptics.ts` guards with `'vibrate' in navigator` |
| 10 | Pinia options store = Vue 2 migration path | All stores use setup store form: `defineStore('id', () => { ... })` |
| 12 | `matchMedia`, `vibrate`, `ResizeObserver` absent in jsdom → composable tests throw | `test-setup.ts` stubs all three |
| 13 | `100vh` ignores mobile browser chrome | `App.vue`: `min-height: 100dvh` |

### Must actively avoid when writing new components

| # | Gotcha | Rule |
|---|--------|------|
| 2 | `transition: all` + spring easing → every CSS property bounces → layout explosion | Always enumerate: `transition: background 200ms ease, transform 250ms cubic-bezier(...)` |
| 6 | Keyboard composables called with snapshot arrays → keys don't work after async data loads | Accept `getLabels: () => labels.value` (reactive getter), not `labels: []` (snapshot) |
| 8 | Font reflow at ~780ms shifts layout measurements taken in `onMounted` | Measure layout in `document.fonts.ready` promise or after 1s timeout |
| 11 | `useSwipe` from `@vueuse/core` fires on desktop trackpad pointer events, not just touch | Add `pointer-type === 'touch'` guard if you need touch-only behavior |
| 14 | Rebuild workflow confusion | `cd web && npm run build` → refresh browser. Only restart FastAPI if `app/api.py` changed. |
| 15 | `:global(ancestor) .descendant` in `<style scoped>` → Vue drops the descendant entirely | Never use `:global(X) .Y` in scoped CSS. Use JS gate or CSS custom property token. |

---

## FastAPI Integration

### SPA serving (gotcha #7)

When the Vue SPA is built, FastAPI needs to serve it. Register the explicit `/` route **before** the `StaticFiles` mount, otherwise `index.html` gets cached and old asset hashes cause 404s after rebuild:

```python
from pathlib import Path
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

_DIST = Path(__file__).parent.parent / "web" / "dist"
_NO_CACHE = {
    "Cache-Control": "no-cache, no-store, must-revalidate",
    "Pragma": "no-cache",
}

@app.get("/")
def spa_root():
    return FileResponse(_DIST / "index.html", headers=_NO_CACHE)

# Must come after the explicit route above
app.mount("/", StaticFiles(directory=str(_DIST), html=True), name="spa")
```

Hashed assets (`/assets/index-abc123.js`) can be cached aggressively — their filenames change with content. Only `index.html` needs no-cache.

### API prefix

Vue Router uses HTML5 history mode. All `/api/*` routes must be registered on FastAPI before the `StaticFiles` mount. Vue routes (`/`, `/review`, `/apply`, etc.) are handled client-side; FastAPI's `html=True` on `StaticFiles` serves `index.html` for any unmatched path.

---

## Peregrine-Specific Considerations

### Auth & license gating

The Streamlit UI uses `app/wizard/tiers.py` for tier gating. In the Vue SPA, tier state should be fetched from a `GET /api/license/status` endpoint on mount and stored in a Pinia store. Components check `licenseStore.tier` to gate features.

### Discovery trigger

The "Start Discovery" button on Home triggers `python scripts/discover.py` as a background process. The Vue version should use SSE (same pattern as avocet's finetune SSE) to stream progress back in real-time. The `useApiSSE` composable is already wired for this.

### Job Review — card stack UX

This is the daily-driver view. Consider the avocet ASMR bucket pattern here — approve/reject could transform into buckets on drag pickup. The motion tokens (`--transition-spring`, `--transition-dismiss`) are pre-defined in `peregrine.css`. The `useHaptics` composable is ready.

### Kanban (Interviews view)

The drag-to-column kanban is a strong candidate for `@vueuse/core`'s `useDraggable`. Watch for the `useSwipe` gotcha #11 — use pointer-type guards if drag behavior differs between touch and mouse.

### Settings — 6 tabs

Use a tab component with reactive route query params (`/settings?tab=license`) so direct links work and the page is shareable/bookmarkable.

---

## Build & Dev Workflow

```bash
# From worktree root
cd web
npm install        # first time only
npm run dev        # Vite dev server at :5173 (proxies /api/* to FastAPI at :8502)
npm run build      # output to web/dist/
npm run test       # Vitest unit tests
```

FastAPI serves the built `dist/` on the main port. During dev, configure Vite to proxy `/api` to the running FastAPI:

```ts
// vite.config.ts addition for dev proxy
server: {
  proxy: {
    '/api': 'http://localhost:8502',
  }
}
```

After `npm run build`, just refresh the browser — no FastAPI restart needed unless `app/api.py` changed (gotcha #14).

---

## Implementation Order

Suggested sequence — validate the full stack before porting complex pages:

1. **FastAPI SPA endpoint** — serve `web/dist/` with correct cache headers
2. **App shell** — nav, routing, hacker mode, motion toggle work end-to-end
3. **Home view** — dashboard widgets, discovery trigger with SSE progress
4. **Job Review** — most-used view; gets the most polish
5. **Settings** — license tab is the blocker for tier gating in other views
6. **Apply Workspace** — cover letter gen + PDF export
7. **Interviews kanban** — drag-to-column + calendar sync
8. **Interview Prep** — reference sheet, practice Q&A
9. **Survey Assistant** — screenshot + text paste

---

## Checklist

Copy of the avocet gotchas checklist (all pre-applied at scaffold level are checked):

- [x] App.vue root element: use `.app-root` class, NOT `id="app"`
- [ ] No `transition: all` with spring easings — enumerate properties explicitly
- [ ] No `:global(ancestor) .descendant` in scoped CSS — Vue drops the descendant
- [x] `overflow-x: clip` on html, `overflow-x: hidden` on body
- [x] UnoCSS `presetAttributify`: `prefixedOnly: true`
- [x] Product CSS aliases: `--color-bg`, `--color-text-secondary` mapped in `peregrine.css`
- [ ] Keyboard composables: accept reactive getters, not snapshot arrays
- [x] FastAPI SPA serving pattern documented — apply when wiring FastAPI
- [ ] Font reflow: measure layout after `document.fonts.ready` or 1s timeout
- [x] Haptics: guard `navigator.vibrate` with feature detection
- [x] Pinia: use setup store form (function syntax)
- [x] Tests: mock matchMedia, vibrate, ResizeObserver in test-setup.ts
- [x] `min-height: 100dvh` on full-height layout containers
