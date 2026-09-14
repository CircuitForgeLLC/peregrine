<template>
  <Teleport to="body">
    <div
      class="rsm-backdrop"
      role="dialog"
      aria-modal="true"
      aria-labelledby="rsm-title"
      @keydown.esc="close"
      @click.self="close"
    >
      <div class="rsm-card" ref="cardRef" tabindex="-1">
        <div class="rsm__header">
          <h2 id="rsm-title" class="rsm__title">Resume Score</h2>
          <button class="rsm__close" aria-label="Close" @click="close">✕</button>
        </div>

        <div class="rsm__body">
          <div v-if="state === 'idle'" class="rsm__idle">
            <p>Get a holistic score and feedback on this resume — overall quality plus ATS hygiene.</p>
            <button class="btn-generate" @click="startScoring">Score this resume</button>
          </div>
          <div v-else-if="state === 'loading'" class="rsm__loading" role="status" aria-live="polite">
            <p>{{ stageLabel }}</p>
          </div>

          <div v-else-if="state === 'error'" class="rsm__error" role="alert">
            <p>Scoring failed{{ errorSuffix }}</p>
            <button class="btn-secondary" @click="startScoring">Try again</button>
          </div>
          <div v-else-if="state === 'done' && feedback" class="rsm__result">
            <div class="rsm__score-badge" :class="scoreClass(feedback.overall_score)">
              <span class="rsm__score-value">{{ overallScoreLabel }}</span>
              <span class="rsm__score-max">/10</span>
            </div>
            <p class="rsm__summary">{{ feedback.summary }}</p>

            <div class="rsm__columns">
              <div class="rsm__column">
                <h3>Strengths</h3>
                <ul>
                  <li v-for="(s, i) in feedback.strengths" :key="i">{{ s }}</li>
                </ul>
              </div>
              <div class="rsm__column">
                <h3>Areas for Improvement</h3>
                <ul>
                  <li v-for="(s, i) in feedback.improvements" :key="i">{{ s }}</li>
                </ul>
              </div>
            </div>
            <h3>Suggestions</h3>
            <ul class="rsm__suggestions">
              <li v-for="sugg in feedback.suggestions" :key="sugg.id" class="rsm__suggestion">
                <p class="rsm__before"><strong>Before:</strong> {{ sugg.before }}</p>
                <p class="rsm__after"><strong>After:</strong> {{ sugg.after }}</p>
                <p class="rsm__rationale">{{ sugg.rationale }}</p>
                <button
                  v-if="sugg.appliable"
                  class="btn-secondary"
                  :disabled="applyingId === sugg.id || appliedIds.has(sugg.id)"
                  @click="applySuggestion(sugg)"
                >
                  {{ applyLabel(sugg) }}
                </button>
                <button v-else class="btn-secondary" disabled>Needs manual review</button>
              </li>
            </ul>
            <div class="rsm__ats-card">
              <h3>ATS Hygiene</h3>
              <div class="rsm__score-badge rsm__score-badge--small" :class="scoreClass(feedback.ats_score)">
                <span class="rsm__score-value">{{ atsScoreLabel }}</span>
                <span class="rsm__score-max">/10</span>
              </div>
              <p class="rsm__ats-basis">{{ feedback.ats_basis }}</p>
              <ul>
                <li v-for="(issue, i) in feedback.ats_issues" :key="i">{{ issue }}</li>
              </ul>
            </div>

            <button class="btn-secondary" @click="startScoring">Re-score</button>
          </div>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount, onUnmounted, nextTick } from 'vue'
import { useApiFetch } from '../composables/useApi'

const props = defineProps<{ resumeId: number }>()
const emit = defineEmits<{ close: []; applied: [] }>()

interface Suggestion {
  id: string; section: string; target: string
  before: string; after: string; rationale: string; appliable: boolean
}
interface Feedback {
  overall_score: number | null; summary: string
  strengths: string[]; improvements: string[]; suggestions: Suggestion[]
  ats_score: number | null; ats_basis: string; ats_issues: string[]
}

type State = 'idle' | 'loading' | 'error' | 'done'
const state = ref<State>('idle')
const phaseText = ref<string | null>(null)
const errorMessage = ref<string | null>(null)
const feedback = ref<Feedback | null>(null)
const applyingId = ref<string | null>(null)
const appliedIds = ref<Set<string>>(new Set())
const cardRef = ref<HTMLElement | null>(null)

