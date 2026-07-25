<template>
  <div class="step">
    <h2 class="step__heading">Step 3 — Your Resume</h2>
    <p class="step__caption">
      Upload a resume to auto-populate your profile, build it manually, or let an AI guide you.
    </p>

    <!-- Tabs -->
    <div class="resume-tabs" role="tablist">
      <button
        role="tab"
        :aria-selected="tab === 'upload'"
        class="resume-tab"
        :class="{ 'resume-tab--active': tab === 'upload' }"
        @click="tab = 'upload'"
      >
        <span class="resume-tab__icon" aria-hidden="true">📄</span>
        <span class="resume-tab__label">Upload File</span>
      </button>
      <button
        role="tab"
        :aria-selected="tab === 'manual'"
        class="resume-tab"
        :class="{ 'resume-tab--active': tab === 'manual' }"
        @click="tab = 'manual'"
      >
        <span class="resume-tab__icon" aria-hidden="true">✏️</span>
        <span class="resume-tab__label">Build Manually</span>
      </button>
      <button
        role="tab"
        :aria-selected="tab === 'ai'"
        class="resume-tab resume-tab--ai"
        :class="{ 'resume-tab--active': tab === 'ai' }"
        @click="tab = 'ai'"
      >
        <span class="resume-tab__icon" aria-hidden="true">{{ hasAiAccess ? '✨' : '🔒' }}</span>
        <span class="resume-tab__label">AI Assistant</span>
        <span v-if="!hasAiAccess" class="resume-tab__badge">Paid</span>
      </button>
    </div>

    <!-- Upload tab -->
    <div v-if="tab === 'upload'" class="resume-upload">
      <label class="upload-zone" :class="{ 'upload-zone--active': dragging }"
             @dragover.prevent="dragging = true"
             @dragleave="dragging = false"
             @drop.prevent="onDrop">
        <input
          type="file"
          accept=".pdf,.docx,.odt"
          class="upload-input"
          @change="onFileChange"
        />
        <span class="upload-icon" aria-hidden="true">📄</span>
        <span class="upload-label">
          {{ fileName || 'Drop PDF, DOCX, or ODT here, or click to browse' }}
        </span>
      </label>

      <div v-if="parseError" class="step__warning">{{ parseError }}</div>

      <button
        v-if="selectedFile"
        class="btn-secondary"
        :disabled="parsing"
        style="margin-top: var(--space-3)"
        @click="parseResume"
      >
        {{ parsing ? 'Parsing…' : '⚙️ Parse Resume' }}
      </button>

      <div v-if="parsedOk" class="step__success">
        ✅ Resume parsed — {{ wizard.resume.experience.length }} experience
        {{ wizard.resume.experience.length === 1 ? 'entry' : 'entries' }} found.
        Switch to "Build Manually" to review or edit.
      </div>
    </div>

    <!-- Manual build tab -->
    <div v-if="tab === 'manual'" class="resume-manual">
      <div
        v-for="(exp, i) in wizard.resume.experience"
        :key="i"
        class="exp-entry"
      >
        <div class="exp-entry__header">
          <span class="exp-entry__num">{{ i + 1 }}</span>
          <button class="exp-entry__remove btn-ghost" @click="removeExp(i)">✕ Remove</button>
        </div>
        <div class="step__field">
          <label class="step__label">Job title</label>
          <input v-model="exp.title" type="text" class="step__input" placeholder="Software Engineer" />
        </div>
        <div class="step__field">
          <label class="step__label">Company</label>
          <input v-model="exp.company" type="text" class="step__input" placeholder="Acme Corp" />
        </div>
        <div class="exp-dates">
          <div class="step__field">
            <label class="step__label">Start</label>
            <input v-model="exp.start_date" type="text" class="step__input" placeholder="2020" />
          </div>
          <div class="step__field">
            <label class="step__label">End</label>
            <input v-model="exp.end_date" type="text" class="step__input" placeholder="present" />
          </div>
        </div>
        <div class="step__field">
          <label class="step__label">Key accomplishments (one per line)</label>
          <textarea
            class="step__textarea"
            rows="4"
            :value="exp.bullets.join('\n')"
            @input="(e) => exp.bullets = (e.target as HTMLTextAreaElement).value.split('\n')"
            placeholder="Reduced load time by 40%&#10;Led a team of 5 engineers"
          />
        </div>
      </div>

      <button class="btn-secondary" style="width: 100%" @click="addExp">
        + Add Experience Entry
      </button>
    </div>

    <!-- AI assistant tab -->
    <div v-if="tab === 'ai'" class="resume-ai">
      <div v-if="!hasAiAccess" class="ai-gate">
        <p class="ai-gate__icon" aria-hidden="true">🔒</p>
        <p class="ai-gate__heading">AI Assistant requires a Paid plan</p>
        <p class="ai-gate__body">
          Upgrade to Paid, or bring your own LLM key in
          <strong>Settings → LLM Backends</strong> to unlock the AI profile assistant for free.
        </p>
        <p class="ai-gate__body">
          In the meantime, use <button class="ai-gate__link" @click="tab = 'upload'">Upload File</button>
          or <button class="ai-gate__link" @click="tab = 'manual'">Build Manually</button>.
        </p>
      </div>
      <div v-else class="ai-embed">
        <p class="ai-embed__intro">
          The AI assistant will ask you a few questions to build your profile.
          Your answers are saved locally — nothing is sent anywhere without your approval.
        </p>
        <a href="/wizard/ai-profile" class="btn-primary ai-embed__cta">
          Open AI Assistant →
        </a>
        <p class="ai-embed__note">
          Opens in a focused view. Come back here to continue the wizard once you're done.
        </p>
      </div>
    </div>

    <div v-if="validationError" class="step__warning" style="margin-top: var(--space-4)">
      {{ validationError }}
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
import { ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import { useWizardStore } from '../../stores/wizard'
import type { WorkExperience } from '../../stores/wizard'
import { useApiFetch } from '../../composables/useApi'
import { useAppConfigStore } from '../../stores/appConfig'
import './wizard.css'

const wizard = useWizardStore()
const router = useRouter()
const config = useAppConfigStore()

const hasAiAccess = computed(() => config.tier !== 'free' || config.byokUnlocked)

const tab = ref<'upload' | 'manual' | 'ai'>(
  wizard.resume.experience.length > 0 ? 'manual' : 'upload',
)
const dragging = ref(false)
const selectedFile = ref<File | null>(null)
const fileName = ref('')
const parsing = ref(false)
const parsedOk = ref(false)
const parseError = ref('')
const validationError = ref('')

function onFileChange(e: Event) {
  const file = (e.target as HTMLInputElement).files?.[0]
  if (file) { selectedFile.value = file; fileName.value = file.name }
}

function onDrop(e: DragEvent) {
  dragging.value = false
  const file = e.dataTransfer?.files[0]
  if (file) { selectedFile.value = file; fileName.value = file.name }
}

async function parseResume() {
  if (!selectedFile.value) return
  parsing.value = true
  parseError.value = ''
  parsedOk.value = false

  const form = new FormData()
  form.append('file', selectedFile.value)

  try {
    const res = await fetch('/api/settings/resume/upload', { method: 'POST', body: form })
    if (!res.ok) {
      parseError.value = `Parse failed (HTTP ${res.status}) — switch to Build Manually to enter your resume.`
      tab.value = 'manual'
      return
    }
    const resp = await res.json()
    // API returns { ok, data: { experience, name, email, … } }
    const data = resp.data ?? {}
    // Map parsed sections to experience entries
    if (data.experience?.length) {
      wizard.resume.experience = data.experience as WorkExperience[]
    }
    wizard.resume.parsedData = data
    // Pre-fill identity from parsed data
    if (data.name && !wizard.identity.name) wizard.identity.name = data.name
    if (data.email && !wizard.identity.email) wizard.identity.email = data.email
    if (data.phone && !wizard.identity.phone) wizard.identity.phone = data.phone
    if (data.career_summary && !wizard.identity.careerSummary)
      wizard.identity.careerSummary = data.career_summary

    parsedOk.value = true
    tab.value = 'manual'
  } catch {
    parseError.value = 'Network error — switch to Build Manually to enter your resume.'
    tab.value = 'manual'
  } finally {
    parsing.value = false
  }
}

function addExp() {
  wizard.resume.experience.push({
    title: '', company: '', start_date: '', end_date: 'present', bullets: [],
  })
}

function removeExp(i: number) {
  wizard.resume.experience.splice(i, 1)
}

function back() { router.push('/setup/tier') }

async function next() {
  validationError.value = ''
  const valid = wizard.resume.experience.some(e => e.title.trim() && e.company.trim())
  if (!valid) {
    validationError.value = 'Add at least one experience entry with a title and company.'
    return
  }
  const ok = await wizard.saveStep(3, { resume: {
    experience: wizard.resume.experience,
    ...(wizard.resume.parsedData ?? {}),
  }})
  if (ok) router.push('/setup/training')
}
</script>

<style scoped>
.resume-tabs {
  display: flex;
  gap: var(--space-2);
  border-bottom: 2px solid var(--color-border);
  margin-bottom: var(--space-6);
}

.resume-tab {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-5);
  background: var(--color-surface-alt);
  border: 1.5px solid var(--color-border);
  border-bottom: 2px solid transparent;
  border-radius: var(--radius-md) var(--radius-md) 0 0;
  margin-bottom: -2px;
  cursor: pointer;
  font-family: var(--font-body);
  font-size: 0.875rem;
  color: var(--color-text-muted);
  transition: color var(--transition), background var(--transition), border-color var(--transition);
}

