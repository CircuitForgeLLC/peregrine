<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { useInterviewsStore } from '../stores/interviews'
import type { PipelineJob, PipelineStage } from '../stores/interviews'
import type { StageSignal } from '../stores/interviews'
import { useApiFetch } from '../composables/useApi'
import InterviewCard from '../components/InterviewCard.vue'
import MoveToSheet from '../components/MoveToSheet.vue'

const router = useRouter()
const store  = useInterviewsStore()

// ── Move sheet ────────────────────────────────────────────────────────────────
const moveTarget      = ref<PipelineJob | null>(null)
const movePreSelected = ref<PipelineStage | undefined>(undefined)

function openMove(jobId: number, preSelectedStage?: PipelineStage) {
  moveTarget.value      = store.jobs.find(j => j.id === jobId) ?? null
  movePreSelected.value = preSelectedStage
}

async function onMove(stage: PipelineStage, opts: { interview_date?: string; rejection_stage?: string }) {
  if (!moveTarget.value) return
  const wasHired = stage === 'hired'
  await store.move(moveTarget.value.id, stage, opts)
  moveTarget.value = null
  if (wasHired) triggerConfetti()
}

// ── Collapsible Applied section ────────────────────────────────────────────
const APPLIED_EXPANDED_KEY = 'peregrine.interviews.appliedExpanded'
const appliedExpanded = ref(localStorage.getItem(APPLIED_EXPANDED_KEY) === 'true')
watch(appliedExpanded, v => localStorage.setItem(APPLIED_EXPANDED_KEY, String(v)))

const APPLIED_PAGE_SIZE = 10

const appliedPage = ref(0)
const allApplied  = computed(() => [...store.applied, ...store.survey])
const appliedPageCount = computed(() => Math.ceil(allApplied.value.length / APPLIED_PAGE_SIZE))
const pagedApplied = computed(() =>
  allApplied.value.slice(
    appliedPage.value * APPLIED_PAGE_SIZE,
    (appliedPage.value + 1) * APPLIED_PAGE_SIZE,
  )
)

// Clamp page when the list shrinks (e.g. after a move)
watch(allApplied, () => {
  if (appliedPage.value >= appliedPageCount.value) appliedPage.value = 0
})

const appliedSignalCount = computed(() =>
  [...store.applied, ...store.survey]
    .reduce((n, job) => n + (job.stage_signals?.length ?? 0), 0)
)

// ── Signal metadata (pre-list rows) ───────────────────────────────────────
const SIGNAL_META_PRE = {
  interview_scheduled: { label: 'Move to Phone Screen', stage: 'phone_screen'       as PipelineStage, color: 'amber' },
  positive_response:   { label: 'Move to Phone Screen', stage: 'phone_screen'       as PipelineStage, color: 'amber' },
  offer_received:      { label: 'Move to Offer',        stage: 'offer'              as PipelineStage, color: 'green' },
  survey_received:     { label: 'Move to Survey',       stage: 'survey'             as PipelineStage, color: 'amber' },
  rejected:            { label: 'Mark Rejected',        stage: 'interview_rejected' as PipelineStage, color: 'red'   },
} as const

const sigExpandedIds = ref(new Set<number>())
// IMPORTANT: must reassign .value (not mutate in place) to trigger Vue reactivity
function togglePreSigExpand(jobId: number) {
  const next = new Set(sigExpandedIds.value)
  if (next.has(jobId)) next.delete(jobId)
  else next.add(jobId)
  sigExpandedIds.value = next
}

async function dismissPreSignal(job: PipelineJob, sig: StageSignal) {
  const idx = job.stage_signals.findIndex(s => s.id === sig.id)
  if (idx !== -1) job.stage_signals.splice(idx, 1)
  await useApiFetch(`/api/stage-signals/${sig.id}/dismiss`, { method: 'POST' })
}

const bodyExpandedMap = ref<Record<number, boolean>>({})

function toggleBodyExpand(sigId: number) {
  bodyExpandedMap.value = { ...bodyExpandedMap.value, [sigId]: !bodyExpandedMap.value[sigId] }
}

const PRE_RECLASSIFY_CHIPS = [
  { label: '🟡 Interview', value: 'interview_scheduled' as const },
  { label: '✅ Positive',  value: 'positive_response'   as const },
  { label: '🟢 Offer',     value: 'offer_received'      as const },
  { label: '📋 Survey',    value: 'survey_received'     as const },
  { label: '✖ Rejected',   value: 'rejected'            as const },
  { label: '🚫 Unrelated', value: 'unrelated'           },
  { label: '📰 Digest',    value: 'digest'              },
  { label: '— Neutral',    value: 'neutral'             },
] as const

