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

    <!-- Email section -->
    <section class="form-section">
      <h3>Email (IMAP)</h3>
      <p class="section-note">Used for email sync in the Interviews pipeline.</p>
      <div class="field-row">
        <label>IMAP Host</label>
        <input v-model="(store.emailConfig as any).host" placeholder="imap.gmail.com" />
      </div>
      <div class="field-row">
        <label>Port</label>
        <input v-model.number="(store.emailConfig as any).port" type="number" placeholder="993" />
      </div>
      <label class="checkbox-row">
        <input type="checkbox" v-model="(store.emailConfig as any).ssl" /> Use SSL
      </label>
      <div class="field-row">
        <label>Username</label>
        <input v-model="(store.emailConfig as any).username" type="email" />
      </div>
      <div class="field-row">
        <label>Password / App Password</label>
        <input
          v-model="emailPasswordInput"
          type="password"
          :placeholder="(store.emailConfig as any).password_set ? '••••••• (saved — enter new to change)' : 'Password'"
        />
        <span class="field-hint">Gmail: use an App Password. Tip: type ${ENV_VAR_NAME} to use an environment variable.</span>
      </div>
      <div class="field-row">
        <label>Sent Folder</label>
        <input v-model="(store.emailConfig as any).sent_folder" placeholder="[Gmail]/Sent Mail" />
      </div>
      <div class="field-row">
        <label>Lookback Days</label>
        <input v-model.number="(store.emailConfig as any).lookback_days" type="number" placeholder="30" />
      </div>
      <div class="form-actions">
        <button @click="handleSaveEmail()" :disabled="store.emailSaving" class="btn-primary">
          {{ store.emailSaving ? 'Saving…' : 'Save Email Config' }}
        </button>
        <button @click="handleTestEmail" class="btn-secondary">Test Connection</button>
        <span v-if="emailTestResult !== null" :class="emailTestResult ? 'test-ok' : 'test-fail'">
          {{ emailTestResult ? '✓ Connected' : '✗ Failed' }}
        </span>
        <p v-if="store.emailError" class="error">{{ store.emailError }}</p>
      </div>
    </section>

    <!-- Integrations -->
    <section class="form-section">
      <h3>Integrations</h3>
      <div v-if="store.integrations.length === 0" class="empty-note">No integrations registered.</div>
      <div v-for="integration in store.integrations" :key="integration.id" class="integration-card">
        <div class="integration-header">
          <span class="integration-name">{{ integration.name }}</span>
          <div class="integration-badges">
            <span v-if="!meetsRequiredTier(integration.tier_required)" class="tier-badge">
              Requires {{ integration.tier_required }}
            </span>
            <span :class="['status-badge', integration.connected ? 'badge-connected' : 'badge-disconnected']">
              {{ integration.connected ? 'Connected' : 'Disconnected' }}
            </span>
          </div>
        </div>
        <!-- Locked state for insufficient tier -->
        <div v-if="!meetsRequiredTier(integration.tier_required)" class="tier-locked">
          <p>Upgrade to {{ integration.tier_required }} to use this integration.</p>
        </div>
        <!-- Normal state for sufficient tier -->
        <template v-else>
          <div v-if="!integration.connected" class="integration-form">
            <div v-for="field in integration.fields" :key="field.key" class="field-row">
              <label>{{ field.label }}</label>
              <input v-model="integrationInputs[integration.id + ':' + field.key]"
                     :type="field.type === 'password' ? 'password' : 'text'" />
            </div>
            <div class="form-actions">
              <button @click="handleConnect(integration.id)" class="btn-primary">Connect</button>
              <button @click="handleTest(integration.id)" class="btn-secondary">Test</button>
              <span v-if="integrationResults[integration.id]" :class="integrationResults[integration.id].ok ? 'test-ok' : 'test-fail'">
                {{ integrationResults[integration.id].ok ? '✓ OK' : '✗ ' + integrationResults[integration.id].error }}
              </span>
            </div>
          </div>
          <div v-else>
            <button @click="store.disconnectIntegration(integration.id)" class="btn-danger">Disconnect</button>
          </div>
        </template>
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
import { storeToRefs } from 'pinia'
import { useSystemStore } from '../../stores/settings/system'
import { useAppConfigStore } from '../../stores/appConfig'

const store = useSystemStore()
const config = useAppConfigStore()
const { tier } = storeToRefs(config)

const byokConfirmed = ref(false)
const dragIdx = ref<number | null>(null)

const CONTRACTED_ONLY = ['claude-code', 'copilot']

const visibleBackends = computed(() =>
  store.backends.filter(b =>
    !CONTRACTED_ONLY.includes(b.id) || config.contractedClient
  )
)

const tierOrder = ['free', 'paid', 'premium', 'ultra']
function meetsRequiredTier(required: string): boolean {
  return tierOrder.indexOf(tier.value) >= tierOrder.indexOf(required || 'free')
}

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

