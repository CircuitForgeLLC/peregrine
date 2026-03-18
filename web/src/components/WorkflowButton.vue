<template>
  <button
    class="workflow-btn"
    :class="{ 'workflow-btn--loading': loading }"
    :disabled="loading"
    :aria-busy="loading"
    v-bind="$attrs"
  >
    <span class="workflow-btn__icon" aria-hidden="true">{{ emoji }}</span>
    <span class="workflow-btn__body">
      <span class="workflow-btn__label">{{ label }}</span>
      <span class="workflow-btn__desc">{{ description }}</span>
    </span>
    <span v-if="loading" class="workflow-btn__spinner" aria-label="Running…" />
  </button>
</template>

<script setup lang="ts">
defineProps<{
  emoji:       string
  label:       string
  description: string
  loading?:    boolean
}>()
</script>

<style scoped>
.workflow-btn {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-4) var(--space-5);
  background: var(--color-surface-raised);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  cursor: pointer;
  text-align: left;
  min-height: 72px;   /* WCAG 2.5.5 */
  width: 100%;
  /* Enumerate transitions — no transition:all. Gotcha #2. */
  transition:
    background   150ms ease,
    border-color 150ms ease,
    box-shadow   150ms ease,
    transform    150ms ease;
}

.workflow-btn:hover {
  background: var(--app-primary-light);
  border-color: var(--app-primary);
  box-shadow: var(--shadow-sm);
  transform: translateY(-1px);
}

.workflow-btn:disabled {
  opacity: 0.7;
  cursor: not-allowed;
  transform: none;
}

.workflow-btn__icon {
  font-size: 1.5rem;
  flex-shrink: 0;
}

.workflow-btn__body {
  display: flex;
  flex-direction: column;
  gap: 2px;
  flex: 1;
  min-width: 0;
}

.workflow-btn__label {
  font-size: var(--text-sm);
  font-weight: 700;
  color: var(--color-text);
}

.workflow-btn__desc {
  font-size: var(--text-xs);
  color: var(--color-text-muted);
}

.workflow-btn__spinner {
  width: 1.1rem;
  height: 1.1rem;
  border: 2px solid var(--color-border);
  border-top-color: var(--app-primary);
  border-radius: 50%;
  animation: spin 0.7s linear infinite;
  flex-shrink: 0;
}

@keyframes spin { to { transform: rotate(360deg); } }
</style>
