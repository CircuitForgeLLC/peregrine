<template>
  <div class="system-settings">
    <h2>System Settings</h2>
    <p class="tab-note">This tab is only available in self-hosted mode.</p>

    <p v-if="store.loadError" class="error-banner">{{ store.loadError }}</p>

    <!-- LLM Backends -->
    <section class="form-section">
      <h3>LLM Backends</h3>
      <p class="section-note">Drag to reorder. Higher position = higher priority in the fallback chain.</p>

      <div class="backend-list">
        <div
          v-for="(backend, idx) in visibleBackends"
          :key="backend.id"
          class="backend-card"
          draggable="true"
          @dragstart="dragStart(idx)"
          @dragover.prevent="dragOver(idx)"
          @drop="drop"
        >
          <span class="drag-handle" aria-hidden="true">⠿</span>
          <span class="priority-badge">{{ idx + 1 }}</span>
          <span class="backend-id">{{ backend.id }}</span>
          <label class="toggle-label">
            <input
              type="checkbox"
              :checked="backend.enabled"
              @change="store.backends = store.backends.map(b =>
                b.id === backend.id ? { ...b, enabled: !b.enabled } : b
              )"
            />
            <span class="toggle-text">{{ backend.enabled ? 'Enabled' : 'Disabled' }}</span>
          </label>
        </div>
      </div>

      <div class="form-actions">
        <button @click="store.trySave()" :disabled="store.saving" class="btn-primary">
          {{ store.saving ? 'Saving…' : 'Save Backends' }}
        </button>
        <p v-if="store.saveError" class="error">{{ store.saveError }}</p>
      </div>
    </section>

    <!-- BYOK Modal -->
    <Teleport to="body">
      <div v-if="store.byokPending.length > 0" class="modal-overlay" @click.self="store.cancelByok()">
        <div class="modal-card" role="dialog" aria-modal="true" aria-labelledby="byok-title">
          <h3 id="byok-title">⚠️ Cloud LLM Key Required</h3>
          <p>You are enabling the following cloud backends:</p>
          <ul>
            <li v-for="b in store.byokPending" :key="b">{{ b }}</li>
          </ul>
          <p class="byok-warning">
            These services require your own API key. Your requests and data will be
            sent to these third-party providers. Costs will be charged to your account.
          </p>
          <label class="checkbox-row">
            <input type="checkbox" v-model="byokConfirmed" />
            I understand and have configured my API key in <code>config/llm.yaml</code>
          </label>
          <div class="modal-actions">
            <button @click="store.cancelByok()" class="btn-cancel">Cancel</button>
            <button
              @click="handleConfirmByok"
              :disabled="!byokConfirmed || store.saving"
              class="btn-primary"
            >{{ store.saving ? 'Saving…' : 'Save with Cloud LLM' }}</button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useSystemStore } from '../../stores/settings/system'
import { useAppConfigStore } from '../../stores/appConfig'

const store = useSystemStore()
const config = useAppConfigStore()

const byokConfirmed = ref(false)
const dragIdx = ref<number | null>(null)

const CONTRACTED_ONLY = ['claude-code', 'copilot']

const visibleBackends = computed(() =>
  store.backends.filter(b =>
    !CONTRACTED_ONLY.includes(b.id) || config.contractedClient
  )
)

function dragStart(idx: number) {
  dragIdx.value = idx
}

function dragOver(toFilteredIdx: number) {
  if (dragIdx.value === null || dragIdx.value === toFilteredIdx) return
  const fromId = visibleBackends.value[dragIdx.value].id
  const toId = visibleBackends.value[toFilteredIdx].id
  const arr = [...store.backends]
  const fromFull = arr.findIndex(b => b.id === fromId)
  const toFull = arr.findIndex(b => b.id === toId)
  if (fromFull === -1 || toFull === -1) return
  const [moved] = arr.splice(fromFull, 1)
  arr.splice(toFull, 0, moved)
  store.backends = arr.map((b, i) => ({ ...b, priority: i + 1 }))
  dragIdx.value = toFilteredIdx
}

function drop() {
  dragIdx.value = null
}

async function handleConfirmByok() {
  await store.confirmByok()
  byokConfirmed.value = false
}

