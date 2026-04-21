<!-- web/src/components/MessageTemplateModal.vue -->
<template>
  <Teleport to="body">
    <div
      v-if="show"
      class="modal-backdrop"
      @click.self="emit('close')"
    >
      <div
        ref="dialogEl"
        class="modal-dialog modal-dialog--wide"
        role="dialog"
        aria-modal="true"
        :aria-label="title"
        tabindex="-1"
        @keydown.esc="emit('close')"
      >
        <header class="modal-header">
          <h2 class="modal-title">{{ title }}</h2>
          <button class="modal-close" @click="emit('close')" aria-label="Close">✕</button>
        </header>

        <!-- APPLY MODE -->
        <div v-if="mode === 'apply'" class="modal-body">
          <div class="tpl-list" role="list" aria-label="Available templates">
            <button
              v-for="tpl in store.templates"
              :key="tpl.id"
              class="tpl-item"
              :class="{ 'tpl-item--selected': selectedId === tpl.id }"
              role="listitem"
              @click="selectTemplate(tpl)"
            >
              <span class="tpl-item__icon" aria-hidden="true">
                {{ tpl.is_builtin ? '🔒' : '📝' }}
              </span>
              <span class="tpl-item__title">{{ tpl.title }}</span>
              <span class="tpl-item__cat">{{ tpl.category }}</span>
            </button>
          </div>

          <div v-if="preview" class="tpl-preview">
            <p class="tpl-preview__subject" v-if="preview.subject">
              <strong>Subject:</strong> <span v-html="highlightTokens(preview.subject)" />
            </p>
            <pre class="tpl-preview__body" v-html="highlightTokens(preview.body)" />
            <div class="tpl-preview__actions">
              <button class="btn btn--primary" @click="copyPreview">Copy body</button>
              <button class="btn btn--ghost" @click="emit('close')">Cancel</button>
            </div>
          </div>
          <p v-else class="tpl-hint">Select a template to preview it with your job details.</p>
        </div>

        <!-- CREATE / EDIT MODE -->
        <form v-else class="modal-body" @submit.prevent="handleSubmit">
          <div class="field">
            <label class="field-label" for="tpl-title">Title *</label>
            <input id="tpl-title" v-model="form.title" type="text" class="field-input" required aria-required="true" />
          </div>
          <div class="field">
            <label class="field-label" for="tpl-category">Category</label>
            <select id="tpl-category" v-model="form.category" class="field-select">
              <option value="follow_up">Follow-up</option>
              <option value="thank_you">Thank you</option>
              <option value="accommodation">Accommodation request</option>
              <option value="withdrawal">Withdrawal</option>
              <option value="custom">Custom</option>
            </select>
          </div>
          <div class="field">
            <label class="field-label" for="tpl-subject">Subject template (optional)</label>
            <input id="tpl-subject" v-model="form.subject_template" type="text" class="field-input"
              placeholder="e.g. Following up — {{role}} application" />
          </div>
          <div class="field">
            <label class="field-label" for="tpl-body">Body template *</label>
            <p class="field-hint">Use <code>{{name}}</code>, <code>{{company}}</code>, <code>{{role}}</code>, <code>{{recruiter_name}}</code>, <code>{{date}}</code>, <code>{{accommodation_details}}</code></p>
            <textarea id="tpl-body" v-model="form.body_template" class="field-textarea" rows="8"
              required aria-required="true" />
          </div>
          <p v-if="error" class="modal-error" role="alert">{{ error }}</p>
          <footer class="modal-footer">
            <button type="button" class="btn btn--ghost" @click="emit('close')">Cancel</button>
            <button type="submit" class="btn btn--primary" :disabled="store.saving">
              {{ store.saving ? 'Saving…' : (mode === 'create' ? 'Create template' : 'Save changes') }}
            </button>
          </footer>
        </form>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { ref, computed, watch, nextTick } from 'vue'
import { useMessagingStore, type MessageTemplate } from '../stores/messaging'

const props = defineProps<{
  show: boolean
  mode: 'apply' | 'create' | 'edit'
  jobTokens?: Record<string, string>   // { name, company, role, recruiter_name, date }
  editTemplate?: MessageTemplate        // required when mode='edit'
}>()

const emit = defineEmits<{
  (e: 'close'): void
  (e: 'saved'): void
  (e: 'applied', body: string): void
}>()

const store = useMessagingStore()
const dialogEl = ref<HTMLElement | null>(null)
const selectedId = ref<number | null>(null)
const error = ref<string | null>(null)

const form = ref({
  title: '',
  category: 'custom',
  subject_template: '',
  body_template: '',
})

const title = computed(() => ({
  apply: 'Use a template',
  create: 'Create template',
  edit: 'Edit template',
}[props.mode]))

