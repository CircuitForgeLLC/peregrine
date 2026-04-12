<template>
  <div class="rp-confirm">
    <h3 class="rp__heading">Ready to preview?</h3>
    <p class="rp__hint">Here's a summary of your decisions. Click Preview to assemble the resume.</p>
    <ul class="rp-confirm__list">
      <li v-for="page in pages" :key="page.id" class="rp-confirm__item">
        <span class="tab__dot" :class="`tab__dot--${tabStatus(page)}`" aria-hidden="true" />
        <span>{{ page.label }}</span>
        <span class="rp-confirm__status">{{ tabStatus(page) }}</span>
      </li>
    </ul>
    <p v-if="error" class="rp__error" role="alert">{{ error }}</p>
    <div class="rp-confirm__actions">
      <button class="btn-generate" :disabled="submitting" @click="emit('preview')">
        <span aria-hidden="true">👁️</span>
        {{ submitting ? 'Generating…' : 'Preview Full Resume' }}
      </button>
      <button class="btn-secondary" @click="emit('rewrite')">
        <span aria-hidden="true">🔄</span> Rewrite again
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
interface PageRef {
  id: string
  type: string
  label: string
  entryKey?: string
}

defineProps<{
  pages: PageRef[]
  tabStatus: (page: PageRef) => string
  submitting: boolean
  error: string
}>()

const emit = defineEmits<{
  preview: []
  rewrite: []
}>()
</script>

<style scoped>
.rp-confirm { display: flex; flex-direction: column; gap: var(--space-4, 1rem); }
.rp__heading { font-size: var(--font-lg, 1.125rem); font-weight: 600; margin: 0; color: var(--color-text, #1a2338); }
.rp__hint { font-size: var(--font-sm, 0.875rem); color: var(--color-text-muted, #4a5c7a); margin: 0; }
.rp-confirm__list { list-style: none; padding: 0; margin: 0; display: flex; flex-direction: column; gap: var(--space-2, 0.5rem); }
.rp-confirm__item { display: flex; align-items: center; gap: var(--space-3, 0.75rem); padding: var(--space-2, 0.5rem) var(--space-3, 0.75rem); background: var(--color-surface-alt, #dde4f0); border-radius: var(--radius-sm, 0.25rem); font-size: var(--font-sm, 0.875rem); }
.rp-confirm__status { margin-left: auto; font-size: var(--font-xs, 0.75rem); color: var(--color-text-muted, #4a5c7a); text-transform: capitalize; }
.rp__error { color: var(--color-error, #c0392b); font-size: var(--font-sm, 0.875rem); margin: 0; }
.rp-confirm__actions { display: flex; gap: var(--space-3, 0.75rem); flex-wrap: wrap; }
.tab__dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; background: var(--tab-color, #94a3b8); }
.tab__dot--unvisited   { --tab-color: var(--color-text-muted, #94a3b8); }
.tab__dot--in-progress { --tab-color: var(--color-accent, #c4732a); }
.tab__dot--accepted    { --tab-color: var(--color-success, #3a7a32); }
.tab__dot--partial     { --tab-color: var(--color-warning, #d4891a); }
.tab__dot--skipped     { --tab-color: var(--color-border, #a8b8d0); }

.btn-generate {
  display: inline-flex; align-items: center; gap: var(--space-2, 0.5rem);
  padding: var(--space-3, 0.75rem) var(--space-4, 1rem);
  background: var(--color-accent, #c4732a); color: #fff;
  border: none; border-radius: var(--radius-md, 0.5rem);
  font-size: var(--font-sm, 0.875rem); font-weight: 600; cursor: pointer;
}
.btn-generate:disabled { opacity: 0.6; cursor: not-allowed; }
.btn-secondary {
  display: inline-flex; align-items: center; gap: var(--space-2, 0.5rem);
  padding: var(--space-3, 0.75rem) var(--space-4, 1rem);
  background: var(--color-surface-alt, #dde4f0); color: var(--color-text, #1a2338);
  border: 1px solid var(--color-border, #a8b8d0); border-radius: var(--radius-md, 0.5rem);
  font-size: var(--font-sm, 0.875rem); font-weight: 600; cursor: pointer;
}
</style>
