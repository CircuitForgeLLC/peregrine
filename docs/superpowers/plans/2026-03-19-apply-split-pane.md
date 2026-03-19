# Apply View — Desktop Split-Pane Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor the Apply view for desktop into a master-detail split pane (28% job list / 72% workspace) with an expand-from-divider animation, while leaving mobile completely unchanged.

**Architecture:** `ApplyWorkspace.vue` is extracted from `ApplyWorkspaceView.vue` as a prop-driven component, allowing it to render both inline (split pane) and as a standalone route (mobile). `ApplyView.vue` owns the split layout, selection state, and three easter eggs. The fourth easter egg (Perfect Match shimmer) lives inside `ApplyWorkspace.vue` since it needs access to the loaded job's score.

**Tech Stack:** Vue 3 + TypeScript + Pinia-free (local `ref` state) + CSS Grid column transitions + `useEasterEgg.ts` composables (existing)

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `web/src/assets/peregrine.css` | Modify | Add `--score-mid-high` CSS variable; add `.score-badge--mid-high` class |
| `web/src/components/ApplyWorkspace.vue` | **Create** | Extracted workspace: `jobId: number` prop, emits `job-removed` + `cover-letter-generated`, Perfect Match shimmer |
| `web/src/views/ApplyWorkspaceView.vue` | Modify | Slim to thin wrapper: `<ApplyWorkspace :job-id="...">` |
| `web/src/views/ApplyView.vue` | **Replace** | Split-pane layout, narrow list rows, Speed Demon + Marathon + (Konami already global) |

No router changes — `/apply/:id` stays as-is.

---

## Task 1: Score Badge 4-Tier CSS

**Files:**
- Modify: `web/src/assets/peregrine.css`

The current badge CSS has 3 tiers with outdated thresholds (`≥80`, `≥60`). The new spec uses 4 tiers aligned with the existing CSS variable comments: green ≥70%, **blue 50–69%** (new), amber 30–49%, red <30%.

**Why `peregrine.css`?** Score tokens (`--score-high`, `--score-mid`, `--score-low`) are defined there. The new `--score-mid-high` token and the `.score-badge--mid-high` class belong alongside them.

**Note:** `ApplyWorkspaceView.vue` defines `.score-badge--*` classes in its `<style scoped>`. After Task 2 extracts the workspace into `ApplyWorkspace.vue`, those scoped styles move with it. The canonical badge classes already also exist in `ApplyView.vue`'s scoped styles and will be updated there in Task 3.

- [ ] **Step 1: Add `--score-mid-high` token and `.score-badge--mid-high` class**

Open `web/src/assets/peregrine.css`. Find the score token block (around line 55). Add the `--score-mid-high` variable and its dark-mode equivalent. Then find where `.score-badge--*` classes are defined (if they exist globally) or note the pattern for Task 2.

In `:root`:
```css
  --score-high:     var(--color-success);   /* ≥ 70% */
  --score-mid-high: #2b7cb8;               /* 50–69% — Falcon Blue variant */
  --score-mid:      var(--color-warning);   /* 30–49% */
  --score-low:      var(--color-error);     /* < 30% */
  --score-none:     var(--color-text-muted);
```

Also add dark-mode override. The existing dark-mode block in `peregrine.css` uses:
`@media (prefers-color-scheme: dark) { :root:not([data-theme="hacker"]) { ... } }`
Add inside that exact block:
```css
  --score-mid-high: #5ba3d9;  /* lighter blue for dark bg */
```

Also update the existing `--score-mid` comment from `/* 40–69% */` to `/* 30–49% */` to keep the inline documentation accurate.

- [ ] **Step 2: Verify the token exists by checking the file**

```bash
grep -n "score-mid-high\|score-high\|score-mid\|score-low" \
  /Library/Development/CircuitForge/peregrine/.worktrees/feature-vue-spa/web/src/assets/peregrine.css
```

Expected: 4 lines with the new token appearing between `score-high` and `score-mid`.

- [ ] **Step 3: Commit**

```bash
cd /Library/Development/CircuitForge/peregrine/.worktrees/feature-vue-spa
git add web/src/assets/peregrine.css
git commit -m "style(apply): add score-badge--mid-high token for 4-tier scoring"
```

---

## Task 2: Extract `ApplyWorkspace.vue` + Perfect Match Easter Egg

**Files:**
- Create: `web/src/components/ApplyWorkspace.vue`
- Modify: `web/src/views/ApplyWorkspaceView.vue`

