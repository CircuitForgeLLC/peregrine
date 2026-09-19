import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import SystemSettingsView from './SystemSettingsView.vue'
import { useAppConfigStore } from '../../stores/appConfig'

vi.mock('../../composables/useApi', () => ({ useApiFetch: vi.fn() }))
import { useApiFetch } from '../../composables/useApi'
const mockFetch = vi.mocked(useApiFetch)

describe('SystemSettingsView, Compute & AI Backend section', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
    mockFetch.mockResolvedValue({ data: {}, error: null } as never)
  })

  it('shows the section only when not cloud', () => {
    const config = useAppConfigStore()
    config.isCloud = false
    const wrapper = mount(SystemSettingsView)
    expect(wrapper.text()).toContain('Compute & AI Backend')
  })

  it('hides the section in cloud mode', () => {
    const config = useAppConfigStore()
    config.isCloud = true
    const wrapper = mount(SystemSettingsView)
    expect(wrapper.text()).not.toContain('Compute & AI Backend')
  })
})

describe('SystemSettingsView, Ollama model download', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  function mockRoutes(routes: Record<string, unknown>) {
    mockFetch.mockImplementation((url: string) => {
      if (url in routes) return Promise.resolve({ data: routes[url], error: null }) as never
      return Promise.resolve({ data: {}, error: null }) as never
    })
  }

  it('shows the configured model as installed when it is in the models list', async () => {
    const config = useAppConfigStore()
    config.isCloud = false
    mockRoutes({
      '/api/settings/system/llm-backend': { ollama_model: 'llama3.1:8b' },
      '/api/wizard/hardware': { profiles: ['cpu'], suggested_profile: 'cpu', gpus: [] },
      '/api/settings/llm/ollama-models': { models: ['llama3.1:8b', 'llama3.2:3b'] },
    })
    const wrapper = mount(SystemSettingsView)
    await flushPromises()

    expect(wrapper.find('.model-status--ok').exists()).toBe(true)
    expect(wrapper.find('.model-status--warn').exists()).toBe(false)
  })

  it('shows not-installed status with a Download button when the model is missing', async () => {
    const config = useAppConfigStore()
    config.isCloud = false
    mockRoutes({
      '/api/settings/system/llm-backend': { ollama_model: 'llama3.2:3b' },
      '/api/wizard/hardware': { profiles: ['cpu'], suggested_profile: 'cpu', gpus: [] },
      '/api/settings/llm/ollama-models': { models: ['llama3.1:8b'] },
    })
    const wrapper = mount(SystemSettingsView)
    await flushPromises()

    expect(wrapper.find('.model-status--warn').exists()).toBe(true)
    expect(wrapper.text()).toContain('Download')
    // The dropdown must still offer the configured-but-uninstalled model.
    const options = wrapper.findAll('option').map(o => o.text())
    expect(options).toContain('llama3.2:3b')
  })

  it('clicking Download triggers a pull, then polls until the model appears installed', async () => {
    const config = useAppConfigStore()
    config.isCloud = false
    let modelsResponse = { models: ['llama3.1:8b'] }
    mockFetch.mockImplementation((url: string, opts?: { method?: string }) => {
      if (url === '/api/settings/system/llm-backend') {
        return Promise.resolve({ data: { ollama_model: 'llama3.2:3b' }, error: null }) as never
      }
      if (url === '/api/wizard/hardware') {
        return Promise.resolve({ data: { profiles: ['cpu'], suggested_profile: 'cpu', gpus: [] }, error: null }) as never
      }
      if (url === '/api/settings/llm/ollama-models') {
        return Promise.resolve({ data: modelsResponse, error: null }) as never
      }
      if (url === '/api/settings/system/ollama-pull' && opts?.method === 'POST') {
        modelsResponse = { models: ['llama3.1:8b', 'llama3.2:3b'] }  // pull "completes" before the next poll
        return Promise.resolve({ data: { ok: true, status: 'pulling' }, error: null }) as never
      }
      return Promise.resolve({ data: {}, error: null }) as never
    })
    const wrapper = mount(SystemSettingsView)
    await flushPromises()

    const downloadBtn = wrapper.findAll('button').find(b => b.text().includes('Download'))
    expect(downloadBtn).toBeDefined()
    await downloadBtn!.trigger('click')
    await flushPromises()

    const pullCall = mockFetch.mock.calls.find(c => c[0] === '/api/settings/system/ollama-pull')
    expect(pullCall).toBeDefined()
    const pullBody = JSON.parse((pullCall![1] as { body: string }).body)
    expect(pullBody.model).toBe('llama3.2:3b')

    expect(wrapper.find('.model-status--ok').exists()).toBe(true)
  })
})

describe('SystemSettingsView, Custom Model tier gate', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
    mockFetch.mockResolvedValue({ data: {}, error: null } as never)
  })

  it('disables the custom model input and Save button, and shows the upgrade note, when tier is not premium', async () => {
    const config = useAppConfigStore()
    config.isCloud = true
    config.tier = 'paid'
    const wrapper = mount(SystemSettingsView)
    await flushPromises()
    const input = wrapper.find('input[data-testid="custom-model-alias-input"]')
    expect(input.attributes('disabled')).toBeDefined()
    expect(input.attributes('aria-disabled')).toBe('true')
    expect(wrapper.text()).toContain('Upgrade to use your own fine-tuned model.')
    const saveBtn = wrapper.find('button[data-testid="custom-model-save"]')
    expect(saveBtn.attributes('disabled')).toBeDefined()
  })

  it('enables the custom model input when tier is premium', async () => {
    const config = useAppConfigStore()
    config.isCloud = true
    config.tier = 'premium'
    const wrapper = mount(SystemSettingsView)
    await flushPromises()
    const input = wrapper.find('input[data-testid="custom-model-alias-input"]')
    expect(input.attributes('disabled')).toBeUndefined()
    expect(wrapper.text()).not.toContain('Upgrade to use your own fine-tuned model.')
  })

  it('keeps the Save button enabled for a non-Premium user clearing an existing alias', async () => {
    const config = useAppConfigStore()
    config.isCloud = true
    config.tier = 'paid'
    mockFetch.mockImplementation((url: string) => {
      if (url === '/api/settings/system/custom-model') {
        return Promise.resolve({ data: { custom_model_alias: 'old-alias' }, error: null }) as never
      }
      return Promise.resolve({ data: {}, error: null }) as never
    })
    const wrapper = mount(SystemSettingsView)
    await flushPromises()
    const saveBtn = wrapper.find('button[data-testid="custom-model-save"]')
    expect(saveBtn.attributes('disabled')).toBeUndefined()
  })
})
