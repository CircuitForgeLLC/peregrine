<template>
  <div class="wizard">
    <div class="wizard__card">
      <!-- Header -->
      <div class="wizard__header">
        <img
          v-if="logoSrc"
          :src="logoSrc"
          alt="Peregrine"
          class="wizard__logo"
        />
        <h1 class="wizard__title">Welcome to Peregrine</h1>
        <p class="wizard__subtitle">
          Complete the setup to start your job search.
          Progress saves automatically.
        </p>
      </div>

      <!-- Progress bar -->
      <div class="wizard__progress" role="progressbar"
           :aria-valuenow="Math.round(wizard.progressFraction * 100)"
           aria-valuemin="0" aria-valuemax="100">
        <div class="wizard__progress-track">
          <div class="wizard__progress-fill" :style="{ width: `${wizard.progressFraction * 100}%` }" />
        </div>
        <span class="wizard__progress-label">{{ wizard.stepLabel }}</span>
      </div>

      <!-- Step content -->
      <div class="wizard__body">
        <div v-if="wizard.loading" class="wizard__loading" aria-live="polite">
          <span class="wizard__spinner" aria-hidden="true" />
          Loading…
        </div>
        <RouterView v-else />
      </div>

      <!-- Global error banner -->
      <div v-if="wizard.errors.length" class="wizard__error" role="alert">
        <span v-for="e in wizard.errors" :key="e">{{ e }}</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useWizardStore } from '../../stores/wizard'
import { useAppConfigStore } from '../../stores/appConfig'

const wizard = useWizardStore()
const config = useAppConfigStore()
const router = useRouter()

// Peregrine logo — served from the static assets directory
const logoSrc = '/static/peregrine_logo_circle.png'

onMounted(async () => {
  if (!config.loaded) await config.load()
  const target = await wizard.loadStatus(config.isCloud)
  if (router.currentRoute.value.path === '/setup') {
    router.replace(target)
  }
})
</script>

<style scoped>
.wizard {
  min-height: 100dvh;
  display: flex;
  align-items: flex-start;
  justify-content: center;
  padding: var(--space-8) var(--space-4);
  background: var(--color-surface);
}

.wizard__card {
  width: 100%;
  max-width: 640px;
  background: var(--color-surface-raised);
  border: 1px solid var(--color-border-light);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-lg);
  overflow: hidden;
}

.wizard__header {
  padding: var(--space-8) var(--space-8) var(--space-6);
  text-align: center;
  border-bottom: 1px solid var(--color-border-light);
}

.wizard__logo {
  width: 56px;
  height: 56px;
  border-radius: var(--radius-full);
  margin-bottom: var(--space-4);
}

.wizard__title {
  font-family: var(--font-display);
  font-size: 1.625rem;
  font-weight: 700;
  color: var(--color-text);
  margin-bottom: var(--space-2);
}

.wizard__subtitle {
  font-size: 0.9rem;
  color: var(--color-text-muted);
}

/* Progress */
.wizard__progress {
  padding: var(--space-4) var(--space-8);
  border-bottom: 1px solid var(--color-border-light);
}

.wizard__progress-track {
  height: 6px;
  background: var(--color-surface-alt);
  border-radius: var(--radius-full);
  overflow: hidden;
  margin-bottom: var(--space-2);
}

.wizard__progress-fill {
  height: 100%;
  background: var(--color-primary);
  border-radius: var(--radius-full);
  transition: width var(--transition-slow);
}

.wizard__progress-label {
  font-size: 0.8rem;
  color: var(--color-text-muted);
  font-weight: 500;
}

/* Body */
.wizard__body {
  padding: var(--space-8);
}

/* Loading */
.wizard__loading {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  color: var(--color-text-muted);
  font-size: 0.9rem;
  padding: var(--space-8) 0;
  justify-content: center;
}

.wizard__spinner {
  display: inline-block;
  width: 18px;
  height: 18px;
  border: 2px solid var(--color-border);
  border-top-color: var(--color-primary);
  border-radius: var(--radius-full);
  animation: spin 0.7s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

/* Error */
.wizard__error {
  margin: 0 var(--space-8) var(--space-6);
  padding: var(--space-3) var(--space-4);
  background: color-mix(in srgb, var(--color-error) 10%, transparent);
  border: 1px solid var(--color-error);
  border-radius: var(--radius-md);
  color: var(--color-error);
  font-size: 0.875rem;
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}

/* Mobile */
@media (max-width: 680px) {
  .wizard {
    padding: 0;
    align-items: stretch;
  }

  .wizard__card {
    border-radius: 0;
    box-shadow: none;
    min-height: 100dvh;
  }

  .wizard__header,
  .wizard__body {
    padding-left: var(--space-6);
    padding-right: var(--space-6);
  }
}
</style>
