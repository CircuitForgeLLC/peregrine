import { ref } from 'vue'
import { defineStore } from 'pinia'
import { useApiFetch } from '../composables/useApi'

export type Tier = 'free' | 'paid' | 'premium' | 'ultra'
export type InferenceProfile = 'remote' | 'cpu' | 'single-gpu' | 'dual-gpu'

export const useAppConfigStore = defineStore('appConfig', () => {
  const isCloud = ref(false)
  const isDevMode = ref(false)
  const tier = ref<Tier>('free')
  const contractedClient = ref(false)
  const inferenceProfile = ref<InferenceProfile>('cpu')
  const isDemo = ref(false)
  const wizardComplete = ref(true)  // optimistic default — guard corrects on load
  const loaded = ref(false)
  const devTierOverride = ref(localStorage.getItem('dev_tier_override') ?? '')

  async function load() {
    const { data } = await useApiFetch<{
      isCloud: boolean; isDemo: boolean; isDevMode: boolean; tier: Tier
      contractedClient: boolean; inferenceProfile: InferenceProfile
      wizardComplete: boolean
    }>('/api/config/app')
    if (!data) return
    isCloud.value = data.isCloud
    isDemo.value = data.isDemo ?? false
    isDevMode.value = data.isDevMode
    tier.value = data.tier
    contractedClient.value = data.contractedClient
    inferenceProfile.value = data.inferenceProfile
    wizardComplete.value = data.wizardComplete ?? true
    loaded.value = true
  }

  function setDevTierOverride(value: string | null) {
    if (value) {
      localStorage.setItem('dev_tier_override', value)
      devTierOverride.value = value
    } else {
      localStorage.removeItem('dev_tier_override')
      devTierOverride.value = ''
    }
  }

  return { isCloud, isDemo, isDevMode, wizardComplete, tier, contractedClient, inferenceProfile, loaded, load, devTierOverride, setDevTierOverride }
})
