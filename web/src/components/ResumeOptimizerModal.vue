<template>
  <Teleport to="body">
    <div class="modal-backdrop" role="dialog" aria-modal="true" :aria-labelledby="`rop-modal-title-${jobId}`" @click.self="emit('close')">
      <div class="modal-card">
        <div class="modal-header">
          <h2 :id="`rop-modal-title-${jobId}`" class="modal-title">🎯 Resume Optimizer</h2>
          <div class="modal-header-actions">
            <button class="btn-close" @click="emit('close')" aria-label="Close">✕</button>
          </div>
        </div>

        <div class="modal-body">
          <ResumeOptimizerPanel :job-id="jobId" />
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { onMounted, onUnmounted } from 'vue'
import ResumeOptimizerPanel from './ResumeOptimizerPanel.vue'

defineProps<{ jobId: number }>()
const emit = defineEmits<{ close: [] }>()

function onEsc(e: KeyboardEvent) {
  if (e.key === 'Escape') emit('close')
}

onMounted(() => document.addEventListener('keydown', onEsc))
onUnmounted(() => document.removeEventListener('keydown', onEsc))
</script>

<style scoped>
.modal-backdrop {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.55);
  z-index: 500;
  display: flex;
  align-items: flex-start;
  justify-content: center;
  padding: var(--space-8) var(--space-4);
  overflow-y: auto;
}

.modal-card {
  background: var(--color-surface-raised);
  border-radius: var(--radius-lg);
  box-shadow: 0 8px 40px rgba(0, 0, 0, 0.3);
  width: 100%;
  max-width: 680px;
  overflow: hidden;
}

.modal-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--space-3);
  padding: var(--space-5) var(--space-6);
  border-bottom: 1px solid var(--color-border-light);
}

.modal-title {
  font-size: 1rem;
  font-weight: 700;
  color: var(--color-text);
  margin: 0;
  line-height: 1.3;
}

.modal-header-actions {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  flex-shrink: 0;
}

.btn-close {
  background: none;
  border: none;
  cursor: pointer;
  font-size: 1rem;
  color: var(--color-text-muted);
  padding: 2px 6px;
}

.modal-body {
  padding: var(--space-6);
  max-height: 75vh;
  overflow-y: auto;
}
</style>