const DISMISS_LABELS = new Set(['neutral', 'unrelated', 'digest'] as const)

async function reclassifyPreSignal(job: PipelineJob, sig: StageSignal, newLabel: StageSignal['stage_signal'] | 'neutral' | 'unrelated' | 'digest') {
  if (DISMISS_LABELS.has(newLabel)) {
    const idx = job.stage_signals.findIndex(s => s.id === sig.id)
    if (idx !== -1) job.stage_signals.splice(idx, 1)
    await useApiFetch(`/api/stage-signals/${sig.id}/reclassify`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ stage_signal: newLabel }),
    })
    await useApiFetch(`/api/stage-signals/${sig.id}/dismiss`, { method: 'POST' })
    // Digest-only: add to browsable queue (fire-and-forget; sig.id === job_contacts.id)
    if (newLabel === 'digest') {
      void useApiFetch('/api/digest-queue', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ job_contact_id: sig.id }),
      })
    }
  } else {
    const prev = sig.stage_signal
    sig.stage_signal = newLabel
    const { error } = await useApiFetch(`/api/stage-signals/${sig.id}/reclassify`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ stage_signal: newLabel }),
    })
    if (error) sig.stage_signal = prev
  }
}

// ── Email sync status ──────────────────────────────────────────────────────
interface SyncStatus {
  state: 'idle' | 'queued' | 'running' | 'completed' | 'failed' | 'not_configured'
  lastCompletedAt: string | null
  error: string | null
}

const syncStatus = ref<SyncStatus>({ state: 'idle', lastCompletedAt: null, error: null })
const now        = ref(Date.now())
let   syncPollId: ReturnType<typeof setInterval> | null = null
let   nowTickId:  ReturnType<typeof setInterval> | null = null

function elapsedLabel(isoTs: string | null): string {
  if (!isoTs) return ''
  const diffMs = now.value - new Date(isoTs).getTime()
  const mins   = Math.floor(diffMs / 60000)
  if (mins < 1)   return 'just now'
  if (mins < 60)  return `${mins}m ago`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24)   return `${hrs}h ago`
  return `${Math.floor(hrs / 24)}d ago`
}

async function fetchSyncStatus() {
  const { data } = await useApiFetch<{
    status: string; last_completed_at: string | null; error: string | null
  }>('/api/email/sync/status')
  if (!data) return
  syncStatus.value = {
    state:           data.status as SyncStatus['state'],
    lastCompletedAt: data.last_completed_at,
    error:           data.error,
  }
}

function startSyncPoll() {
  if (syncPollId) return
  syncPollId = setInterval(async () => {
    await fetchSyncStatus()
    if (syncStatus.value.state === 'completed' || syncStatus.value.state === 'failed') {
      clearInterval(syncPollId!); syncPollId = null
      if (syncStatus.value.state === 'completed') store.fetchAll()
    }
  }, 3000)
}

async function triggerSync() {
  if (syncStatus.value.state === 'queued' || syncStatus.value.state === 'running') return
  const { data, error } = await useApiFetch<{ task_id: number }>('/api/email/sync', { method: 'POST' })
  if (error) {
    if (error.kind === 'http' && error.status === 503) {
      // Email integration not configured — set permanently for this session
      syncStatus.value = { state: 'not_configured', lastCompletedAt: null, error: null }
    } else {
      // Transient error (network, server 5xx etc.) — show failed but allow retry
      syncStatus.value = { ...syncStatus.value, state: 'failed', error: error.kind === 'http' ? error.detail : error.message }
    }
    return
  }
  if (data) {
    syncStatus.value = { ...syncStatus.value, state: 'queued' }
    startSyncPoll()
  }
}

// ── Confetti (easter egg 9.5) ─────────────────────────────────────────────────
const showHiredToast = ref(false)
const confettiCanvas = ref<HTMLCanvasElement | null>(null)

