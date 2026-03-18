<template>
  <nav class="app-nav" role="navigation" aria-label="Main navigation">
    <div class="app-nav__brand">
      <RouterLink to="/" class="app-nav__logo">Peregrine</RouterLink>
    </div>
    <ul class="app-nav__links" role="list">
      <li v-for="link in navLinks" :key="link.to">
        <RouterLink :to="link.to" class="app-nav__link" active-class="app-nav__link--active">
          <span class="app-nav__icon" aria-hidden="true">{{ link.icon }}</span>
          <span class="app-nav__label">{{ link.label }}</span>
        </RouterLink>
      </li>
    </ul>
  </nav>
</template>

<script setup lang="ts">
import { RouterLink } from 'vue-router'

const navLinks = [
  { to: '/',           icon: '🏠', label: 'Home' },
  { to: '/review',     icon: '📋', label: 'Job Review' },
  { to: '/apply',      icon: '✍️',  label: 'Apply' },
  { to: '/interviews', icon: '🗓️', label: 'Interviews' },
  { to: '/prep',       icon: '🎯', label: 'Interview Prep' },
  { to: '/survey',     icon: '🔍', label: 'Survey' },
  { to: '/settings',   icon: '⚙️',  label: 'Settings' },
]
</script>

<style scoped>
.app-nav {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  height: var(--nav-height, 4rem);
  display: flex;
  align-items: center;
  gap: var(--space-4);
  padding: 0 var(--space-6);
  background: var(--color-surface-raised);
  border-bottom: 2px solid var(--color-border);
  z-index: 100;
}

.app-nav__brand { flex-shrink: 0; }

.app-nav__logo {
  font-family: var(--font-display);
  font-weight: 700;
  font-size: 1.2rem;
  color: var(--color-primary);
  text-decoration: none;
}

.app-nav__links {
  display: flex;
  gap: var(--space-2);
  list-style: none;
  margin: 0;
  padding: 0;
  overflow-x: auto;
}

.app-nav__link {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-3);
  border-radius: var(--radius-md);
  color: var(--color-text-muted);
  text-decoration: none;
  font-size: 0.875rem;
  white-space: nowrap;
  /* Enumerate only the properties that animate — no transition:all with spring easing. Gotcha #2. */
  transition:
    background   150ms ease,
    color        150ms ease;
}

.app-nav__link:hover,
.app-nav__link--active {
  background: var(--color-primary-light);
  color: var(--color-primary);
}

.app-nav__icon { font-size: 1rem; }
</style>
