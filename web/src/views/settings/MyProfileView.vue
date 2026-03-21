<template>
  <div class="my-profile">
    <header class="page-header">
      <h2>My Profile</h2>
      <p class="subtitle">Your identity and preferences used for cover letters, research, and interview prep.</p>
    </header>

    <div v-if="store.loading" class="loading-state">Loading profile…</div>

    <template v-else>
      <div v-if="loadError" class="load-error-banner" role="alert">
        <strong>Error loading profile:</strong> {{ loadError }}
      </div>
      <!-- ── Identity ─────────────────────────────────────── -->
      <section class="form-section">
        <h3 class="section-title">Identity</h3>

        <div class="field-row">
          <label class="field-label" for="profile-name">Full name</label>
          <input id="profile-name" v-model="store.name" type="text" class="text-input" placeholder="Your Name" />
        </div>

        <div class="field-row">
          <label class="field-label" for="profile-email">Email</label>
          <input id="profile-email" v-model="store.email" type="email" class="text-input" placeholder="you@example.com" />
        </div>

        <div class="field-row">
          <label class="field-label" for="profile-phone">Phone</label>
          <input id="profile-phone" v-model="store.phone" type="tel" class="text-input" placeholder="555-000-0000" />
        </div>

        <div class="field-row">
          <label class="field-label" for="profile-linkedin">LinkedIn URL</label>
          <input id="profile-linkedin" v-model="store.linkedin_url" type="url" class="text-input" placeholder="linkedin.com/in/yourprofile" />
        </div>

        <div class="field-row field-row--stacked">
          <label class="field-label" for="profile-summary">Career summary</label>
          <textarea
            id="profile-summary"
            v-model="store.career_summary"
            class="text-area"
            rows="5"
            placeholder="2–3 sentences summarising your experience and focus."
          />
          <button
            v-if="config.tier !== 'free'"
            class="btn-generate"
            type="button"
            @click="generateSummary"
            :disabled="generatingSummary"
          >{{ generatingSummary ? 'Generating…' : 'Generate ✦' }}</button>
        </div>

        <div class="field-row field-row--stacked">
          <label class="field-label" for="profile-voice">Candidate voice</label>
          <textarea
            id="profile-voice"
            v-model="store.candidate_voice"
            class="text-area"
            rows="3"
            placeholder="How you write and communicate — used to shape cover letter voice."
          />
        </div>

        <div class="field-row">
          <label class="field-label" for="profile-inference">Inference profile</label>
          <select id="profile-inference" v-model="store.inference_profile" class="select-input">
            <option value="remote">Remote</option>
            <option value="cpu">CPU</option>
            <option value="single-gpu">Single GPU</option>
            <option value="dual-gpu">Dual GPU</option>
          </select>
        </div>

        <div class="save-row">
          <button class="btn-save" type="button" @click="store.save()" :disabled="store.saving">
            {{ store.saving ? 'Saving…' : 'Save Identity' }}
          </button>
          <p v-if="store.saveError" class="error-msg">{{ store.saveError }}</p>
        </div>
      </section>

      <!-- ── Mission & Values ────────────────────────────── -->
      <section class="form-section">
        <h3 class="section-title">Mission &amp; Values</h3>
        <p class="section-desc">
          Industries you care about. When a job matches, the cover letter includes your personal alignment note.
        </p>

        <div
          v-for="(pref, idx) in store.mission_preferences"
          :key="pref.id"
          class="mission-row"
        >
          <input
            v-model="pref.industry"
            type="text"
            class="text-input mission-industry"
            placeholder="Industry (e.g. music)"
          />
          <input
            v-model="pref.note"
            type="text"
            class="text-input mission-note"
            placeholder="Your personal note (optional)"
          />
          <button class="btn-remove" type="button" @click="removeMission(idx)" aria-label="Remove">×</button>
        </div>

        <div class="mission-actions">
          <button class="btn-secondary" type="button" @click="addMission">+ Add mission</button>
          <button
            v-if="config.tier !== 'free'"
            class="btn-generate"
            type="button"
            @click="generateMissions"
            :disabled="generatingMissions"
          >{{ generatingMissions ? 'Generating…' : 'Generate ✦' }}</button>
        </div>

        <div class="save-row">
          <button class="btn-save" type="button" @click="store.save()" :disabled="store.saving">
            {{ store.saving ? 'Saving…' : 'Save Mission' }}
          </button>
          <p v-if="store.saveError" class="error-msg">{{ store.saveError }}</p>
        </div>
      </section>

      <!-- ── NDA Companies ───────────────────────────────── -->
      <section class="form-section">
        <h3 class="section-title">NDA Companies</h3>
        <p class="section-desc">
          Companies you can't name. They appear as "previous employer (NDA)" in research briefs when match score is low.
        </p>

        <div class="tag-list">
          <span
            v-for="(company, idx) in store.nda_companies"
            :key="company"
            class="tag"
          >
            {{ company }}
            <button class="tag-remove" type="button" @click="removeNda(idx)" :aria-label="`Remove ${company}`">×</button>
          </span>
        </div>

        <div class="nda-add-row">
          <input
            v-model="newNdaCompany"
            type="text"
            class="text-input nda-input"
            placeholder="Company name"
            @keydown.enter.prevent="addNda"
          />
          <button class="btn-secondary" type="button" @click="addNda" :disabled="!newNdaCompany.trim()">Add</button>
        </div>
      </section>

      <!-- ── Research Brief Preferences ────────────────── -->
      <section class="form-section">
        <h3 class="section-title">Research Brief Preferences</h3>
        <p class="section-desc">
          Optional sections added to company briefs — for your personal decision-making only.
          These details are never included in applications.
        </p>

        <div class="checkbox-row">
          <input
            id="pref-accessibility"
            v-model="store.accessibility_focus"
            type="checkbox"
            class="checkbox"
            @change="autosave"
          />
          <label for="pref-accessibility" class="checkbox-label">
            Include accessibility &amp; inclusion research in company briefs
          </label>
        </div>

        <div class="checkbox-row">
          <input
            id="pref-lgbtq"
            v-model="store.lgbtq_focus"
            type="checkbox"
            class="checkbox"
            @change="autosave"
          />
          <label for="pref-lgbtq" class="checkbox-label">
            Include LGBTQ+ inclusion research in company briefs
          </label>
        </div>
      </section>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { storeToRefs } from 'pinia'
