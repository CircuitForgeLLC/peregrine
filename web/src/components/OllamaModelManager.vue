<template>
  <div class="omm">
    <div v-if="store.ollamaModelsLoading" class="omm__loading">Checking model status…</div>

    <div v-else-if="!store.ollamaReachable" class="omm__offline">
      <span class="omm__dot omm__dot--off"></span>
      Ollama is not reachable. Start it via the Services section below, then reload.
    </div>

    <template v-else>
      <div
        v-for="model in store.ollamaModels"
        :key="model.name"
        class="omm__row"
      >
        <div class="omm__info">
          <span class="omm__dot" :class="model.installed ? 'omm__dot--ok' : 'omm__dot--missing'"></span>
          <div>
            <div class="omm__name">{{ model.display_name }}</div>
            <div class="omm__desc">{{ model.description }}</div>
            <div class="omm__meta">
              <code class="omm__tag">{{ model.name }}</code>
              <span v-if="model.size_gb" class="omm__size">~{{ model.size_gb }} GB</span>
              <span class="omm__status" :class="model.installed ? 'omm__status--ok' : 'omm__status--missing'">
                {{ model.installed ? 'Installed' : 'Not installed' }}
              </span>
            </div>
          </div>
        </div>

        <button
          v-if="!model.installed"
          class="omm__btn"
          :disabled="pulling === model.name"
          @click="startConsent(model)"
        >
          {{ pulling === model.name ? 'Downloading…' : 'Download' }}
        </button>
        <span v-else class="omm__check" aria-label="Installed">✓</span>
      </div>

      <p v-if="store.ollamaModels.length === 0" class="omm__empty">
        No Ollama backends are configured in your LLM settings.
      </p>
    </template>

    <!-- Consent + progress modal -->
    <Teleport to="body">
      <div v-if="consentModel" class="omm__overlay" @click.self="cancelConsent">
        <div class="omm__modal" role="dialog" aria-modal="true" aria-labelledby="omm-title">
          <h3 id="omm-title">Download {{ consentModel.display_name }}?</h3>
          <p class="omm__modal-desc">{{ consentModel.description }}</p>

          <div class="omm__modal-meta">
            <div class="omm__meta-row">
              <span class="omm__meta-label">Model</span>
              <code>{{ consentModel.name }}</code>
            </div>
            <div class="omm__meta-row" v-if="consentModel.size_gb">
              <span class="omm__meta-label">Download size</span>
              <span>~{{ consentModel.size_gb }} GB</span>
            </div>
          </div>

          <div class="omm__privacy">
            <span class="omm__privacy-icon">🔒</span>
            <span>
              This model runs entirely on your own hardware.
              No data is sent to any server during inference.
            </span>
          </div>

          <!-- Progress bar (shown during download) -->
          <div v-if="pulling === consentModel.name" class="omm__progress-wrap">
            <div class="omm__progress-label">{{ pullStatus }}</div>
            <div class="omm__progress-bar">
              <div class="omm__progress-fill" :style="{ width: pullPct + '%' }"></div>
            </div>
            <div class="omm__progress-pct">{{ pullPct }}%</div>
          </div>

          <p v-if="pullError" class="omm__error">{{ pullError }}</p>

          <div class="omm__modal-actions">
            <button
              class="omm__btn-cancel"
              @click="cancelConsent"
              :disabled="pulling === consentModel.name"
            >Cancel</button>
            <button
              class="omm__btn-confirm"
              @click="confirmDownload"
              :disabled="pulling === consentModel.name"
            >
              {{ pulling === consentModel.name ? 'Downloading…' : `Download ${consentModel.size_gb ? '(~' + consentModel.size_gb + ' GB)' : ''}` }}
            </button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useSystemStore, type OllamaModel } from '../stores/settings/system'
import { useApiSSE } from '../composables/useApi'

const store = useSystemStore()

const consentModel = ref<OllamaModel | null>(null)
const pulling = ref<string | null>(null)
const pullStatus = ref('')
const pullPct = ref(0)
const pullError = ref<string | null>(null)
let _stopSSE: (() => void) | null = null

function startConsent(model: OllamaModel) {
  consentModel.value = model
  pullStatus.value = ''
  pullPct.value = 0
  pullError.value = null
}

function cancelConsent() {
  if (pulling.value) return  // don't dismiss mid-download
  consentModel.value = null
}

function confirmDownload() {
  if (!consentModel.value) return
  const model = consentModel.value
  pulling.value = model.name
  pullStatus.value = 'Starting download…'
  pullPct.value = 0
  pullError.value = null

  _stopSSE = useApiSSE(
    `/api/system/ollama/pull?model=${encodeURIComponent(model.name)}`,
    (event) => {
      const type = event.type as string
      if (type === 'already_installed' || type === 'complete') {
        pulling.value = null
        consentModel.value = null
        _stopSSE?.()
        store.loadOllamaModels()
        return
      }
      if (type === 'error') {
        pullError.value = String(event.message ?? 'Download failed')
        pulling.value = null
        _stopSSE?.()
        return
      }
      if (type === 'progress') {
        pullStatus.value = String(event.status ?? '')
        if (typeof event.pct === 'number') pullPct.value = event.pct
      }
    },
    () => {
      // onComplete (server closes stream)
      pulling.value = null
      consentModel.value = null
      store.loadOllamaModels()
    },
    () => {
      pullError.value = 'Connection to server lost during download.'
      pulling.value = null
    },
  )
}
</script>

