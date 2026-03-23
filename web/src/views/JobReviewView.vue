<template>
  <div class="review">
    <!-- Header -->
    <header class="review__header">
      <div class="review__title-row">
        <h1 class="review__title">Review Jobs</h1>
        <button class="help-btn" :aria-expanded="showHelp" @click="showHelp = !showHelp">
          <span aria-hidden="true">?</span>
          <span class="sr-only">Keyboard shortcuts</span>
        </button>
      </div>

      <!-- Status filter tabs (segmented control) -->
      <div class="review__tabs" role="tablist" aria-label="Filter by status">
        <button
          v-for="tab in TABS"
          :key="tab.status"
          role="tab"
          class="review__tab"
          :class="{ 'review__tab--active': activeTab === tab.status }"
          :aria-selected="activeTab === tab.status"
          @click="setTab(tab.status)"
        >
          {{ tab.label }}
          <span v-if="tab.status === 'pending' && store.remaining > 0" class="tab-badge">
            {{ store.remaining }}
          </span>
        </button>
      </div>
    </header>

    <!-- ── PENDING: card stack ──────────────────────────────────────────── -->
    <div v-if="activeTab === 'pending'" class="review__body">
      <!-- Loading -->
      <div v-if="store.loading" class="review__loading" aria-live="polite" aria-label="Loading jobs…">
        <span class="spinner" aria-hidden="true" />
        <span>Loading queue…</span>
      </div>

      <!-- Empty state — falcon stoop animation (easter egg 9.3) -->
      <div v-else-if="store.remaining === 0 && !store.loading" class="review__empty" role="status">
        <span class="empty-falcon" aria-hidden="true">🦅</span>
        <h2 class="empty-title">Queue cleared.</h2>
        <p class="empty-desc">Nothing to review right now. Run discovery to find new listings.</p>
      </div>

      <!-- Card stack -->
      <template v-else-if="store.currentJob">
        <!-- Keyboard hint bar -->
        <div class="hint-bar" aria-hidden="true">
          <span class="hint"><kbd>←</kbd><kbd>J</kbd> Reject</span>
          <span class="hint-counter">{{ store.remaining }} remaining</span>
          <span class="hint"><kbd>→</kbd><kbd>L</kbd> Approve</span>
        </div>

        <JobCardStack
          ref="stackRef"
          :job="store.currentJob"
          :remaining="store.remaining"
          @approve="onApprove"
          @reject="onReject"
          @skip="onSkip"
        />

        <!-- Action buttons (non-swipe path) -->
        <div class="review__actions" aria-label="Review actions">
          <button
            class="action-btn action-btn--reject"
            aria-label="Reject this job"
            @click="stackRef?.dismissReject()"
          >
            <span aria-hidden="true">✗</span> Reject
          </button>
          <button
            class="action-btn action-btn--skip"
            aria-label="Skip — come back later"
            @click="stackRef?.dismissSkip()"
          >
            <span aria-hidden="true">→↓</span> Skip
          </button>
          <button
            class="action-btn action-btn--approve"
            aria-label="Approve this job"
            @click="stackRef?.dismissApprove()"
          >
            <span aria-hidden="true">✓</span> Approve
          </button>
        </div>

        <!-- Undo hint -->
        <p class="review__undo-hint" aria-hidden="true">Press <kbd>Z</kbd> to undo</p>
      </template>
    </div>

    <!-- ── OTHER STATUS: list view ──────────────────────────────────────── -->
    <div v-else class="review__body">
      <div v-if="store.loading" class="review__loading" aria-live="polite">
        <span class="spinner" aria-hidden="true" />
        <span>Loading…</span>
      </div>
      <div v-else-if="store.listJobs.length === 0" class="review__empty" role="status">
        <p class="empty-desc">No {{ activeTab }} jobs.</p>
      </div>
      <ul v-else class="job-list" role="list">
        <li v-for="job in store.listJobs" :key="job.id" class="job-list__item">
          <div class="job-list__info">
            <span class="job-list__title">{{ job.title }}</span>
            <span class="job-list__company">{{ job.company }}</span>
          </div>
          <div class="job-list__meta">
            <span v-if="job.match_score !== null" class="score-pill" :class="scorePillClass(job.match_score)">
              {{ job.match_score }}%
            </span>
            <a :href="job.url" target="_blank" rel="noopener noreferrer" class="job-list__link">
              View ↗
            </a>
          </div>
        </li>
      </ul>
    </div>

    <!-- ── Help overlay ─────────────────────────────────────────────────── -->
    <Transition name="overlay">
      <div
        v-if="showHelp"
        class="help-overlay"
        role="dialog"
        aria-modal="true"
        aria-labelledby="help-title"
        @click.self="showHelp = false"
      >
        <div class="help-modal">
          <h2 id="help-title" class="help-modal__title">Keyboard Shortcuts</h2>
          <dl class="help-keys">
            <div class="help-keys__row">
              <dt><kbd>→</kbd> / <kbd>L</kbd></dt>
              <dd>Approve</dd>
            </div>
            <div class="help-keys__row">
              <dt><kbd>←</kbd> / <kbd>J</kbd></dt>
              <dd>Reject</dd>
            </div>
            <div class="help-keys__row">
              <dt><kbd>S</kbd></dt>
              <dd>Skip (come back later)</dd>
            </div>
            <div class="help-keys__row">
              <dt><kbd>Enter</kbd></dt>
              <dd>Expand / collapse description</dd>
            </div>
            <div class="help-keys__row">
              <dt><kbd>Z</kbd></dt>
              <dd>Undo last action</dd>
            </div>
            <div class="help-keys__row">
              <dt><kbd>?</kbd></dt>
              <dd>Toggle this help</dd>
            </div>
          </dl>
          <button class="help-modal__close" @click="showHelp = false" aria-label="Close help">✕</button>
        </div>
      </div>
    </Transition>

    <!-- ── Undo toast ────────────────────────────────────────────────────── -->
    <Transition name="toast">
      <div
        v-if="undoToast"
        class="undo-toast"
        role="status"
        aria-live="polite"
      >
        <span>{{ undoToast.message }}</span>
        <button class="undo-toast__btn" @click="doUndo">Undo</button>
      </div>
    </Transition>

    <!-- ── Stoop speed toast — easter egg 9.2 ───────────────────────────── -->
    <Transition name="toast">
      <div v-if="stoopToastVisible" class="stoop-toast" role="status" aria-live="polite">
        🦅 Stoop speed.
      </div>
    </Transition>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { useRoute } from 'vue-router'
