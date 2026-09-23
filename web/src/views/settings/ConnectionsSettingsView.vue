<template>
  <div class="connections-settings">
    <h2>Connections</h2>
    <p class="tab-note">Configure email and external service integrations.</p>

    <p v-if="store.loadError" class="error-banner">{{ store.loadError }}</p>

    <!-- Email section -->
    <section class="form-section">
      <h3>Email (IMAP)</h3>
      <p class="section-note">Used for email sync in the Interviews pipeline.</p>

      <div class="field-row">
        <label>Provider</label>
        <select v-model="selectedProvider" @change="applyProviderPreset">
          <option value="">Custom / other</option>
          <option v-for="p in EMAIL_PROVIDERS" :key="p.id" :value="p.id">{{ p.label }}</option>
        </select>
      </div>
      <p v-if="activeProvider" class="field-hint">
        {{ activeProvider.appPasswordHint }}
        <a :href="activeProvider.appPasswordUrl" target="_blank" rel="noopener">Get an app password →</a>
      </p>

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
        <span class="field-hint">Most providers require an app-specific password, not your regular login password. Tip: type ${ENV_VAR_NAME} to use an environment variable.</span>
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
        <div v-if="!meetsRequiredTier(integration.tier_required)" class="tier-locked">
          <p>Upgrade to {{ integration.tier_required }} to use this integration.</p>
        </div>
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
              <span v-if="store.integrationResults[integration.id]" :class="store.integrationResults[integration.id].ok ? 'test-ok' : 'test-fail'">
                {{ store.integrationResults[integration.id].ok ? '✓ OK' : '✗ ' + store.integrationResults[integration.id].error }}
              </span>
            </div>
          </div>
          <div v-else>
            <button @click="store.disconnectIntegration(integration.id)" class="btn-danger">Disconnect</button>
          </div>
        </template>
      </div>
    </section>
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

const emailPasswordInput = ref('')
const emailTestResult = ref<boolean | null>(null)
const integrationInputs = ref<Record<string, string>>({})

// ── Email provider presets ──────────────────────────────────────────────────
// Google buried the app-password page a few settings layers deep behind
// "2-Step Verification" (it used to be one click from the main security
// page) -- a direct link plus the equivalent for the other major providers
// saves a frustrating hunt, and the host/port/SSL/sent-folder presets save
// typing values most users wouldn't otherwise know off-hand.

interface EmailProvider {
  id: string
  label: string
  host: string
  port: number
  ssl: boolean
  sentFolder: string
  appPasswordHint: string
  appPasswordUrl: string
}

const EMAIL_PROVIDERS: EmailProvider[] = [
  {
    id: 'gmail',
    label: 'Gmail',
    host: 'imap.gmail.com',
    port: 993,
    ssl: true,
    sentFolder: '[Gmail]/Sent Mail',
    appPasswordHint: 'Requires 2-Step Verification to be turned on first, then an app password from your Google Account.',
    appPasswordUrl: 'https://myaccount.google.com/apppasswords',
  },
  {
    id: 'outlook',
    label: 'Outlook / Microsoft 365',
    host: 'outlook.office365.com',
    port: 993,
    ssl: true,
    sentFolder: 'Sent Items',
    appPasswordHint: 'Generate an app password from your Microsoft account security settings.',
    appPasswordUrl: 'https://account.microsoft.com/security',
  },
  {
    id: 'icloud',
    label: 'iCloud Mail',
    host: 'imap.mail.me.com',
    port: 993,
    ssl: true,
    sentFolder: 'Sent Messages',
    appPasswordHint: 'Apple calls these "app-specific passwords" -- generate one from Sign-In and Security in your Apple ID settings.',
    appPasswordUrl: 'https://appleid.apple.com/account/manage',
  },
  {
    id: 'yahoo',
    label: 'Yahoo Mail',
    host: 'imap.mail.yahoo.com',
    port: 993,
    ssl: true,
    sentFolder: 'Sent',
    appPasswordHint: 'Generate an app password from Yahoo Account Security.',
    appPasswordUrl: 'https://login.yahoo.com/myaccount/security',
  },
]

const selectedProvider = ref('')
const activeProvider = computed(() =>
  EMAIL_PROVIDERS.find(p => p.id === selectedProvider.value) ?? null
)

function applyProviderPreset() {
  const provider = activeProvider.value
  if (!provider) return
  const cfg = store.emailConfig as any
  cfg.host = provider.host
  cfg.port = provider.port
  cfg.ssl = provider.ssl
  cfg.sent_folder = provider.sentFolder
}

const tierOrder = ['free', 'paid', 'premium', 'ultra']
function meetsRequiredTier(required: string): boolean {
  return tierOrder.indexOf(tier.value) >= tierOrder.indexOf(required || 'free')
}

async function handleTestEmail() {
  const result = await store.testEmail()
  emailTestResult.value = result?.ok ?? false
}

async function handleSaveEmail() {
  const payload = { ...store.emailConfig, password: emailPasswordInput.value || undefined }
  await store.saveEmailWithPassword(payload)
  // test_email() always tests the *stored* credential, never one just typed
  // into the form -- a test run before Save (a natural first instinct) fails
  // against whatever was previously saved (often nothing), and that failure
  // then sits on screen indefinitely since nothing else clears it, looking
  // like the connection is still broken even after a successful save.
  // Re-test automatically so the badge reflects what was actually just saved.
  emailPasswordInput.value = ''
  await handleTestEmail()
}

