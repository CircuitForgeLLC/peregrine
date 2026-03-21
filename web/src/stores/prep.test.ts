import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { usePrepStore } from './prep'

// Mock useApiFetch
vi.mock('../composables/useApiFetch', () => ({
  useApiFetch: vi.fn(),
}))

import { useApiFetch } from '../composables/useApiFetch'

describe('usePrepStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.clearAllMocks()
  })

  it('fetchFor loads research, contacts, task, and full job in parallel', async () => {
    const mockApiFetch = vi.mocked(useApiFetch)
    mockApiFetch
      .mockResolvedValueOnce({ company_brief: 'Acme', ceo_brief: null, talking_points: null,
        tech_brief: null, funding_brief: null, red_flags: null, accessibility_brief: null,
        generated_at: '2026-03-20T12:00:00' })  // research
      .mockResolvedValueOnce([])                  // contacts
      .mockResolvedValueOnce({ status: 'none', stage: null, message: null }) // task
      .mockResolvedValueOnce({ id: 1, title: 'Engineer', company: 'Acme', url: null,
        description: 'Build things.', cover_letter: null, match_score: 80,
        keyword_gaps: null })                     // fullJob

    const store = usePrepStore()
    await store.fetchFor(1)

    expect(store.research?.company_brief).toBe('Acme')
    expect(store.contacts).toEqual([])
    expect(store.taskStatus.status).toBe('none')
    expect(store.fullJob?.description).toBe('Build things.')
    expect(store.currentJobId).toBe(1)
  })

  it('fetchFor clears state when called for a different job', async () => {
    const mockApiFetch = vi.mocked(useApiFetch)
    // First call for job 1
    mockApiFetch
      .mockResolvedValueOnce({ company_brief: 'OldCo', ceo_brief: null, talking_points: null,
        tech_brief: null, funding_brief: null, red_flags: null, accessibility_brief: null,
        generated_at: null })
      .mockResolvedValueOnce([])
      .mockResolvedValueOnce({ status: 'none', stage: null, message: null })
      .mockResolvedValueOnce({ id: 1, title: 'Old Job', company: 'OldCo', url: null,
        description: null, cover_letter: null, match_score: null, keyword_gaps: null })

    const store = usePrepStore()
    await store.fetchFor(1)
    expect(store.research?.company_brief).toBe('OldCo')

    // Second call for job 2 - clears first
    mockApiFetch
      .mockResolvedValueOnce(null)  // 404 → null
      .mockResolvedValueOnce([])
      .mockResolvedValueOnce({ status: 'none', stage: null, message: null })
      .mockResolvedValueOnce({ id: 2, title: 'New Job', company: 'NewCo', url: null,
        description: null, cover_letter: null, match_score: null, keyword_gaps: null })

    await store.fetchFor(2)
    expect(store.research).toBeNull()
    expect(store.currentJobId).toBe(2)
  })

  it('generateResearch calls POST then starts polling', async () => {
    const mockApiFetch = vi.mocked(useApiFetch)
    mockApiFetch.mockResolvedValueOnce({ task_id: 7, is_new: true })

    const store = usePrepStore()
    store.currentJobId = 1

    // Spy on pollTask via the interval
    const pollSpy = mockApiFetch
      .mockResolvedValueOnce({ status: 'running', stage: 'Analyzing', message: null })

    await store.generateResearch(1)

    // Advance timer one tick — should poll
    await vi.advanceTimersByTimeAsync(3000)

    // Should have called POST generate + poll task
    expect(mockApiFetch).toHaveBeenCalledWith(
      expect.stringContaining('/research/generate'),
      expect.objectContaining({ method: 'POST' })
    )
  })

  it('pollTask stops when status is completed and re-fetches research', async () => {
    const mockApiFetch = vi.mocked(useApiFetch)
    // Set up store with a job loaded
    mockApiFetch
      .mockResolvedValueOnce({ company_brief: 'Acme', ceo_brief: null, talking_points: null,
        tech_brief: null, funding_brief: null, red_flags: null, accessibility_brief: null,
        generated_at: null })
      .mockResolvedValueOnce([])
      .mockResolvedValueOnce({ status: 'none', stage: null, message: null })
      .mockResolvedValueOnce({ id: 1, title: 'Eng', company: 'Acme', url: null,
        description: null, cover_letter: null, match_score: null, keyword_gaps: null })

    const store = usePrepStore()
    await store.fetchFor(1)

    // Mock first poll → completed
    mockApiFetch
      .mockResolvedValueOnce({ status: 'completed', stage: null, message: null })
      // re-fetch on completed: research, contacts, task, fullJob
      .mockResolvedValueOnce({ company_brief: 'Updated!', ceo_brief: null, talking_points: null,
        tech_brief: null, funding_brief: null, red_flags: null, accessibility_brief: null,
        generated_at: '2026-03-20T13:00:00' })
      .mockResolvedValueOnce([])
      .mockResolvedValueOnce({ status: 'completed', stage: null, message: null })
      .mockResolvedValueOnce({ id: 1, title: 'Eng', company: 'Acme', url: null,
        description: 'Now with content', cover_letter: null, match_score: null, keyword_gaps: null })

    store.pollTask(1)
    await vi.advanceTimersByTimeAsync(3000)
    await vi.runAllTimersAsync()

    expect(store.research?.company_brief).toBe('Updated!')
  })

  it('clear cancels polling interval and resets state', async () => {
    const mockApiFetch = vi.mocked(useApiFetch)
    mockApiFetch
      .mockResolvedValueOnce({ company_brief: 'Acme', ceo_brief: null, talking_points: null,
        tech_brief: null, funding_brief: null, red_flags: null, accessibility_brief: null,
        generated_at: null })
      .mockResolvedValueOnce([])
      .mockResolvedValueOnce({ status: 'none', stage: null, message: null })
      .mockResolvedValueOnce({ id: 1, title: 'Eng', company: 'Acme', url: null,
        description: null, cover_letter: null, match_score: null, keyword_gaps: null })

    const store = usePrepStore()
    await store.fetchFor(1)
    store.pollTask(1)

    store.clear()

    // Advance timers — if polling wasn't cancelled, fetchFor would be called again
    const callCountBeforeClear = mockApiFetch.mock.calls.length
    await vi.advanceTimersByTimeAsync(9000)
    expect(mockApiFetch.mock.calls.length).toBe(callCountBeforeClear)

    expect(store.research).toBeNull()
    expect(store.contacts).toEqual([])
    expect(store.currentJobId).toBeNull()
  })
})
