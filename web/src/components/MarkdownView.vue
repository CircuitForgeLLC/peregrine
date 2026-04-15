<template>
  <!-- eslint-disable-next-line vue/no-v-html -->
  <div class="markdown-body" :class="className" v-html="rendered" />
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { marked } from 'marked'
import DOMPurify from 'dompurify'

const props = defineProps<{
  content: string
  className?: string
}>()

// Configure marked: gfm for GitHub-flavored markdown, breaks converts \n → <br>
marked.setOptions({ gfm: true, breaks: true })

const rendered = computed(() => {
  if (!props.content?.trim()) return ''
  const html = marked(props.content) as string
  return DOMPurify.sanitize(html, {
    ALLOWED_TAGS: ['p','br','strong','em','b','i','ul','ol','li','h1','h2','h3','h4','blockquote','code','pre','a','hr'],
    ALLOWED_ATTR: ['href','target','rel'],
  })
})
</script>

<style scoped>
.markdown-body { line-height: 1.6; color: var(--color-text); }
.markdown-body :deep(p) { margin: 0 0 0.75em; }
.markdown-body :deep(p:last-child) { margin-bottom: 0; }
.markdown-body :deep(ul), .markdown-body :deep(ol) { margin: 0 0 0.75em; padding-left: 1.5em; }
.markdown-body :deep(li) { margin-bottom: 0.25em; }
.markdown-body :deep(h1), .markdown-body :deep(h2), .markdown-body :deep(h3), .markdown-body :deep(h4) {
  font-weight: 700; margin: 1em 0 0.4em; color: var(--color-text);
}
.markdown-body :deep(h1) { font-size: 1.2em; }
.markdown-body :deep(h2) { font-size: 1.1em; }
.markdown-body :deep(h3) { font-size: 1em; }
.markdown-body :deep(strong), .markdown-body :deep(b) { font-weight: 700; }
.markdown-body :deep(em), .markdown-body :deep(i) { font-style: italic; }
.markdown-body :deep(code) {
  font-family: var(--font-mono);
  font-size: 0.875em;
  background: var(--color-surface-alt);
  border: 1px solid var(--color-border-light);
  padding: 0.1em 0.3em;
  border-radius: var(--radius-sm);
}
.markdown-body :deep(pre) {
  background: var(--color-surface-alt);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  padding: var(--space-3);
  overflow-x: auto;
  font-size: 0.875em;
}
.markdown-body :deep(pre code) { background: none; border: none; padding: 0; }
.markdown-body :deep(blockquote) {
  border-left: 3px solid var(--color-accent);
  margin: 0.75em 0;
  padding: 0.25em 0 0.25em 1em;
  color: var(--color-text-muted);
  font-style: italic;
}
.markdown-body :deep(hr) {
  border: none;
  border-top: 1px solid var(--color-border);
  margin: 1em 0;
}
.markdown-body :deep(a) {
  color: var(--color-accent);
  text-decoration: underline;
  text-underline-offset: 2px;
}
</style>
