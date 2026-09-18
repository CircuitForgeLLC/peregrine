import { describe, it, expect, vi, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useTaskModelsStore } from './taskModels'

vi.mock('../../composables/useApi', () => ({ useApiFetch: vi.fn() }))
import { useApiFetch } from '../../composables/useApi'
const mockFetch = vi.mocked(useApiFetch)

describe('useTaskModelsStore', () => {
  beforeEach(() => { setActivePinia(createPinia()); vi.clearAllMocks() })

  it('load() populates primary/research/chat from the API', async () => {
    mockFetch.mockResolvedValue({
      data: {
        primary: { backend: 'ollama', model: 'meghan-cover-writer:latest' },
        research: { backend: 'ollama', model: 'llama3.1:8b' },
        chat: null,
      },
      error: null,
    })
    const store = useTaskModelsStore()
    await store.load()
    expect(store.primary).toEqual({ backend: 'ollama', model: 'meghan-cover-writer:latest' })
    expect(store.research?.model).toBe('llama3.1:8b')
    expect(store.chat).toBe(null)
  })

  it('save() PUTs the current assignments', async () => {
    mockFetch.mockResolvedValue({ data: { ok: true }, error: null })
    const store = useTaskModelsStore()
    store.research = { backend: 'ollama', model: 'llama3.1:8b' }
    await store.save()
    expect(mockFetch).toHaveBeenCalledWith('/api/settings/system/task-models', expect.objectContaining({
      method: 'PUT',
      body: JSON.stringify({ primary: null, research: { backend: 'ollama', model: 'llama3.1:8b' }, chat: null }),
    }))
  })

  it('save() sets saveError on failure', async () => {
    mockFetch.mockResolvedValue({ data: null, error: { kind: 'network', message: 'boom' } })
    const store = useTaskModelsStore()
    await store.save()
    expect(store.saveError).toBeTruthy()
  })

  it('probeModel() stores the result keyed by backend:model', async () => {
    mockFetch.mockResolvedValue({ data: { passed: true, checked_at: '2026-01-01' }, error: null })
    const store = useTaskModelsStore()
    await store.probeModel('ollama', 'llama3.1:8b')
    expect(store.probeResults['ollama:llama3.1:8b']).toEqual({ passed: true })
  })

  it('probeModel() treats an unreachable result as untested, not failed', async () => {
    mockFetch.mockResolvedValue({ data: { error: 'unreachable' }, error: null })
    const store = useTaskModelsStore()
    await store.probeModel('ollama', 'llama3.1:8b')
    expect(store.probeResults['ollama:llama3.1:8b']).toBeUndefined()
  })

  it('detectOllama() returns the found host', async () => {
    mockFetch.mockResolvedValue({ data: { found: true, host: 'host.docker.internal', port: 11434 }, error: null })
    const store = useTaskModelsStore()
    const result = await store.detectOllama(11434)
    expect(result).toEqual({ found: true, host: 'host.docker.internal', port: 11434 })
  })
})
