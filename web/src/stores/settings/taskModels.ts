import { ref } from 'vue'
import { defineStore } from 'pinia'
import { useApiFetch } from '../../composables/useApi'

export interface TaskAssignment { backend: string; model: string }
export type TaskName = 'primary' | 'research' | 'chat'

export const useTaskModelsStore = defineStore('settings/taskModels', () => {
  const primary = ref<TaskAssignment | null>(null)
  const research = ref<TaskAssignment | null>(null)
  const chat = ref<TaskAssignment | null>(null)
  const ollamaModels = ref<string[]>([])
  const probeResults = ref<Record<string, { passed: boolean }>>({})

  const loading = ref(false)
  const saving = ref(false)
  const saveError = ref<string | null>(null)

  async function load() {
    loading.value = true
    const { data } = await useApiFetch<{
      primary: TaskAssignment | null; research: TaskAssignment | null; chat: TaskAssignment | null
    }>('/api/settings/system/task-models')
    loading.value = false
    if (!data) return
    primary.value = data.primary
    research.value = data.research
    chat.value = data.chat
  }

  async function loadOllamaModels() {
    const { data } = await useApiFetch<{ models: string[] }>('/api/settings/llm/ollama-models')
    ollamaModels.value = data?.models ?? []
  }

  async function save() {
    saving.value = true
    saveError.value = null
    const { error } = await useApiFetch('/api/settings/system/task-models', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ primary: primary.value, research: research.value, chat: chat.value }),
    })
    saving.value = false
    if (error) saveError.value = 'Save failed — please try again.'
  }

  async function probeModel(backend: string, model: string) {
    const { data } = await useApiFetch<{ passed?: boolean; error?: string }>(
      '/api/settings/system/probe-model',
      { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ backend, model }) },
    )
    if (data && data.passed !== undefined) {
      probeResults.value = { ...probeResults.value, [`${backend}:${model}`]: { passed: data.passed } }
    }
    // an "unreachable" result leaves probeResults untouched -- untested,
    // not failed; the UI must not show a warning badge for this case.
  }

  async function detectOllama(port: number) {
    const { data } = await useApiFetch<{ found: boolean; host?: string; port?: number; tried?: string[] }>(
      '/api/settings/system/ollama-detect',
      { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ port }) },
    )
    return data ?? { found: false, tried: [] }
  }

  return {
    primary, research, chat, ollamaModels, probeResults, loading, saving, saveError,
    load, loadOllamaModels, save, probeModel, detectOllama,
  }
})