import { useReviewStore } from '../stores/review'
import JobCardStack from '../components/JobCardStack.vue'

const store    = useReviewStore()
const route    = useRoute()
const stackRef = ref<InstanceType<typeof JobCardStack> | null>(null)

// ─── Tabs ──────────────────────────────────────────────────────────────────────

const TABS = [
  { status: 'pending',  label: 'Pending'  },
  { status: 'approved', label: 'Approved' },
  { status: 'rejected', label: 'Rejected' },
  { status: 'applied',  label: 'Applied'  },
  { status: 'synced',   label: 'Synced'   },
]

const activeTab = ref((route.query.status as string) ?? 'pending')

async function setTab(status: string) {
  activeTab.value = status
  if (status === 'pending') {
    await store.fetchQueue()
  } else {
    await store.fetchList(status)
  }
}

// ─── Undo toast ────────────────────────────────────────────────────────────────

const undoToast  = ref<{ message: string } | null>(null)
let   toastTimer = 0

function showUndoToast(action: 'approved' | 'rejected' | 'skipped') {
  clearTimeout(toastTimer)
  undoToast.value = { message: `${capitalize(action)}` }
  toastTimer = window.setTimeout(() => { undoToast.value = null }, 5000)
}

async function doUndo() {
  clearTimeout(toastTimer)
  undoToast.value = null
  await store.undo()
}

function capitalize(s: string) { return s.charAt(0).toUpperCase() + s.slice(1) }

// ─── Action handlers ───────────────────────────────────────────────────────────

async function onApprove() {
  const job = store.currentJob
  if (!job) return
  await store.approve(job)
  showUndoToast('approved')
  checkStoopSpeed()
}

async function onReject() {
  const job = store.currentJob
  if (!job) return
  await store.reject(job)
  showUndoToast('rejected')
  checkStoopSpeed()
}

function onSkip() {
  const job = store.currentJob
  if (!job) return
  store.skip(job)
  showUndoToast('skipped')
}

// ─── Stoop speed — easter egg 9.2 ─────────────────────────────────────────────

const stoopToastVisible = ref(false)

function checkStoopSpeed() {
  if (!store.stoopAchieved && store.isStoopSpeed) {
    store.markStoopAchieved()
    stoopToastVisible.value = true
    setTimeout(() => { stoopToastVisible.value = false }, 3500)
  }
}

// ─── Keyboard shortcuts ────────────────────────────────────────────────────────

