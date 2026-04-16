<template>
  <div class="demo-banner" role="status" aria-live="polite">
    <span class="demo-banner__label">👁 Demo mode — changes are not saved</span>
    <div class="demo-banner__ctas">
      <a
        href="https://circuitforge.tech/peregrine"
        class="demo-banner__cta demo-banner__cta--primary"
        target="_blank"
        rel="noopener"
      >Get free key</a>
      <a
        href="https://git.opensourcesolarpunk.com/Circuit-Forge/peregrine"
        class="demo-banner__cta demo-banner__cta--secondary"
        target="_blank"
        rel="noopener"
      >Self-host</a>
    </div>
  </div>
</template>

<script setup lang="ts">
// No props — DemoBanner is only rendered when config.isDemo is true (App.vue)
</script>

<style scoped>
.demo-banner {
  position: sticky;
  top: 0;
  z-index: 200;
  background: var(--color-surface-raised);
  border-bottom: 1px solid var(--color-border);
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 6px var(--space-4);
  gap: var(--space-3);
}

.demo-banner__label {
  font-size: 0.8rem;
  color: var(--color-text-muted);
}

.demo-banner__ctas {
  display: flex;
  gap: var(--space-2);
  flex-shrink: 0;
}

.demo-banner__cta {
  font-size: 0.75rem;
  font-weight: 600;
  padding: 3px 10px;
  border-radius: var(--radius-sm);
  text-decoration: none;
  transition: opacity var(--transition);
}

.demo-banner__cta:hover {
  opacity: 0.85;
}

.demo-banner__cta--primary {
  background: var(--color-primary);
  color: white;
}

.demo-banner__cta--secondary {
  background: none;
  border: 1px solid var(--color-border);
  color: var(--color-text-muted);
}

@media (max-width: 480px) {
  .demo-banner__label {
    display: none;
  }
}
</style>
