<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { storeToRefs } from 'pinia'
import { useFineTuneStore } from '../../stores/settings/fineTune'
import { useAppConfigStore } from '../../stores/appConfig'
import { showToast } from '../../composables/useToast'

const store = useFineTuneStore()
const config = useAppConfigStore()
const { step, inFlightJob, jobStatus, pairsCount, quotaRemaining, pairs, pairsLoading,
        optedIn, dbPairs, dbPairsLoading, dbExcludedCount } = storeToRefs(store)

const fileInput = ref<HTMLInputElement | null>(null)
const selectedFiles = ref<File[]>([])
const uploadResult = ref<{ file_count: number } | null>(null)
const extractError = ref<string | null>(null)
const modelReady = ref<boolean | null>(null)
const toggling = ref(false)
const toggleSaved = ref(false)

async function handleOptInChange(e: Event) {
  const enabled = (e.target as HTMLInputElement).checked
  toggling.value = true
  toggleSaved.value = false
  await store.toggleOptIn(enabled)
  await store.loadDbPairs()
  toggling.value = false
  toggleSaved.value = true
  setTimeout(() => { toggleSaved.value = false }, 2000)
}

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
  await store.loadStatus()
  await store.loadPairs()
  await store.loadDbPairs()
  if (store.step === 3 && !config.isCloud) await checkLocalModel()
})
onUnmounted(() => { store.stopPolling(); store.resetStep() })
</script>

