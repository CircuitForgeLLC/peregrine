import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createRouter, createWebHistory } from 'vue-router'
import OnboardingFlow from './OnboardingFlow.vue'
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

function statusResponse(overrides: Partial<{
  profile: boolean; resume: boolean; search: boolean; compute_backend: boolean
  connections_acknowledged: boolean; setup_path: 'ai' | 'manual' | null
}> = {}) {
  return {
    data: {
      sections: {
        profile: overrides.profile ?? false,
        resume: overrides.resume ?? false,
        search: overrides.search ?? false,
        compute_backend: overrides.compute_backend ?? false,
      },
      connections_acknowledged: overrides.connections_acknowledged ?? false,
      setup_path: overrides.setup_path ?? null,
    },
    error: null,
  }
}

async function mountFlow(config: { isCloud?: boolean } = {}) {
  const cfg = useAppConfigStore()
  cfg.isCloud = config.isCloud ?? true
  cfg.loaded = true
  const router = makeRouter()
  const wrapper = mount(OnboardingFlow, { global: { plugins: [router] } })
  await wrapper.vm.$nextTick()
  await wrapper.vm.$nextTick()
  return { wrapper, router }
}

describe('OnboardingFlow', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  it('shows the Resume step first for a cloud user (Compute step skipped)', async () => {
    mockFetch.mockResolvedValue(statusResponse())
    const { wrapper } = await mountFlow({ isCloud: true })
    expect(wrapper.text()).toContain('Resume')
    expect(wrapper.text()).not.toContain('Compute & AI Backend')
  })

  it('shows the Compute & AI Backend step first for a self-hosted user', async () => {
    mockFetch.mockResolvedValue(statusResponse())
    const { wrapper } = await mountFlow({ isCloud: false })
    expect(wrapper.text()).toContain('Compute & AI Backend')
  })

  it('advances to Connections once Resume is complete', async () => {
    mockFetch.mockResolvedValue(statusResponse({ resume: true }))
    const { wrapper } = await mountFlow({ isCloud: true })
    expect(wrapper.text()).toContain('Connections')
  })

  it('advances to the setup-path choice once Connections is acknowledged', async () => {
    mockFetch.mockResolvedValue(statusResponse({ resume: true, connections_acknowledged: true }))
    const { wrapper } = await mountFlow({ isCloud: true })
    expect(wrapper.text()).toContain('How would you like to finish setting up')
  })

  it('advances to Profile once a setup path has been chosen', async () => {
    mockFetch.mockResolvedValue(statusResponse({
      resume: true, connections_acknowledged: true, setup_path: 'manual',
    }))
    const { wrapper } = await mountFlow({ isCloud: true })
    expect(wrapper.text()).toContain('Profile')
  })

  it('shows completed earlier steps as reopenable, not hidden', async () => {
    mockFetch.mockResolvedValue(statusResponse({ resume: true, connections_acknowledged: true }))
    const { wrapper } = await mountFlow({ isCloud: true })
    const resumeLink = wrapper.findAll('a').find(a => a.text().includes('Resume'))
    expect(resumeLink).toBeDefined()
    expect(resumeLink!.attributes('href')).toBe('/settings/resume')
  })

  it('shows Finish Setup once profile, resume, and search are all complete', async () => {
    mockFetch.mockResolvedValue(statusResponse({
      resume: true, connections_acknowledged: true, setup_path: 'manual',
      profile: true, search: true,
    }))
    const { wrapper } = await mountFlow({ isCloud: true })
    expect(wrapper.find('.flow__finish').exists()).toBe(true)
  })

  it('finishing setup submits an initial discovery run and navigates home', async () => {
    mockFetch.mockImplementation((url: string) => {
      if (url === '/api/wizard/status') return Promise.resolve(statusResponse({
        resume: true, connections_acknowledged: true, setup_path: 'manual',
        profile: true, search: true,
      })) as never
      if (url === '/api/wizard/complete') return Promise.resolve({ data: { ok: true }, error: null }) as never
      return Promise.resolve({ data: {}, error: null }) as never
    })
    const { wrapper, router } = await mountFlow({ isCloud: true })
    await wrapper.find('.flow__finish button').trigger('click')
    await flushPromises()

    const discoveryCall = mockFetch.mock.calls.find(c => c[0] === '/api/tasks/discovery')
    expect(discoveryCall).toBeDefined()
    const cfg = useAppConfigStore()
    expect(cfg.wizardComplete).toBe(true)
    expect(router.currentRoute.value.path).toBe('/')
  })
})
