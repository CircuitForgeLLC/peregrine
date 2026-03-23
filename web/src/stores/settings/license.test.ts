import { describe, it, expect, vi, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useLicenseStore } from './license'

vi.mock('../../composables/useApi', () => ({ useApiFetch: vi.fn() }))
import { useApiFetch } from '../../composables/useApi'
const mockFetch = vi.mocked(useApiFetch)

describe('useLicenseStore', () => {
  beforeEach(() => { setActivePinia(createPinia()); vi.clearAllMocks() })

  it('initial active is false', () => {
    expect(useLicenseStore().active).toBe(false)
  })

  it('activate() on success sets tier and active=true', async () => {
    mockFetch.mockResolvedValue({ data: { ok: true, tier: 'paid' }, error: null })
    const store = useLicenseStore()
    await store.activate('CFG-PRNG-TEST-1234-5678')
    expect(store.tier).toBe('paid')
    expect(store.active).toBe(true)
  })

  it('activate() on failure sets activateError', async () => {
    mockFetch.mockResolvedValue({ data: { ok: false, error: 'Invalid key' }, error: null })
    const store = useLicenseStore()
    await store.activate('bad-key')
    expect(store.activateError).toBe('Invalid key')
  })
})
