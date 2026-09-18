import { describe, it, expect, vi, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useResumeStore } from './resume'

vi.mock('../../composables/useApi', () => ({ useApiFetch: vi.fn() }))
import { useApiFetch } from '../../composables/useApi'
const mockFetch = vi.mocked(useApiFetch)

describe('useResumeStore', () => {
  beforeEach(() => { setActivePinia(createPinia()); vi.clearAllMocks() })

  it('hasResume is false before load', () => {
    expect(useResumeStore().hasResume).toBe(false)
  })

  it('load() sets hasResume from API exists flag', async () => {
    mockFetch.mockResolvedValue({ data: { exists: true, name: 'Meg', email: '', phone: '',
      linkedin_url: '', surname: '', address: '', city: '', zip_code: '', date_of_birth: '',
      experience: [], salary_min: 0, salary_max: 0, notice_period: '', remote: false,
      relocation: false, assessment: false, background_check: false,
      gender: '', pronouns: '', ethnicity: '', veteran_status: '', disability: '',
      skills: [], domains: [], keywords: [],
    }, error: null })
    const store = useResumeStore()
    await store.load()
    expect(store.hasResume).toBe(true)
  })

  it('syncFromProfile() copies identity fields', () => {
    const store = useResumeStore()
    store.syncFromProfile({ name: 'Test', email: 'a@b.com', phone: '555', linkedin_url: 'li.com/test' })
    expect(store.name).toBe('Test')
    expect(store.email).toBe('a@b.com')
  })

  it('load() empty-state when exists=false', async () => {
    mockFetch.mockResolvedValue({ data: { exists: false }, error: null })
    const store = useResumeStore()
    await store.load()
    expect(store.hasResume).toBe(false)
  })

  it('load() sets loadError on API error', async () => {
    mockFetch.mockResolvedValue({ data: null, error: { kind: 'network', message: 'Network error' } })
    const store = useResumeStore()
    await store.load()
    expect(store.loadError).toBeTruthy()
    expect(store.hasResume).toBe(false)
  })

  // Regression: `.map() ?? []` (nullish-coalescing applied AFTER calling
  // .map()) throws synchronously if experience is undefined, aborting the
  // rest of load() before skills/education/achievements ever populate --
  // a resume that parsed correctly on the backend showed as missing work
  // experience AND skills on the Settings page, since both never got a
  // chance to load. The safe pattern is `(x ?? []).map()`.
  it('load() populates skills and education even when experience is missing from the response', async () => {
    mockFetch.mockResolvedValue({
      data: {
        exists: true, name: 'Meg', email: '', phone: '', linkedin_url: '',
        surname: '', address: '', city: '', zip_code: '', date_of_birth: '',
        // experience deliberately omitted, matching a resume file the parser
        // wrote without that key
        salary_min: 0, salary_max: 0, notice_period: '', remote: false,
        relocation: false, assessment: false, background_check: false,
        gender: '', pronouns: '', ethnicity: '', veteran_status: '', disability: '',
        skills: ['Python', 'TypeScript'], domains: [], keywords: [],
        career_summary: '', education: [], achievements: ['Shipped a thing'],
      },
      error: null,
    })
    const store = useResumeStore()
    await store.load()
    expect(store.experience).toEqual([])
    expect(store.skills).toEqual(['Python', 'TypeScript'])
    expect(store.achievements).toEqual(['Shipped a thing'])
  })

  it('load() populates experience entries with generated ids when present', async () => {
    mockFetch.mockResolvedValue({
      data: {
        exists: true, name: 'Meg', email: '', phone: '', linkedin_url: '',
        surname: '', address: '', city: '', zip_code: '', date_of_birth: '',
        experience: [{ title: 'Engineer', company: 'Acme', period: '2020-present', location: '', industry: '', responsibilities: '', skills: [] }],
        salary_min: 0, salary_max: 0, notice_period: '', remote: false,
        relocation: false, assessment: false, background_check: false,
        gender: '', pronouns: '', ethnicity: '', veteran_status: '', disability: '',
        skills: [], domains: [], keywords: [],
      },
      error: null,
    })
    const store = useResumeStore()
    await store.load()
    expect(store.experience).toHaveLength(1)
    expect(store.experience[0].title).toBe('Engineer')
    expect(store.experience[0].id).toBeTruthy()
  })

  // Regression: the Suggest button silently did nothing when the LLM
  // returned no usable suggestions -- no error, no empty state, just a
  // button that looked broken. suggestTags() now surfaces both failure
  // modes (a request error, and a successful-but-empty response) as a
  // per-field message instead of failing silently.
  it('suggestTags() sets a per-field error when the request fails', async () => {
    mockFetch.mockResolvedValue({ data: null, error: { kind: 'network', message: 'boom' } })
    const store = useResumeStore()
    await store.suggestTags('skills')
    expect(store.suggestErrors.skills).toBeTruthy()
    expect(store.suggestingField).toBe(null)
  })

  it('suggestTags() sets a per-field error when the LLM returns zero suggestions', async () => {
    mockFetch.mockResolvedValue({ data: { suggestions: [] }, error: null })
    const store = useResumeStore()
    await store.suggestTags('domains')
    expect(store.suggestErrors.domains).toBeTruthy()
    expect(store.domainSuggestions).toEqual([])
  })

  it('suggestTags() clears the field error on a successful non-empty response', async () => {
    const store = useResumeStore()
    store.suggestErrors.keywords = 'stale error from a previous attempt'
    mockFetch.mockResolvedValue({ data: { suggestions: ['SQL', 'Tableau'] }, error: null })
    await store.suggestTags('keywords')
    expect(store.suggestErrors.keywords).toBe(null)
    expect(store.keywordSuggestions).toEqual(['SQL', 'Tableau'])
  })
})