const showHelp = ref(false)

function onKeyDown(e: KeyboardEvent) {
  // Don't steal keys when typing in an input
  if ((e.target as Element).closest('input, textarea, select, [contenteditable]')) return
  if (activeTab.value !== 'pending') return

  switch (e.key) {
    case 'ArrowRight':
    case 'l':
    case 'L':
      e.preventDefault()
      stackRef.value?.dismissApprove()
      break
    case 'ArrowLeft':
    case 'j':
    case 'J':
      e.preventDefault()
      stackRef.value?.dismissReject()
      break
    case 's':
    case 'S':
      e.preventDefault()
      stackRef.value?.dismissSkip()
      break
    case 'z':
    case 'Z':
      e.preventDefault()
      doUndo()
      break
    case 'Enter':
      // Expand/collapse — bubble to the card's button naturally; no action needed here
      break
    case '?':
      showHelp.value = !showHelp.value
      break
    case 'Escape':
      showHelp.value = false
      break
  }
}

// ─── List view score pill ─────────────────────────────────────────────────────

function scorePillClass(score: number) {
  if (score >= 80) return 'score-pill--high'
  if (score >= 60) return 'score-pill--mid'
  return 'score-pill--low'
}

// ─── Lifecycle ────────────────────────────────────────────────────────────────

onMounted(async () => {
  document.addEventListener('keydown', onKeyDown)
  await store.fetchQueue()
})

onUnmounted(() => {
  document.removeEventListener('keydown', onKeyDown)
  clearTimeout(toastTimer)
})
</script>

<style scoped>
.review {
  max-width: 680px;
  margin: 0 auto;
  padding: var(--space-8) var(--space-6);
  display: flex;
  flex-direction: column;
  gap: var(--space-6);
  min-height: 100dvh;
}

/* ── Header ─────────────────────────────────────────────────────────── */

.review__header {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.review__title-row {
  display: flex;
  align-items: center;
  gap: var(--space-3);
}

.review__title {
  font-family: var(--font-display);
  font-size: var(--text-2xl);
  color: var(--app-primary);
  flex: 1;
}

.help-btn {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  border: 1px solid var(--color-border);
  background: var(--color-surface-raised);
  color: var(--color-text-muted);
  font-size: var(--text-sm);
  font-weight: 700;
  cursor: pointer;
  flex-shrink: 0;
  transition: background 150ms ease, border-color 150ms ease;
  display: flex;
  align-items: center;
  justify-content: center;
}

.help-btn:hover { background: var(--app-primary-light); border-color: var(--app-primary); }

/* ── Tabs ────────────────────────────────────────────────────────────── */

.review__tabs {
  display: flex;
  background: var(--color-surface-raised);
  border-radius: var(--radius-lg);
  border: 1px solid var(--color-border-light);
  padding: 3px;
  gap: 2px;
  overflow-x: auto;
  scrollbar-width: none;
}

.review__tabs::-webkit-scrollbar { display: none; }

.review__tab {
  flex: 1;
  min-width: 0;
  padding: var(--space-2) var(--space-3);
  border: none;
  border-radius: calc(var(--radius-lg) - 3px);
  background: transparent;
  color: var(--color-text-muted);
  font-size: var(--text-xs);
  font-weight: 600;
  cursor: pointer;
  white-space: nowrap;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-1);
  transition: background 150ms ease, color 150ms ease;
  min-height: 32px;
}

.review__tab--active {
  background: var(--app-primary);
  color: white;
  box-shadow: var(--shadow-sm);
}

.review__tab:not(.review__tab--active):hover {
  background: var(--color-surface-alt);
  color: var(--color-text);
}

.tab-badge {
  background: var(--color-warning);
  color: white;
  font-size: 0.65rem;
  font-weight: 700;
  border-radius: 999px;
  padding: 1px 5px;
  line-height: 1.4;
}

.review__tab--active .tab-badge { background: rgba(255,255,255,0.3); }

/* ── Body ────────────────────────────────────────────────────────────── */

.review__body {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
  flex: 1;
}

/* ── Loading ─────────────────────────────────────────────────────────── */

.review__loading {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-3);
  padding: var(--space-12);
  color: var(--color-text-muted);
  font-size: var(--text-sm);
}

/* ── Empty state — falcon stoop (easter egg 9.3) ────────────────────── */

.review__empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-4);
  padding: var(--space-16) var(--space-8);
  text-align: center;
}

.empty-falcon {
  font-size: 4rem;
  animation: falcon-stoop 1.2s cubic-bezier(0.4, 0, 0.2, 1) forwards;
  display: block;
}

