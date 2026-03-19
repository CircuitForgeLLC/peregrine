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
import { ref, onMounted, onUnmounted } from 'vue'
import { RouterLink } from 'vue-router'
import { useApiFetch } from '../composables/useApi'
import ApplyWorkspace from '../components/ApplyWorkspace.vue'

// ── Responsive ───────────────────────────────────────────────────────────────

const isMobile = ref(window.innerWidth < 1024)

let _mq: MediaQueryList | null = null
let _mqHandler: ((e: MediaQueryListEvent) => void) | null = null

onMounted(() => {
  _mq = window.matchMedia('(max-width: 1023px)')
  _mqHandler = (e: MediaQueryListEvent) => { isMobile.value = e.matches }
  _mq.addEventListener('change', _mqHandler)
})

onUnmounted(() => {
  if (_mq && _mqHandler) _mq.removeEventListener('change', _mqHandler)
  clearTimeout(toastTimer)
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
  try {
    const { data } = await useApiFetch<ApprovedJob[]>(
      '/api/jobs?status=approved&limit=100&fields=id,title,company,location,is_remote,salary,match_score,has_cover_letter'
    )
    if (data) jobs.value = data
  } finally {
    loading.value = false
  }
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
    const y = startY + Math.sin(progress * Math.PI) * -30
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
.job-row__sep    { color: var(--color-border); }
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
