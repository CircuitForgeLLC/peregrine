<template>
  <Teleport to="body">
    <div v-if="visible" class="welcome-modal-overlay" @click.self="dismiss">
      <div
        class="welcome-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="welcome-modal-title"
      >
        <span aria-hidden="true" class="welcome-modal__icon">🦅</span>
        <h2 id="welcome-modal-title" class="welcome-modal__heading">
          Welcome to Peregrine
        </h2>
        <p class="welcome-modal__desc">
          A live demo with realistic job search data. Explore freely — nothing you do here is saved.
        </p>
        <ul class="welcome-modal__features" aria-label="What to try">
          <li>📋 Review &amp; rate matched jobs</li>
          <li>✏ Draft a cover letter with AI</li>
          <li>📅 Track your interview pipeline</li>
          <li>🎉 See a hired outcome</li>
        </ul>
        <button class="welcome-modal__explore" @click="dismiss">
          Explore the demo →
        </button>
        <div class="welcome-modal__links">
          <a
            href="https://circuitforge.tech/account"
            class="welcome-modal__link welcome-modal__link--primary"
            target="_blank"
            rel="noopener"
          >Get a free key</a>
          <a
            href="https://git.opensourcesolarpunk.com/Circuit-Forge/peregrine"
            class="welcome-modal__link welcome-modal__link--secondary"
            target="_blank"
            rel="noopener"
          >Self-host →</a>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { ref } from 'vue'

const LS_KEY = 'peregrine_demo_visited'

const emit = defineEmits<{ dismissed: [] }>()

const visible = ref(!localStorage.getItem(LS_KEY))

function dismiss(): void {
  localStorage.setItem(LS_KEY, '1')
  visible.value = false
  emit('dismissed')
}
</script>

<style scoped>
.welcome-modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.6);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
  padding: var(--space-4, 16px);
}

.welcome-modal {
  background: var(--color-surface-raised, #1e2d45);
  border: 1px solid var(--color-border, #2a3a56);
  border-radius: var(--radius-lg, 12px);
  padding: var(--space-6, 24px);
  width: 100%;
  max-width: 360px;
  box-shadow: 0 12px 40px rgba(0, 0, 0, 0.6);
  display: flex;
  flex-direction: column;
  gap: var(--space-3, 12px);
}

.welcome-modal__icon { font-size: 2rem; }

.welcome-modal__heading {
  font-size: 1.15rem;
  font-weight: 700;
  color: var(--color-text, #eaeff8);
  margin: 0;
}

.welcome-modal__desc {
  font-size: 0.85rem;
  color: var(--color-text-muted, #8898aa);
  line-height: 1.5;
  margin: 0;
}

.welcome-modal__features {
  list-style: none;
  padding: 0;
  margin: 0;
  border-top: 1px solid var(--color-border, #2a3a56);
  padding-top: var(--space-3, 12px);
  display: flex;
  flex-direction: column;
  gap: var(--space-2, 8px);
}

.welcome-modal__features li {
  font-size: 0.85rem;
  color: var(--color-text-muted, #8898aa);
}

.welcome-modal__explore {
  width: 100%;
  background: var(--app-primary, #2B6CB0);
  color: #fff;
  border: none;
  border-radius: var(--radius-md, 8px);
  padding: 10px;
  font-size: 0.9rem;
  font-weight: 600;
  cursor: pointer;
  transition: opacity 150ms;
}

.welcome-modal__explore:hover { opacity: 0.85; }

.welcome-modal__links {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--space-2, 8px);
}

.welcome-modal__link {
  text-align: center;
  font-size: 0.8rem;
  font-weight: 600;
  padding: 6px;
  border-radius: var(--radius-sm, 4px);
  text-decoration: none;
  transition: opacity 150ms;
}

.welcome-modal__link:hover { opacity: 0.85; }

.welcome-modal__link--primary {
  border: 1px solid var(--app-primary, #2B6CB0);
  color: var(--app-primary-light, #68A8D8);
}

.welcome-modal__link--secondary {
  border: 1px solid var(--color-border, #2a3a56);
  color: var(--color-text-muted, #8898aa);
}
</style>
