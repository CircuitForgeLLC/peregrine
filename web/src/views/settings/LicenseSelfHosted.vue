<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { storeToRefs } from 'pinia'
import { useLicenseStore } from '../../stores/settings/license'

const store = useLicenseStore()
const { tier, licenseKey, active, gracePeriodEnds, activating, activateError } = storeToRefs(store)
const keyInput = ref('')
const showDeactivateConfirm = ref(false)

onMounted(() => store.loadLicense())
</script>

<template>
  <div class="form-section">
    <h2>License</h2>

    <!-- Active license -->
    <template v-if="active">
      <div class="license-info">
        <span :class="`tier-badge tier-${tier}`">{{ tier.toUpperCase() }}</span>
        <span v-if="licenseKey" class="license-key">{{ licenseKey }}</span>
        <span v-if="gracePeriodEnds" class="grace-notice">Grace period ends: {{ gracePeriodEnds }}</span>
      </div>
      <div class="form-actions">
        <button @click="showDeactivateConfirm = true" class="btn-danger">Deactivate</button>
      </div>
      <Teleport to="body">
        <div v-if="showDeactivateConfirm" class="modal-overlay" @click.self="showDeactivateConfirm = false">
          <div class="modal-card" role="dialog">
            <h3>Deactivate License?</h3>
            <p>You will lose access to paid features. You can reactivate later with the same key.</p>
            <div class="modal-actions">
              <button @click="store.deactivate(); showDeactivateConfirm = false" class="btn-danger">Deactivate</button>
              <button @click="showDeactivateConfirm = false" class="btn-secondary">Cancel</button>
            </div>
          </div>
        </div>
      </Teleport>
    </template>

    <!-- No active license -->
    <template v-else>
      <p class="section-note">Enter your license key to unlock paid features.</p>
      <div class="field-row">
        <label>License Key</label>
        <input v-model="keyInput" placeholder="CFG-PRNG-XXXX-XXXX-XXXX" class="monospace" />
      </div>
      <p v-if="activateError" class="error-msg">{{ activateError }}</p>
      <div class="form-actions">
        <button @click="store.activate(keyInput)" :disabled="!keyInput || activating" class="btn-primary">
          {{ activating ? 'Activating…' : 'Activate' }}
        </button>
      </div>
    </template>
  </div>
</template>
