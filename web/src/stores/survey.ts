import { ref } from 'vue'
import { defineStore } from 'pinia'
import { useApiFetch } from '../composables/useApi'

const validSources = ['text_paste', 'screenshot'] as const
type ValidSource = typeof validSources[number]
function isValidSource(s: string): s is ValidSource {
  return validSources.includes(s as ValidSource)
}

export interface SurveyAnalysis {
  output: string
  source: 'text_paste' | 'screenshot'
  mode: 'quick' | 'detailed'
  rawInput: string | null
}

export interface SurveyResponse {
  id: number
  survey_name: string | null
  mode: 'quick' | 'detailed'
  source: string
  raw_input: string | null
  image_path: string | null
  llm_output: string
  reported_score: string | null
  received_at: string | null
  created_at: string | null
}

export const useSurveyStore = defineStore('survey', () => {
  const analysis = ref<SurveyAnalysis | null>(null)
  const history = ref<SurveyResponse[]>([])
  const loading = ref(false)
  const saving = ref(false)
  const error = ref<string | null>(null)
  const visionAvailable = ref(false)
  const currentJobId = ref<number | null>(null)

  async function fetchFor(jobId: number) {
    if (jobId !== currentJobId.value) {
      analysis.value = null
      history.value = []
      error.value = null
      visionAvailable.value = false
      currentJobId.value = jobId
    }

    loading.value = true
    try {
      const [historyResult, visionResult] = await Promise.all([
        useApiFetch<SurveyResponse[]>(`/api/jobs/${jobId}/survey/responses`),
        useApiFetch<{ available: boolean }>('/api/vision/health'),
      ])

      if (historyResult.error) {
        error.value = 'Could not load survey history.'
      } else {
        history.value = historyResult.data ?? []
      }

      visionAvailable.value = visionResult.data?.available ?? false
    } finally {
      loading.value = false
    }
  }

  async function analyze(
    jobId: number,
    payload: { text?: string; image_b64?: string; mode: 'quick' | 'detailed' }
  ) {
    loading.value = true
    error.value = null
    const { data, error: fetchError } = await useApiFetch<{ output: string; source: string }>(
      `/api/jobs/${jobId}/survey/analyze`,
      { method: 'POST', body: JSON.stringify(payload) }
    )
    loading.value = false
    if (fetchError || !data) {
      error.value = 'Analysis failed. Please try again.'
      return
    }
    analysis.value = {
      output: data.output,
      source: isValidSource(data.source) ? data.source : 'text_paste',
      mode: payload.mode,
      rawInput: payload.text ?? null,
    }
  }

  async function saveResponse(
    jobId: number,
    args: { surveyName: string; reportedScore: string; image_b64?: string }
  ) {
    if (!analysis.value) return
    saving.value = true
    error.value = null
    const body = {
      survey_name: args.surveyName || undefined,
      mode: analysis.value.mode,
      source: analysis.value.source,
      raw_input: analysis.value.rawInput,
      image_b64: args.image_b64,
      llm_output: analysis.value.output,
      reported_score: args.reportedScore || undefined,
    }
    const { data, error: fetchError } = await useApiFetch<{ id: number }>(
      `/api/jobs/${jobId}/survey/responses`,
      { method: 'POST', body: JSON.stringify(body) }
    )
    saving.value = false
    if (fetchError || !data) {
      error.value = 'Save failed. Your analysis is preserved — try again.'
      return
    }
    // Prepend the saved response to history
    const now = new Date().toISOString()
    const saved: SurveyResponse = {
      id: data.id,
      survey_name: args.surveyName || null,
      mode: analysis.value.mode,
      source: analysis.value.source,
      raw_input: analysis.value.rawInput,
      image_path: null,
      llm_output: analysis.value.output,
      reported_score: args.reportedScore || null,
      received_at: now,
      created_at: now,
    }
    history.value = [saved, ...history.value]
    analysis.value = null
  }

  function clear() {
    analysis.value = null
    history.value = []
    loading.value = false
    saving.value = false
    error.value = null
    visionAvailable.value = false
    currentJobId.value = null
  }

  return {
    analysis,
    history,
    loading,
    saving,
    error,
    visionAvailable,
    currentJobId,
    fetchFor,
    analyze,
    saveResponse,
    clear,
  }
})
