<template>
  <!-- Root uses .app-root class, NOT id="app" — index.html owns #app.
       Nested #app elements cause ambiguous CSS specificity. Gotcha #1. -->
  <div class="app-root" :class="{ 'rich-motion': motion.rich.value }">
    <AppNav />
    <main class="app-main" id="main-content" tabindex="-1">
      <!-- Skip to main content link (screen reader / keyboard nav) -->
      <a href="#main-content" class="skip-link">Skip to main content</a>
      <RouterView />
    </main>
  </div>
</template>

<script setup lang="ts">
import { onMounted } from 'vue'
import { RouterView } from 'vue-router'
import { useMotion } from './composables/useMotion'
import { useHackerMode, useKonamiCode } from './composables/useEasterEgg'
import AppNav from './components/AppNav.vue'

const motion = useMotion()
const { toggle, restore } = useHackerMode()

useKonamiCode(toggle)

onMounted(() => {
  restore()  // re-apply hacker mode from localStorage on hard reload
})
</script>

<style>
/* Global resets — unscoped, applied once to document */
*, *::before, *::after {
  box-sizing: border-box;
  margin: 0;
  padding: 0;
}

html {
  font-family: var(--font-body, sans-serif);
  color: var(--color-text, #1a2338);
  background: var(--color-surface, #eaeff8);
  overflow-x: clip;  /* no BFC side effects. Gotcha #3. */
}

body {
  min-height: 100dvh;   /* dynamic viewport — mobile chrome-aware. Gotcha #13. */
  overflow-x: hidden;
}

#app { min-height: 100dvh; }

/* Layout root — sidebar pushes content right on desktop */
.app-root {
  display: flex;
  min-height: 100dvh;
}

/* Main content area */
.app-main {
  flex: 1;
  min-width: 0;  /* prevents flex blowout */
  /* Desktop: offset by sidebar width */
  margin-left: var(--sidebar-width, 220px);
  /* Mobile: no sidebar, leave room for bottom tab bar */
}

/* Skip-to-content link — visible only on keyboard focus */
.skip-link {
  position: absolute;
  top: -999px;
  left: var(--space-4);
  background: var(--app-primary);
  color: white;
  padding: var(--space-2) var(--space-4);
  border-radius: var(--radius-md);
  font-weight: 600;
  z-index: 9999;
  text-decoration: none;
  transition: top 0ms;
}

.skip-link:focus {
  top: var(--space-4);
}

/* Mobile: no sidebar margin, add bottom tab bar clearance */
@media (max-width: 1023px) {
  .app-main {
    margin-left: 0;
    padding-bottom: calc(56px + env(safe-area-inset-bottom));
  }
}
</style>
