<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { storeToRefs } from 'pinia'
import { useFineTuneStore } from '../../stores/settings/fineTune'
import { useAppConfigStore } from '../../stores/appConfig'

const store = useFineTuneStore()
const config = useAppConfigStore()
const { step, inFlightJob, jobStatus, pairsCount, quotaRemaining } = storeToRefs(store)

const fileInput = ref<HTMLInputElement | null>(null)
const selectedFiles = ref<File[]>([])
const uploadResult = ref<{ file_count: number } | null>(null)
const extractError = ref<string | null>(null)
const modelReady = ref<boolean | null>(null)

async function handleUpload() {
  if (!selectedFiles.value.length) return
  store.uploading = true
  const form = new FormData()
  for (const f of selectedFiles.value) form.append('files', f)
  try {
    const res = await fetch('/api/settings/fine-tune/upload', { method: 'POST', body: form })
    uploadResult.value = await res.json()
    store.step = 2
  } catch {
    extractError.value = 'Upload failed'
  } finally {
    store.uploading = false
  }
}

async function handleExtract() {
  extractError.value = null
  const res = await fetch('/api/settings/fine-tune/extract', { method: 'POST' })
  if (!res.ok) { extractError.value = 'Extraction failed'; return }
  store.step = 3
}

async function checkLocalModel() {
  const res = await fetch('/api/settings/fine-tune/local-status')
  const data = await res.json()
  modelReady.value = data.model_ready
}

onMounted(async () => {
  store.startPolling()
  if (store.step === 3 && !config.isCloud) await checkLocalModel()
})
onUnmounted(() => { store.stopPolling(); store.resetStep() })
</script>

<template>
  <div class="fine-tune-view">
    <h2>Fine-Tune Model</h2>

    <!-- Wizard steps indicator -->
    <div class="wizard-steps">
      <span :class="['step', step >= 1 ? 'active' : '']">1. Upload</span>
      <span class="step-divider">›</span>
      <span :class="['step', step >= 2 ? 'active' : '']">2. Extract</span>
      <span class="step-divider">›</span>
      <span :class="['step', step >= 3 ? 'active' : '']">3. Train</span>
    </div>

    <!-- Step 1: Upload -->
    <section v-if="step === 1" class="form-section">
      <h3>Upload Cover Letters</h3>
      <p class="section-note">Upload .md or .txt cover letter files to build your training dataset.</p>
      <input
        ref="fileInput"
        type="file"
        accept=".md,.txt"
        multiple
        @change="selectedFiles = Array.from(($event.target as HTMLInputElement).files ?? [])"
        class="file-input"
      />
      <div class="form-actions">
        <button
          @click="handleUpload"
          :disabled="!selectedFiles.length || store.uploading"
          class="btn-primary"
        >
          {{ store.uploading ? 'Uploading…' : `Upload ${selectedFiles.length} file(s)` }}
        </button>
      </div>
    </section>

    <!-- Step 2: Extract pairs -->
    <section v-else-if="step === 2" class="form-section">
      <h3>Extract Training Pairs</h3>
      <p v-if="uploadResult">{{ uploadResult.file_count }} file(s) uploaded.</p>
      <p class="section-note">Extract job description + cover letter pairs for training.</p>
      <p v-if="pairsCount > 0" class="pairs-count">{{ pairsCount }} pairs extracted so far.</p>
      <p v-if="extractError" class="error-msg">{{ extractError }}</p>
      <div class="form-actions">
        <button @click="handleExtract" :disabled="inFlightJob" class="btn-primary">
          {{ inFlightJob ? 'Extracting…' : 'Extract Pairs' }}
        </button>
        <button @click="store.step = 3" class="btn-secondary">Skip → Train</button>
      </div>
    </section>

    <!-- Step 3: Train -->
    <section v-else class="form-section">
      <h3>Train Model</h3>
      <p class="pairs-count">{{ pairsCount }} training pairs available.</p>

      <!-- Job status banner (if in-flight) -->
      <div v-if="inFlightJob" class="status-banner status-running">
        Job {{ jobStatus }} — polling every 2s…
      </div>
      <div v-else-if="jobStatus === 'completed'" class="status-banner status-ok">
        Training complete.
      </div>
      <div v-else-if="jobStatus === 'failed'" class="status-banner status-fail">
        Training failed. Check logs.
      </div>

      <!-- Self-hosted path -->
      <template v-if="!config.isCloud">
        <p class="section-note">Run locally with Unsloth + Ollama:</p>
        <pre class="code-block">make finetune</pre>
        <div v-if="modelReady === null" class="form-actions">
          <button @click="checkLocalModel" class="btn-secondary">Check Model Status</button>
        </div>
        <p v-else-if="modelReady" class="status-ok">✓ alex-cover-writer model is ready in Ollama.</p>
        <p v-else class="status-fail">Model not yet registered. Run <code>make finetune</code> first.</p>
      </template>

      <!-- Cloud path -->
      <template v-else>
        <p v-if="quotaRemaining !== null" class="section-note">
          Cloud quota remaining: {{ quotaRemaining }} jobs
        </p>
        <div class="form-actions">
          <button
            @click="store.submitJob()"
            :disabled="inFlightJob || pairsCount === 0"
            class="btn-primary"
          >
            {{ inFlightJob ? 'Job queued…' : 'Submit Training Job' }}
          </button>
        </div>
      </template>
    </section>
  </div>
</template>

<style scoped>
.fine-tune-view { max-width: 640px; }
.wizard-steps { display: flex; align-items: center; gap: 0.5rem; margin-bottom: 1.5rem; font-size: 0.9rem; }
.step { padding: 0.25rem 0.75rem; border-radius: 99px; background: var(--color-surface-2, #eee); color: var(--color-text-muted, #888); }
.step.active { background: var(--color-accent, #3b82f6); color: #fff; }
.step-divider { color: var(--color-text-muted, #888); }
.file-input { display: block; margin: 0.75rem 0; }
.pairs-count { font-weight: 600; margin-bottom: 0.5rem; }
.code-block { background: var(--color-surface-2, #f5f5f5); padding: 0.75rem 1rem; border-radius: 6px; font-family: monospace; margin: 0.75rem 0; }
.status-banner { padding: 0.6rem 1rem; border-radius: 6px; margin-bottom: 1rem; font-size: 0.9rem; }
.status-running { background: var(--color-warning-bg, #fef3c7); color: var(--color-warning-fg, #92400e); }
.status-ok { color: var(--color-success, #16a34a); }
.status-fail { color: var(--color-error, #dc2626); }
</style>
