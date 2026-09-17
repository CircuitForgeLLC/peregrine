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

export const useOnboardingHubStore = defineStore('onboardingHub', () => {
  const sections = ref<SectionStatus>({ ...EMPTY_SECTIONS })
  const loading = ref(false)

  async function loadSections(): Promise<void> {
    loading.value = true
    const { data } = await useApiFetch<{ sections: SectionStatus }>('/api/wizard/status')
    loading.value = false
    sections.value = data?.sections ?? { ...EMPTY_SECTIONS }
  }

  return { sections, loading, loadSections }
})