This is the largest refactor. The goal is to move all workspace logic out of the route view into a reusable component that accepts a `jobId` prop.

**Dependencies:** Task 2 must complete before Task 3 — `ApplyView.vue` imports `ApplyWorkspace.vue`.

**Key changes vs. `ApplyWorkspaceView.vue`:**
1. `jobId` comes from prop, not `useRoute()` — remove the `useRoute()`, `useRouter()`, and `RouterLink` imports
2. All API calls use `props.jobId` instead of the old module-level `const jobId`. The exact locations: `fetchJob()`, `pollTaskStatus()`, `generate()`, `saveCoverLetter()`, `downloadPdf()`, `markApplied()`, `rejectListing()`, and the in-flight task check inside `onMounted`
3. `markApplied` / `rejectListing`: emit `job-removed` instead of calling `router.push('/apply')`
4. `generate()` polling: emit `cover-letter-generated` when status transitions to `completed`
5. Remove the `← Back to Apply` `RouterLink` (only needed in the standalone route context)
6. **Preserve `onUnmounted`** — `stopPolling()` + `clearTimeout(toastTimer)` cleanup is critical: the component can now unmount mid-session when the user selects a different job
7. `declare module '../stores/review'` augmentation moves here (path `'../stores/review'` is correct from `components/` — resolves to `src/stores/review`)
8. Updated 4-tier `scoreBadgeClass` + `.score-badge--mid-high` class
9. `PERFECT_MATCH_THRESHOLD = 70` const + shimmer on open

- [ ] **Step 1: Create `web/src/components/ApplyWorkspace.vue`**

Create the file with the following structure. Start from `ApplyWorkspaceView.vue` as the source — copy it wholesale, then apply the changes listed below.

**`<script setup lang="ts">` changes:**

```typescript
// Props (replaces route.params.id)
const props = defineProps<{ jobId: number }>()

// Emits
const emit = defineEmits<{
  'job-removed': []
  'cover-letter-generated': []
}>()

// Remove: const route = useRoute()
// Remove: const router = useRouter()
// Remove: RouterLink import
// Remove: const jobId = Number(route.params.id)

// jobId is now: props.jobId — update all references from `jobId` to `props.jobId`

// Perfect Match
const PERFECT_MATCH_THRESHOLD = 70  // intentionally = score-badge--high boundary; update together
const shimmeringBadge = ref(false)

// Updated scoreBadgeClass — 4-tier, replaces old 3-tier
const scoreBadgeClass = computed(() => {
  const s = job.value?.match_score ?? 0
  if (s >= 70) return 'score-badge--high'
  if (s >= 50) return 'score-badge--mid-high'
  if (s >= 30) return 'score-badge--mid'
  return 'score-badge--low'
})

// In markApplied() — replace router.push:
//   showToast('Marked as applied ✓')
//   setTimeout(() => emit('job-removed'), 1200)

// In rejectListing() — replace router.push:
//   showToast('Listing rejected')
//   setTimeout(() => emit('job-removed'), 1000)

// In pollTaskStatus(), when status === 'completed', after clState = 'ready':
//   emit('cover-letter-generated')

// Perfect Match trigger — add inside fetchJob(), after clState and isSaved are set:
//   if ((data.match_score ?? 0) >= PERFECT_MATCH_THRESHOLD) {
//     shimmeringBadge.value = false
//     nextTick(() => { shimmeringBadge.value = true })
//     setTimeout(() => { shimmeringBadge.value = false }, 850)
//   }
```

**`<template>` changes:**
- Remove the `<RouterLink to="/apply" class="workspace__back">← Back to Apply</RouterLink>` element
- Add `:class="{ 'score-badge--shimmer': shimmeringBadge }"` to the score badge `<span>` in `.job-details__badges`

**`<style scoped>` changes:**
- Update `.score-badge--mid` and add `.score-badge--mid-high`:
```css
.score-badge--high     { background: rgba(39,174,96,0.12);   color: var(--score-high);     }
.score-badge--mid-high { background: rgba(43,124,184,0.12);  color: var(--score-mid-high); }
.score-badge--mid      { background: rgba(212,137,26,0.12);  color: var(--score-mid);      }
.score-badge--low      { background: rgba(192,57,43,0.12);   color: var(--score-low);      }

/* Perfect Match shimmer — fires once when a ≥70% job opens */
@keyframes shimmer-badge {
  0%   { box-shadow: 0 0 0 0 rgba(212, 175, 55, 0); background: rgba(39,174,96,0.12); }
  30%  { box-shadow: 0 0 8px 3px rgba(212, 175, 55, 0.6); background: rgba(212, 175, 55, 0.2); }
  100% { box-shadow: 0 0 0 0 rgba(212, 175, 55, 0); background: rgba(39,174,96,0.12); }
}
.score-badge--shimmer { animation: shimmer-badge 850ms ease-out forwards; }
```

