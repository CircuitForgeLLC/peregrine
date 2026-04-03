import { ref, computed } from 'vue'
import { defineStore } from 'pinia'
import { useApiFetch } from '../composables/useApi'

export type WizardProfile = 'remote' | 'cpu' | 'single-gpu' | 'dual-gpu'
export type WizardTier = 'free' | 'paid' | 'premium'

export interface WorkExperience {
  title: string
  company: string
  start_date: string
  end_date: string
  bullets: string[]
}

export interface WizardHardwareData {
  gpus: string[]
  suggestedProfile: WizardProfile
  selectedProfile: WizardProfile
}

export interface WizardSearchData {
  titles: string[]
  locations: string[]
}

export interface WizardIdentityData {
  name: string
  email: string
  phone: string
  linkedin: string
  careerSummary: string
}

export interface WizardInferenceData {
  anthropicKey: string
  openaiUrl: string
  openaiKey: string
  ollamaHost: string
  ollamaPort: number
  services: Record<string, string | number>
  confirmed: boolean
  testMessage: string
}

// Total mandatory steps (integrations step 7 is optional/skip-able)
export const WIZARD_STEPS = 6
export const STEP_LABELS = ['Hardware', 'Tier', 'Resume', 'Identity', 'Inference', 'Search', 'Integrations']
export const STEP_ROUTES = [
  '/setup/hardware',
  '/setup/tier',
  '/setup/resume',
  '/setup/identity',
  '/setup/inference',
  '/setup/search',
  '/setup/integrations',
]

export const useWizardStore = defineStore('wizard', () => {
  // ── Navigation state ──────────────────────────────────────────────────────
  const currentStep = ref(1)       // 1-based; 7 = integrations (optional)
  const loading = ref(false)
  const saving = ref(false)
  const errors = ref<string[]>([])

  // ── Step data ─────────────────────────────────────────────────────────────
  const hardware = ref<WizardHardwareData>({
    gpus: [],
    suggestedProfile: 'remote',
    selectedProfile: 'remote',
  })

  const tier = ref<WizardTier>('free')

  const resume = ref<{ experience: WorkExperience[]; parsedData: Record<string, unknown> | null }>({
    experience: [],
    parsedData: null,
  })

  const identity = ref<WizardIdentityData>({
    name: '',
    email: '',
    phone: '',
    linkedin: '',
    careerSummary: '',
  })

  const inference = ref<WizardInferenceData>({
    anthropicKey: '',
    openaiUrl: '',
    openaiKey: '',
    ollamaHost: 'localhost',
    ollamaPort: 11434,
    services: {},
    confirmed: false,
    testMessage: '',
  })

  const search = ref<WizardSearchData>({
    titles: [],
    locations: [],
  })

  // ── Computed ──────────────────────────────────────────────────────────────
  const progressFraction = computed(() =>
    Math.min((currentStep.value - 1) / WIZARD_STEPS, 1),
  )

  const stepLabel = computed(() =>
    currentStep.value <= WIZARD_STEPS
      ? `Step ${currentStep.value} of ${WIZARD_STEPS}`
      : 'Almost done!',
  )

  const routeForStep = (step: number) => STEP_ROUTES[step - 1] ?? '/setup/hardware'

  // ── Actions ───────────────────────────────────────────────────────────────

  /** Load wizard status from server and hydrate store. Returns the route to navigate to. */
  async function loadStatus(isCloud: boolean): Promise<string> {
    loading.value = true
    errors.value = []
    try {
      const { data } = await useApiFetch<{
        wizard_complete: boolean
        wizard_step: number
        saved_data: {
          inference_profile?: string
          tier?: string
          name?: string
          email?: string
          phone?: string
          linkedin?: string
          career_summary?: string
          services?: Record<string, string | number>
        }
      }>('/api/wizard/status')

      if (!data) return '/setup/hardware'

      const saved = data.saved_data

      if (saved.inference_profile)
        hardware.value.selectedProfile = saved.inference_profile as WizardProfile
      if (saved.tier)
        tier.value = saved.tier as WizardTier
      if (saved.name) identity.value.name = saved.name
      if (saved.email) identity.value.email = saved.email
      if (saved.phone) identity.value.phone = saved.phone
      if (saved.linkedin) identity.value.linkedin = saved.linkedin
      if (saved.career_summary) identity.value.careerSummary = saved.career_summary
      if (saved.services) inference.value.services = saved.services

      // Cloud: auto-skip steps 1 (hardware), 2 (tier), 5 (inference)
      if (isCloud) {
        const cloudStep = data.wizard_step
        if (cloudStep < 1) {
          await saveStep(1, { inference_profile: 'single-gpu' })
          await saveStep(2, { tier: tier.value })
          currentStep.value = 3
          return '/setup/resume'
        }
      }

      // Resume at next step after last completed
      const resumeAt = Math.max(1, Math.min(data.wizard_step + 1, 7))
      currentStep.value = resumeAt
      return routeForStep(resumeAt)
    } finally {
      loading.value = false
    }
  }

  /** Detect GPUs and populate hardware step. */
  async function detectHardware(): Promise<void> {
    loading.value = true
    try {
      const { data } = await useApiFetch<{
        gpus: string[]
        suggested_profile: string
        profiles: string[]
      }>('/api/wizard/hardware')

      if (!data) return
      hardware.value.gpus = data.gpus
      hardware.value.suggestedProfile = data.suggested_profile as WizardProfile
      // Only set selectedProfile if not already chosen by user
      if (!hardware.value.selectedProfile || hardware.value.selectedProfile === 'remote') {
        hardware.value.selectedProfile = data.suggested_profile as WizardProfile
      }
    } finally {
      loading.value = false
    }
  }

  /** Persist a step's data to the server. */
  async function saveStep(step: number, data: Record<string, unknown>): Promise<boolean> {
    saving.value = true
    errors.value = []
    try {
      const { data: result, error } = await useApiFetch('/api/wizard/step', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ step, data }),
      })
      if (error) {
        errors.value = [error.kind === 'http' ? error.detail : error.message]
        return false
      }
      currentStep.value = step
      return true
    } finally {
      saving.value = false
    }
  }

  /** Test LLM / Ollama connectivity. */
  async function testInference(): Promise<{ ok: boolean; message: string }> {
    const payload = {
      profile: hardware.value.selectedProfile,
      anthropic_key: inference.value.anthropicKey,
      openai_url: inference.value.openaiUrl,
      openai_key: inference.value.openaiKey,
      ollama_host: inference.value.ollamaHost,
      ollama_port: inference.value.ollamaPort,
    }
    const { data } = await useApiFetch<{ ok: boolean; message: string }>(
      '/api/wizard/inference/test',
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      },
    )
    const result = data ?? { ok: false, message: 'No response from server.' }
    inference.value.testMessage = result.message
    inference.value.confirmed = true  // always soft-confirm so user isn't blocked
    return result
  }

  /** Finalise the wizard. */
  async function complete(): Promise<boolean> {
    saving.value = true
    try {
      const { error } = await useApiFetch('/api/wizard/complete', { method: 'POST' })
      if (error) {
        errors.value = [error.kind === 'http' ? error.detail : error.message]
        return false
      }
      return true
    } finally {
      saving.value = false
    }
  }

  return {
    // state
    currentStep,
    loading,
    saving,
    errors,
    hardware,
    tier,
    resume,
    identity,
    inference,
    search,
    // computed
    progressFraction,
    stepLabel,
    // actions
    loadStatus,
    detectHardware,
    saveStep,
    testInference,
    complete,
    routeForStep,
  }
})
