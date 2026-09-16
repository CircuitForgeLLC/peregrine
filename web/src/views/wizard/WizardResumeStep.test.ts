import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createRouter, createWebHistory } from 'vue-router'
import WizardResumeStep from './WizardResumeStep.vue'
import { useAppConfigStore } from '../../stores/appConfig'
import { useWizardStore } from '../../stores/wizard'

vi.mock('../../composables/useApi', () => ({ useApiFetch: vi.fn() }))
import { useApiFetch } from '../../composables/useApi'
const mockFetch = vi.mocked(useApiFetch)

function makeRouter() {
  return createRouter({ history: createWebHistory(), routes: [{ path: '/:p*', component: { template: '<div/>' } }] })
}

// Regression coverage for the "AI Assistant" tab embedding the chat inline
// (analysis happens "right there," not by navigating to a separate page),
// with an explicit "Review with LLM" action and a "Skip" sitting prominently
// alongside it rather than funneling the user into the AI flow.
describe('WizardResumeStep — AI Assistant tab', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
    localStorage.clear()
    mockFetch.mockResolvedValue({ data: null, error: null } as never)
  })

  async function openAiTab() {
    const config = useAppConfigStore()
    config.tier = 'paid'
    const wrapper = mount(WizardResumeStep, { global: { plugins: [makeRouter()] } })
    await wrapper.find('.resume-tab--ai').trigger('click')
    return wrapper
  }

  it('shows an intro with Review with LLM and Skip, not an auto-started chat', async () => {
    const wrapper = await openAiTab()
    expect(wrapper.find('.ai-embed__intro').exists()).toBe(true)
    expect(wrapper.text()).toContain('Review with LLM')
    expect(wrapper.text()).toContain('Skip')
    // Chat must not auto-start — no LLM call fired just from opening the tab.
    expect(mockFetch).not.toHaveBeenCalled()
  })

  it('embeds the chat inline (no navigation) when Review with LLM is clicked', async () => {
    const wrapper = await openAiTab()
    const buttons = wrapper.findAll('.ai-embed__actions button')
    const reviewBtn = buttons.find(b => b.text().includes('Review with LLM'))
    await reviewBtn!.trigger('click')
    await Promise.resolve()

    expect(wrapper.find('.ai-embed__intro').exists()).toBe(false)
    expect(wrapper.find('.ai-chat').exists()).toBe(true)
    // The chat's own onMounted() sends the opening turn — this is the one
    // fetch that's expected once the user has explicitly opted in.
    expect(mockFetch).toHaveBeenCalled()
  })

  it('Skip switches to the Upload tab without starting the chat', async () => {
    const wrapper = await openAiTab()
    const buttons = wrapper.findAll('.ai-embed__actions button')
    const skipBtn = buttons.find(b => b.text().includes('Skip'))
    await skipBtn!.trigger('click')

    expect(wrapper.find('.resume-tab--active').text()).toContain('Upload File')
    expect(mockFetch).not.toHaveBeenCalled()
  })

  // Regression coverage: deterministic fields already known from an earlier
  // resume parse (name/email/career_summary land in wizard.identity) must be
  // sent to the LLM as already-gathered, so it doesn't re-ask for them.
  it('seeds the AI chat with identity fields already known from the resume parse', async () => {
    const config = useAppConfigStore()
    config.tier = 'paid'
    const wizard = useWizardStore()
    wizard.identity.name = 'Alex Rivera'
    wizard.identity.email = 'alex@example.com'
    wizard.identity.careerSummary = 'Backend engineer with 5 years experience.'

    const wrapper = mount(WizardResumeStep, { global: { plugins: [makeRouter()] } })
    await wrapper.find('.resume-tab--ai').trigger('click')
    const buttons = wrapper.findAll('.ai-embed__actions button')
    const reviewBtn = buttons.find(b => b.text().includes('Review with LLM'))
    await reviewBtn!.trigger('click')
    await Promise.resolve()

    const call = mockFetch.mock.calls.find(c => c[0] === '/api/wizard/ai/interview')
    expect(call).toBeDefined()
    const body = JSON.parse((call![1] as { body: string }).body)
    expect(body.profile_so_far).toEqual({
      name: 'Alex Rivera',
      email: 'alex@example.com',
      career_summary: 'Backend engineer with 5 years experience.',
    })
  })
})
