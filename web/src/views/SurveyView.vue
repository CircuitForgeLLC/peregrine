<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useInterviewsStore } from '../stores/interviews'
import { useSurveyStore } from '../stores/survey'

const route = useRoute()
const router = useRouter()
const interviewsStore = useInterviewsStore()
const surveyStore = useSurveyStore()

const VALID_STAGES = ['survey', 'phone_screen', 'interviewing', 'offer']

const rawId = route.params.id
const jobId = rawId ? parseInt(String(rawId), 10) : NaN
const pickerMode = !rawId || isNaN(jobId)

// UI state
let saveSuccessTimer: ReturnType<typeof setTimeout> | null = null
const activeTab = ref<'text' | 'screenshot'>('text')
const textInput = ref('')
const imageB64 = ref<string | null>(null)
const imagePreviewUrl = ref<string | null>(null)
const selectedMode = ref<'quick' | 'detailed'>('quick')
const surveyName = ref('')
const reportedScore = ref('')
const saveSuccess = ref(false)

// Computed job from store
const job = computed(() =>
  interviewsStore.jobs.find(j => j.id === jobId) ?? null
)

// Jobs eligible for survey (used in picker mode)
const pickerJobs = computed(() =>
  interviewsStore.jobs.filter(j => VALID_STAGES.includes(j.status))
)

const stageLabel: Record<string, string> = {
  survey: 'Survey', phone_screen: 'Phone Screen',
  interviewing: 'Interviewing', offer: 'Offer',
}

onMounted(async () => {
  if (interviewsStore.jobs.length === 0) {
    await interviewsStore.fetchAll()
  }
  if (pickerMode) return
  if (!job.value || !VALID_STAGES.includes(job.value.status)) {
    router.replace('/interviews')
    return
  }
  await surveyStore.fetchFor(jobId)
})

onUnmounted(() => {
  surveyStore.clear()
  if (saveSuccessTimer) clearTimeout(saveSuccessTimer)
})

// Screenshot handling
function handlePaste(e: ClipboardEvent) {
  if (!surveyStore.visionAvailable) return
  const items = e.clipboardData?.items
  if (!items) return
  for (const item of items) {
    if (item.type.startsWith('image/')) {
      const file = item.getAsFile()
      if (file) loadImageFile(file)
      break
    }
  }
}

function handleDrop(e: DragEvent) {
  e.preventDefault()
  if (!surveyStore.visionAvailable) return
  const file = e.dataTransfer?.files[0]
  if (file && file.type.startsWith('image/')) loadImageFile(file)
}

function handleFileUpload(e: Event) {
  const file = (e.target as HTMLInputElement).files?.[0]
  if (file) loadImageFile(file)
}

function loadImageFile(file: File) {
  const reader = new FileReader()
  reader.onload = (ev) => {
    const result = ev.target?.result as string
    imagePreviewUrl.value = result
    imageB64.value = result.split(',')[1]  // strip "data:image/...;base64,"
  }
  reader.readAsDataURL(file)
}

function clearImage() {
  imageB64.value = null
  imagePreviewUrl.value = null
}

// Analysis
const canAnalyze = computed(() =>
  activeTab.value === 'text' ? textInput.value.trim().length > 0 : imageB64.value !== null
)

async function runAnalyze() {
  const payload: { text?: string; image_b64?: string; mode: 'quick' | 'detailed' } = {
    mode: selectedMode.value,
  }
  if (activeTab.value === 'screenshot' && imageB64.value) {
    payload.image_b64 = imageB64.value
  } else {
    payload.text = textInput.value
  }
  await surveyStore.analyze(jobId, payload)
}

// Save
async function saveToJob() {
  await surveyStore.saveResponse(jobId, {
    surveyName: surveyName.value,
    reportedScore: reportedScore.value,
    image_b64: activeTab.value === 'screenshot' ? imageB64.value ?? undefined : undefined,
  })
  if (!surveyStore.error) {
    saveSuccess.value = true
    surveyName.value = ''
    reportedScore.value = ''
    if (saveSuccessTimer) clearTimeout(saveSuccessTimer)
    saveSuccessTimer = setTimeout(() => { saveSuccess.value = false }, 3000)
  }
}