- Move the `declare module` augmentation from `ApplyWorkspaceView.vue` to here:
```typescript
declare module '../stores/review' {
  interface Job { cover_letter?: string | null }
}
```

- [ ] **Step 2: Slim down `ApplyWorkspaceView.vue`**

Replace the entire file content with:

```vue
<template>
  <ApplyWorkspace
    :job-id="jobId"
    @job-removed="router.push('/apply')"
  />
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import ApplyWorkspace from '../components/ApplyWorkspace.vue'

const route  = useRoute()
const router = useRouter()
const jobId  = computed(() => Number(route.params.id))
</script>
```

- [ ] **Step 3: Run type-check**

```bash
cd /Library/Development/CircuitForge/peregrine/.worktrees/feature-vue-spa/web
./node_modules/.bin/vue-tsc --noEmit
```

Expected: 0 errors. Fix any type errors before continuing. Common errors to expect: forgotten `props.jobId` rename (search for bare `jobId` in `ApplyWorkspace.vue` and confirm every instance is `props.jobId`); leftover `useRoute`/`useRouter` imports.

- [ ] **Step 4: Smoke-test the standalone route**

Start the dev stack (if not already running):
```bash
cd /Library/Development/CircuitForge/peregrine/.worktrees/feature-vue-spa
conda run -n job-seeker uvicorn dev-api:app --port 8601 --reload &
cd web && npm run dev
```

Navigate directly to `http://localhost:5173/apply/1` (or any valid job ID from the staging DB). Verify:
- The workspace loads the job correctly
- "Mark as Applied" and "Reject Listing" navigate back to `/apply` as before
- No console errors

- [ ] **Step 5: Run tests**

```bash
./node_modules/.bin/vitest run
```

Expected: all existing tests still pass (3/3 in `interviews.test.ts`). The refactor should not touch any store logic.

- [ ] **Step 6: Commit**

```bash
cd /Library/Development/CircuitForge/peregrine/.worktrees/feature-vue-spa
git add web/src/components/ApplyWorkspace.vue web/src/views/ApplyWorkspaceView.vue
git commit -m "feat(apply): extract ApplyWorkspace component with job-removed emit and perfect match easter egg"
```

---

## Task 3: Rebuild `ApplyView.vue` — Split Pane + Easter Eggs

**Files:**
- Replace: `web/src/views/ApplyView.vue`

This replaces the entire file. The new `ApplyView.vue` is the split-pane orchestrator on desktop and the unchanged job list on mobile.

**Key behaviors:**
- Desktop (≥1024px): CSS Grid split, `selectedJobId` local state, `<ApplyWorkspace>` panel
- Mobile (<1024px): full-width list, `RouterLink` to `/apply/:id` (unchanged)
- Speed Demon: track last 5 click timestamps; if 5 clicks in < 3s, fire bird animation + toast
- Marathon: `coverLetterCount` ref incremented on `cover-letter-generated` emit from child; badge appears after 5
- Konami: verify it is already registered globally in `App.vue` (see Step 1 below) — if so, no code needed here

- [ ] **Step 1: Verify Konami is already global**

```bash
grep -n "useKonamiCode" \
  /Library/Development/CircuitForge/peregrine/.worktrees/feature-vue-spa/web/src/App.vue
```

Expected: a line like `useKonamiCode(toggle)` — confirming hacker mode is already wired globally. If that line is absent, add `useKonamiCode` + `useHackerMode` to `ApplyView.vue` per the `useEasterEgg.ts` composable API. (In practice it is there — this step just confirms it.)

- [ ] **Step 2: Write the new `ApplyView.vue`**

