import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useFineTuneStore } from './fineTune'
import type { DbPair } from './fineTune'

vi.mock('../../composables/useApi', () => ({ useApiFetch: vi.fn() }))
vi.mock('../appConfig', () => ({ useAppConfigStore: vi.fn(() => ({ isDemo: false })) }))
vi.mock('../../composables/useToast', () => ({ showToast: vi.fn() }))
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

  it('toggleOptIn updates optedIn state', async () => {
    mockFetch.mockResolvedValue({ data: { ok: true, enabled: true }, error: null })
    const store = useFineTuneStore()
    await store.toggleOptIn(true)
    expect(store.optedIn).toBe(true)
  })

  it('loadDbPairs no-ops when not opted in', async () => {
    const store = useFineTuneStore()
    store.optedIn = false
    await store.loadDbPairs()
    expect(store.dbPairs).toEqual([])
    expect(mockFetch).not.toHaveBeenCalledWith('/api/settings/fine-tune/db-pairs')
  })

  it('loadDbPairs fetches when opted in', async () => {
    const pairs: DbPair[] = [{ job_id: 1, title: 'Eng', company: 'Acme', status: 'applied', instruction: 'Write...', input_preview: 'Build', excluded: false }]
    mockFetch.mockResolvedValue({ data: { pairs, total: 1, excluded_count: 0 }, error: null })
    const store = useFineTuneStore()
    store.optedIn = true
    await store.loadDbPairs()
    expect(store.dbPairs).toHaveLength(1)
  })

  it('excludeDbPair marks pair excluded and increments count', async () => {
    mockFetch.mockResolvedValue({ data: { ok: true }, error: null })
    const store = useFineTuneStore()
    store.dbPairs = [{ job_id: 1, title: 'Eng', company: 'Acme', status: 'applied', instruction: 'Write...', input_preview: 'Build', excluded: false }]
    await store.excludeDbPair(1)
    expect(store.dbPairs[0].excluded).toBe(true)
    expect(store.dbExcludedCount).toBe(1)
  })

  it('includeDbPair marks pair included and decrements excludedCount', async () => {
    mockFetch.mockResolvedValue({ data: { ok: true }, error: null })
    const store = useFineTuneStore()
    store.dbPairs = [{ job_id: 1, title: 'Eng', company: 'Acme', status: 'applied', instruction: 'Write...', input_preview: 'Build', excluded: true }]
    store.dbExcludedCount = 1
    await store.includeDbPair(1)
    expect(store.dbPairs[0].excluded).toBe(false)
    expect(store.dbExcludedCount).toBe(0)
  })
})
