<template>
  <Teleport to="body">
    <div v-if="show" class="sync-modal__overlay" role="dialog" aria-modal="true"
         aria-labelledby="sync-modal-title" @keydown.esc="$emit('cancel')">
      <div class="sync-modal">
        <h2 id="sync-modal-title" class="sync-modal__title">Replace profile content?</h2>

        <div class="sync-modal__comparison">
          <div class="sync-modal__col sync-modal__col--before">
            <div class="sync-modal__col-label">Current profile</div>
            <div class="sync-modal__col-name">{{ currentSummary.name || '(no name)' }}</div>
            <div class="sync-modal__col-summary">{{ currentSummary.careerSummary || '(no summary)' }}</div>
            <div class="sync-modal__col-role">{{ currentSummary.latestRole || '(no experience)' }}</div>
          </div>
          <div class="sync-modal__arrow" aria-hidden="true">→</div>
          <div class="sync-modal__col sync-modal__col--after">
            <div class="sync-modal__col-label">Replacing with</div>
            <div class="sync-modal__col-name">{{ sourceSummary.name || '(no name)' }}</div>
            <div class="sync-modal__col-summary">{{ sourceSummary.careerSummary || '(no summary)' }}</div>
            <div class="sync-modal__col-role">{{ sourceSummary.latestRole || '(no experience)' }}</div>
          </div>
        </div>

        <div v-if="blankFields.length" class="sync-modal__blank-warning">
          <strong>Fields that will be blank after import:</strong>
          <ul>
            <li v-for="f in blankFields" :key="f">{{ f }}</li>
          </ul>
          <p class="sync-modal__blank-note">You can fill these in after importing.</p>
        </div>

        <p class="sync-modal__preserve-note">
          Your salary, work preferences, and contact details are not affected.
        </p>

        <div class="sync-modal__actions">
          <button class="btn-secondary" @click="$emit('cancel')">Keep current profile</button>
          <button class="btn-danger" @click="$emit('confirm')">Replace profile content</button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
interface ContentSummary {
  name: string
  careerSummary: string
  latestRole: string
}

defineProps<{
  show: boolean
  currentSummary: ContentSummary
  sourceSummary: ContentSummary
  blankFields: string[]
}>()

defineEmits<{
  confirm: []
  cancel: []
}>()
</script>

<style scoped>
.sync-modal__overlay {
  position: fixed; inset: 0; z-index: 1000;
  background: rgba(0,0,0,0.5);
  display: flex; align-items: center; justify-content: center;
  padding: var(--space-4);
}
.sync-modal {
  background: var(--color-surface-raised);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg, 0.75rem);
  padding: var(--space-6);
  max-width: 600px; width: 100%;
  max-height: 90vh; overflow-y: auto;
}
.sync-modal__title {
  font-size: 1.15rem; font-weight: 700;
  margin-bottom: var(--space-5);
  color: var(--color-text);
}
.sync-modal__comparison {
  display: grid; grid-template-columns: 1fr auto 1fr; gap: var(--space-3);
  align-items: start; margin-bottom: var(--space-5);
}
.sync-modal__arrow {
  font-size: 1.5rem; color: var(--color-text-muted);
  padding-top: var(--space-5);
}
.sync-modal__col {
  background: var(--color-surface-alt);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  padding: var(--space-3);
}
.sync-modal__col--after { border-color: var(--color-primary); }
.sync-modal__col-label {
  font-size: 0.75rem; font-weight: 600; color: var(--color-text-muted);
  text-transform: uppercase; letter-spacing: 0.05em;
  margin-bottom: var(--space-2);
}
.sync-modal__col-name { font-weight: 600; color: var(--color-text); margin-bottom: var(--space-1); }
.sync-modal__col-summary {
  font-size: 0.82rem; color: var(--color-text-muted);
  overflow: hidden; display: -webkit-box;
  -webkit-line-clamp: 2; -webkit-box-orient: vertical;
  margin-bottom: var(--space-1);
}
.sync-modal__col-role { font-size: 0.82rem; color: var(--color-text-muted); font-style: italic; }
.sync-modal__blank-warning {
  background: color-mix(in srgb, var(--color-warning, #d97706) 10%, var(--color-surface-alt));
  border: 1px solid color-mix(in srgb, var(--color-warning, #d97706) 30%, var(--color-border));
  border-radius: var(--radius-md); padding: var(--space-3);
  margin-bottom: var(--space-4);
  font-size: 0.85rem;
}
.sync-modal__blank-warning ul { margin: var(--space-2) 0 0 var(--space-4); }
.sync-modal__blank-note { margin-top: var(--space-2); color: var(--color-text-muted); }
.sync-modal__preserve-note {
  font-size: 0.82rem; color: var(--color-text-muted);
  margin-bottom: var(--space-5);
}
.sync-modal__actions {
  display: flex; gap: var(--space-3); justify-content: flex-end; flex-wrap: wrap;
}
.btn-danger {
  padding: var(--space-2) var(--space-4);
  background: var(--color-error, #dc2626);
  color: #fff; border: none;
  border-radius: var(--radius-md); cursor: pointer;
  font-size: var(--text-sm); font-weight: 600;
}
.btn-danger:hover { filter: brightness(1.1); }
.btn-secondary {
  padding: var(--space-2) var(--space-4);
  background: transparent;
  color: var(--color-text);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md); cursor: pointer;
  font-size: var(--text-sm);
}
.btn-secondary:hover { background: var(--color-surface-alt); }
</style>
