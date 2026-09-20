import { describe, it, expect, vi, beforeEach } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useWizardStore } from './wizard'

vi.mock('../composables/useApi', () => ({ useApiFetch: vi.fn() }))
import { useApiFetch } from '../composables/useApi'
const mockFetch = vi.mocked(useApiFetch)

describe('wizard store — complete', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  it('posts to /api/wizard/complete and returns true on success', async () => {
    mockFetch.mockResolvedValue({ data: { ok: true }, error: null } as never)

    const wizard = useWizardStore()
    const result = await wizard.complete()

    expect(result).toBe(true)
    expect(wizard.saving).toBe(false)
    expect(mockFetch).toHaveBeenCalledWith('/api/wizard/complete', { method: 'POST' })
  })

  it('returns false and records the error message on failure', async () => {
    mockFetch.mockResolvedValue({
      data: null,
      error: { kind: 'http', status: 500, detail: 'boom' },
    } as never)

    const wizard = useWizardStore()
    const result = await wizard.complete()

    expect(result).toBe(false)
    expect(wizard.saving).toBe(false)
    expect(wizard.errors).toEqual(['boom'])
  })
})