const stageLabel = computed(() => phaseText.value || 'Scoring…')
const errorSuffix = computed(() => (errorMessage.value ? `: ${errorMessage.value}` : '.'))
const overallScoreLabel = computed(() => formatScore(feedback.value ? feedback.value.overall_score : null))
const atsScoreLabel = computed(() => formatScore(feedback.value ? feedback.value.ats_score : null))
const formatScore = (score: number | null | undefined) => (score === null || score === undefined ? '—' : String(score))

const applyLabel = (sugg: Suggestion) =>
  appliedIds.value.has(sugg.id) ? 'Applied ✓' : (applyingId.value === sugg.id ? 'Applying…' : 'Apply')

const scoreClass = (score: number | null | undefined) => {
  if (score === null || score === undefined) return 'rsm__score-badge--unknown'
  if (score >= 8) return 'rsm__score-badge--high'
  if (score >= 5) return 'rsm__score-badge--mid'
  return 'rsm__score-badge--low'
}

async function checkExisting() {
  const url = `/api/resumes/${props.resumeId}/score`
  const { data } = await useApiFetch<{ score: Feedback | null }>(url)
  if (data && data.score) {
    feedback.value = data.score
    state.value = 'done'
  }
}
let pollTimer: ReturnType<typeof setInterval> | null = null
function stopPolling() {
  if (pollTimer !== null) { clearInterval(pollTimer); pollTimer = null }
}

async function startScoring() {
  state.value = 'loading'
  errorMessage.value = null
  const url = `/api/resumes/${props.resumeId}/score`
  const POST = 'POST'
  const { error } = await useApiFetch(url, { method: POST })
  if (error) {
    state.value = 'error'
    return
  }
  stopPolling()
  pollTimer = setInterval(pollStatus, 3000)
  pollStatus()
}

async function pollStatus() {
  const url = `/api/resumes/${props.resumeId}/score/task`
  const { data } = await useApiFetch<{ status: string; stage: string | null; message: string | null }>(url)
  if (!data) return
  if (data.status === 'completed') {
    stopPolling()
    const url2 = `/api/resumes/${props.resumeId}/score`
    const { data: scoreData } = await useApiFetch<{ score: Feedback | null }>(url2)
    if (scoreData && scoreData.score) {
      feedback.value = scoreData.score
      state.value = 'done'
    } else {
      state.value = 'error'
      errorMessage.value = 'No result returned'
    }
  } else if (data.status === 'failed') {
    stopPolling()
    state.value = 'error'
    errorMessage.value = data.message
  } else {
    phaseText.value = data.stage
  }
}

async function applySuggestion(sugg: Suggestion) {
  applyingId.value = sugg.id
  const url = `/api/resumes/${props.resumeId}/score/apply-suggestion`
  const body = JSON.stringify({ suggestion: sugg })
  const jsonType = 'application/json'
  const ctKey = 'Content-Type'
  const headers: Record<string, string> = {}
  headers[ctKey] = jsonType
  const postMethod = 'POST'
  const opts = { method: postMethod, body, headers }
  const { error } = await useApiFetch(url, opts)
  applyingId.value = null
  if (!error) {
    appliedIds.value = new Set([...appliedIds.value, sugg.id])
    emit('applied')
  }
}

function close() {
  stopPolling()
  emit('close')
}

function trapFocus(e: KeyboardEvent) {
  if (e.key !== 'Tab' || !cardRef.value) return
  const focusable = cardRef.value.querySelectorAll<HTMLElement>(
    'button:not([disabled]), input, textarea, select, [tabindex]:not([tabindex="-1"])'
  )
  if (focusable.length === 0) return
  const first = focusable[0]
  const last = focusable[focusable.length - 1]
  if (e.shiftKey && document.activeElement === first) {
    e.preventDefault()
    last.focus()
  } else if (!e.shiftKey && document.activeElement === last) {
    e.preventDefault()
    first.focus()
  }
}

onMounted(async () => {
  document.addEventListener('keydown', trapFocus)
  await checkExisting()
  await nextTick()
  cardRef.value?.focus()
})
onBeforeUnmount(stopPolling)
onUnmounted(() => document.removeEventListener('keydown', trapFocus))
</script>

