<script setup lang="ts">
import { ref, computed } from 'vue'
import type { PipelineJob } from '../stores/interviews'
import type { StageSignal, PipelineStage } from '../stores/interviews'
import { useApiFetch } from '../composables/useApi'

const props = defineProps<{
  job: PipelineJob
  focused?: boolean
}>()

const emit = defineEmits<{
  move: [jobId: number, preSelectedStage?: PipelineStage]
  prep: [jobId: number]
}>()

// Signal state
const sigExpanded = ref(false)

interface SignalMeta {
  label: string
  stage: PipelineStage
  color: 'amber' | 'green' | 'red'
}

const SIGNAL_META: Record<StageSignal['stage_signal'], SignalMeta> = {
  interview_scheduled: { label: 'Move to Phone Screen', stage: 'phone_screen',       color: 'amber' },
  positive_response:   { label: 'Move to Phone Screen', stage: 'phone_screen',       color: 'amber' },
  offer_received:      { label: 'Move to Offer',        stage: 'offer',              color: 'green' },
  survey_received:     { label: 'Move to Survey',       stage: 'survey',             color: 'amber' },
  rejected:            { label: 'Mark Rejected',        stage: 'interview_rejected', color: 'red'   },
}

const COLOR_BG: Record<'amber' | 'green' | 'red', string> = {
  amber: 'rgba(245,158,11,0.08)',
  green: 'rgba(39,174,96,0.08)',
  red:   'rgba(192,57,43,0.08)',
}
const COLOR_BORDER: Record<'amber' | 'green' | 'red', string> = {
  amber: 'rgba(245,158,11,0.4)',
  green: 'rgba(39,174,96,0.4)',
  red:   'rgba(192,57,43,0.4)',
}

function visibleSignals(): StageSignal[] {
  const sigs = props.job.stage_signals ?? []
  return sigExpanded.value ? sigs : sigs.slice(0, 1)
}

async function dismissSignal(sig: StageSignal) {
  // Optimistic removal
  const arr = props.job.stage_signals
  const idx = arr.findIndex(s => s.id === sig.id)
  if (idx !== -1) arr.splice(idx, 1)
  await useApiFetch(`/api/stage-signals/${sig.id}/dismiss`, { method: 'POST' })
}

const scoreClass = computed(() => {
  const s = (props.job.match_score ?? 0) * 100
  if (s >= 85) return 'score--high'
  if (s >= 65) return 'score--mid'
  return 'score--low'
})

const scoreLabel = computed(() =>
  props.job.match_score != null
    ? `${Math.round(props.job.match_score * 100)}%`
    : '—'
)

const interviewDateLabel = computed(() => {
  if (!props.job.interview_date) return null
  const d = new Date(props.job.interview_date)
  const now = new Date()
  const diffDays = Math.round((d.getTime() - now.getTime()) / 86400000)
  const timeStr = d.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })
  if (diffDays === 0) return `Today ${timeStr}`
  if (diffDays === 1) return `Tomorrow ${timeStr}`
  if (diffDays === -1) return `Yesterday ${timeStr}`
  if (diffDays > 1 && diffDays < 7) return `${d.toLocaleDateString([], { weekday: 'short' })} ${timeStr}`
  return d.toLocaleDateString([], { month: 'short', day: 'numeric' })
})

const dateChipIcon = computed(() => {
  if (!props.job.interview_date) return ''
  const map: Record<string, string> = { phone_screen: '📞', interviewing: '🎯', offer: '📜' }
  return map[props.job.status] ?? '📅'
})

const columnColor = computed(() => {
  const map: Record<string, string> = {
    phone_screen: 'var(--status-phone)',
    interviewing: 'var(--color-info)',
    offer: 'var(--status-offer)',
    hired: 'var(--color-success)',
  }
  return map[props.job.status] ?? 'var(--color-border)'
})
</script>

