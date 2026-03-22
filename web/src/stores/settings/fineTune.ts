import { ref } from 'vue'
import { defineStore } from 'pinia'
import { useApiFetch } from '../../composables/useApi'

export const useFineTuneStore = defineStore('settings/fineTune', () => {
  const step = ref(1)
  const inFlightJob = ref(false)
  const jobStatus = ref<string>('idle')
  const pairsCount = ref(0)
  const quotaRemaining = ref<number | null>(null)
  const uploading = ref(false)
  const loading = ref(false)
  let _pollTimer: ReturnType<typeof setInterval> | null = null

  function resetStep() { step.value = 1 }

  async function loadStatus() {
    const { data } = await useApiFetch<{ status: string; pairs_count: number; quota_remaining?: number }>('/api/settings/fine-tune/status')
    if (!data) return
    jobStatus.value = data.status
    pairsCount.value = data.pairs_count ?? 0
    quotaRemaining.value = data.quota_remaining ?? null
    inFlightJob.value = ['queued', 'running'].includes(data.status)
  }

  function startPolling() {
    loadStatus()
    _pollTimer = setInterval(loadStatus, 2000)
  }

  function stopPolling() {
    if (_pollTimer !== null) { clearInterval(_pollTimer); _pollTimer = null }
  }

  async function submitJob() {
    const { data, error } = await useApiFetch<{ job_id: string }>('/api/settings/fine-tune/submit', { method: 'POST' })
    if (!error && data) { inFlightJob.value = true; jobStatus.value = 'queued' }
  }

  return {
    step,
    inFlightJob,
    jobStatus,
    pairsCount,
    quotaRemaining,
    uploading,
    loading,
    resetStep,
    loadStatus,
    startPolling,
    stopPolling,
    submitJob,
  }
})
