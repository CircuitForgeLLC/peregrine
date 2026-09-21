import { computed, type ComputedRef } from 'vue'
import { useAppConfigStore } from '../stores/appConfig'

/**
 * Gate for the AI-assisted setup path (the onboarding chat at
 * /wizard/ai-profile, and the "Start AI setup" entry point on My Profile).
 * Mirrors the server-side gate in dev-api.py's _can_use_ai_wizard() --
 * keep the two in sync if either changes.
 */
export function useAiSetupAccess(): { hasAccess: ComputedRef<boolean> } {
  const config = useAppConfigStore()

  const hasAccess = computed(() =>
    config.tier !== 'free' ||
    config.byokUnlocked ||
    (config.isCloud && !config.wizardComplete)
  )

  return { hasAccess }
}
