<template>
  <div class="workspace">
    <!-- Back nav -->
    <RouterLink to="/apply" class="workspace__back">← Back to Apply</RouterLink>

    <div v-if="loadingJob" class="workspace__loading" aria-live="polite">
      <span class="spinner" aria-hidden="true" />
      <span>Loading job…</span>
    </div>

    <div v-else-if="!job" class="workspace__not-found" role="alert">
      <p>Job not found.</p>
      <RouterLink to="/apply" class="btn-ghost">← Back</RouterLink>
    </div>

    <template v-else>
      <!-- Two-panel layout: job details | cover letter -->
      <div class="workspace__panels">

        <!-- ── Left: Job details ──────────────────────────────────────── -->
        <aside class="workspace__job-panel">
          <div class="job-details">
            <!-- Badges -->
            <div class="job-details__badges">
              <span v-if="job.match_score !== null" class="score-badge" :class="scoreBadgeClass">
                {{ job.match_score }}%
              </span>
              <span v-if="job.is_remote" class="remote-badge">Remote</span>
            </div>

            <h1 class="job-details__title">{{ job.title }}</h1>
            <div class="job-details__company">
              {{ job.company }}
              <span v-if="job.location" aria-hidden="true"> · </span>
              <span v-if="job.location" class="job-details__location">{{ job.location }}</span>
            </div>
            <div v-if="job.salary" class="job-details__salary">{{ job.salary }}</div>

            <!-- Description -->
            <div class="job-details__desc" :class="{ 'job-details__desc--clamped': !descExpanded }">
              {{ job.description ?? 'No description available.' }}
            </div>
            <button
              v-if="(job.description?.length ?? 0) > 300"
              class="expand-btn"
              :aria-expanded="descExpanded"
              @click="descExpanded = !descExpanded"
            >
              {{ descExpanded ? 'Show less ▲' : 'Show more ▼' }}
            </button>

            <!-- Keyword gaps -->
            <div v-if="gaps.length > 0" class="job-details__gaps">
              <span class="gaps-label">Missing keywords:</span>
              <span v-for="kw in gaps.slice(0, 6)" :key="kw" class="gap-pill">{{ kw }}</span>
              <span v-if="gaps.length > 6" class="gaps-more">+{{ gaps.length - 6 }}</span>
            </div>

            <a v-if="job.url" :href="job.url" target="_blank" rel="noopener noreferrer" class="job-details__link">
              View listing ↗
            </a>
          </div>
        </aside>

        <!-- ── Right: Cover letter ────────────────────────────────────── -->
        <main class="workspace__cl-panel">
          <h2 class="cl-heading">Cover Letter</h2>

          <!-- State: none — no draft yet -->
          <template v-if="clState === 'none'">
            <div class="cl-empty">
              <p class="cl-empty__hint">No cover letter yet. Generate one with AI or paste your own.</p>
              <div class="cl-empty__actions">
                <button class="btn-generate" :disabled="generating" @click="generate()">
                  <span aria-hidden="true">✨</span> Generate with AI
                </button>
                <button class="btn-ghost" @click="clState = 'ready'; clText = ''">
                  Paste / write manually
                </button>
              </div>
            </div>
          </template>

          <!-- State: queued / running — generating -->
          <template v-else-if="clState === 'queued' || clState === 'running'">
            <div class="cl-generating" role="status" aria-live="polite">
              <span class="spinner spinner--lg" aria-hidden="true" />
              <p class="cl-generating__label">
                {{ clState === 'queued' ? 'Queued…' : (taskStage ?? 'Generating cover letter…') }}
              </p>
              <p class="cl-generating__hint">This usually takes 20–60 seconds</p>
            </div>
          </template>

          <!-- State: failed -->
          <template v-else-if="clState === 'failed'">
            <div class="cl-error" role="alert">
              <span aria-hidden="true">⚠️</span>
              <span class="cl-error__msg">Cover letter generation failed</span>
              <span v-if="taskError" class="cl-error__detail">{{ taskError }}</span>
              <button class="btn-generate" @click="generate()">Retry</button>
            </div>
          </template>

          <!-- State: ready — editor -->
          <template v-else-if="clState === 'ready'">
            <div class="cl-editor">
              <div class="cl-editor__toolbar">
                <span class="cl-editor__wordcount" aria-live="polite">
                  {{ wordCount }} words
                </span>
                <button
                  class="btn-ghost btn-ghost--sm"
                  :disabled="isSaved || saving"
                  @click="saveCoverLetter"
                >
                  {{ saving ? 'Saving…' : (isSaved ? '✓ Saved' : 'Save') }}
                </button>
              </div>
              <textarea
                ref="textareaEl"
                v-model="clText"
                class="cl-editor__textarea"
                aria-label="Cover letter text"
                placeholder="Your cover letter…"
                @input="isSaved = false; autoResize()"
              />
            </div>

            <!-- Download PDF -->
            <button class="btn-download" :disabled="!clText.trim() || downloadingPdf" @click="downloadPdf">
              <span aria-hidden="true">📄</span>
              {{ downloadingPdf ? 'Generating PDF…' : 'Download PDF' }}
            </button>
          </template>

          <!-- Regenerate button (when ready, offer to redo) -->
          <button
            v-if="clState === 'ready'"
            class="btn-ghost btn-ghost--sm cl-regen"
            @click="generate()"
          >
            ↺ Regenerate
          </button>

          <!-- ── Bottom action bar ──────────────────────────────────── -->
          <div class="workspace__actions">
            <button
              class="action-btn action-btn--apply"
              :disabled="actioning"
              @click="markApplied"
            >
              <span aria-hidden="true">🚀</span>
              {{ actioning === 'apply' ? 'Marking…' : 'Mark as Applied' }}
            </button>
            <button
              class="action-btn action-btn--reject"
              :disabled="!!actioning"
              @click="rejectListing"
            >
              <span aria-hidden="true">✗</span>
              {{ actioning === 'reject' ? 'Rejecting…' : 'Reject Listing' }}
            </button>
          </div>

        </main>
      </div>
    </template>

    <!-- Toast -->
    <Transition name="toast">
      <div v-if="toast" class="toast" role="status" aria-live="polite">{{ toast }}</div>
    </Transition>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted, nextTick } from 'vue'
