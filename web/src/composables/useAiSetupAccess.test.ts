import { describe, it, expect, beforeEach } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useAppConfigStore } from '../stores/appConfig'
import { useAiSetupAccess } from './useAiSetupAccess'

describe('useAiSetupAccess', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('grants access when tier is not free', () => {
    const config = useAppConfigStore()
    config.tier = 'paid'
    config.byokUnlocked = false
    config.isCloud = false
    config.wizardComplete = true
    const { hasAccess } = useAiSetupAccess()
    expect(hasAccess.value).toBe(true)
  })

  it('grants access when BYOK is unlocked, even on free tier', () => {
    const config = useAppConfigStore()
    config.tier = 'free'
    config.byokUnlocked = true
    config.isCloud = false
    config.wizardComplete = true
    const { hasAccess } = useAiSetupAccess()
    expect(hasAccess.value).toBe(true)
  })

  it('grants access to free-tier cloud users while onboarding is incomplete', () => {
    const config = useAppConfigStore()
    config.tier = 'free'
    config.byokUnlocked = false
    config.isCloud = true
    config.wizardComplete = false
    const { hasAccess } = useAiSetupAccess()
    expect(hasAccess.value).toBe(true)
  })

  it('revokes access to free-tier cloud users once onboarding is complete', () => {
    const config = useAppConfigStore()
    config.tier = 'free'
    config.byokUnlocked = false
    config.isCloud = true
    config.wizardComplete = true
    const { hasAccess } = useAiSetupAccess()
    expect(hasAccess.value).toBe(false)
  })

  it('denies access to free-tier self-hosted users regardless of wizard state', () => {
    const config = useAppConfigStore()
    config.tier = 'free'
    config.byokUnlocked = false
    config.isCloud = false
    config.wizardComplete = false
    const { hasAccess } = useAiSetupAccess()
    expect(hasAccess.value).toBe(false)
  })
})