function triggerConfetti() {
  const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches
  if (reducedMotion) {
    showHiredToast.value = true
    setTimeout(() => { showHiredToast.value = false }, 6000)
    return
  }
  const canvas = confettiCanvas.value
  if (!canvas) return
  canvas.width  = window.innerWidth
  canvas.height = window.innerHeight
  canvas.style.display = 'block'
  const ctx = canvas.getContext('2d')!
  const COLORS = ['#c4732a','#1a7a6e','#3b82f6','#f5c518','#e84393','#6ab870']
  const particles = Array.from({ length: 120 }, (_, i) => ({
    x: Math.random() * canvas.width,
    y: -10 - Math.random() * 200,
    r: 4 + Math.random() * 6,
    color: COLORS[i % COLORS.length],
    vx: (Math.random() - 0.5) * 4,
    vy: 3 + Math.random() * 4,
    angle: Math.random() * 360,
    spin: (Math.random() - 0.5) * 8,
  }))
  let frame = 0
  function draw() {
    ctx.clearRect(0, 0, canvas!.width, canvas!.height)
    particles.forEach(p => {
      p.x += p.vx; p.y += p.vy; p.vy += 0.08; p.angle += p.spin
      ctx.save()
      ctx.translate(p.x, p.y)
      ctx.rotate((p.angle * Math.PI) / 180)
      ctx.fillStyle = p.color
      ctx.fillRect(-p.r / 2, -p.r / 2, p.r, p.r * 1.6)
      ctx.restore()
    })
    frame++
    if (frame < 240) requestAnimationFrame(draw)
    else canvas!.style.display = 'none'
  }
  draw()
}

// ── Keyboard navigation ───────────────────────────────────────────────────────
const focusedCol  = ref(0)
const focusedCard = ref(0)

const columns = [
  { jobs: () => store.phoneScreen  },
  { jobs: () => store.interviewing },
  { jobs: () => store.offerHired   },
]

function onKeydown(e: KeyboardEvent) {
  if (moveTarget.value) return
  const colJobs = columns[focusedCol.value].jobs()

  if (e.key === 'ArrowUp' || e.key === 'k' || e.key === 'K') {
    e.preventDefault(); focusedCard.value = Math.max(0, focusedCard.value - 1)
  } else if (e.key === 'ArrowDown' || e.key === 'j' || e.key === 'J') {
    e.preventDefault(); focusedCard.value = Math.min(colJobs.length - 1, focusedCard.value + 1)
  } else if (e.key === 'ArrowLeft' || e.key === '[' || e.key === '4') {
    e.preventDefault(); focusedCol.value = Math.max(0, focusedCol.value - 1); focusedCard.value = 0
  } else if (e.key === 'ArrowRight' || e.key === ']' || e.key === '6') {
    e.preventDefault(); focusedCol.value = Math.min(columns.length - 1, focusedCol.value + 1); focusedCard.value = 0
  } else if (e.key === 'm' || e.key === 'M') {
    const job = colJobs[focusedCard.value]; if (job) openMove(job.id)
  } else if (e.key === 'Enter' || e.key === ' ') {
    const job = colJobs[focusedCard.value]; if (job) router.push(`/prep/${job.id}`)
  }
}

onMounted(async () => {
  await store.fetchAll()
  document.addEventListener('keydown', onKeydown)
  await fetchSyncStatus()
  if (syncStatus.value.state === 'queued' || syncStatus.value.state === 'running') {
    startSyncPoll()
  }
  nowTickId = setInterval(() => { now.value = Date.now() }, 60000)
})

onUnmounted(() => {
  document.removeEventListener('keydown', onKeydown)
  if (syncPollId) { clearInterval(syncPollId); syncPollId = null }
  if (nowTickId)  { clearInterval(nowTickId);  nowTickId  = null }
})

function daysSince(dateStr: string | null) {
  if (!dateStr) return null
  return Math.floor((Date.now() - new Date(dateStr).getTime()) / 86400000)
}
</script>