import { useProfileStore } from '../../stores/settings/profile'
import { useAppConfigStore } from '../../stores/appConfig'
import { useApiFetch } from '../../composables/useApi'

const store = useProfileStore()
const { loadError } = storeToRefs(store)
const config = useAppConfigStore()

const newNdaCompany = ref('')
const generatingSummary = ref(false)
const generatingMissions = ref(false)

onMounted(() => { store.load() })

// ── Mission helpers ──────────────────────────────────────
function addMission() {
  store.mission_preferences = [...store.mission_preferences, { id: crypto.randomUUID(), industry: '', note: '' }]
}

function removeMission(idx: number) {
  store.mission_preferences = store.mission_preferences.filter((_, i) => i !== idx)
}

// ── NDA helpers (autosave on add/remove) ────────────────
function addNda() {
  const trimmed = newNdaCompany.value.trim()
  if (!trimmed || store.nda_companies.includes(trimmed)) return
  store.nda_companies = [...store.nda_companies, trimmed]
  newNdaCompany.value = ''
  store.save()
}

function removeNda(idx: number) {
  store.nda_companies = store.nda_companies.filter((_, i) => i !== idx)
  store.save()
}

// ── Research prefs autosave (debounced 400ms) ────────────
let debounceTimer: ReturnType<typeof setTimeout> | null = null
function autosave() {
  if (debounceTimer) clearTimeout(debounceTimer)
  debounceTimer = setTimeout(() => store.save(), 400)
}

// ── AI generation (paid tier) ────────────────────────────
async function generateSummary() {
  generatingSummary.value = true
  const { data, error } = await useApiFetch<{ summary?: string }>(
    '/api/settings/profile/generate-summary', { method: 'POST' }
  )
  generatingSummary.value = false
  if (!error && data?.summary) store.career_summary = data.summary
}

async function generateMissions() {
  generatingMissions.value = true
  const { data, error } = await useApiFetch<{ mission_preferences?: Array<{ industry: string; note: string }> }>(
    '/api/settings/profile/generate-missions', { method: 'POST' }
  )
  generatingMissions.value = false
  if (!error && data?.mission_preferences) {
    store.mission_preferences = data.mission_preferences.map((m) => ({
      id: crypto.randomUUID(), industry: m.industry ?? '', note: m.note ?? '',
    }))
  }
}
</script>

<style scoped>
.my-profile {
  max-width: 680px;
}

.page-header {
  margin-bottom: var(--space-6);
}

.page-header h2 {
  margin: 0 0 var(--space-1);
  font-size: 1.25rem;
  font-weight: 600;
}

.subtitle {
  margin: 0;
  color: var(--color-text-muted);
  font-size: 0.875rem;
}

.loading-state {
  color: var(--color-text-muted);
  font-size: 0.875rem;
  padding: var(--space-4) 0;
}

