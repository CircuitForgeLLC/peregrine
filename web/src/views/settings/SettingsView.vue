<template>
  <div class="settings-layout">
    <!-- Desktop sidebar -->
    <nav class="settings-sidebar" aria-label="Settings navigation">
      <template v-for="group in visibleGroups" :key="group.label">
        <div class="nav-group-label">{{ group.label }}</div>
        <RouterLink
          v-for="item in group.items"
          :key="item.path"
          :to="item.path"
          :data-testid="`nav-${item.key}`"
          class="nav-item"
          active-class="nav-item--active"
        >{{ item.label }}</RouterLink>
      </template>
    </nav>

    <!-- Mobile chip bar -->
    <div class="settings-chip-bar" role="tablist">
      <RouterLink
        v-for="item in visibleTabs"
        :key="item.path"
        :to="item.path"
        class="chip"
        active-class="chip--active"
        role="tab"
      >{{ item.label }}</RouterLink>
    </div>

    <main class="settings-content">
      <RouterView />
    </main>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useAppConfigStore } from '../../stores/appConfig'

const config = useAppConfigStore()
const devOverride = computed(() => !!localStorage.getItem('dev_tier_override'))
const gpuProfiles = ['single-gpu', 'dual-gpu']

const showSystem = computed(() => !config.isCloud)
const showFineTune = computed(() => {
  if (config.isCloud) return config.tier === 'premium'
  return gpuProfiles.includes(config.inferenceProfile)
})
const showDeveloper = computed(() => config.isDevMode || devOverride.value)

// IMPORTANT: `show` values must be ComputedRef<boolean> objects (e.g. showSystem),
// NOT raw booleans (e.g. showSystem.value). Using .value here would capture a static
// boolean at setup time and break reactivity.
const allGroups = [
  { label: 'Profile', items: [
    { key: 'my-profile', path: '/settings/my-profile', label: 'My Profile', show: true },
    { key: 'resume', path: '/settings/resume', label: 'Resume Profile', show: true },
  ]},
  { label: 'Search', items: [
    { key: 'search', path: '/settings/search', label: 'Search Prefs', show: true },
  ]},
  { label: 'App', items: [
    { key: 'system', path: '/settings/system', label: 'System', show: showSystem },
    { key: 'fine-tune', path: '/settings/fine-tune', label: 'Fine-Tune', show: showFineTune },
  ]},
  { label: 'Account', items: [
    { key: 'license', path: '/settings/license', label: 'License', show: true },
    { key: 'data', path: '/settings/data', label: 'Data', show: true },
    { key: 'privacy', path: '/settings/privacy', label: 'Privacy', show: true },
  ]},
  { label: 'Dev', items: [
    { key: 'developer', path: '/settings/developer', label: 'Developer', show: showDeveloper },
  ]},
]

const visibleGroups = computed(() =>
  allGroups
    .map(g => ({ ...g, items: g.items.filter(i => i.show === true || (typeof i.show !== 'boolean' && i.show.value)) }))
    .filter(g => g.items.length > 0)
)

const visibleTabs = computed(() => visibleGroups.value.flatMap(g => g.items))
</script>

<style scoped>
.settings-layout {
  display: grid;
  grid-template-columns: 180px 1fr;
  grid-template-rows: auto 1fr;
  min-height: calc(100vh - var(--header-height, 56px));
}
.settings-sidebar {
  grid-column: 1;
  grid-row: 1 / -1;
  border-right: 1px solid var(--color-border);
  padding: var(--space-4) 0;
}
.nav-group-label {
  padding: var(--space-3) var(--space-4) var(--space-1);
  font-size: 0.65rem;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--color-text-muted);
}
.nav-item {
  display: block;
  padding: var(--space-2) var(--space-4);
  font-size: 0.8rem;
  color: var(--color-text-secondary);
  text-decoration: none;
  border-right: 2px solid transparent;
}
.nav-item--active {
  background: color-mix(in srgb, var(--color-primary) 15%, transparent);
  color: var(--color-primary);
  border-right-color: var(--color-primary);
}
.settings-chip-bar {
  display: none;
  grid-column: 1 / -1;
  overflow-x: auto;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-3);
  border-bottom: 1px solid var(--color-border);
  white-space: nowrap;
  -webkit-mask-image: linear-gradient(to right, black 85%, transparent);
  mask-image: linear-gradient(to right, black 85%, transparent);
}
.chip {
  display: inline-block;
  padding: var(--space-1) var(--space-3);
  border-radius: 999px;
  border: 1px solid var(--color-border);
  background: var(--color-surface-raised);
  color: var(--color-text-secondary);
  font-size: 0.78rem;
  text-decoration: none;
  flex-shrink: 0;
}
.chip--active {
  background: color-mix(in srgb, var(--color-primary) 20%, transparent);
  border-color: var(--color-primary);
  color: var(--color-primary);
}
.settings-content {
  grid-column: 2;
  padding: var(--space-6) var(--space-8);
  overflow-y: auto;
}
@media (max-width: 767px) {
  .settings-layout { grid-template-columns: 1fr; }
  .settings-sidebar { display: none; }
  .settings-chip-bar { display: flex; }
  .settings-content { grid-column: 1; padding: var(--space-4); }
}
</style>
