<template>
  <!-- Root uses .app-root class, NOT id="app" — index.html owns #app.
       Nested #app elements cause ambiguous CSS specificity. Gotcha #1. -->
  <div class="app-root" :class="{ 'rich-motion': motion.rich.value, 'app-root--wizard': isWizard }">
    <AppNav v-if="!isWizard" />
    <main class="app-main" :class="{ 'app-main--wizard': isWizard }" id="main-content" tabindex="-1">
      <!-- Skip to main content link (screen reader / keyboard nav) -->
      <a href="#main-content" class="skip-link">Skip to main content</a>

      <!-- Demo mode banner — sticky top bar, visible on all pages -->
      <div v-if="config.isDemo" class="demo-banner" role="status" aria-live="polite">
        👁 Demo mode — changes are not saved and AI features are disabled.
      </div>

      <RouterView />

      <!-- Global toast — rendered at App level so any component can trigger it -->
      <Transition name="global-toast">
        <div v-if="toast.message.value" class="global-toast" role="status" aria-live="polite">
          {{ toast.message.value }}
        </div>
      </Transition>
    </main>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { RouterView, useRoute } from 'vue-router'
import { useMotion } from './composables/useMotion'
import { useHackerMode, useKonamiCode } from './composables/useEasterEgg'
import { useTheme } from './composables/useTheme'
import { useToast } from './composables/useToast'
import AppNav from './components/AppNav.vue'
import { useAppConfigStore } from './stores/appConfig'
import { useDigestStore } from './stores/digest'

const motion = useMotion()
const route = useRoute()
const { toggle, restore } = useHackerMode()
const { initTheme } = useTheme()
const toast = useToast()
const config = useAppConfigStore()
const digestStore = useDigestStore()

const isWizard = computed(() => route.path.startsWith('/setup'))

useKonamiCode(toggle)

onMounted(() => {
  initTheme()  // apply persisted theme (hacker mode takes priority inside initTheme)
  restore()    // kept for hacker mode re-entry on hard reload (initTheme handles it, belt+suspenders)
  digestStore.fetchAll()  // populate badge immediately, before user visits Digest tab
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

/* Wizard: full-bleed, no sidebar offset, no tab-bar clearance */
.app-root--wizard {
  display: block;
}

.app-main--wizard {
  margin-left: 0;
  padding-bottom: 0;
}

/* Demo mode banner — sticky top bar */
.demo-banner {
  position: sticky;
  top: 0;
  z-index: 200;
  background: var(--color-warning);
  color: #1a1a1a;  /* forced dark — warning bg is always light enough */
  text-align: center;
  font-size: 0.85rem;
  font-weight: 600;
  padding: 6px var(--space-4, 16px);
  letter-spacing: 0.01em;
}

/* Global toast — bottom-center, above tab bar */
.global-toast {
  position: fixed;
  bottom: calc(72px + env(safe-area-inset-bottom));
  left: 50%;
  transform: translateX(-50%);
  background: var(--color-surface-raised, #2a3650);
  color: var(--color-text, #eaeff8);
  padding: 10px 20px;
  border-radius: var(--radius-md, 8px);
  font-size: 0.9rem;
  font-weight: 500;
  box-shadow: 0 4px 16px rgba(0,0,0,0.25);
  white-space: nowrap;
  z-index: 9000;
  pointer-events: none;
}

.global-toast-enter-active, .global-toast-leave-active {
  transition: opacity 220ms ease, transform 220ms ease;
}
.global-toast-enter-from, .global-toast-leave-to {
  opacity: 0;
  transform: translateX(-50%) translateY(8px);
}

@media (min-width: 1024px) {
  .global-toast {
    bottom: calc(24px + env(safe-area-inset-bottom));
    left: calc(50% + var(--sidebar-width, 220px) / 2);
  }
}
</style>
