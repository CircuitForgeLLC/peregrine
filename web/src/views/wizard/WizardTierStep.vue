<template>
  <div class="step">
    <h2 class="step__heading">Step 2 — Choose Your Plan</h2>
    <p class="step__caption">
      You can upgrade or change this later in Settings → License.
    </p>

    <div class="step__radio-group">
      <label
        v-for="option in tiers"
        :key="option.value"
        class="step__radio-card"
        :class="{ 'step__radio-card--selected': selected === option.value }"
      >
        <input type="radio" :value="option.value" v-model="selected" />
        <div class="step__radio-card__body">
          <span class="step__radio-card__title">{{ option.label }}</span>
          <span class="step__radio-card__desc">{{ option.desc }}</span>
        </div>
      </label>
    </div>

    <div class="step__nav">
      <button class="btn-ghost" @click="back">← Back</button>
      <button class="btn-primary" :disabled="wizard.saving" @click="next">
        {{ wizard.saving ? 'Saving…' : 'Next →' }}
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useWizardStore } from '../../stores/wizard'
import type { WizardTier } from '../../stores/wizard'
import './wizard.css'

const wizard = useWizardStore()
const router = useRouter()
const selected = ref<WizardTier>(wizard.tier)

const tiers = [
  {
    value: 'free' as WizardTier,
    label: '🆓 Free',
    desc: 'Core pipeline, job discovery, and resume matching. Bring your own LLM to unlock AI generation.',
  },
  {
    value: 'paid' as WizardTier,
    label: '⭐ Paid',
    desc: 'Everything in Free, plus cloud AI generation, integrations (Notion, Calendar, Slack), and email sync.',
  },
  {
    value: 'premium' as WizardTier,
    label: '🏆 Premium',
    desc: 'Everything in Paid, plus fine-tuned cover letter model, multi-user support, and advanced analytics.',
  },
]

function back() { router.push('/setup/hardware') }

async function next() {
  wizard.tier = selected.value
  const ok = await wizard.saveStep(2, { tier: selected.value })
  if (ok) router.push('/setup/resume')
}
</script>
