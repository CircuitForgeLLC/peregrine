<template>
  <div class="system-settings">
    <h2>System Settings</h2>
    <p class="tab-note">This tab is only available in self-hosted mode.</p>

    <p v-if="store.loadError" class="error-banner">{{ store.loadError }}</p>

    <!-- LLM Backends -->
    <section class="form-section">
      <h3>LLM Backends</h3>
      <p class="section-note">Drag to reorder. Higher position = higher priority in the fallback chain.</p>

      <div class="backend-list">
        <div
          v-for="(backend, idx) in visibleBackends"
          :key="backend.id"
          class="backend-card"
          draggable="true"
          @dragstart="dragStart(idx)"
          @dragover.prevent="dragOver(idx)"
          @drop="drop"
        >
          <span class="drag-handle" aria-hidden="true">⠿</span>
          <span class="priority-badge">{{ idx + 1 }}</span>
          <span class="backend-id">{{ backend.id }}</span>
          <label class="toggle-label">
            <input
              type="checkbox"
              :checked="backend.enabled"
              @change="store.backends = store.backends.map(b =>
                b.id === backend.id ? { ...b, enabled: !b.enabled } : b
              )"
            />
            <span class="toggle-text">{{ backend.enabled ? 'Enabled' : 'Disabled' }}</span>
          </label>
        </div>
      </div>

      <div class="form-actions">
        <button @click="store.trySave()" :disabled="store.saving" class="btn-primary">
          {{ store.saving ? 'Saving…' : 'Save Backends' }}
        </button>
        <p v-if="store.saveError" class="error">{{ store.saveError }}</p>
      </div>
    </section>

    <!-- Services section -->
    <section class="form-section">
      <h3>Services</h3>
      <p class="section-note">Port-based status. Start/Stop via Docker Compose.</p>
      <div class="service-grid">
        <div v-for="svc in store.services" :key="svc.name" class="service-card">
          <div class="service-header">
            <span class="service-dot" :class="svc.running ? 'dot-running' : 'dot-stopped'"></span>
            <span class="service-name">{{ svc.name }}</span>
            <span class="service-port">:{{ svc.port }}</span>
          </div>
          <p class="service-note">{{ svc.note }}</p>
          <div class="service-actions">
            <button v-if="!svc.running" @click="store.startService(svc.name)" class="btn-start">Start</button>
            <button v-else @click="store.stopService(svc.name)" class="btn-stop">Stop</button>
          </div>
          <p v-if="store.serviceErrors[svc.name]" class="error">{{ store.serviceErrors[svc.name] }}</p>
        </div>
      </div>
    </section>

    <!-- File Paths -->
    <section class="form-section">
      <h3>File Paths</h3>
      <div class="field-row">
        <label>Documents Directory</label>
        <input v-model="(store.filePaths as any).docs_dir" placeholder="/Library/Documents/JobSearch" />
      </div>
      <div class="field-row">
        <label>Data Directory</label>
        <input v-model="(store.filePaths as any).data_dir" placeholder="data/" />
      </div>
      <div class="field-row">
        <label>Model Directory</label>
        <input v-model="(store.filePaths as any).model_dir" placeholder="/Library/Assets/LLM" />
      </div>
      <div class="form-actions">
        <button @click="store.saveFilePaths()" :disabled="store.filePathsSaving" class="btn-primary">
          {{ store.filePathsSaving ? 'Saving…' : 'Save Paths' }}
        </button>
      </div>
      <p v-if="store.filePathsError" class="error-msg">{{ store.filePathsError }}</p>
    </section>

    <!-- Deployment / Server -->
    <section class="form-section">
      <h3>Deployment / Server</h3>
      <p class="section-note">Restart required for changes to take effect.</p>
      <div class="field-row">
        <label>Base URL Path</label>
        <input v-model="(store.deployConfig as any).base_url_path" placeholder="/peregrine" />
      </div>
      <div class="field-row">
        <label>Server Host</label>
        <input v-model="(store.deployConfig as any).server_host" placeholder="0.0.0.0" />
      </div>
      <div class="field-row">
        <label>Server Port</label>
        <input v-model.number="(store.deployConfig as any).server_port" type="number" placeholder="8502" />
      </div>
      <div class="form-actions">
        <button @click="store.saveDeployConfig()" :disabled="store.deploySaving" class="btn-primary">
          {{ store.deploySaving ? 'Saving…' : 'Save (requires restart)' }}
        </button>
      </div>
      <p v-if="store.deployError" class="error-msg">{{ store.deployError }}</p>
    </section>

    <!-- Compute & AI Backend -->
    <section v-if="!config.isCloud" class="form-section">
      <h3>Compute &amp; AI Backend</h3>
      <p class="section-note">
        Which hardware profile Peregrine uses, and the keys/hosts for
        whichever inference backend that profile needs.
      </p>

      <div class="field-row">
        <label>Hardware profile</label>
        <select v-model="hardwareProfile" class="field-select">
          <option v-for="p in hardwareProfiles" :key="p" :value="p">{{ p }}</option>
        </select>
      </div>
      <p v-if="detectedGpus.length" class="section-note">
        Detected: {{ detectedGpus.join(', ') }}
      </p>

      <div class="field-row">
        <label>Anthropic API key</label>
        <input
          v-model="anthropicKey"
          type="password"
          :placeholder="anthropicKeySet ? '••••••••  (set, enter to replace)' : 'sk-ant-…'"
          class="field-input-wide"
          autocomplete="off"
        />
      </div>

      <div class="field-row">
        <label>OpenAI-compatible endpoint</label>
        <input v-model="openaiUrl" type="url" placeholder="https://api.together.xyz/v1" class="field-input-wide" />
      </div>
      <div v-if="openaiUrl" class="field-row">
        <label>Endpoint API key</label>
        <input
          v-model="openaiKey"
          type="password"
          :placeholder="openaiKeySet ? '••••••••  (set, enter to replace)' : 'API key for the endpoint above'"
          class="field-input-wide"
          autocomplete="off"
        />
      </div>

      <div class="field-row">
        <label>Ollama host</label>
        <input v-model="ollamaHost" type="text" placeholder="localhost" class="field-input-wide" />
      </div>
      <div class="field-row">
        <label>Ollama port</label>
        <input v-model.number="ollamaPort" type="number" class="field-input-wide" />
      </div>

      <div class="field-row">
        <label>Ollama model</label>
        <select v-model="ollamaModel" class="field-select">
          <option value="">(none selected)</option>
          <option v-for="m in ollamaModelOptions" :key="m" :value="m">{{ m }}</option>
        </select>
      </div>
      <p v-if="ollamaModel && ollamaModelAvailable" class="model-status model-status--ok">
        ✓ Installed and ready to use.
      </p>
      <p v-else-if="ollamaModel && !ollamaModelAvailable" class="model-status model-status--warn">
        ⚠ Not installed on this Ollama host yet.
        <button
          class="btn-save-inline"
          :disabled="ollamaModelPulling"
          @click="pullOllamaModel"
        >{{ ollamaModelPulling ? 'Downloading…' : 'Download' }}</button>
      </p>

      <div class="form-actions">
        <button @click="saveLlmBackend" :disabled="llmBackendSaving" class="btn-primary">
          {{ llmBackendSaving ? 'Saving…' : 'Save Compute & AI Backend' }}
        </button>
        <p v-if="llmBackendError" class="error">{{ llmBackendError }}</p>
        <p v-if="llmBackendSaved" class="success">Saved.</p>
      </div>
    </section>

    <!-- Model Assignments -->
    <section v-if="!config.isCloud" class="form-section">
      <h3>Model Assignments</h3>
      <p class="section-note">
        Which model handles each kind of task. Research and Chat are checked
        for reliable structured-output before being used without a warning;
        Primary (cover letters) is not, since writing quality can't be
        tested automatically.
      </p>

      <div class="field-row">
        <label>Find Ollama</label>
        <button class="btn-save-inline" :disabled="detecting" @click="runOllamaDetect">
          {{ detecting ? 'Detecting…' : 'Detect' }}
        </button>
      </div>
      <p v-if="detectResult" class="section-note">{{ detectResult }}</p>

      <div v-for="task in (['primary', 'research', 'chat'] as const)" :key="task" class="field-row">
        <label>{{ task === 'primary' ? 'Primary (cover letters)' : task === 'research' ? 'Research (suggestions)' : 'Chat (AI assistant)' }}</label>
        <select :value="taskModels[task]?.model ?? ''" class="field-select" @change="onTaskModelChange(task, ($event.target as HTMLSelectElement).value)">
          <option value="">(none assigned)</option>
          <option v-for="m in taskModelsStore.ollamaModels" :key="m" :value="m">{{ m }}</option>
        </select>
        <span
          v-if="task !== 'primary' && taskModels[task]?.model && probeBadge(task) === 'warn'"
          class="model-status model-status--warn"
        >⚠ May not follow instructions reliably</span>
        <span
          v-if="task !== 'primary' && taskModels[task]?.model && probeBadge(task) === 'ok'"
          class="model-status model-status--ok"
        >✓ Structured output OK</span>
      </div>

      <div class="form-actions">
        <button @click="saveTaskModels" :disabled="taskModelsStore.saving" class="btn-primary">
          {{ taskModelsStore.saving ? 'Saving…' : 'Save Model Assignments' }}
        </button>
        <p v-if="taskModelsStore.saveError" class="error">{{ taskModelsStore.saveError }}</p>
      </div>
    </section>

    <!-- Orchard coordinator -->
    <section class="form-section">
      <h3>Orchard Coordinator</h3>
      <p class="section-note">
        The Orchard is CircuitForge's distributed GPU cluster. Requires a Paid license or higher.
        Leave blank to disable Orchard routing.
      </p>
      <div class="field-row">
        <label>Coordinator URL</label>
        <input
          v-model="orchUrl"
          type="url"
          placeholder="https://orch.circuitforge.tech"
          class="field-input-wide"
        />
        <button @click="saveOrchUrl" :disabled="orchSaving" class="btn-save-inline">
          {{ orchSaving ? 'Saving…' : 'Save' }}
        </button>
      </div>
      <p v-if="orchError" class="error">{{ orchError }}</p>
      <p v-if="orchSaved" class="success">Saved.</p>
    </section>

    <!-- BYOK Modal -->
    <Teleport to="body">
      <div v-if="store.byokPending.length > 0" class="modal-overlay" @click.self="store.cancelByok()">
        <div class="modal-card" role="dialog" aria-modal="true" aria-labelledby="byok-title">
          <h3 id="byok-title">⚠️ Cloud LLM Key Required</h3>
          <p>You are enabling the following cloud backends:</p>
          <ul>
            <li v-for="b in store.byokPending" :key="b">{{ b }}</li>
          </ul>
          <p class="byok-warning">
            These services require your own API key. Your requests and data will be
            sent to these third-party providers. Costs will be charged to your account.
          </p>
          <label class="checkbox-row">
            <input type="checkbox" v-model="byokConfirmed" />
            I understand and have configured my API key in <code>config/llm.yaml</code>
          </label>
          <div class="modal-actions">
            <button @click="store.cancelByok()" class="btn-cancel">Cancel</button>
            <button
              @click="handleConfirmByok"
              :disabled="!byokConfirmed || store.saving"
              class="btn-primary"
            >{{ store.saving ? 'Saving…' : 'Save with Cloud LLM' }}</button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useSystemStore } from '../../stores/settings/system'
