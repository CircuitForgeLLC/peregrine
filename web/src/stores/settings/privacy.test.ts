import { describe, it, expect, vi, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { usePrivacyStore } from './privacy'

vi.mock('../../composables/useApi', () => ({ useApiFetch: vi.fn() }))
import { useApiFetch } from '../../composables/useApi'
const mockFetch = vi.mocked(useApiFetch)

describe('usePrivacyStore', () => {
  beforeEach(() => { setActivePinia(createPinia()); vi.clearAllMocks() })

  it('byokInfoDismissed is false by default', () => {
    expect(usePrivacyStore().byokInfoDismissed).toBe(false)
  })

  it('dismissByokInfo() sets dismissed to true', () => {
    const store = usePrivacyStore()
    store.dismissByokInfo()
    expect(store.byokInfoDismissed).toBe(true)
  })

  it('showByokPanel is true when cloud backends configured and not dismissed', () => {
    const store = usePrivacyStore()
    store.activeCloudBackends = ['anthropic']
    store.byokInfoDismissed = false
    expect(store.showByokPanel).toBe(true)
  })

  it('showByokPanel is false when dismissed', () => {
    const store = usePrivacyStore()
    store.activeCloudBackends = ['anthropic']
    store.byokInfoDismissed = true
    expect(store.showByokPanel).toBe(false)
  })

  it('showByokPanel re-appears when new backend added after dismissal', () => {
    const store = usePrivacyStore()
    store.activeCloudBackends = ['anthropic']
    store.dismissByokInfo()
    store.activeCloudBackends = ['anthropic', 'openai']
    expect(store.showByokPanel).toBe(true)
  })
})