<style scoped>
.omm { display: flex; flex-direction: column; gap: var(--space-3); }
.omm__loading, .omm__offline, .omm__empty {
  font-size: 0.85rem; color: var(--color-text-muted); padding: var(--space-2) 0;
}
.omm__offline { display: flex; align-items: center; gap: var(--space-2); }

.omm__row {
  display: flex; align-items: flex-start; justify-content: space-between; gap: var(--space-4);
  padding: var(--space-3) var(--space-4);
  background: var(--color-surface-alt);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
}
.omm__info { display: flex; align-items: flex-start; gap: var(--space-3); flex: 1; min-width: 0; }
.omm__dot {
  width: 10px; height: 10px; border-radius: 50%; flex-shrink: 0; margin-top: 5px;
}
.omm__dot--ok { background: var(--color-success, #22c55e); }
.omm__dot--missing { background: var(--color-warning, #f59e0b); }
.omm__dot--off { background: var(--color-text-muted); }
.omm__name { font-weight: 600; font-size: 0.9rem; color: var(--color-text); }
.omm__desc { font-size: 0.8rem; color: var(--color-text-muted); margin-top: 2px; }
.omm__meta { display: flex; align-items: center; gap: var(--space-2); margin-top: var(--space-1); flex-wrap: wrap; }
.omm__tag { font-size: 0.75rem; background: var(--color-surface); padding: 1px 6px; border-radius: 4px; border: 1px solid var(--color-border); }
.omm__size { font-size: 0.75rem; color: var(--color-text-muted); }
.omm__status { font-size: 0.75rem; font-weight: 600; }
.omm__status--ok { color: var(--color-success, #22c55e); }
.omm__status--missing { color: var(--color-warning, #f59e0b); }

.omm__btn {
  padding: 6px 14px; border-radius: var(--radius-sm);
  background: var(--color-accent); color: var(--color-text-inverse);
  border: none; font-size: 0.82rem; font-weight: 600; cursor: pointer; white-space: nowrap; flex-shrink: 0;
}
.omm__btn:disabled { opacity: 0.55; cursor: default; }
.omm__check { font-size: 1rem; color: var(--color-success, #22c55e); flex-shrink: 0; padding: 4px 8px; }

/* Modal */
.omm__overlay {
  position: fixed; inset: 0; background: rgba(0,0,0,0.5);
  display: flex; align-items: center; justify-content: center; z-index: 1000;
}
.omm__modal {
  background: var(--color-surface); border: 1px solid var(--color-border);
  border-radius: var(--radius-lg); padding: var(--space-6); max-width: 420px; width: 90%;
  box-shadow: 0 8px 32px rgba(0,0,0,0.3);
}
.omm__modal h3 { margin: 0 0 var(--space-3); font-size: 1.1rem; }
.omm__modal-desc { font-size: 0.88rem; color: var(--color-text-muted); margin-bottom: var(--space-4); }
.omm__modal-meta { display: flex; flex-direction: column; gap: var(--space-2); margin-bottom: var(--space-4); }
.omm__meta-row { display: flex; gap: var(--space-3); align-items: center; font-size: 0.85rem; }
.omm__meta-label { color: var(--color-text-muted); width: 110px; flex-shrink: 0; }

.omm__privacy {
  display: flex; align-items: flex-start; gap: var(--space-2);
  background: color-mix(in srgb, var(--color-accent) 8%, transparent);
  border: 1px solid color-mix(in srgb, var(--color-accent) 20%, transparent);
  border-radius: var(--radius-sm); padding: var(--space-3);
  font-size: 0.82rem; color: var(--color-text-muted); margin-bottom: var(--space-5);
}
.omm__privacy-icon { flex-shrink: 0; }

.omm__progress-wrap { margin-bottom: var(--space-4); }
.omm__progress-label { font-size: 0.8rem; color: var(--color-text-muted); margin-bottom: var(--space-1); }
.omm__progress-bar {
  width: 100%; height: 6px; background: var(--color-surface-alt);
  border-radius: 3px; overflow: hidden;
}
.omm__progress-fill { height: 100%; background: var(--color-accent); transition: width 0.3s ease; }
.omm__progress-pct { font-size: 0.75rem; color: var(--color-text-muted); margin-top: 4px; text-align: right; }

.omm__error { color: var(--color-error, #ef4444); font-size: 0.82rem; margin-bottom: var(--space-3); }

.omm__modal-actions { display: flex; gap: var(--space-3); justify-content: flex-end; }
.omm__btn-cancel {
  padding: 8px 16px; border-radius: var(--radius-sm);
  background: transparent; border: 1px solid var(--color-border);
  color: var(--color-text-muted); font-size: 0.88rem; cursor: pointer;
}
.omm__btn-cancel:disabled { opacity: 0.5; cursor: default; }
.omm__btn-confirm {
  padding: 8px 18px; border-radius: var(--radius-sm);
  background: var(--color-accent); color: var(--color-text-inverse);
  border: none; font-size: 0.88rem; font-weight: 600; cursor: pointer;
}
.omm__btn-confirm:disabled { opacity: 0.55; cursor: default; }
</style>
