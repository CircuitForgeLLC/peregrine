import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useSurveyStore } from './survey'

vi.mock('../composables/useApi', () => ({
  useApiFetch: vi.fn(),
}))

import { useApiFetch } from '../composables/useApi'

describe('useSurveyStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  it('fetchFor loads history and vision availability in parallel', async () => {
    const mockApiFetch = vi.mocked(useApiFetch)
    mockApiFetch
      .mockResolvedValueOnce({ data: [], error: null })                    // history
      .mockResolvedValueOnce({ data: { available: true }, error: null })   // vision

    const store = useSurveyStore()
    await store.fetchFor(1)

    expect(store.history).toEqual([])
    expect(store.visionAvailable).toBe(true)
    expect(store.currentJobId).toBe(1)
    expect(mockApiFetch).toHaveBeenCalledTimes(2)
  })

  it('fetchFor clears state when called for a different job', async () => {
    const mockApiFetch = vi.mocked(useApiFetch)
    // Job 1
    mockApiFetch
      .mockResolvedValueOnce({ data: [{ id: 1, llm_output: 'old' }], error: null })
      .mockResolvedValueOnce({ data: { available: false }, error: null })

    const store = useSurveyStore()
    await store.fetchFor(1)
    expect(store.history.length).toBe(1)

    // Job 2 — state must be cleared before new data arrives
    mockApiFetch
      .mockResolvedValueOnce({ data: [], error: null })
      .mockResolvedValueOnce({ data: { available: true }, error: null })

    await store.fetchFor(2)
    expect(store.history).toEqual([])
    expect(store.currentJobId).toBe(2)
  })

  it('analyze stores result including mode and rawInput', async () => {
    const mockApiFetch = vi.mocked(useApiFetch)
    mockApiFetch.mockResolvedValueOnce({
      data: { output: '1. B — reason', source: 'text_paste' },
      error: null,
    })

    const store = useSurveyStore()
    await store.analyze(1, { text: 'Q1: test', mode: 'quick' })

    expect(store.analysis).not.toBeNull()
    expect(store.analysis!.output).toBe('1. B — reason')
    expect(store.analysis!.source).toBe('text_paste')
    expect(store.analysis!.mode).toBe('quick')
    expect(store.analysis!.rawInput).toBe('Q1: test')
    expect(store.loading).toBe(false)
  })

  it('analyze sets error on failure', async () => {
    const mockApiFetch = vi.mocked(useApiFetch)
    mockApiFetch.mockResolvedValueOnce({
      data: null,
      error: { kind: 'http', status: 500, detail: 'LLM unavailable' },
    })

    const store = useSurveyStore()
    await store.analyze(1, { text: 'Q1: test', mode: 'quick' })

    expect(store.analysis).toBeNull()
    expect(store.error).toBeTruthy()
    expect(store.loading).toBe(false)
  })

  it('saveResponse prepends to history and clears analysis', async () => {
    const mockApiFetch = vi.mocked(useApiFetch)
    // Setup: fetchFor
    mockApiFetch
      .mockResolvedValueOnce({ data: [], error: null })
      .mockResolvedValueOnce({ data: { available: true }, error: null })

    const store = useSurveyStore()
    await store.fetchFor(1)

    // Set analysis state manually (as if analyze() was called)
    store.analysis = {
      output: '1. B — reason',
      source: 'text_paste',
      mode: 'quick',
      rawInput: 'Q1: test',
    }

    // Save
    mockApiFetch.mockResolvedValueOnce({
      data: { id: 42 },
      error: null,
    })

    await store.saveResponse(1, { surveyName: 'Round 1', reportedScore: '85%' })

    expect(store.history.length).toBe(1)
    expect(store.history[0].id).toBe(42)
    expect(store.history[0].llm_output).toBe('1. B — reason')
    expect(store.analysis).toBeNull()
    expect(store.saving).toBe(false)
  })

  it('clear resets all state to initial values', async () => {
    const mockApiFetch = vi.mocked(useApiFetch)
    mockApiFetch
      .mockResolvedValueOnce({ data: [{ id: 1, llm_output: 'test' }], error: null })
      .mockResolvedValueOnce({ data: { available: true }, error: null })

    const store = useSurveyStore()
    await store.fetchFor(1)

    store.clear()

    expect(store.history).toEqual([])
    expect(store.analysis).toBeNull()
    expect(store.visionAvailable).toBe(false)
    expect(store.loading).toBe(false)
    expect(store.saving).toBe(false)
    expect(store.error).toBeNull()
    expect(store.currentJobId).toBeNull()
  })
})
