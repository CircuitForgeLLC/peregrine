import { describe, it, expect, vi, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useAppConfigStore } from '../stores/appConfig'
import { wizardGuard } from './wizardGuard'

vi.mock('../composables/useApi', () => ({ useApiFetch: vi.fn() }))

describe('wizardGuard', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('allows /settings/* through when the wizard is incomplete', async () => {
    const config = useAppConfigStore()
    config.loaded = true
    config.wizardComplete = false
    const next = vi.fn()
    await wizardGuard({ path: '/settings/my-profile' }, {}, next)
    expect(next).toHaveBeenCalledWith()
  })

  it('still redirects non-/setup, non-/settings routes to /setup when incomplete', async () => {
    const config = useAppConfigStore()
    config.loaded = true
    config.wizardComplete = false
    const next = vi.fn()
    await wizardGuard({ path: '/review' }, {}, next)
    expect(next).toHaveBeenCalledWith('/setup')
  })

  it('redirects /setup to / once the wizard is complete', async () => {
    const config = useAppConfigStore()
    config.loaded = true
    config.wizardComplete = true
    const next = vi.fn()
    await wizardGuard({ path: '/setup' }, {}, next)
    expect(next).toHaveBeenCalledWith('/')
  })

  it('allows /settings/* through once the wizard is complete', async () => {
    const config = useAppConfigStore()
    config.loaded = true
    config.wizardComplete = true
    const next = vi.fn()
    await wizardGuard({ path: '/settings/my-profile' }, {}, next)
    expect(next).toHaveBeenCalledWith()
  })
})