// History accordion
const historyOpen = ref(false)
function formatDate(iso: string | null): string {
  if (!iso) return ''
  return new Date(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}
const expandedHistory = ref<Set<number>>(new Set())
function toggleHistoryEntry(id: number) {
  const next = new Set(expandedHistory.value)
  if (next.has(id)) next.delete(id)
  else next.add(id)
  expandedHistory.value = next
}
</script>

<template>
  <div class="survey-layout">

    <!-- ── Job picker (no id in route) ── -->
    <div v-if="pickerMode" class="survey-content picker-mode">
      <h2 class="picker-heading">Survey Assistant</h2>
      <p class="picker-sub">Select a job to open the survey assistant.</p>
      <div v-if="pickerJobs.length === 0" class="picker-empty">
        No jobs in an active interview stage. Move a job to Survey, Phone Screen, Interviewing, or Offer first.
      </div>
      <ul v-else class="picker-list" role="list">
        <li
          v-for="j in pickerJobs"
          :key="j.id"
          class="picker-item"
          @click="router.push('/survey/' + j.id)"
        >
          <div class="picker-item__main">
            <span class="picker-item__company">{{ j.company }}</span>
            <span class="picker-item__title">{{ j.title }}</span>
          </div>
          <span class="stage-badge">{{ stageLabel[j.status] ?? j.status }}</span>
        </li>
      </ul>
    </div>

    <!-- ── Survey assistant (id present) ── -->
    <template v-else>
    <!-- Sticky context bar -->
    <div class="context-bar" v-if="job">
      <span class="context-company">{{ job.company }}</span>
      <span class="context-sep">·</span>
      <span class="context-title">{{ job.title }}</span>
      <span class="stage-badge">{{ stageLabel[job.status] ?? job.status }}</span>
    </div>

    <!-- Load/history error banner -->
    <div class="error-banner" v-if="surveyStore.error && !surveyStore.analysis">
      {{ surveyStore.error }}
    </div>

    <div class="survey-content">
      <!-- Input card -->
      <div class="card">
        <div class="tab-bar">
          <button
            class="tab-btn"
            :class="{ active: activeTab === 'text' }"
            @click="activeTab = 'text'"
          >📝 Paste Text</button>
          <button
            class="tab-btn"
            :class="{ active: activeTab === 'screenshot', disabled: !surveyStore.visionAvailable }"
            :aria-disabled="!surveyStore.visionAvailable"
            :title="!surveyStore.visionAvailable ? 'Vision service not running — start it with: bash scripts/manage-vision.sh start' : undefined"
            @click="surveyStore.visionAvailable && (activeTab = 'screenshot')"
          >📷 Screenshot</button>
        </div>

        <!-- Text tab -->
        <div v-if="activeTab === 'text'" class="tab-panel">
          <textarea
            v-model="textInput"
            class="survey-textarea"
            placeholder="Paste your survey questions here, e.g.:&#10;Q1: Which best describes your work style?&#10;A. I prefer working alone&#10;B. I thrive in teams&#10;C. Depends on the project"
          />
        </div>

        <!-- Screenshot tab -->
        <div
          v-else
          class="screenshot-zone"
          role="region"
          aria-label="Screenshot upload area — paste, drag, or choose file"
          @paste="handlePaste"
          @dragover.prevent
          @drop="handleDrop"
          tabindex="0"
        >
          <div v-if="imagePreviewUrl" class="image-preview">
            <img :src="imagePreviewUrl" alt="Survey screenshot preview" />
            <button class="remove-btn" @click="clearImage">✕ Remove</button>
          </div>
          <div v-else class="drop-hint">
            <p>Paste (Ctrl+V), drag &amp; drop, or upload a screenshot</p>
            <label class="upload-label">
              Choose file
              <input type="file" accept="image/*" class="file-input" @change="handleFileUpload" />
            </label>
          </div>
        </div>
      </div>

      <!-- Mode selection -->
      <div class="mode-cards">
        <button
          class="mode-card"
          :class="{ selected: selectedMode === 'quick' }"
          @click="selectedMode = 'quick'"
        >
          <span class="mode-icon">⚡</span>
          <span class="mode-name">Quick</span>
          <span class="mode-desc">Best answer + one-liner per question</span>
        </button>
        <button
          class="mode-card"
          :class="{ selected: selectedMode === 'detailed' }"
          @click="selectedMode = 'detailed'"
        >
          <span class="mode-icon">📋</span>
          <span class="mode-name">Detailed</span>
          <span class="mode-desc">Option-by-option breakdown with reasoning</span>
        </button>
      </div>

      <!-- Analyze button -->
      <button
        class="analyze-btn"
        :disabled="!canAnalyze || surveyStore.loading"
        @click="runAnalyze"
      >
        <span v-if="surveyStore.loading" class="spinner" aria-hidden="true"></span>
        {{ surveyStore.loading ? 'Analyzing…' : '🔍 Analyze' }}
      </button>

      <!-- Analyze error -->
      <div class="error-inline" v-if="surveyStore.error && !surveyStore.analysis">
        {{ surveyStore.error }}
      </div>

      <!-- Results card -->
      <div class="card results-card" v-if="surveyStore.analysis">
        <div class="results-output">{{ surveyStore.analysis.output }}</div>
        <div class="save-form">
          <input
            v-model="surveyName"
            class="save-input"
            type="text"
            placeholder="Survey name (e.g. Culture Fit Round 1)"
          />
          <input
            v-model="reportedScore"
            class="save-input"
            type="text"
            placeholder="Reported score (e.g. 82% or 4.2/5)"
          />
          <button
            class="save-btn"
            :disabled="surveyStore.saving"
            @click="saveToJob"
          >
            <span v-if="surveyStore.saving" class="spinner" aria-hidden="true"></span>
            💾 Save to job
          </button>
          <div v-if="saveSuccess" class="save-success">Saved!</div>
          <div v-if="surveyStore.error" class="error-inline">{{ surveyStore.error }}</div>
        </div>
      </div>

      <!-- History accordion -->
      <details class="history-accordion" :open="historyOpen" @toggle="historyOpen = ($event.target as HTMLDetailsElement).open">
        <summary class="history-summary">
          Survey history ({{ surveyStore.history.length }} response{{ surveyStore.history.length === 1 ? '' : 's' }})
        </summary>
        <div v-if="surveyStore.history.length === 0" class="history-empty">No responses saved yet.</div>
        <div v-else class="history-list">
          <div v-for="resp in surveyStore.history" :key="resp.id" class="history-entry">
            <button class="history-toggle" @click="toggleHistoryEntry(resp.id)">
              <span class="history-name">{{ resp.survey_name ?? 'Survey response' }}</span>
              <span class="history-meta">{{ formatDate(resp.received_at) }}{{ resp.reported_score ? ` · ${resp.reported_score}` : '' }}</span>
              <span class="history-chevron">{{ expandedHistory.has(resp.id) ? '▲' : '▼' }}</span>
            </button>
            <div v-if="expandedHistory.has(resp.id)" class="history-detail">
              <div class="history-tags">
                <span class="tag">{{ resp.mode }}</span>
                <span class="tag">{{ resp.source }}</span>
                <span v-if="resp.received_at" class="tag">{{ resp.received_at }}</span>
              </div>
              <div class="history-output">{{ resp.llm_output }}</div>
            </div>
          </div>
        </div>
      </details>
    </div>
    </template><!-- end v-else (id present) -->

  </div>
</template>

<style scoped>
.survey-layout {
  display: flex;
  flex-direction: column;
  min-height: 100vh;
}

.context-bar {
  position: sticky;
  top: 0;
  z-index: 10;
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: 0 var(--space-6);
  height: 40px;
  background: var(--color-surface-raised, #f8f9fa);
  border-bottom: 1px solid var(--color-border, #e2e8f0);
  font-size: 0.875rem;
}

.context-company {
  font-weight: 600;
  color: var(--color-text, #1a202c);
}

.context-sep {
  color: var(--color-text-muted, #718096);
}

.context-title {
  color: var(--color-text-muted, #718096);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.stage-badge {
  margin-left: auto;
  padding: 2px 8px;
  border-radius: 9999px;
  font-size: 0.75rem;
  font-weight: 600;
  background: var(--color-accent-subtle, #ebf4ff);
  color: var(--color-accent, #3182ce);
}

.survey-content {
  max-width: 760px;
  margin: 0 auto;
  padding: var(--space-6);
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.card {
  background: var(--color-surface, #fff);
  border: 1px solid var(--color-border, #e2e8f0);
  border-radius: var(--radius-md, 8px);
  overflow: hidden;
}

.tab-bar {
  display: flex;
  border-bottom: 1px solid var(--color-border, #e2e8f0);
}

.tab-btn {
  flex: 1;
  padding: var(--space-3) var(--space-4);
  background: none;
  border: none;
  cursor: pointer;
  font-size: 0.875rem;
  color: var(--color-text-muted, #718096);
  transition: color 0.15s, background 0.15s;
}

.tab-btn.active {
  color: var(--color-accent, #3182ce);
  background: var(--color-accent-subtle, #ebf4ff);
  font-weight: 600;
}

.tab-btn.disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.tab-panel {
  padding: var(--space-4);
}

.survey-textarea {
  width: 100%;
  min-height: 200px;
  padding: var(--space-3);
  font-family: inherit;
  font-size: 0.875rem;
  border: 1px solid var(--color-border, #e2e8f0);
  border-radius: var(--radius-sm, 4px);
  resize: vertical;
  background: var(--color-bg, #fff);
  color: var(--color-text, #1a202c);
  box-sizing: border-box;
}

.screenshot-zone {
  min-height: 160px;
  padding: var(--space-6);
  display: flex;
  align-items: center;
  justify-content: center;
  border: 2px dashed var(--color-border, #e2e8f0);
  margin: var(--space-4);
  border-radius: var(--radius-md, 8px);
  outline: none;
}

.screenshot-zone:focus {
  border-color: var(--color-accent, #3182ce);
}

.drop-hint {
  text-align: center;
  color: var(--color-text-muted, #718096);
}

.upload-label {
  display: inline-block;
  margin-top: var(--space-2);
  padding: var(--space-2) var(--space-4);
  border: 1px solid var(--color-border, #e2e8f0);
  border-radius: var(--radius-sm, 4px);
  cursor: pointer;
  font-size: 0.875rem;
  background: var(--color-surface, #fff);
}

.file-input {
  display: none;
}

.image-preview {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-2);
  width: 100%;
}

.image-preview img {
  max-width: 100%;
  max-height: 300px;
  border-radius: var(--radius-sm, 4px);
}

.remove-btn {
  font-size: 0.8rem;
  color: var(--color-text-muted, #718096);
  background: none;
  border: 1px solid var(--color-border, #e2e8f0);
  border-radius: var(--radius-sm, 4px);
  padding: 2px 8px;
  cursor: pointer;
}

.mode-cards {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.mode-card {
  display: grid;
  grid-template-columns: 2rem 1fr;
  grid-template-rows: auto auto;
  align-items: center;
  gap: 0 var(--space-2);
  padding: var(--space-4);
  background: var(--color-surface, #fff);
  border: 2px solid var(--color-border, #e2e8f0);
  border-radius: var(--radius-md, 8px);
  cursor: pointer;
  text-align: left;
  transition: border-color 0.15s, background 0.15s;
}

.mode-card.selected {
  border-color: var(--color-accent, #3182ce);
  background: var(--color-accent-subtle, #ebf4ff);
}

.mode-icon {
  grid-row: 1 / 3;
  font-size: 1.25rem;
  line-height: 1;
  align-self: center;
}

.mode-name {
  font-weight: 600;
  color: var(--color-text, #1a202c);
  line-height: 1.3;
}

.mode-desc {
  font-size: 0.8rem;
  color: var(--color-text-muted, #718096);
}

.analyze-btn {
  width: 100%;
  padding: var(--space-3) var(--space-4);
  background: var(--color-accent, #3182ce);
  color: #fff;
  border: none;
  border-radius: var(--radius-md, 8px);
  font-size: 1rem;
  font-weight: 600;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-2);
  transition: opacity 0.15s;
}

.analyze-btn:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.results-card {
  padding: var(--space-4);
}

.results-output {
  white-space: pre-wrap;
  font-size: 0.9rem;
  line-height: 1.6;
  color: var(--color-text, #1a202c);
  margin-bottom: var(--space-4);
}

.save-form {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  padding-top: var(--space-4);
  border-top: 1px solid var(--color-border, #e2e8f0);
}

.save-input {
  padding: var(--space-2) var(--space-3);
  border: 1px solid var(--color-border, #e2e8f0);
  border-radius: var(--radius-sm, 4px);
  font-size: 0.875rem;
  background: var(--color-bg, #fff);
  color: var(--color-text, #1a202c);
  box-sizing: border-box;
}

.save-btn {
  align-self: flex-start;
  padding: var(--space-2) var(--space-4);
  background: var(--color-surface-raised, #f8f9fa);
  border: 1px solid var(--color-border, #e2e8f0);
  border-radius: var(--radius-md, 8px);
  cursor: pointer;
  font-weight: 600;
  display: flex;
  align-items: center;
  gap: var(--space-2);
  transition: background 0.15s;
}

.save-btn:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.save-success {
  color: var(--color-success, #38a169);
  font-size: 0.875rem;
  font-weight: 600;
}

.history-accordion {
  border: 1px solid var(--color-border, #e2e8f0);
  border-radius: var(--radius-md, 8px);
  background: var(--color-surface, #fff);
}

.history-summary {
  padding: var(--space-3) var(--space-4);
  cursor: pointer;
  font-size: 0.875rem;
  color: var(--color-text-muted, #718096);
  font-weight: 500;
  list-style: none;
}

.history-summary::-webkit-details-marker { display: none; }

.history-empty {
  padding: var(--space-4);
  color: var(--color-text-muted, #718096);
  font-size: 0.875rem;
}

.history-list {
  display: flex;
  flex-direction: column;
  gap: 1px;
  background: var(--color-border, #e2e8f0);
}

.history-entry {
  background: var(--color-surface, #fff);
}

.history-toggle {
  width: 100%;
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-3) var(--space-4);
  background: none;
  border: none;
  cursor: pointer;
  text-align: left;
  font-size: 0.875rem;
}

.history-name {
  font-weight: 500;
  color: var(--color-text, #1a202c);
}

.history-meta {
  color: var(--color-text-muted, #718096);
  font-size: 0.8rem;
  margin-left: auto;
}

.history-chevron {
  font-size: 0.7rem;
  color: var(--color-text-muted, #718096);
}

.history-detail {
  padding: var(--space-3) var(--space-4) var(--space-4);
  border-top: 1px solid var(--color-border, #e2e8f0);
}

.history-tags {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-1);
  margin-bottom: var(--space-2);
}

.tag {
  padding: 1px 6px;
  background: var(--color-accent-subtle, #ebf4ff);
  color: var(--color-accent, #3182ce);
  border-radius: 4px;
  font-size: 0.75rem;
}

.history-output {
  white-space: pre-wrap;
  font-size: 0.875rem;
  line-height: 1.6;
  color: var(--color-text, #1a202c);
}

.error-banner {
  background: var(--color-error-subtle, #fff5f5);
  border-bottom: 1px solid var(--color-error, #fc8181);
  padding: var(--space-2) var(--space-6);
  font-size: 0.875rem;
  color: var(--color-error-text, #c53030);
}

.error-inline {
  font-size: 0.875rem;
  color: var(--color-error-text, #c53030);
  padding: var(--space-1) 0;
}

.spinner {
  display: inline-block;
  width: 1em;
  height: 1em;
  border: 2px solid rgba(255,255,255,0.4);
  border-top-color: #fff;
  border-radius: 50%;
  animation: spin 0.7s linear infinite;
}

.analyze-btn .spinner {
  border-color: rgba(255,255,255,0.4);
  border-top-color: #fff;
}

.save-btn .spinner {
  border-color: rgba(0,0,0,0.15);
  border-top-color: var(--color-accent, #3182ce);
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

/* ── Picker mode ── */
.picker-mode {
  padding-top: var(--space-8, 2rem);
}

.picker-heading {
  font-size: 1.25rem;
  font-weight: 700;
  color: var(--color-text, #1a202c);
  margin: 0 0 var(--space-1) 0;
}

.picker-sub {
  font-size: 0.875rem;
  color: var(--color-text-muted, #718096);
  margin: 0 0 var(--space-4) 0;
}

.picker-empty {
  font-size: 0.875rem;
  color: var(--color-text-muted, #718096);
  padding: var(--space-4);
  border: 1px dashed var(--color-border, #e2e8f0);
  border-radius: var(--radius-md, 8px);
  text-align: center;
}

.picker-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.picker-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
  padding: var(--space-3) var(--space-4);
  background: var(--color-surface, #fff);
  border: 1px solid var(--color-border, #e2e8f0);
  border-radius: var(--radius-md, 8px);
  cursor: pointer;
  transition: border-color 0.15s, background 0.15s;
}

.picker-item:hover {
  border-color: var(--color-accent, #3182ce);
  background: var(--color-accent-subtle, #ebf4ff);
}

.picker-item__main {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.picker-item__company {
  font-weight: 600;
  font-size: 0.9rem;
  color: var(--color-text, #1a202c);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.picker-item__title {
  font-size: 0.8rem;
  color: var(--color-text-muted, #718096);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
</style>
