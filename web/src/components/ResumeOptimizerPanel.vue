<template>
  <section class="rop" aria-labelledby="rop-heading">
    <h2 id="rop-heading" class="rop__heading">ATS Resume Optimizer</h2>

    <!-- ── Tier gate notice (free) ────────────────────────────────────── -->
    <p v-if="isFree" class="rop__tier-note">
      <span aria-hidden="true">🔒</span>
      Keyword gap report is free. Full AI rewrite requires a
      <strong>Paid</strong> license.
    </p>

    <!-- ── Gap report section (all tiers) ────────────────────────────── -->
    <div class="rop__gaps">
      <div class="rop__gaps-header">
        <h3 class="rop__subheading">Keyword Gap Report</h3>
        <button
          class="btn-generate"
          :disabled="gapState === 'queued' || gapState === 'running'"
          @click="runGapReport"
        >
          <span aria-hidden="true">🔍</span>
          {{ gapState === 'queued' || gapState === 'running' ? 'Analyzing…' : 'Analyze Keywords' }}
        </button>
      </div>

      <template v-if="gapState === 'queued' || gapState === 'running'">
        <div class="rop__spinner-row" role="status" aria-live="polite">
          <span class="spinner" aria-hidden="true" />
          <span>{{ gapStage ?? 'Extracting keyword gaps…' }}</span>
        </div>
      </template>

      <template v-else-if="gapState === 'failed'">
        <p class="rop__error" role="alert">Gap analysis failed. Try again.</p>
      </template>

      <template v-else-if="gaps.length > 0">
        <div class="rop__gap-list" role="list" aria-label="Keyword gaps by section">
          <div
            v-for="item in gaps"
            :key="item.term"
            class="rop__gap-item"
            :class="`rop__gap-item--p${item.priority}`"
            role="listitem"
          >
            <span class="rop__gap-section" :title="`Route to ${item.section}`">{{ item.section }}</span>
            <span class="rop__gap-term">{{ item.term }}</span>
            <span class="rop__gap-rationale">{{ item.rationale }}</span>
          </div>
        </div>
      </template>

      <template v-else-if="gapState === 'completed'">
        <p class="rop__empty">No significant keyword gaps found — your resume already covers this JD well.</p>
      </template>

      <template v-else>
        <p class="rop__hint">Click <em>Analyze Keywords</em> to see which ATS terms your resume is missing.</p>
      </template>
    </div>

    <!-- ── Full rewrite section (paid+) ──────────────────────────────── -->
    <div v-if="!isFree" class="rop__rewrite">
      <div class="rop__gaps-header">
        <h3 class="rop__subheading">Optimized Resume</h3>
        <button
          class="btn-generate"
          :disabled="rewriteState === 'queued' || rewriteState === 'running' || gaps.length === 0"
          :title="gaps.length === 0 ? 'Run gap analysis first' : ''"
          @click="runFullRewrite"
        >
          <span aria-hidden="true">✨</span>
          {{ rewriteState === 'queued' || rewriteState === 'running' ? 'Rewriting…' : 'Optimize Resume' }}
        </button>
      </div>

      <template v-if="rewriteState === 'queued' || rewriteState === 'running'">
        <div class="rop__spinner-row" role="status" aria-live="polite">
          <span class="spinner" aria-hidden="true" />
          <span>{{ rewriteStage ?? 'Rewriting resume sections…' }}</span>
        </div>
      </template>

      <template v-else-if="rewriteState === 'failed'">
        <p class="rop__error" role="alert">Resume rewrite failed. Check that a resume file is configured in Settings.</p>
      </template>

      <template v-else-if="optimizedResume">
        <!-- Hallucination warning — shown when the task message flags it -->
        <div v-if="hallucinationWarning" class="rop__hallucination-badge" role="alert">
          <span aria-hidden="true">⚠️</span>
          Hallucination check failed — the rewrite introduced content not in your original resume.
          The optimized version has been discarded; only the gap report is available.
        </div>

        <div class="rop__rewrite-toolbar">
          <span class="rop__wordcount" aria-live="polite">{{ rewriteWordCount }} words</span>
          <span class="rop__verified-badge" aria-label="Hallucination check passed">✓ Verified</span>
        </div>
        <textarea
          v-model="optimizedResume"
          class="rop__textarea"
          aria-label="Optimized resume text"
          spellcheck="false"
        />
        <button class="btn-download" @click="downloadTxt">
          <span aria-hidden="true">📄</span> Download .txt
        </button>
      </template>

      <template v-else>
        <p class="rop__hint">
          Run <em>Analyze Keywords</em> first, then click <em>Optimize Resume</em> to rewrite your resume
          sections to naturally incorporate missing ATS keywords.
        </p>
      </template>
    </div>
  </section>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useApiFetch } from '../composables/useApi'
