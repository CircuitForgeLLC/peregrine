import { ref } from 'vue'
import { defineStore } from 'pinia'
import { useApiFetch } from '../../composables/useApi'

const CLOUD_BACKEND_IDS = ['anthropic', 'openai']

export interface Backend { id: string; enabled: boolean; priority: number }

export const useSystemStore = defineStore('settings/system', () => {
  const backends = ref<Backend[]>([])
  const byokAcknowledged = ref<string[]>([])
  const byokPending = ref<string[]>([])
  // Private snapshot — NOT in return(). Closure-level only.
  let _preSaveSnapshot: Backend[] = []
  const saving = ref(false)
  const saveError = ref<string | null>(null)
  const loadError = ref<string | null>(null)

  async function loadLlm() {
    loadError.value = null
    const { data, error } = await useApiFetch<{ backends: Backend[]; byok_acknowledged: string[] }>('/api/settings/system/llm')
    if (error) { loadError.value = 'Failed to load LLM config'; return }
    if (!data) return
    backends.value = data.backends ?? []
    byokAcknowledged.value = data.byok_acknowledged ?? []
  }

  async function trySave() {
    _preSaveSnapshot = JSON.parse(JSON.stringify(backends.value))
    const newlyEnabled = backends.value
      .filter(b => CLOUD_BACKEND_IDS.includes(b.id) && b.enabled)
      .map(b => b.id)
      .filter(id => !byokAcknowledged.value.includes(id))
    if (newlyEnabled.length > 0) {
      byokPending.value = newlyEnabled
      return  // modal takes over
    }
    await _commitSave()
  }

  async function confirmByok() {
    saving.value = true
    const { error } = await useApiFetch('/api/settings/system/llm/byok-ack', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ backends: byokPending.value }),
    })
    if (!error) byokAcknowledged.value = [...byokAcknowledged.value, ...byokPending.value]
    byokPending.value = []
    await _commitSave()
  }

  function cancelByok() {
    backends.value = JSON.parse(JSON.stringify(_preSaveSnapshot))
    byokPending.value = []
    _preSaveSnapshot = []
  }

  async function _commitSave() {
    saving.value = true
    saveError.value = null
    const { error } = await useApiFetch('/api/settings/system/llm', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ backends: backends.value }),
    })
    saving.value = false
    if (error) saveError.value = 'Save failed — please try again.'
  }

  // Services, email, integrations added in Task 6
  return { backends, byokAcknowledged, byokPending, saving, saveError, loadError, loadLlm, trySave, confirmByok, cancelByok }
})
