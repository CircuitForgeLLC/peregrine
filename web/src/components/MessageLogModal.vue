<!-- web/src/components/MessageLogModal.vue -->
<template>
  <Teleport to="body">
    <div
      v-if="show"
      class="modal-backdrop"
      @click.self="emit('close')"
      @keydown.esc="emit('close')"
    >
      <div
        ref="dialogEl"
        class="modal-dialog"
        role="dialog"
        aria-modal="true"
        :aria-label="title"
        tabindex="-1"
      >
        <header class="modal-header">
          <h2 class="modal-title">{{ title }}</h2>
          <button class="modal-close" @click="emit('close')" aria-label="Close">✕</button>
        </header>

        <form class="modal-body" @submit.prevent="handleSubmit">
          <!-- Direction (not shown for pure notes) -->
          <div v-if="type !== 'in_person'" class="field">
            <label class="field-label" for="log-direction">Direction</label>
            <select id="log-direction" v-model="form.direction" class="field-select">
              <option value="">-- not specified --</option>
              <option value="inbound">Inbound (they called me)</option>
              <option value="outbound">Outbound (I called them)</option>
            </select>
          </div>

          <div class="field">
            <label class="field-label" for="log-subject">Subject (optional)</label>
            <input id="log-subject" v-model="form.subject" type="text" class="field-input" />
          </div>

          <div class="field">
            <label class="field-label" for="log-body">
              Notes <span class="field-required" aria-hidden="true">*</span>
            </label>
            <textarea
              id="log-body"
              v-model="form.body"
              class="field-textarea"
              rows="5"
              required
              aria-required="true"
            />
          </div>

          <div class="field">
            <label class="field-label" for="log-date">Date/time</label>
            <input id="log-date" v-model="form.logged_at" type="datetime-local" class="field-input" />
          </div>

          <p v-if="error" class="modal-error" role="alert">{{ error }}</p>

          <footer class="modal-footer">
            <button type="button" class="btn btn--ghost" @click="emit('close')">Cancel</button>
            <button type="submit" class="btn btn--primary" :disabled="saving">
              {{ saving ? 'Saving…' : 'Save' }}
            </button>
          </footer>
        </form>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { ref, computed, watch, nextTick } from 'vue'
import { useMessagingStore } from '../stores/messaging'

const props = defineProps<{
  show: boolean
  jobId: number
  type: 'call_note' | 'in_person'
}>()

const emit = defineEmits<{
  (e: 'close'): void
  (e: 'saved'): void
}>()

const store = useMessagingStore()
const dialogEl = ref<HTMLElement | null>(null)
const saving = ref(false)
const error = ref<string | null>(null)

const title = computed(() =>
  props.type === 'call_note' ? 'Log a call' : 'Log an in-person note'
)

const now = new Date()
const localNow = new Date(now.getTime() - now.getTimezoneOffset() * 60000)
  .toISOString()
  .slice(0, 16)

const form = ref({
  direction: '',
  subject: '',
  body: '',
  logged_at: localNow,
})

// Focus the dialog when it opens
watch(() => props.show, async (val) => {
  if (val) {
    error.value = null
    form.value = { direction: '', subject: '', body: '', logged_at: localNow }
    await nextTick()
    dialogEl.value?.focus()
  }
})

async function handleSubmit() {
  if (!form.value.body.trim()) { error.value = 'Notes are required.'; return }
  saving.value = true
  error.value = null
  const result = await store.createMessage({
    job_id: props.jobId,
    job_contact_id: null,
    type: props.type,
    direction: form.value.direction || null,
    subject: form.value.subject || null,
    body: form.value.body,
    from_addr: null,
    to_addr: null,
    template_id: null,
  })
  saving.value = false
  if (result) emit('saved')
  else error.value = store.error ?? 'Save failed.'
}
</script>

<style scoped>
.modal-backdrop {
  position: fixed;
  inset: 0;
  background: rgba(0,0,0,0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 200;
}
.modal-dialog {
  background: var(--color-surface-raised);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  width: min(480px, 95vw);
  max-height: 90vh;
  overflow-y: auto;
  outline: none;
}
.modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--space-4) var(--space-5);
  border-bottom: 1px solid var(--color-border-light);
}
.modal-title { font-size: var(--text-lg); font-weight: 600; margin: 0; }
.modal-close {
  background: none; border: none; cursor: pointer;
  color: var(--color-text-muted); font-size: var(--text-lg);
  padding: var(--space-1); border-radius: var(--radius-sm);
  min-width: 32px; min-height: 32px;
}
.modal-close:hover { background: var(--color-surface-alt); }
.modal-body { padding: var(--space-4) var(--space-5); display: flex; flex-direction: column; gap: var(--space-4); }
.field { display: flex; flex-direction: column; gap: var(--space-1); }
.field-label { font-size: var(--text-sm); font-weight: 500; color: var(--color-text-muted); }
.field-required { color: var(--app-accent); }
.field-input, .field-select, .field-textarea {
  padding: var(--space-2) var(--space-3);
  background: var(--color-surface-alt);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  color: var(--color-text);
  font-size: var(--text-sm);
  font-family: var(--font-body);
  width: 100%;
}
.field-input:focus-visible, .field-select:focus-visible, .field-textarea:focus-visible {
  outline: 2px solid var(--app-primary);
  outline-offset: 2px;
}
.field-textarea { resize: vertical; }
.modal-error { color: var(--app-accent); font-size: var(--text-sm); margin: 0; }
.modal-footer { display: flex; justify-content: flex-end; gap: var(--space-3); padding-top: var(--space-2); }
.btn { padding: var(--space-2) var(--space-4); border-radius: var(--radius-md); font-size: var(--text-sm); font-weight: 500; cursor: pointer; min-height: 40px; }
.btn--primary { background: var(--app-primary); color: var(--color-surface); border: none; }
.btn--primary:hover:not(:disabled) { opacity: 0.9; }
.btn--primary:disabled { opacity: 0.5; cursor: not-allowed; }
.btn--ghost { background: none; border: 1px solid var(--color-border); color: var(--color-text); }
.btn--ghost:hover { background: var(--color-surface-alt); }
</style>
