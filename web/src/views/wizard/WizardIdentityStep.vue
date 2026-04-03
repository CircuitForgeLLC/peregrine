<template>
  <div class="step">
    <h2 class="step__heading">Step 4 — Your Identity</h2>
    <p class="step__caption">
      Used in cover letters, research briefs, and interview prep. You can update
      this any time in Settings → My Profile.
    </p>

    <div class="step__field">
      <label class="step__label" for="id-name">Full name <span class="required">*</span></label>
      <input id="id-name" v-model="form.name" type="text" class="step__input"
             placeholder="Your Name" autocomplete="name" />
    </div>

    <div class="step__field">
      <label class="step__label" for="id-email">Email <span class="required">*</span></label>
      <input id="id-email" v-model="form.email" type="email" class="step__input"
             placeholder="you@example.com" autocomplete="email" />
    </div>

    <div class="step__field">
      <label class="step__label step__label--optional" for="id-phone">Phone</label>
      <input id="id-phone" v-model="form.phone" type="tel" class="step__input"
             placeholder="555-000-0000" autocomplete="tel" />
    </div>

    <div class="step__field">
      <label class="step__label step__label--optional" for="id-linkedin">LinkedIn URL</label>
      <input id="id-linkedin" v-model="form.linkedin" type="url" class="step__input"
             placeholder="linkedin.com/in/yourprofile" autocomplete="url" />
    </div>

    <div class="step__field">
      <label class="step__label" for="id-summary">
        Career summary <span class="required">*</span>
      </label>
      <textarea
        id="id-summary"
        v-model="form.careerSummary"
        class="step__textarea"
        rows="5"
        placeholder="2–3 sentences summarising your experience, domain, and what you're looking for next."
      />
      <p class="field-hint">This appears in your cover letters and research briefs.</p>
    </div>

    <div v-if="validationError" class="step__warning">{{ validationError }}</div>

    <div class="step__nav">
      <button class="btn-ghost" @click="back">← Back</button>
      <button class="btn-primary" :disabled="wizard.saving" @click="next">
        {{ wizard.saving ? 'Saving…' : 'Next →' }}
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useWizardStore } from '../../stores/wizard'
import './wizard.css'

const wizard = useWizardStore()
const router = useRouter()
const validationError = ref('')

// Local reactive copy — sync back to store on Next
const form = reactive({
  name: wizard.identity.name,
  email: wizard.identity.email,
  phone: wizard.identity.phone,
  linkedin: wizard.identity.linkedin,
  careerSummary: wizard.identity.careerSummary,
})

function back() { router.push('/setup/resume') }

async function next() {
  validationError.value = ''
  if (!form.name.trim()) {
    validationError.value = 'Full name is required.'
    return
  }
  if (!form.email.trim() || !form.email.includes('@')) {
    validationError.value = 'A valid email address is required.'
    return
  }
  if (!form.careerSummary.trim()) {
    validationError.value = 'Please add a short career summary.'
    return
  }

  wizard.identity = { ...form }
  const ok = await wizard.saveStep(4, {
    name: form.name,
    email: form.email,
    phone: form.phone,
    linkedin: form.linkedin,
    career_summary: form.careerSummary,
  })
  if (ok) router.push('/setup/inference')
}
</script>

<style scoped>
.required {
  color: var(--color-error);
  margin-left: 2px;
}

.field-hint {
  font-size: 0.8rem;
  color: var(--color-text-muted);
  margin-top: var(--space-1);
}
</style>