import { useAppConfigStore } from '../../stores/appConfig'
import { useApiFetch } from '../../composables/useApi'
import { useTaskModelsStore, type TaskName } from '../../stores/settings/taskModels'

const store = useSystemStore()
const config = useAppConfigStore()

const byokConfirmed = ref(false)
const dragIdx = ref<number | null>(null)

const CONTRACTED_ONLY = ['claude-code', 'copilot']

const visibleBackends = computed(() =>
  store.backends.filter(b =>
    !CONTRACTED_ONLY.includes(b.id) || config.contractedClient
  )
)

function dragStart(idx: number) {
  dragIdx.value = idx
}

function dragOver(toFilteredIdx: number) {
  if (dragIdx.value === null || dragIdx.value === toFilteredIdx) return
  const fromId = visibleBackends.value[dragIdx.value].id
  const toId = visibleBackends.value[toFilteredIdx].id
  const arr = [...store.backends]
  const fromFull = arr.findIndex(b => b.id === fromId)
  const toFull = arr.findIndex(b => b.id === toId)
  if (fromFull === -1 || toFull === -1) return
  const [moved] = arr.splice(fromFull, 1)
  arr.splice(toFull, 0, moved)
  store.backends = arr.map((b, i) => ({ ...b, priority: i + 1 }))
  dragIdx.value = toFilteredIdx
}

