import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import AiProfileChat from './AiProfileChat.vue'
import { useAiInterviewStore } from '../stores/wizard/aiInterview'

vi.mock('../composables/useApi', () => ({ useApiFetch: vi.fn() }))
import { useApiFetch } from '../composables/useApi'
const mockFetch = vi.mocked(useApiFetch)

// Regression coverage: tone chips used to be shown/hidden by keyword-matching
// the assistant's free-text reply ("writing", "voice", "cover letter"), which
// false-positived whenever an unrelated question happened to contain one of
// those words (e.g. a career_summary question mentioning "writing
// experience"). They must now key off the backend's explicit asking_about
// field instead.
describe('AiProfileChat — tone chip visibility', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
    localStorage.clear()
    mockFetch.mockResolvedValue({
      data: { reply: 'Welcome!', extracted_fields: {}, complete: false, asking_about: null },
      error: null,
    })
  })

  it('does not show tone chips for a reply about an unrelated field, even if it mentions "writing"', async () => {
    const store = useAiInterviewStore()
    store.messages = [
      { role: 'assistant', content: 'Tell me about your background and writing experience.' },
    ]
    store.askingAbout = 'career_summary'

    const wrapper = mount(AiProfileChat)
    await wrapper.vm.$nextTick()

    expect(wrapper.find('.ai-tone-chips').exists()).toBe(false)
  })

  it('shows tone chips when the backend reports asking_about candidate_voice', async () => {
    const store = useAiInterviewStore()
    store.messages = [{ role: 'assistant', content: "What's your preferred tone?" }]
    store.askingAbout = 'candidate_voice'

    const wrapper = mount(AiProfileChat)
    await wrapper.vm.$nextTick()

    expect(wrapper.find('.ai-tone-chips').exists()).toBe(true)
  })
})

// Regression coverage: "LLMs are drafts, never decisions" — the completion
// panel used to say "ready to save" with no visibility into what was
// actually extracted (in particular the LLM-authored career_summary prose),
// so nothing was actually reviewable before Save Profile wrote it. Every
// gathered field must be shown, and editable, before save.
describe('AiProfileChat — review before save', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
    localStorage.clear()
    mockFetch.mockResolvedValue({
      data: { reply: 'Welcome!', extracted_fields: {}, complete: false, asking_about: null },
      error: null,
    })
  })

  function completeStore() {
    const store = useAiInterviewStore()
    store.messages = [{ role: 'assistant', content: 'All set!' }]
    store.complete = true
    store.fields = {
      name: 'Alex Rivera',
      email: 'alex@example.com',
      career_summary: 'Backend engineer with 5 years experience.',
      candidate_voice: 'warm and conversational',
      mission_preferences: ['climate', 'animal welfare'],
      candidate_accessibility_focus: true,
      candidate_lgbtq_focus: false,
    }
    return store
  }

  it('shows every gathered field for review instead of a blind "ready to save" message', async () => {
    completeStore()
    const wrapper = mount(AiProfileChat)
    await wrapper.vm.$nextTick()

    const review = wrapper.find('.ai-review')
    expect(review.exists()).toBe(true)
    expect(review.text()).toContain('Full name')
    expect((wrapper.find('#ai-review-name').element as HTMLInputElement).value).toBe('Alex Rivera')
    expect((wrapper.find('#ai-review-career_summary').element as HTMLTextAreaElement).value)
      .toBe('Backend engineer with 5 years experience.')
  })

  it('does not render a review row for a field that was never gathered', async () => {
    const store = completeStore()
    delete store.fields.linkedin
    const wrapper = mount(AiProfileChat)
    await wrapper.vm.$nextTick()

    expect(wrapper.find('#ai-review-linkedin').exists()).toBe(false)
  })

  it('editing a text field updates the store, and Save Profile submits the edited value', async () => {
    const store = completeStore()
    const wrapper = mount(AiProfileChat)
    await wrapper.vm.$nextTick()

    await wrapper.find('#ai-review-name').setValue('Alexandra Rivera')
    expect(store.fields.name).toBe('Alexandra Rivera')

    mockFetch.mockResolvedValue({ data: {}, error: null })
    const saveBtn = wrapper.findAll('.ai-complete__actions button')
      .find(b => b.text().includes('Save Profile'))
    await saveBtn!.trigger('click')

    const call = mockFetch.mock.calls.find(c => c[0] === '/api/wizard/ai/finalize')
    expect(call).toBeDefined()
    const body = JSON.parse((call![1] as { body: string }).body)
    expect(body.profile.name).toBe('Alexandra Rivera')
  })

  it('editing the mission_preferences list field updates the store as an array', async () => {
    const store = completeStore()
    const wrapper = mount(AiProfileChat)
    await wrapper.vm.$nextTick()

    await wrapper.find('#ai-review-mission_preferences').setValue('climate, education, animal welfare')
    expect(store.fields.mission_preferences).toEqual(['climate', 'education', 'animal welfare'])
  })

  it('toggling a boolean field updates the store', async () => {
    const store = completeStore()
    const wrapper = mount(AiProfileChat)
    await wrapper.vm.$nextTick()

    await wrapper.find('#ai-review-candidate_lgbtq_focus').setValue(true)
    expect(store.fields.candidate_lgbtq_focus).toBe(true)
  })
})
