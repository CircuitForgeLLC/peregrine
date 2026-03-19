import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { useApiFetch } from '../composables/useApi'

export interface StageSignal {
  id: number              // job_contacts.id — used for POST /api/stage-signals/{id}/dismiss
  subject: string
  received_at: string     // ISO timestamp
  stage_signal: 'interview_scheduled' | 'positive_response' | 'offer_received' | 'survey_received' | 'rejected'
}

export interface PipelineJob {
  id:               number
  title:            string
  company:          string
  url:              string | null
  location:         string | null
  is_remote:        boolean
  salary:           string | null
  match_score:      number | null
  keyword_gaps:     string | null
  status:           string
  interview_date:   string | null
  rejection_stage:  string | null
  applied_at:       string | null
  phone_screen_at:  string | null
  interviewing_at:  string | null
  offer_at:         string | null
  hired_at:         string | null
  survey_at:        string | null
  stage_signals:    StageSignal[]  // undismissed signals, newest first
}

export const PIPELINE_STAGES = ['applied', 'survey', 'phone_screen', 'interviewing', 'offer', 'hired', 'interview_rejected'] as const
export type PipelineStage = typeof PIPELINE_STAGES[number]

export const STAGE_LABELS: Record<PipelineStage, string> = {
  applied:            'Applied',
  survey:             'Survey',
  phone_screen:       'Phone Screen',
  interviewing:       'Interviewing',
  offer:              'Offer',
  hired:              'Hired',
  interview_rejected: 'Rejected',
}

export const useInterviewsStore = defineStore('interviews', () => {
  const jobs    = ref<PipelineJob[]>([])
  const loading = ref(false)
  const error   = ref<string | null>(null)

  const applied      = computed(() => jobs.value.filter(j => j.status === 'applied'))
  const survey       = computed(() => jobs.value.filter(j => j.status === 'survey'))
  const phoneScreen  = computed(() => jobs.value.filter(j => j.status === 'phone_screen'))
  const interviewing = computed(() => jobs.value.filter(j => j.status === 'interviewing'))
  const offer        = computed(() => jobs.value.filter(j => j.status === 'offer'))
  const hired        = computed(() => jobs.value.filter(j => j.status === 'hired'))
  const offerHired   = computed(() => jobs.value.filter(j => j.status === 'offer' || j.status === 'hired'))
  const rejected     = computed(() => jobs.value.filter(j => j.status === 'interview_rejected'))

  async function fetchAll() {
    loading.value = true
    const { data, error: err } = await useApiFetch<PipelineJob[]>('/api/interviews')
    loading.value = false
    if (err) { error.value = 'Could not load interview pipeline'; return }
    jobs.value = (data ?? []).map(j => ({ ...j }))
  }

  async function move(jobId: number, status: PipelineStage, opts: { interview_date?: string; rejection_stage?: string } = {}) {
    const job = jobs.value.find(j => j.id === jobId)
    if (!job) return
    const prevStatus = job.status
    job.status = status

    const { error: err } = await useApiFetch(`/api/jobs/${jobId}/move`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status, ...opts }),
    })

    if (err) {
      job.status = prevStatus
      error.value = 'Move failed — please try again'
    }
  }

  return { jobs, loading, error, applied, survey, phoneScreen, interviewing, offer, hired, offerHired, rejected, fetchAll, move }
})
