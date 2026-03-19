<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { useInterviewsStore } from '../stores/interviews'
import type { PipelineJob, PipelineStage } from '../stores/interviews'
import InterviewCard from '../components/InterviewCard.vue'
import MoveToSheet from '../components/MoveToSheet.vue'

const router = useRouter()
const store  = useInterviewsStore()

// ── Move sheet ────────────────────────────────────────────────────────────────
const moveTarget = ref<PipelineJob | null>(null)

function openMove(jobId: number) {
  moveTarget.value = store.jobs.find(j => j.id === jobId) ?? null
}

async function onMove(stage: PipelineStage, opts: { interview_date?: string; rejection_stage?: string }) {
  if (!moveTarget.value) return
  const wasHired = stage === 'hired'
  await store.move(moveTarget.value.id, stage, opts)
  moveTarget.value = null
  if (wasHired) triggerConfetti()
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

onMounted(async () => { await store.fetchAll(); document.addEventListener('keydown', onKeydown) })
onUnmounted(() => document.removeEventListener('keydown', onKeydown))

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
      <button class="btn-refresh" @click="store.fetchAll()" :disabled="store.loading" aria-label="Refresh">
        {{ store.loading ? '⟳' : '↺' }}
      </button>
    </header>

    <div v-if="store.error" class="error-banner">{{ store.error }}</div>

    <!-- Pre-list: Applied + Survey -->
    <section class="pre-list" aria-label="Applied jobs">
      <div class="pre-list-header">
        <span>Applied ({{ store.applied.length + store.survey.length }})</span>
        <span class="pre-list-hint">Move here when a recruiter reaches out →</span>
      </div>
      <div v-if="store.applied.length === 0 && store.survey.length === 0" class="pre-list-empty">
        <span class="empty-bird">🦅</span>
        <span>No applied jobs yet. <RouterLink to="/apply">Go to Apply</RouterLink> to submit applications.</span>
      </div>
      <div v-for="job in [...store.applied, ...store.survey]" :key="job.id" class="pre-list-row">
        <div class="pre-row-info">
          <span class="pre-row-title">{{ job.title }}</span>
          <span class="pre-row-company">{{ job.company }}</span>
          <span v-if="job.status === 'survey'" class="survey-badge">Survey</span>
        </div>
        <div class="pre-row-meta">
          <span v-if="daysSince(job.applied_at) !== null" class="pre-row-days">{{ daysSince(job.applied_at) }}d ago</span>
          <button class="btn-move-pre" @click="openMove(job.id)" :aria-label="`Move ${job.title}`">Move to… ›</button>
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
          @move="openMove" @prep="router.push(`/prep/${$event}`)" />
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
          @move="openMove" @prep="router.push(`/prep/${$event}`)" />
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
          @move="openMove" @prep="router.push(`/prep/${$event}`)" />
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
      @move="onMove"
      @close="moveTarget = null"
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
.pre-list         { background: var(--color-surface); border-radius: 10px; padding: var(--space-3) var(--space-4); margin-bottom: var(--space-6); }
.pre-list-header  { display: flex; justify-content: space-between; align-items: center; font-weight: 700; font-size: 0.85rem; color: var(--color-text-muted); margin-bottom: var(--space-2); }
.pre-list-hint    { font-weight: 400; font-size: 0.75rem; }
.pre-list-empty   { display: flex; align-items: center; gap: var(--space-2); font-size: 0.85rem; color: var(--color-text-muted); padding: var(--space-2) 0; }
.pre-list-row     { display: flex; align-items: center; justify-content: space-between; padding: var(--space-2) 0; border-top: 1px solid var(--color-border-light); gap: var(--space-3); }
.pre-row-info     { display: flex; align-items: center; gap: var(--space-2); flex: 1; min-width: 0; }
.pre-row-title    { font-weight: 600; font-size: 0.875rem; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.pre-row-company  { color: var(--color-text-muted); font-size: 0.8rem; white-space: nowrap; }
.survey-badge     { background: color-mix(in srgb, var(--status-phone) 12%, var(--color-surface-raised)); color: var(--status-phone); border-radius: 99px; padding: 1px 7px; font-size: 0.7rem; font-weight: 700; }
.pre-row-meta     { display: flex; align-items: center; gap: var(--space-2); flex-shrink: 0; }
.pre-row-days     { font-size: 0.75rem; color: var(--color-text-muted); }
.btn-move-pre     { background: none; border: 1px solid var(--color-border); border-radius: 6px; padding: 2px 8px; font-size: 0.75rem; font-weight: 700; color: var(--color-info); cursor: pointer; }
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
</style>
