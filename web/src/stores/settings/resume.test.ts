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
})
