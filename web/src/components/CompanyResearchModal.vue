<template>
  <Teleport to="body">
    <div class="modal-backdrop" role="dialog" aria-modal="true" :aria-labelledby="`research-title-${jobId}`" @click.self="emit('close')">
      <div class="modal-card">
        <!-- Header -->
        <div class="modal-header">
          <h2 :id="`research-title-${jobId}`" class="modal-title">
            🔍 {{ jobTitle }} — Company Research
          </h2>
          <div class="modal-header-actions">
            <button v-if="state === 'ready'" class="btn-regen" @click="generate" title="Refresh research">↺ Refresh</button>
            <button class="btn-close" @click="emit('close')" aria-label="Close">✕</button>
          </div>
        </div>

        <!-- Generating state -->
        <div v-if="state === 'generating'" class="modal-body modal-body--loading">
          <div class="research-spinner" aria-hidden="true" />
          <p class="generating-msg">{{ stage ?? 'Researching…' }}</p>
          <p class="generating-sub">This takes 30–90 seconds depending on your LLM backend.</p>
        </div>

        <!-- Error state -->
        <div v-else-if="state === 'error'" class="modal-body modal-body--error">
          <p>Research generation failed.</p>
          <p v-if="errorMsg" class="error-detail">{{ errorMsg }}</p>
          <button class="btn-primary-sm" @click="generate">Retry</button>
        </div>

        <!-- Ready state -->
        <div v-else-if="state === 'ready' && brief" class="modal-body">
          <p v-if="brief.generated_at" class="generated-at">
            Updated {{ fmtDate(brief.generated_at) }}
          </p>

          <section v-if="brief.company_brief" class="research-section">
            <h3 class="section-title">🏢 Company</h3>
            <p class="section-body">{{ brief.company_brief }}</p>
          </section>

          <section v-if="brief.ceo_brief" class="research-section">
            <h3 class="section-title">👤 Leadership</h3>
            <p class="section-body">{{ brief.ceo_brief }}</p>
          </section>

          <section v-if="brief.talking_points" class="research-section">
            <div class="section-title-row">
              <h3 class="section-title">💬 Talking Points</h3>
              <button class="btn-copy" @click="copy(brief.talking_points!)" :aria-label="copied ? 'Copied!' : 'Copy talking points'">
                {{ copied ? '✓ Copied' : '⎘ Copy' }}
              </button>
            </div>
            <p class="section-body">{{ brief.talking_points }}</p>
          </section>

          <section v-if="brief.tech_brief" class="research-section">
            <h3 class="section-title">⚙️ Tech Stack</h3>
            <p class="section-body">{{ brief.tech_brief }}</p>
          </section>

          <section v-if="brief.funding_brief" class="research-section">
            <h3 class="section-title">💰 Funding & Stage</h3>
            <p class="section-body">{{ brief.funding_brief }}</p>
          </section>

          <section v-if="brief.red_flags" class="research-section research-section--warn">
            <h3 class="section-title">⚠️ Red Flags</h3>
            <p class="section-body">{{ brief.red_flags }}</p>
          </section>

          <section v-if="brief.accessibility_brief" class="research-section">
            <h3 class="section-title">♿ Inclusion & Accessibility</h3>
            <p class="section-body section-body--private">{{ brief.accessibility_brief }}</p>
            <p class="private-note">For your decision-making only — not disclosed in applications.</p>
          </section>
        </div>

        <!-- Empty state (no research, not generating) -->
        <div v-else class="modal-body modal-body--empty">
          <p>No research yet for this company.</p>
          <button class="btn-primary-sm" @click="generate">🔍 Generate Research</button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { useApiFetch } from '../composables/useApi'

const props = defineProps<{
  jobId: number
  jobTitle: string
  autoGenerate?: boolean
}>()

const emit = defineEmits<{ close: [] }>()

interface ResearchBrief {
  company_brief: string | null
  ceo_brief: string | null
  talking_points: string | null
  tech_brief: string | null
  funding_brief: string | null
  red_flags: string | null
  accessibility_brief: string | null
  generated_at: string | null
}

type ModalState = 'loading' | 'generating' | 'ready' | 'empty' | 'error'

const state    = ref<ModalState>('loading')
const brief    = ref<ResearchBrief | null>(null)
const stage    = ref<string | null>(null)
const errorMsg = ref<string | null>(null)
const copied   = ref(false)
let   pollId:  ReturnType<typeof setInterval> | null = null

function fmtDate(iso: string) {
  const d = new Date(iso)
  const diffH = Math.round((Date.now() - d.getTime()) / 3600000)
  if (diffH < 1)   return 'just now'
  if (diffH < 24)  return `${diffH}h ago`
  if (diffH < 168) return `${Math.floor(diffH / 24)}d ago`
  return d.toLocaleDateString([], { month: 'short', day: 'numeric' })
}

async function copy(text: string) {
  await navigator.clipboard.writeText(text)
  copied.value = true
  setTimeout(() => { copied.value = false }, 2000)
}

function stopPoll() {
  if (pollId) { clearInterval(pollId); pollId = null }
}

async function pollTask() {
  const { data } = await useApiFetch<{ status: string; stage: string | null; message: string | null }>(
    `/api/jobs/${props.jobId}/research/task`,
  )
  if (!data) return
  stage.value = data.stage

  if (data.status === 'completed') {
    stopPoll()
    await load()
  } else if (data.status === 'failed') {
    stopPoll()
    state.value = 'error'
    errorMsg.value = data.message ?? 'Unknown error'
  }
}

