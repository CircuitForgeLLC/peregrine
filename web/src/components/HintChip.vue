<template>
  <div v-if="!dismissed" class="hint-chip" role="status">
    <span aria-hidden="true" class="hint-chip__icon">💡</span>
    <span class="hint-chip__message">{{ message }}</span>
    <button
      class="hint-chip__dismiss"
      @click="dismiss"
      :aria-label="`Dismiss hint for ${viewKey}`"
    >✕</button>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'

const props = defineProps<{
  viewKey: string  // used for localStorage key — e.g. 'home', 'review'
  message: string
}>()

const LS_KEY = `peregrine_hint_${props.viewKey}`
const dismissed = ref(!!localStorage.getItem(LS_KEY))

function dismiss(): void {
  localStorage.setItem(LS_KEY, '1')
  dismissed.value = true
}
</script>

<style scoped>
.hint-chip {
  display: flex;
  align-items: flex-start;
  gap: var(--space-2, 8px);
  background: var(--color-surface, #0d1829);
  border: 1px solid var(--app-primary, #2B6CB0);
  border-radius: var(--radius-md, 8px);
  padding: var(--space-2, 8px) var(--space-3, 12px);
  margin-bottom: var(--space-3, 12px);
}

.hint-chip__icon { flex-shrink: 0; font-size: 0.9rem; }

.hint-chip__message {
  flex: 1;
  font-size: 0.85rem;
  color: var(--color-text, #1a202c);
  line-height: 1.4;
}

.hint-chip__dismiss {
  flex-shrink: 0;
  background: none;
  border: none;
  color: var(--color-text-muted, #8898aa);
  cursor: pointer;
  font-size: 0.75rem;
  padding: 0 2px;
  line-height: 1;
}

.hint-chip__dismiss:hover { color: var(--color-text, #eaeff8); }
</style>
