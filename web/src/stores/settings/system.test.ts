import { describe, it, expect, vi, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useSystemStore } from './system'

vi.mock('../../composables/useApi', () => ({ useApiFetch: vi.fn() }))
import { useApiFetch } from '../../composables/useApi'
const mockFetch = vi.mocked(useApiFetch)

describe('useSystemStore — BYOK gate', () => {
  beforeEach(() => { setActivePinia(createPinia()); vi.clearAllMocks() })

  it('save() proceeds without modal when no cloud backends enabled', async () => {
    mockFetch.mockResolvedValue({ data: { ok: true }, error: null })
    const store = useSystemStore()
    store.backends = [{ id: 'ollama', enabled: true, priority: 1 }]
    store.byokAcknowledged = []
    await store.trySave()
    expect(store.byokPending).toHaveLength(0)
    expect(mockFetch).toHaveBeenCalledWith('/api/settings/system/llm', expect.anything())
  })

  it('save() sets byokPending when new cloud backend enabled', async () => {
    const store = useSystemStore()
    store.backends = [{ id: 'anthropic', enabled: true, priority: 1 }]
    store.byokAcknowledged = []
    await store.trySave()
    expect(store.byokPending).toContain('anthropic')
    expect(mockFetch).not.toHaveBeenCalledWith('/api/settings/system/llm', expect.anything())
  })

  it('save() skips modal for already-acknowledged backends', async () => {
    mockFetch.mockResolvedValue({ data: { ok: true }, error: null })
    const store = useSystemStore()
    store.backends = [{ id: 'anthropic', enabled: true, priority: 1 }]
    store.byokAcknowledged = ['anthropic']
    await store.trySave()
    expect(store.byokPending).toHaveLength(0)
  })

  it('confirmByok() saves acknowledgment then commits LLM config', async () => {
    mockFetch.mockResolvedValue({ data: { ok: true }, error: null })
    const store = useSystemStore()
    store.byokPending = ['anthropic']
    store.backends = [{ id: 'anthropic', enabled: true, priority: 1 }]
    await store.confirmByok()
    expect(mockFetch).toHaveBeenCalledWith('/api/settings/system/llm/byok-ack', expect.anything())
    expect(mockFetch).toHaveBeenCalledWith('/api/settings/system/llm', expect.anything())
  })

  it('confirmByok() sets saveError and leaves modal open when ack POST fails', async () => {
    mockFetch.mockResolvedValue({ data: null, error: 'Network error' })
    const store = useSystemStore()
    store.byokPending = ['anthropic']
    store.backends = [{ id: 'anthropic', enabled: true, priority: 1 }]
    await store.confirmByok()
    expect(store.saveError).toBeTruthy()
    expect(store.byokPending).toContain('anthropic')  // modal stays open
    expect(mockFetch).not.toHaveBeenCalledWith('/api/settings/system/llm', expect.anything())
  })

  it('cancelByok() clears pending and restores backends to pre-save state', async () => {
    mockFetch.mockResolvedValue({ data: { ok: true }, error: null })
    const store = useSystemStore()
    const original = [{ id: 'ollama', enabled: true, priority: 1 }]
    store.backends = [...original]
    await store.trySave()  // captures snapshot, commits (no cloud backends)
    store.backends = [{ id: 'anthropic', enabled: true, priority: 1 }]
    store.byokPending = ['anthropic']
    store.cancelByok()
    expect(store.byokPending).toHaveLength(0)
    expect(store.backends).toEqual(original)
  })
})

describe('useSystemStore — services', () => {
  it('loadServices() populates services list', async () => {
    mockFetch.mockResolvedValue({ data: [{ name: 'ollama', port: 11434, running: true, note: '' }], error: null })
    const store = useSystemStore()
    await store.loadServices()
    expect(store.services[0].name).toBe('ollama')
    expect(store.services[0].running).toBe(true)
  })
})
