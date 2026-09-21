import { ref } from 'vue'
import { defineStore } from 'pinia'
import { useApiFetch } from '../composables/useApi'

export interface SectionStatus {
  profile: boolean
  resume: boolean
  search: boolean
  compute_backend: boolean
}

const EMPTY_SECTIONS: SectionStatus = {
  profile: false,
  resume: false,
  search: false,
  compute_backend: false,
}

interface WizardStatusResponse {
  sections: SectionStatus
  connections_acknowledged: boolean
  setup_path: 'ai' | 'manual' | null
}

export const useOnboardingHubStore = defineStore('onboardingHub', () => {
  const sections = ref<SectionStatus>({ ...EMPTY_SECTIONS })
  const connectionsAcknowledged = ref(false)
  const setupPath = ref<'ai' | 'manual' | null>(null)
  const loading = ref(false)

  async function loadSections(): Promise<void> {
    loading.value = true
    const { data } = await useApiFetch<WizardStatusResponse>('/api/wizard/status')
    loading.value = false
    sections.value = data?.sections ?? { ...EMPTY_SECTIONS }
    connectionsAcknowledged.value = data?.connections_acknowledged ?? false
    setupPath.value = data?.setup_path ?? null
  }

  return { sections, connectionsAcknowledged, setupPath, loading, loadSections }
})
