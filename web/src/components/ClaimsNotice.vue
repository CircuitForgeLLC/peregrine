<template>
  <section v-if="hasContent" class="cn" aria-labelledby="cn-heading">
    <h3 id="cn-heading" class="cn__heading">A few things to check</h3>

    <div v-if="novel.shown.length" class="cn__group">
      <p class="cn__intro">
        These words are in the rewritten resume but not in your original resume or your saved answers.
        Please check that each one is true for you. Some may just be rewordings.
      </p>
      <ul class="cn__list">
        <li v-for="w in novel.shown" :key="w">{{ w }}</li>
      </ul>
      <p v-if="novel.more" class="cn__more">and {{ novel.more }} more</p>
    </div>

    <div v-if="unused.shown.length" class="cn__group">
      <p class="cn__intro">These keywords were not used, because you said No, kept your answer private, skipped them, or have not answered yet.</p>
      <ul class="cn__list">
        <li v-for="t in unused.shown" :key="t">{{ t }}</li>
      </ul>
      <p v-if="unused.more" class="cn__more">and {{ unused.more }} more</p>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const MAX_SHOWN = 20

const props = defineProps<{
  novelWords: string[]
  unusedTerms: string[]
}>()

function clean(value: unknown): string[] {
  if (!Array.isArray(value)) return []
  const seen = new Set<string>()
  for (const item of value) {
    if (typeof item !== 'string') continue
    const text = item.trim()
    if (text) seen.add(text)
  }
  return [...seen]
}

function limited(value: unknown) {
  const all = clean(value)
  return { shown: all.slice(0, MAX_SHOWN), more: Math.max(0, all.length - MAX_SHOWN) }
}

const novel = computed(() => limited(props.novelWords))
const unused = computed(() => limited(props.unusedTerms))
const hasContent = computed(() => novel.value.shown.length > 0 || unused.value.shown.length > 0)
</script>

<style scoped>
.cn { display: flex; flex-direction: column; gap: var(--space-3); padding: var(--space-4); border: 1px solid var(--color-border); border-radius: var(--radius-md); background: var(--color-surface); }
.cn__heading { margin: 0; color: var(--color-text); }
.cn__group { display: flex; flex-direction: column; gap: var(--space-2); }
.cn__intro, .cn__more { margin: 0; color: var(--color-text-muted); }
.cn__list { margin: 0; padding-left: var(--space-5, 1.5rem); display: flex; flex-wrap: wrap; gap: var(--space-1) var(--space-5, 1.5rem); color: var(--color-text); }
/* A long unbroken term wraps instead of scrolling sideways on a phone. */
.cn__list li { min-width: 0; max-width: 100%; overflow-wrap: anywhere; }
</style>