async function handleConnect(id: string) {
  const integration = store.integrations.find(i => i.id === id)
  if (!integration) return
  const credentials: Record<string, string> = {}
  for (const field of integration.fields) {
    credentials[field.key] = integrationInputs.value[`${id}:${field.key}`] ?? ''
  }
  await store.connectIntegration(id, credentials)
}

async function handleTest(id: string) {
  const integration = store.integrations.find(i => i.id === id)
  if (!integration) return
  const credentials: Record<string, string> = {}
  for (const field of integration.fields) {
    credentials[field.key] = integrationInputs.value[`${id}:${field.key}`] ?? ''
  }
  await store.testIntegration(id, credentials)
}

onMounted(async () => {
  await Promise.all([store.loadEmail(), store.loadIntegrations()])
  const savedHost = (store.emailConfig as any)?.host
  const matched = EMAIL_PROVIDERS.find(p => p.host === savedHost)
  if (matched) selectedProvider.value = matched.id
})
</script>

<style scoped>
.connections-settings { max-width: 720px; margin: 0 auto; padding: var(--space-4); }
h2 { font-size: 1.4rem; font-weight: 600; margin-bottom: 6px; }
h3 { font-size: 1rem; font-weight: 600; margin-bottom: var(--space-3); }
.tab-note { font-size: 0.82rem; color: var(--color-text-muted); margin-bottom: var(--space-6); }
.error-banner {
  background: color-mix(in srgb, var(--color-error) 10%, transparent);
  border: 1px solid color-mix(in srgb, var(--color-error) 30%, transparent);
  border-radius: 6px;
  color: var(--color-error);
  padding: 10px 14px;
  margin-bottom: 20px;
  font-size: 0.85rem;
}
.form-section {
  margin-bottom: var(--space-8);
  padding-bottom: var(--space-6);
  border-bottom: 1px solid var(--color-border);
}
.section-note { font-size: 0.78rem; color: var(--color-text-muted); margin-bottom: 14px; }
.field-row { display: flex; flex-direction: column; gap: 4px; margin-bottom: 14px; }
.field-row label { font-size: 0.82rem; color: var(--color-text-muted); }
.field-row input,
.field-row select {
  background: var(--color-surface-alt);
  border: 1px solid var(--color-border);
  border-radius: 6px;
  color: var(--color-text);
  padding: 7px 10px;
  font-size: 0.88rem;
}
.field-hint { font-size: 0.72rem; color: var(--color-text-muted); margin-top: 3px; }
.field-hint a { color: var(--app-primary); }
.checkbox-row {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  font-size: 0.85rem;
  color: var(--color-text);
  cursor: pointer;
  margin: 0 0 14px;
}
.form-actions { display: flex; align-items: center; gap: var(--space-4); flex-wrap: wrap; }
.btn-primary {
  padding: 9px 24px;
  background: var(--color-accent);
  color: var(--color-text-inverse);
  border: none;
  border-radius: 7px;
  font-size: 0.9rem;
  cursor: pointer;
  font-weight: 600;
}
.btn-primary:disabled { opacity: 0.5; cursor: not-allowed; }
.btn-secondary {
  padding: 9px 18px;
  background: transparent;
  border: 1px solid var(--color-border);
  border-radius: 7px;
  color: var(--color-text-muted);
  cursor: pointer;
  font-size: 0.88rem;
}
.btn-danger {
  padding: 6px 14px;
  border-radius: 6px;
  background: color-mix(in srgb, var(--color-error) 10%, transparent);
  color: var(--color-error);
  border: 1px solid color-mix(in srgb, var(--color-error) 25%, transparent);
  cursor: pointer;
  font-size: 0.82rem;
}
.error { color: var(--color-error); font-size: 0.82rem; }
.test-ok { color: var(--color-success); font-size: 0.85rem; }
.test-fail { color: var(--color-error); font-size: 0.85rem; }
.integration-card {
  background: var(--color-surface-alt);
  border: 1px solid var(--color-border);
  border-radius: 8px;
  padding: 16px;
  margin-bottom: 12px;
}
.integration-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}
.integration-name { font-weight: 600; font-size: 0.9rem; color: var(--color-text); }
.integration-badges { display: flex; align-items: center; gap: 4px; }
.status-badge { font-size: 0.72rem; padding: 2px 8px; border-radius: 10px; }
.badge-connected {
  background: color-mix(in srgb, var(--color-success) 15%, transparent);
  color: var(--color-success);
  border: 1px solid color-mix(in srgb, var(--color-success) 30%, transparent);
}
.badge-disconnected {
  background: color-mix(in srgb, var(--color-text-muted) 15%, transparent);
  color: var(--color-text-muted);
  border: 1px solid color-mix(in srgb, var(--color-text-muted) 20%, transparent);
}
.tier-badge {
  font-size: 0.68rem;
  padding: 2px 7px;
  border-radius: 8px;
  background: color-mix(in srgb, var(--color-warning) 15%, transparent);
  color: var(--color-warning);
  border: 1px solid color-mix(in srgb, var(--color-warning) 30%, transparent);
  margin-right: 6px;
}
.tier-locked { padding: 12px 0; font-size: 0.85rem; color: var(--color-text-muted); }
.empty-note { font-size: 0.85rem; color: var(--color-text-muted); padding: 16px 0; }
.integration-form .field-row { margin-bottom: 10px; }
</style>