const emailTestResult = ref<boolean | null>(null)
const emailPasswordInput = ref('')
const integrationInputs = ref<Record<string, string>>({})
const integrationResults = ref<Record<string, {ok: boolean; error?: string}>>({})

async function handleTestEmail() {
  const result = await store.testEmail()
  emailTestResult.value = result?.ok ?? false
}

async function handleSaveEmail() {
  const payload = { ...store.emailConfig, password: emailPasswordInput.value || undefined }
  await store.saveEmailWithPassword(payload)
}

async function handleConnect(id: string) {
  const integration = store.integrations.find(i => i.id === id)
  if (!integration) return
  const credentials: Record<string, string> = {}
  for (const field of integration.fields) {
    credentials[field.key] = integrationInputs.value[`${id}:${field.key}`] ?? ''
  }
  const result = await store.connectIntegration(id, credentials)
  integrationResults.value = { ...integrationResults.value, [id]: result }
}

async function handleTest(id: string) {
  const integration = store.integrations.find(i => i.id === id)
  if (!integration) return
  const credentials: Record<string, string> = {}
  for (const field of integration.fields) {
    credentials[field.key] = integrationInputs.value[`${id}:${field.key}`] ?? ''
  }
  const result = await store.testIntegration(id, credentials)
  integrationResults.value = { ...integrationResults.value, [id]: result }
}

onMounted(async () => {
  await store.loadLlm()
  await Promise.all([
    store.loadServices(),
    store.loadEmail(),
    store.loadIntegrations(),
    store.loadFilePaths(),
    store.loadDeployConfig(),
  ])
})
</script>

