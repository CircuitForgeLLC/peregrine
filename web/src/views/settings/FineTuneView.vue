<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { storeToRefs } from 'pinia'
import { useFineTuneStore } from '../../stores/settings/fineTune'
import { useAppConfigStore } from '../../stores/appConfig'

const store = useFineTuneStore()
const config = useAppConfigStore()
const { step, inFlightJob, jobStatus, pairsCount, quotaRemaining, pairs, pairsLoading } = storeToRefs(store)

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
  await store.loadPairs()
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

      <!-- Training pairs list -->
      <div v-if="pairs.length > 0" class="pairs-list">
        <h4>Training Pairs <span class="pairs-badge">{{ pairs.length }}</span></h4>
        <p class="section-note">Review and remove any low-quality pairs before training.</p>
        <div v-if="pairsLoading" class="pairs-loading">Loading…</div>
        <ul v-else class="pairs-items">
          <li v-for="pair in pairs" :key="pair.index" class="pair-item">
            <div class="pair-info">
              <span class="pair-instruction">{{ pair.instruction }}</span>
              <span class="pair-source">{{ pair.source_file }}</span>
            </div>
            <button class="pair-delete" @click="store.deletePair(pair.index)" title="Remove this pair">✕</button>
          </li>
        </ul>
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

.pairs-list { margin-top: var(--space-6, 1.5rem); }
.pairs-list h4 { font-size: 0.95rem; font-weight: 600; margin: 0 0 var(--space-2, 0.5rem); display: flex; align-items: center; gap: 0.5rem; }
.pairs-badge { background: var(--color-primary, #2d5a27); color: #fff; font-size: 0.75rem; padding: 1px 7px; border-radius: var(--radius-full, 9999px); }
.pairs-loading { color: var(--color-text-muted); font-size: 0.875rem; padding: var(--space-2, 0.5rem) 0; }
.pairs-items { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: var(--space-2, 0.5rem); max-height: 280px; overflow-y: auto; }
.pair-item { display: flex; align-items: center; gap: var(--space-3, 0.75rem); padding: var(--space-2, 0.5rem) var(--space-3, 0.75rem); background: var(--color-surface-alt); border: 1px solid var(--color-border-light); border-radius: var(--radius-md); }
.pair-info { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 2px; }
.pair-instruction { font-size: 0.85rem; color: var(--color-text); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.pair-source { font-size: 0.75rem; color: var(--color-text-muted); }
.pair-delete { flex-shrink: 0; background: none; border: none; color: var(--color-error); cursor: pointer; font-size: 0.9rem; padding: 2px 4px; border-radius: var(--radius-sm); transition: background 150ms; }
.pair-delete:hover { background: var(--color-error); color: #fff; }
</style>