@keyframes falcon-stoop {
  0%   { transform: translateY(-60px) rotate(-30deg); opacity: 0; }
  60%  { transform: translateY(6px) rotate(0deg); opacity: 1; }
  80%  { transform: translateY(-4px); }
  100% { transform: translateY(0); opacity: 1; }
}

@media (prefers-reduced-motion: reduce) {
  .empty-falcon { animation: none; }
}

.empty-title {
  font-family: var(--font-display);
  font-size: var(--text-xl);
  color: var(--color-text);
}

.empty-desc {
  font-size: var(--text-sm);
  color: var(--color-text-muted);
  max-width: 32ch;
}

/* ── Hint bar ────────────────────────────────────────────────────────── */

.hint-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--space-2) var(--space-1);
}

.hint {
  font-size: var(--text-xs);
  color: var(--color-text-muted);
  display: flex;
  align-items: center;
  gap: 4px;
}

.hint-counter {
  font-size: var(--text-xs);
  font-weight: 600;
  color: var(--color-text-muted);
  font-family: var(--font-mono);
}

kbd {
  display: inline-flex;
  align-items: center;
  padding: 1px 5px;
  border-radius: 4px;
  border: 1px solid var(--color-border);
  background: var(--color-surface-alt);
  font-size: 0.7rem;
  font-family: var(--font-mono);
  color: var(--color-text);
  line-height: 1.5;
}

/* ── Action buttons ──────────────────────────────────────────────────── */

.review__actions {
  display: flex;
  gap: var(--space-3);
  justify-content: center;
  margin-top: var(--space-2);
}

.action-btn {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-3) var(--space-6);
  border-radius: var(--radius-lg);
  font-size: var(--text-sm);
  font-weight: 700;
  cursor: pointer;
  border: 2px solid transparent;
  min-height: 44px;
  transition: background 150ms ease, border-color 150ms ease, transform 100ms ease;
}

.action-btn:active { transform: scale(0.96); }

.action-btn--reject {
  background: rgba(192, 57, 43, 0.08);
  border-color: var(--color-error);
  color: var(--color-error);
}
.action-btn--reject:hover { background: rgba(192, 57, 43, 0.16); }

.action-btn--skip {
  background: var(--color-surface-raised);
  border-color: var(--color-border);
  color: var(--color-text-muted);
}
.action-btn--skip:hover { background: var(--color-surface-alt); }

.action-btn--approve {
  background: rgba(39, 174, 96, 0.08);
  border-color: var(--color-success);
  color: var(--color-success);
}
.action-btn--approve:hover { background: rgba(39, 174, 96, 0.16); }

.review__undo-hint {
  text-align: center;
  font-size: var(--text-xs);
  color: var(--color-text-muted);
}

/* ── Job list (non-pending tabs) ─────────────────────────────────────── */

.job-list {
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.job-list__item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
  padding: var(--space-4) var(--space-5);
  background: var(--color-surface-raised);
  border: 1px solid var(--color-border-light);
  border-radius: var(--radius-md);
  min-height: 44px;
  transition: box-shadow 150ms ease;
}

.job-list__item:hover { box-shadow: var(--shadow-sm); }

.job-list__info { display: flex; flex-direction: column; gap: 2px; flex: 1; min-width: 0; }