import { useRoute, useRouter, RouterLink } from 'vue-router'
import { useApiFetch } from '../composables/useApi'
import type { Job } from '../stores/review'

const route  = useRoute()
const router = useRouter()
const jobId  = Number(route.params.id)

// ─── Job ──────────────────────────────────────────────────────────────────────

const job        = ref<Job | null>(null)
const loadingJob = ref(true)
const descExpanded = ref(false)

const gaps = computed<string[]>(() => {
  if (!job.value?.keyword_gaps) return []
  try   { return JSON.parse(job.value.keyword_gaps) as string[] }
  catch { return [] }
})

const scoreBadgeClass = computed(() => {
  const s = job.value?.match_score ?? 0
  if (s >= 80) return 'score-badge--high'
  if (s >= 60) return 'score-badge--mid'
  return 'score-badge--low'
})

// ─── Cover letter state machine ───────────────────────────────────────────────
// none → queued → running → ready | failed

type ClState = 'none' | 'queued' | 'running' | 'ready' | 'failed'

const clState   = ref<ClState>('none')
const clText    = ref('')
const isSaved   = ref(true)
const saving    = ref(false)
const generating = ref(false)
const taskStage = ref<string | null>(null)
const taskError = ref<string | null>(null)

const wordCount = computed(() => {
  const words = clText.value.trim().split(/\s+/).filter(Boolean)
  return words.length
})

// ─── Polling ──────────────────────────────────────────────────────────────────

let pollTimer = 0

function startPolling() {
  stopPolling()
  pollTimer = window.setInterval(pollTaskStatus, 2000)
}