function drop() {
  dragIdx.value = null
}

async function handleConfirmByok() {
  await store.confirmByok()
  byokConfirmed.value = false
}

// ── Model Assignments (Primary/Research/Chat) ─────────────────────────────────
// Note: `ollamaModels` below is shared with the "Compute & AI Backend" section
// (ollamaModelOptions/ollamaModelAvailable/pullOllamaModel/loadLlmBackend) --
// it is unrelated to the removed cover-letter picker and is kept here.
const ollamaModels = ref<string[]>([])

const taskModelsStore = useTaskModelsStore()
const taskModels = computed(() => ({
  primary: taskModelsStore.primary, research: taskModelsStore.research, chat: taskModelsStore.chat,
}))
const detecting = ref(false)
const detectResult = ref<string | null>(null)

function onTaskModelChange(task: TaskName, model: string) {
  const assignment = model ? { backend: 'ollama', model } : null
  if (task === 'primary') taskModelsStore.primary = assignment
  else if (task === 'research') taskModelsStore.research = assignment
  else taskModelsStore.chat = assignment
  if (assignment && task !== 'primary') {
    taskModelsStore.probeModel('ollama', model)
  }
}

function probeBadge(task: TaskName): 'ok' | 'warn' | null {
  const assignment = taskModels.value[task]
  if (!assignment) return null
  const result = taskModelsStore.probeResults[`${assignment.backend}:${assignment.model}`]
  if (!result) return null
  return result.passed ? 'ok' : 'warn'
}

