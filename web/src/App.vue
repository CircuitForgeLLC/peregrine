<template>
  <!-- IMPORTANT: root element uses class="app-root", NOT id="app".
       index.html owns #app as the mount target.
       Mixing the two creates nested #app elements with ambiguous CSS specificity.
       Gotcha #1 from docs/vue-port-gotchas.md. -->
  <div
    class="app-root"
    :class="{ 'rich-motion': motion.rich.value }"
    :data-theme="hackerTheme"
  >
    <AppNav />
    <main class="app-main">
      <RouterView />
    </main>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { RouterView } from 'vue-router'
import { useMotion } from './composables/useMotion'
import { useHackerMode, useKonamiCode } from './composables/useEasterEgg'
import AppNav from './components/AppNav.vue'

const motion = useMotion()
const { toggle, restore } = useHackerMode()

// Computed so template reactively tracks localStorage-driven theme
const hackerTheme = computed(() =>
  typeof document !== 'undefined' && document.documentElement.dataset.theme === 'hacker'
    ? 'hacker'
    : undefined,
)

useKonamiCode(toggle)

onMounted(() => {
  restore()  // re-apply hacker mode from localStorage on hard reload
})
</script>

<style>
/* Global resets in <style> (no scoped) — applied once to the document */
*, *::before, *::after {
  box-sizing: border-box;
  margin: 0;
  padding: 0;
}

html {
  font-family: var(--font-body, sans-serif);
  color: var(--color-text, #1a2338);
  background: var(--color-surface, #eaeff8);
  /* clip (not hidden) — avoids BFC scroll-container side effects. Gotcha #3. */
  overflow-x: clip;
}

body {
  min-height: 100dvh;  /* dvh = dynamic viewport height — mobile chrome-aware. Gotcha #13. */
  overflow-x: hidden;  /* body hidden is survivable; html must be clip */
}

/* Mount shell — thin container, no layout */
#app {
  min-height: 100dvh;
}

/* App layout root */
.app-root {
  display: flex;
  min-height: 100dvh;
}

.app-main {
  flex: 1;
  min-width: 0;  /* prevents flex children from blowing out container width */
  padding-top: var(--nav-height, 4rem);
}
</style>
