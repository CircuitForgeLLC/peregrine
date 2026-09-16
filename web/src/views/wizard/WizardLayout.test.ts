import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createRouter, createWebHistory } from 'vue-router'
import WizardLayout from './WizardLayout.vue'
import { useWizardStore, STEP_ROUTES } from '../../stores/wizard'
import { useAppConfigStore } from '../../stores/appConfig'

vi.mock('../../composables/useApi', () => ({ useApiFetch: vi.fn() }))
import { useApiFetch } from '../../composables/useApi'
const mockFetch = vi.mocked(useApiFetch)

const DummyStep = { template: '<div>step</div>' }

function makeRouter(startPath: string) {
  const router = createRouter({
    history: createWebHistory(),
    routes: [
      {
        path: '/setup',
        component: WizardLayout,
        children: [
          { path: '', component: DummyStep },
          ...STEP_ROUTES.map((p) => ({ path: p.replace('/setup/', ''), component: DummyStep })),
        ],
      },
    ],
  })
  router.push(startPath)
  return router
}

// Regression coverage for: the progress bar ("Step N of 8") could show a
// different step number than the page actually on screen, when landing
// directly on a /setup/<step> route (direct nav, refresh, browser
// back/forward) whose number doesn't match the server's "resume at" step.
describe('WizardLayout — progress step sync', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
    const config = useAppConfigStore()
    config.loaded = true
    config.isDemo = false
  })

  it('syncs currentStep to the actually-mounted route, not the server resume-at step', async () => {
    // Server reports wizard_step=2 (tier done) -> loadStatus would normally
    // resume at step 3 (resume). But the user is directly on /setup/hardware
    // (step 1) -- the progress bar must reflect step 1, not 3.
    mockFetch.mockResolvedValue({
      data: { wizard_complete: false, wizard_step: 2, saved_data: {} },
      error: null,
    } as never)

    const router = makeRouter('/setup/hardware')
    await router.isReady()
    mount(WizardLayout, { global: { plugins: [router] } })
    await flushPromises()

    const wizard = useWizardStore()
    expect(wizard.currentStep).toBe(1)
    expect(wizard.stepLabel).toBe('Step 1 of 8')
  })

  it('still redirects bare /setup to the server resume-at step', async () => {
    mockFetch.mockResolvedValue({
      data: { wizard_complete: false, wizard_step: 2, saved_data: {} },
      error: null,
    } as never)

    const router = makeRouter('/setup')
    await router.isReady()
    mount(WizardLayout, { global: { plugins: [router] } })
    await flushPromises()

    expect(router.currentRoute.value.path).toBe('/setup/resume')
    const wizard = useWizardStore()
    expect(wizard.currentStep).toBe(3)
  })

  it('keeps currentStep in sync when navigating between step routes after mount', async () => {
    mockFetch.mockResolvedValue({
      data: { wizard_complete: false, wizard_step: 0, saved_data: {} },
      error: null,
    } as never)

    const router = makeRouter('/setup/hardware')
    await router.isReady()
    mount(WizardLayout, { global: { plugins: [router] } })
    await flushPromises()

    const wizard = useWizardStore()
    expect(wizard.currentStep).toBe(1)

    await router.push('/setup/identity')
    await flushPromises()
    expect(wizard.currentStep).toBe(5)
  })
})