```vue
<template>
  <!-- ── Mobile: full-width list ──────────────────────────────────── -->
  <div v-if="isMobile" class="apply-list">
    <header class="apply-list__header">
      <h1 class="apply-list__title">Apply</h1>
      <p class="apply-list__subtitle">Approved jobs ready for applications</p>
    </header>

    <div v-if="loading" class="apply-list__loading" aria-live="polite">
      <span class="spinner" aria-hidden="true" />
      <span>Loading approved jobs…</span>
    </div>

    <div v-else-if="jobs.length === 0" class="apply-list__empty" role="status">
      <span aria-hidden="true" class="empty-icon">📋</span>
      <h2 class="empty-title">No approved jobs yet</h2>
      <p class="empty-desc">Approve listings in Job Review, then come back here to write applications.</p>
      <RouterLink to="/review" class="empty-cta">Go to Job Review →</RouterLink>
    </div>

    <ul v-else class="apply-list__jobs" role="list">
      <li v-for="job in jobs" :key="job.id">
        <RouterLink :to="`/apply/${job.id}`" class="job-row" :aria-label="`Open ${job.title} at ${job.company}`">
          <div class="job-row__main">
            <div class="job-row__badges">
              <span v-if="job.match_score !== null" class="score-badge" :class="scoreBadgeClass(job.match_score)">
                {{ job.match_score }}%
              </span>
              <span v-if="job.is_remote" class="remote-badge">Remote</span>
              <span v-if="job.has_cover_letter" class="cl-badge cl-badge--done">✓ Draft</span>
              <span v-else class="cl-badge cl-badge--pending">○ No draft</span>
            </div>
            <span class="job-row__title">{{ job.title }}</span>
            <span class="job-row__company">
              {{ job.company }}
              <span v-if="job.location" class="job-row__sep" aria-hidden="true"> · </span>
              <span v-if="job.location">{{ job.location }}</span>
            </span>
          </div>
          <div class="job-row__meta">
            <span v-if="job.salary" class="job-row__salary">{{ job.salary }}</span>
            <span class="job-row__arrow" aria-hidden="true">›</span>
          </div>
        </RouterLink>
      </li>
    </ul>
  </div>

  <!-- ── Desktop: split pane ─────────────────────────────────────── -->
  <div v-else class="apply-split" :class="{ 'has-selection': selectedJobId !== null }" ref="splitEl">
    <!-- Left: narrow job list -->
    <div class="apply-split__list">
      <div class="split-list__header">
        <h1 class="split-list__title">Apply</h1>
        <span v-if="coverLetterCount >= 5" class="marathon-badge" title="You're on a roll!">
          📬 {{ coverLetterCount }} today
        </span>
      </div>

      <div v-if="loading" class="split-list__loading" aria-live="polite">
        <span class="spinner" aria-hidden="true" />
      </div>

      <div v-else-if="jobs.length === 0" class="split-list__empty" role="status">
        <span>No approved jobs yet.</span>
        <RouterLink to="/review" class="split-list__cta">Go to Job Review →</RouterLink>
      </div>

      <ul v-else class="split-list__jobs" role="list">
        <li v-for="job in jobs" :key="job.id">
          <button
            class="narrow-row"
            :class="{ 'narrow-row--selected': job.id === selectedJobId }"
            :aria-label="`Open ${job.title} at ${job.company}`"
            :aria-pressed="job.id === selectedJobId"
            @click="selectJob(job.id)"
          >
            <div class="narrow-row__top">
              <span class="narrow-row__title">{{ job.title }}</span>
              <span
                v-if="job.match_score !== null"
                class="score-badge"
                :class="scoreBadgeClass(job.match_score)"
              >{{ job.match_score }}%</span>
            </div>
            <div class="narrow-row__company">
              {{ job.company }}<span v-if="job.has_cover_letter" class="narrow-row__cl-tick"> ✓</span>
            </div>
          </button>
        </li>
      </ul>
    </div>

    <!-- Right: workspace panel -->
    <div class="apply-split__panel" aria-live="polite">
      <!-- Empty state -->
      <div v-if="selectedJobId === null" class="split-panel__empty">
        <span aria-hidden="true" style="font-size: 2rem;">🦅</span>
        <p>Select a job to open the workspace</p>
      </div>

      <!-- Workspace -->
      <ApplyWorkspace
        v-else
        :key="selectedJobId"
        :job-id="selectedJobId"
        @job-removed="onJobRemoved"
        @cover-letter-generated="onCoverLetterGenerated"
      />
    </div>

    <!-- Speed Demon canvas (hidden until triggered) -->
    <canvas ref="birdCanvas" class="bird-canvas" aria-hidden="true" />

    <!-- Toast -->
    <Transition name="toast">
      <div v-if="toast" class="split-toast" role="status" aria-live="polite">{{ toast }}</div>
    </Transition>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { RouterLink } from 'vue-router'
import { useApiFetch } from '../composables/useApi'
import ApplyWorkspace from '../components/ApplyWorkspace.vue'

// ── Responsive ───────────────────────────────────────────────────────────────

const isMobile = ref(window.innerWidth < 1024)

onMounted(() => {
  const mq = window.matchMedia('(max-width: 1023px)')
  mq.addEventListener('change', e => { isMobile.value = e.matches })
})

// ── Job list data ─────────────────────────────────────────────────────────────

interface ApprovedJob {
  id:              number
  title:           string
  company:         string
  location:        string | null
  is_remote:       boolean
  salary:          string | null
  match_score:     number | null
  has_cover_letter: boolean
}

const jobs    = ref<ApprovedJob[]>([])
const loading = ref(true)

async function fetchJobs() {
  loading.value = true
  const { data } = await useApiFetch<ApprovedJob[]>(
    '/api/jobs?status=approved&limit=100&fields=id,title,company,location,is_remote,salary,match_score,has_cover_letter'
  )
  loading.value = false
  if (data) jobs.value = data
}

onMounted(fetchJobs)

// ── Score badge — 4-tier ──────────────────────────────────────────────────────

function scoreBadgeClass(score: number | null): string {
  if (score === null) return ''
  if (score >= 70) return 'score-badge--high'
  if (score >= 50) return 'score-badge--mid-high'
  if (score >= 30) return 'score-badge--mid'
  return 'score-badge--low'
}

// ── Selection ─────────────────────────────────────────────────────────────────

const selectedJobId = ref<number | null>(null)

// Speed Demon: track up to 5 most-recent click timestamps
// Plain let (not ref) — never bound to template, no reactivity needed
let recentClicks: number[] = []

function selectJob(id: number) {
  selectedJobId.value = id

  // Speed Demon tracking
  const now = Date.now()
  recentClicks = [...recentClicks, now].slice(-5)
  if (
    recentClicks.length === 5 &&
    recentClicks[4] - recentClicks[0] < 3000
  ) {
    fireSpeedDemon()
    recentClicks = []
  }
}

// ── Job removed ───────────────────────────────────────────────────────────────

async function onJobRemoved() {
  selectedJobId.value = null
  await fetchJobs()
}

// ── Marathon counter ──────────────────────────────────────────────────────────

const coverLetterCount = ref(0)

function onCoverLetterGenerated() {
  coverLetterCount.value++
}

// ── Toast ─────────────────────────────────────────────────────────────────────

const toast = ref<string | null>(null)
let toastTimer = 0

function showToast(msg: string) {
  clearTimeout(toastTimer)
  toast.value = msg
  toastTimer  = window.setTimeout(() => { toast.value = null }, 2500)
}

// ── Easter egg: Speed Demon 🦅 ────────────────────────────────────────────────

const birdCanvas = ref<HTMLCanvasElement | null>(null)
const splitEl    = ref<HTMLElement | null>(null)

function fireSpeedDemon() {
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
    showToast('🦅 You\'re on the hunt!')
    return
  }

  const canvas = birdCanvas.value
  const parent = splitEl.value
  if (!canvas || !parent) return

  const rect    = parent.getBoundingClientRect()
  canvas.width  = rect.width
  canvas.height = rect.height
  canvas.style.display = 'block'

  const ctx    = canvas.getContext('2d')!
  const FRAMES = 36  // 600ms at 60fps
  const startY = rect.height * 0.35
  let   frame  = 0

  function draw() {
    ctx.clearRect(0, 0, canvas.width, canvas.height)
    const progress = frame / FRAMES
    const x = progress * (canvas.width + 60) - 30
    const y = startY + Math.sin(progress * Math.PI) * -30  // slight arc up then down
    ctx.font      = '2rem serif'
    ctx.globalAlpha = frame < 4 ? frame / 4 : frame > FRAMES - 4 ? (FRAMES - frame) / 4 : 1
    ctx.fillText('🦅', x, y)
    frame++
    if (frame <= FRAMES) {
      requestAnimationFrame(draw)
    } else {
      ctx.clearRect(0, 0, canvas.width, canvas.height)
      canvas.style.display = 'none'
      showToast('🦅 You\'re on the hunt!')
    }
  }

  requestAnimationFrame(draw)
}
</script>

<style scoped>
/* ── Shared: spinner ─────────────────────────────────────────────── */
.spinner {
  display: inline-block;
  width: 1.2rem;
  height: 1.2rem;
  border: 2px solid var(--color-border);
  border-top-color: var(--app-primary);
  border-radius: 50%;
  animation: spin 0.7s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }

/* ── Shared: score badges ────────────────────────────────────────── */
.score-badge {
  display: inline-flex;
  align-items: center;
  padding: 1px var(--space-2);
  border-radius: 999px;
  font-size: var(--text-xs);
  font-weight: 700;
  font-family: var(--font-mono);
  flex-shrink: 0;
}
.score-badge--high     { background: rgba(39,174,96,0.12);   color: var(--score-high);     }
.score-badge--mid-high { background: rgba(43,124,184,0.12);  color: var(--score-mid-high); }
.score-badge--mid      { background: rgba(212,137,26,0.12);  color: var(--score-mid);      }
.score-badge--low      { background: rgba(192,57,43,0.12);   color: var(--score-low);      }

.remote-badge {
  padding: 1px var(--space-2);
  border-radius: 999px;
  font-size: var(--text-xs);
  font-weight: 600;
  background: var(--app-primary-light);
  color: var(--app-primary);
}

/* ── Mobile list (unchanged from original) ───────────────────────── */
.apply-list {
  max-width: 760px;
  margin: 0 auto;
  padding: var(--space-8) var(--space-6);
  display: flex;
  flex-direction: column;
  gap: var(--space-6);
}
.apply-list__header  { display: flex; flex-direction: column; gap: var(--space-1); }
.apply-list__title   { font-family: var(--font-display); font-size: var(--text-2xl); color: var(--app-primary); }
.apply-list__subtitle { font-size: var(--text-sm); color: var(--color-text-muted); }
.apply-list__loading  { display: flex; align-items: center; gap: var(--space-3); padding: var(--space-12); color: var(--color-text-muted); font-size: var(--text-sm); justify-content: center; }
.apply-list__empty    { display: flex; flex-direction: column; align-items: center; gap: var(--space-3); padding: var(--space-16) var(--space-8); text-align: center; }
.empty-icon  { font-size: 3rem; }
.empty-title { font-family: var(--font-display); font-size: var(--text-xl); color: var(--color-text); }
.empty-desc  { font-size: var(--text-sm); color: var(--color-text-muted); max-width: 32ch; }
.empty-cta   { margin-top: var(--space-2); color: var(--app-primary); font-size: var(--text-sm); font-weight: 600; text-decoration: none; }
.empty-cta:hover { opacity: 0.7; }
.apply-list__jobs { list-style: none; display: flex; flex-direction: column; gap: var(--space-2); }
.job-row { display: flex; align-items: center; justify-content: space-between; gap: var(--space-4); padding: var(--space-4) var(--space-5); background: var(--color-surface-raised); border: 1px solid var(--color-border-light); border-radius: var(--radius-lg); text-decoration: none; min-height: 72px; transition: border-color 150ms ease, box-shadow 150ms ease, transform 120ms ease; }
.job-row:hover { border-color: var(--app-primary); box-shadow: var(--shadow-sm); transform: translateY(-1px); }
.job-row__main  { display: flex; flex-direction: column; gap: var(--space-1); flex: 1; min-width: 0; }
.job-row__badges { display: flex; flex-wrap: wrap; gap: var(--space-1); margin-bottom: 2px; }
.job-row__title  { font-size: var(--text-sm); font-weight: 700; color: var(--color-text); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.job-row__company { font-size: var(--text-xs); color: var(--color-text-muted); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.job-row__meta   { display: flex; align-items: center; gap: var(--space-3); flex-shrink: 0; }
.job-row__salary { font-size: var(--text-xs); color: var(--color-success); font-weight: 600; white-space: nowrap; }
.job-row__arrow  { font-size: 1.25rem; color: var(--color-text-muted); line-height: 1; }
.cl-badge { padding: 1px var(--space-2); border-radius: 999px; font-size: var(--text-xs); font-weight: 600; }
.cl-badge--done    { background: rgba(39,174,96,0.10); color: var(--color-success); }
.cl-badge--pending { background: var(--color-surface-alt); color: var(--color-text-muted); }

/* ── Desktop split pane ──────────────────────────────────────────── */
.apply-split {
  position: relative;
  display: grid;
  grid-template-columns: 28% 0fr;
  height: calc(100vh - var(--nav-height, 4rem));
  overflow: hidden;
  transition: grid-template-columns 200ms ease-out;
}

@media (prefers-reduced-motion: reduce) {
  .apply-split { transition: none; }
}

.apply-split.has-selection {
  grid-template-columns: 28% 1fr;
}

/* ── Left: narrow list column ────────────────────────────────────── */
.apply-split__list {
  display: flex;
  flex-direction: column;
  border-right: 1px solid var(--color-border-light);
  overflow: hidden;
}

.split-list__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--space-5) var(--space-4) var(--space-3);
  border-bottom: 1px solid var(--color-border-light);
  flex-shrink: 0;
}

.split-list__title {
  font-family: var(--font-display);
  font-size: var(--text-xl);
  color: var(--app-primary);
}

/* Marathon badge */
.marathon-badge {
  font-size: var(--text-xs);
  font-weight: 700;
  padding: 2px var(--space-2);
  border-radius: 999px;
  background: rgba(224, 104, 32, 0.12);
  color: var(--app-accent);
  border: 1px solid rgba(224, 104, 32, 0.3);
  cursor: default;
}

.split-list__loading {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: var(--space-8);
}

.split-list__empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-8) var(--space-4);
  text-align: center;
  font-size: var(--text-sm);
  color: var(--color-text-muted);
}

.split-list__cta {
  color: var(--app-primary);
  font-size: var(--text-xs);
  font-weight: 600;
  text-decoration: none;
}

.split-list__jobs {
  list-style: none;
  overflow-y: auto;
  flex: 1;
}

/* ── Narrow row ──────────────────────────────────────────────────── */
.narrow-row {
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: var(--space-3) var(--space-4);
  background: none;
  border: none;
  border-left: 3px solid transparent;
  border-bottom: 1px solid var(--color-border-light);
  cursor: pointer;
  text-align: left;
  transition: background 100ms ease, border-left-color 100ms ease;
}

.narrow-row:hover {
  background: var(--app-primary-light);
  border-left-color: rgba(43, 108, 176, 0.3);
}

.narrow-row--selected {
  background: var(--app-primary-light);
  /* color-mix enhancement for supported browsers */
  background: color-mix(in srgb, var(--app-primary) 8%, var(--color-surface-raised));
  border-left-color: var(--app-primary);
}

.narrow-row__top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-2);
  min-width: 0;
}

.narrow-row__title {
  font-size: var(--text-sm);
  font-weight: 700;
  color: var(--color-text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1;
  min-width: 0;
}

.narrow-row__company {
  font-size: var(--text-xs);
  color: var(--color-text-muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.narrow-row__cl-tick {
  color: var(--color-success);
  font-weight: 700;
}

/* ── Right: workspace panel ──────────────────────────────────────── */
.apply-split__panel {
  min-width: 0;
  overflow: clip; /* clip prevents BFC side-effect of hidden; also lets position:sticky work inside */
  overflow-y: auto;
  height: 100%;
  opacity: 0;
  transition: opacity 150ms ease 100ms; /* 100ms delay so content fades in after column expands */
}

.apply-split.has-selection .apply-split__panel {
  opacity: 1;
}

@media (prefers-reduced-motion: reduce) {
  .apply-split__panel { transition: none; opacity: 1; }
}

.split-panel__empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--space-3);
  height: 100%;
  color: var(--color-text-muted);
  font-size: var(--text-sm);
}

/* ── Easter egg: Speed Demon canvas ─────────────────────────────── */
.bird-canvas {
  display: none;
  position: absolute;
  inset: 0;
  pointer-events: none;
  z-index: 50;
}

/* ── Toast ───────────────────────────────────────────────────────── */
.split-toast {
  position: absolute;
  bottom: var(--space-6);
  right: var(--space-6);
  background: var(--color-surface-raised);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  padding: var(--space-3) var(--space-5);
  font-size: var(--text-sm);
  color: var(--color-text);
  box-shadow: var(--shadow-lg);
  z-index: 100;
  white-space: nowrap;
}

.toast-enter-active, .toast-leave-active { transition: opacity 200ms ease, transform 200ms ease; }
.toast-enter-from, .toast-leave-to { opacity: 0; transform: translateY(6px); }

/* ── Mobile overrides ────────────────────────────────────────────── */
@media (max-width: 767px) {
  .apply-list { padding: var(--space-4); gap: var(--space-4); }
  .apply-list__title { font-size: var(--text-xl); }
  .job-row { padding: var(--space-3) var(--space-4); }
}
</style>
```