<style scoped>
.rsm-backdrop {
  position: fixed; inset: 0; background: rgba(0, 0, 0, 0.5);
  display: flex; align-items: center; justify-content: center; z-index: 1000;
  padding: var(--space-4, 1rem);
}
.rsm-card {
  background: var(--color-surface-raised, #f5f7fc); color: var(--color-text, #1a2338);
  border-radius: var(--radius-lg, 1rem); box-shadow: var(--shadow-lg, 0 10px 30px rgba(26, 35, 56, 0.12));
  max-width: 42rem; width: 100%;
  max-height: 90vh; overflow-y: auto; padding: var(--space-4, 1rem);
  outline: none;
}
.rsm__header { display: flex; justify-content: space-between; align-items: center; }
.rsm__title {
  font-size: var(--font-lg, 1.125rem); font-weight: 600; margin: 0;
  color: var(--color-text, #1a2338); font-family: var(--font-display, Georgia, serif);
}
.rsm__close {
  background: none; border: none; font-size: 1.25rem; cursor: pointer;
  color: var(--color-text-muted, #4a5c7a);
}
.rsm__close:hover { color: var(--color-text, #1a2338); }

.rsm__score-badge {
  display: inline-flex; align-items: baseline; gap: 0.15rem;
  padding: 0.5rem 1rem; border-radius: var(--radius-full, 9999px);
  font-weight: 700; font-size: 1.5rem;
  border: 2px solid var(--color-border, #a8b8d0);
}
.rsm__score-badge--high { border-color: var(--color-success, #3a7a32); color: var(--color-success, #3a7a32); }
.rsm__score-badge--mid  { border-color: var(--color-warning, #d4891a); color: var(--color-warning, #d4891a); }
.rsm__score-badge--low  { border-color: var(--color-error, #c0392b);  color: var(--color-error, #c0392b); }
.rsm__score-badge--unknown { border-color: var(--color-border, #a8b8d0); color: var(--color-text-muted, #4a5c7a); }
.rsm__score-badge--small { font-size: 1rem; padding: 0.25rem 0.6rem; }
.rsm__score-max { font-size: 0.85rem; font-weight: 400; opacity: 0.7; }

.rsm__columns { display: flex; gap: var(--space-4, 1rem); flex-wrap: wrap; }
.rsm__column { flex: 1 1 12rem; min-width: 0; }

.rsm__suggestion {
  border: 1px solid var(--color-border, #a8b8d0); border-radius: var(--radius-md, 0.5rem);
  padding: var(--space-3, 0.75rem); margin-bottom: var(--space-2, 0.5rem);
}
.rsm__before { opacity: 0.75; }
.rsm__ats-card {
  border-top: 1px solid var(--color-border, #a8b8d0); margin-top: var(--space-4, 1rem);
  padding-top: var(--space-3, 0.75rem);
}
.rsm__ats-basis { font-size: 0.85rem; color: var(--color-text-muted, #4a5c7a); font-style: italic; }

.btn-generate {
  display: inline-flex; align-items: center; gap: var(--space-2, 0.5rem);
  padding: var(--space-2, 0.5rem) var(--space-4, 1rem);
  background: var(--color-accent, #c4732a); color: var(--color-text-inverse, #fff);
  border: none; border-radius: var(--radius-md, 0.5rem);
  font-size: var(--text-sm, 0.875rem); font-weight: 600; cursor: pointer;
  transition: background var(--transition, 200ms ease);
}
.btn-generate:hover:not(:disabled) { background: var(--color-accent-hover, #a85c1f); }
.btn-generate:disabled { opacity: 0.6; cursor: not-allowed; }

.btn-secondary {
  display: inline-flex; align-items: center; gap: var(--space-2, 0.5rem);
  padding: var(--space-2, 0.5rem) var(--space-4, 1rem);
  background: var(--color-surface-alt, #dde4f0); color: var(--color-text, #1a2338);
  border: 1px solid var(--color-border, #a8b8d0); border-radius: var(--radius-md, 0.5rem);
  font-size: var(--text-sm, 0.875rem); font-weight: 600; cursor: pointer;
  transition: background var(--transition, 200ms ease);
}
.btn-secondary:hover:not(:disabled) { background: var(--color-surface, #eaeff8); }
.btn-secondary:disabled { opacity: 0.4; cursor: not-allowed; }

@media (max-width: 640px) {
  .rsm__columns { flex-direction: column; }
  .rsm-card { max-height: 100vh; border-radius: 0; }
  .rsm-backdrop { padding: 0; align-items: flex-end; }
}
</style>
