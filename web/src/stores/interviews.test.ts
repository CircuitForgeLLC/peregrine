import { describe, it, expect, beforeEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useInterviewsStore } from './interviews'

vi.mock('../composables/useApi', () => ({
  useApiFetch: vi.fn(),
}))

import { useApiFetch } from '../composables/useApi'
const mockFetch = vi.mocked(useApiFetch)

const SAMPLE_JOBS = [
  { id: 1, title: 'CS Lead', company: 'Stripe', status: 'applied', match_score: 0.92, interview_date: null },
  { id: 2, title: 'CS Dir',  company: 'Notion', status: 'phone_screen', match_score: 0.78, interview_date: '2026-03-20T15:00:00' },
  { id: 3, title: 'VP CS',   company: 'Linear', status: 'hired', match_score: 0.95, interview_date: null },
]

describe('useInterviewsStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    mockFetch.mockResolvedValue({ data: SAMPLE_JOBS, error: null })
  })

  it('loads and groups jobs by status', async () => {
    const store = useInterviewsStore()
    await store.fetchAll()
    expect(store.applied).toHaveLength(1)
    expect(store.phoneScreen).toHaveLength(1)
    expect(store.hired).toHaveLength(1)
  })

  it('move updates status optimistically', async () => {
    mockFetch.mockResolvedValueOnce({ data: SAMPLE_JOBS, error: null })
    mockFetch.mockResolvedValueOnce({ data: null, error: null }) // move API
    const store = useInterviewsStore()
    await store.fetchAll()
    await store.move(1, 'phone_screen')
    expect(store.applied).toHaveLength(0)
    expect(store.phoneScreen).toHaveLength(2)
  })

  it('move rolls back on API error', async () => {
    mockFetch.mockResolvedValueOnce({ data: SAMPLE_JOBS, error: null })
    mockFetch.mockResolvedValueOnce({ data: null, error: { kind: 'http', status: 500, detail: 'err' } })
    const store = useInterviewsStore()
    await store.fetchAll()
    await store.move(1, 'phone_screen')
    expect(store.applied).toHaveLength(1)
  })
})