async function load() {
  const { data, error } = await useApiFetch<ResearchBrief>(`/api/jobs/${props.jobId}/research`)
  if (error) {
    if (error.kind === 'http' && error.status === 404) {
      // Check if a task is running
      const { data: task } = await useApiFetch<{ status: string; stage: string | null; message: string | null }>(
        `/api/jobs/${props.jobId}/research/task`,
      )
      if (task && (task.status === 'queued' || task.status === 'running')) {
        state.value = 'generating'
        stage.value = task.stage
        pollId = setInterval(pollTask, 3000)
      } else if (props.autoGenerate) {
        await generate()
      } else {
        state.value = 'empty'
      }
    } else {
      state.value = 'error'
      errorMsg.value = error.kind === 'http' ? error.detail : error.message
    }
    return
  }
  brief.value = data
  state.value = 'ready'
}

async function generate() {
  state.value = 'generating'
  stage.value = null
  errorMsg.value = null
  stopPoll()
  const { error } = await useApiFetch(`/api/jobs/${props.jobId}/research/generate`, { method: 'POST' })
  if (error) {
    state.value = 'error'
    errorMsg.value = error.kind === 'http' ? error.detail : error.message
    return
  }
  pollId = setInterval(pollTask, 3000)
}

function onEsc(e: KeyboardEvent) {
  if (e.key === 'Escape') emit('close')
}

onMounted(async () => {
  document.addEventListener('keydown', onEsc)
  await load()
})

onUnmounted(() => {
  document.removeEventListener('keydown', onEsc)
  stopPoll()
})
</script>

<style scoped>
.modal-backdrop {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.55);
  z-index: 500;
  display: flex;
  align-items: flex-start;
  justify-content: center;
  padding: var(--space-8) var(--space-4);
  overflow-y: auto;
}

.modal-card {
  background: var(--color-surface-raised);
  border-radius: var(--radius-lg);
  box-shadow: 0 8px 40px rgba(0, 0, 0, 0.3);
  width: 100%;
  max-width: 620px;
  overflow: hidden;
}

.modal-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--space-3);
  padding: var(--space-5) var(--space-6);
  border-bottom: 1px solid var(--color-border-light);
}

.modal-title {
  font-size: 1rem;
  font-weight: 700;
  color: var(--color-text);
  margin: 0;
  line-height: 1.3;
}

.modal-header-actions {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  flex-shrink: 0;
}

.btn-close {
  background: none;
  border: none;
  cursor: pointer;
  font-size: 1rem;
  color: var(--color-text-muted);
  padding: 2px 6px;
}

.btn-regen {
  background: none;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  cursor: pointer;
  font-size: 0.78rem;
  color: var(--color-text-muted);
  padding: 2px 8px;
}

.modal-body {
  padding: var(--space-6);
  display: flex;
  flex-direction: column;
  gap: var(--space-5);
  max-height: 70vh;
  overflow-y: auto;
}

.modal-body--loading {
  align-items: center;
  text-align: center;
  padding: var(--space-10) var(--space-6);
  gap: var(--space-4);
}

.modal-body--empty {
  align-items: center;
  text-align: center;
  padding: var(--space-10) var(--space-6);
  gap: var(--space-4);
  color: var(--color-text-muted);
}

.modal-body--error {
  align-items: center;
  text-align: center;
  padding: var(--space-8) var(--space-6);
  gap: var(--space-3);
  color: var(--color-error);
}

.error-detail {
  font-size: 0.8rem;
  opacity: 0.8;
}

.research-spinner {
  width: 36px;
  height: 36px;
  border: 3px solid var(--color-border);
  border-top-color: var(--color-primary);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin { to { transform: rotate(360deg); } }

.generating-msg {
  font-weight: 600;
  color: var(--color-text);
}

.generating-sub {
  font-size: 0.8rem;
  color: var(--color-text-muted);
}

.generated-at {
  font-size: 0.75rem;
  color: var(--color-text-muted);
  margin-bottom: calc(-1 * var(--space-2));
}

.research-section {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  padding-bottom: var(--space-4);
  border-bottom: 1px solid var(--color-border-light);
}

.research-section:last-child {
  border-bottom: none;
  padding-bottom: 0;
}

.research-section--warn .section-title {
  color: var(--color-warning);
}

.section-title-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.section-title {
  font-size: 0.8rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--color-text-muted);
  margin: 0;
}

.section-body {
  font-size: 0.875rem;
  color: var(--color-text);
  line-height: 1.6;
  white-space: pre-wrap;
}

.section-body--private {
  font-style: italic;
}

.private-note {
  font-size: 0.7rem;
  color: var(--color-text-muted);
}

.btn-copy {
  background: none;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  cursor: pointer;
  font-size: 0.72rem;
  color: var(--color-text-muted);
  padding: 2px 8px;
  transition: color 150ms, border-color 150ms;
}

.btn-copy:hover { color: var(--color-primary); border-color: var(--color-primary); }

.btn-primary-sm {
  background: var(--color-primary);
  color: #fff;
  border: none;
  border-radius: var(--radius-md);
  padding: var(--space-2) var(--space-5);
  font-size: 0.875rem;
  font-weight: 600;
  cursor: pointer;
}
</style>
