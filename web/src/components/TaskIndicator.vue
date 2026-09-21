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
</template>

<script setup lang="ts">
import { onMounted, onUnmounted } from 'vue'
import { useTasksStore, TASK_LABEL } from '../stores/tasks'
import { storeToRefs } from 'pinia'

const store = useTasksStore()
const { count, groups } = storeToRefs(store)

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

@keyframes task-spin {
  to { transform: rotate(360deg); }
}

/* ── Desktop sidebar variant — the only variant this component renders now.
   The mobile pill variant moved to MobileTaskPill.vue, mounted as a sibling
   of the mobile tab bar in AppNav.vue instead of nested in here -- being
   nested inside .app-sidebar (display:none on mobile) made it unreachable. ── */
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

/* ── Responsive ─────────────────────────────────────── */
@media (max-width: 1023px) {
  .task-indicator--sidebar { display: none; }
}
</style>
