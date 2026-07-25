<template>
  <Transition name="banner-slide">
    <div
      v-if="show"
      class="omm-banner"
      role="status"
      aria-live="polite"
    >
      <span class="omm-banner__icon">⚠</span>
      <div class="omm-banner__body">
        <strong>Local AI not ready</strong>
        <span class="omm-banner__sep"> — </span>
        <span>{{ missingNames }} need{{ missingModels.length === 1 ? 's' : '' }} to be downloaded to enable AI features.</span>
      </div>
      <RouterLink to="/settings/system" class="omm-banner__link" @click="dismiss">
        Download in Settings →
      </RouterLink>
      <button class="omm-banner__close" @click="dismiss" aria-label="Dismiss">✕</button>
    </div>
  </Transition>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { useSystemStore } from '../stores/settings/system'

const DISMISSED_KEY = 'peregrine:ollama-banner-dismissed'

const store = useSystemStore()
const dismissed = ref(localStorage.getItem(DISMISSED_KEY) === '1')

const missingModels = computed(() => store.ollamaModels.filter(m => !m.installed))
const missingNames = computed(() =>
  missingModels.value.map(m => m.display_name).join(', ')
)

const show = computed(() =>
  !dismissed.value &&
  store.ollamaReachable &&
  missingModels.value.length > 0
)

function dismiss() {
  dismissed.value = true
  localStorage.setItem(DISMISSED_KEY, '1')
}

onMounted(() => {
  // Refresh model status to ensure banner reflects current state
  if (!store.ollamaModelsLoading && store.ollamaModels.length === 0) {
    store.loadOllamaModels()
  }
})
</script>

<style scoped>
.omm-banner {
  display: flex; align-items: center; gap: var(--space-3);
  padding: var(--space-2) var(--space-4);
  background: color-mix(in srgb, var(--color-warning, #f59e0b) 12%, transparent);
  border-bottom: 1px solid color-mix(in srgb, var(--color-warning, #f59e0b) 30%, transparent);
  font-size: 0.85rem;
}
.omm-banner__icon { flex-shrink: 0; color: var(--color-warning, #f59e0b); font-size: 1rem; }
.omm-banner__body { flex: 1; min-width: 0; color: var(--color-text); }
.omm-banner__sep { color: var(--color-text-muted); }
.omm-banner__link {
  color: var(--color-accent); text-decoration: none; white-space: nowrap; flex-shrink: 0;
  font-weight: 600; font-size: 0.82rem;
}
.omm-banner__link:hover { text-decoration: underline; }
.omm-banner__close {
  background: none; border: none; cursor: pointer; padding: 2px 6px;
  color: var(--color-text-muted); font-size: 0.9rem; flex-shrink: 0;
  border-radius: var(--radius-sm);
}
.omm-banner__close:hover { background: var(--color-surface-alt); }

.banner-slide-enter-active, .banner-slide-leave-active { transition: all 0.2s ease; }
.banner-slide-enter-from, .banner-slide-leave-to { opacity: 0; transform: translateY(-8px); }
</style>