async function saveTaskModels() {
  await taskModelsStore.save()
}

async function runOllamaDetect() {
  detecting.value = true
  detectResult.value = null
  const result = await taskModelsStore.detectOllama(11434)
  detecting.value = false
  if (result.found) {
    // Write into the real, persisted Ollama host field (saved by
    // saveLlmBackend) -- not a second, dead copy of it.
    ollamaHost.value = result.host ?? ''
    detectResult.value = `Found Ollama at ${result.host}:${result.port}. Filled into the Ollama host field above — click “Save Compute & AI Backend” to keep it.`
  } else {
    detectResult.value = `Couldn't find Ollama — tried: ${(result.tried ?? []).join(', ')}.`
  }
}

// ── Orchard coordinator URL ───────────────────────────────────────────────────
const orchUrl    = ref('')
const orchSaving = ref(false)
const orchError  = ref<string | null>(null)
const orchSaved  = ref(false)

async function loadOrchUrl() {
  const { data } = await useApiFetch<{ orch_url: string }>('/api/settings/system/orch-url')
  if (data) orchUrl.value = data.orch_url ?? ''
}

async function saveOrchUrl() {
  orchSaving.value = true
  orchError.value  = null
  orchSaved.value  = false
  const { error } = await useApiFetch('/api/settings/system/orch-url', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ orch_url: orchUrl.value }),
  })
  orchSaving.value = false
  if (error) { orchError.value = 'Failed to save.'; return }
  orchSaved.value = true
  setTimeout(() => { orchSaved.value = false }, 3000)
}

