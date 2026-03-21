import { ref } from 'vue'
import { defineStore } from 'pinia'
import { useApiFetch } from '../composables/useApi'

export interface ResearchBrief {
  company_brief: string | null
  ceo_brief: string | null
  talking_points: string | null
  tech_brief: string | null
  funding_brief: string | null
  red_flags: string | null
  accessibility_brief: string | null
  generated_at: string | null
}

export interface Contact {
  id: number
  direction: 'inbound' | 'outbound'
  subject: string | null
  from_addr: string | null
  body: string | null
  received_at: string | null
}

export interface TaskStatus {
  status: 'queued' | 'running' | 'completed' | 'failed' | 'none' | null
  stage: string | null
  message: string | null
}

export interface FullJobDetail {
  id: number
  title: string
  company: string
  url: string | null
  description: string | null
  cover_letter: string | null
  match_score: number | null
  keyword_gaps: string | null
}

export const usePrepStore = defineStore('prep', () => {
  const research = ref<ResearchBrief | null>(null)
  const contacts = ref<Contact[]>([])
  const taskStatus = ref<TaskStatus>({ status: null, stage: null, message: null })
  const fullJob = ref<FullJobDetail | null>(null)
  const loading = ref(false)
  const error = ref<string | null>(null)
  const currentJobId = ref<number | null>(null)

  let pollInterval: ReturnType<typeof setInterval> | null = null

  function _clearInterval() {
    if (pollInterval !== null) {
      clearInterval(pollInterval)
      pollInterval = null
    }
  }

  async function fetchFor(jobId: number) {
    if (jobId !== currentJobId.value) {
      _clearInterval()
      research.value = null
      contacts.value = []
      taskStatus.value = { status: null, stage: null, message: null }
      fullJob.value = null
      error.value = null
      currentJobId.value = jobId
    }

    loading.value = true
    try {
      const [researchResult, contactsResult, taskResult, jobResult] = await Promise.all([
        useApiFetch<ResearchBrief>(`/api/jobs/${jobId}/research`),
        useApiFetch<Contact[]>(`/api/jobs/${jobId}/contacts`),
        useApiFetch<TaskStatus>(`/api/jobs/${jobId}/research/task`),
        useApiFetch<FullJobDetail>(`/api/jobs/${jobId}`),
      ])

      research.value = researchResult.data ?? null
      contacts.value = (contactsResult.data as Contact[]) ?? []
      taskStatus.value = (taskResult.data as TaskStatus) ?? { status: null, stage: null, message: null }
      fullJob.value = (jobResult.data as FullJobDetail) ?? null

      // If a task is already running/queued, start polling
      const ts = taskStatus.value.status
      if (ts === 'queued' || ts === 'running') {
        pollTask(jobId)
      }
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'Failed to load prep data'
    } finally {
      loading.value = false
    }
  }

  async function generateResearch(jobId: number) {
    await useApiFetch<unknown>(`/api/jobs/${jobId}/research/generate`, { method: 'POST' })
    pollTask(jobId)
  }

  function pollTask(jobId: number) {
    _clearInterval()
    pollInterval = setInterval(async () => {
      const { data } = await useApiFetch<TaskStatus>(`/api/jobs/${jobId}/research/task`)
      if (data) {
        taskStatus.value = data as TaskStatus
        if (data.status === 'completed' || data.status === 'failed') {
          _clearInterval()
          if (data.status === 'completed') {
            await fetchFor(jobId)
          }
        }
      }
    }, 3000)
  }

  function clear() {
    _clearInterval()
    research.value = null
    contacts.value = []
    taskStatus.value = { status: null, stage: null, message: null }
    fullJob.value = null
    loading.value = false
    error.value = null
    currentJobId.value = null
  }

  return {
    research,
    contacts,
    taskStatus,
    fullJob,
    loading,
    error,
    currentJobId,
    fetchFor,
    generateResearch,
    pollTask,
    clear,
  }
})