<template>
  <div class="interviews-view">
    <canvas ref="confettiCanvas" class="confetti-canvas" aria-hidden="true" />

    <Transition name="toast">
      <div v-if="showHiredToast" class="hired-toast" role="alert">
        🎉 Congratulations! You got the job!
      </div>
    </Transition>

    <header class="view-header">
      <h1 class="view-title">Interviews</h1>
      <div class="header-actions">
        <!-- Email sync pill -->
        <button
          v-if="syncStatus.state === 'not_configured'"
          class="sync-pill sync-pill--muted"
          disabled
          aria-label="Email not configured"
        >📧 Email not configured</button>
        <button
          v-else-if="syncStatus.state === 'queued' || syncStatus.state === 'running'"
          class="sync-pill sync-pill--syncing"
          disabled
          aria-label="Syncing emails"
        >⏳ Syncing…</button>
        <button
          v-else-if="(syncStatus.state === 'completed' || syncStatus.state === 'idle') && syncStatus.lastCompletedAt"
          class="sync-pill sync-pill--synced"
          @click="triggerSync"
          :aria-label="`Email synced ${elapsedLabel(syncStatus.lastCompletedAt)} — click to re-sync`"
        >📧 Synced {{ elapsedLabel(syncStatus.lastCompletedAt) }}</button>
        <button
          v-else-if="syncStatus.state === 'failed'"
          class="sync-pill sync-pill--failed"
          @click="triggerSync"
          aria-label="Sync failed — click to retry"
        >⚠ Sync failed</button>
        <button
          v-else
          class="sync-pill sync-pill--idle"
          @click="triggerSync"
          aria-label="Sync emails"
        >📧 Sync Emails</button>

        <button class="btn-refresh" @click="store.fetchAll()" :disabled="store.loading" aria-label="Refresh">
          {{ store.loading ? '⟳' : '↺' }}
        </button>
      </div>
    </header>

    <div v-if="store.error" class="error-banner">{{ store.error }}</div>

    <!-- Pre-list: Applied + Survey (collapsible) -->
    <section class="pre-list" aria-label="Applied jobs">
      <button
        class="pre-list-toggle"
        @click="appliedExpanded = !appliedExpanded"
        :aria-expanded="appliedExpanded"
        aria-controls="pre-list-body"
      >
        <span class="pre-list-chevron" :class="{ 'is-expanded': appliedExpanded }">▶</span>
        <span class="pre-list-toggle-title">
          Applied
          <span class="pre-list-count">{{ store.applied.length + store.survey.length }}</span>
        </span>
        <span v-if="appliedSignalCount > 0" class="pre-list-signal-count">⚡ {{ appliedSignalCount }} signal{{ appliedSignalCount !== 1 ? 's' : '' }}</span>
      </button>

      <div
        id="pre-list-body"
        class="pre-list-body"
        :class="{ 'is-expanded': appliedExpanded }"
      >
        <div v-if="store.applied.length === 0 && store.survey.length === 0" class="pre-list-empty">
          <span class="empty-bird">🦅</span>
          <span>No applied jobs yet. <RouterLink to="/apply">Go to Apply</RouterLink> to submit applications.</span>
        </div>
        <template v-for="job in pagedApplied" :key="job.id">
          <div class="pre-list-row">
            <div class="pre-row-info">
              <span class="pre-row-title">{{ job.title }}</span>
              <span class="pre-row-company">{{ job.company }}</span>
              <span v-if="job.status === 'survey'" class="survey-badge">Survey</span>
            </div>
            <div class="pre-row-meta">
              <span v-if="daysSince(job.applied_at) !== null" class="pre-row-days">{{ daysSince(job.applied_at) }}d ago</span>
              <button class="btn-move-pre" @click="openMove(job.id)" :aria-label="`Move ${job.title}`">Move to… ›</button>
              <button
                v-if="job.status === 'survey'"
                class="btn-move-pre"
                @click="router.push('/survey/' + job.id)"
              >Survey →</button>
            </div>
          </div>
          <!-- Signal banners for pre-list rows -->
          <template v-if="job.stage_signals?.length">
            <div
              v-for="sig in (job.stage_signals ?? []).slice(0, sigExpandedIds.has(job.id) ? undefined : 1)"
              :key="sig.id"
              class="pre-signal-banner"
              :data-color="SIGNAL_META_PRE[sig.stage_signal]?.color"
            >
              <div class="signal-header">
                <span class="signal-label">📧 <strong>{{ SIGNAL_META_PRE[sig.stage_signal]?.label?.replace('Move to ', '') ?? sig.stage_signal }}</strong></span>
                <span class="signal-subject">{{ sig.subject.slice(0, 60) }}{{ sig.subject.length > 60 ? '…' : '' }}</span>
                <div class="signal-header-actions">
                  <button class="btn-signal-read" @click.stop="toggleBodyExpand(sig.id)"
                    :aria-expanded="bodyExpandedMap[sig.id] ?? false"
                    :aria-label="(bodyExpandedMap[sig.id] ? 'Hide' : 'Read') + ' email body'">
                    {{ bodyExpandedMap[sig.id] ? '▾ Hide' : '▸ Read' }}
                  </button>
                  <button
                    class="btn-signal-move"
                    @click.stop="openMove(job.id, SIGNAL_META_PRE[sig.stage_signal]?.stage)"
                    :aria-label="`Move ${job.title} — ${SIGNAL_META_PRE[sig.stage_signal]?.label ?? 'Move'}`"
                  >→ Move</button>
                  <button class="btn-signal-dismiss" @click.stop="dismissPreSignal(job, sig)" aria-label="Dismiss signal">✕</button>
                </div>
              </div>
              <!-- Expanded body + reclassify chips -->
              <div v-if="bodyExpandedMap[sig.id]" class="signal-body-expanded">
                <div v-if="sig.from_addr" class="signal-from">From: {{ sig.from_addr }}</div>
                <div v-if="sig.body" class="signal-body-text">{{ sig.body }}</div>
                <div v-else class="signal-body-empty">No email body available.</div>
                <div class="signal-reclassify">
                  <span class="signal-reclassify-label">Re-classify:</span>
                  <button
                    v-for="chip in PRE_RECLASSIFY_CHIPS"
                    :key="chip.value"
                    class="btn-chip"
                    :class="{ 'btn-chip-active': sig.stage_signal === chip.value }"
                    @click.stop="reclassifyPreSignal(job, sig, chip.value)"
                  >{{ chip.label }}</button>
                </div>
              </div>
            </div>
            <button
              v-if="(job.stage_signals?.length ?? 0) > 1"
              class="btn-sig-expand"
              @click="togglePreSigExpand(job.id)"
            >{{ sigExpandedIds.has(job.id) ? '− less' : `+${(job.stage_signals?.length ?? 1) - 1} more` }}</button>
          </template>
        </template>
        <!-- Pagination -->
        <div v-if="appliedPageCount > 1" class="pre-list-pagination">
          <button
            class="btn-page"
            :disabled="appliedPage === 0"
            @click="appliedPage--"
            aria-label="Previous page"
          >‹</button>
          <span class="page-indicator">{{ appliedPage + 1 }} / {{ appliedPageCount }}</span>
          <button
            class="btn-page"
            :disabled="appliedPage >= appliedPageCount - 1"
            @click="appliedPage++"
            aria-label="Next page"
          >›</button>
        </div>
      </div>
    </section>

    <!-- Kanban columns -->
    <section class="kanban" aria-label="Interview pipeline">
      <div class="kanban-col" :class="{ 'kanban-col--focused': focusedCol === 0 }" aria-label="Phone Screen">
        <div class="col-header" style="color: var(--status-phone)">
          📞 Phone Screen <span class="col-count">{{ store.phoneScreen.length }}</span>
        </div>
        <div v-if="store.phoneScreen.length === 0" class="col-empty">
          <div class="empty-bird-wrap"><span class="empty-bird-float">🦅</span></div>
          <p class="empty-msg">No phone screens yet.<br>Move an applied job here when a recruiter reaches out.</p>
        </div>
        <InterviewCard v-for="(job, i) in store.phoneScreen" :key="job.id" :job="job"
          :focused="focusedCol === 0 && focusedCard === i"
          @move="openMove" @prep="router.push(`/prep/${$event}`)" @survey="router.push('/survey/' + $event)" />
      </div>

      <div class="kanban-col" :class="{ 'kanban-col--focused': focusedCol === 1 }" aria-label="Interviewing">
        <div class="col-header" style="color: var(--color-info)">
          🎯 Interviewing <span class="col-count">{{ store.interviewing.length }}</span>
        </div>
        <div v-if="store.interviewing.length === 0" class="col-empty">
          <div class="empty-bird-wrap"><span class="empty-bird-float">🦅</span></div>
          <p class="empty-msg">Phone screen going well?<br>Move it here when you've got a real interview scheduled.</p>
        </div>
        <InterviewCard v-for="(job, i) in store.interviewing" :key="job.id" :job="job"
          :focused="focusedCol === 1 && focusedCard === i"
          @move="openMove" @prep="router.push(`/prep/${$event}`)" @survey="router.push('/survey/' + $event)" />
      </div>

      <div class="kanban-col" :class="{ 'kanban-col--focused': focusedCol === 2 }" aria-label="Offer and Hired">
        <div class="col-header" style="color: var(--status-offer)">
          📜 Offer / Hired <span class="col-count">{{ store.offerHired.length }}</span>
        </div>
        <div v-if="store.offerHired.length === 0" class="col-empty">
          <div class="empty-bird-wrap"><span class="empty-bird-float">🦅</span></div>
          <p class="empty-msg">This is where offers land.<br>You've got this. 🙌</p>
        </div>
        <InterviewCard v-for="(job, i) in store.offerHired" :key="job.id" :job="job"
          :focused="focusedCol === 2 && focusedCard === i"
          @move="openMove" @prep="router.push(`/prep/${$event}`)" @survey="router.push('/survey/' + $event)" />
      </div>
    </section>

    <!-- Rejected accordion -->
    <details class="rejected-accordion" v-if="store.rejected.length > 0">
      <summary class="rejected-summary">
        ✗ Rejected ({{ store.rejected.length }})
        <span class="rejected-hint">— expand for details</span>
      </summary>
      <div class="rejected-body">
        <div class="rejected-stats">
          <div class="stat-chip">
            <span class="stat-num">{{ store.rejected.length }}</span>
            <span class="stat-lbl">Total</span>
          </div>
        </div>
        <div v-for="job in store.rejected" :key="job.id" class="rejected-row">
          <span class="rejected-title">{{ job.title }} — {{ job.company }}</span>
          <span class="rejected-stage">{{ job.rejection_stage ?? 'No response' }}</span>
          <button class="btn-unrej" @click="openMove(job.id)">Move →</button>
        </div>
      </div>
    </details>

    <MoveToSheet
      v-if="moveTarget"
      :currentStatus="moveTarget.status"
      :jobTitle="`${moveTarget.title} at ${moveTarget.company}`"
      :preSelectedStage="movePreSelected"
      @move="onMove"
      @close="moveTarget = null; movePreSelected = undefined"
    />
  </div>
