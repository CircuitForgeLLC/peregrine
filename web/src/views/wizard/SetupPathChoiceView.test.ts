import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createRouter, createWebHistory } from 'vue-router'
import SetupPathChoiceView from './SetupPathChoiceView.vue'
import { useAppConfigStore } from '../../stores/appConfig'

vi.mock('../../composables/useApi', () => ({ useApiFetch: vi.fn() }))
import { useApiFetch } from '../../composables/useApi'
const mockFetch = vi.mocked(useApiFetch)

function makeRouter() {
  return createRouter({
    history: createWebHistory(),
    routes: [{ path: '/:pathMatch(.*)*', component: { template: '<div/>' } }],
  })
}

describe('SetupPathChoiceView', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
    mockFetch.mockResolvedValue({ data: { ok: true }, error: null } as never)
  })

  it('shows both options unlocked for a paid-tier user', () => {
    const config = useAppConfigStore()
    config.tier = 'paid'
    config.byokUnlocked = false
    config.isCloud = false
    config.wizardComplete = false
    const wrapper = mount(SetupPathChoiceView, { global: { plugins: [makeRouter()] } })
    const aiButton = wrapper.find('[data-testid="setup-path-ai"]')
    expect(aiButton.attributes('disabled')).toBeUndefined()
  })

  it('locks the AI option for a self-hosted free-tier user without BYOK', () => {
    const config = useAppConfigStore()
    config.tier = 'free'
    config.byokUnlocked = false
    config.isCloud = false
    config.wizardComplete = false
    const wrapper = mount(SetupPathChoiceView, { global: { plugins: [makeRouter()] } })
    const aiButton = wrapper.find('[data-testid="setup-path-ai"]')
    expect(aiButton.attributes('disabled')).toBeDefined()
    expect(wrapper.text()).toContain('Upgrade to Paid, or bring your own LLM key')
  })

  it('unlocks the AI option for a cloud free-tier user mid-onboarding', () => {
    const config = useAppConfigStore()
    config.tier = 'free'
    config.byokUnlocked = false
    config.isCloud = true
    config.wizardComplete = false
    const wrapper = mount(SetupPathChoiceView, { global: { plugins: [makeRouter()] } })
    const aiButton = wrapper.find('[data-testid="setup-path-ai"]')
    expect(aiButton.attributes('disabled')).toBeUndefined()
  })

  it('saves setup_path and navigates to /wizard/ai-profile when AI is chosen', async () => {
    const config = useAppConfigStore()
    config.tier = 'paid'
    config.wizardComplete = false
    const router = makeRouter()
    const wrapper = mount(SetupPathChoiceView, { global: { plugins: [router] } })
    await wrapper.find('[data-testid="setup-path-ai"]').trigger('click')
    await flushPromises()

    const call = mockFetch.mock.calls.find(c => c[0] === '/api/wizard/setup-path')
    expect(call).toBeDefined()
    expect((call as [string, { method?: string; body?: unknown }])[1]?.method).toBe('POST')
    expect(router.currentRoute.value.path).toBe('/wizard/ai-profile')
  })

  it('saves setup_path and navigates to /setup when manual is chosen', async () => {
    const config = useAppConfigStore()
    config.tier = 'free'
    config.wizardComplete = false
    const router = makeRouter()
    const wrapper = mount(SetupPathChoiceView, { global: { plugins: [router] } })
    await wrapper.find('[data-testid="setup-path-manual"]').trigger('click')
    await flushPromises()

    const call = mockFetch.mock.calls.find(c => c[0] === '/api/wizard/setup-path')
    expect(call).toBeDefined()
    expect(router.currentRoute.value.path).toBe('/setup')
  })
})
