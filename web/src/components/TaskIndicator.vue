<template>
  <!-- Desktop: inline queue in sidebar footer -->
  <div v-if="count > 0" class="task-indicator task-indicator--sidebar" aria-live="polite" role="status">
    <template v-for="group in groups" :key="group.primary.id">
      <!-- Primary task row -->
      <div class="task-row task-row--primary">
        <span class="task-row__spinner" :class="`task-row__spinner--${group.primary.status}`" aria-hidden="true" />
        <span class="task-row__label">{{ TASK_LABEL[group.primary.task_type] ?? group.primary.task_type }}</span>
        <span class="task-row__status">{{ group.primary.status }}</span>
      </div>
      <!-- Pipeline sub-steps (indented) -->
      <div
        v-for="step in group.steps"
        :key="step.id"
        class="task-row task-row--step"
        :class="`task-row--${step.status}`"
      >
        <span class="task-row__indent" aria-hidden="true">↳</span>
        <span class="task-row__spinner" :class="`task-row__spinner--${step.status}`" aria-hidden="true" />
        <span class="task-row__label">{{ TASK_LABEL[step.task_type] ?? step.task_type }}</span>
        <span class="task-row__status">{{ step.status }}</span>
      </div>
    </template>
  </div>

  <!-- Mobile: fixed pill above bottom tab bar (compact — keeps existing design) -->
  <Transition name="task-pill">
    <div
      v-if="count > 0"
      class="task-indicator task-indicator--pill"
      aria-live="polite"
      role="status"
    >
      <span class="task-indicator__spinner" aria-hidden="true" />
      <span class="task-indicator__label">{{ label }}</span>
      <span class="task-indicator__badge">{{ count }}</span>
    </div>
  </Transition>
</template>

<script setup lang="ts">
import { onMounted, onUnmounted } from 'vue'
import { useTasksStore, TASK_LABEL } from '../stores/tasks'
import { storeToRefs } from 'pinia'

const store = useTasksStore()
const { count, groups, label } = storeToRefs(store)

onMounted(store.startPolling)
onUnmounted(store.stopPolling)
</script>

<style scoped>
/* ── Shared ─────────────────────────────────────────── */
.task-indicator {
  display: flex;
  align-items: center;
  gap: var(--space-2);
}

/* Spinner — CSS-only rotating ring */
.task-indicator__spinner {
  flex-shrink: 0;
  width: 14px;
  height: 14px;
  border: 2px solid color-mix(in srgb, var(--app-primary) 30%, transparent);
  border-top-color: var(--app-primary);
  border-radius: 50%;
  animation: task-spin 0.8s linear infinite;
}

@keyframes task-spin {
  to { transform: rotate(360deg); }
}

.task-indicator__label {
  flex: 1;
  font-size: var(--text-xs);
  color: var(--color-text-muted);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.task-indicator__badge {
  font-size: var(--text-xs);
  font-weight: 700;
  background: var(--app-primary);
  color: white;
  border-radius: var(--radius-full);
  min-width: 18px;
  height: 18px;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0 4px;
}

/* ── Desktop sidebar variant — shown by the sidebar, hidden on mobile ── */
.task-indicator--sidebar {
  padding: var(--space-2) var(--space-4);
  border-top: 1px solid var(--color-border-light);
  flex-direction: column;
  gap: var(--space-1);
  align-items: stretch;
}

/* ── Task rows ─────────────────────────────────────── */
.task-row {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  min-height: 26px;
}

.task-row--primary { padding: var(--space-1) 0; }

.task-row--step {
  padding-left: var(--space-3);
  opacity: 0.75;
}

.task-row--queued { opacity: 0.5; }

.task-row__indent {
  font-size: var(--text-xs);
  color: var(--color-text-muted);
  flex-shrink: 0;
  line-height: 1;
}

.task-row__spinner {
  flex-shrink: 0;
  width: 10px;
  height: 10px;
  border-radius: 50%;
}

.task-row__spinner--running {
  border: 1.5px solid color-mix(in srgb, var(--app-primary) 30%, transparent);
  border-top-color: var(--app-primary);
  animation: task-spin 0.8s linear infinite;
}

.task-row__spinner--queued {
  border: 1.5px solid var(--color-border);
  background: transparent;
}

.task-row__label {
  flex: 1;
  font-size: var(--text-xs);
  color: var(--color-text-muted);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.task-row__status {
  font-size: 9px;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--color-text-muted);
  opacity: 0.6;
  flex-shrink: 0;
}

/* ── Mobile pill variant — fixed above tab bar ─────── */
.task-indicator--pill {
  position: fixed;
  left: 50%;
  transform: translateX(-50%);
  bottom: calc(56px + env(safe-area-inset-bottom) + var(--space-2));
  background: var(--color-surface-raised);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-full);
  padding: var(--space-1) var(--space-3);
  box-shadow: 0 2px 8px rgba(0,0,0,0.15);
  z-index: 200;
  pointer-events: none;
  /* hidden on desktop, shown on mobile */
  display: none;
}

/* ── Responsive ─────────────────────────────────────── */
@media (max-width: 1023px) {
  .task-indicator--sidebar { display: none; }
  .task-indicator--pill    { display: flex; }
}

@media (min-width: 1024px) {
  .task-indicator--pill { display: none; }
}

/* ── Transition (pill slide-up) ─────────────────────── */
.task-pill-enter-active,
.task-pill-leave-active {
  transition: opacity 200ms ease, transform 200ms ease;
}
.task-pill-enter-from,
.task-pill-leave-to {
  opacity: 0;
  transform: translateX(-50%) translateY(8px);
}
</style>