</template>

<style scoped>
.interviews-view {
  padding: var(--space-4) var(--space-4) var(--space-12);
  max-width: 1100px; margin: 0 auto; position: relative;
}
.confetti-canvas { position: fixed; inset: 0; z-index: 300; pointer-events: none; display: none; }
.hired-toast {
  position: fixed; bottom: var(--space-8); left: 50%; transform: translateX(-50%);
  background: var(--color-success); color: #fff;
  padding: var(--space-3) var(--space-6); border-radius: 12px;
  font-weight: 700; font-size: 1.1rem; z-index: 400;
  box-shadow: 0 4px 20px rgba(0,0,0,.2);
}
.toast-enter-active, .toast-leave-active { transition: all 400ms ease; }
.toast-enter-from, .toast-leave-to { opacity: 0; transform: translateX(-50%) translateY(20px); }
.view-header  { display: flex; align-items: center; gap: var(--space-3); margin-bottom: var(--space-6); }
.view-title   { font-size: 1.5rem; font-weight: 700; margin: 0; }
.btn-refresh  { background: none; border: 1px solid var(--color-border); border-radius: 6px; cursor: pointer; padding: 4px 10px; font-size: 1rem; color: var(--color-text-muted); }
.error-banner { background: color-mix(in srgb, var(--color-error) 10%, var(--color-surface)); color: var(--color-error); padding: var(--space-2) var(--space-3); border-radius: 8px; margin-bottom: var(--space-4); }