// ── Compute & AI Backend ──────────────────────────────────────────────────────
const hardwareProfile   = ref('')
const hardwareProfiles  = ref<string[]>([])
const detectedGpus      = ref<string[]>([])
const anthropicKey      = ref('')
const anthropicKeySet   = ref(false)
const openaiUrl         = ref('')
const openaiKey         = ref('')
const openaiKeySet      = ref(false)
const ollamaHost        = ref('')
const ollamaPort        = ref(11434)
const ollamaModel       = ref('')
const ollamaModelPulling = ref(false)
const llmBackendSaving  = ref(false)
const llmBackendError   = ref<string | null>(null)
const llmBackendSaved   = ref(false)

// The dropdown must always include the currently configured model, even if
// it isn't installed yet -- otherwise picking a model that needs a download
// would silently disappear from its own picker.
const ollamaModelOptions = computed(() => {
  if (ollamaModel.value && !ollamaModels.value.includes(ollamaModel.value)) {
    return [ollamaModel.value, ...ollamaModels.value]
  }
  return ollamaModels.value
})
const ollamaModelAvailable = computed(() => ollamaModels.value.includes(ollamaModel.value))

async function loadLlmBackend() {
  const { data } = await useApiFetch<{
    anthropic_key_set: boolean; openai_url: string; openai_key_set: boolean
    ollama_host: string; ollama_port: number; inference_profile: string; ollama_model: string
  }>('/api/settings/system/llm-backend')
  if (data) {
    anthropicKeySet.value = data.anthropic_key_set
    openaiUrl.value       = data.openai_url
    openaiKeySet.value    = data.openai_key_set
    ollamaHost.value      = data.ollama_host
    ollamaPort.value      = data.ollama_port
    ollamaModel.value     = data.ollama_model
    if (data.inference_profile) hardwareProfile.value = data.inference_profile
  }

  const { data: hwData } = await useApiFetch<{ profiles: string[]; suggested_profile: string; gpus: string[] }>(
    '/api/wizard/hardware',
  )
  if (hwData) {
    hardwareProfiles.value = hwData.profiles ?? []
    detectedGpus.value     = hwData.gpus ?? []
    if (!hardwareProfile.value) hardwareProfile.value = hwData.suggested_profile ?? ''
  }

  const { data: mData } = await useApiFetch<{ models: string[] }>('/api/settings/llm/ollama-models')
  if (mData) ollamaModels.value = mData.models ?? []
}

async function saveLlmBackend() {
  llmBackendSaving.value = true
  llmBackendError.value  = null
  llmBackendSaved.value  = false
  const { error } = await useApiFetch('/api/settings/system/llm-backend', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      anthropic_key: anthropicKey.value,
      openai_url: openaiUrl.value,
      openai_key: openaiKey.value,
      ollama_host: ollamaHost.value,
      ollama_port: ollamaPort.value,
      inference_profile: hardwareProfile.value,
      ollama_model: ollamaModel.value,
    }),
  })
  llmBackendSaving.value = false
  if (error) { llmBackendError.value = 'Failed to save.'; return }
  anthropicKey.value = ''
  openaiKey.value = ''
  llmBackendSaved.value = true
  setTimeout(() => { llmBackendSaved.value = false }, 3000)
}

async function pullOllamaModel() {
  if (!ollamaModel.value || ollamaModelPulling.value) return
  ollamaModelPulling.value = true
  await useApiFetch('/api/settings/system/ollama-pull', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ model: ollamaModel.value }),
  })
  await pollForOllamaModel(ollamaModel.value)
  ollamaModelPulling.value = false
}

async function pollForOllamaModel(model: string, attempt = 0) {
  const MAX_ATTEMPTS = 120  // 120 x 5s = 10 minutes
  if (attempt >= MAX_ATTEMPTS) return
  const { data } = await useApiFetch<{ models: string[] }>('/api/settings/llm/ollama-models')
  if (data) ollamaModels.value = data.models ?? []
  if (ollamaModels.value.includes(model)) return
  await new Promise(resolve => setTimeout(resolve, 5000))
  await pollForOllamaModel(model, attempt + 1)
}