onMounted(() => store.loadLlm())
</script>

<style scoped>
.system-settings { max-width: 720px; margin: 0 auto; padding: var(--space-4, 24px); }
h2 { font-size: 1.4rem; font-weight: 600; margin-bottom: 6px; color: var(--color-text-primary, #e2e8f0); }
h3 { font-size: 1rem; font-weight: 600; margin-bottom: var(--space-3, 16px); color: var(--color-text-primary, #e2e8f0); }
.tab-note { font-size: 0.82rem; color: var(--color-text-secondary, #94a3b8); margin-bottom: var(--space-6, 32px); }
.form-section { margin-bottom: var(--space-8, 48px); padding-bottom: var(--space-6, 32px); border-bottom: 1px solid var(--color-border, rgba(255,255,255,0.08)); }
.section-note { font-size: 0.78rem; color: var(--color-text-secondary, #94a3b8); margin-bottom: 14px; }
.backend-list { display: flex; flex-direction: column; gap: 8px; margin-bottom: 20px; }
.backend-card { display: flex; align-items: center; gap: 12px; padding: 10px 14px; background: var(--color-surface-2, rgba(255,255,255,0.04)); border: 1px solid var(--color-border, rgba(255,255,255,0.08)); border-radius: 8px; cursor: grab; user-select: none; }
.backend-card:active { cursor: grabbing; }
.drag-handle { font-size: 1.1rem; color: var(--color-text-secondary, #64748b); }
.priority-badge { width: 22px; height: 22px; border-radius: 50%; background: rgba(124,58,237,0.2); color: var(--color-accent, #a78bfa); font-size: 0.72rem; font-weight: 700; display: flex; align-items: center; justify-content: center; flex-shrink: 0; }
.backend-id { flex: 1; font-size: 0.9rem; font-family: monospace; color: var(--color-text-primary, #e2e8f0); }
.toggle-label { display: flex; align-items: center; gap: 6px; cursor: pointer; font-size: 0.82rem; color: var(--color-text-secondary, #94a3b8); }
.form-actions { display: flex; align-items: center; gap: var(--space-4, 24px); }
.btn-primary { padding: 9px 24px; background: var(--color-accent, #7c3aed); color: #fff; border: none; border-radius: 7px; font-size: 0.9rem; cursor: pointer; font-weight: 600; }
.btn-primary:disabled { opacity: 0.5; cursor: not-allowed; }
.btn-cancel { padding: 9px 18px; background: transparent; border: 1px solid var(--color-border, rgba(255,255,255,0.2)); border-radius: 7px; color: var(--color-text-secondary, #94a3b8); cursor: pointer; font-size: 0.9rem; }
.error-banner { background: rgba(239,68,68,0.1); border: 1px solid rgba(239,68,68,0.3); border-radius: 6px; color: #ef4444; padding: 10px 14px; margin-bottom: 20px; font-size: 0.85rem; }
.error { color: #ef4444; font-size: 0.82rem; }
/* BYOK Modal */
.modal-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.6); display: flex; align-items: center; justify-content: center; z-index: 9999; }
.modal-card { background: var(--color-surface-1, #1e293b); border: 1px solid var(--color-border, rgba(255,255,255,0.12)); border-radius: 12px; padding: 28px; max-width: 480px; width: 90%; }
.modal-card h3 { font-size: 1.1rem; margin-bottom: 12px; color: var(--color-text-primary, #e2e8f0); }
.modal-card p { font-size: 0.88rem; color: var(--color-text-secondary, #94a3b8); margin-bottom: 12px; }
.modal-card ul { margin: 8px 0 16px 20px; font-size: 0.88rem; color: var(--color-text-primary, #e2e8f0); }
.byok-warning { background: rgba(245,158,11,0.1); border: 1px solid rgba(245,158,11,0.3); border-radius: 6px; padding: 10px 12px; color: #fbbf24 !important; }
.checkbox-row { display: flex; align-items: flex-start; gap: 8px; font-size: 0.85rem; color: var(--color-text-primary, #e2e8f0); cursor: pointer; margin: 16px 0; }
.modal-actions { display: flex; gap: 10px; justify-content: flex-end; margin-top: 20px; }
</style>
