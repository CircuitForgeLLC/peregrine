import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createRouter, createWebHistory } from 'vue-router'
import OnboardingHub from './OnboardingHub.vue'
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

describe('OnboardingHub', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
    mockFetch.mockResolvedValue({
      data: { sections: { profile: false, resume: false, search: false, compute_backend: false } },
      error: null,
    } as never)
  })

  it('shows the self-hosted-only Compute & AI Backend card when not cloud', async () => {
    const config = useAppConfigStore()
    config.isCloud = false
    config.loaded = true  // onMounted skips config.load() when already loaded, so the
                           // mocked useApiFetch response (which has no isCloud key) can't
                           // clobber the value just set above
    const wrapper = mount(OnboardingHub, { global: { plugins: [makeRouter()] } })
    await wrapper.vm.$nextTick()
    await wrapper.vm.$nextTick()
    expect(wrapper.text()).toContain('Compute & AI Backend')
  })

  it('hides the Compute & AI Backend card in cloud mode', async () => {
    const config = useAppConfigStore()
    config.isCloud = true
    config.loaded = true
    const wrapper = mount(OnboardingHub, { global: { plugins: [makeRouter()] } })
    await wrapper.vm.$nextTick()
    await wrapper.vm.$nextTick()
    expect(wrapper.text()).not.toContain('Compute & AI Backend')
  })

  it('shows a complete marker on a section whose data is already present', async () => {
    mockFetch.mockResolvedValue({
      data: { sections: { profile: true, resume: false, search: false, compute_backend: false } },
      error: null,
    } as never)
    const config = useAppConfigStore()
    config.isCloud = true
    config.loaded = true
    const wrapper = mount(OnboardingHub, { global: { plugins: [makeRouter()] } })
    await wrapper.vm.$nextTick()
    await wrapper.vm.$nextTick()
    const profileCard = wrapper.findAll('.hub-card').find(c => c.text().includes('Profile'))
    expect(profileCard!.classes()).toContain('hub-card--complete')
  })

  it('links the Profile card to /settings/my-profile', async () => {
    const config = useAppConfigStore()
    config.isCloud = true
    config.loaded = true
    const wrapper = mount(OnboardingHub, { global: { plugins: [makeRouter()] } })
    await wrapper.vm.$nextTick()
    await wrapper.vm.$nextTick()
    const profileLink = wrapper.findAll('a.hub-card').find(c => c.text().includes('Profile'))
    expect(profileLink!.attributes('href')).toBe('/settings/my-profile')
  })

  it('hides Finish Setup until profile, resume, and search are all complete', async () => {
    mockFetch.mockResolvedValue({
      data: { sections: { profile: true, resume: true, search: false, compute_backend: false } },
      error: null,
    } as never)
    const config = useAppConfigStore()
    config.isCloud = true
    config.loaded = true
    const wrapper = mount(OnboardingHub, { global: { plugins: [makeRouter()] } })
    await wrapper.vm.$nextTick()
    await wrapper.vm.$nextTick()
    expect(wrapper.find('.hub__finish').exists()).toBe(false)
  })

  it('shows Finish Setup once profile, resume, and search are all complete, and completing navigates home', async () => {
    mockFetch.mockImplementation((url: string) => {
      if (url === '/api/wizard/status') {
        return Promise.resolve({
          data: { sections: { profile: true, resume: true, search: true, compute_backend: false } },
          error: null,
        }) as never
      }
      if (url === '/api/wizard/complete') {
        return Promise.resolve({ data: { ok: true }, error: null }) as never
      }
      return Promise.resolve({ data: {}, error: null }) as never
    })
    const config = useAppConfigStore()
    config.isCloud = true
    config.loaded = true
    config.wizardComplete = false
    const router = makeRouter()
    const wrapper = mount(OnboardingHub, { global: { plugins: [router] } })
    await wrapper.vm.$nextTick()
    await wrapper.vm.$nextTick()

    expect(wrapper.find('.hub__finish').exists()).toBe(true)
    await wrapper.find('.hub__finish button').trigger('click')
    await flushPromises()

    expect(config.wizardComplete).toBe(true)
    expect(router.currentRoute.value.path).toBe('/')
  })
})
