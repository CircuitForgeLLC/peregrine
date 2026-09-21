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

  it('load() hydrates probeResults from the response so badges survive a reload', async () => {
    mockFetch.mockResolvedValue({
      data: {
        primary: null,
        research: { backend: 'ollama', model: 'llama3.1:8b' },
        chat: null,
        probes: { 'ollama:llama3.1:8b': { passed: false } },
      },
      error: null,
    })
    const store = useTaskModelsStore()
    await store.load()
    expect(store.probeResults['ollama:llama3.1:8b']).toEqual({ passed: false })
  })

  it('load() leaves probeResults empty when the response has no probes', async () => {
    mockFetch.mockResolvedValue({
      data: { primary: null, research: null, chat: null },
      error: null,
    })
    const store = useTaskModelsStore()
    await store.load()
    expect(store.probeResults).toEqual({})
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

  it('loadOllamaModels() with no args hits the endpoint with no query string', async () => {
    mockFetch.mockResolvedValue({ data: { models: ['llama3.1:8b'] }, error: null })
    const store = useTaskModelsStore()
    await store.loadOllamaModels()
    expect(mockFetch).toHaveBeenCalledWith('/api/settings/llm/ollama-models')
    expect(store.ollamaModels).toEqual(['llama3.1:8b'])
  })

  it('loadOllamaModels(host, port) queries that host directly', async () => {
    mockFetch.mockResolvedValue({ data: { models: ['llama3.1:8b'] }, error: null })
    const store = useTaskModelsStore()
    await store.loadOllamaModels('host.docker.internal', 11434)
    expect(mockFetch).toHaveBeenCalledWith('/api/settings/llm/ollama-models?host=host.docker.internal&port=11434')
  })

  it('loadVllmModels() populates vllmModels', async () => {
    mockFetch.mockResolvedValue({ data: { models: ['Qwen2.5-3B-Instruct'] }, error: null })
    const store = useTaskModelsStore()
    await store.loadVllmModels()
    expect(mockFetch).toHaveBeenCalledWith('/api/settings/llm/vllm-models')
    expect(store.vllmModels).toEqual(['Qwen2.5-3B-Instruct'])
  })

  it('loadVllmModels(host, port) queries that host directly', async () => {
    mockFetch.mockResolvedValue({ data: { models: [] }, error: null })
    const store = useTaskModelsStore()
    await store.loadVllmModels('host.docker.internal', 8000)
    expect(mockFetch).toHaveBeenCalledWith('/api/settings/llm/vllm-models?host=host.docker.internal&port=8000')
  })

  it('detectVllm() returns the found host', async () => {
    mockFetch.mockResolvedValue({ data: { found: true, host: 'host.docker.internal', port: 8000 }, error: null })
    const store = useTaskModelsStore()
    const result = await store.detectVllm(8000)
    expect(result).toEqual({ found: true, host: 'host.docker.internal', port: 8000 })
    expect(mockFetch).toHaveBeenCalledWith('/api/settings/system/vllm-detect', expect.objectContaining({
      method: 'POST',
      body: JSON.stringify({ port: 8000 }),
    }))
  })
})
