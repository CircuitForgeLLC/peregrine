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

// Regression: the "Generate" buttons used to overwrite career_summary,
// candidate_voice, and mission_preferences directly with no review step,
// destroying whatever the user had already entered. peregrine#190.
describe('MyProfileView, AI generate buttons require review', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
    const config = useAppConfigStore()
    config.wizardComplete = true
    config.tier = 'paid'
  })

  it('generate-summary does not overwrite the field until accepted', async () => {
    mockFetch.mockResolvedValueOnce({
      data: { career_summary: 'Existing summary I wrote myself.', mission_preferences: [] },
      error: null,
    } as never)
    const wrapper = mountView()
    await flushPromises()

    mockFetch.mockResolvedValueOnce({ data: { summary: 'AI-generated summary.' }, error: null } as never)
    await wrapper.find('#profile-summary').setValue('Existing summary I wrote myself.')
    await wrapper.findAll('.btn-generate')[0].trigger('click')
    await flushPromises()

    // Field is untouched; the suggestion sits in its own review box instead.
    expect((wrapper.find('#profile-summary').element as HTMLTextAreaElement).value)
      .toBe('Existing summary I wrote myself.')
    expect(wrapper.find('.suggestion-box').text()).toContain('AI-generated summary.')

    await wrapper.find('.suggestion-box .btn-generate').trigger('click')
    expect((wrapper.find('#profile-summary').element as HTMLTextAreaElement).value)
      .toBe('AI-generated summary.')
    expect(wrapper.find('.suggestion-box').exists()).toBe(false)
  })

  it('generate-summary suggestion can be discarded without touching the field', async () => {
    mockFetch.mockResolvedValueOnce({ data: { career_summary: 'Mine.', mission_preferences: [] }, error: null } as never)
    const wrapper = mountView()
    await flushPromises()

    mockFetch.mockResolvedValueOnce({ data: { summary: 'AI draft.' }, error: null } as never)
    await wrapper.findAll('.btn-generate')[0].trigger('click')
    await flushPromises()

    await wrapper.find('.suggestion-box .btn-secondary').trigger('click')
    expect((wrapper.find('#profile-summary').element as HTMLTextAreaElement).value).toBe('Mine.')
    expect(wrapper.find('.suggestion-box').exists()).toBe(false)
  })

  it('generate-missions appends suggestions instead of replacing existing entries', async () => {
    mockFetch.mockResolvedValueOnce({
      data: {
        mission_preferences: [{ industry: 'nonprofit', note: 'my own note' }],
      },
      error: null,
    } as never)
    const wrapper = mountView()
    await flushPromises()
    expect(wrapper.findAll('.mission-row')).toHaveLength(1)

    mockFetch.mockResolvedValueOnce({
      data: { mission_preferences: [{ industry: 'music', note: 'suggested note' }] },
      error: null,
    } as never)
    const generateMissionsBtn = wrapper.findAll('.mission-actions .btn-generate')[0]
    await generateMissionsBtn.trigger('click')
    await flushPromises()

    const rows = wrapper.findAll('.mission-row')
    expect(rows).toHaveLength(2)
    // Existing entry is untouched.
    expect((rows[0].find('.mission-industry').element as HTMLInputElement).value).toBe('nonprofit')
    expect((rows[0].find('.mission-note').element as HTMLInputElement).value).toBe('my own note')
    // New suggestion is appended and marked as suggested.
    expect((rows[1].find('.mission-industry').element as HTMLInputElement).value).toBe('music')
    expect(rows[1].classes()).toContain('mission-row--suggested')
    expect(rows[1].find('.suggested-badge').exists()).toBe(true)
  })

  it('generate-missions skips suggestions that duplicate an existing industry', async () => {
    mockFetch.mockResolvedValueOnce({
      data: { mission_preferences: [{ industry: 'Music', note: '' }] },
      error: null,
    } as never)
    const wrapper = mountView()
    await flushPromises()

    mockFetch.mockResolvedValueOnce({
      data: { mission_preferences: [{ industry: 'music', note: 'dup' }, { industry: 'nonprofit', note: '' }] },
      error: null,
    } as never)
    await wrapper.findAll('.mission-actions .btn-generate')[0].trigger('click')
    await flushPromises()

    const rows = wrapper.findAll('.mission-row')
    expect(rows).toHaveLength(2) // original "Music" + new "nonprofit", "music" dup skipped
    const industries = rows.map((r) => (r.find('.mission-industry').element as HTMLInputElement).value)
    expect(industries).toEqual(['Music', 'nonprofit'])
  })

  it('editing a suggested mission row clears the suggested marker', async () => {
    mockFetch.mockResolvedValueOnce({ data: { mission_preferences: [] }, error: null } as never)
    const wrapper = mountView()
    await flushPromises()

    mockFetch.mockResolvedValueOnce({
      data: { mission_preferences: [{ industry: 'music', note: '' }] },
      error: null,
    } as never)
    await wrapper.findAll('.mission-actions .btn-generate')[0].trigger('click')
    await flushPromises()

    const row = wrapper.find('.mission-row')
    expect(row.classes()).toContain('mission-row--suggested')

    await row.find('.mission-note').setValue('now reviewed by me')
    expect(row.classes()).not.toContain('mission-row--suggested')
  })
})
