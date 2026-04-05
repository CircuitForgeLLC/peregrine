<template>
  <!-- Desktop: persistent sidebar (≥1024px) -->
  <!-- Mobile: bottom tab bar (<1024px) -->
  <!-- Design spec: circuitforge-plans/peregrine/2026-03-03-nuxt-frontend-design.md §3.1 -->
  <nav class="app-sidebar" role="navigation" aria-label="Main navigation">
    <!-- Brand -->
    <div class="sidebar__brand">
      <RouterLink to="/" class="sidebar__logo" @click.prevent="handleLogoClick">
        <span class="sidebar__bird" :class="{ 'sidebar__bird--ruffle': ruffling }" aria-hidden="true">🦅</span>
        <span class="sidebar__wordmark">Peregrine</span>
      </RouterLink>
    </div>

    <!-- Nav links -->
    <ul class="sidebar__links" role="list">
      <li v-for="link in navLinks" :key="link.to">
        <RouterLink
          :to="link.to"
          class="sidebar__link"
          active-class="sidebar__link--active"
          :aria-label="link.label"
        >
          <component :is="link.icon" class="sidebar__icon" aria-hidden="true" />
          <span class="sidebar__label">{{ link.label }}</span>
          <span v-if="link.badge" class="sidebar__badge" :aria-label="`${link.badge} items`">{{ link.badge }}</span>
        </RouterLink>
      </li>
    </ul>

    <!-- Hacker mode exit (shows when active) -->
    <div v-if="isHackerMode" class="sidebar__hacker-exit">
      <button class="sidebar__hacker-btn" @click="exitHackerMode">
        Exit hacker mode
      </button>
    </div>

    <!-- Settings at bottom -->
    <div class="sidebar__footer">
      <RouterLink to="/settings" class="sidebar__link sidebar__link--footer" active-class="sidebar__link--active">
        <Cog6ToothIcon class="sidebar__icon" aria-hidden="true" />
        <span class="sidebar__label">Settings</span>
      </RouterLink>
      <button class="sidebar__classic-btn" @click="switchToClassic" title="Switch to Classic (Streamlit) UI">
        ⚡ Classic
      </button>
    </div>
  </nav>

  <!-- Mobile bottom tab bar -->
  <nav class="app-tabbar" role="navigation" aria-label="Main navigation">
    <ul class="tabbar__links" role="list">
      <li v-for="link in mobileLinks" :key="link.to">
        <RouterLink
          :to="link.to"
          class="tabbar__link"
          active-class="tabbar__link--active"
          :aria-label="link.label"
        >
          <component :is="link.icon" class="tabbar__icon" aria-hidden="true" />
          <span class="tabbar__label">{{ link.label }}</span>
        </RouterLink>
      </li>
    </ul>
  </nav>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { RouterLink } from 'vue-router'
import {
  HomeIcon,
  ClipboardDocumentListIcon,
  PencilSquareIcon,
  CalendarDaysIcon,
  LightBulbIcon,
  MagnifyingGlassIcon,
  NewspaperIcon,
  Cog6ToothIcon,
} from '@heroicons/vue/24/outline'

import { useDigestStore } from '../stores/digest'
const digestStore = useDigestStore()

// Logo click easter egg — 9.6: Click the Bird 5× rapidly
const logoClickCount = ref(0)
const ruffling = ref(false)
let clickTimer: ReturnType<typeof setTimeout> | null = null

function handleLogoClick() {
  logoClickCount.value++
  if (clickTimer) clearTimeout(clickTimer)
  clickTimer = setTimeout(() => { logoClickCount.value = 0 }, 800)

  if (logoClickCount.value >= 5) {
    logoClickCount.value = 0
    ruffling.value = true
    setTimeout(() => { ruffling.value = false }, 600)
  }
}

// Hacker mode state
const isHackerMode = computed(() =>
  document.documentElement.dataset.theme === 'hacker',
)

function exitHackerMode() {
  delete document.documentElement.dataset.theme
  localStorage.removeItem('cf-hacker-mode')
}

const _apiBase = import.meta.env.BASE_URL.replace(/\/$/, '')

async function switchToClassic() {
  // Persist preference via API so Streamlit reads streamlit from user.yaml
  // and won't re-set the cookie back to vue (avoids the ?prgn_switch rerun cycle)
  try {
    await fetch(_apiBase + '/api/settings/ui-preference', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ preference: 'streamlit' }),
    })
  } catch { /* non-fatal — cookie below is enough for immediate redirect */ }
  document.cookie = 'prgn_ui=streamlit; path=/; SameSite=Lax'
  // Navigate to root (no query params) — Caddy routes to Streamlit based on cookie
  window.location.href = window.location.origin + '/'
}

const navLinks = computed(() => [
  { to: '/',           icon: HomeIcon,                   label: 'Home' },
  { to: '/review',     icon: ClipboardDocumentListIcon,  label: 'Job Review' },
  { to: '/apply',      icon: PencilSquareIcon,           label: 'Apply' },
  { to: '/interviews', icon: CalendarDaysIcon,           label: 'Interviews' },
  { to: '/digest',     icon: NewspaperIcon,              label: 'Digest',
    badge: digestStore.entries.length || undefined },
  { to: '/prep',       icon: LightBulbIcon,              label: 'Interview Prep' },
  { to: '/survey',     icon: MagnifyingGlassIcon,        label: 'Survey' },
])

