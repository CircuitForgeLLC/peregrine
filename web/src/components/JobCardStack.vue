<template>
  <div class="card-stack" :aria-label="`${remaining} jobs remaining`">
    <!-- Peek cards — depth illusion behind active card -->
    <div class="card-peek card-peek-2" aria-hidden="true" />
    <div class="card-peek card-peek-1" aria-hidden="true" />

    <!-- Active card wrapper — receives pointer events -->
    <div
      ref="wrapperEl"
      class="card-wrapper"
      :class="{
        'is-held':    isHeld,
        'is-exiting': isExiting,
      }"
      :style="cardStyle"
      role="region"
      :aria-label="job.title"
      @pointerdown="onPointerDown"
      @pointermove="onPointerMove"
      @pointerup="onPointerUp"
      @pointercancel="onPointerCancel"
    >
      <!-- Directional tint overlay -->
      <div
        class="card-tint"
        :class="{
          'card-tint--approve': dx > 0,
          'card-tint--reject':  dx < 0,
        }"
        :style="{ opacity: tintOpacity }"
        aria-hidden="true"
      >
        <span class="card-tint__icon">{{ dx > 0 ? '✓' : '✗' }}</span>
      </div>

      <JobCard
        :job="job"
        :expanded="isExpanded"
        @expand="isExpanded = true"
        @collapse="isExpanded = false"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import JobCard from './JobCard.vue'
import type { Job } from '../stores/review'

const props = defineProps<{
  job:       Job
  remaining: number
}>()

const emit = defineEmits<{
  approve: []
  reject:  []
  skip:    []
}>()

// ─── State ────────────────────────────────────────────────────────────────────

const wrapperEl  = ref<HTMLElement | null>(null)
const isExpanded = ref(false)
const isHeld     = ref(false)
const isExiting  = ref(false)

const dx = ref(0)
const dy = ref(0)

// ─── Derived style ────────────────────────────────────────────────────────────

// Max tilt at ±120px drag = ±6°
const TILT_MAX_DEG = 6
const TILT_AT_PX   = 120

const cardStyle = computed(() => {
  if (isExiting.value) return {}  // exiting uses CSS class transition
  if (!isHeld.value && dx.value === 0 && dy.value === 0) return {}
  const tilt = Math.max(-TILT_MAX_DEG, Math.min(TILT_MAX_DEG, (dx.value / TILT_AT_PX) * TILT_MAX_DEG))
  return { transform: `translate(${dx.value}px, ${dy.value}px) rotate(${tilt}deg)` }
})

// Tint opacity 0→0.6 at ±0→120px
const tintOpacity = computed(() =>
  isHeld.value ? Math.min(Math.abs(dx.value) / TILT_AT_PX, 1) * 0.6 : 0,
)

// ─── Fling detection ──────────────────────────────────────────────────────────

const FLING_SPEED_PX_S = 600   // minimum px/s to qualify
const FLING_ALIGN      = 0.707 // cos(45°) — must be within 45° of horizontal
const FLING_WINDOW_MS  = 50    // rolling sample window

let velocityBuf: { x: number; y: number; t: number }[] = []

// ─── Zone detection ───────────────────────────────────────────────────────────

const ZONE_PCT = 0.2  // 20% of viewport width on each side

// ─── Pointer events ───────────────────────────────────────────────────────────

let pickupX = 0
let pickupY = 0

function onPointerDown(e: PointerEvent) {
  // Let interactive children (links, buttons) receive their events
  if ((e.target as Element).closest('button, a, input, select, textarea')) return
  if (isExiting.value) return
  ;(e.currentTarget as HTMLElement).setPointerCapture(e.pointerId)
  pickupX = e.clientX
  pickupY = e.clientY
  isHeld.value  = true
  velocityBuf   = []
}

function onPointerMove(e: PointerEvent) {
  if (!isHeld.value) return
  dx.value = e.clientX - pickupX
  dy.value = e.clientY - pickupY

  // Rolling velocity buffer
  const now = performance.now()
  velocityBuf.push({ x: e.clientX, y: e.clientY, t: now })
  while (velocityBuf.length > 1 && now - velocityBuf[0].t > FLING_WINDOW_MS) {
    velocityBuf.shift()
  }
}

function onPointerUp(e: PointerEvent) {
  if (!isHeld.value) return
  ;(e.currentTarget as HTMLElement).releasePointerCapture(e.pointerId)
  isHeld.value = false

  // Fling detection — fires first so a fast flick resolves without reaching the edge zone
  if (velocityBuf.length >= 2) {
    const oldest = velocityBuf[0]
    const newest = velocityBuf[velocityBuf.length - 1]
    const dt = (newest.t - oldest.t) / 1000
    if (dt > 0) {
      const vx    = (newest.x - oldest.x) / dt
      const vy    = (newest.y - oldest.y) / dt
      const speed = Math.sqrt(vx * vx + vy * vy)
      if (speed >= FLING_SPEED_PX_S && Math.abs(vx) / speed >= FLING_ALIGN) {
        velocityBuf = []
        _dismiss(vx > 0 ? 'right' : 'left')
        return
      }
    }
  }
  velocityBuf = []

  // Zone check — did the pointer release in an edge zone?
  const vw = window.innerWidth
  if (e.clientX < vw * ZONE_PCT) {
    _dismiss('left')
  } else if (e.clientX > vw * (1 - ZONE_PCT)) {
    _dismiss('right')
  } else {
    _snapBack()
  }
}