- [ ] **Step 2: Run type-check**

```bash
cd /Library/Development/CircuitForge/peregrine/.worktrees/feature-vue-spa/web
./node_modules/.bin/vue-tsc --noEmit
```

Expected: 0 errors. Fix any type errors before continuing.

- [ ] **Step 3: Smoke-test in the browser**

Start the dev stack:
```bash
# Terminal 1
cd /Library/Development/CircuitForge/peregrine/.worktrees/feature-vue-spa
conda run -n job-seeker uvicorn dev-api:app --port 8601 --reload &

# Terminal 2
cd web && npm run dev
```

Open http://localhost:5173/apply and verify:
- Desktop (≥1024px): split pane renders, list is narrow on left, right shows empty state with 🦅
- Click a job → panel expands from the divider with animation; workspace loads
- Click another job → panel content switches, selected row highlight updates
- Mark a job as Applied → panel closes, job disappears from list
- Mobile emulation (DevTools → 375px) → single-column list with RouterLink navigation (no split)

- [ ] **Step 4: Test Speed Demon easter egg**

Quickly click 5 different jobs within 3 seconds. Expected: 🦅 streaks across the panel, "You're on the hunt!" toast appears.

With DevTools → Rendering → `prefers-reduced-motion: reduce`: toast only, no canvas animation.

