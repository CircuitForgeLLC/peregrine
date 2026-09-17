<template>
  <div class="hub">
    <header class="hub__header">
      <h1 class="hub__title">Set up your profile</h1>
      <p class="hub__subtitle">
        Complete each section in any order. Progress saves automatically.
      </p>
    </header>

    <div class="hub__grid">
      <RouterLink
        v-for="card in cards"
        :key="card.key"
        :to="card.to"
        class="hub-card"
        :class="{ 'hub-card--complete': sections[card.key] }"
      >
        <span class="hub-card__status" aria-hidden="true">{{ sections[card.key] ? '✓' : '○' }}</span>
        <span class="hub-card__label">{{ card.label }}</span>
        <span class="hub-card__status-text">{{ sections[card.key] ? 'Complete' : 'Incomplete' }}</span>
      </RouterLink>
    </div>

    <div class="hub__optional">
      <h2 class="hub__optional-title">Optional</h2>
      <RouterLink to="/settings/connections" class="hub-card hub-card--optional">
        <span class="hub-card__label">Integrations</span>
      </RouterLink>
      <RouterLink to="/settings/fine-tune" class="hub-card hub-card--optional">
        <span class="hub-card__label">Fine-tuning</span>
      </RouterLink>
    </div>

    <div v-if="requiredSectionsComplete" class="hub__finish">
      <p class="hub__finish-msg">Everything required is filled in.</p>
      <button class="btn-primary" :disabled="wizard.saving" @click="finishSetup">
        {{ wizard.saving ? 'Finishing…' : 'Finish Setup' }}
      </button>
      <p v-if="finishError" class="error">{{ finishError }}</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useOnboardingHubStore } from '../../stores/onboardingHub'
import { useAppConfigStore } from '../../stores/appConfig'
import { useWizardStore } from '../../stores/wizard'

const hub = useOnboardingHubStore()
const config = useAppConfigStore()
const wizard = useWizardStore()
const router = useRouter()

const sections = computed(() => hub.sections)
const finishError = ref<string | null>(null)

interface HubCardDef {
  key: 'profile' | 'resume' | 'search' | 'compute_backend'
  label: string
  to: string
  cloudHidden?: boolean
}

const ALL_CARDS: HubCardDef[] = [
  { key: 'compute_backend', label: 'Compute & AI Backend', to: '/settings/system', cloudHidden: true },
  { key: 'profile', label: 'Profile', to: '/settings/my-profile' },
  { key: 'resume', label: 'Resume', to: '/settings/resume' },
  { key: 'search', label: 'Search Preferences', to: '/settings/search' },
]

const cards = computed(() => ALL_CARDS.filter(c => !(c.cloudHidden && config.isCloud)))

// Required for completion: profile, resume, search. Matches the spec's
// minimal-required-section set. compute_backend stays optional (sensible
// hardware/inference defaults exist from day one) and is never required
// here, in cloud mode or self-hosted.
const requiredSectionsComplete = computed(() =>
  sections.value.profile && sections.value.resume && sections.value.search,
)

async function finishSetup() {
  finishError.value = null
  const ok = await wizard.complete()
  if (!ok) { finishError.value = 'Failed to finish setup. Please try again.'; return }
  // Order matters: config.wizardComplete must flip before the redirect,
  // or wizardGuard's next navigation check can still see the stale value
  // and bounce back to /setup (see peregrine_wizard_complete_guard).
  config.wizardComplete = true
  router.replace('/')
}

onMounted(async () => {
  if (!config.loaded) await config.load()
  await hub.loadSections()
})
</script>

<style scoped>
.hub {
  min-height: 100dvh;
  padding: var(--space-8) var(--space-4);
  max-width: 720px;
  margin: 0 auto;
}

.hub__header {
  text-align: center;
  margin-bottom: var(--space-8);
}

.hub__title {
  font-family: var(--font-display);
  font-size: 1.625rem;
  font-weight: 700;
  color: var(--color-text);
  margin-bottom: var(--space-2);
}

.hub__subtitle {
  font-size: 0.9rem;
  color: var(--color-text-muted);
}

.hub__grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: var(--space-4);
}

.hub-card {
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

.hub-card:hover,
.hub-card:focus-visible {
  border-color: var(--color-primary);
  outline: none;
}

.hub-card--complete {
  border-color: color-mix(in srgb, var(--color-success) 40%, transparent);
}

.hub-card__status {
  font-size: 1.25rem;
}

.hub-card__label {
  font-weight: 600;
}

.hub-card__status-text {
  font-size: 0.8rem;
  color: var(--color-text-muted);
}

.hub__optional {
  margin-top: var(--space-8);
}

.hub__optional-title {
  font-size: 0.9rem;
  font-weight: 600;
  color: var(--color-text-muted);
  margin-bottom: var(--space-3);
}

.hub-card--optional {
  display: inline-flex;
  margin-right: var(--space-3);
  padding: var(--space-3) var(--space-4);
}

.hub__finish {
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

.hub__finish-msg {
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
