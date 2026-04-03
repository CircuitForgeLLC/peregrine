<template>
  <div class="step">
    <h2 class="step__heading">Step 7 — Integrations</h2>
    <p class="step__caption">
      Optional. Connect external tools to supercharge your workflow.
      You can configure these any time in Settings → System.
    </p>

    <div class="int-grid">
      <label
        v-for="card in integrations"
        :key="card.id"
        class="int-card"
        :class="{
          'int-card--selected': selected.has(card.id),
          'int-card--paid': card.paid && !isPaid,
        }"
      >
        <input
          type="checkbox"
          class="int-card__check"
          :value="card.id"
          :disabled="card.paid && !isPaid"
          v-model="checkedIds"
        />
        <span class="int-card__icon" aria-hidden="true">{{ card.icon }}</span>
        <span class="int-card__name">{{ card.name }}</span>
        <span v-if="card.paid && !isPaid" class="int-card__badge">Paid</span>
      </label>
    </div>

    <div v-if="selected.size > 0" class="step__info" style="margin-top: var(--space-4)">
      You'll configure credentials for {{ [...selected].map(id => labelFor(id)).join(', ') }}
      in Settings → System after setup completes.
    </div>

    <div class="step__nav">
      <button class="btn-ghost" @click="back">← Back</button>
      <button class="btn-primary" :disabled="wizard.saving" @click="finish">
        {{ wizard.saving ? 'Saving…' : 'Finish Setup →' }}
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import { useWizardStore } from '../../stores/wizard'
import { useAppConfigStore } from '../../stores/appConfig'
import './wizard.css'

const wizard = useWizardStore()
const config = useAppConfigStore()
const router = useRouter()

const isPaid = computed(() =>
  wizard.tier === 'paid' || wizard.tier === 'premium',
)

interface IntegrationCard {
  id: string
  name: string
  icon: string
  paid: boolean
}

const integrations: IntegrationCard[] = [
  { id: 'notion',           name: 'Notion',          icon: '🗒️',  paid: false },
  { id: 'google_calendar',  name: 'Google Calendar',  icon: '📅',  paid: true  },
  { id: 'apple_calendar',   name: 'Apple Calendar',   icon: '🍏',  paid: true  },
  { id: 'slack',            name: 'Slack',            icon: '💬',  paid: true  },
  { id: 'discord',          name: 'Discord',          icon: '🎮',  paid: true  },
  { id: 'google_drive',     name: 'Google Drive',     icon: '📁',  paid: true  },
]

const checkedIds = ref<string[]>([])
const selected = computed(() => new Set(checkedIds.value))

function labelFor(id: string): string {
  return integrations.find(i => i.id === id)?.name ?? id
}

function back() { router.push('/setup/search') }

async function finish() {
  // Save integration selections (step 7) then mark wizard complete
  await wizard.saveStep(7, { integrations: [...checkedIds.value] })
  const ok = await wizard.complete()
  if (ok) router.replace('/')
}
</script>

<style scoped>
.int-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
  gap: var(--space-3);
  margin-top: var(--space-2);
}

.int-card {
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-4) var(--space-3);
  border: 2px solid var(--color-border-light);
  border-radius: var(--radius-md);
  background: var(--color-surface-alt);
  cursor: pointer;
  transition: border-color var(--transition), background var(--transition);
  text-align: center;
}

.int-card:hover:not(.int-card--paid) {
  border-color: var(--color-border);
}

.int-card--selected {
  border-color: var(--color-primary);
  background: color-mix(in srgb, var(--color-primary) 6%, var(--color-surface-alt));
}

.int-card--paid {
  opacity: 0.55;
  cursor: not-allowed;
}

.int-card__check {
  /* visually hidden but accessible */
  position: absolute;
  opacity: 0;
  width: 0;
  height: 0;
}

.int-card__icon {
  font-size: 1.75rem;
}

.int-card__name {
  font-size: 0.8rem;
  font-weight: 600;
  color: var(--color-text);
  line-height: 1.2;
}

.int-card__badge {
  font-size: 0.65rem;
  font-weight: 700;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--color-warning);
  background: color-mix(in srgb, var(--color-warning) 12%, transparent);
  border-radius: var(--radius-full);
  padding: 1px 6px;
}
</style>