- [ ] **Step 5: Test Marathon easter egg**

Generate cover letters for 5 jobs (or temporarily lower the threshold to 2 for testing, then revert). Expected: `📬 5 today` badge appears in list header. Tooltip on hover: "You're on a roll!".

- [ ] **Step 6: Commit**

```bash
cd /Library/Development/CircuitForge/peregrine/.worktrees/feature-vue-spa
git add web/src/views/ApplyView.vue
git commit -m "feat(apply): desktop split-pane layout with narrow list, expand animation, speed demon + marathon easter eggs"
```

---

## Task 4: Type-Check and Test Suite

**Files:**
- No changes — verification only

- [ ] **Step 1: Run full type-check**

```bash
cd /Library/Development/CircuitForge/peregrine/.worktrees/feature-vue-spa/web
./node_modules/.bin/vue-tsc --noEmit
```

Expected: 0 errors.

- [ ] **Step 2: Run full test suite**

```bash
./node_modules/.bin/vitest run
```

Expected: all tests pass (minimum 3 from `interviews.test.ts`; any other tests that exist).

- [ ] **Step 3: Commit fixes if needed**

If any fixes were required:
```bash
cd /Library/Development/CircuitForge/peregrine/.worktrees/feature-vue-spa
git add -p
git commit -m "fix(apply): type-check and test fixes"
```

