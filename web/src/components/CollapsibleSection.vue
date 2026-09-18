<template>
  <div class="collapsible-section">
    <button
      class="collapsible-section__toggle"
      :aria-expanded="expanded"
      @click="toggle"
    >
      <span class="collapsible-section__label">{{ title }}</span>
      <span v-if="badge !== null && badge !== undefined" class="collapsible-section__badge">{{ badge }}</span>
      <span class="collapsible-section__icon" aria-hidden="true">{{ expanded ? '▲' : '▼' }}</span>
    </button>
    <div v-if="expanded" class="collapsible-section__body">
      <slot />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useStorage } from '@vueuse/core'

const props = withDefaults(defineProps<{
  title: string
  badge?: string | number | null
  /** Controlled mode: parent owns the expanded state (e.g. dynamic
   *  auto-expand-on-data logic). Ignored when persistId is set. */
  modelValue?: boolean
  /** Uncontrolled mode: this component owns and persists the expanded
   *  state to localStorage itself, keyed by this string. Takes priority
   *  over modelValue when both are given. */
  persistId?: string
  defaultExpanded?: boolean
}>(), {
  badge: null,
  modelValue: undefined,
  persistId: undefined,
  defaultExpanded: false,
})

const emit = defineEmits<{ 'update:modelValue': [value: boolean] }>()

const persisted = props.persistId ? useStorage(props.persistId, props.defaultExpanded) : null

const expanded = computed<boolean>({
  get: () => persisted ? persisted.value : (props.modelValue ?? props.defaultExpanded),
  set: (value) => {
    if (persisted) persisted.value = value
    emit('update:modelValue', value)
  },
})

function toggle() {
  expanded.value = !expanded.value
}
</script>

<style scoped>
.collapsible-section {
  background: var(--color-surface-raised);
  border: 1px solid var(--color-border-light);
  border-radius: var(--radius-lg);
  overflow: hidden;
}

.collapsible-section__toggle {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  width: 100%;
  padding: var(--space-3) var(--space-4);
  background: none;
  border: none;
  cursor: pointer;
  color: var(--color-text);
}

.collapsible-section__toggle:hover {
  background: var(--color-surface-alt);
}

.collapsible-section__label {
  font-size: var(--text-xs);
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  flex: 1;
  text-align: left;
}

.collapsible-section__badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  background: var(--app-primary-light);
  color: var(--app-primary);
  font-size: 10px;
  font-weight: 700;
}

.collapsible-section__icon {
  font-size: var(--text-xs);
}

.collapsible-section__body {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  padding: var(--space-4);
  border-top: 1px solid var(--color-border-light);
}
</style>
