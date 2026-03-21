import { describe, it, expect, vi, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useProfileStore } from './profile'

vi.mock('../../composables/useApi', () => ({ useApiFetch: vi.fn() }))
import { useApiFetch } from '../../composables/useApi'
const mockFetch = vi.mocked(useApiFetch)

describe('useProfileStore', () => {
  beforeEach(() => { setActivePinia(createPinia()); vi.clearAllMocks() })

  it('load() populates fields from API', async () => {
    mockFetch.mockResolvedValue({
      data: { name: 'Meg', email: 'meg@example.com', phone: '555-0100',
              linkedin_url: '', career_summary: '', candidate_voice: '',
              inference_profile: 'cpu', mission_preferences: [],
              nda_companies: [], accessibility_focus: false, lgbtq_focus: false },
      error: null,
    })
    const store = useProfileStore()
    await store.load()
    expect(store.name).toBe('Meg')
    expect(store.email).toBe('meg@example.com')
  })

  it('save() calls PUT /api/settings/profile', async () => {
    mockFetch.mockResolvedValue({ data: { ok: true }, error: null })
    const store = useProfileStore()
    store.name = 'Meg'
    await store.save()
    expect(mockFetch).toHaveBeenCalledWith('/api/settings/profile', expect.objectContaining({ method: 'PUT' }))
    expect(mockFetch).toHaveBeenCalledWith(
      '/api/settings/resume/sync-identity',
      expect.objectContaining({ method: 'POST' })
    )
  })

  it('save() error sets error state', async () => {
    mockFetch.mockResolvedValue({ data: null, error: { kind: 'network', message: 'fail' } })
    const store = useProfileStore()
    await store.save()
    expect(store.saveError).toBeTruthy()
  })
})
