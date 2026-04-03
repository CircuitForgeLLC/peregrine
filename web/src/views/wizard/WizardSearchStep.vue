<template>
  <div class="step">
    <h2 class="step__heading">Step 6 — Search Preferences</h2>
    <p class="step__caption">
      Tell Peregrine what roles and markets to watch. You can add more profiles
      in Settings → Search later.
    </p>

    <!-- Job titles -->
    <div class="step__field">
      <label class="step__label">
        Job titles <span class="required">*</span>
      </label>
      <div class="chip-field">
        <div class="chip-list" v-if="form.titles.length">
          <span v-for="(t, i) in form.titles" :key="i" class="chip">
            {{ t }}
            <button class="chip__remove" @click="removeTitle(i)" aria-label="Remove title">×</button>
          </span>
        </div>
        <input
          v-model="titleInput"
          type="text"
          class="step__input chip-input"
          placeholder="e.g. Software Engineer — press Enter to add"
          @keydown.enter.prevent="addTitle"
          @keydown.","="onTitleComma"
        />
      </div>
      <p class="field-hint">Press Enter or comma after each title.</p>
    </div>

    <!-- Locations -->
    <div class="step__field">
      <label class="step__label">
        Locations <span class="step__label--optional">(optional)</span>
      </label>
      <div class="chip-field">
        <div class="chip-list" v-if="form.locations.length">
          <span v-for="(l, i) in form.locations" :key="i" class="chip">
            {{ l }}
            <button class="chip__remove" @click="removeLocation(i)" aria-label="Remove location">×</button>
          </span>
        </div>
        <input
          v-model="locationInput"
          type="text"
          class="step__input chip-input"
          placeholder="e.g. San Francisco, CA — press Enter to add"
          @keydown.enter.prevent="addLocation"
          @keydown.","="onLocationComma"
        />
      </div>
      <p class="field-hint">Leave blank to search everywhere, or add specific cities/metros.</p>
    </div>

    <!-- Remote preference -->
    <div class="step__field step__field--inline">
      <label class="step__label step__label--inline" for="srch-remote">
        Remote jobs only
      </label>
      <input
        id="srch-remote"
        v-model="form.remoteOnly"
        type="checkbox"
        class="step__checkbox"
      />
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

const form = reactive({
  titles: [...wizard.search.titles],
  locations: [...wizard.search.locations],
  remoteOnly: false,
})

const titleInput = ref('')
const locationInput = ref('')

function addTitle() {
  const v = titleInput.value.trim().replace(/,$/, '')
  if (v && !form.titles.includes(v)) form.titles.push(v)
  titleInput.value = ''
}

function onTitleComma(e: KeyboardEvent) {
  e.preventDefault()
  addTitle()
}

function removeTitle(i: number) {
  form.titles.splice(i, 1)
}

function addLocation() {
  const v = locationInput.value.trim().replace(/,$/, '')
  if (v && !form.locations.includes(v)) form.locations.push(v)
  locationInput.value = ''
}

function onLocationComma(e: KeyboardEvent) {
  e.preventDefault()
  addLocation()
}

function removeLocation(i: number) {
  form.locations.splice(i, 1)
}

function back() { router.push('/setup/inference') }

async function next() {
  // Flush any partial inputs before validating
  addTitle()
  addLocation()

  validationError.value = ''
  if (form.titles.length === 0) {
    validationError.value = 'Add at least one job title.'
    return
  }

  wizard.search.titles = [...form.titles]
  wizard.search.locations = [...form.locations]

  const ok = await wizard.saveStep(6, {
    search: {
      titles: form.titles,
      locations: form.locations,
      remote_only: form.remoteOnly,
    },
  })
  if (ok) router.push('/setup/integrations')
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

.step__field--inline {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  flex-direction: row;
}

.step__label--inline {
  margin-bottom: 0;
}

.step__checkbox {
  width: 18px;
  height: 18px;
  accent-color: var(--color-primary);
  cursor: pointer;
}

/* Chip input */
.chip-field {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.chip-list {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
}

.chip {
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
  padding: var(--space-1) var(--space-3);
  background: color-mix(in srgb, var(--color-primary) 12%, transparent);
  color: var(--color-primary);
  border-radius: var(--radius-full);
  font-size: 0.85rem;
  font-weight: 500;
  border: 1px solid color-mix(in srgb, var(--color-primary) 25%, transparent);
}

.chip__remove {
  background: none;
  border: none;
  cursor: pointer;
  color: inherit;
  font-size: 1rem;
  line-height: 1;
  padding: 0 2px;
  opacity: 0.7;
  transition: opacity var(--transition);
}

.chip__remove:hover {
  opacity: 1;
}

.chip-input {
  margin-top: var(--space-1);
}
</style>
