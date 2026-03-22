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
