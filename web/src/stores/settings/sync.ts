import { defineStore } from 'pinia'
import { ref } from 'vue'
import { useApiFetch } from '../../composables/useApi'

export const SYNC_DATA_CLASSES = [
  { key: 'peregrine:dismissed', label: 'Dismissed job IDs',        description: 'Hides jobs you have already reviewed across devices.' },
  { key: 'peregrine:drafts',    label: 'Cover letter drafts',      description: 'Saves in-progress drafts so you can continue on another device.' },
] as const

export type SyncDataClass = typeof SYNC_DATA_CLASSES[number]['key']

export interface SyncPref {
  data_class: string
  enabled:    boolean
}

export const useSyncStore = defineStore('sync', () => {
  const prefs   = ref<Record<string, boolean>>({})
  const loading = ref(false)
  const saving  = ref<string | null>(null)
  const wiping  = ref(false)
  const error   = ref<string | null>(null)

  async function loadPrefs() {
    loading.value = true
    error.value   = null
    const { data, error: err } = await useApiFetch<SyncPref[]>('/sync/prefs')
    loading.value = false
    if (err) { error.value = 'Failed to load sync preferences.'; return }
    const map: Record<string, boolean> = {}
    for (const p of data ?? []) map[p.data_class] = p.enabled
    prefs.value = map
  }

  async function setPref(dataClass: string, enabled: boolean) {
    saving.value  = dataClass
    error.value   = null
    const { error: err } = await useApiFetch('/sync/prefs', {
      method: 'PATCH',
      body: JSON.stringify({ data_class: dataClass, enabled }),
    })
    saving.value = null
    if (err) { error.value = `Failed to update sync preference for ${dataClass}.`; return }
    prefs.value = { ...prefs.value, [dataClass]: enabled }
  }

  async function wipeAll() {
    wiping.value = true
    error.value  = null
    const { error: err } = await useApiFetch('/sync/all', { method: 'DELETE' })
    wiping.value = false
    if (err) { error.value = 'Failed to delete sync data.'; return }
    prefs.value = {}
  }

  return { prefs, loading, saving, wiping, error, loadPrefs, setPref, wipeAll }
})
