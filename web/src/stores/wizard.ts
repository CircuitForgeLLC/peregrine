import { ref } from 'vue'
import { defineStore } from 'pinia'
import { useApiFetch } from '../composables/useApi'

export const useWizardStore = defineStore('wizard', () => {
  // ── Navigation state ──────────────────────────────────────────────────────
  const saving = ref(false)
  const errors = ref<string[]>([])

  // ── Actions ───────────────────────────────────────────────────────────────

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
    saving,
    errors,
    // actions
    complete,
  }
})
