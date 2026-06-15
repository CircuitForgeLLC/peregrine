import { defineStore } from 'pinia'
import { ref } from 'vue'
import { useApiFetch } from '../../composables/useApi'

const LS_KEY     = 'peregrine:wizard-draft'
const SKIP_SIGNAL = 'skip'

export interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
}

export const useAiInterviewStore = defineStore('aiInterview', () => {
  const messages    = ref<ChatMessage[]>([])
  const fields      = ref<Record<string, unknown>>({})
  const complete    = ref(false)
  const loading     = ref(false)
  const saving      = ref(false)
  const error       = ref<string | null>(null)

  function _persist() {
    localStorage.setItem(LS_KEY, JSON.stringify({
      messages: messages.value,
      fields: fields.value,
      complete: complete.value,
    }))
  }

  function restore() {
    try {
      const raw = localStorage.getItem(LS_KEY)
      if (!raw) return
      const d = JSON.parse(raw) as { messages?: ChatMessage[]; fields?: Record<string, unknown>; complete?: boolean }
      messages.value = d.messages  ?? []
      fields.value   = d.fields    ?? {}
      complete.value = d.complete  ?? false
    } catch { /* ignore corrupted draft */ }
  }

  async function send(userText: string) {
    if (loading.value) return
    if (userText !== '') {
      messages.value = [...messages.value, { role: 'user', content: userText }]
      _persist()
    }
    loading.value = true
    error.value   = null
    const { data, error: err } = await useApiFetch<{
      reply: string
      extracted_fields: Record<string, unknown>
      complete: boolean
    }>('/api/wizard/ai/interview', {
      method: 'POST',
      body: JSON.stringify({ history: messages.value, profile_so_far: fields.value }),
    })
    loading.value = false
    if (err || !data) {
      if (err?.kind === 'http' && err.status === 402) {
        error.value = 'AI profile assistant requires a Paid plan or a BYOK API key.'
      } else if (err?.kind === 'http' && err.status === 503) {
        try {
          const body = JSON.parse(err.detail) as { detail?: { error?: string } }
          error.value = body.detail?.error === 'llm_error'
            ? 'No LLM backend configured — add an API key in Settings → System first.'
            : 'Could not reach the assistant. Please try again.'
        } catch {
          error.value = 'Could not reach the assistant. Please try again.'
        }
      } else {
        error.value = 'Could not reach the assistant. Please try again.'
      }
      return
    }
    messages.value = [...messages.value, { role: 'assistant', content: data.reply }]
    fields.value   = { ...fields.value, ...data.extracted_fields }
    complete.value = data.complete
    _persist()
  }

  async function finalize(): Promise<boolean> {
    saving.value = true
    error.value  = null
    const { error: err } = await useApiFetch('/api/wizard/ai/finalize', {
      method: 'POST',
      body: JSON.stringify({ profile: fields.value }),
    })
    saving.value = false
    if (err) {
      error.value = 'Failed to save profile. Please try again.'
      return false
    }
    localStorage.removeItem(LS_KEY)
    return true
  }

  function skip() {
    return send(SKIP_SIGNAL)
  }

  function keepChatting() {
    complete.value = false
  }

  function startOver() {
    messages.value = []
    fields.value   = {}
    complete.value = false
    error.value    = null
    localStorage.removeItem(LS_KEY)
  }

  return { messages, fields, complete, loading, saving, error, restore, send, skip, finalize, keepChatting, startOver }
})