.job-list__title {
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--color-text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.job-list__company {
  font-size: var(--text-xs);
  color: var(--color-text-muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.job-list__meta { display: flex; align-items: center; gap: var(--space-2); flex-shrink: 0; }

.score-pill {
  padding: 2px var(--space-2);
  border-radius: 999px;
  font-size: var(--text-xs);
  font-weight: 700;
  font-family: var(--font-mono);
}

.score-pill--high { background: rgba(39, 174, 96, 0.15);  color: var(--score-high); }
.score-pill--mid  { background: rgba(212, 137, 26, 0.15); color: var(--score-mid);  }
.score-pill--low  { background: rgba(192, 57, 43, 0.15);  color: var(--score-low);  }

.job-list__link {
  font-size: var(--text-xs);
  color: var(--app-primary);
  text-decoration: none;
  font-weight: 600;
}

/* ── Help overlay ────────────────────────────────────────────────────── */

.help-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.45);
  backdrop-filter: blur(2px);
  z-index: 400;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: var(--space-6);
}

.help-modal {
  background: var(--color-surface-raised);
  border-radius: var(--radius-lg);
  border: 1px solid var(--color-border);
  padding: var(--space-6);
  width: 100%;
  max-width: 360px;
  position: relative;
  box-shadow: var(--shadow-xl, 0 16px 48px rgba(0,0,0,0.2));
}

.help-modal__title {
  font-family: var(--font-display);
  font-size: var(--text-xl);
  color: var(--color-text);
  margin-bottom: var(--space-4);
}

.help-keys { display: flex; flex-direction: column; gap: var(--space-3); }

.help-keys__row {
  display: flex;
  align-items: center;
  gap: var(--space-4);
  font-size: var(--text-sm);
}

.help-keys__row dt { width: 6rem; flex-shrink: 0; display: flex; align-items: center; gap: 4px; }
.help-keys__row dd { color: var(--color-text-muted); }

.help-modal__close {
  position: absolute;
  top: var(--space-4);
  right: var(--space-4);
  width: 32px;
  height: 32px;
  border-radius: 50%;
  border: 1px solid var(--color-border-light);
  background: transparent;
  color: var(--color-text-muted);
  font-size: var(--text-base);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: background 150ms ease;
}

.help-modal__close:hover { background: var(--color-surface-alt); }

/* ── Toasts ──────────────────────────────────────────────────────────── */

.undo-toast {
  position: fixed;
  bottom: var(--space-6);
  left: 50%;
  transform: translateX(-50%);
  background: var(--color-surface-raised);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  padding: var(--space-3) var(--space-4);
  display: flex;
  align-items: center;
  gap: var(--space-4);
  font-size: var(--text-sm);
  color: var(--color-text);
  box-shadow: var(--shadow-lg);
  z-index: 300;
  white-space: nowrap;
}

.undo-toast__btn {
  background: var(--app-primary);
  color: white;
  border: none;
  border-radius: var(--radius-md);
  padding: var(--space-1) var(--space-3);
  font-size: var(--text-xs);
  font-weight: 700;
  cursor: pointer;
  transition: background 150ms ease;
}

.undo-toast__btn:hover { background: var(--app-primary-hover); }

.stoop-toast {
  position: fixed;
  bottom: calc(var(--space-6) + 56px);
  right: var(--space-6);
  background: var(--color-surface-raised);
  border: 1px solid var(--color-border);
  padding: var(--space-3) var(--space-5);
  border-radius: var(--radius-md);
  font-size: var(--text-sm);
  color: var(--color-text-muted);
  box-shadow: var(--shadow-lg);
  z-index: 300;
}

/* ── Toast transitions ───────────────────────────────────────────────── */

.toast-enter-active, .toast-leave-active  { transition: opacity 280ms ease, transform 280ms ease; }
.toast-enter-from,  .toast-leave-to       { opacity: 0; transform: translateY(8px) translateX(-50%); }
.stoop-toast.toast-enter-from,
.stoop-toast.toast-leave-to               { transform: translateY(8px); }

.overlay-enter-active, .overlay-leave-active { transition: opacity 200ms ease; }
.overlay-enter-from,   .overlay-leave-to     { opacity: 0; }

/* ── Spinner ─────────────────────────────────────────────────────────── */

.spinner {
  width: 1.2rem;
  height: 1.2rem;
  border: 2px solid var(--color-border);
  border-top-color: var(--app-primary);
  border-radius: 50%;
  animation: spin 0.7s linear infinite;
}

@keyframes spin { to { transform: rotate(360deg); } }

/* ── Screen reader only ──────────────────────────────────────────────── */

.sr-only {
  position: absolute;
  width: 1px; height: 1px;
  padding: 0; margin: -1px;
  overflow: hidden;
  clip: rect(0,0,0,0);
  white-space: nowrap;
  border: 0;
}

/* ── Responsive ──────────────────────────────────────────────────────── */

@media (max-width: 767px) {
  .review { padding: var(--space-4); gap: var(--space-4); }
  .review__title { font-size: var(--text-xl); }

  .review__tab {
    font-size: 0.65rem;
    padding: var(--space-2);
  }

  .hint-bar { display: none; }  /* mobile: no room — swipe speaks for itself */

  .review__actions { gap: var(--space-2); }
  .action-btn      { padding: var(--space-3) var(--space-4); font-size: var(--text-xs); }

  .undo-toast {
    left:  var(--space-4);
    right: var(--space-4);
    transform: none;
    bottom: calc(56px + env(safe-area-inset-bottom) + var(--space-4));
  }
  .toast-enter-from, .toast-leave-to { transform: translateY(8px); }
}
</style>
