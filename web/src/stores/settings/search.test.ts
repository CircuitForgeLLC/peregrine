import { describe, it, expect, vi, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useSearchStore } from './search'

vi.mock('../../composables/useApi', () => ({ useApiFetch: vi.fn() }))
import { useApiFetch } from '../../composables/useApi'
const mockFetch = vi.mocked(useApiFetch)

describe('useSearchStore', () => {
  beforeEach(() => { setActivePinia(createPinia()); vi.clearAllMocks() })

  it('defaults remote_preference to both', () => {
    expect(useSearchStore().remote_preference).toBe('both')
  })

  it('load() sets fields from API', async () => {
    mockFetch.mockResolvedValue({ data: {
      remote_preference: 'remote', job_titles: ['Engineer'], locations: ['NYC'],
      exclude_keywords: [], job_boards: [], custom_board_urls: [],
      blocklist_companies: [], blocklist_industries: [], blocklist_locations: [],
    }, error: null })
    const store = useSearchStore()
    await store.load()
    expect(store.remote_preference).toBe('remote')
    expect(store.job_titles).toContain('Engineer')
  })

  it('suggest() adds to titleSuggestions without persisting', async () => {
    mockFetch.mockResolvedValue({ data: { suggestions: ['Staff Engineer'] }, error: null })
    const store = useSearchStore()
    await store.suggestTitles()
    expect(store.titleSuggestions).toContain('Staff Engineer')
    expect(store.job_titles).not.toContain('Staff Engineer')
  })

  it('save() calls PUT endpoint', async () => {
    mockFetch.mockResolvedValue({ data: { ok: true }, error: null })
    const store = useSearchStore()
    await store.save()
    expect(mockFetch).toHaveBeenCalledWith('/api/settings/search', expect.objectContaining({ method: 'PUT' }))
  })
})
