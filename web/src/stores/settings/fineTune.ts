import { ref } from 'vue'
import { defineStore } from 'pinia'
import { useApiFetch } from '../../composables/useApi'
import { useAppConfigStore } from '../appConfig'
import { showToast } from '../../composables/useToast'

export interface TrainingPair {
  index: number
  instruction: string
  source_file: string
}

export interface DbPair {
  job_id: number
  title: string
  company: string
  status: string
  instruction: string
  input_preview: string
  excluded: boolean
}

export const useFineTuneStore = defineStore('settings/fineTune', () => {
  const step = ref(1)
  const inFlightJob = ref(false)
  const jobStatus = ref<string>('idle')
  const pairsCount = ref(0)
  const quotaRemaining = ref<number | null>(null)
  const uploading = ref(false)
  const loading = ref(false)
  const pairs = ref<TrainingPair[]>([])
  const pairsLoading = ref(false)
  let _pollTimer: ReturnType<typeof setInterval> | null = null

  const optedIn = ref(false)
  const dbPairs = ref<DbPair[]>([])
  const dbPairsLoading = ref(false)
  const dbExcludedCount = ref(0)

  function resetStep() { step.value = 1 }

  async function loadStatus() {
    const { data } = await useApiFetch<{ status: string; pairs_count: number; quota_remaining?: number }>('/api/settings/fine-tune/status')
    if (!data) return
    jobStatus.value = data.status
    pairsCount.value = data.pairs_count ?? 0
    quotaRemaining.value = data.quota_remaining ?? null
    inFlightJob.value = ['queued', 'running'].includes(data.status)
    optedIn.value = (data as any).opted_in ?? false
  }

  function startPolling() {
    loadStatus()
    _pollTimer = setInterval(loadStatus, 2000)
  }

  function stopPolling() {
    if (_pollTimer !== null) { clearInterval(_pollTimer); _pollTimer = null }
  }

  async function submitJob() {
    if (useAppConfigStore().isDemo) { showToast('AI features are disabled in demo mode'); return }
    const { data, error } = await useApiFetch<{ job_id: string }>('/api/settings/fine-tune/submit', { method: 'POST' })
    if (!error && data) { inFlightJob.value = true; jobStatus.value = 'queued' }
  }

  async function loadPairs() {
    pairsLoading.value = true
    const { data } = await useApiFetch<{ pairs: TrainingPair[]; total: number }>('/api/settings/fine-tune/pairs')
    pairsLoading.value = false
    if (data) {
      pairs.value = data.pairs
      pairsCount.value = data.total
    }
  }

  async function deletePair(index: number) {
    const { data } = await useApiFetch<{ ok: boolean; remaining: number }>(
      `/api/settings/fine-tune/pairs/${index}`, { method: 'DELETE' }
    )
    if (data?.ok) {
      pairs.value = pairs.value.filter(p => p.index !== index).map((p, i) => ({ ...p, index: i }))
      pairsCount.value = data.remaining
    }
  }

  async function toggleOptIn(enabled: boolean) {
    const { data } = await useApiFetch<{ ok: boolean; enabled: boolean }>(
      '/api/settings/fine-tune/opt-in',
      { method: 'PATCH', body: JSON.stringify({ enabled }), headers: { 'Content-Type': 'application/json' } },
    )
    if (data) optedIn.value = data.enabled
  }

  async function loadDbPairs() {
    if (!optedIn.value) { dbPairs.value = []; return }
    dbPairsLoading.value = true
    const { data } = await useApiFetch<{ pairs: DbPair[]; total: number; excluded_count: number }>(
      '/api/settings/fine-tune/db-pairs',
    )
    dbPairsLoading.value = false
    if (data) {
      dbPairs.value = data.pairs
      dbExcludedCount.value = data.excluded_count
    }
  }

  async function excludeDbPair(jobId: number) {
    const { data } = await useApiFetch<{ ok: boolean }>(
      `/api/settings/fine-tune/db-pairs/${jobId}/exclude`,
      { method: 'PATCH' },
    )
    if (data?.ok) {
      dbPairs.value = dbPairs.value.map(p =>
        p.job_id === jobId ? { ...p, excluded: true } : p,
      )
      dbExcludedCount.value += 1
    }
  }

  async function includeDbPair(jobId: number) {
    const { data } = await useApiFetch<{ ok: boolean }>(
      `/api/settings/fine-tune/db-pairs/${jobId}/include`,
      { method: 'PATCH' },
    )
    if (data?.ok) {
      dbPairs.value = dbPairs.value.map(p =>
        p.job_id === jobId ? { ...p, excluded: false } : p,
      )
      dbExcludedCount.value = Math.max(0, dbExcludedCount.value - 1)
    }
  }

  function downloadExport() {
    const a = document.createElement('a')
    a.href = '/api/settings/fine-tune/export'
    a.download = 'peregrine_training_pairs.jsonl'
    a.click()
  }

  return {
    step,
    inFlightJob,
    jobStatus,
    pairsCount,
    quotaRemaining,
    uploading,
    loading,
    pairs,
    pairsLoading,
    resetStep,
    loadStatus,
    startPolling,
    stopPolling,
    submitJob,
    loadPairs,
    deletePair,
    optedIn,
    dbPairs,
    dbPairsLoading,
    dbExcludedCount,
    toggleOptIn,
    loadDbPairs,
    excludeDbPair,
    includeDbPair,
    downloadExport,
  }
})
