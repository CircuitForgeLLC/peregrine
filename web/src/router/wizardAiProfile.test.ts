import { describe, it, expect, beforeEach } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { router } from './index'
import { useAppConfigStore } from '../stores/appConfig'

// Regression test for: "opening the AI assistant tab on the onboarding
// dumps the user back to the first page."
//
// Root cause: /wizard/ai-profile is linked from WizardResumeStep.vue's "AI
// Assistant" tab (usable mid-onboarding), but the global wizard-completion
// guard treated it like any other main-app route and bounced it to bare
// /setup — which itself has a static route redirect straight to
// /setup/hardware (step 1), regardless of actual wizard progress.
describe('wizard gate: /wizard/ai-profile', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    const config = useAppConfigStore()
    config.loaded = true
    config.isDemo = false
  })

  it('is reachable while the wizard is still incomplete (mid-onboarding)', async () => {
    const config = useAppConfigStore()
    config.wizardComplete = false

    await router.push('/wizard/ai-profile')
    expect(router.currentRoute.value.path).toBe('/wizard/ai-profile')
  })

  it('is reachable after the wizard is complete (settings entry point)', async () => {
    const config = useAppConfigStore()
    config.wizardComplete = true

    await router.push('/wizard/ai-profile')
    expect(router.currentRoute.value.path).toBe('/wizard/ai-profile')
  })

  it('other main-app routes are still gated to /setup while incomplete (guard stays narrow)', async () => {
    const config = useAppConfigStore()
    config.wizardComplete = false

    await router.push('/settings/my-profile')
    // Resolves to bare /setup, not /setup/hardware — the '' child route no
    // longer has a static redirect (see router/index.ts comment); it's
    // WizardLayout's own onMounted logic that routes on to the real resume
    // point from there.
    expect(router.currentRoute.value.path).toBe('/setup')
  })
})