function stopPolling() {
  clearInterval(pollTimer)
}

async function pollTaskStatus() {
  const { data } = await useApiFetch<{
    status:  string
    stage:   string | null
    message: string | null
  }>(`/api/jobs/${jobId}/cover_letter/task`)
  if (!data) return

  taskStage.value = data.stage

  if (data.status === 'completed') {
    stopPolling()
    // Re-fetch the job to get the new cover letter text
    await fetchJob()
    clState.value = 'ready'
    generating.value = false
  } else if (data.status === 'failed') {
    stopPolling()
    clState.value  = 'failed'
    taskError.value = data.message ?? 'Unknown error'
    generating.value = false
  } else {
    clState.value = data.status === 'queued' ? 'queued' : 'running'
  }
}

// ─── Actions ──────────────────────────────────────────────────────────────────

async function generate() {
  if (generating.value) return
  generating.value = true
  clState.value    = 'queued'
  taskError.value  = null

  const { error } = await useApiFetch(`/api/jobs/${jobId}/cover_letter/generate`, { method: 'POST' })
  if (error) {
    clState.value    = 'failed'
    taskError.value  = error.kind === 'http' ? error.detail : 'Network error'
    generating.value = false
    return
  }
  startPolling()
}

async function saveCoverLetter() {
  saving.value = true
  await useApiFetch(`/api/jobs/${jobId}/cover_letter`, {
    method:  'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body:    JSON.stringify({ text: clText.value }),
  })
  saving.value = false
  isSaved.value = true
}

// ─── PDF download ─────────────────────────────────────────────────────────────

const downloadingPdf = ref(false)

async function downloadPdf() {
  if (!job.value) return
  downloadingPdf.value = true
  try {
    const res = await fetch(`/api/jobs/${jobId}/cover_letter/pdf`)
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    const blob = await res.blob()
    const url  = URL.createObjectURL(blob)
    const a    = document.createElement('a')
    const company   = job.value.company.replace(/[^a-zA-Z0-9]/g, '') || 'Company'
    const dateStr   = new Date().toISOString().slice(0, 10)
    a.href     = url
    a.download = `CoverLetter_${company}_${dateStr}.pdf`
    a.click()
    URL.revokeObjectURL(url)
  } catch {
    showToast('PDF generation failed — save first and try again')
  } finally {
    downloadingPdf.value = false
  }
}

// ─── Mark applied / reject ────────────────────────────────────────────────────

const actioning = ref<'apply' | 'reject' | null>(null)

async function markApplied() {
  if (actioning.value) return
  actioning.value = 'apply'
  if (!isSaved.value) await saveCoverLetter()
  await useApiFetch(`/api/jobs/${jobId}/applied`, { method: 'POST' })
  actioning.value = null
  showToast('Marked as applied ✓')
  setTimeout(() => router.push('/apply'), 1200)
}

async function rejectListing() {
  if (actioning.value) return
  actioning.value = 'reject'
  await useApiFetch(`/api/jobs/${jobId}/reject`, { method: 'POST' })
  actioning.value = null
  showToast('Listing rejected')
  setTimeout(() => router.push('/apply'), 1000)
}

// ─── Toast ────────────────────────────────────────────────────────────────────

const toast = ref<string | null>(null)
let toastTimer = 0

function showToast(msg: string) {
  clearTimeout(toastTimer)
  toast.value  = msg
  toastTimer   = window.setTimeout(() => { toast.value = null }, 3500)
}

// ─── Auto-resize textarea ─────────────────────────────────────────────────────

const textareaEl = ref<HTMLTextAreaElement | null>(null)

function autoResize() {
  const el = textareaEl.value
  if (!el) return
  el.style.height = 'auto'
  el.style.height = `${el.scrollHeight}px`
}

watch(clText, () => nextTick(autoResize))

// ─── Data loading ─────────────────────────────────────────────────────────────

