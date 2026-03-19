<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, nextTick } from 'vue'
import { STAGE_LABELS, PIPELINE_STAGES } from '../stores/interviews'
import type { PipelineStage } from '../stores/interviews'

const props = defineProps<{
  currentStatus:     string
  jobTitle:          string
  preSelectedStage?: PipelineStage
}>()

const emit = defineEmits<{
  move:  [stage: PipelineStage, opts: { interview_date?: string; rejection_stage?: string }]
  close: []
}>()

const selectedStage  = ref<PipelineStage | null>(props.preSelectedStage ?? null)
const interviewDate  = ref('')
const rejectionStage = ref('')
const focusIndex     = ref(0)
const firstOptionEl  = ref<HTMLButtonElement | null>(null)

const stages = computed(() =>
  PIPELINE_STAGES.filter(s => s !== props.currentStatus)
)

function select(stage: PipelineStage) {
  selectedStage.value = stage
}

function confirm() {
  if (!selectedStage.value) return
  const opts: { interview_date?: string; rejection_stage?: string } = {}
  if (interviewDate.value) opts.interview_date = new Date(interviewDate.value).toISOString()
  if (rejectionStage.value) opts.rejection_stage = rejectionStage.value
  emit('move', selectedStage.value, opts)
}

function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape') { emit('close'); return }
  if (e.key === 'ArrowDown' || e.key === 'ArrowRight') {
    e.preventDefault()
    focusIndex.value = Math.min(focusIndex.value + 1, stages.value.length - 1)
  }
  if (e.key === 'ArrowUp' || e.key === 'ArrowLeft') {
    e.preventDefault()
    focusIndex.value = Math.max(focusIndex.value - 1, 0)
  }
  if (e.key === 'Enter' && stages.value[focusIndex.value]) {
    select(stages.value[focusIndex.value])
  }
}

onMounted(() => {
  document.addEventListener('keydown', onKeydown)
  nextTick(() => firstOptionEl.value?.focus())
})
onUnmounted(() => document.removeEventListener('keydown', onKeydown))
</script>

<template>
  <Teleport to="body">
    <div
      class="sheet-backdrop"
      role="dialog"
      aria-modal="true"
      :aria-label="`Move ${jobTitle}`"
      @click.self="emit('close')"
    >
      <div class="sheet-panel">
        <div class="sheet-header">
          <span class="sheet-title">Move to…</span>
          <button class="sheet-close" @click="emit('close')" aria-label="Close">✕</button>
        </div>

        <div class="sheet-stages" role="listbox">
          <button
            v-for="(stage, i) in stages"
            :key="stage"
            :ref="i === 0 ? (el) => { firstOptionEl = el as HTMLButtonElement } : undefined"
            class="stage-option"
            :class="{
              'stage-option--selected': selectedStage === stage,
              'stage-option--focused': focusIndex === i,
            }"
            role="option"
            :aria-selected="selectedStage === stage"
            @click="select(stage)"
          >
            {{ STAGE_LABELS[stage] }}
          </button>
        </div>

        <div
          v-if="selectedStage === 'phone_screen' || selectedStage === 'interviewing'"
          class="sheet-extras"
        >
          <label class="field-label">
            Interview date/time (optional)
            <input type="datetime-local" v-model="interviewDate" class="field-input" />
          </label>
        </div>

        <div v-if="selectedStage === 'interview_rejected'" class="sheet-extras">
          <label class="field-label">
            Rejected after…
            <select v-model="rejectionStage" class="field-input">
              <option value="">— select —</option>
              <option>Application</option>
              <option>Phone screen</option>
              <option>Interviewing</option>
              <option>Offer stage</option>
            </select>
          </label>
        </div>

        <div class="sheet-actions">
          <button class="btn-cancel" @click="emit('close')">Cancel</button>
          <button class="btn-confirm" :disabled="!selectedStage" @click="confirm">Move →</button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.sheet-backdrop {
  position: fixed; inset: 0; z-index: 200;
  background: rgba(0,0,0,.45);
  display: flex; align-items: flex-end; justify-content: center;
}
@media (min-width: 640px) {
  .sheet-backdrop { align-items: center; }
}
.sheet-panel {
  background: var(--color-surface-raised);
  border-radius: 16px 16px 0 0;
  padding: var(--space-4) var(--space-4) var(--space-6);
  width: 100%; max-width: 480px;
  display: flex; flex-direction: column; gap: var(--space-3);
}
@media (min-width: 640px) {
  .sheet-panel { border-radius: 12px; }
}
.sheet-header  { display: flex; align-items: center; justify-content: space-between; }
.sheet-title   { font-weight: 700; font-size: 1rem; }
.sheet-close   { background: none; border: none; cursor: pointer; font-size: 1rem; color: var(--color-text-muted); }
.sheet-stages  { display: flex; flex-direction: column; gap: var(--space-2); }
.stage-option {
  background: var(--color-surface);
  border: 2px solid transparent;
  border-radius: 8px; padding: var(--space-2) var(--space-3);
  font-size: 0.9rem; font-weight: 600; text-align: left;
  cursor: pointer; color: var(--color-text);
  transition: border-color 120ms, background 120ms;
}
.stage-option:hover      { background: var(--color-surface-alt); }
.stage-option--selected  { border-color: var(--color-primary); background: var(--color-primary-light); }
.stage-option--focused   { outline: 2px solid var(--color-primary); outline-offset: 1px; }
.sheet-extras  { display: flex; flex-direction: column; gap: var(--space-2); }
.field-label   { font-size: 0.8rem; font-weight: 600; color: var(--color-text-muted); display: flex; flex-direction: column; gap: 4px; }
.field-input   { padding: var(--space-2); border: 1px solid var(--color-border); border-radius: 6px; background: var(--color-surface); font-size: 0.875rem; color: var(--color-text); }
.sheet-actions { display: flex; gap: var(--space-2); justify-content: flex-end; margin-top: var(--space-2); }
.btn-cancel {
  background: var(--color-surface-alt); border: none; border-radius: 8px;
  padding: var(--space-2) var(--space-4); font-weight: 600; cursor: pointer;
  color: var(--color-text-muted);
}
.btn-confirm {
  background: var(--color-primary); border: none; border-radius: 8px;
  padding: var(--space-2) var(--space-4); font-weight: 700; cursor: pointer;
  color: var(--color-text-inverse);
}
.btn-confirm:disabled { opacity: .4; cursor: not-allowed; }
</style>