onMounted(async () => {
  await store.loadLlm()
  const tasks = [
    store.loadServices(),
    store.loadFilePaths(),
    store.loadDeployConfig(),
    loadOrchUrl(),
  ]
  if (!config.isCloud) {
    tasks.push(loadLlmBackend())
    tasks.push(taskModelsStore.load())
    tasks.push(taskModelsStore.loadOllamaModels())
  }
  await Promise.all(tasks)
})
</script>

<style scoped>
.system-settings { max-width: 720px; margin: 0 auto; padding: var(--space-4); }
h2 { font-size: 1.4rem; font-weight: 600; margin-bottom: 6px; }
h3 { font-size: 1rem; font-weight: 600; margin-bottom: var(--space-3); }
.tab-note { font-size: 0.82rem; color: var(--color-text-muted); margin-bottom: var(--space-6); }
.form-section { margin-bottom: var(--space-8); padding-bottom: var(--space-6); border-bottom: 1px solid var(--color-border); }
.section-note { font-size: 0.78rem; color: var(--color-text-muted); margin-bottom: 14px; }
.model-status { font-size: 0.82rem; margin-bottom: 14px; display: flex; align-items: center; gap: var(--space-2); }
.model-status--ok { color: var(--color-success); }
.model-status--warn { color: var(--color-warning); }
.backend-list { display: flex; flex-direction: column; gap: 8px; margin-bottom: 20px; }
.backend-card { display: flex; align-items: center; gap: 12px; padding: 10px 14px; background: var(--color-surface-alt); border: 1px solid var(--color-border); border-radius: 8px; cursor: grab; user-select: none; }
.backend-card:active { cursor: grabbing; }
.drag-handle { font-size: 1.1rem; color: var(--color-text-muted); }
.priority-badge { width: 22px; height: 22px; border-radius: 50%; background: color-mix(in srgb, var(--color-accent) 20%, transparent); color: var(--color-accent); font-size: 0.72rem; font-weight: 700; display: flex; align-items: center; justify-content: center; flex-shrink: 0; }
.backend-id { flex: 1; font-size: 0.9rem; font-family: monospace; color: var(--color-text); }
.toggle-label { display: flex; align-items: center; gap: 6px; cursor: pointer; font-size: 0.82rem; color: var(--color-text-muted); }
.form-actions { display: flex; align-items: center; gap: var(--space-4); flex-wrap: wrap; }
.btn-primary { padding: 9px 24px; background: var(--color-accent); color: var(--color-text-inverse); border: none; border-radius: 7px; font-size: 0.9rem; cursor: pointer; font-weight: 600; }
.btn-primary:disabled { opacity: 0.5; cursor: not-allowed; }
.btn-cancel { padding: 9px 18px; background: transparent; border: 1px solid var(--color-border); border-radius: 7px; color: var(--color-text-muted); cursor: pointer; font-size: 0.9rem; }
.error-banner {
  background: color-mix(in srgb, var(--color-error) 10%, transparent);
  border: 1px solid color-mix(in srgb, var(--color-error) 30%, transparent);
  border-radius: 6px; color: var(--color-error); padding: 10px 14px; margin-bottom: 20px; font-size: 0.85rem;
}
.error { color: var(--color-error); font-size: 0.82rem; }
/* BYOK Modal */
.modal-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.6); display: flex; align-items: center; justify-content: center; z-index: 9999; }
.modal-card { background: var(--color-surface-raised); border: 1px solid var(--color-border); border-radius: 12px; padding: 28px; max-width: 480px; width: 90%; }
.modal-card h3 { font-size: 1.1rem; margin-bottom: 12px; }
.modal-card p { font-size: 0.88rem; color: var(--color-text-muted); margin-bottom: 12px; }
.modal-card ul { margin: 8px 0 16px 20px; font-size: 0.88rem; color: var(--color-text); }
.byok-warning {
  background: color-mix(in srgb, var(--color-warning) 10%, transparent);
  border: 1px solid color-mix(in srgb, var(--color-warning) 30%, transparent);
  border-radius: 6px; padding: 10px 12px; color: var(--color-warning) !important;
}
.checkbox-row { display: flex; align-items: flex-start; gap: 8px; font-size: 0.85rem; color: var(--color-text); cursor: pointer; margin: 16px 0; }
.modal-actions { display: flex; gap: 10px; justify-content: flex-end; margin-top: 20px; }
.service-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 12px; margin-bottom: 16px; }
.service-card { background: var(--color-surface-alt); border: 1px solid var(--color-border); border-radius: 8px; padding: 14px; }
.service-header { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; }
.service-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.dot-running { background: var(--color-success); box-shadow: 0 0 6px color-mix(in srgb, var(--color-success) 50%, transparent); }
.dot-stopped { background: var(--color-text-muted); }
.service-name { font-weight: 600; font-size: 0.88rem; color: var(--color-text); }
.service-port { font-size: 0.75rem; color: var(--color-text-muted); font-family: monospace; }
.service-note { font-size: 0.75rem; color: var(--color-text-muted); margin-bottom: 10px; }
.service-actions { display: flex; gap: 6px; }
.btn-start {
  padding: 4px 12px; border-radius: 4px;
  background: color-mix(in srgb, var(--color-success) 15%, transparent);
  color: var(--color-success);
  border: 1px solid color-mix(in srgb, var(--color-success) 30%, transparent);
  cursor: pointer; font-size: 0.78rem;
}
.btn-stop {
  padding: 4px 12px; border-radius: 4px;
  background: color-mix(in srgb, var(--color-error) 10%, transparent);
  color: var(--color-error);
  border: 1px solid color-mix(in srgb, var(--color-error) 20%, transparent);
  cursor: pointer; font-size: 0.78rem;
}
.field-row { display: flex; flex-direction: column; gap: 4px; margin-bottom: 14px; }
.field-row label { font-size: 0.82rem; color: var(--color-text-muted); }
.field-row input { background: var(--color-surface-alt); border: 1px solid var(--color-border); border-radius: 6px; color: var(--color-text); padding: 7px 10px; font-size: 0.88rem; }
.field-input-wide { width: 100%; max-width: 400px; }
.field-hint { font-size: 0.72rem; color: var(--color-text-muted); margin-top: 3px; }
.btn-secondary { padding: 9px 18px; background: transparent; border: 1px solid var(--color-border); border-radius: 7px; color: var(--color-text-muted); cursor: pointer; font-size: 0.88rem; }
.btn-danger {
  padding: 6px 14px; border-radius: 6px;
  background: color-mix(in srgb, var(--color-error) 10%, transparent);
  color: var(--color-error);
  border: 1px solid color-mix(in srgb, var(--color-error) 25%, transparent);
  cursor: pointer; font-size: 0.82rem;
}
.test-ok { color: var(--color-success); font-size: 0.85rem; }
.test-fail { color: var(--color-error); font-size: 0.85rem; }

.field-select {
  flex: 1;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  padding: var(--space-1) var(--space-2);
  font-size: var(--text-sm);
  color: var(--color-text);
  min-width: 0;
}
.field-select:focus-visible {
  outline: 2px solid var(--app-primary);
  border-color: var(--app-primary);
}

.btn-save-inline {
  background: var(--app-primary);
  color: var(--color-text-inverse);
  border: none;
  border-radius: var(--radius-md);
  padding: var(--space-1) var(--space-3);
  font-size: var(--text-sm);
  font-weight: 600;
  cursor: pointer;
  white-space: nowrap;
  flex-shrink: 0;
}
.btn-save-inline:disabled { opacity: 0.6; cursor: default; }
.btn-save-inline:hover:not(:disabled) { background: var(--app-primary-hover); }

.success {
  color: var(--color-success);
  font-size: var(--text-sm);
  margin: var(--space-1) 0 0;
}
</style>