.resume-tab:hover:not(.resume-tab--active) {
  background: var(--color-surface-raised);
  color: var(--color-text);
  border-color: var(--color-border);
}

.resume-tab--active {
  background: var(--color-surface);
  color: var(--color-primary);
  border-color: var(--color-border);
  border-bottom-color: var(--color-surface);
  font-weight: 600;
}

.resume-tab--ai.resume-tab--active {
  color: var(--color-accent);
  border-bottom-color: var(--color-surface);
}

.resume-tab__icon {
  font-size: 1rem;
  line-height: 1;
}

.resume-tab__label {
  /* explicit — keeps tab text from being an accessibility mystery */
}

.resume-tab__badge {
  font-size: 0.7rem;
  font-weight: 700;
  padding: 1px var(--space-2);
  background: color-mix(in srgb, var(--color-accent) 15%, transparent);
  color: var(--color-accent);
  border: 1px solid color-mix(in srgb, var(--color-accent) 30%, transparent);
  border-radius: var(--radius-full);
  margin-left: var(--space-1);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.upload-zone {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--space-3);
  padding: var(--space-8);
  border: 2px dashed var(--color-border);
  border-radius: var(--radius-md);
  cursor: pointer;
  text-align: center;
  transition: border-color var(--transition), background var(--transition);
}