watch(() => props.show, async (val) => {
  if (!val) return
  error.value = null
  selectedId.value = null
  if (props.mode === 'edit' && props.editTemplate) {
    form.value = {
      title: props.editTemplate.title,
      category: props.editTemplate.category,
      subject_template: props.editTemplate.subject_template ?? '',
      body_template: props.editTemplate.body_template,
    }
  } else {
    form.value = { title: '', category: 'custom', subject_template: '', body_template: '' }
  }
  await nextTick()
  dialogEl.value?.focus()
})

function substituteTokens(text: string): string {
  const tokens = props.jobTokens ?? {}
  return text.replace(/\{\{(\w+)\}\}/g, (_, key) => tokens[key] ?? `{{${key}}}`)
}

function highlightTokens(text: string): string {
  // Remaining unresolved tokens are highlighted
  const escaped = text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
  return escaped.replace(
    /\{\{(\w+)\}\}/g,
    '<mark class="token-unresolved">{{$1}}</mark>'
  )
}

interface PreviewData { subject: string; body: string }

const preview = computed<PreviewData | null>(() => {
  if (props.mode !== 'apply' || selectedId.value === null) return null
  const tpl = store.templates.find(t => t.id === selectedId.value)
  if (!tpl) return null
  return {
    subject: substituteTokens(tpl.subject_template ?? ''),
    body: substituteTokens(tpl.body_template),
  }
})

function selectTemplate(tpl: MessageTemplate) {
  selectedId.value = tpl.id
}

function copyPreview() {
  if (!preview.value) return
  navigator.clipboard.writeText(preview.value.body)
  emit('applied', preview.value.body)
  emit('close')
}

async function handleSubmit() {
  error.value = null
  if (props.mode === 'create') {
    const result = await store.createTemplate({
      title: form.value.title,
      category: form.value.category,
      subject_template: form.value.subject_template || undefined,
      body_template: form.value.body_template,
    })
    if (result) emit('saved')
    else error.value = store.error ?? 'Save failed.'
  } else if (props.mode === 'edit' && props.editTemplate) {
    const result = await store.updateTemplate(props.editTemplate.id, {
      title: form.value.title,
      category: form.value.category,
      subject_template: form.value.subject_template || undefined,
      body_template: form.value.body_template,
    })
    if (result) emit('saved')
    else error.value = store.error ?? 'Save failed.'
  }
}
</script>

<style scoped>
.modal-backdrop {
  position: fixed; inset: 0;
  background: rgba(0,0,0,0.5);
  display: flex; align-items: center; justify-content: center;
  z-index: 200;
}
.modal-dialog {
  background: var(--color-surface-raised);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  width: min(560px, 95vw);
  max-height: 90vh;
  overflow-y: auto;
  outline: none;
}
.modal-dialog--wide { width: min(700px, 95vw); }
.modal-header {
  display: flex; align-items: center; justify-content: space-between;
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
.tpl-list { display: flex; flex-direction: column; gap: var(--space-1); max-height: 220px; overflow-y: auto; }
.tpl-item {
  display: flex; align-items: center; gap: var(--space-2);
  padding: var(--space-2) var(--space-3);
  border: 1px solid var(--color-border); border-radius: var(--radius-md);
  background: var(--color-surface-alt); cursor: pointer;
  text-align: left; width: 100%;
  transition: border-color 150ms, background 150ms;
}
.tpl-item:hover { border-color: var(--app-primary); background: var(--app-primary-light); }
.tpl-item--selected { border-color: var(--app-primary); background: var(--app-primary-light); font-weight: 600; }
.tpl-item__title { flex: 1; font-size: var(--text-sm); }
.tpl-item__cat { font-size: var(--text-xs); color: var(--color-text-muted); text-transform: capitalize; }
.tpl-preview { border: 1px solid var(--color-border); border-radius: var(--radius-md); padding: var(--space-4); background: var(--color-surface); }
.tpl-preview__subject { margin: 0 0 var(--space-2); font-size: var(--text-sm); }
.tpl-preview__body {
  font-size: var(--text-sm); white-space: pre-wrap; font-family: var(--font-body);
  margin: 0 0 var(--space-3); max-height: 200px; overflow-y: auto;
}
.tpl-preview__actions { display: flex; gap: var(--space-2); }
.tpl-hint { color: var(--color-text-muted); font-size: var(--text-sm); margin: 0; }
:global(.token-unresolved) {
  background: var(--app-accent-light, #fef3c7);
  color: var(--app-accent, #d97706);
  border-radius: 2px;
  padding: 0 2px;
}
.field { display: flex; flex-direction: column; gap: var(--space-1); }
.field-label { font-size: var(--text-sm); font-weight: 500; color: var(--color-text-muted); }
.field-hint { font-size: var(--text-xs); color: var(--color-text-muted); margin: 0; }
.field-input, .field-select, .field-textarea {
  padding: var(--space-2) var(--space-3);
  background: var(--color-surface-alt);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  color: var(--color-text); font-size: var(--text-sm); font-family: var(--font-body); width: 100%;
}
.field-input:focus-visible, .field-select:focus-visible, .field-textarea:focus-visible {
  outline: 2px solid var(--app-primary); outline-offset: 2px;
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