---

## Done Criteria

- [ ] `--score-mid-high` CSS token added; `.score-badge--mid-high` class works
- [ ] `scoreBadgeClass()` uses 4-tier thresholds (≥70 / ≥50 / ≥30 / else) in all apply-flow files
- [ ] `ApplyWorkspace.vue` renders the full workspace from a `jobId: number` prop
- [ ] `ApplyWorkspace.vue` emits `job-removed` on mark-applied / reject-listing
- [ ] `ApplyWorkspace.vue` emits `cover-letter-generated` when polling completes
- [ ] Perfect Match shimmer fires once when a ≥70% job opens (`.score-badge--shimmer` keyframe)
- [ ] `ApplyWorkspaceView.vue` is a thin wrapper with `<ApplyWorkspace :job-id="..." @job-removed="...">`
- [ ] Desktop (≥1024px): 28/72 CSS Grid split with `grid-template-columns` transition
- [ ] Panel expand animation uses `overflow: clip` + `min-width: 0` (not `overflow: hidden`)
- [ ] Panel content fades in with 100ms delay after column expands
- [ ] `prefers-reduced-motion`: no grid transition, no canvas animation (toast only for Speed Demon)
- [ ] Narrow list rows: title + score badge (top row), company + ✓ tick (bottom row)
- [ ] Selected row: border-left accent + tinted background (`color-mix` with `--app-primary-light` fallback)
- [ ] Empty panel state shows 🦅 + "Select a job to open the workspace"
- [ ] `@job-removed` clears `selectedJobId` + re-fetches job list
- [ ] Speed Demon: 5 clicks in <3s → canvas bird + toast (reduced-motion: toast only)
- [ ] Marathon: 5+ cover letters in session → `📬 N today` badge in list header
- [ ] Konami: already global in `App.vue` — no additional code needed
- [ ] Mobile (<1024px): unchanged — full-width list with `RouterLink` navigation
- [ ] Type-check: 0 errors; all tests pass
