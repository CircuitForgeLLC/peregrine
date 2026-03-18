<template>
  <article
    class="job-card"
    :class="{
      'job-card--expanded': expanded,
      'job-card--shimmer':  isPerfectMatch,
    }"
    :aria-label="`${job.title} at ${job.company}`"
  >
    <!-- Score badge + remote badge -->
    <div class="job-card__badges">
      <span
        v-if="job.match_score !== null"
        class="score-badge"
        :class="scoreBadgeClass"
        :aria-label="`${job.match_score}% match`"
      >
        {{ job.match_score }}%
      </span>
      <span v-if="job.is_remote" class="remote-badge">Remote</span>
    </div>

    <!-- Title + company -->
    <h2 class="job-card__title">{{ job.title }}</h2>
    <div class="job-card__company">
      <span>{{ job.company }}</span>
      <span v-if="job.location" class="job-card__sep" aria-hidden="true"> · </span>
      <span v-if="job.location" class="job-card__location">{{ job.location }}</span>
    </div>

    <!-- Salary -->
    <div v-if="job.salary" class="job-card__salary">{{ job.salary }}</div>

    <!-- Description -->
    <div class="job-card__desc" :class="{ 'job-card__desc--clamped': !expanded }">
      {{ descriptionText }}
    </div>

    <!-- Expand/collapse -->
    <button
      v-if="job.description && job.description.length > DESC_LIMIT"
      class="job-card__expand-btn"
      :aria-expanded="expanded"
      @click.stop="$emit(expanded ? 'collapse' : 'expand')"
    >
      {{ expanded ? 'Show less ▲' : 'Show more ▼' }}
    </button>

    <!-- Keyword gaps -->
    <div v-if="gaps.length > 0" class="job-card__gaps">
      <span class="job-card__gaps-label">Missing keywords:</span>
      <span v-for="kw in gaps.slice(0, 5)" :key="kw" class="gap-pill">{{ kw }}</span>
      <span v-if="gaps.length > 5" class="job-card__gaps-more">+{{ gaps.length - 5 }} more</span>
    </div>

    <!-- Footer: source + date -->
    <div class="job-card__footer">
      <a
        v-if="job.url"
        :href="job.url"
        class="job-card__url"
        target="_blank"
        rel="noopener noreferrer"
        @click.stop
      >View listing ↗</a>
      <span class="job-card__date">{{ formattedDate }}</span>
    </div>
  </article>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { Job } from '../stores/review'

const props = defineProps<{
  job:      Job
  expanded: boolean
}>()

defineEmits<{ expand: []; collapse: [] }>()

const DESC_LIMIT = 300

const isPerfectMatch = computed(() => (props.job.match_score ?? 0) >= 95)

const scoreBadgeClass = computed(() => {
  const s = props.job.match_score ?? 0
  if (s >= 80) return 'score-badge--high'
  if (s >= 60) return 'score-badge--mid'
  return 'score-badge--low'
})

const gaps = computed<string[]>(() => {
  if (!props.job.keyword_gaps) return []
  try   { return JSON.parse(props.job.keyword_gaps) as string[] }
  catch { return [] }
})

const descriptionText = computed(() => {
  const d = props.job.description ?? ''
  return !props.expanded && d.length > DESC_LIMIT
    ? d.slice(0, DESC_LIMIT) + '…'
    : d
})

const formattedDate = computed(() => {
  if (!props.job.date_found) return ''
  const d = new Date(props.job.date_found)
  const days = Math.floor((Date.now() - d.getTime()) / 86400000)
  if (days === 0)  return 'Today'
  if (days === 1)  return 'Yesterday'
  if (days < 7)   return `${days}d ago`
  if (days < 30)  return `${Math.floor(days / 7)}w ago`
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
})
</script>

<style scoped>
.job-card {
  padding: var(--space-6);
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  background: var(--color-surface-raised);
  border-radius: var(--radius-card, 1rem);
  user-select: none;
}

/* Perfect match shimmer — easter egg 9.4 */
.job-card--shimmer {
  background: linear-gradient(
    105deg,
    var(--color-surface-raised) 30%,
    rgba(251, 210, 60, 0.25) 50%,
    var(--color-surface-raised) 70%
  );
  background-size: 300% auto;
  animation: shimmer-sweep 1.8s ease 2;
}

@keyframes shimmer-sweep {
  0%   { background-position: 100% center; }
  100% { background-position: -100% center; }
}

@media (prefers-reduced-motion: reduce) {
  .job-card--shimmer { animation: none; }
}

.job-card__badges {
  display: flex;
  gap: var(--space-2);
  flex-wrap: wrap;
}

.score-badge {
  display: inline-flex;
  align-items: center;
  padding: 2px var(--space-2);
  border-radius: 999px;
  font-size: var(--text-xs);
  font-weight: 700;
  font-family: var(--font-mono);
}

.score-badge--high { background: rgba(39, 174, 96, 0.15);  color: var(--score-high); }
.score-badge--mid  { background: rgba(212, 137, 26, 0.15); color: var(--score-mid);  }
.score-badge--low  { background: rgba(192, 57, 43, 0.15);  color: var(--score-low);  }

.remote-badge {
  display: inline-flex;
  align-items: center;
  padding: 2px var(--space-2);
  border-radius: 999px;
  font-size: var(--text-xs);
  font-weight: 600;
  background: var(--app-primary-light);
  color: var(--app-primary);
}

.job-card__title {
  font-family: var(--font-display);
  font-size: var(--text-xl);
  color: var(--color-text);
  line-height: 1.25;
}

.job-card__company {
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--color-text-muted);
}

.job-card__sep     { color: var(--color-border); }
.job-card__location { font-weight: 400; }

.job-card__salary {
  font-size: var(--text-sm);
  color: var(--color-success);
  font-weight: 600;
}

.job-card__desc {
  font-size: var(--text-sm);
  color: var(--color-text);
  line-height: 1.6;
  white-space: pre-wrap;
  overflow-wrap: break-word;
}

.job-card__desc--clamped {
  display: -webkit-box;
  -webkit-line-clamp: 5;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.job-card__expand-btn {
  align-self: flex-start;
  background: transparent;
  border: none;
  color: var(--app-primary);
  font-size: var(--text-xs);
  cursor: pointer;
  padding: 0;
  font-weight: 600;
  transition: opacity 150ms ease;
}

.job-card__expand-btn:hover { opacity: 0.7; }

.job-card__gaps {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-2);
}

.job-card__gaps-label {
  font-size: var(--text-xs);
  color: var(--color-text-muted);
  font-weight: 600;
}

.gap-pill {
  padding: 2px var(--space-2);
  border-radius: 999px;
  font-size: var(--text-xs);
  background: var(--color-surface-alt);
  border: 1px solid var(--color-border-light);
  color: var(--color-text-muted);
}

.job-card__gaps-more {
  font-size: var(--text-xs);
  color: var(--color-text-muted);
}

.job-card__footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: var(--space-1);
  padding-top: var(--space-3);
  border-top: 1px solid var(--color-border-light);
}

.job-card__url {
  font-size: var(--text-xs);
  color: var(--app-primary);
  text-decoration: none;
  font-weight: 600;
  transition: opacity 150ms ease;
}

.job-card__url:hover { opacity: 0.7; }

.job-card__date {
  font-size: var(--text-xs);
  color: var(--color-text-muted);
}
</style>