/* Header actions */
.header-actions { display: flex; align-items: center; gap: var(--space-2); margin-left: auto; }

/* Email sync pill */
.sync-pill {
  border-radius: 999px; padding: 3px 10px; font-size: 0.78em; font-weight: 600; cursor: pointer;
  border: 1px solid transparent; transition: opacity 150ms;
}
.sync-pill:disabled { cursor: default; opacity: 0.8; }
.sync-pill--idle   { border-color: var(--color-border); background: none; color: var(--color-text-muted); }
.sync-pill--syncing { background: color-mix(in srgb, var(--color-info) 10%, var(--color-surface)); color: var(--color-info); border-color: color-mix(in srgb, var(--color-info) 30%, transparent); animation: pulse 1.5s ease-in-out infinite; }
.sync-pill--synced  { background: color-mix(in srgb, var(--color-success) 12%, var(--color-surface)); color: var(--color-success); border-color: color-mix(in srgb, var(--color-success) 30%, transparent); }
.sync-pill--failed  { background: color-mix(in srgb, var(--color-error) 10%, var(--color-surface)); color: var(--color-error); border-color: color-mix(in srgb, var(--color-error) 30%, transparent); }
.sync-pill--muted   { background: var(--color-surface-alt); color: var(--color-text-muted); border-color: var(--color-border-light); }
@keyframes pulse { 0%,100%{opacity:1} 50%{opacity:0.55} }

