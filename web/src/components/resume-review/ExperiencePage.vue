<template>
  <div class="rp-exp">
    <h3 class="rp__heading">{{ entry.title }}</h3>
    <p class="rp__company">{{ entry.company }}</p>
    <div class="rp__diff-pair">
      <div class="rp__diff-col">
        <span class="rp__diff-label">Original</span>
        <ul class="rp__bullet-list">
          <li v-for="b in entry.original_bullets" :key="b">{{ b }}</li>
        </ul>
      </div>
      <div class="rp__diff-col rp__diff-col--editable">
        <span class="rp__diff-label">Proposed — edit below</span>
        <div class="rp__bullet-edit-list" role="list" :aria-label="`Edit proposed bullets for ${entry.title}`">
          <div
            v-for="(bullet, idx) in editedBullets"
            :key="idx"
            class="rp__bullet-edit-row"
            role="listitem"
          >
            <textarea
              class="rp__bullet-textarea"
              :value="bullet"
              :aria-label="`Bullet ${idx + 1}`"
              rows="2"
              spellcheck="true"
              @input="updateBullet(idx, ($event.target as HTMLTextAreaElement).value)"
            />
          </div>
        </div>
      </div>
    </div>
    <label class="rp__accept-toggle">
      <input
        type="checkbox"
        :checked="accepted"
        @change="emit('update:accepted', ($event.target as HTMLInputElement).checked)"
      />
      Accept proposed bullets
    </label>
  </div>
</template>

<script setup lang="ts">
const props = defineProps<{
  entry: {
    title: string
    company: string
    original_bullets: string[]
    proposed_bullets: string[]
  }
  accepted: boolean
  editedBullets: string[]
}>()

const emit = defineEmits<{
  'update:accepted': [v: boolean]
  'update:editedBullets': [v: string[]]
}>()

function updateBullet(idx: number, value: string) {
  const next = props.editedBullets.map((b, i) => (i === idx ? value : b))
  emit('update:editedBullets', next)
}
</script>

<style scoped>
.rp-exp { display: flex; flex-direction: column; gap: var(--space-4, 1rem); }
.rp__heading { font-size: var(--font-lg, 1.125rem); font-weight: 600; margin: 0; color: var(--color-text, #1a2338); }
.rp__company { font-size: var(--font-sm, 0.875rem); color: var(--color-text-muted, #4a5c7a); margin: 0; }
.rp__diff-pair { display: grid; grid-template-columns: 1fr 1fr; gap: var(--space-4, 1rem); }
@media (max-width: 600px) { .rp__diff-pair { grid-template-columns: 1fr; } }
.rp__diff-col { display: flex; flex-direction: column; gap: var(--space-2, 0.5rem); }
.rp__diff-col--editable { gap: var(--space-2, 0.5rem); }
.rp__diff-label { font-size: var(--font-xs, 0.75rem); font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em; color: var(--color-text-muted, #4a5c7a); }
.rp__bullet-list { margin: 0; padding-left: var(--space-4, 1rem); font-size: var(--font-sm, 0.875rem); line-height: 1.6; background: var(--color-surface-alt, #dde4f0); border-radius: var(--radius-sm, 0.25rem); padding: var(--space-3, 0.75rem) var(--space-3, 0.75rem) var(--space-3, 0.75rem) var(--space-6, 1.5rem); }
.rp__bullet-edit-list { display: flex; flex-direction: column; gap: var(--space-2, 0.5rem); }
.rp__bullet-edit-row { display: flex; align-items: flex-start; gap: var(--space-1, 0.25rem); }
.rp__bullet-textarea {
  flex: 1;
  font-size: var(--font-sm, 0.875rem);
  line-height: 1.5;
  padding: var(--space-2, 0.5rem) var(--space-3, 0.75rem);
  background: var(--color-surface, #eaeff8);
  border: 1.5px solid var(--color-accent, #c4732a);
  border-radius: var(--radius-sm, 0.25rem);
  color: var(--color-text, #1a2338);
  resize: vertical;
  width: 100%;
  box-sizing: border-box;
  font-family: inherit;
}
.rp__bullet-textarea:focus { outline: 2px solid var(--color-accent, #c4732a); outline-offset: 2px; }
.rp__accept-toggle { display: inline-flex; align-items: center; gap: var(--space-2, 0.5rem); cursor: pointer; font-size: var(--font-sm, 0.875rem); }
</style>
