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

  // ── seedFields() ───────────────────────────────────────────────────────────
  // Deterministic data already known from the resume parse / identity step
  // must never be re-asked by the LLM.

  it('seedFields() fills in fields not already present', () => {
    const store = useAiInterviewStore()
    store.seedFields({ name: 'Alex Rivera', email: 'alex@example.com', linkedin: '' })

    expect(store.fields).toEqual({ name: 'Alex Rivera', email: 'alex@example.com' })
  })

  it('seedFields() never overwrites a field already present', () => {
    const store = useAiInterviewStore()
    store.fields.name = 'Chat-provided Name'

    store.seedFields({ name: 'Resume Name', email: 'from-resume@example.com' })

    expect(store.fields.name).toBe('Chat-provided Name')
    expect(store.fields.email).toBe('from-resume@example.com')
  })

  it('seedFields() skips null, undefined, and empty-string values', () => {
    const store = useAiInterviewStore()
    store.seedFields({ name: undefined, email: null, linkedin: '' })

    expect(store.fields).toEqual({})
  })

  it('seedFields() persists to localStorage', () => {
    const store = useAiInterviewStore()
    store.seedFields({ name: 'Alex Rivera' })

    const stored = JSON.parse(localStorage.getItem(LS_KEY) ?? '{}')
    expect(stored.fields).toEqual({ name: 'Alex Rivera' })
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

  // ── askingAbout ────────────────────────────────────────────────────────────
  // Regression coverage: the UI previously guessed which field was being
  // asked about by keyword-matching the reply text ("writing", "voice",
  // "cover letter"), which false-positived on unrelated questions (e.g. a
  // career_summary question containing the word "writing"). The backend now
  // reports this explicitly.

  it('send() tracks the asking_about field reported by the backend', async () => {
    mockFetch.mockResolvedValue({
      data: {
        reply: "What's your preferred writing tone?",
        extracted_fields: {},
        complete: false,
        asking_about: 'candidate_voice',
      },
      error: null,
    })

    const store = useAiInterviewStore()
    await store.send('Hello')

    expect(store.askingAbout).toBe('candidate_voice')
  })

  it('send() clears askingAbout when the backend reports null', async () => {
    mockFetch.mockResolvedValueOnce({
      data: { reply: 'What tone?', extracted_fields: {}, complete: false, asking_about: 'candidate_voice' },
      error: null,
    })
    mockFetch.mockResolvedValueOnce({
      data: { reply: 'Great, thanks!', extracted_fields: {}, complete: false, asking_about: null },
      error: null,
    })

    const store = useAiInterviewStore()
    await store.send('first')
    expect(store.askingAbout).toBe('candidate_voice')
    await store.send('warm and conversational')
    expect(store.askingAbout).toBeNull()
  })

  it('startOver() resets askingAbout', async () => {
    mockFetch.mockResolvedValue({
      data: { reply: 'Tone?', extracted_fields: {}, complete: false, asking_about: 'candidate_voice' },
      error: null,
    })
    const store = useAiInterviewStore()
    await store.send('hi')
    expect(store.askingAbout).toBe('candidate_voice')

    store.startOver()
    expect(store.askingAbout).toBeNull()
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

  // ── 503 llm_error surfacing ───────────────────────────────────────────────
  // The backend's LLMRouter reports *why* each backend was skipped (unreachable,
  // missing API key, model not pulled, etc). Previously this store discarded
  // that detail and always guessed "add an API key", which was actively wrong
  // when e.g. the real issue was an Ollama model tag that was never pulled.

  it('send() surfaces the backend-provided message on a 503 llm_error', async () => {
    mockFetch.mockResolvedValue({
      data: null,
      error: {
        kind: 'http',
        status: 503,
        detail: JSON.stringify({
          detail: {
            error: 'llm_error',
            message: 'All LLM backends exhausted. Tried: ollama: model "llama3.2:3b" not found',
          },
        }),
      },
    })

    const store = useAiInterviewStore()
    await store.send('Hello')

    expect(store.error).toBe(
      "Couldn't reach the AI assistant: All LLM backends exhausted. Tried: ollama: model \"llama3.2:3b\" not found",
    )
  })

  it('send() falls back to a generic message on a 503 with no llm_error detail', async () => {
    mockFetch.mockResolvedValue({
      data: null,
      error: { kind: 'http', status: 503, detail: JSON.stringify({ detail: 'Service Unavailable' }) },
    })

    const store = useAiInterviewStore()
    await store.send('Hello')

    expect(store.error).toBe('Could not reach the assistant. Please try again.')
  })

  it('send() falls back to a generic message when 503 body is not valid JSON', async () => {
    mockFetch.mockResolvedValue({
      data: null,
      error: { kind: 'http', status: 503, detail: 'not json' },
    })

    const store = useAiInterviewStore()
    await store.send('Hello')

    expect(store.error).toBe('Could not reach the assistant. Please try again.')
  })

  it('send() tells the user to start over on a 422 (corrupted history)', async () => {
    mockFetch.mockResolvedValue({
      data: null,
      error: { kind: 'http', status: 422, detail: JSON.stringify({ detail: [] }) },
    })

    const store = useAiInterviewStore()
    await store.send('Hello')

    expect(store.error).toBe("This conversation hit an unexpected error and can't continue. Please start over.")
  })

  it('send() never pushes a non-string reply into message history', async () => {
    mockFetch.mockResolvedValue({
      data: { reply: null as unknown as string, extracted_fields: null as unknown as Record<string, unknown>, complete: false },
      error: null,
    })

    const store = useAiInterviewStore()
    await store.send('Hello')

    expect(store.messages[store.messages.length - 1]).toEqual({ role: 'assistant', content: '' })
    expect(store.fields).toEqual({})
  })

  it('send() sets a fixed message on a 402 tier-gate error', async () => {
    mockFetch.mockResolvedValue({
      data: null,
      error: { kind: 'http', status: 402, detail: JSON.stringify({ detail: { error: 'tier_required' } }) },
    })

    const store = useAiInterviewStore()
    await store.send('Hello')

    expect(store.error).toBe('AI profile assistant requires a Paid plan or a BYOK API key.')
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

  // ── skip() ─────────────────────────────────────────────────────────────────

  it('skip() sends the skip signal to the backend', async () => {
    mockFetch.mockResolvedValue({
      data: { reply: 'No problem, moving on.', extracted_fields: {}, complete: false },
      error: null,
    })

    const store = useAiInterviewStore()
    await store.skip()

    expect(mockFetch).toHaveBeenCalledWith(
      '/api/wizard/ai/interview',
      expect.objectContaining({ method: 'POST' }),
    )
    const body = JSON.parse((mockFetch.mock.calls[0][1] as { body: string }).body)
    expect(body.history[0]).toEqual({ role: 'user', content: 'skip' })
  })

  // ── Content-Type header regression ──────────────────────────────────────────
  // useApiFetch is a thin wrapper over raw fetch() with no default headers.
  // Without an explicit Content-Type, the browser sends a stringified JSON
  // body as text/plain, which FastAPI can't parse — it 422s the request
  // before it ever reaches the LLM, surfacing as a generic "Could not reach
  // the assistant" error with no indication it never left the browser.

  it('send() sets Content-Type: application/json', async () => {
    mockFetch.mockResolvedValue({
      data: { reply: 'Hi!', extracted_fields: {}, complete: false },
      error: null,
    })
    const store = useAiInterviewStore()
    await store.send('hello')

    expect(mockFetch).toHaveBeenCalledWith(
      '/api/wizard/ai/interview',
      expect.objectContaining({ headers: { 'Content-Type': 'application/json' } }),
    )
  })

  it('finalize() sets Content-Type: application/json', async () => {
    mockFetch.mockResolvedValue({ data: {}, error: null })
    const store = useAiInterviewStore()
    await store.finalize()

    expect(mockFetch).toHaveBeenCalledWith(
      '/api/wizard/ai/finalize',
      expect.objectContaining({ headers: { 'Content-Type': 'application/json' } }),
    )
  })

  // ── keepChatting() ─────────────────────────────────────────────────────────

  it('keepChatting() clears the complete flag without resetting messages', async () => {
    mockFetch.mockResolvedValue({
      data: { reply: 'All done!', extracted_fields: { name: 'Alice' }, complete: true },
      error: null,
    })

    const store = useAiInterviewStore()
    await store.send('done')
    expect(store.complete).toBe(true)

    store.keepChatting()

    expect(store.complete).toBe(false)
    expect(store.messages.length).toBeGreaterThan(0)
    expect(store.fields).toEqual({ name: 'Alice' })
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
