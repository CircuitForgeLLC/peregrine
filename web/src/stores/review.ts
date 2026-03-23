import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { useApiFetch } from '../composables/useApi'

export interface Job {
  id:           number
  title:        string
  company:      string
  url:          string
  source:       string | null
  location:     string | null
  is_remote:    boolean
  salary:       string | null
  description:  string | null
  match_score:  number | null
  keyword_gaps: string | null  // JSON-encoded string[]
  date_found:   string
  status:       string
}

interface UndoEntry {
  job:        Job
  action:     'approve' | 'reject' | 'skip'
  prevStatus: string
}

// Stoop speed: 10 cards in 60 seconds — easter egg 9.2
const STOOP_CARDS = 10
const STOOP_SECS  = 60

export const useReviewStore = defineStore('review', () => {
  const queue    = ref<Job[]>([])
  const listJobs = ref<Job[]>([])
  const loading  = ref(false)
  const error    = ref<string | null>(null)

  const undoStack      = ref<UndoEntry[]>([])
  const sessionStart   = ref<number | null>(null)
  const sessionCount   = ref(0)
  const stoopAchieved  = ref(false)

  const currentJob = computed(() => queue.value[0] ?? null)
  const remaining  = computed(() => queue.value.length)

  const isStoopSpeed = computed(() => {
    if (stoopAchieved.value || !sessionStart.value) return false
    const elapsed = (Date.now() - sessionStart.value) / 1000
    return sessionCount.value >= STOOP_CARDS && elapsed <= STOOP_SECS
  })

  async function fetchQueue() {
    loading.value = true
    error.value   = null
    const { data, error: err } = await useApiFetch<Job[]>('/api/jobs?status=pending&limit=50')
    loading.value = false
    if (err) { error.value = 'Failed to load queue'; return }
    queue.value = data ?? []
    // Start session clock on first load with items
    if (!sessionStart.value && queue.value.length > 0) {
      sessionStart.value = Date.now()
      sessionCount.value = 0
    }
  }

  async function fetchList(status: string) {
    loading.value = true
    error.value   = null
    const { data, error: err } = await useApiFetch<Job[]>(`/api/jobs?status=${encodeURIComponent(status)}`)
    loading.value = false
    if (err) { error.value = 'Failed to load jobs'; return }
    listJobs.value = data ?? []
  }

  async function approve(job: Job) {
    const { error: err } = await useApiFetch(`/api/jobs/${job.id}/approve`, { method: 'POST' })
    if (err) return false
    undoStack.value.push({ job, action: 'approve', prevStatus: job.status })
    queue.value = queue.value.filter(j => j.id !== job.id)
    _tickSession()
    return true
  }

  async function reject(job: Job) {
    const { error: err } = await useApiFetch(`/api/jobs/${job.id}/reject`, { method: 'POST' })
    if (err) return false
    undoStack.value.push({ job, action: 'reject', prevStatus: job.status })
    queue.value = queue.value.filter(j => j.id !== job.id)
    _tickSession()
    return true
  }

  function skip(job: Job) {
    // Skip: move current card to back of queue without API call
    queue.value = queue.value.filter(j => j.id !== job.id)
    queue.value.push(job)
    undoStack.value.push({ job, action: 'skip', prevStatus: job.status })
    _tickSession()
    return true
  }

  async function undo() {
    const entry = undoStack.value.pop()
    if (!entry) return false
    const { job, action } = entry
    if (action === 'skip') {
      // Was at back of queue — remove from wherever it landed, put at front
      queue.value = queue.value.filter(j => j.id !== job.id)
      queue.value.unshift(job)
    } else {
      await useApiFetch(`/api/jobs/${job.id}/revert`, {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({ status: entry.prevStatus }),
      })
      queue.value.unshift(job)
    }
    sessionCount.value = Math.max(0, sessionCount.value - 1)
    return true
  }

  function _tickSession() {
    sessionCount.value++
  }

  function markStoopAchieved() {
    stoopAchieved.value = true
  }

  function resetSession() {
    sessionStart.value  = Date.now()
    sessionCount.value  = 0
    stoopAchieved.value = false
  }

  return {
    queue, listJobs, loading, error,
    undoStack,
    currentJob, remaining,
    sessionCount, isStoopSpeed, stoopAchieved,
    fetchQueue, fetchList,
    approve, reject, skip, undo,
    markStoopAchieved, resetSession,
  }
})
