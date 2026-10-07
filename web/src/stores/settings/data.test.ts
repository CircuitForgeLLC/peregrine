import { describe, it, expect, vi, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useDataStore } from './data'

vi.mock('../../composables/useApi', () => ({ useApiFetch: vi.fn() }))
import { useApiFetch } from '../../composables/useApi'
const mockFetch = vi.mocked(useApiFetch)

describe('useDataStore', () => {
  beforeEach(() => { setActivePinia(createPinia()); vi.clearAllMocks() })

  it('initial backupPath is null', () => {
    expect(useDataStore().backupPath).toBeNull()
  })

  it('createBackup() sets backupPath after success', async () => {
    mockFetch.mockResolvedValue({ data: { path: 'data/backup.zip', file_count: 12, size_bytes: 1024 }, error: null })
    const store = useDataStore()
    await store.createBackup(false)
    expect(store.backupPath).toBe('data/backup.zip')
  })
})

describe('useDataStore restore()', () => {
  beforeEach(() => { setActivePinia(createPinia()); vi.clearAllMocks() })

  const zip = () => new File(['PK'], 'backup.zip', { type: 'application/zip' })

  it('uploads the chosen zip as multipart form data', async () => {
    mockFetch.mockResolvedValue({ data: { restored: ['config/user.yaml'], skipped: [] }, error: null })
    await useDataStore().restore(zip())

    const [url, opts] = mockFetch.mock.calls[0]
    expect(url).toBe('/api/settings/data/backup/restore')
    expect(opts?.method).toBe('POST')
    expect((opts?.body as FormData).get('file')).toBeInstanceOf(File)
  })

  it('sends the custom header the server requires, and no Content-Type of its own', async () => {
    mockFetch.mockResolvedValue({ data: { restored: [], skipped: [] }, error: null })
    await useDataStore().restore(zip())

    const headers = mockFetch.mock.calls[0][1]?.headers as Record<string, string>
    expect(headers['X-Requested-With']).toBe('peregrine')
    expect(Object.keys(headers).map(k => k.toLowerCase())).not.toContain('content-type')
  })

  it('stores the result and clears any earlier error on success', async () => {
    const store = useDataStore()
    store.restoreError = 'old problem'
    mockFetch.mockResolvedValue({ data: { restored: ['config/user.yaml'], skipped: ['data/staging.db'] }, error: null })

    await store.restore(zip())

    expect(store.restoreResult).toEqual({ restored: ['config/user.yaml'], skipped: ['data/staging.db'] })
    expect(store.restoreError).toBeNull()
    expect(store.restoring).toBe(false)
  })

  it('shows the server message when the backup is rejected', async () => {
    mockFetch.mockResolvedValue({
      data: null,
      error: { kind: 'http', status: 400, detail: JSON.stringify({ detail: "That doesn't look like a Peregrine backup." }) },
    })
    const store = useDataStore()

    await store.restore(zip())

    expect(store.restoreError).toBe("That doesn't look like a Peregrine backup.")
    expect(store.restoreResult).toBeNull()
  })

  it('falls back to a plain message on a network failure', async () => {
    mockFetch.mockResolvedValue({ data: null, error: { kind: 'network', message: 'boom' } })
    const store = useDataStore()

    await store.restore(zip())

    expect(store.restoreError).toMatch(/restore failed/i)
    expect(store.restoring).toBe(false)
  })

  it('stays quiet in demo mode because the toast already explained', async () => {
    mockFetch.mockResolvedValue({ data: null, error: { kind: 'demo-blocked' } })
    const store = useDataStore()

    await store.restore(zip())

    expect(store.restoreError).toBeNull()
  })
})
