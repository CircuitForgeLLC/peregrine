import { ref } from 'vue'
import { defineStore } from 'pinia'
import { useApiFetch } from '../../composables/useApi'

const CLOUD_BACKEND_IDS = ['anthropic', 'openai']

export interface Backend { id: string; enabled: boolean; priority: number }
export interface Service { name: string; port: number; running: boolean; note: string }
export interface IntegrationField { key: string; label: string; type: string }
export interface Integration { id: string; name: string; connected: boolean; tier_required: string; fields: IntegrationField[] }

export const useSystemStore = defineStore('settings/system', () => {
  const backends = ref<Backend[]>([])
  const byokAcknowledged = ref<string[]>([])
  const byokPending = ref<string[]>([])
  // Private snapshot — NOT in return(). Closure-level only.
  let _preSaveSnapshot: Backend[] = []
  const saving = ref(false)
  const saveError = ref<string | null>(null)
  const loadError = ref<string | null>(null)

  const services = ref<Service[]>([])
  const emailConfig = ref<Record<string, unknown>>({})
  const integrations = ref<Integration[]>([])
  const serviceErrors = ref<Record<string, string>>({})
  const emailSaving = ref(false)
  const emailError = ref<string | null>(null)
  // File paths + deployment
  const filePaths = ref<Record<string, string>>({})
  const deployConfig = ref<Record<string, unknown>>({})
  const filePathsSaving = ref(false)
  const deploySaving = ref(false)
  const filePathsError = ref<string | null>(null)
  const deployError = ref<string | null>(null)
  // Integration test/connect results — keyed by integration id
  const integrationResults = ref<Record<string, {ok: boolean; error?: string}>>({})

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
    saveError.value = null
    const { error } = await useApiFetch('/api/settings/system/llm/byok-ack', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ backends: byokPending.value }),
    })
    if (error) {
      saving.value = false
      saveError.value = 'Failed to save acknowledgment — please try again.'
      return  // leave modal open, byokPending intact
    }
    byokAcknowledged.value = [...byokAcknowledged.value, ...byokPending.value]
    byokPending.value = []
    await _commitSave()
  }

  function cancelByok() {
    if (_preSaveSnapshot.length > 0) {
      backends.value = JSON.parse(JSON.stringify(_preSaveSnapshot))
    }
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

  async function loadServices() {
    const { data } = await useApiFetch<Service[]>('/api/settings/system/services')
    if (data) services.value = data
  }

  async function startService(name: string) {
    const { data, error } = await useApiFetch<{ok: boolean; output: string}>(
      `/api/settings/system/services/${name}/start`, { method: 'POST' }
    )
    if (error || !data?.ok) {
      serviceErrors.value = { ...serviceErrors.value, [name]: data?.output ?? 'Start failed' }
    } else {
      serviceErrors.value = { ...serviceErrors.value, [name]: '' }
      await loadServices()
    }
  }

  async function stopService(name: string) {
    const { data, error } = await useApiFetch<{ok: boolean; output: string}>(
      `/api/settings/system/services/${name}/stop`, { method: 'POST' }
    )
    if (error || !data?.ok) {
      serviceErrors.value = { ...serviceErrors.value, [name]: data?.output ?? 'Stop failed' }
    } else {
      serviceErrors.value = { ...serviceErrors.value, [name]: '' }
      await loadServices()
    }
  }

  async function loadEmail() {
    const { data } = await useApiFetch<Record<string, unknown>>('/api/settings/system/email')
    if (data) emailConfig.value = data
  }

  async function saveEmail() {
    emailSaving.value = true
    emailError.value = null
    const { error } = await useApiFetch('/api/settings/system/email', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(emailConfig.value),
    })
    emailSaving.value = false
    if (error) emailError.value = 'Save failed — please try again.'
  }

  async function testEmail() {
    const { data } = await useApiFetch<{ok: boolean; error?: string}>(
      '/api/settings/system/email/test', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(emailConfig.value),
      }
    )
    return data
  }

  async function loadIntegrations() {
    const { data } = await useApiFetch<Integration[]>('/api/settings/system/integrations')
    if (data) integrations.value = data
  }

  async function connectIntegration(id: string, credentials: Record<string, string>) {
    const { data, error } = await useApiFetch<{ok: boolean; error?: string}>(
      `/api/settings/system/integrations/${id}/connect`,
      { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(credentials) }
    )
    const result = error || !data?.ok
      ? { ok: false, error: data?.error ?? 'Connection failed' }
      : { ok: true }
    integrationResults.value = { ...integrationResults.value, [id]: result }
    if (result.ok) await loadIntegrations()
    return result
  }

  async function testIntegration(id: string, credentials: Record<string, string>) {
    const { data, error } = await useApiFetch<{ok: boolean; error?: string}>(
      `/api/settings/system/integrations/${id}/test`,
      { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(credentials) }
    )
    const result = { ok: data?.ok ?? false, error: data?.error ?? (error ? 'Test failed' : undefined) }
    integrationResults.value = { ...integrationResults.value, [id]: result }
    return result
  }

  async function disconnectIntegration(id: string) {
    const { error } = await useApiFetch(
      `/api/settings/system/integrations/${id}/disconnect`, { method: 'POST' }
    )
    if (!error) await loadIntegrations()
  }

  async function saveEmailWithPassword(payload: Record<string, unknown>) {
    emailSaving.value = true
    emailError.value = null
    const { error } = await useApiFetch('/api/settings/system/email', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
    emailSaving.value = false
    if (error) emailError.value = 'Save failed — please try again.'
    else await loadEmail()  // reload to get fresh password_set status
  }

  async function loadFilePaths() {
    const { data } = await useApiFetch<Record<string, string>>('/api/settings/system/paths')
    if (data) filePaths.value = data
  }

  async function saveFilePaths() {
    filePathsSaving.value = true
    const { error } = await useApiFetch('/api/settings/system/paths', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(filePaths.value),
    })
    filePathsSaving.value = false
    filePathsError.value = error ? 'Failed to save file paths.' : null
  }

  async function loadDeployConfig() {
    const { data } = await useApiFetch<Record<string, unknown>>('/api/settings/system/deploy')
    if (data) deployConfig.value = data
  }

  async function saveDeployConfig() {
    deploySaving.value = true
    const { error } = await useApiFetch('/api/settings/system/deploy', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(deployConfig.value),
    })
    deploySaving.value = false
    deployError.value = error ? 'Failed to save deployment config.' : null
  }

  return {
    backends, byokAcknowledged, byokPending, saving, saveError, loadError,
    loadLlm, trySave, confirmByok, cancelByok,
    services, emailConfig, integrations, integrationResults, serviceErrors, emailSaving, emailError,
    filePaths, deployConfig, filePathsSaving, deploySaving, filePathsError, deployError,
    loadServices, startService, stopService,
    loadEmail, saveEmail, testEmail, saveEmailWithPassword,
    loadIntegrations, connectIntegration, testIntegration, disconnectIntegration,
    loadFilePaths, saveFilePaths,
    loadDeployConfig, saveDeployConfig,
  }
})