async function fetchJob() {
  const { data } = await useApiFetch<Job>(`/api/jobs/${jobId}`)
  if (data) {
    job.value = data
    if (data.cover_letter) {
      clText.value = data.cover_letter as string
      clState.value = 'ready'
      isSaved.value = true
    }
  }
}

onMounted(async () => {
  await fetchJob()
  loadingJob.value = false

  // Check if a generation task is already in flight
  if (clState.value === 'none') {
    const { data } = await useApiFetch<{ status: string; stage: string | null }>(`/api/jobs/${jobId}/cover_letter/task`)
    if (data && (data.status === 'queued' || data.status === 'running')) {
      clState.value    = data.status as ClState
      taskStage.value  = data.stage
      generating.value = true
      startPolling()
    }
  }

  await nextTick(autoResize)
})

onUnmounted(() => {
  stopPolling()
  clearTimeout(toastTimer)
})

// Extra type to allow cover_letter field on Job
declare module '../stores/review' {
  interface Job { cover_letter?: string | null }
}
</script>

<style scoped>
.workspace {
  max-width: 1200px;
  margin: 0 auto;
  padding: var(--space-6) var(--space-6) var(--space-12);
  display: flex;
  flex-direction: column;
  gap: var(--space-5);
}

.workspace__back {
  color: var(--app-primary);
  font-size: var(--text-sm);
  font-weight: 600;
  text-decoration: none;
  align-self: flex-start;
  transition: opacity 150ms ease;
}
.workspace__back:hover { opacity: 0.7; }

.workspace__loading,
.workspace__not-found {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--space-4);
  padding: var(--space-16);
  color: var(--color-text-muted);
  font-size: var(--text-sm);
}

/* ── Two-panel layout ────────────────────────────────────────────────── */

.workspace__panels {
  display: grid;
  grid-template-columns: 1fr 1.3fr;
  gap: var(--space-6);
  align-items: start;
}

/* ── Job details panel ───────────────────────────────────────────────── */

.workspace__job-panel {
  position: sticky;
  top: var(--space-4);
}

.job-details {
  background: var(--color-surface-raised);
  border: 1px solid var(--color-border-light);
  border-radius: var(--radius-lg);
  padding: var(--space-5);
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.job-details__badges { display: flex; flex-wrap: wrap; gap: var(--space-2); }

.job-details__title {
  font-family: var(--font-display);
  font-size: var(--text-xl);
  color: var(--color-text);
  line-height: 1.25;
}

.job-details__company {
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--color-text-muted);
}

.job-details__location { font-weight: 400; }

.job-details__salary {
  font-size: var(--text-sm);
  font-weight: 700;
  color: var(--color-success);
}

.job-details__desc {
  font-size: var(--text-sm);
  color: var(--color-text);
  line-height: 1.6;
  white-space: pre-wrap;
  overflow-wrap: break-word;
}

.job-details__desc--clamped {
  display: -webkit-box;
  -webkit-line-clamp: 6;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.expand-btn {
  align-self: flex-start;
  background: transparent;
  border: none;
  color: var(--app-primary);
  font-size: var(--text-xs);
  cursor: pointer;
  padding: 0;
  font-weight: 600;
}

.job-details__gaps { display: flex; flex-wrap: wrap; gap: var(--space-1); align-items: center; }
.gaps-label { font-size: var(--text-xs); color: var(--color-text-muted); font-weight: 600; }
.gap-pill {
  padding: 1px var(--space-2);
  border-radius: 999px;
  font-size: var(--text-xs);
  background: var(--color-surface-alt);
  border: 1px solid var(--color-border-light);
  color: var(--color-text-muted);
}
.gaps-more { font-size: var(--text-xs); color: var(--color-text-muted); }

.job-details__link {
  font-size: var(--text-xs);
  color: var(--app-primary);
  font-weight: 600;
  text-decoration: none;
  align-self: flex-start;
  transition: opacity 150ms ease;
}
.job-details__link:hover { opacity: 0.7; }

/* ── Cover letter panel ──────────────────────────────────────────────── */

.workspace__cl-panel {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.cl-heading {
  font-family: var(--font-display);
  font-size: var(--text-xl);
  color: var(--color-text);
}

/* Empty state */
.cl-empty {
  background: var(--color-surface-raised);
  border: 1px solid var(--color-border-light);
  border-radius: var(--radius-lg);
  padding: var(--space-8);
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-4);
  text-align: center;
}

.cl-empty__hint { font-size: var(--text-sm); color: var(--color-text-muted); max-width: 36ch; }

.cl-empty__actions { display: flex; flex-direction: column; gap: var(--space-2); width: 100%; max-width: 260px; }

/* Generating state */
.cl-generating {
  background: var(--color-surface-raised);
  border: 1px solid var(--color-border-light);
  border-radius: var(--radius-lg);
  padding: var(--space-10);
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-4);
  text-align: center;
}

