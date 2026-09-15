<script setup lang="ts">
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { useAppConfigStore } from '../../stores/appConfig'
import AiProfileChat from '../../components/AiProfileChat.vue'
import { RouterLink } from 'vue-router'

const router = useRouter()
const config = useAppConfigStore()

const hasAccess = computed(() => config.tier !== 'free' || config.byokUnlocked)

function onSaved() {
  // Reached from onboarding (WizardResumeStep's AI Assistant tab) or from
  // settings after onboarding is done — send the user back to whichever one.
  // /settings/my-profile while the wizard is still incomplete would bounce
  // through the global wizard gate straight to /setup's step-1 redirect,
  // undoing the progress they just made.
  router.push(config.wizardComplete ? '/settings/my-profile' : '/setup/resume')
}
</script>

<template>
  <div class="ai-view">
    <!-- Tier gate -->
    <div v-if="!hasAccess" class="ai-locked">
      <div class="ai-locked__icon" aria-hidden="true">🔒</div>
      <h2 class="ai-locked__heading">AI Profile Assistant</h2>
      <p class="ai-locked__body">
        The AI profile assistant is available on the Paid plan, or for free when you bring your own LLM.
        You can
        <RouterLink to="/settings/my-profile" class="ai-locked__link">set up your profile manually</RouterLink>
        instead.
      </p>
    </div>

    <!-- Chat UI -->
    <AiProfileChat v-else class="ai-view__chat" @saved="onSaved" />
  </div>
</template>

<style scoped>
/* ── Page container ────────────────────────────────── */
.ai-view {
  min-height: 100vh;
  background: var(--color-surface);
  display: flex;
  justify-content: center;
  padding: var(--space-8) var(--space-4);
}

.ai-view__chat {
  max-width: 680px;
}

/* ── Locked state ──────────────────────────────────── */
.ai-locked {
  max-width: 480px;
  width: 100%;
  margin: auto;
  text-align: center;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-4);
}

.ai-locked__icon {
  font-size: 3rem;
}

.ai-locked__heading {
  font-family: var(--font-display);
  font-size: 1.5rem;
  font-weight: 700;
  color: var(--color-text);
  margin: 0;
}

.ai-locked__body {
  font-size: 0.95rem;
  color: var(--color-text-muted);
  line-height: 1.6;
  margin: 0;
}

.ai-locked__link {
  color: var(--color-accent);
  text-decoration: underline;
  text-underline-offset: 3px;
}

/* ── Mobile ────────────────────────────────────────── */
@media (max-width: 600px) {
  .ai-view {
    padding: var(--space-4) var(--space-3);
  }
}
</style>
