// web/src/stores/messaging.ts
import { ref } from 'vue'
import { defineStore } from 'pinia'
import { useApiFetch } from '../composables/useApi'

export interface Message {
  id: number
  job_id: number | null
  job_contact_id: number | null
  type: 'call_note' | 'in_person' | 'email' | 'draft'
  direction: 'inbound' | 'outbound' | null
  subject: string | null
  body: string | null
  from_addr: string | null
  to_addr: string | null
  logged_at: string
  approved_at: string | null
  template_id: number | null
  osprey_call_id: string | null
}

export interface MessageTemplate {
  id: number
  key: string | null
  title: string
  category: string
  subject_template: string | null
  body_template: string
  is_builtin: number
  is_community: number
  community_source: string | null
  created_at: string
  updated_at: string
}

export const useMessagingStore = defineStore('messaging', () => {
  const messages     = ref<Message[]>([])
  const templates    = ref<MessageTemplate[]>([])
  const loading      = ref(false)
  const saving       = ref(false)
  const error        = ref<string | null>(null)
  const draftPending = ref<number | null>(null)   // message_id of pending draft

  async function fetchMessages(jobId: number) {
    loading.value = true
    error.value = null
    const { data, error: fetchErr } = await useApiFetch<Message[]>(
      `/api/messages?job_id=${jobId}`
    )
    loading.value = false
    if (fetchErr) { error.value = 'Could not load messages.'; return }
    messages.value = data ?? []
  }

  async function fetchTemplates() {
    const { data, error: fetchErr } = await useApiFetch<MessageTemplate[]>(
      '/api/message-templates'
    )
    if (fetchErr) { error.value = 'Could not load templates.'; return }
    templates.value = data ?? []
  }

  async function createMessage(payload: Omit<Message, 'id' | 'logged_at' | 'approved_at' | 'osprey_call_id'>) {
    saving.value = true
    error.value = null
    const { data, error: fetchErr } = await useApiFetch<Message>(
      '/api/messages',
      { method: 'POST', body: JSON.stringify(payload), headers: { 'Content-Type': 'application/json' } }
    )
    saving.value = false
    if (fetchErr || !data) { error.value = 'Failed to save message.'; return null }
    messages.value = [data, ...messages.value]
    return data
  }

  async function deleteMessage(id: number) {
    const { error: fetchErr } = await useApiFetch(
      `/api/messages/${id}`,
      { method: 'DELETE' }
    )
    if (fetchErr) { error.value = 'Failed to delete message.'; return }
    messages.value = messages.value.filter(m => m.id !== id)
  }

  async function createTemplate(payload: Pick<MessageTemplate, 'title' | 'category' | 'body_template'> & { subject_template?: string }) {
    saving.value = true
    error.value = null
    const { data, error: fetchErr } = await useApiFetch<MessageTemplate>(
      '/api/message-templates',
      { method: 'POST', body: JSON.stringify(payload), headers: { 'Content-Type': 'application/json' } }
    )
    saving.value = false
    if (fetchErr || !data) { error.value = 'Failed to create template.'; return null }
    templates.value = [...templates.value, data]
    return data
  }

  async function updateTemplate(id: number, payload: Partial<Pick<MessageTemplate, 'title' | 'category' | 'subject_template' | 'body_template'>>) {
    saving.value = true
    error.value = null
    const { data, error: fetchErr } = await useApiFetch<MessageTemplate>(
      `/api/message-templates/${id}`,
      { method: 'PUT', body: JSON.stringify(payload), headers: { 'Content-Type': 'application/json' } }
    )
    saving.value = false
    if (fetchErr || !data) { error.value = 'Failed to update template.'; return null }
    templates.value = templates.value.map(t => t.id === id ? data : t)
    return data
  }

  async function deleteTemplate(id: number) {
    const { error: fetchErr } = await useApiFetch(
      `/api/message-templates/${id}`,
      { method: 'DELETE' }
    )
    if (fetchErr) { error.value = 'Failed to delete template.'; return }
    templates.value = templates.value.filter(t => t.id !== id)
  }

  async function requestDraft(contactId: number) {
    loading.value = true
    error.value = null
    const { data, error: fetchErr } = await useApiFetch<{ message_id: number }>(
      `/api/contacts/${contactId}/draft-reply`,
      { method: 'POST', headers: { 'Content-Type': 'application/json' } }
    )
    loading.value = false
    if (fetchErr || !data) {
      error.value = 'Could not generate draft. Check LLM settings.'
      return null
    }
    draftPending.value = data.message_id
    return data.message_id
  }

  async function approveDraft(messageId: number): Promise<string | null> {
    const { data, error: fetchErr } = await useApiFetch<{ body: string; approved_at: string }>(
      `/api/messages/${messageId}/approve`,
      { method: 'POST' }
    )
    if (fetchErr || !data) { error.value = 'Approve failed.'; return null }
    messages.value = messages.value.map(m =>
      m.id === messageId ? { ...m, approved_at: data.approved_at } : m
    )
    draftPending.value = null
    return data.body
  }

  function clear() {
    messages.value  = []
    templates.value = []
    loading.value   = false
    saving.value    = false
    error.value     = null
    draftPending.value = null
  }

  return {
    messages, templates, loading, saving, error, draftPending,
    fetchMessages, fetchTemplates, createMessage, deleteMessage,
    createTemplate, updateTemplate, deleteTemplate,
    requestDraft, approveDraft, clear,
  }
})
