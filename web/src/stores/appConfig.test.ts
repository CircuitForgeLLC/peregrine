import { describe, it, expect, vi, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useAppConfigStore } from './appConfig'

vi.mock('../composables/useApi', () => ({
  useApiFetch: vi.fn(),
}))

import { useApiFetch } from '../composables/useApi'
const mockFetch = vi.mocked(useApiFetch)

describe('useAppConfigStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  it('defaults to safe values before load', () => {
    const store = useAppConfigStore()
    expect(store.isCloud).toBe(false)
    expect(store.tier).toBe('free')
  })

  it('load() populates from API response', async () => {
    mockFetch.mockResolvedValue({
      data: { isCloud: true, isDevMode: false, tier: 'paid', contractedClient: false, inferenceProfile: 'cpu' },
      error: null,
    })
    const store = useAppConfigStore()
    await store.load()
    expect(store.isCloud).toBe(true)
    expect(store.tier).toBe('paid')
  })

  it('load() error leaves defaults intact', async () => {
    mockFetch.mockResolvedValue({ data: null, error: { kind: 'network', message: 'fail' } })
    const store = useAppConfigStore()
    await store.load()
    expect(store.isCloud).toBe(false)
  })
})