<template>
  <article
    class="interview-card"
    :class="{ 'interview-card--focused': focused }"
    :style="{ '--card-accent': columnColor }"
    tabindex="0"
    :aria-label="`${job.title} at ${job.company}`"
    @keydown.enter="emit('prep', job.id)"
    @keydown.m.exact="emit('move', job.id)"
  >
    <div class="card-body">
      <div class="card-title">{{ job.title }}</div>
      <div class="card-company">
        {{ job.company }}
        <span v-if="job.salary" class="card-salary">· {{ job.salary }}</span>
      </div>
      <div class="card-badges">
        <span class="score-badge" :class="scoreClass">{{ scoreLabel }}</span>
        <span v-if="job.is_remote" class="remote-badge">Remote</span>
      </div>
      <div v-if="interviewDateLabel" class="date-chip">
        {{ dateChipIcon }} {{ interviewDateLabel }}
      </div>
      <div class="research-badge research-badge--done">🔬 Research ready</div>
    </div>
    <footer class="card-footer">
      <button class="card-action" @click.stop="emit('move', job.id)">Move to… ›</button>
      <button class="card-action" @click.stop="emit('prep', job.id)">Prep →</button>
    </footer>
    <!-- Signal banners -->
    <template v-if="job.stage_signals?.length">
      <div
        v-for="sig in visibleSignals()"
        :key="sig.id"
        class="signal-banner"
        :style="{
          background: COLOR_BG[SIGNAL_META[sig.stage_signal].color],
          borderTopColor: COLOR_BORDER[SIGNAL_META[sig.stage_signal].color],
        }"
      >
        <span class="signal-label">
          📧 Email suggests: <strong>{{ SIGNAL_META[sig.stage_signal].label }}</strong>
        </span>
        <span class="signal-subject">{{ sig.subject.slice(0, 60) }}{{ sig.subject.length > 60 ? '…' : '' }}</span>
        <div class="signal-actions">
          <button
            class="btn-signal-move"
            @click.stop="emit('move', props.job.id, SIGNAL_META[sig.stage_signal].stage)"
            :aria-label="`${SIGNAL_META[sig.stage_signal].label} for ${props.job.title}`"
          >→ {{ SIGNAL_META[sig.stage_signal].label }}</button>
          <button
            class="btn-signal-dismiss"
            @click.stop="dismissSignal(sig)"
            aria-label="Dismiss signal"
          >✕</button>
        </div>
      </div>
      <button
        v-if="(job.stage_signals?.length ?? 0) > 1"
        class="btn-sig-expand"
        @click.stop="sigExpanded = !sigExpanded"
      >{{ sigExpanded ? '− less' : `+${(job.stage_signals?.length ?? 1) - 1} more` }}</button>
    </template>
  </article>
</template>

<style scoped>
.interview-card {
  background: var(--color-surface-raised);
  border-radius: 10px;
  border-left: 4px solid var(--card-accent, var(--color-border));
  box-shadow: 0 2px 6px rgba(0, 0, 0, 0.07);
  cursor: pointer;
  outline: none;
  transition: box-shadow 150ms;
}

.interview-card--focused,
.interview-card:focus-visible {
  box-shadow: 0 0 0 3px var(--card-accent, var(--color-primary));
}

.card-body {
  padding: 10px 12px 8px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.card-title {
  font-weight: 700;
  font-size: 0.875rem;
  color: var(--color-text);
  line-height: 1.2;
}

.card-company {
  font-size: 0.75rem;
  color: var(--color-text-muted);
}

.card-salary {
  color: var(--color-text-muted);
}

.card-badges {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
  margin-top: 2px;
}

.score-badge {
  border-radius: 99px;
  padding: 2px 8px;
  font-size: 0.7rem;
  font-weight: 700;
}

.score--high {
  background: color-mix(in srgb, var(--color-success) 18%, var(--color-surface-raised));
  color: var(--color-success);
}

.score--mid {
  background: color-mix(in srgb, var(--color-warning) 18%, var(--color-surface-raised));
  color: var(--color-warning);
}

.score--low {
  background: color-mix(in srgb, var(--color-error) 18%, var(--color-surface-raised));
  color: var(--color-error);
}

.remote-badge {
  border-radius: 99px;
  padding: 2px 8px;
  font-size: 0.7rem;
  font-weight: 700;
  background: color-mix(in srgb, var(--color-info) 14%, var(--color-surface-raised));
  color: var(--color-info);
}

.date-chip {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  background: color-mix(in srgb, var(--color-info) 12%, var(--color-surface-raised));
  color: var(--color-info);
  border-radius: 6px;
  padding: 3px 8px;
  font-size: 0.7rem;
  font-weight: 700;
  margin-top: 2px;
  align-self: flex-start;
}

.research-badge {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  border-radius: 99px;
  padding: 2px 8px;
  font-size: 0.7rem;
  font-weight: 700;
  align-self: flex-start;
  margin-top: 2px;
}

.research-badge--done {
  background: color-mix(in srgb, var(--status-phone) 12%, var(--color-surface-raised));
  color: var(--status-phone);
  border: 1px solid color-mix(in srgb, var(--status-phone) 30%, var(--color-surface-raised));
}

.card-footer {
  border-top: 1px solid var(--color-border-light);
  padding: 6px 10px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: color-mix(in srgb, var(--color-surface) 60%, transparent);
}

.card-action {
  background: none;
  border: none;
  cursor: pointer;
  font-size: 0.7rem;
  font-weight: 700;
  color: var(--color-info);
  padding: 2px 4px;
  border-radius: 4px;
}

.card-action:hover {
  background: var(--color-surface);
}

.signal-banner {
  border-top: 1px solid transparent; /* color set inline */
  padding: 8px 12px;
  display: flex; flex-direction: column; gap: 4px;
}
.signal-label  { font-size: 0.82em; }
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
.btn-sig-expand {
  background: none; border: none; font-size: 0.75em; color: var(--color-info); cursor: pointer;
  padding: 4px 12px; text-align: left;
}
</style>
