import { describe, it, expect, vi, beforeEach } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useWizardStore } from './wizard'

vi.mock('../composables/useApi', () => ({ useApiFetch: vi.fn() }))
import { useApiFetch } from '../composables/useApi'
const mockFetch = vi.mocked(useApiFetch)

describe('wizard store — loadStatus cloud auto-skip', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  it('auto-skips hardware, inference, and tier for a fresh cloud instance, preconfigured for cf-orch', async () => {
    mockFetch.mockResolvedValueOnce({
      data: { wizard_complete: false, wizard_step: 0, saved_data: {} },
      error: null,
    } as never)
    // saveStep(1), saveStep(2), saveStep(3) each POST /api/wizard/step
    mockFetch.mockResolvedValue({ data: { ok: true }, error: null } as never)

    const wizard = useWizardStore()
    const route = await wizard.loadStatus(true)

    expect(route).toBe('/setup/legacy/resume')
    expect(wizard.currentStep).toBe(4)

    // First saveStep call: hardware profile forced to cf-orch
    expect(mockFetch).toHaveBeenNthCalledWith(2, '/api/wizard/step', expect.objectContaining({
      body: JSON.stringify({ step: 1, data: { inference_profile: 'cf-orch' } }),
    }))
    // Second saveStep call: inference step advanced with no user-entered config
    // (cloud already has GPU_SERVER_URL configured server-side)
    expect(mockFetch).toHaveBeenNthCalledWith(3, '/api/wizard/step', expect.objectContaining({
      body: JSON.stringify({ step: 2, data: {} }),
    }))
    // Third saveStep call: tier comes from the account's license, not user choice
    expect(mockFetch).toHaveBeenNthCalledWith(4, '/api/wizard/step', expect.objectContaining({
      body: JSON.stringify({ step: 3, data: { tier: 'free' } }),
    }))
  })

  it('does not auto-skip for a self-hosted (non-cloud) instance', async () => {
    mockFetch.mockResolvedValueOnce({
      data: { wizard_complete: false, wizard_step: 0, saved_data: {} },
      error: null,
    } as never)

    const wizard = useWizardStore()
    const route = await wizard.loadStatus(false)

    expect(route).toBe('/setup/legacy/hardware')
    expect(mockFetch).toHaveBeenCalledTimes(1)
  })
})