<template>
  <div class="fine-tune-view">
    <h2>Fine-Tune Model</h2>

    <!-- Training Export: consent toggle (always visible) -->
    <section class="form-section training-export-consent">
      <h3>Training Export</h3>
      <p class="section-note">
        When enabled, your applied-job cover letters are available as a local dataset file
        for fine-tuning a language model to your writing style.
      </p>
      <label class="toggle-label" :class="{ 'toggle-saving': toggling }">
        <input
          type="checkbox"
          :checked="optedIn"
          :disabled="toggling"
          @change="handleOptInChange"
          aria-describedby="opt-in-desc"
        />
        Include cover letters in training export
        <span v-if="toggling" class="toggle-status" aria-live="polite">Saving…</span>
        <span v-else-if="toggleSaved" class="toggle-status" aria-live="polite">Saved</span>
      </label>
      <p class="section-note" id="opt-in-desc">
        <template v-if="!config.isCloud">
          Your cover letters stay on your device unless you explicitly request cloud fine-tuning.
        </template>
        <template v-else>
          Your cover letters are stored on your CircuitForge account and are not shared with any
          third party unless you explicitly request cloud fine-tuning.
        </template>
        <span v-if="!optedIn" class="opt-out-receipt">
          Training export is off — cover letters remain local only.
          You can change this in Settings at any time.
        </span>
      </p>
    </section>

    <!-- From Applied Jobs: curation list (only when opted in) -->
    <section v-if="optedIn" class="form-section">
      <h3>From Applied Jobs</h3>
      <div class="db-pairs-header">
        <span class="pairs-count">
          {{
            dbPairs.filter(p => !p.excluded).length === 1
              ? '1 pair available'
              : `${dbPairs.filter(p => !p.excluded).length} pairs available`
          }}
          <span
            v-if="dbExcludedCount > 0"
            class="excluded-badge"
            :title="`${dbExcludedCount} pair(s) excluded — use Restore to re-include`"
          >{{ dbExcludedCount }} excluded</span>
        </span>
        <div class="db-pairs-actions">
          <button
            class="btn-secondary"
            :disabled="dbPairs.filter(p => !p.excluded).length === 0"
            @click="store.downloadExport()"
          >
            Download JSONL <span aria-hidden="true">↓</span>
          </button>
          <div class="cloud-finetune-wrap">
            <button
              class="btn-secondary"
              :disabled="config.tier !== 'premium' || dbPairs.filter(p => !p.excluded).length === 0"
              @click="config.tier === 'premium' && showToast('Cloud fine-tuning coming soon')"
            >
              Request Cloud Fine-Tune
            </button>
            <p v-if="config.tier !== 'premium'" class="tier-gate-note">
              Available on Premium.
              <a href="/settings?tab=license" class="upgrade-link">Upgrade your plan →</a>
            </p>
          </div>
        </div>
      </div>
      <p class="section-note download-advisory">
        The downloaded file contains your cover letters in plain text (JSONL format).
        Store it in a secure location.
      </p>

      <div aria-live="polite" aria-atomic="false" aria-label="Applied jobs training pairs">
        <div v-if="dbPairsLoading" class="pairs-loading">Loading…</div>
        <ul v-else-if="dbPairs.length > 0" class="pairs-items db-pairs-items">
          <li
            v-for="pair in dbPairs"
            :key="pair.job_id"
            class="pair-item"
            :class="{ 'pair-excluded': pair.excluded }"
          >
            <div class="pair-info">
              <span class="pair-instruction">{{ pair.title }} · {{ pair.company }}</span>
              <span class="pair-source">{{ pair.status }}</span>
            </div>
            <button
              v-if="!pair.excluded"
              class="pair-delete"
              title="Exclude from training export"
              @click="store.excludeDbPair(pair.job_id)"
            >Exclude</button>
            <button
              v-else
              class="pair-restore"
              title="Restore to training export"
              @click="store.includeDbPair(pair.job_id)"
            >Restore</button>
          </li>
        </ul>
        <p v-else class="section-note">No applied jobs with cover letters found.</p>
      </div>
    </section>

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
.training-export-consent { border: 1px solid var(--color-border-light); border-radius: var(--radius-md); padding: var(--space-4, 1rem); margin-bottom: var(--space-6, 1.5rem); }
.toggle-label { display: flex; align-items: center; gap: var(--space-2, 0.5rem); font-size: 0.9rem; font-weight: 500; cursor: pointer; flex-wrap: wrap; }
.toggle-label.toggle-saving { opacity: 0.7; }
.toggle-label input[type="checkbox"] { width: 16px; height: 16px; accent-color: var(--color-primary); cursor: pointer; flex-shrink: 0; }
.toggle-status { font-size: 0.8rem; color: var(--color-text-muted); margin-left: var(--space-1, 0.25rem); }
.opt-out-receipt { display: block; margin-top: var(--space-1, 0.25rem); color: var(--color-text-muted); font-size: 0.8rem; }
.db-pairs-header { display: flex; align-items: flex-start; justify-content: space-between; flex-wrap: wrap; gap: var(--space-3, 0.75rem); margin-bottom: var(--space-4, 1rem); }
.db-pairs-actions { display: flex; align-items: flex-start; gap: var(--space-2, 0.5rem); flex-wrap: wrap; }
.cloud-finetune-wrap { display: flex; flex-direction: column; gap: var(--space-1, 0.25rem); }
.tier-gate-note { font-size: 0.8rem; color: var(--color-text-muted); margin: 0; }
.upgrade-link { color: var(--color-primary); text-decoration: underline; }
.excluded-badge { margin-left: var(--space-2, 0.5rem); background: var(--color-warning-bg, #fef3c7); color: var(--color-warning-fg, #92400e); font-size: 0.75rem; padding: 1px 6px; border-radius: var(--radius-full, 9999px); }
.db-pairs-items { max-height: 320px; }
.pair-excluded { opacity: 0.5; }
.pair-restore { flex-shrink: 0; background: none; border: 1px solid var(--color-border); color: var(--color-text-muted); cursor: pointer; font-size: 0.8rem; padding: 2px 8px; border-radius: var(--radius-sm); }
.pair-restore:hover { background: var(--color-surface-alt); }
.download-advisory { margin-top: var(--space-2, 0.5rem); font-style: italic; }
</style>
