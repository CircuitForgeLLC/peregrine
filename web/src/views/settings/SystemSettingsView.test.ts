import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
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