function onPointerCancel(e: PointerEvent) {
  if (!isHeld.value) return
  ;(e.currentTarget as HTMLElement).releasePointerCapture(e.pointerId)
  isHeld.value = false
  velocityBuf  = []
  _snapBack()
}

// ─── Animation helpers ────────────────────────────────────────────────────────

function _snapBack() {
  dx.value = 0
  dy.value = 0
}

/** Fly card off-screen, then emit the action. */
async function _dismiss(direction: 'left' | 'right') {
  if (!wrapperEl.value || isExiting.value) return
  isExiting.value = true

  const exitX   = direction === 'right' ? 700 : -700
  const exitTilt = direction === 'right' ? 14 : -14
  wrapperEl.value.style.transform = `translate(${exitX}px, -60px) rotate(${exitTilt}deg)`
  wrapperEl.value.style.opacity   = '0'

  await new Promise(r => setTimeout(r, 280))
  emit(direction === 'right' ? 'approve' : 'reject')
}

// Keyboard-triggered dismiss (called from parent via template ref)
async function dismissApprove() { await _dismiss('right') }
async function dismissReject()  { await _dismiss('left') }
function       dismissSkip()    { _snapBack(); emit('skip') }

// Reset when a new job is slotted in (Vue reuses the element)
watch(() => props.job.id, () => {
  dx.value         = 0
  dy.value         = 0
  isExiting.value  = false
  isHeld.value     = false
  isExpanded.value = false
  if (wrapperEl.value) {
    // Suppress the spring transition for this frame — without this the card
    // spring-animates from its exit position back to center before the new
    // job renders (the "snap-back on processed cards" glitch).
    wrapperEl.value.style.transition = 'none'
    wrapperEl.value.style.transform  = ''
    wrapperEl.value.style.opacity    = ''
    requestAnimationFrame(() => {
      if (wrapperEl.value) wrapperEl.value.style.transition = ''
    })
  }
})

defineExpose({ dismissApprove, dismissReject, dismissSkip })
</script>

<style scoped>
.card-stack {
  position: relative;
  /* Reserve space for peek cards below active card */
  padding-bottom: 18px;
}

/* Peek cards — static shadows giving a stack depth feel */
.card-peek {
  position: absolute;
  left: 0; right: 0; bottom: 0;
  border-radius: var(--radius-card, 1rem);
  background: var(--color-surface-raised);
  border: 1px solid var(--color-border-light);
}

.card-peek-1 { transform: translateY(8px) scale(0.97);  opacity: 0.55; height: 80px; }
.card-peek-2 { transform: translateY(16px) scale(0.94); opacity: 0.30; height: 80px; }

/* Active card wrapper */
.card-wrapper {
  position: relative;
  z-index: 1;
  border-radius: var(--radius-card, 1rem);
  background: var(--color-surface-raised);
  border: 1px solid var(--color-border-light);
  box-shadow: var(--shadow-md);
  /* Spring snap-back when released with no action */
  transition:
    transform var(--swipe-spring),
    opacity   200ms ease,
    box-shadow 150ms ease;
  touch-action: none;
  cursor: grab;
  overflow: hidden;
  will-change: transform;
}

.card-wrapper.is-held {
  cursor: grabbing;
  transition: none;  /* instant response while dragging */
  box-shadow: var(--shadow-xl, 0 12px 40px rgba(0,0,0,0.18));
}

/* is-exiting: override to linear ease-in for off-screen fly */
.card-wrapper.is-exiting {
  transition:
    transform 280ms ease-in,
    opacity   240ms ease-in !important;
  pointer-events: none;
}

/* Directional tint overlay */
.card-tint {
  position: absolute;
  inset: 0;
  border-radius: inherit;
  pointer-events: none;
  z-index: 2;
  display: flex;
  align-items: flex-start;
  padding: var(--space-4);
  transition: opacity 60ms linear;
}

.card-tint--approve { background: rgba(39, 174, 96, 0.35); }
.card-tint--reject  { background: rgba(192, 57, 43, 0.35); }

.card-tint__icon {
  font-size: 2rem;
  font-weight: 900;
  color: white;
  text-shadow: 0 1px 3px rgba(0,0,0,0.3);
  opacity: 0.85;
}

.card-tint--approve .card-tint__icon { margin-left: auto; }
.card-tint--reject  .card-tint__icon { margin-right: auto; }

@media (prefers-reduced-motion: reduce) {
  .card-wrapper        { transition: none; }
  .card-wrapper.is-exiting { transition: opacity 200ms ease !important; }
}
</style>
