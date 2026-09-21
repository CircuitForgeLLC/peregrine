import { describe, it, expect, vi, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useOnboardingHubStore } from './onboardingHub'

vi.mock('../composables/useApi', () => ({ useApiFetch: vi.fn() }))
import { useApiFetch } from '../composables/useApi'
const mockFetch = vi.mocked(useApiFetch)

describe('useOnboardingHubStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  it('loadSections() fetches and stores the sections map from wizard status', async () => {
    mockFetch.mockResolvedValue({
      data: {
        wizard_complete: false,
        wizard_step: 0,
        saved_data: {},
        sections: { profile: true, resume: false, search: false, compute_backend: true },
      },
      error: null,
    } as never)

    const store = useOnboardingHubStore()
    await store.loadSections()

    expect(store.sections).toEqual({
      profile: true, resume: false, search: false, compute_backend: true,
    })
    expect(mockFetch).toHaveBeenCalledWith('/api/wizard/status')
  })

  it('loadSections() sets loading false and leaves sections at defaults on fetch failure', async () => {
    mockFetch.mockResolvedValue({ data: null, error: { kind: 'network', message: 'fail' } } as never)

    const store = useOnboardingHubStore()
    await store.loadSections()

    expect(store.loading).toBe(false)
    expect(store.sections).toEqual({
      profile: false, resume: false, search: false, compute_backend: false,
    })
  })

  it('loadSections() sets loading true during the fetch', async () => {
    let resolveFetch: (v: unknown) => void = () => {}
    mockFetch.mockReturnValue(new Promise(resolve => { resolveFetch = resolve }) as never)

    const store = useOnboardingHubStore()
    const promise = store.loadSections()
    expect(store.loading).toBe(true)

    resolveFetch({ data: { sections: { profile: false, resume: false, search: false, compute_backend: false } }, error: null })
    await promise
    expect(store.loading).toBe(false)
  })
})
