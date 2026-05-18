<template>
  <div class="rp-summary">
    <h3 class="rp__heading">Summary</h3>
    <div class="rp__diff-pair">
      <div class="rp__diff-col">
        <span class="rp__diff-label" aria-label="Original">Original</span>
        <p class="rp__diff-text">{{ section.original || '(empty)' }}</p>
      </div>
      <div class="rp__diff-col rp__diff-col--editable">
        <span class="rp__diff-label" aria-label="Proposed — editable">Proposed</span>
        <textarea
          class="rp__edit-textarea"
          :value="editedProposed"
          :aria-label="`Edit proposed summary`"
          spellcheck="true"
          @input="emit('update:editedProposed', ($event.target as HTMLTextAreaElement).value)"
        />
      </div>
    </div>
    <label class="rp__accept-toggle">
      <input
        type="checkbox"
        :checked="accepted"
        @change="emit('update:accepted', ($event.target as HTMLInputElement).checked)"
      />
      Accept proposed summary
    </label>
  </div>
</template>

<script setup lang="ts">
import type { TextDiff } from '../ResumeReviewModal.vue'

defineProps<{
  section: TextDiff
  accepted: boolean
  editedProposed: string
}>()

const emit = defineEmits<{
  'update:accepted': [v: boolean]
  'update:editedProposed': [v: string]
}>()
</script>

<style scoped>
.rp-summary { display: flex; flex-direction: column; gap: var(--space-4, 1rem); }
.rp__heading { font-size: var(--font-lg, 1.125rem); font-weight: 600; margin: 0; color: var(--color-text, #1a2338); }
.rp__diff-pair { display: grid; grid-template-columns: 1fr 1fr; gap: var(--space-4, 1rem); }
@media (max-width: 600px) { .rp__diff-pair { grid-template-columns: 1fr; } }
.rp__diff-col { display: flex; flex-direction: column; gap: var(--space-2, 0.5rem); }
.rp__diff-col--editable { gap: var(--space-2, 0.5rem); }
.rp__diff-label { font-size: var(--font-xs, 0.75rem); font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em; color: var(--color-text-muted, #4a5c7a); }
.rp__diff-text { font-size: var(--text-sm); line-height: 1.6; padding: var(--space-3, 0.75rem); background: var(--color-surface-alt, #dde4f0); border-radius: var(--radius-sm, 0.25rem); margin: 0; }
.rp__edit-textarea {
  font-size: var(--text-sm);
  line-height: 1.6;
  padding: var(--space-3, 0.75rem);
  background: var(--color-surface, #eaeff8);
  border: 1.5px solid var(--color-accent, #c4732a);
  border-radius: var(--radius-sm, 0.25rem);
  color: var(--color-text, #1a2338);
  resize: vertical;
  min-height: 7rem;
  width: 100%;
  box-sizing: border-box;
  font-family: inherit;
}
.rp__edit-textarea:focus { outline: 2px solid var(--color-accent, #c4732a); outline-offset: 2px; }
.rp__accept-toggle { display: inline-flex; align-items: center; gap: var(--space-2, 0.5rem); cursor: pointer; font-size: var(--text-sm); }
</style>
