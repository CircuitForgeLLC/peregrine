<script setup lang="ts">
import { useRouter } from 'vue-router'
import { useApiFetch } from '../../composables/useApi'
import { useAiSetupAccess } from '../../composables/useAiSetupAccess'

const router = useRouter()
const { hasAccess } = useAiSetupAccess()

async function choose(path: 'ai' | 'manual') {
  await useApiFetch('/api/wizard/setup-path', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ path }),
  })
  router.push(path === 'ai' ? '/wizard/ai-profile' : '/setup')
}
</script>

<template>
  <div class="path-choice">
    <h2 class="path-choice__title">How would you like to finish setting up?</h2>
    <p class="path-choice__subtitle">
      Either way, you can go back and change anything afterward in Settings.
    </p>

    <div class="path-choice__options">
      <button
        type="button"
        data-testid="setup-path-ai"
        class="path-choice__option"
        :disabled="!hasAccess"
        @click="choose('ai')"
      >
        <span class="path-choice__option-label">Set up with AI</span>
        <span class="path-choice__option-desc">
          Answer a few questions in a short chat and we'll fill in the rest.
        </span>
        <span v-if="!hasAccess" class="path-choice__lock">
          Upgrade to Paid, or bring your own LLM key, to unlock this.
        </span>
      </button>

      <button
        type="button"
        data-testid="setup-path-manual"
        class="path-choice__option"
        @click="choose('manual')"
      >
        <span class="path-choice__option-label">Set up manually</span>
        <span class="path-choice__option-desc">
          Fill in your profile and search preferences yourself.
        </span>
      </button>
    </div>
  </div>
</template>

<style scoped>
.path-choice {
  max-width: 640px;
  margin: 0 auto;
  padding: var(--space-8) var(--space-4);
  text-align: center;
}

.path-choice__title {
  font-family: var(--font-display);
  font-size: 1.375rem;
  font-weight: 700;
  color: var(--color-text);
  margin-bottom: var(--space-2);
}

.path-choice__subtitle {
  font-size: 0.9rem;
  color: var(--color-text-muted);
  margin-bottom: var(--space-6);
}

.path-choice__options {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--space-4);
}

@media (max-width: 600px) {
  .path-choice__options {
    grid-template-columns: 1fr;
  }
}

.path-choice__option {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  padding: var(--space-5);
  background: var(--color-surface-raised);
  border: 1px solid var(--color-border-light);
  border-radius: var(--radius-lg);
  font-family: var(--font-body);
  text-align: left;
  cursor: pointer;
  transition: border-color var(--transition);
}

.path-choice__option:hover:not(:disabled),
.path-choice__option:focus-visible:not(:disabled) {
  border-color: var(--color-primary);
  outline: none;
}

.path-choice__option:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.path-choice__option-label {
  font-weight: 600;
  color: var(--color-text);
}

.path-choice__option-desc {
  font-size: 0.85rem;
  color: var(--color-text-muted);
}

.path-choice__lock {
  font-size: 0.8rem;
  color: var(--color-text-muted);
  font-style: italic;
}
</style>
