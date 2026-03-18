<template>
  <div class="apply-list">
    <header class="apply-list__header">
      <h1 class="apply-list__title">Apply</h1>
      <p class="apply-list__subtitle">Approved jobs ready for applications</p>
    </header>

    <div v-if="loading" class="apply-list__loading" aria-live="polite">
      <span class="spinner" aria-hidden="true" />
      <span>Loading approved jobs…</span>
    </div>

    <div v-else-if="jobs.length === 0" class="apply-list__empty" role="status">
      <span aria-hidden="true" class="empty-icon">📋</span>
      <h2 class="empty-title">No approved jobs yet</h2>
      <p class="empty-desc">Approve listings in Job Review, then come back here to write applications.</p>
      <RouterLink to="/review" class="empty-cta">Go to Job Review →</RouterLink>
    </div>

    <ul v-else class="apply-list__jobs" role="list">
      <li v-for="job in jobs" :key="job.id">
        <RouterLink :to="`/apply/${job.id}`" class="job-row" :aria-label="`Open ${job.title} at ${job.company}`">
          <div class="job-row__main">
            <div class="job-row__badges">
              <span
                v-if="job.match_score !== null"
                class="score-badge"
                :class="scoreBadgeClass(job.match_score)"
              >{{ job.match_score }}%</span>
              <span v-if="job.is_remote" class="remote-badge">Remote</span>
              <span v-if="job.has_cover_letter" class="cl-badge cl-badge--done">✓ Draft</span>
              <span v-else class="cl-badge cl-badge--pending">○ No draft</span>
            </div>
            <span class="job-row__title">{{ job.title }}</span>
            <span class="job-row__company">
              {{ job.company }}
              <span v-if="job.location" class="job-row__sep" aria-hidden="true"> · </span>
              <span v-if="job.location">{{ job.location }}</span>
            </span>
          </div>
          <div class="job-row__meta">
            <span v-if="job.salary" class="job-row__salary">{{ job.salary }}</span>
            <span class="job-row__arrow" aria-hidden="true">›</span>
          </div>
        </RouterLink>
      </li>
    </ul>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { RouterLink } from 'vue-router'
import { useApiFetch } from '../composables/useApi'

interface ApprovedJob {
  id:              number
  title:           string
  company:         string
  location:        string | null
  is_remote:       boolean
  salary:          string | null
  match_score:     number | null
  has_cover_letter: boolean
}

const jobs    = ref<ApprovedJob[]>([])
const loading = ref(true)

function scoreBadgeClass(score: number) {
  if (score >= 80) return 'score-badge--high'
  if (score >= 60) return 'score-badge--mid'
  return 'score-badge--low'
}

onMounted(async () => {
  const { data } = await useApiFetch<ApprovedJob[]>('/api/jobs?status=approved&limit=100&fields=id,title,company,location,is_remote,salary,match_score,has_cover_letter')
  loading.value = false
  if (data) jobs.value = data
})
</script>

<style scoped>
.apply-list {
  max-width: 760px;
  margin: 0 auto;
  padding: var(--space-8) var(--space-6);
  display: flex;
  flex-direction: column;
  gap: var(--space-6);
}

.apply-list__header { display: flex; flex-direction: column; gap: var(--space-1); }

.apply-list__title {
  font-family: var(--font-display);
  font-size: var(--text-2xl);
  color: var(--app-primary);
}

.apply-list__subtitle { font-size: var(--text-sm); color: var(--color-text-muted); }

.apply-list__loading {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-12);
  color: var(--color-text-muted);
  font-size: var(--text-sm);
  justify-content: center;
}

.apply-list__empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-16) var(--space-8);
  text-align: center;
}

.empty-icon  { font-size: 3rem; }
.empty-title { font-family: var(--font-display); font-size: var(--text-xl); color: var(--color-text); }
.empty-desc  { font-size: var(--text-sm); color: var(--color-text-muted); max-width: 32ch; }

.empty-cta {
  margin-top: var(--space-2);
  color: var(--app-primary);
  font-size: var(--text-sm);
  font-weight: 600;
  text-decoration: none;
  transition: opacity 150ms ease;
}
.empty-cta:hover { opacity: 0.7; }

.apply-list__jobs { list-style: none; display: flex; flex-direction: column; gap: var(--space-2); }

.job-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-4);
  padding: var(--space-4) var(--space-5);
  background: var(--color-surface-raised);
  border: 1px solid var(--color-border-light);
  border-radius: var(--radius-lg);
  text-decoration: none;
  min-height: 72px;
  transition: border-color 150ms ease, box-shadow 150ms ease, transform 120ms ease;
}

.job-row:hover {
  border-color: var(--app-primary);
  box-shadow: var(--shadow-sm);
  transform: translateY(-1px);
}

.job-row__main { display: flex; flex-direction: column; gap: var(--space-1); flex: 1; min-width: 0; }

.job-row__badges {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-1);
  margin-bottom: 2px;
}

.score-badge {
  display: inline-flex;
  align-items: center;
  padding: 1px var(--space-2);
  border-radius: 999px;
  font-size: var(--text-xs);
  font-weight: 700;
  font-family: var(--font-mono);
}
.score-badge--high { background: rgba(39,174,96,0.12);  color: var(--score-high); }
.score-badge--mid  { background: rgba(212,137,26,0.12); color: var(--score-mid);  }
.score-badge--low  { background: rgba(192,57,43,0.12);  color: var(--score-low);  }

.remote-badge {
  padding: 1px var(--space-2);
  border-radius: 999px;
  font-size: var(--text-xs);
  font-weight: 600;
  background: var(--app-primary-light);
  color: var(--app-primary);
}

.cl-badge {
  padding: 1px var(--space-2);
  border-radius: 999px;
  font-size: var(--text-xs);
  font-weight: 600;
}
.cl-badge--done    { background: rgba(39,174,96,0.10);  color: var(--color-success); }
.cl-badge--pending { background: var(--color-surface-alt); color: var(--color-text-muted); }

.job-row__title {
  font-size: var(--text-sm);
  font-weight: 700;
  color: var(--color-text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.job-row__company {
  font-size: var(--text-xs);
  color: var(--color-text-muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.job-row__sep { color: var(--color-border); }

.job-row__meta {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  flex-shrink: 0;
}

.job-row__salary {
  font-size: var(--text-xs);
  color: var(--color-success);
  font-weight: 600;
  white-space: nowrap;
}

.job-row__arrow {
  font-size: 1.25rem;
  color: var(--color-text-muted);
  line-height: 1;
}

.spinner {
  width: 1.2rem;
  height: 1.2rem;
  border: 2px solid var(--color-border);
  border-top-color: var(--app-primary);
  border-radius: 50%;
  animation: spin 0.7s linear infinite;
}

@keyframes spin { to { transform: rotate(360deg); } }

@media (max-width: 767px) {
  .apply-list { padding: var(--space-4); gap: var(--space-4); }
  .apply-list__title { font-size: var(--text-xl); }
  .job-row { padding: var(--space-3) var(--space-4); }
}
</style>
