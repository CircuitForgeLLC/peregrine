<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { storeToRefs } from 'pinia'
import { usePrivacyStore } from '../../stores/settings/privacy'
import { useAppConfigStore } from '../../stores/appConfig'
import { useSystemStore } from '../../stores/settings/system'

const privacy = usePrivacyStore()
const config = useAppConfigStore()
const system = useSystemStore()
const { telemetryOptIn, masterOff, usageEvents, contentSharing, showByokPanel, saving } = storeToRefs(privacy)

// Sync active cloud backends from system store into privacy store
const activeCloudBackends = computed(() =>
  system.backends.filter(b => b.enabled && ['anthropic', 'openai'].includes(b.id)).map(b => b.id)
)

onMounted(async () => {
  await privacy.loadPrivacy()
  privacy.activeCloudBackends = activeCloudBackends.value
})

async function handleSave() {
  if (config.isCloud) {
    await privacy.savePrivacy({ master_off: masterOff.value, usage_events: usageEvents.value, content_sharing: contentSharing.value })
  } else {
    await privacy.savePrivacy({ telemetry_opt_in: telemetryOptIn.value })
  }
}
</script>

<template>
  <div class="privacy-view">
    <h2>Privacy</h2>

    <!-- Self-hosted -->
    <template v-if="!config.isCloud">
      <section class="form-section">
        <h3>Telemetry</h3>
        <p class="section-note">Peregrine is fully local by default — no data leaves your machine unless you opt in.</p>
        <label class="checkbox-row">
          <input type="checkbox" v-model="telemetryOptIn" />
          Share anonymous usage statistics to help improve Peregrine
        </label>
      </section>

      <!-- BYOK Info Panel -->
      <section v-if="showByokPanel" class="form-section byok-panel">
        <h3>Cloud LLM Privacy Notice</h3>
        <p>You have cloud LLM backends enabled. Your job descriptions and cover letter content will be sent to those providers' APIs. Peregrine never logs this content, but the providers' own data policies apply.</p>
        <div class="form-actions">
          <button @click="privacy.dismissByokInfo()" class="btn-secondary">Got it, don't show again</button>
        </div>
      </section>
    </template>

    <!-- Cloud -->
    <template v-else>
      <section class="form-section">
        <h3>Data Controls</h3>
        <label class="checkbox-row danger">
          <input type="checkbox" v-model="masterOff" />
          Disable all data collection (master off)
        </label>
        <label class="checkbox-row">
          <input type="checkbox" v-model="usageEvents" :disabled="masterOff" />
          Usage events (feature analytics)
        </label>
        <label class="checkbox-row">
          <input type="checkbox" v-model="contentSharing" :disabled="masterOff" />
          Share content for model improvement
        </label>
      </section>
    </template>

    <div class="form-actions">
      <button @click="handleSave" :disabled="saving" class="btn-primary">
        {{ saving ? 'Saving…' : 'Save' }}
      </button>
    </div>
  </div>
</template>
