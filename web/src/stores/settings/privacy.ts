import { ref, computed } from 'vue'
import { defineStore } from 'pinia'
import { useApiFetch } from '../../composables/useApi'

export const usePrivacyStore = defineStore('settings/privacy', () => {
  // Session-scoped BYOK panel state
  const activeCloudBackends = ref<string[]>([])
  const byokInfoDismissed = ref(false)
  const dismissedForBackends = ref<string[]>([])

  // Self-hosted privacy prefs
  const telemetryOptIn = ref(false)

  // Cloud privacy prefs
  const masterOff = ref(false)
  const usageEvents = ref(true)
  const contentSharing = ref(false)

  const loading = ref(false)
  const saving = ref(false)

  // Panel shows if there are active cloud backends not yet covered by dismissal snapshot,
  // or if byokInfoDismissed was set directly (e.g. loaded from server) and new backends haven't appeared
  const showByokPanel = computed(() => {
    if (activeCloudBackends.value.length === 0) return false
    if (byokInfoDismissed.value && activeCloudBackends.value.every(b => dismissedForBackends.value.includes(b))) return false
    if (byokInfoDismissed.value && dismissedForBackends.value.length === 0) return false
    return !activeCloudBackends.value.every(b => dismissedForBackends.value.includes(b))
  })

  function dismissByokInfo() {
    dismissedForBackends.value = [...activeCloudBackends.value]
    byokInfoDismissed.value = true
  }

  async function loadPrivacy() {
    loading.value = true
    const { data } = await useApiFetch<Record<string, unknown>>('/api/settings/privacy')
    loading.value = false
    if (!data) return
    telemetryOptIn.value = Boolean(data.telemetry_opt_in)
    byokInfoDismissed.value = Boolean(data.byok_info_dismissed)
    masterOff.value = Boolean(data.master_off)
    usageEvents.value = data.usage_events !== false
    contentSharing.value = Boolean(data.content_sharing)
  }

  async function savePrivacy(prefs: Record<string, unknown>) {
    saving.value = true
    await useApiFetch('/api/settings/privacy', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(prefs),
    })
    saving.value = false
  }

  return {
    activeCloudBackends, byokInfoDismissed, dismissedForBackends,
    telemetryOptIn, masterOff, usageEvents, contentSharing,
    loading, saving, showByokPanel,
    dismissByokInfo, loadPrivacy, savePrivacy,
  }
})
