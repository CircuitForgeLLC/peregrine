<template>
  <Transition name="task-pill">
    <div
      v-if="count > 0"
      class="mobile-task-pill"
      aria-live="polite"
      role="status"
    >
      <span class="mobile-task-pill__spinner" aria-hidden="true" />
      <span class="mobile-task-pill__label">{{ label }}</span>
      <span class="mobile-task-pill__badge">{{ count }}</span>
    </div>
  </Transition>
</template>

<script setup lang="ts">
import { storeToRefs } from 'pinia'
import { useTasksStore } from '../stores/tasks'

// Reads the same shared task store TaskIndicator (in the desktop sidebar)
// already polls -- this component doesn't start/stop polling itself, it
// just renders the mobile-only pill variant of the same live state.
const { count, label } = storeToRefs(useTasksStore())
</script>

<style scoped>
.mobile-task-pill {
  position: fixed;
  left: 50%;
  transform: translateX(-50%);
  bottom: calc(56px + env(safe-area-inset-bottom) + var(--space-2));
  display: flex;
  align-items: center;
  gap: var(--space-2);
  background: var(--color-surface-raised);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-full);
  padding: var(--space-1) var(--space-3);
  box-shadow: 0 2px 8px rgba(0,0,0,0.15);
  z-index: 200;
  pointer-events: none;
}

.mobile-task-pill__spinner {
  flex-shrink: 0;
  width: 14px;
  height: 14px;
  border: 2px solid color-mix(in srgb, var(--app-primary) 30%, transparent);
  border-top-color: var(--app-primary);
  border-radius: 50%;
  animation: mobile-task-pill-spin 0.8s linear infinite;
}

@keyframes mobile-task-pill-spin {
  to { transform: rotate(360deg); }
}

.mobile-task-pill__label {
  flex: 1;
  font-size: var(--text-xs);
  color: var(--color-text-muted);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.mobile-task-pill__badge {
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

/* Desktop never shows this -- it's only mounted as a sibling of the mobile
   tab bar in AppNav.vue, but guard with display:none too in case that
   changes later. */
@media (min-width: 1024px) {
  .mobile-task-pill { display: none; }
}

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
