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

  // Regression: the Suggest buttons on Search Prefs (titles/locations/
  // exclude keywords) gave zero feedback on either a request error or a
  // successful-but-empty response -- same silent-no-op shape as the Resume
  // Profile Suggest button. suggestTitles/suggestLocations/
  // suggestExcludeKeywords now surface both cases as a per-field message.
  it('suggestTitles() sets a field error when the request fails', async () => {
    mockFetch.mockResolvedValue({ data: null, error: { kind: 'network', message: 'boom' } })
    const store = useSearchStore()
    await store.suggestTitles()
    expect(store.suggestErrors.titles).toBeTruthy()
    expect(store.suggestingField).toBe(null)
  })

  it('suggestTitles() sets a field error when the LLM returns zero suggestions', async () => {
    mockFetch.mockResolvedValue({ data: { suggestions: [] }, error: null })
    const store = useSearchStore()
    await store.suggestTitles()
    expect(store.suggestErrors.titles).toBeTruthy()
  })

  it('suggestLocations() sets a field error on failure', async () => {
    mockFetch.mockResolvedValue({ data: null, error: { kind: 'network', message: 'boom' } })
    const store = useSearchStore()
    await store.suggestLocations()
    expect(store.suggestErrors.locations).toBeTruthy()
  })

  it('suggestExcludeKeywords() sets a field error on failure', async () => {
    mockFetch.mockResolvedValue({ data: null, error: { kind: 'network', message: 'boom' } })
    const store = useSearchStore()
    await store.suggestExcludeKeywords()
    expect(store.suggestErrors.exclude).toBeTruthy()
  })

  it('suggestTitles() clears a stale error on a successful non-empty response', async () => {
    const store = useSearchStore()
    store.suggestErrors.titles = 'stale error from a previous attempt'
    mockFetch.mockResolvedValue({ data: { suggestions: ['Staff Engineer'] }, error: null })
    await store.suggestTitles()
    expect(store.suggestErrors.titles).toBe(null)
  })
})
