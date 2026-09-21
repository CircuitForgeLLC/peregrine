import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createRouter, createWebHistory } from 'vue-router'
import MyProfileView from './MyProfileView.vue'
import { useAppConfigStore } from '../../stores/appConfig'

vi.mock('../../composables/useApi', () => ({ useApiFetch: vi.fn() }))
import { useApiFetch } from '../../composables/useApi'
const mockFetch = vi.mocked(useApiFetch)

function makeRouter() {
  return createRouter({ history: createWebHistory(), routes: [{ path: '/:p*', component: { template: '<div/>' } }] })
}

function mountView() {
  return mount(MyProfileView, { global: { plugins: [makeRouter()] } })
}

// Regression: the big "Set up your profile with AI" banner used to render
// unconditionally (gated only on tier access, never on whether setup was
// already finished), so it stayed visible forever after onboarding. Per-field
// Suggest buttons throughout this page are the intended ongoing AI-assist
// entry point once setup is done -- this banner is a one-time onboarding
// nudge, not a permanent fixture.
describe('MyProfileView, AI setup banner', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
    mockFetch.mockResolvedValue({ data: {}, error: null } as never)
  })

  it('shows the banner before setup is finished', async () => {
    const config = useAppConfigStore()
    config.wizardComplete = false
    config.tier = 'paid'
    const wrapper = mountView()
    await flushPromises()
    expect(wrapper.find('.wizard-cta').exists()).toBe(true)
  })

  it('hides the banner once setup is finished', async () => {
    const config = useAppConfigStore()
    config.wizardComplete = true
    config.tier = 'paid'
    const wrapper = mountView()
    await flushPromises()
    expect(wrapper.find('.wizard-cta').exists()).toBe(false)
  })
})
