<template>
  <div class="criteria-strip" role="group" aria-label="What's driving your matches">
    <span class="criteria-strip__label">Matching on</span>

    <span
      v-for="pill in pills"
      :key="pill.key"
      class="criteria-pill"
      :class="{ 'criteria-pill--unset': pill.unset }"
    >
      <span v-if="pill.icon" class="criteria-pill__icon" aria-hidden="true">{{ pill.icon }}</span>
      {{ pill.text }}
    </span>

    <RouterLink to="/settings/search" class="criteria-pill criteria-pill--link">
      Edit preferences →
    </RouterLink>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useSearchStore } from '../stores/settings/search'
import { useResumeStore } from '../stores/settings/resume'

const search = useSearchStore()
const resume = useResumeStore()

onMounted(() => {
  search.load()
  resume.load()
})

const REMOTE_LABELS: Record<string, string> = {
  remote: 'Remote',
  onsite: 'On-site',
  both: 'Remote/Hybrid',
}

interface Pill {
  key: string
  text: string
  icon?: string
  unset?: boolean
}

// Each criterion renders as a filled pill when set, or a dashed "unset" pill
// inviting completion — mirrors Peregrine's job-match scoring inputs so users
// can see (and fix) exactly what's shaping their queue, without a Settings trip.
const pills = computed<Pill[]>(() => {
  const result: Pill[] = []

  if (search.locations.length > 0) {
    const [first, ...rest] = search.locations
    result.push({ key: 'locations', text: rest.length ? `${first} +${rest.length}` : first })
  } else {
    result.push({ key: 'locations', text: 'Locations?', unset: true })
  }

  if (resume.salary_min > 0) {
    result.push({ key: 'salary', text: `$${Math.round(resume.salary_min / 1000)}k+` })
  } else {
    result.push({ key: 'salary', text: 'Min salary?', unset: true })
  }

  result.push({ key: 'remote', text: REMOTE_LABELS[search.remote_preference] ?? 'Remote/Hybrid' })

  if (search.job_titles.length > 0) {
    const [first, ...rest] = search.job_titles
    result.push({ key: 'titles', text: rest.length ? `${first} +${rest.length}` : first })
  } else {
    result.push({ key: 'titles', text: 'Target titles?', unset: true })
  }

  result.push({
    key: 'resume',
    text: 'Resume',
    icon: resume.hasResume ? '✓' : undefined,
    unset: !resume.hasResume,
  })

  return result
})
</script>

<style scoped>
.criteria-strip {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-3) var(--space-4);
  margin-bottom: var(--space-4);
  background: var(--color-surface-raised);
  border: 1px solid var(--color-border-light);
  border-radius: var(--radius-md);
}

.criteria-strip__label {
  font-size: 0.75rem;
  font-weight: 600;
  letter-spacing: 0.03em;
  text-transform: uppercase;
  color: var(--color-text-muted);
  margin-right: var(--space-1);
}

.criteria-pill {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 3px 10px;
  font-size: 0.8rem;
  color: var(--color-accent);
  background: color-mix(in srgb, var(--color-accent) 15%, transparent);
  border: 1px solid color-mix(in srgb, var(--color-accent) 30%, transparent);
  border-radius: var(--radius-full);
  white-space: nowrap;
  transition: var(--transition);
}

.criteria-pill--unset {
  color: var(--color-text-muted);
  background: transparent;
  border-style: dashed;
  border-color: var(--color-border);
}

.criteria-pill__icon {
  color: var(--color-success);
  font-weight: 700;
}

.criteria-pill--link {
  color: var(--color-text-muted);
  background: transparent;
  border-color: var(--color-border);
  text-decoration: none;
  margin-left: auto;
}

.criteria-pill--link:hover,
.criteria-pill--link:focus-visible {
  color: var(--color-accent);
  border-color: var(--color-accent);
}

@media (max-width: 640px) {
  .criteria-strip { padding: var(--space-2) var(--space-3); }
  .criteria-pill--link { margin-left: 0; }
}
</style>
