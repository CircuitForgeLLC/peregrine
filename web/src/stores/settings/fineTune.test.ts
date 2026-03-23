import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useFineTuneStore } from './fineTune'

vi.mock('../../composables/useApi', () => ({ useApiFetch: vi.fn() }))
import { useApiFetch } from '../../composables/useApi'
const mockFetch = vi.mocked(useApiFetch)

describe('useFineTuneStore', () => {
  beforeEach(() => { setActivePinia(createPinia()); vi.clearAllMocks(); vi.useFakeTimers() })
  afterEach(() => { vi.useRealTimers() })

  it('initial step is 1', () => {
    expect(useFineTuneStore().step).toBe(1)
  })

  it('resetStep() returns to step 1', () => {
    const store = useFineTuneStore()
    store.step = 3
    store.resetStep()
    expect(store.step).toBe(1)
  })

  it('loadStatus() sets inFlightJob when status is running', async () => {
    mockFetch.mockResolvedValue({ data: { status: 'running', pairs_count: 10 }, error: null })
    const store = useFineTuneStore()
    await store.loadStatus()
    expect(store.inFlightJob).toBe(true)
  })

  it('startPolling() calls loadStatus on interval', async () => {
    mockFetch.mockResolvedValue({ data: { status: 'idle' }, error: null })
    const store = useFineTuneStore()
    store.startPolling()
    await vi.advanceTimersByTimeAsync(4000)
    expect(mockFetch).toHaveBeenCalledWith('/api/settings/fine-tune/status')
    store.stopPolling()
  })
})
