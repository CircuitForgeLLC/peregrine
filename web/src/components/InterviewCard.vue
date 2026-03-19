<script setup lang="ts">
import { computed } from 'vue'
import type { PipelineJob } from '../stores/interviews'

const props = defineProps<{
  job: PipelineJob
  focused?: boolean
}>()

const emit = defineEmits<{
  move: [jobId: number]
  prep: [jobId: number]
}>()

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
  </article>
</template>

<style scoped>
.interview-card {
  background: var(--color-surface-raised);
  border-radius: 10px;
  border-left: 4px solid var(--card-accent, var(--color-border));
  box-shadow: 0 2px 6px rgba(0, 0, 0, 0.07);
  overflow: hidden;
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
</style>
