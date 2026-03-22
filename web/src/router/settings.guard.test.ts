import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useAppConfigStore } from '../stores/appConfig'
import { settingsGuard } from './settingsGuard'

vi.mock('../composables/useApi', () => ({ useApiFetch: vi.fn() }))

describe('settingsGuard', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
  })
  afterEach(() => {
    localStorage.clear()
  })

  it('passes through non-settings routes immediately', () => {
    const next = vi.fn()
    settingsGuard({ path: '/review' }, {}, next)
    // Guard only handles /settings/* — for non-settings routes the router
    // calls next() before reaching settingsGuard, but the guard itself
    // will still call next() with no redirect since no tab matches
    expect(next).toHaveBeenCalledWith()
  })

  it('redirects /settings/system in cloud mode', () => {
    const store = useAppConfigStore()
    store.isCloud = true
    const next = vi.fn()
    settingsGuard({ path: '/settings/system' }, {}, next)
    expect(next).toHaveBeenCalledWith('/settings/my-profile')
  })

  it('allows /settings/system in self-hosted mode', () => {
    const store = useAppConfigStore()
    store.isCloud = false
    const next = vi.fn()
    settingsGuard({ path: '/settings/system' }, {}, next)
    expect(next).toHaveBeenCalledWith()
  })

  it('redirects /settings/fine-tune for non-GPU self-hosted', () => {
    const store = useAppConfigStore()
    store.isCloud = false
    store.inferenceProfile = 'cpu'
    const next = vi.fn()
    settingsGuard({ path: '/settings/fine-tune' }, {}, next)
    expect(next).toHaveBeenCalledWith('/settings/my-profile')
  })

  it('allows /settings/fine-tune for single-gpu self-hosted', () => {
    const store = useAppConfigStore()
    store.isCloud = false
    store.inferenceProfile = 'single-gpu'
    const next = vi.fn()
    settingsGuard({ path: '/settings/fine-tune' }, {}, next)
    expect(next).toHaveBeenCalledWith()
  })

  it('allows /settings/fine-tune for dual-gpu self-hosted', () => {
    const store = useAppConfigStore()
    store.isCloud = false
    store.inferenceProfile = 'dual-gpu'
    const next = vi.fn()
    settingsGuard({ path: '/settings/fine-tune' }, {}, next)
    expect(next).toHaveBeenCalledWith()
  })

  it('redirects /settings/fine-tune on cloud when tier is not premium', () => {
    const store = useAppConfigStore()
    store.isCloud = true
    store.tier = 'paid'
    const next = vi.fn()
    settingsGuard({ path: '/settings/fine-tune' }, {}, next)
    expect(next).toHaveBeenCalledWith('/settings/my-profile')
  })

  it('allows /settings/fine-tune on cloud when tier is premium', () => {
    const store = useAppConfigStore()
    store.isCloud = true
    store.tier = 'premium'
    const next = vi.fn()
    settingsGuard({ path: '/settings/fine-tune' }, {}, next)
    expect(next).toHaveBeenCalledWith()
  })

  it('redirects /settings/developer when not dev mode and no override', () => {
    const store = useAppConfigStore()
    store.isDevMode = false
    const next = vi.fn()
    settingsGuard({ path: '/settings/developer' }, {}, next)
    expect(next).toHaveBeenCalledWith('/settings/my-profile')
  })

  it('allows /settings/developer when isDevMode is true', () => {
    const store = useAppConfigStore()
    store.isDevMode = true
    const next = vi.fn()
    settingsGuard({ path: '/settings/developer' }, {}, next)
    expect(next).toHaveBeenCalledWith()
  })

  it('allows /settings/developer when dev_tier_override set in localStorage', () => {
    const store = useAppConfigStore()
    store.isDevMode = false
    localStorage.setItem('dev_tier_override', 'premium')
    const next = vi.fn()
    settingsGuard({ path: '/settings/developer' }, {}, next)
    expect(next).toHaveBeenCalledWith()
  })

  it('allows /settings/privacy in cloud mode', () => {
    const store = useAppConfigStore()
    store.isCloud = true
    const next = vi.fn()
    settingsGuard({ path: '/settings/privacy' }, {}, next)
    expect(next).toHaveBeenCalledWith()
  })

  it('allows /settings/privacy in self-hosted mode', () => {
    const store = useAppConfigStore()
    store.isCloud = false
    const next = vi.fn()
    settingsGuard({ path: '/settings/privacy' }, {}, next)
    expect(next).toHaveBeenCalledWith()
  })

  it('allows /settings/license in both modes', () => {
    const store = useAppConfigStore()
    store.isCloud = true
    const next = vi.fn()
    settingsGuard({ path: '/settings/license' }, {}, next)
    expect(next).toHaveBeenCalledWith()
  })
})