// Mobile: only the 5 most-used views
const mobileLinks = [
  { to: '/',           icon: HomeIcon,                   label: 'Home' },
  { to: '/review',     icon: ClipboardDocumentListIcon,  label: 'Review' },
  { to: '/apply',      icon: PencilSquareIcon,           label: 'Apply' },
  { to: '/interviews', icon: CalendarDaysIcon,           label: 'Interviews' },
  { to: '/settings',   icon: Cog6ToothIcon,              label: 'Settings' },
]
</script>

<style scoped>
/* ── Sidebar (desktop ≥1024px) ──────────────────────── */
.app-sidebar {
  position: fixed;
  top: 0;
  left: 0;
  bottom: 0;
  width: var(--sidebar-width);
  display: flex;
  flex-direction: column;
  background: var(--color-surface-raised);
  border-right: 1px solid var(--color-border);
  z-index: 100;
  padding: var(--space-4) 0;
}

.sidebar__brand {
  padding: 0 var(--space-4) var(--space-4);
  border-bottom: 1px solid var(--color-border-light);
  margin-bottom: var(--space-3);
}

.sidebar__logo {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  text-decoration: none;
}

/* Click-the-bird ruffle animation — easter egg 9.6 */
.sidebar__bird {
  font-size: 1.4rem;
  display: inline-block;
  transform-origin: center bottom;
}

.sidebar__bird--ruffle {
  animation: bird-ruffle 0.5s ease;
}

@keyframes bird-ruffle {
  0%   { transform: rotate(0deg) scale(1); }
  20%  { transform: rotate(-8deg) scale(1.15); }
  40%  { transform: rotate(8deg) scale(1.2); }
  60%  { transform: rotate(-6deg) scale(1.1); }
  80%  { transform: rotate(4deg) scale(1.05); }
  100% { transform: rotate(0deg) scale(1); }
}

.sidebar__wordmark {
  font-family: var(--font-display);
  font-weight: 700;
  font-size: var(--text-lg);
  color: var(--app-primary);
}

.sidebar__links {
  flex: 1;
  list-style: none;
  margin: 0;
  padding: 0 var(--space-3);
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  overflow-y: auto;
}

.sidebar__link {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-3) var(--space-4);
  border-radius: var(--radius-md);
  color: var(--color-text-muted);
  text-decoration: none;
  font-size: var(--text-sm);
  font-weight: 500;
  min-height: 44px;  /* WCAG 2.5.5 touch target */
  /* Enumerate properties explicitly — no transition:all. Gotcha #2. */
  transition:
    background 150ms ease,
    color      150ms ease;
}

.sidebar__link:hover {
  background: var(--app-primary-light);
  color: var(--app-primary);
}

.sidebar__link--active {
  background: var(--app-primary-light);
  color: var(--app-primary);
  font-weight: 600;
}

.sidebar__icon {
  width: 1.25rem;
  height: 1.25rem;
  flex-shrink: 0;
}

.sidebar__badge {
  margin-left: auto;
  background: var(--app-accent);
  color: var(--app-accent-text);
  font-size: var(--text-xs);
  font-weight: 700;
  padding: 1px 6px;
  border-radius: var(--radius-full);
  min-width: 18px;
  text-align: center;
}

/* Hacker mode exit button */
.sidebar__hacker-exit {
  padding: var(--space-3);
  border-top: 1px solid var(--color-border-light);
}

.sidebar__hacker-btn {
  width: 100%;
  padding: var(--space-2) var(--space-3);
  background: transparent;
  border: 1px solid var(--app-primary);
  border-radius: var(--radius-md);
  color: var(--app-primary);
  font-family: var(--font-mono);
  font-size: var(--text-xs);
  cursor: pointer;
  transition: background 150ms ease, color 150ms ease;
}

.sidebar__hacker-btn:hover {
  background: var(--app-primary);
  color: var(--color-surface);
}

.sidebar__footer {
  padding: var(--space-3) var(--space-3) 0;
  border-top: 1px solid var(--color-border-light);
}

.sidebar__link--footer {
  margin: 0;
}

.sidebar__classic-btn {
  display: flex;
  align-items: center;
  width: 100%;
  padding: var(--space-2) var(--space-3);
  margin-top: var(--space-1);
  background: none;
  border: none;
  border-radius: var(--radius-md);
  color: var(--color-text-muted);
  font-size: var(--text-xs);
  font-weight: 500;
  cursor: pointer;
  opacity: 0.6;
  transition: opacity 150ms, background 150ms;
  white-space: nowrap;
}

.sidebar__classic-btn:hover {
  opacity: 1;
  background: var(--color-surface-alt);
}

/* ── Mobile tab bar (<1024px) ───────────────────────── */
.app-tabbar {
  display: none;  /* hidden on desktop */
  position: fixed;
  bottom: 0;
  left: 0;
  right: 0;
  background: var(--color-surface-raised);
  border-top: 1px solid var(--color-border);
  z-index: 100;
  padding-bottom: env(safe-area-inset-bottom);  /* iPhone notch */
}

.tabbar__links {
  display: flex;
  list-style: none;
  margin: 0;
  padding: 0;
}

.tabbar__link {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 2px;
  padding: var(--space-2) var(--space-1);
  min-height: 56px;  /* WCAG 2.5.5 touch target */
  color: var(--color-text-muted);
  text-decoration: none;
  font-size: 10px;
  transition: color 150ms ease;
}

.tabbar__link--active { color: var(--app-primary); }
.tabbar__icon { width: 1.5rem; height: 1.5rem; }

/* ── Responsive ─────────────────────────────────────── */
@media (max-width: 1023px) {
  .app-sidebar { display: none; }
  .app-tabbar  { display: block; }
}
</style>
