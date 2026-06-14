import { describe, it, expect, vi, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useAiInterviewStore } from '../aiInterview'

vi.mock('../../../composables/useApi', () => ({ useApiFetch: vi.fn() }))
import { useApiFetch } from '../../../composables/useApi'
const mockFetch = vi.mocked(useApiFetch)

const LS_KEY = 'peregrine:wizard-draft'

describe('useAiInterviewStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
    localStorage.clear()
  })

  // ── restore() ──────────────────────────────────────────────────────────────

  it('restore() loads messages, fields, and complete from localStorage', () => {
    const draft = {
      messages: [{ role: 'assistant', content: 'Hello!' }],
      fields: { name: 'Alice' },
      complete: true,
    }
    localStorage.setItem(LS_KEY, JSON.stringify(draft))

    const store = useAiInterviewStore()
    store.restore()

    expect(store.messages).toEqual(draft.messages)
    expect(store.fields).toEqual(draft.fields)
    expect(store.complete).toBe(true)
  })

  it('restore() is a no-op when localStorage is empty', () => {
    const store = useAiInterviewStore()
    store.restore()
    expect(store.messages).toEqual([])
    expect(store.fields).toEqual({})
    expect(store.complete).toBe(false)
  })

  it('restore() ignores corrupted localStorage data without throwing', () => {
    localStorage.setItem(LS_KEY, '{not valid json}}}')
    const store = useAiInterviewStore()
    expect(() => store.restore()).not.toThrow()
    expect(store.messages).toEqual([])
  })

  // ── send() ─────────────────────────────────────────────────────────────────

  it('send() appends user message and assistant reply on success', async () => {
    mockFetch.mockResolvedValue({
      data: { reply: 'Nice to meet you!', extracted_fields: {}, complete: false },
      error: null,
    })

    const store = useAiInterviewStore()
    await store.send('Hello')

    expect(store.messages).toEqual([
      { role: 'user', content: 'Hello' },
      { role: 'assistant', content: 'Nice to meet you!' },
    ])
    expect(store.complete).toBe(false)
    expect(store.error).toBeNull()
  })

  it('send() does not add a user bubble for empty string (intro trigger)', async () => {
    mockFetch.mockResolvedValue({
      data: { reply: 'Welcome!', extracted_fields: {}, complete: false },
      error: null,
    })

    const store = useAiInterviewStore()
    await store.send('')

    expect(store.messages).toEqual([
      { role: 'assistant', content: 'Welcome!' },
    ])
  })

  it('send() merges extracted_fields into existing fields', async () => {
    mockFetch.mockResolvedValueOnce({
      data: { reply: 'Got it.', extracted_fields: { name: 'Alice' }, complete: false },
      error: null,
    })
    mockFetch.mockResolvedValueOnce({
      data: { reply: 'Thanks.', extracted_fields: { title: 'Engineer' }, complete: false },
      error: null,
    })

    const store = useAiInterviewStore()
    await store.send('My name is Alice')
    await store.send('I am an engineer')

    expect(store.fields).toEqual({ name: 'Alice', title: 'Engineer' })
  })

  it('send() sets complete flag when backend signals done', async () => {
    mockFetch.mockResolvedValue({
      data: { reply: 'All done!', extracted_fields: { name: 'Alice' }, complete: true },
      error: null,
    })

    const store = useAiInterviewStore()
    await store.send('done')

    expect(store.complete).toBe(true)
  })

  it('send() sets error and rolls back loading on API failure', async () => {
    mockFetch.mockResolvedValue({ data: null, error: { kind: 'network', message: 'fail' } })

    const store = useAiInterviewStore()
    await store.send('Hello')

    expect(store.error).toBe('Could not reach the assistant. Please try again.')
    expect(store.loading).toBe(false)
  })

  it('send() persists draft to localStorage on success', async () => {
    mockFetch.mockResolvedValue({
      data: { reply: 'Hi!', extracted_fields: { name: 'Bob' }, complete: false },
      error: null,
    })

    const store = useAiInterviewStore()
    await store.send('Hello')

    const stored = JSON.parse(localStorage.getItem(LS_KEY) ?? '{}')
    expect(stored.fields).toEqual({ name: 'Bob' })
  })

  // ── finalize() ─────────────────────────────────────────────────────────────

  it('finalize() calls the finalize API and clears localStorage on success', async () => {
    localStorage.setItem(LS_KEY, JSON.stringify({ messages: [], fields: { name: 'Alice' }, complete: true }))
    mockFetch.mockResolvedValue({ data: {}, error: null })

    const store = useAiInterviewStore()
    const ok = await store.finalize()

    expect(ok).toBe(true)
    expect(localStorage.getItem(LS_KEY)).toBeNull()
    expect(store.saving).toBe(false)
  })

  it('finalize() returns false and sets error on API failure', async () => {
    mockFetch.mockResolvedValue({ data: null, error: { kind: 'network', message: 'fail' } })

    const store = useAiInterviewStore()
    const ok = await store.finalize()

    expect(ok).toBe(false)
    expect(store.error).toBe('Failed to save profile. Please try again.')
  })

  // ── startOver() ────────────────────────────────────────────────────────────

  it('startOver() resets all state and clears localStorage', async () => {
    mockFetch.mockResolvedValue({
      data: { reply: 'Hi!', extracted_fields: { name: 'Alice' }, complete: true },
      error: null,
    })

    const store = useAiInterviewStore()
    await store.send('test')  // populates state and localStorage

    store.startOver()

    expect(store.messages).toEqual([])
    expect(store.fields).toEqual({})
    expect(store.complete).toBe(false)
    expect(store.error).toBeNull()
    expect(localStorage.getItem(LS_KEY)).toBeNull()
  })
})
