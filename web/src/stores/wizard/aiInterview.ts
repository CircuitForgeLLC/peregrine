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
  // The field name the assistant's last reply is asking about, reported
  // explicitly by the LLM (see dev-api.py's asking_about) — not guessed by
  // keyword-matching the reply text, which produced false positives (e.g. a
  // career_summary question that happened to contain the word "writing"
  // wrongly triggered the candidate_voice tone-chip suggestions).
  const askingAbout = ref<string | null>(null)

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

  /**
   * Fill in fields already known from elsewhere in the wizard (resume parse,
   * identity step) without overwriting anything the chat itself has already
   * gathered or the user already edited — deterministic data should never
   * make the LLM re-ask for it.
   */
  function seedFields(known: Record<string, unknown>) {
    const additions: Record<string, unknown> = {}
    for (const [key, value] of Object.entries(known)) {
      if (value !== undefined && value !== null && value !== '' && !(key in fields.value)) {
        additions[key] = value
      }
    }
    if (Object.keys(additions).length > 0) {
      fields.value = { ...fields.value, ...additions }
      _persist()
    }
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
      asking_about: string | null
    }>('/api/wizard/ai/interview', {
      method: 'POST',
      body: JSON.stringify({ history: messages.value, profile_so_far: fields.value }),
      headers: { 'Content-Type': 'application/json' },
    })
    loading.value = false
    if (err || !data) {
      if (err?.kind === 'http' && err.status === 402) {
        error.value = 'AI profile assistant requires a Paid plan or a BYOK API key.'
      } else if (err?.kind === 'http' && (err.status === 400 || err.status === 502)) {
        try {
          const body = JSON.parse(err.detail) as { detail?: string }
          error.value = body.detail ?? 'Could not reach the assistant. Please try again.'
        } catch {
          error.value = 'Could not reach the assistant. Please try again.'
        }
      } else if (err?.kind === 'http' && err.status === 422) {
        // The server rejected the conversation history itself — usually a
        // malformed prior turn (e.g. a null reply that slipped through).
        // Retrying with the same history will 422 again, so tell the user
        // to start over rather than implying a transient connectivity issue.
        error.value = 'This conversation hit an unexpected error and can\'t continue. Please start over.'
      } else {
        error.value = 'Could not reach the assistant. Please try again.'
      }
      return
    }
    // Defensive: never let a non-string reply (e.g. a model emitting
    // `"reply": null`) into message history — it would fail server-side
    // validation on the very next turn and get every message after it stuck.
    messages.value = [...messages.value, { role: 'assistant', content: data.reply ?? '' }]
    fields.value   = { ...fields.value, ...(data.extracted_fields ?? {}) }
    complete.value = data.complete
    askingAbout.value = data.asking_about ?? null
    _persist()
  }

  async function finalize(): Promise<boolean> {
    saving.value = true
    error.value  = null
    const { error: err } = await useApiFetch('/api/wizard/ai/finalize', {
      method: 'POST',
      body: JSON.stringify({ profile: fields.value }),
      headers: { 'Content-Type': 'application/json' },
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
    askingAbout.value = null
    localStorage.removeItem(LS_KEY)
  }

  return { messages, fields, complete, loading, saving, error, askingAbout, restore, seedFields, send, skip, finalize, keepChatting, startOver }
})