import { useAppConfigStore } from '../stores/appConfig'

const props = defineProps<{ jobId: number }>()

const config = useAppConfigStore()
const isFree = computed(() => config.tier === 'free')

// ── Gap report state ─────────────────────────────────────────────────────────

type TaskState = 'none' | 'queued' | 'running' | 'completed' | 'failed'

const gapState    = ref<TaskState>('none')
const gapStage    = ref<string | null>(null)
const gaps        = ref<Array<{ term: string; section: string; priority: number; rationale: string }>>([])

// ── Rewrite state ────────────────────────────────────────────────────────────

const rewriteState        = ref<TaskState>('none')
const rewriteStage        = ref<string | null>(null)
const optimizedResume     = ref('')
const hallucinationWarning = ref(false)

const rewriteWordCount = computed(() =>
  optimizedResume.value.trim().split(/\s+/).filter(Boolean).length
)

// ── Task polling ─────────────────────────────────────────────────────────────

let pollTimer: ReturnType<typeof setInterval> | null = null

function startPolling() {
  stopPolling()
  pollTimer = setInterval(pollTaskStatus, 3000)
}

function stopPolling() {
  if (pollTimer !== null) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

async function pollTaskStatus() {
  const { data } = await useApiFetch<{ status: string; stage: string | null; message: string | null }>(
    `/api/jobs/${props.jobId}/resume_optimizer/task`
  )
  if (!data) return

  const status = data.status as TaskState

  // Update whichever phase is in-flight
  if (gapState.value === 'queued' || gapState.value === 'running') {
    gapState.value = status
    gapStage.value = data.stage ?? null
    if (status === 'completed' || status === 'failed') {
      stopPolling()
      if (status === 'completed') await loadResults()
    }
  } else if (rewriteState.value === 'queued' || rewriteState.value === 'running') {
    rewriteState.value = status
    rewriteStage.value = data.stage ?? null
    if (status === 'completed' || status === 'failed') {
      stopPolling()
      if (status === 'completed') await loadResults()
    }
  }
}

// ── Load existing results ────────────────────────────────────────────────────

async function loadResults() {
  const { data } = await useApiFetch<{
    optimized_resume: string
    ats_gap_report: Array<{ term: string; section: string; priority: number; rationale: string }>
  }>(`/api/jobs/${props.jobId}/resume_optimizer`)

  if (!data) return

  if (data.ats_gap_report?.length) {
    gaps.value = data.ats_gap_report
    gapState.value = 'completed'
  }

  if (data.optimized_resume) {
    optimizedResume.value = data.optimized_resume
    rewriteState.value = 'completed'
  }
}

// ── Actions ──────────────────────────────────────────────────────────────────

async function runGapReport() {
  gapState.value = 'queued'
  gapStage.value = null
  gaps.value = []
  const { error } = await useApiFetch(`/api/jobs/${props.jobId}/resume_optimizer/generate`, {
    method: 'POST',
    body: JSON.stringify({ full_rewrite: false }),
    headers: { 'Content-Type': 'application/json' },
  })
  if (error) {
    gapState.value = 'failed'
    return
  }
  startPolling()
}

async function runFullRewrite() {
  rewriteState.value = 'queued'
  rewriteStage.value = null
  optimizedResume.value = ''
  hallucinationWarning.value = false
  const { error } = await useApiFetch(`/api/jobs/${props.jobId}/resume_optimizer/generate`, {
    method: 'POST',
    body: JSON.stringify({ full_rewrite: true }),
    headers: { 'Content-Type': 'application/json' },
  })
  if (error) {
    rewriteState.value = 'failed'
    return
  }
  startPolling()
}

function downloadTxt() {
  const blob = new Blob([optimizedResume.value], { type: 'text/plain' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `resume-optimized-job-${props.jobId}.txt`
  a.click()
  URL.revokeObjectURL(url)
}

// ── Lifecycle ────────────────────────────────────────────────────────────────

onMounted(async () => {
  await loadResults()
  // Resume polling if a task was still in-flight when the page last unloaded
  const { data } = await useApiFetch<{ status: string }>(
    `/api/jobs/${props.jobId}/resume_optimizer/task`
  )
  if (data?.status === 'queued' || data?.status === 'running') {
    // Restore in-flight state to whichever phase makes sense
    if (!optimizedResume.value && !gaps.value.length) {
      gapState.value = data.status as TaskState
    } else if (gaps.value.length) {
      rewriteState.value = data.status as TaskState
    }
    startPolling()
  }
})

onUnmounted(stopPolling)
</script>

<style scoped>
.rop {
  display: flex;
  flex-direction: column;
  gap: var(--space-5, 1.25rem);
  padding: var(--space-4, 1rem);
  border-top: 1px solid var(--app-border, #e2e8f0);
}

.rop__heading {
  font-size: var(--font-lg, 1.125rem);
  font-weight: 600;
  color: var(--app-text, #1e293b);
  margin: 0;
}

.rop__subheading {
  font-size: var(--font-base, 1rem);
  font-weight: 600;
  color: var(--app-text, #1e293b);
  margin: 0;
}

.rop__tier-note {
  font-size: var(--font-sm, 0.875rem);
  color: var(--app-text-muted, #64748b);
  background: var(--app-surface-alt, #f8fafc);
  border: 1px solid var(--app-border, #e2e8f0);
  border-radius: var(--radius-md, 0.5rem);
  padding: var(--space-3, 0.75rem) var(--space-4, 1rem);
  margin: 0;
}

.rop__gaps,
.rop__rewrite {
  display: flex;
  flex-direction: column;
  gap: var(--space-3, 0.75rem);
}

.rop__gaps-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3, 0.75rem);
}

.rop__hint,
.rop__empty {
  font-size: var(--font-sm, 0.875rem);
  color: var(--app-text-muted, #64748b);
  margin: 0;
}

.rop__error {
  font-size: var(--font-sm, 0.875rem);
  color: var(--app-danger, #dc2626);
  margin: 0;
}

.rop__spinner-row {
  display: flex;
  align-items: center;
  gap: var(--space-2, 0.5rem);
  font-size: var(--font-sm, 0.875rem);
  color: var(--app-text-muted, #64748b);
}

/* ── Gap list ─────────────────────────────────────────────────────── */

.rop__gap-list {
  display: flex;
  flex-direction: column;
  gap: var(--space-1, 0.25rem);
}

.rop__gap-item {
  display: grid;
  grid-template-columns: 6rem 1fr;
  grid-template-rows: auto auto;
  gap: 0 var(--space-2, 0.5rem);
  padding: var(--space-2, 0.5rem) var(--space-3, 0.75rem);
  border-radius: var(--radius-sm, 0.25rem);
  border-left: 3px solid transparent;
  background: var(--app-surface-alt, #f8fafc);
  font-size: var(--font-sm, 0.875rem);
}

.rop__gap-item--p1 { border-left-color: var(--app-accent, #6366f1); }
.rop__gap-item--p2 { border-left-color: var(--app-warning, #f59e0b); }
.rop__gap-item--p3 { border-left-color: var(--app-border, #e2e8f0); }

.rop__gap-section {
  grid-row: 1;
  grid-column: 1;
  font-size: var(--font-xs, 0.75rem);
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--app-text-muted, #64748b);
  align-self: center;
}

.rop__gap-term {
  grid-row: 1;
  grid-column: 2;
  font-weight: 500;
  color: var(--app-text, #1e293b);
}

.rop__gap-rationale {
  grid-row: 2;
  grid-column: 2;
  font-size: var(--font-xs, 0.75rem);
  color: var(--app-text-muted, #64748b);
}

/* ── Rewrite output ───────────────────────────────────────────────── */

.rop__rewrite-toolbar {
  display: flex;
  align-items: center;
  gap: var(--space-3, 0.75rem);
  justify-content: space-between;
}

.rop__wordcount {
  font-size: var(--font-sm, 0.875rem);
  color: var(--app-text-muted, #64748b);
}

.rop__verified-badge {
  font-size: var(--font-xs, 0.75rem);
  font-weight: 600;
  color: var(--app-success, #16a34a);
  background: color-mix(in srgb, var(--app-success, #16a34a) 10%, transparent);
  padding: 0.2em 0.6em;
  border-radius: var(--radius-full, 9999px);
}

.rop__hallucination-badge {
  display: flex;
  align-items: flex-start;
  gap: var(--space-2, 0.5rem);
  padding: var(--space-3, 0.75rem) var(--space-4, 1rem);
  background: color-mix(in srgb, var(--app-danger, #dc2626) 8%, transparent);
  border: 1px solid color-mix(in srgb, var(--app-danger, #dc2626) 30%, transparent);
  border-radius: var(--radius-md, 0.5rem);
  font-size: var(--font-sm, 0.875rem);
  color: var(--app-danger, #dc2626);
}

.rop__textarea {
  width: 100%;
  min-height: 20rem;
  padding: var(--space-3, 0.75rem);
  font-family: var(--font-mono, monospace);
  font-size: var(--font-sm, 0.875rem);
  line-height: 1.6;
  border: 1px solid var(--app-border, #e2e8f0);
  border-radius: var(--radius-md, 0.5rem);
  background: var(--app-surface, #fff);
  color: var(--app-text, #1e293b);
  resize: vertical;
  box-sizing: border-box;
}

.rop__textarea:focus {
  outline: 2px solid var(--app-accent, #6366f1);
  outline-offset: 2px;
}

/* ── Buttons (inherit app-wide classes) ──────────────────────────── */

.btn-generate {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2, 0.5rem);
  padding: var(--space-2, 0.5rem) var(--space-4, 1rem);
  background: var(--app-accent, #6366f1);
  color: #fff;
  border: none;
  border-radius: var(--radius-md, 0.5rem);
  font-size: var(--font-sm, 0.875rem);
  font-weight: 500;
  cursor: pointer;
  transition: background 0.15s;
  white-space: nowrap;
}

.btn-generate:hover:not(:disabled) { background: var(--app-accent-hover, #4f46e5); }
.btn-generate:disabled { opacity: 0.6; cursor: not-allowed; }

.btn-download {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2, 0.5rem);
  padding: var(--space-2, 0.5rem) var(--space-4, 1rem);
  background: var(--app-surface-alt, #f8fafc);
  color: var(--app-text, #1e293b);
  border: 1px solid var(--app-border, #e2e8f0);
  border-radius: var(--radius-md, 0.5rem);
  font-size: var(--font-sm, 0.875rem);
  font-weight: 500;
  cursor: pointer;
  transition: background 0.15s;
  align-self: flex-start;
}

.btn-download:hover { background: var(--app-border, #e2e8f0); }

@media (max-width: 640px) {
  .rop__gaps-header { flex-direction: column; align-items: flex-start; }
  .btn-generate { width: 100%; justify-content: center; }
}
</style>