.cl-generating__label {
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--color-text);
}

.cl-generating__hint { font-size: var(--text-xs); color: var(--color-text-muted); }

/* Error state */
.cl-error {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: var(--space-2);
  padding: var(--space-5);
  background: rgba(192, 57, 43, 0.06);
  border: 1px solid var(--color-error);
  border-radius: var(--radius-lg);
  color: var(--color-error);
  font-size: var(--text-sm);
  font-weight: 600;
}

.cl-error__msg    { font-weight: 700; }
.cl-error__detail { font-size: var(--text-xs); color: var(--color-text-muted); font-weight: 400; }

/* Editor */
.cl-editor {
  background: var(--color-surface-raised);
  border: 1px solid var(--color-border-light);
  border-radius: var(--radius-lg);
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.cl-editor__toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--space-2) var(--space-4);
  border-bottom: 1px solid var(--color-border-light);
  background: var(--color-surface-alt);
}

.cl-editor__wordcount {
  font-size: var(--text-xs);
  color: var(--color-text-muted);
  font-family: var(--font-mono);
}

.cl-editor__textarea {
  width: 100%;
  min-height: 360px;
  padding: var(--space-5);
  border: none;
  background: transparent;
  color: var(--color-text);
  font-family: var(--font-body);
  font-size: var(--text-sm);
  line-height: 1.7;
  resize: none;
  overflow: hidden;
}

.cl-editor__textarea:focus { outline: none; }

.cl-regen {
  align-self: flex-end;
  color: var(--color-text-muted);
}

/* Download button */
.btn-download {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-3) var(--space-5);
  background: var(--color-surface-raised);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  color: var(--color-text);
  font-size: var(--text-sm);
  font-weight: 600;
  cursor: pointer;
  transition: background 150ms ease, border-color 150ms ease;
  min-height: 44px;
  width: 100%;
  justify-content: center;
}

.btn-download:hover:not(:disabled) { background: var(--app-primary-light); border-color: var(--app-primary); }
.btn-download:disabled { opacity: 0.5; cursor: not-allowed; }

/* Generate button */
.btn-generate {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-2);
  padding: var(--space-3) var(--space-5);
  background: var(--app-accent);
  color: var(--app-accent-text);
  border: none;
  border-radius: var(--radius-md);
  font-size: var(--text-sm);
  font-weight: 700;
  cursor: pointer;
  min-height: 44px;
  transition: background 150ms ease;
  width: 100%;
}

.btn-generate:hover:not(:disabled) { background: var(--app-accent-hover); }
.btn-generate:disabled { opacity: 0.6; cursor: not-allowed; }

/* ── Action bar ──────────────────────────────────────────────────────── */

.workspace__actions {
  display: flex;
  gap: var(--space-3);
  padding-top: var(--space-2);
  border-top: 1px solid var(--color-border-light);
  margin-top: var(--space-2);
}

.action-btn {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-2);
  padding: var(--space-3) var(--space-4);
  border-radius: var(--radius-lg);
  font-size: var(--text-sm);
  font-weight: 700;
  cursor: pointer;
  border: 2px solid transparent;
  min-height: 48px;
  transition: background 150ms ease, border-color 150ms ease;
}