/* Collapsible pre-list toggle header */
.pre-list-toggle {
  display: flex; align-items: center; gap: var(--space-2); width: 100%;
  background: none; border: none; cursor: pointer; padding: var(--space-1) 0;
  font-size: 0.9rem; font-weight: 700; color: var(--color-text);
  text-align: left;
}
.pre-list-chevron { font-size: 0.7em; color: var(--color-text-muted); transition: transform 200ms; display: inline-block; }
.pre-list-chevron.is-expanded { transform: rotate(90deg); }
.pre-list-count {
  display: inline-block; background: var(--color-surface-raised); border-radius: 999px;
  padding: 1px 8px; font-size: 0.75em; font-weight: 700; margin-left: var(--space-1);
  color: var(--color-text-muted);
}
.pre-list-signal-count { margin-left: auto; font-size: 0.75em; font-weight: 700; color: #e67e22; }

/* Collapsible pre-list body */
.pre-list-body {
  max-height: 0;
  overflow: hidden;
  transition: max-height 300ms ease;
}
.pre-list-body.is-expanded { max-height: 800px; }
@media (prefers-reduced-motion: reduce) {
  .pre-list-body, .pre-list-chevron { transition: none; }
}

.pre-list         { background: var(--color-surface); border-radius: 10px; padding: var(--space-3) var(--space-4); margin-bottom: var(--space-6); }
.pre-list-toggle-title { display: flex; align-items: center; }
.pre-list-empty   { display: flex; align-items: center; gap: var(--space-2); font-size: 0.85rem; color: var(--color-text-muted); padding: var(--space-2) 0; }
.pre-list-row     { display: flex; align-items: center; justify-content: space-between; padding: var(--space-2) 0; border-top: 1px solid var(--color-border-light); gap: var(--space-3); }
.pre-row-info     { display: flex; align-items: center; gap: var(--space-2); flex: 1; min-width: 0; }
.pre-row-title    { font-weight: 600; font-size: 0.875rem; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.pre-row-company  { color: var(--color-text-muted); font-size: 0.8rem; white-space: nowrap; }
.survey-badge     { background: color-mix(in srgb, var(--status-phone) 12%, var(--color-surface-raised)); color: var(--status-phone); border-radius: 99px; padding: 1px 7px; font-size: 0.7rem; font-weight: 700; }
.pre-row-meta     { display: flex; align-items: center; gap: var(--space-2); flex-shrink: 0; }
.pre-row-days     { font-size: 0.75rem; color: var(--color-text-muted); }
.btn-move-pre     { background: none; border: 1px solid var(--color-border); border-radius: 6px; padding: 2px 8px; font-size: 0.75rem; font-weight: 700; color: var(--color-info); cursor: pointer; }

/* Pre-list signal banners */
.pre-signal-banner {
  padding: 8px 12px; border-radius: 6px; margin: 4px 0;
  border-top: 1px solid transparent;
  display: flex; flex-direction: column; gap: 4px;
}
.pre-signal-banner[data-color="amber"] { background: rgba(245,158,11,0.08); border-top-color: rgba(245,158,11,0.4); }
.pre-signal-banner[data-color="green"] { background: rgba(39,174,96,0.08);  border-top-color: rgba(39,174,96,0.4);  }
.pre-signal-banner[data-color="red"]   { background: rgba(192,57,43,0.08);  border-top-color: rgba(192,57,43,0.4);  }

.signal-label   { font-size: 0.82em; }
.signal-subject { font-size: 0.78em; color: var(--color-text-muted); }
.signal-actions { display: flex; gap: 6px; align-items: center; }
.btn-signal-move {
  background: var(--color-primary); color: #fff;
  border: none; border-radius: 4px; padding: 2px 8px; font-size: 0.78em; cursor: pointer;
}
.btn-signal-dismiss {
  background: none; border: none; color: var(--color-text-muted); font-size: 0.85em; cursor: pointer;
  padding: 2px 4px;
}
.btn-signal-read {
  background: none; border: none; color: var(--color-text-muted); font-size: 0.82em;
  cursor: pointer; padding: 2px 6px; white-space: nowrap;
}
.signal-header {
  display: flex; align-items: center; gap: 8px; flex-wrap: wrap;
}
.signal-header-actions {
  margin-left: auto; display: flex; gap: 6px; align-items: center;
}
.signal-body-expanded {
  margin-top: 8px; font-size: 0.8em; border-top: 1px dashed var(--color-border);
  padding-top: 8px;
}
.signal-from {
  color: var(--color-text-muted); margin-bottom: 4px;
}
.signal-body-text {
  white-space: pre-wrap; color: var(--color-text); line-height: 1.5;
  max-height: 200px; overflow-y: auto;
}
.signal-body-empty {
  color: var(--color-text-muted); font-style: italic;
}
.signal-reclassify {
  display: flex; gap: 6px; flex-wrap: wrap; align-items: center; margin-top: 8px;
}
.signal-reclassify-label {
  font-size: 0.75em; color: var(--color-text-muted);
}
.btn-chip {
  background: var(--color-surface); color: var(--color-text-muted);
  border: 1px solid var(--color-border); border-radius: 4px;
  padding: 2px 7px; font-size: 0.75em; cursor: pointer;
}
.btn-chip:hover {
  background: var(--color-hover);
}
.btn-chip-active {
  background: var(--color-primary-muted, #e8f0ff);
  color: var(--color-primary); border-color: var(--color-primary);
  font-weight: 600;
}
.btn-sig-expand {
  background: none; border: none; font-size: 0.75em; color: var(--color-info); cursor: pointer;
  padding: 4px 12px; text-align: left;
}

.kanban {
  display: grid; grid-template-columns: repeat(3, 1fr);
  gap: var(--space-4); margin-bottom: var(--space-6);
}
@media (max-width: 720px) { .kanban { grid-template-columns: 1fr; } }
.kanban-col {
  background: var(--color-surface); border-radius: 10px;
  padding: var(--space-3); display: flex; flex-direction: column; gap: var(--space-3);
  transition: box-shadow 150ms;
}
.kanban-col--focused { box-shadow: 0 0 0 2px var(--color-primary); }
.col-header {
  font-size: 0.8rem; font-weight: 700; text-transform: uppercase;
  letter-spacing: .05em; display: flex; align-items: center; justify-content: space-between;
}
.col-count { background: rgba(0,0,0,.08); border-radius: 99px; padding: 1px 8px; font-size: 0.75rem; font-weight: 700; color: var(--color-text-muted); }
.col-empty {
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  gap: var(--space-2); padding: var(--space-6) var(--space-3); text-align: center;
}
.empty-bird-wrap  { background: var(--color-surface-alt); border-radius: 50%; width: 52px; height: 52px; display: flex; align-items: center; justify-content: center; }
.empty-bird-float { font-size: 1.75rem; animation: float 3s ease-in-out infinite; }
@keyframes float  { 0%,100%{transform:translateY(0)} 50%{transform:translateY(-6px)} }
.empty-msg        { font-size: 0.8rem; color: var(--color-text-muted); line-height: 1.5; }
.rejected-accordion { border: 1px solid var(--color-border-light); border-radius: 10px; overflow: hidden; }
.rejected-summary {
  list-style: none; padding: var(--space-3) var(--space-4);
  background: color-mix(in srgb, var(--color-error) 10%, var(--color-surface));
  cursor: pointer; font-weight: 700; font-size: 0.85rem; color: var(--color-error);
  display: flex; align-items: center; gap: var(--space-2);
}
.rejected-summary::-webkit-details-marker { display: none; }
.rejected-hint  { font-weight: 400; color: var(--color-text-muted); font-size: 0.75rem; }
.rejected-body  { padding: var(--space-3) var(--space-4); background: color-mix(in srgb, var(--color-error) 4%, var(--color-surface-raised)); display: flex; flex-direction: column; gap: var(--space-2); }
.rejected-stats { display: flex; gap: var(--space-3); margin-bottom: var(--space-2); }
.stat-chip      { background: var(--color-surface-raised); border-radius: 6px; padding: var(--space-2) var(--space-3); border: 1px solid var(--color-border-light); text-align: center; }
.stat-num       { display: block; font-size: 1.25rem; font-weight: 700; color: var(--color-error); }
.stat-lbl       { font-size: 0.7rem; color: var(--color-text-muted); }
.rejected-row   { display: flex; align-items: center; gap: var(--space-3); background: var(--color-surface-raised); border-radius: 6px; padding: var(--space-2) var(--space-3); border-left: 3px solid var(--color-error); }
.rejected-title { flex: 1; font-weight: 600; font-size: 0.875rem; }
.rejected-stage { font-size: 0.75rem; color: var(--color-text-muted); }
.btn-unrej      { background: none; border: 1px solid var(--color-border); border-radius: 6px; padding: 2px 8px; font-size: 0.75rem; font-weight: 700; color: var(--color-info); cursor: pointer; }
.empty-bird     { font-size: 1.25rem; }
.pre-list-pagination {
  display: flex; align-items: center; justify-content: center; gap: var(--space-2);
  padding: 6px 12px; border-top: 1px solid var(--color-border-light);
}
.btn-page {
  background: none; border: 1px solid var(--color-border); border-radius: 4px;
  color: var(--color-text); font-size: 0.9em; padding: 2px 10px; cursor: pointer;
  line-height: 1.6;
}
.btn-page:disabled {
  opacity: 0.35; cursor: default;
}
.btn-page:not(:disabled):hover {
  background: var(--color-surface-raised);
}
.page-indicator {
  font-size: 0.8em; color: var(--color-text-muted); min-width: 40px; text-align: center;
}
</style>
