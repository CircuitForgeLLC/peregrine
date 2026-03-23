import { defineStore } from 'pinia'
import { ref } from 'vue'
import { useApiFetch } from '../composables/useApi'

export interface DigestEntry {
  id: number
  job_contact_id: number
  created_at: string
  subject: string
  from_addr: string | null
  received_at: string
  body: string | null
}

/** Extracted link from a digest email body. Used by DigestView.vue. */
export interface DigestLink {
  url: string
  score: number   // 2 = job-likely, 1 = other
  hint: string
}

export const useDigestStore = defineStore('digest', () => {
  const entries = ref<DigestEntry[]>([])
  const loading = ref(false)
  const error   = ref<string | null>(null)

  async function fetchAll() {
    error.value = null
    loading.value = true
    const { data, error: err } = await useApiFetch<DigestEntry[]>('/api/digest-queue')
    loading.value = false
    if (err) {
      error.value = err.kind === 'network' ? 'Network error' : `Error ${err.status}`
      return
    }
    entries.value = data ?? []
  }

  async function remove(id: number) {
    const snapshot = entries.value.find(e => e.id === id)
    entries.value = entries.value.filter(e => e.id !== id)
    const { error: err } = await useApiFetch(`/api/digest-queue/${id}`, { method: 'DELETE' })
    if (err) {
      if (snapshot) entries.value = [...entries.value, snapshot]
      error.value = err.kind === 'network' ? 'Network error' : `Error ${err.status}`
    }
  }

  return { entries, loading, error, fetchAll, remove }
})