.action-btn:disabled { opacity: 0.5; cursor: not-allowed; }

.action-btn--apply {
  background: rgba(39, 174, 96, 0.10);
  border-color: var(--color-success);
  color: var(--color-success);
}
.action-btn--apply:hover:not(:disabled)  { background: rgba(39, 174, 96, 0.20); }

.action-btn--reject {
  background: rgba(192, 57, 43, 0.08);
  border-color: var(--color-error);
  color: var(--color-error);
}
.action-btn--reject:hover:not(:disabled) { background: rgba(192, 57, 43, 0.16); }

/* ── Shared badges ───────────────────────────────────────────────────── */

.score-badge {
  padding: 2px var(--space-2);
  border-radius: 999px;
  font-size: var(--text-xs);
  font-weight: 700;
  font-family: var(--font-mono);
}
.score-badge--high { background: rgba(39,174,96,0.12);  color: var(--score-high); }
.score-badge--mid  { background: rgba(212,137,26,0.12); color: var(--score-mid);  }
.score-badge--low  { background: rgba(192,57,43,0.12);  color: var(--score-low);  }

.remote-badge {
  padding: 2px var(--space-2);
  border-radius: 999px;
  font-size: var(--text-xs);
  font-weight: 600;
  background: var(--app-primary-light);
  color: var(--app-primary);
}

/* ── Ghost button ────────────────────────────────────────────────────── */

.btn-ghost {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: var(--space-2) var(--space-4);
  background: transparent;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  color: var(--color-text-muted);
  font-size: var(--text-sm);
  font-weight: 600;
  cursor: pointer;
  min-height: 36px;
  transition: background 150ms ease, color 150ms ease;
  text-decoration: none;
}
.btn-ghost:hover   { background: var(--color-surface-alt); color: var(--color-text); }
.btn-ghost:disabled { opacity: 0.5; cursor: not-allowed; }
.btn-ghost--sm     { font-size: var(--text-xs); padding: var(--space-1) var(--space-3); min-height: 28px; }

/* ── Spinner ─────────────────────────────────────────────────────────── */

.spinner {
  width: 1.2rem;
  height: 1.2rem;
  border: 2px solid var(--color-border);
  border-top-color: var(--app-primary);
  border-radius: 50%;
  animation: spin 0.7s linear infinite;
  flex-shrink: 0;
}

.spinner--lg { width: 2rem; height: 2rem; border-width: 3px; }

@keyframes spin { to { transform: rotate(360deg); } }

/* ── Toast ───────────────────────────────────────────────────────────── */

.toast {
  position: fixed;
  bottom: var(--space-6);
  left: 50%;
  transform: translateX(-50%);
  background: var(--color-surface-raised);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  padding: var(--space-3) var(--space-5);
  font-size: var(--text-sm);
  color: var(--color-text);
  box-shadow: var(--shadow-lg);
  z-index: 300;
  white-space: nowrap;
}

.toast-enter-active, .toast-leave-active { transition: opacity 250ms ease, transform 250ms ease; }
.toast-enter-from, .toast-leave-to { opacity: 0; transform: translateX(-50%) translateY(8px); }

/* ── Responsive ──────────────────────────────────────────────────────── */

@media (max-width: 900px) {
  .workspace__panels {
    grid-template-columns: 1fr;
  }

  .workspace__job-panel {
    position: static;
  }

  .cl-editor__textarea { min-height: 260px; }

  .toast {
    left:  var(--space-4);
    right: var(--space-4);
    transform: none;
    bottom: calc(56px + env(safe-area-inset-bottom) + var(--space-3));
  }
  .toast-enter-from, .toast-leave-to { transform: translateY(8px); }
}

@media (max-width: 600px) {
  .workspace { padding: var(--space-4); }
  .workspace__actions { flex-direction: column; }
}
</style>
