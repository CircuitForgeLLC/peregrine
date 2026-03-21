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
  const loaded = ref(false)

  async function load() {
    const { data } = await useApiFetch<{
      isCloud: boolean; isDevMode: boolean; tier: Tier
      contractedClient: boolean; inferenceProfile: InferenceProfile
    }>('/api/config/app')
    if (!data) return
    isCloud.value = data.isCloud
    isDevMode.value = data.isDevMode
    tier.value = data.tier
    contractedClient.value = data.contractedClient
    inferenceProfile.value = data.inferenceProfile
    loaded.value = true
  }

  return { isCloud, isDevMode, tier, contractedClient, inferenceProfile, loaded, load }
})
