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
