<template>
  <section class="pipeline-stepper" aria-labelledby="pipeline-stepper-heading">
    <div class="pipeline-stepper__header">
      <h2 id="pipeline-stepper-heading" class="home__section-title">Interview Pipeline</h2>
      <RouterLink to="/interviews" class="pipeline-stepper__link">View all interviews →</RouterLink>
    </div>

    <ol class="pipeline-stepper__stages" aria-label="Pipeline stages">
      <li
        v-for="stage in stages"
        :key="stage.key"
        class="pipeline-stage"
        :class="{ 'pipeline-stage--active': stage.count > 0 }"
      >
        <span class="pipeline-stage__node" aria-hidden="true">{{ stage.icon }}</span>
        <span class="pipeline-stage__label">{{ stage.label }}</span>
        <span class="pipeline-stage__count">{{ store.loading ? '—' : stage.count }}</span>
      </li>
    </ol>

    <p v-if="!store.loading && store.rejected.length > 0" class="pipeline-stepper__rejected">
      {{ store.rejected.length }} rejected — still visible in the full board
    </p>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { RouterLink } from 'vue-router'
import { useInterviewsStore, PIPELINE_STAGES, STAGE_LABELS, type PipelineStage } from '../stores/interviews'

const store = useInterviewsStore()

onMounted(() => store.fetchAll())

// interview_rejected is a terminal side-branch, not a step in the linear
// flow — shown separately below rather than as a 7th stage.
const VISIBLE_STAGES = PIPELINE_STAGES.filter((s): s is Exclude<PipelineStage, 'interview_rejected'> => s !== 'interview_rejected')

const STAGE_ICONS: Record<string, string> = {
  applied: '📝',
  survey: '📋',
  phone_screen: '☎️',
  interviewing: '🎤',
  offer: '🎉',
  hired: '✅',
}

const stages = computed(() =>
  VISIBLE_STAGES.map(key => ({
    key,
    label: STAGE_LABELS[key],
    icon: STAGE_ICONS[key],
    count: store.jobs.filter(j => j.status === key).length,
  }))
)
</script>

<style scoped>
.pipeline-stepper {
  margin-bottom: var(--space-8);
}

.pipeline-stepper__header {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: var(--space-3);
  margin-bottom: var(--space-4);
}

.pipeline-stepper__link {
  font-size: 0.85rem;
  color: var(--color-accent);
  text-decoration: none;
  white-space: nowrap;
}

.pipeline-stepper__link:hover,
.pipeline-stepper__link:focus-visible {
  text-decoration: underline;
}

.pipeline-stepper__stages {
  display: flex;
  list-style: none;
  margin: 0;
  padding: 0;
  gap: var(--space-2);
}

.pipeline-stage {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  padding: var(--space-3) var(--space-1);
  text-align: center;
}

.pipeline-stage__node {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 2.25rem;
  height: 2.25rem;
  border-radius: var(--radius-full);
  background: var(--color-surface-raised);
  border: 2px solid var(--color-border);
  font-size: 1.1rem;
  transition: var(--transition);
}

.pipeline-stage--active .pipeline-stage__node {
  border-color: var(--color-accent);
  background: var(--color-accent-light);
}

.pipeline-stage__label {
  font-size: 0.75rem;
  color: var(--color-text-muted);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 100%;
}

.pipeline-stage__count {
  font-size: 1.1rem;
  font-weight: 700;
  color: var(--color-text);
}

.pipeline-stage:not(.pipeline-stage--active) .pipeline-stage__count {
  color: var(--color-text-muted);
  font-weight: 500;
}

.pipeline-stepper__rejected {
  margin: var(--space-3) 0 0;
  font-size: 0.8rem;
  color: var(--color-text-muted);
}

@media (max-width: 640px) {
  .pipeline-stepper__stages { flex-wrap: wrap; }
  .pipeline-stage { flex: 1 1 30%; }
}
</style>
