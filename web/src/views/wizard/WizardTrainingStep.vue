<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAppConfigStore } from '../../stores/appConfig'

const router = useRouter()
const config = useAppConfigStore()
const optIn = ref(false)
const saving = ref(false)

async function next() {
  saving.value = true
  try {
    if (optIn.value) {
      await fetch('/api/settings/fine-tune/opt-in', {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ enabled: true }),
      })
    }
    router.push('/setup/identity')
  } finally {
    saving.value = false
  }
}

function back() { router.push('/setup/resume') }
</script>

<template>
  <div class="wizard-step">
    <h2 class="step-title">
      Training Export
      <span class="optional-badge">Optional</span>
    </h2>
    <p class="step-body">
      Would you like to save your cover letters for training export?
      This lets you build a personal dataset to fine-tune a language model to your writing style.
    </p>
    <p v-if="!config.isCloud" class="step-body-note">
      Your data stays on your device unless you explicitly request cloud fine-tuning.
    </p>
    <p v-else class="step-body-note">
      Your cover letters are stored on your CircuitForge account.
      They are not shared with any third party unless you request cloud fine-tuning.
    </p>

    <label class="opt-in-label">
      <input type="checkbox" v-model="optIn" />
      Yes, include my cover letters in training export
    </label>

    <div class="step-actions">
      <button class="btn-ghost" @click="back">
        <span aria-hidden="true">←</span> Back
      </button>
      <button class="btn-primary" :disabled="saving" :aria-busy="saving" @click="next">
        {{ saving ? 'Saving…' : 'Continue' }}
        <span v-if="!saving" aria-hidden="true">→</span>
      </button>
    </div>
  </div>
</template>

<style scoped>
.wizard-step { display: flex; flex-direction: column; gap: var(--space-5, 1.25rem); }
.step-title { font-family: var(--font-display); font-size: 1.25rem; font-weight: 700; display: flex; align-items: center; gap: var(--space-2, 0.5rem); }
.optional-badge { font-family: var(--font-body); font-size: 0.75rem; font-weight: 500; background: var(--color-surface-alt); color: var(--color-text-muted); padding: 2px 8px; border-radius: var(--radius-full, 9999px); }
.step-body { font-size: 0.9rem; color: var(--color-text); line-height: 1.6; }
.step-body-note { font-size: 0.85rem; color: var(--color-text-muted); line-height: 1.5; margin-top: calc(-1 * var(--space-3, 0.75rem)); }
.opt-in-label { display: flex; align-items: flex-start; gap: var(--space-2, 0.5rem); font-size: 0.9rem; cursor: pointer; }
.opt-in-label input[type="checkbox"] { margin-top: 2px; width: 16px; height: 16px; accent-color: var(--color-primary); flex-shrink: 0; cursor: pointer; }
.step-actions { display: flex; gap: var(--space-3, 0.75rem); justify-content: flex-end; padding-top: var(--space-4, 1rem); border-top: 1px solid var(--color-border-light); }
</style>
