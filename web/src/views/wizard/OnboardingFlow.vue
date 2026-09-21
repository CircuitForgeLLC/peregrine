<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter, RouterLink } from 'vue-router'
import { useOnboardingHubStore } from '../../stores/onboardingHub'
import { useAppConfigStore } from '../../stores/appConfig'
import { useWizardStore } from '../../stores/wizard'
import { useApiFetch } from '../../composables/useApi'

type StepKey = 'compute_backend' | 'resume' | 'connections' | 'choice' | 'profile' | 'search'

interface StepDef {
  key: StepKey
  label: string
  to?: string
  complete: boolean
}

const hub = useOnboardingHubStore()
const config = useAppConfigStore()
const wizard = useWizardStore()
const router = useRouter()

const finishError = ref<string | null>(null)
const connectionsSaving = ref(false)
const connectionsError = ref<string | null>(null)

const steps = computed<StepDef[]>(() => {
  const s = hub.sections
  const list: StepDef[] = []

  if (!config.isCloud) {
    list.push({ key: 'compute_backend', label: 'Compute & AI Backend', to: '/settings/system', complete: s.compute_backend })
  }
  list.push({ key: 'resume', label: 'Resume', to: '/settings/resume', complete: s.resume })
  list.push({ key: 'connections', label: 'Connections', to: '/settings/connections', complete: hub.connectionsAcknowledged })
  list.push({ key: 'choice', label: 'How would you like to finish setting up?', to: '/wizard/setup-path', complete: hub.setupPath !== null })
  list.push({ key: 'profile', label: 'Profile', to: '/settings/my-profile', complete: s.profile })
  list.push({ key: 'search', label: 'Search Preferences', to: '/settings/search', complete: s.search })

  return list
})

// The first not-yet-complete step in order -- everything before it is done
// and stays visible/reopenable, everything after it is not shown yet.
const currentIndex = computed(() => {
  const idx = steps.value.findIndex(s => !s.complete)
  return idx === -1 ? steps.value.length : idx
})

const visibleSteps = computed(() => steps.value.slice(0, currentIndex.value + 1))

const requiredSectionsComplete = computed(() =>
  hub.sections.profile && hub.sections.resume && hub.sections.search,
)

async function acknowledgeConnections() {
  connectionsError.value = null
  connectionsSaving.value = true
  const { error } = await useApiFetch('/api/wizard/connections/acknowledge', { method: 'POST' })
  connectionsSaving.value = false
  if (error) { connectionsError.value = 'Failed to save. Please try again.'; return }
  await hub.loadSections()
}

async function finishSetup() {
  finishError.value = null
  const ok = await wizard.complete()
  if (!ok) { finishError.value = 'Failed to finish setup. Please try again.'; return }
  useApiFetch('/api/tasks/discovery', { method: 'POST' })
  config.wizardComplete = true
  router.replace('/')
}

onMounted(async () => {
  if (!config.loaded) await config.load()
  await hub.loadSections()
})
</script>

<template>
  <div class="flow">
    <header class="flow__header">
      <h1 class="flow__title">Set up your profile</h1>
      <p class="flow__subtitle">Step {{ Math.min(currentIndex + 1, steps.length) }} of {{ steps.length }}</p>
    </header>

    <ol class="flow__steps">
      <li v-for="(step, i) in visibleSteps" :key="step.key" class="flow__step" :class="{ 'flow__step--current': i === currentIndex }">
        <template v-if="step.key === 'connections' && i === currentIndex && !step.complete">
          <div class="flow-card">
            <span class="flow-card__label">{{ step.label }}</span>
            <p class="flow-card__desc">Set up email or integrations now, or skip and come back to this later.</p>
            <div class="flow-card__actions">
              <RouterLink :to="step.to!" class="btn-secondary">Configure Connections</RouterLink>
              <button class="btn-primary" :disabled="connectionsSaving" @click="acknowledgeConnections">
                {{ connectionsSaving ? 'Saving…' : 'Continue' }}
              </button>
            </div>
            <p v-if="connectionsError" class="error">{{ connectionsError }}</p>
          </div>
        </template>
        <template v-else>
          <RouterLink :to="step.to!" class="flow-card" :class="{ 'flow-card--complete': step.complete }">
            <span class="flow-card__status" aria-hidden="true">{{ step.complete ? '✓' : '○' }}</span>
            <span class="flow-card__label">{{ step.label }}</span>
          </RouterLink>
        </template>
      </li>
    </ol>

    <div v-if="requiredSectionsComplete" class="flow__finish">
      <p class="flow__finish-msg">Everything required is filled in.</p>
      <button class="btn-primary" :disabled="wizard.saving" @click="finishSetup">
        {{ wizard.saving ? 'Finishing…' : 'Finish Setup' }}
      </button>
      <p v-if="finishError" class="error">{{ finishError }}</p>
    </div>
  </div>
</template>

<style scoped>
.flow {
  min-height: 100dvh;
  padding: var(--space-8) var(--space-4);
  max-width: 640px;
  margin: 0 auto;
}

.flow__header {
  text-align: center;
  margin-bottom: var(--space-6);
}

.flow__title {
  font-family: var(--font-display);
  font-size: 1.625rem;
  font-weight: 700;
  color: var(--color-text);
  margin-bottom: var(--space-2);
}

.flow__subtitle {
  font-size: 0.9rem;
  color: var(--color-text-muted);
}

.flow__steps {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.flow-card {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  padding: var(--space-5);
  background: var(--color-surface-raised);
  border: 1px solid var(--color-border-light);
  border-radius: var(--radius-lg);
  text-decoration: none;
  color: var(--color-text);
  transition: border-color var(--transition);
}

.flow-card:hover,
.flow-card:focus-visible {
  border-color: var(--color-primary);
  outline: none;
}

.flow-card--complete {
  border-color: color-mix(in srgb, var(--color-success) 40%, transparent);
}

.flow-card__status {
  font-size: 1.25rem;
}

.flow-card__label {
  font-weight: 600;
}

.flow-card__desc {
  font-size: 0.85rem;
  color: var(--color-text-muted);
  margin: 0;
}

.flow-card__actions {
  display: flex;
  gap: var(--space-3);
  flex-wrap: wrap;
}

.btn-secondary {
  padding: var(--space-2) var(--space-5);
  background: transparent;
  color: var(--color-text);
  border: 1px solid var(--color-border-light);
  border-radius: var(--radius-md);
  font-family: var(--font-body);
  font-size: 0.9rem;
  font-weight: 600;
  text-decoration: none;
  display: inline-flex;
  align-items: center;
  min-height: 44px;
}

.flow__finish {
  margin-top: var(--space-8);
  padding: var(--space-5);
  background: color-mix(in srgb, var(--color-success) 10%, transparent);
  border: 1px solid color-mix(in srgb, var(--color-success) 35%, transparent);
  border-radius: var(--radius-md);
  display: flex;
  align-items: center;
  gap: var(--space-4);
  flex-wrap: wrap;
}

.flow__finish-msg {
  flex: 1;
  margin: 0;
  font-weight: 600;
  color: var(--color-success);
}

.btn-primary {
  padding: var(--space-2) var(--space-6);
  background: var(--color-primary);
  color: var(--color-text-inverse);
  border: none;
  border-radius: var(--radius-md);
  font-family: var(--font-body);
  font-size: 0.9rem;
  font-weight: 600;
  cursor: pointer;
  min-height: 44px;
}

.btn-primary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.error {
  font-size: 0.875rem;
  color: var(--color-error);
  margin: 0;
}
</style>
