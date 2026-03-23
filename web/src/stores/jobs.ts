import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { useApiFetch } from '../composables/useApi'

export interface JobCounts {
  pending:   number
  approved:  number
  applied:   number
  synced:    number
  rejected:  number
  total:     number
}

export interface SystemStatus {
  enrichment_enabled:   boolean
  enrichment_last_run:  string | null
  enrichment_next_run:  string | null
  tasks_running:        number
  integration_name:     string | null   // e.g. "Notion", "Airtable"
  integration_unsynced: number
}

// Pinia setup store — function form, not options form (gotcha #10)
export const useJobsStore = defineStore('jobs', () => {
  const counts      = ref<JobCounts | null>(null)
  const status      = ref<SystemStatus | null>(null)
  const loading     = ref(false)
  const error       = ref<string | null>(null)

  const hasPending = computed(() => (counts.value?.pending ?? 0) > 0)

  async function fetchCounts() {
    loading.value = true
    const { data, error: err } = await useApiFetch<JobCounts>('/api/jobs/counts')
    loading.value = false
    if (err) { error.value = err.kind === 'network' ? 'Network error' : `Error ${err.status}`; return }
    counts.value = data
  }

  async function fetchStatus() {
    const { data } = await useApiFetch<SystemStatus>('/api/system/status')
    if (data) status.value = data
  }

  async function refresh() {
    await Promise.all([fetchCounts(), fetchStatus()])
  }

  return { counts, status, loading, error, hasPending, fetchCounts, fetchStatus, refresh }
})
