import { ref } from 'vue'
import { defineStore } from 'pinia'
import { useApiFetch } from '../../composables/useApi'

export const useLicenseStore = defineStore('settings/license', () => {
  const tier = ref<string>('free')
  const licenseKey = ref<string | null>(null)
  const active = ref(false)
  const gracePeriodEnds = ref<string | null>(null)
  const loading = ref(false)
  const activating = ref(false)
  const activateError = ref<string | null>(null)

  async function loadLicense() {
    loading.value = true
    const { data } = await useApiFetch<{tier: string; key: string | null; active: boolean; grace_period_ends?: string}>('/api/settings/license')
    loading.value = false
    if (!data) return
    tier.value = data.tier
    licenseKey.value = data.key
    active.value = data.active
    gracePeriodEnds.value = data.grace_period_ends ?? null
  }

  async function activate(key: string) {
    activating.value = true
    activateError.value = null
    const { data } = await useApiFetch<{ok: boolean; tier?: string; error?: string}>(
      '/api/settings/license/activate',
      { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ key }) }
    )
    activating.value = false
    if (!data) { activateError.value = 'Request failed'; return }
    if (data.ok) {
      active.value = true
      tier.value = data.tier ?? tier.value
      licenseKey.value = key
    } else {
      activateError.value = data.error ?? 'Activation failed'
    }
  }

  async function deactivate() {
    await useApiFetch('/api/settings/license/deactivate', { method: 'POST' })
    active.value = false
    licenseKey.value = null
    tier.value = 'free'
  }

  return { tier, licenseKey, active, gracePeriodEnds, loading, activating, activateError, loadLicense, activate, deactivate }
})
