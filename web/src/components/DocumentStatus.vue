<template>
  <ul class="doc-status" :class="{ 'doc-status--compact': compact }" role="list">
    <li
      v-for="item in items"
      :key="item.key"
      class="doc-status__item"
      :class="item.done ? 'doc-status__item--done' : 'doc-status__item--pending'"
      role="listitem"
    >
      <template v-if="compact">
        <span aria-hidden="true">{{ item.short }} {{ item.done ? '✓' : '○' }}</span>
        <span class="sr-only">{{ item.full }}</span>
      </template>
      <template v-else>
        <span aria-hidden="true" class="doc-status__mark">{{ item.done ? '✓' : '○' }}</span>
        <span>{{ item.full }}</span>
      </template>
    </li>
  </ul>
</template>

<script setup lang="ts">
import { computed } from 'vue'

// A generated cover letter and an approved tailored resume are two separate statuses, so a job
// with only a letter never looks finished (peregrine#256). Done and pending differ by symbol and
// wording as well as colour.
const props = defineProps<{
  hasLetter: boolean
  hasResume: boolean
  /** Short on-screen text for narrow layouts. The full wording stays available to screen readers. */
  compact?: boolean
}>()

const items = computed(() => [
  {
    key: 'letter',
    short: 'Letter',
    done: props.hasLetter,
    full: props.hasLetter ? 'Letter drafted' : 'No letter',
  },
  {
    key: 'resume',
    short: 'Resume',
    done: props.hasResume,
    full: props.hasResume ? 'Resume tailored' : 'Resume not tailored',
  },
])
</script>

<style scoped>
.doc-status {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-1);
  margin: 0;
  padding: 0;
  list-style: none;
}
.doc-status__item {
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
  padding: 1px var(--space-2);
  border-radius: 999px;
  font-size: var(--text-xs);
  font-weight: 600;
  white-space: nowrap;
}
.doc-status__item--done {
  background: rgba(39, 174, 96, 0.10);
  color: var(--color-success);
}
.doc-status__item--pending {
  background: var(--color-surface-alt);
  color: var(--color-text-muted);
}
.doc-status--compact .doc-status__item {
  padding: 0;
  background: none;
  font-weight: 500;
}
.doc-status--compact .doc-status__item--done {
  font-weight: 700;
}
</style>