.upload-zone--active,
.upload-zone:hover {
  border-color: var(--color-primary);
  background: var(--color-primary-light);
}

.upload-input {
  display: none;
}

.upload-icon { font-size: 2rem; }

.upload-label {
  font-size: 0.875rem;
  color: var(--color-text-muted);
}

.exp-entry {
  border: 1px solid var(--color-border-light);
  border-radius: var(--radius-md);
  padding: var(--space-4);
  margin-bottom: var(--space-4);
  background: var(--color-surface-alt);
}

.exp-entry__header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--space-3);
}

.exp-entry__num {
  font-weight: 700;
  font-size: 0.875rem;
  color: var(--color-text-muted);
}

.exp-entry__remove {
  font-size: 0.8rem;
  padding: var(--space-1) var(--space-2);
  min-height: 32px;
}

.exp-dates {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--space-4);
}

/* ── AI tab panels ──────────────────────────────────── */
.resume-ai {
  min-height: 200px;
  display: flex;
  flex-direction: column;
  justify-content: center;
}

.ai-gate {
  text-align: center;
  padding: var(--space-8) var(--space-4);
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-3);
  background: var(--color-surface-alt);
  border: 1px dashed var(--color-border);
  border-radius: var(--radius-lg);
}

.ai-gate__icon {
  font-size: 2rem;
  margin: 0;
}

.ai-gate__heading {
  font-size: 1rem;
  font-weight: 600;
  color: var(--color-text);
  margin: 0;
}

.ai-gate__body {
  font-size: 0.875rem;
  color: var(--color-text-muted);
  line-height: 1.55;
  margin: 0;
  max-width: 380px;
}

.ai-gate__link {
  background: none;
  border: none;
  padding: 0;
  font-family: var(--font-body);
  font-size: inherit;
  color: var(--color-primary);
  cursor: pointer;
  text-decoration: underline;
  text-underline-offset: 2px;
}

.ai-embed {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: var(--space-4);
  padding: var(--space-6);
  background: color-mix(in srgb, var(--color-accent) 6%, var(--color-surface));
  border: 1px solid color-mix(in srgb, var(--color-accent) 25%, transparent);
  border-radius: var(--radius-lg);
}

.ai-embed__intro {
  font-size: 0.9rem;
  color: var(--color-text);
  line-height: 1.6;
  margin: 0;
}

.ai-embed__cta {
  text-decoration: none;
  display: inline-flex;
  align-items: center;
}

.ai-embed__note {
  font-size: 0.8rem;
  color: var(--color-text-muted);
  margin: 0;
}
</style>