.load-error-banner {
  padding: var(--space-3) var(--space-4);
  margin-bottom: var(--space-4);
  background: color-mix(in srgb, var(--color-danger, #c0392b) 10%, transparent);
  border: 1px solid color-mix(in srgb, var(--color-danger, #c0392b) 40%, transparent);
  border-radius: 6px;
  color: var(--color-danger, #c0392b);
  font-size: 0.875rem;
}

/* ── Sections ──────────────────────────────────────────── */
.form-section {
  border: 1px solid var(--color-border);
  border-radius: 8px;
  padding: var(--space-5);
  margin-bottom: var(--space-5);
}

.section-title {
  margin: 0 0 var(--space-3);
  font-size: 0.9rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--color-text-muted);
}

.section-desc {
  margin: calc(-1 * var(--space-2)) 0 var(--space-4);
  font-size: 0.8rem;
  color: var(--color-text-muted);
  line-height: 1.5;
}

/* ── Fields ───────────────────────────────────────────── */
.field-row {
  display: grid;
  grid-template-columns: 160px 1fr;
  align-items: center;
  gap: var(--space-3);
  margin-bottom: var(--space-3);
}

.field-row--stacked {
  grid-template-columns: 1fr;
  align-items: flex-start;
}

.field-row--stacked .field-label {
  margin-bottom: var(--space-1);
}

.field-label {
  font-size: 0.825rem;
  color: var(--color-text-muted);
  font-weight: 500;
}

.text-input,
.select-input {
  width: 100%;
  padding: var(--space-2) var(--space-3);
  border: 1px solid var(--color-border);
  border-radius: 6px;
  background: var(--color-surface-raised, var(--color-surface));
  color: var(--color-text);
  font-size: 0.875rem;
  box-sizing: border-box;
}

.text-input:focus,
.select-input:focus,
.text-area:focus {
  outline: 2px solid var(--color-primary);
  outline-offset: -1px;
  border-color: transparent;
}

.text-area {
  width: 100%;
  padding: var(--space-2) var(--space-3);
  border: 1px solid var(--color-border);
  border-radius: 6px;
  background: var(--color-surface-raised, var(--color-surface));
  color: var(--color-text);
  font-size: 0.875rem;
  resize: vertical;
  font-family: inherit;
  box-sizing: border-box;
}

/* ── Save row ─────────────────────────────────────────── */
.save-row {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  margin-top: var(--space-4);
  padding-top: var(--space-4);
  border-top: 1px solid var(--color-border);
}

.btn-save {
  padding: var(--space-2) var(--space-5);
  background: var(--color-primary);
  color: var(--color-on-primary, #fff);
  border: none;
  border-radius: 6px;
  font-size: 0.875rem;
  font-weight: 500;
  cursor: pointer;
}

.btn-save:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.error-msg {
  margin: 0;
  color: var(--color-danger, #c0392b);
  font-size: 0.825rem;
}

.btn-generate {
  padding: var(--space-2) var(--space-3);
  background: transparent;
  border: 1px solid var(--color-primary);
  color: var(--color-primary);
  border-radius: 6px;
  font-size: 0.8rem;
  cursor: pointer;
  margin-top: var(--space-2);
  align-self: flex-start;
}

.btn-generate:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.btn-secondary {
  padding: var(--space-2) var(--space-3);
  background: transparent;
  border: 1px solid var(--color-border);
  color: var(--color-text-secondary);
  border-radius: 6px;
  font-size: 0.8rem;
  cursor: pointer;
}

.btn-secondary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* ── Mission rows ─────────────────────────────────────── */
.mission-row {
  display: grid;
  grid-template-columns: 1fr 2fr auto;
  gap: var(--space-2);
  margin-bottom: var(--space-2);
  align-items: center;
}

.mission-actions {
  display: flex;
  gap: var(--space-2);
  margin-top: var(--space-2);
}

.btn-remove {
  background: transparent;
  border: 1px solid var(--color-border);
  color: var(--color-text-muted);
  border-radius: 4px;
  width: 28px;
  height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  font-size: 1rem;
  line-height: 1;
}

.btn-remove:hover {
  border-color: var(--color-danger, #c0392b);
  color: var(--color-danger, #c0392b);
}

/* ── NDA tags ─────────────────────────────────────────── */
.tag-list {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
  margin-bottom: var(--space-3);
  min-height: 32px;
}

.tag {
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
  padding: var(--space-1) var(--space-2);
  background: color-mix(in srgb, var(--color-primary) 12%, transparent);
  border: 1px solid color-mix(in srgb, var(--color-primary) 30%, transparent);
  border-radius: 999px;
  font-size: 0.8rem;
  color: var(--color-text);
}

.tag-remove {
  background: transparent;
  border: none;
  color: var(--color-text-muted);
  cursor: pointer;
  font-size: 1rem;
  line-height: 1;
  padding: 0;
  display: flex;
  align-items: center;
}

.tag-remove:hover {
  color: var(--color-danger, #c0392b);
}

.nda-add-row {
  display: flex;
  gap: var(--space-2);
}

.nda-input {
  flex: 1;
}

/* ── Checkboxes ───────────────────────────────────────── */
.checkbox-row {
  display: flex;
  align-items: flex-start;
  gap: var(--space-3);
  margin-bottom: var(--space-3);
}

.checkbox {
  flex-shrink: 0;
  margin-top: 2px;
  width: 16px;
  height: 16px;
  accent-color: var(--color-primary);
  cursor: pointer;
}

.checkbox-label {
  font-size: 0.875rem;
  line-height: 1.5;
  cursor: pointer;
}

/* ── Mobile ───────────────────────────────────────────── */
@media (max-width: 767px) {
  .field-row {
    grid-template-columns: 1fr;
  }

  .mission-row {
    grid-template-columns: 1fr auto;
    grid-template-rows: auto auto;
  }

  .mission-note {
    grid-column: 1;
  }

  .btn-remove {
    grid-row: 1;
    grid-column: 2;
    align-self: start;
  }
}
</style>
