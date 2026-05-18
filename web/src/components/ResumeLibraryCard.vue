<template>
  <div class="rlc">
    <div class="rlc__header">
      <h3 class="rlc__title"><span aria-hidden="true">📄</span> Resume</h3>
      <div class="rlc__actions">
        <button class="btn-secondary rlc__switch" @click="showPicker = !showPicker">Switch</button>
        <RouterLink to="/resumes" class="btn-secondary rlc__manage">Manage</RouterLink>
      </div>
    </div>

    <div v-if="loading" class="rlc__loading">Loading…</div>

    <div v-else-if="resume" class="rlc__resume">
      <span class="rlc__name">{{ resume.name }}</span>
      <span class="rlc__meta">{{ resume.word_count }} words</span>
      <span v-if="resume.job_id === jobId" class="rlc__optimized-badge">✦ Optimized for this job</span>
    </div>

    <div v-else class="rlc__empty">
      No resume attached.
      <RouterLink to="/resumes" class="rlc__import-link">Import one</RouterLink>
      or optimize below.
    </div>

    <!-- Picker dropdown -->
    <div v-if="showPicker && allResumes.length" class="rlc__picker">
      <ul class="rlc__picker-list">
        <li
          v-for="r in allResumes"
          :key="r.id"
          class="rlc__picker-item"
          :class="{ 'rlc__picker-item--active': resume?.id === r.id }"
          @click="switchResume(r.id)"
        >
          <span>{{ r.name }}</span>
          <span class="rlc__picker-meta">{{ r.word_count }}w</span>
        </li>
      </ul>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { RouterLink } from 'vue-router'
import { useApiFetch } from '../composables/useApi'

interface Resume {
  id: number
  name: string
  word_count: number
  job_id: number | null
  is_default: number
}

const props = defineProps<{ jobId: number }>()

const resume     = ref<Resume | null>(null)
const allResumes = ref<Resume[]>([])
const loading    = ref(true)
const showPicker = ref(false)

async function load() {
  loading.value = true
  const [jobRes, listRes] = await Promise.all([
    useApiFetch<Resume>(`/api/jobs/${props.jobId}/resume`),
    useApiFetch<{ resumes: Resume[] }>('/api/resumes'),
  ])
  resume.value = jobRes.data ?? null
  allResumes.value = listRes.data?.resumes ?? []
  loading.value = false
}

async function switchResume(resumeId: number) {
  showPicker.value = false
  const { data } = await useApiFetch<Resume>(
    `/api/jobs/${props.jobId}/resume`,
    {
      method: 'PATCH',
      body: JSON.stringify({ resume_id: resumeId }),
      headers: { 'Content-Type': 'application/json' },
    }
  )
  if (data) resume.value = data
}

onMounted(load)
</script>

<style scoped>
.rlc {
  background: var(--color-surface-alt, #f8fafc);
  border: 1px solid var(--color-border, #e2e8f0);
  border-radius: var(--radius-md, 0.5rem);
  padding: var(--space-3, 0.75rem) var(--space-4, 1rem);
  display: flex;
  flex-direction: column;
  gap: var(--space-2, 0.5rem);
  position: relative;
}

.rlc__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.rlc__title {
  font-size: var(--text-sm);
  font-weight: 600;
  margin: 0;
  display: flex;
  align-items: center;
  gap: var(--space-2, 0.5rem);
}

.rlc__actions {
  display: flex;
  gap: var(--space-2, 0.5rem);
}

.rlc__resume {
  display: flex;
  align-items: center;
  gap: var(--space-2, 0.5rem);
  flex-wrap: wrap;
}

.rlc__name {
  font-weight: 500;
  font-size: var(--text-sm);
}

.rlc__meta {
  font-size: var(--font-xs, 0.75rem);
  color: var(--color-text-muted, #64748b);
}

.rlc__optimized-badge {
  font-size: var(--font-xs, 0.75rem);
  color: var(--color-accent, #6366f1);
  font-weight: 500;
}

.rlc__empty {
  font-size: var(--text-sm);
  color: var(--color-text-muted, #64748b);
}

.rlc__import-link {
  color: var(--color-accent, #6366f1);
  text-decoration: underline;
}

.rlc__loading {
  font-size: var(--text-sm);
  color: var(--color-text-muted, #64748b);
}

.rlc__picker {
  position: absolute;
  top: 100%;
  left: 0;
  right: 0;
  z-index: 10;
  background: var(--color-surface, #fff);
  border: 1px solid var(--color-border, #e2e8f0);
  border-radius: var(--radius-md, 0.5rem);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
  margin-top: 4px;
}

.rlc__picker-list {
  list-style: none;
  margin: 0;
  padding: var(--space-1, 0.25rem);
}

.rlc__picker-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--space-2, 0.5rem) var(--space-3, 0.75rem);
  cursor: pointer;
  border-radius: var(--radius-sm, 0.25rem);
  font-size: var(--text-sm);
}

.rlc__picker-item:hover,
.rlc__picker-item--active {
  background: var(--color-surface-alt, #f8fafc);
}

.rlc__picker-meta {
  font-size: var(--font-xs, 0.75rem);
  color: var(--color-text-muted, #64748b);
}
</style>
