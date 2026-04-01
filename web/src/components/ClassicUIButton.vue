<template>
  <button
    class="classic-ui-btn"
    :title="label"
    @click="switchToClassic"
  >
    {{ label }}
  </button>
</template>

<script setup lang="ts">
const props = withDefaults(defineProps<{
  label?: string
}>(), {
  label: 'Switch to Classic UI',
})

function switchToClassic(): void {
  // Set cookie so Caddy routes next request to Streamlit
  document.cookie = 'prgn_ui=streamlit; path=/; SameSite=Lax'

  // Append ?prgn_switch=streamlit so Streamlit's sync_ui_cookie()
  // updates user.yaml to match — cookie alone can't be read server-side
  const url = new URL(window.location.href)
  url.searchParams.set('prgn_switch', 'streamlit')
  window.location.href = url.toString()
}
</script>

<style scoped>
.classic-ui-btn {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  padding: 0.4rem 0.9rem;
  border-radius: 0.5rem;
  border: 1px solid var(--color-border, #444);
  background: transparent;
  color: var(--color-text-muted, #aaa);
  font-size: 0.8rem;
  cursor: pointer;
  transition: color 0.15s, border-color 0.15s;
}
.classic-ui-btn:hover {
  color: var(--color-text, #eee);
  border-color: var(--color-text, #eee);
}
</style>