<style scoped>
.system-settings { max-width: 720px; margin: 0 auto; padding: var(--space-4, 24px); }
h2 { font-size: 1.4rem; font-weight: 600; margin-bottom: 6px; color: var(--color-text-primary, #e2e8f0); }
h3 { font-size: 1rem; font-weight: 600; margin-bottom: var(--space-3, 16px); color: var(--color-text-primary, #e2e8f0); }
.tab-note { font-size: 0.82rem; color: var(--color-text-secondary, #94a3b8); margin-bottom: var(--space-6, 32px); }
.form-section { margin-bottom: var(--space-8, 48px); padding-bottom: var(--space-6, 32px); border-bottom: 1px solid var(--color-border, rgba(255,255,255,0.08)); }
.section-note { font-size: 0.78rem; color: var(--color-text-secondary, #94a3b8); margin-bottom: 14px; }
.backend-list { display: flex; flex-direction: column; gap: 8px; margin-bottom: 20px; }
.backend-card { display: flex; align-items: center; gap: 12px; padding: 10px 14px; background: var(--color-surface-2, rgba(255,255,255,0.04)); border: 1px solid var(--color-border, rgba(255,255,255,0.08)); border-radius: 8px; cursor: grab; user-select: none; }
.backend-card:active { cursor: grabbing; }
.drag-handle { font-size: 1.1rem; color: var(--color-text-secondary, #64748b); }
.priority-badge { width: 22px; height: 22px; border-radius: 50%; background: rgba(124,58,237,0.2); color: var(--color-accent, #a78bfa); font-size: 0.72rem; font-weight: 700; display: flex; align-items: center; justify-content: center; flex-shrink: 0; }
.backend-id { flex: 1; font-size: 0.9rem; font-family: monospace; color: var(--color-text-primary, #e2e8f0); }
.toggle-label { display: flex; align-items: center; gap: 6px; cursor: pointer; font-size: 0.82rem; color: var(--color-text-secondary, #94a3b8); }
.form-actions { display: flex; align-items: center; gap: var(--space-4, 24px); }
.btn-primary { padding: 9px 24px; background: var(--color-accent, #7c3aed); color: #fff; border: none; border-radius: 7px; font-size: 0.9rem; cursor: pointer; font-weight: 600; }
.btn-primary:disabled { opacity: 0.5; cursor: not-allowed; }
.btn-cancel { padding: 9px 18px; background: transparent; border: 1px solid var(--color-border, rgba(255,255,255,0.2)); border-radius: 7px; color: var(--color-text-secondary, #94a3b8); cursor: pointer; font-size: 0.9rem; }
.error-banner { background: rgba(239,68,68,0.1); border: 1px solid rgba(239,68,68,0.3); border-radius: 6px; color: #ef4444; padding: 10px 14px; margin-bottom: 20px; font-size: 0.85rem; }
.error { color: #ef4444; font-size: 0.82rem; }
/* BYOK Modal */
.modal-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.6); display: flex; align-items: center; justify-content: center; z-index: 9999; }
.modal-card { background: var(--color-surface-1, #1e293b); border: 1px solid var(--color-border, rgba(255,255,255,0.12)); border-radius: 12px; padding: 28px; max-width: 480px; width: 90%; }
.modal-card h3 { font-size: 1.1rem; margin-bottom: 12px; color: var(--color-text-primary, #e2e8f0); }
.modal-card p { font-size: 0.88rem; color: var(--color-text-secondary, #94a3b8); margin-bottom: 12px; }
.modal-card ul { margin: 8px 0 16px 20px; font-size: 0.88rem; color: var(--color-text-primary, #e2e8f0); }
.byok-warning { background: rgba(245,158,11,0.1); border: 1px solid rgba(245,158,11,0.3); border-radius: 6px; padding: 10px 12px; color: #fbbf24 !important; }
.checkbox-row { display: flex; align-items: flex-start; gap: 8px; font-size: 0.85rem; color: var(--color-text-primary, #e2e8f0); cursor: pointer; margin: 16px 0; }
.modal-actions { display: flex; gap: 10px; justify-content: flex-end; margin-top: 20px; }
.service-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 12px; margin-bottom: 16px; }
.service-card { background: var(--color-surface-2, rgba(255,255,255,0.04)); border: 1px solid var(--color-border, rgba(255,255,255,0.08)); border-radius: 8px; padding: 14px; }
.service-header { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; }
.service-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.dot-running { background: #22c55e; box-shadow: 0 0 6px rgba(34,197,94,0.5); }
.dot-stopped { background: #64748b; }
.service-name { font-weight: 600; font-size: 0.88rem; color: var(--color-text-primary, #e2e8f0); }
.service-port { font-size: 0.75rem; color: var(--color-text-secondary, #64748b); font-family: monospace; }
.service-note { font-size: 0.75rem; color: var(--color-text-secondary, #94a3b8); margin-bottom: 10px; }
.service-actions { display: flex; gap: 6px; }
.btn-start { padding: 4px 12px; border-radius: 4px; background: rgba(34,197,94,0.15); color: #22c55e; border: 1px solid rgba(34,197,94,0.3); cursor: pointer; font-size: 0.78rem; }
.btn-stop { padding: 4px 12px; border-radius: 4px; background: rgba(239,68,68,0.1); color: #f87171; border: 1px solid rgba(239,68,68,0.2); cursor: pointer; font-size: 0.78rem; }
.field-row { display: flex; flex-direction: column; gap: 4px; margin-bottom: 14px; }
.field-row label { font-size: 0.82rem; color: var(--color-text-secondary, #94a3b8); }
.field-row input { background: var(--color-surface-2, rgba(255,255,255,0.05)); border: 1px solid var(--color-border, rgba(255,255,255,0.12)); border-radius: 6px; color: var(--color-text-primary, #e2e8f0); padding: 7px 10px; font-size: 0.88rem; }
.field-hint { font-size: 0.72rem; color: var(--color-text-secondary, #64748b); margin-top: 3px; }
.btn-secondary { padding: 9px 18px; background: transparent; border: 1px solid var(--color-border, rgba(255,255,255,0.2)); border-radius: 7px; color: var(--color-text-secondary, #94a3b8); cursor: pointer; font-size: 0.88rem; }
.btn-danger { padding: 6px 14px; border-radius: 6px; background: rgba(239,68,68,0.1); color: #ef4444; border: 1px solid rgba(239,68,68,0.25); cursor: pointer; font-size: 0.82rem; }
.test-ok { color: #22c55e; font-size: 0.85rem; }
.test-fail { color: #ef4444; font-size: 0.85rem; }
.integration-card { background: var(--color-surface-2, rgba(255,255,255,0.04)); border: 1px solid var(--color-border, rgba(255,255,255,0.08)); border-radius: 8px; padding: 16px; margin-bottom: 12px; }
.integration-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.integration-name { font-weight: 600; font-size: 0.9rem; color: var(--color-text-primary, #e2e8f0); }
.status-badge { font-size: 0.72rem; padding: 2px 8px; border-radius: 10px; }
.badge-connected { background: rgba(34,197,94,0.15); color: #22c55e; border: 1px solid rgba(34,197,94,0.3); }
.badge-disconnected { background: rgba(100,116,139,0.15); color: #94a3b8; border: 1px solid rgba(100,116,139,0.2); }
.empty-note { font-size: 0.85rem; color: var(--color-text-secondary, #94a3b8); padding: 16px 0; }
.tier-badge { font-size: 0.68rem; padding: 2px 7px; border-radius: 8px; background: rgba(245,158,11,0.15); color: #f59e0b; border: 1px solid rgba(245,158,11,0.3); margin-right: 6px; }
.tier-locked { padding: 12px 0; font-size: 0.85rem; color: var(--color-text-secondary, #94a3b8); }
.integration-badges { display: flex; align-items: center; gap: 4px; }
</style>
