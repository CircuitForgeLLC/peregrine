<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useApiFetch } from '../../composables/useApi'

const devTierOverride = ref<string | null>(null)
const hfTokenInput = ref('')
const hfTokenSet = ref(false)
const hfTestResult = ref<{ok: boolean; error?: string; username?: string} | null>(null)
const saving = ref(false)
const showWizardResetConfirm = ref(false)
const exportResult = ref<{count: number} | null>(null)

const TIERS = ['free', 'paid', 'premium', 'ultra']

onMounted(async () => {
  const { data } = await useApiFetch<{dev_tier_override: string | null; hf_token_set: boolean}>('/api/settings/developer')
  if (data) {
    devTierOverride.value = data.dev_tier_override ?? null
    hfTokenSet.value = data.hf_token_set
  }
})

async function saveTierOverride() {
  saving.value = true
  await useApiFetch('/api/settings/developer/tier', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ tier: devTierOverride.value }),
  })
  saving.value = false
  // Reload page so tier gate updates
  window.location.reload()
}

async function saveHfToken() {
  if (!hfTokenInput.value) return
  await useApiFetch('/api/settings/developer/hf-token', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ token: hfTokenInput.value }),
  })
  hfTokenSet.value = true
  hfTokenInput.value = ''
}

async function testHfToken() {
  const { data } = await useApiFetch<{ok: boolean; error?: string; username?: string}>('/api/settings/developer/hf-token/test', { method: 'POST' })
  hfTestResult.value = data
}

async function resetWizard() {
  await useApiFetch('/api/settings/developer/wizard-reset', { method: 'POST' })
  showWizardResetConfirm.value = false
}

async function exportClassifier() {
  const { data } = await useApiFetch<{count: number}>('/api/settings/developer/export-classifier', { method: 'POST' })
  if (data) exportResult.value = { count: data.count }
}
</script>

<template>
  <div class="developer-view">
    <h2>Developer</h2>

    <!-- Tier override -->
    <section class="form-section">
      <h3>Tier Override</h3>
      <p class="section-note">Override the effective tier for UI testing. Does not affect licensing.</p>
      <div class="field-row">
        <label>Override Tier</label>
        <select v-model="devTierOverride">
          <option :value="null">— none (use real tier) —</option>
          <option v-for="t in TIERS" :key="t" :value="t">{{ t }}</option>
        </select>
      </div>
      <div class="form-actions">
        <button @click="saveTierOverride" :disabled="saving" class="btn-primary">Apply Override</button>
      </div>
    </section>

    <!-- HF Token -->
    <section class="form-section">
      <h3>HuggingFace Token</h3>
      <p class="section-note">Required for model downloads and fine-tune uploads.</p>
      <p v-if="hfTokenSet" class="token-set">&#x2713; Token stored securely</p>
      <div class="field-row">
        <label>Token</label>
        <input v-model="hfTokenInput" type="password" placeholder="hf_…" autocomplete="new-password" />
      </div>
      <div class="form-actions">
        <button @click="saveHfToken" :disabled="!hfTokenInput" class="btn-primary">Save Token</button>
        <button @click="testHfToken" class="btn-secondary">Test</button>
      </div>
      <p v-if="hfTestResult" :class="hfTestResult.ok ? 'status-ok' : 'error-msg'">
        {{ hfTestResult.ok ? `✓ Logged in as ${hfTestResult.username}` : '✗ ' + hfTestResult.error }}
      </p>
    </section>

    <!-- Wizard reset -->
    <section class="form-section">
      <h3>Wizard</h3>
      <div class="form-actions">
        <button @click="showWizardResetConfirm = true" class="btn-warning">Reset Setup Wizard</button>
      </div>
      <Teleport to="body">
        <div v-if="showWizardResetConfirm" class="modal-overlay" @click.self="showWizardResetConfirm = false">
          <div class="modal-card" role="dialog">
            <h3>Reset Setup Wizard?</h3>
            <p>The first-run setup wizard will be shown again on next launch.</p>
            <div class="modal-actions">
              <button @click="resetWizard" class="btn-warning">Reset</button>
              <button @click="showWizardResetConfirm = false" class="btn-secondary">Cancel</button>
            </div>
          </div>
        </div>
      </Teleport>
    </section>

    <!-- Export classifier data -->
    <section class="form-section">
      <h3>Export Training Data</h3>
      <p class="section-note">Export labeled emails as JSONL for classifier training.</p>
      <div class="form-actions">
        <button @click="exportClassifier" class="btn-secondary">Export to data/email_score.jsonl</button>
      </div>
      <p v-if="exportResult" class="status-ok">Exported {{ exportResult.count }} labeled emails.</p>
    </section>
  </div>
</template>
