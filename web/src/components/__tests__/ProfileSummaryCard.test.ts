import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createRouter, createWebHistory } from 'vue-router'
import ProfileSummaryCard from '../ProfileSummaryCard.vue'
import { useSearchStore } from '../../stores/settings/search'
import { useResumeStore } from '../../stores/settings/resume'

vi.mock('../../composables/useApi', () => ({ useApiFetch: vi.fn() }))
import { useApiFetch } from '../../composables/useApi'
const mockFetch = vi.mocked(useApiFetch)

function makeRouter() {
  return createRouter({ history: createWebHistory(), routes: [{ path: '/:p*', component: { template: '<div/>' } }] })
}

describe('ProfileSummaryCard', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  it('renders the current locations as tags', async () => {
    mockFetch.mockResolvedValue({ data: null, error: null })
    const search = useSearchStore()
    search.locations = ['Boston', 'Remote']
    const wrapper = mount(ProfileSummaryCard, { global: { plugins: [makeRouter()] } })
    await wrapper.vm.$nextTick()
    const tagText = wrapper.findAll('.tag').map(t => t.text())
    expect(tagText.some(t => t.includes('Boston'))).toBe(true)
    expect(tagText.some(t => t.includes('Remote'))).toBe(true)
  })

  it('adding a location via the input + Enter calls addTag and shows the new tag', async () => {
    mockFetch.mockResolvedValue({ data: null, error: null })
    const search = useSearchStore()
    const wrapper = mount(ProfileSummaryCard, { global: { plugins: [makeRouter()] } })
    await wrapper.vm.$nextTick()
    const input = wrapper.find('input[aria-label="Add location"]')
    await input.setValue('Chicago')
    await input.trigger('keydown.enter')
    expect(search.locations).toContain('Chicago')
    await wrapper.vm.$nextTick()
    expect(wrapper.findAll('.tag').some(t => t.text().includes('Chicago'))).toBe(true)
  })

  it('removing a location tag calls removeTag', async () => {
    mockFetch.mockResolvedValue({ data: null, error: null })
    const search = useSearchStore()
    search.locations = ['Boston']
    const wrapper = mount(ProfileSummaryCard, { global: { plugins: [makeRouter()] } })
    await wrapper.vm.$nextTick()
    await wrapper.find('.tag button').trigger('click')
    expect(search.locations).not.toContain('Boston')
  })

  it('min-salary input reflects and updates resume.salary_min', async () => {
    mockFetch.mockResolvedValue({ data: null, error: null })
    const resume = useResumeStore()
    resume.salary_min = 90000
    const wrapper = mount(ProfileSummaryCard, { global: { plugins: [makeRouter()] } })
    await wrapper.vm.$nextTick()
    const input = wrapper.find('#profile-summary-min-salary')
    expect((input.element as HTMLInputElement).value).toBe('90000')
    await input.setValue(110000)
    expect(resume.salary_min).toBe(110000)
  })

  it('clicking a remote-preference button updates search.remote_preference and marks it active', async () => {
    mockFetch.mockResolvedValue({ data: null, error: null })
    const search = useSearchStore()
    const wrapper = mount(ProfileSummaryCard, { global: { plugins: [makeRouter()] } })
    await wrapper.vm.$nextTick()
    const buttons = wrapper.findAll('.remote-btn')
    const remoteBtn = buttons.find(b => b.text() === 'Remote')
    await remoteBtn!.trigger('click')
    expect(search.remote_preference).toBe('remote')
    expect(remoteBtn!.classes()).toContain('active')
  })

  it('shows "Resume uploaded" with a checkmark when hasResume is true', async () => {
    mockFetch.mockResolvedValue({ data: null, error: null })
    const resume = useResumeStore()
    resume.hasResume = true
    const wrapper = mount(ProfileSummaryCard, { global: { plugins: [makeRouter()] } })
    await wrapper.vm.$nextTick()
    expect(wrapper.text()).toContain('Resume uploaded')
    expect(wrapper.text()).toContain('✓')
    expect(wrapper.find('a[href="/settings/resume"]').exists()).toBe(false)
  })

  it('shows an "Upload resume →" link to /settings/resume when hasResume is false', async () => {
    mockFetch.mockResolvedValue({ data: null, error: null })
    const resume = useResumeStore()
    resume.hasResume = false
    const wrapper = mount(ProfileSummaryCard, { global: { plugins: [makeRouter()] } })
    await wrapper.vm.$nextTick()
    const link = wrapper.find('a[href="/settings/resume"]')
    expect(link.exists()).toBe(true)
    expect(link.text()).toContain('Upload resume')
  })

  it('disables the Save button while stores are loading on mount', async () => {
    // Never-resolving promise simulates a load() still in flight.
    mockFetch.mockReturnValue(new Promise(() => {}))
    const wrapper = mount(ProfileSummaryCard, { global: { plugins: [makeRouter()] } })
    await wrapper.vm.$nextTick()
    const search = useSearchStore()
    const resume = useResumeStore()
    expect(search.loading).toBe(true)
    expect(resume.loading).toBe(true)
    const saveBtn = wrapper.find('.btn-primary')
    expect(saveBtn.attributes('disabled')).toBeDefined()
  })

  it('clicking Save (once loaded) calls both search.save and resume.save', async () => {
    mockFetch.mockResolvedValue({ data: null, error: null })
    const search = useSearchStore()
    const resume = useResumeStore()
    const wrapper = mount(ProfileSummaryCard, { global: { plugins: [makeRouter()] } })
    await wrapper.vm.$nextTick()
    await wrapper.vm.$nextTick()
    const searchSaveSpy = vi.spyOn(search, 'save')
    const resumeSaveSpy = vi.spyOn(resume, 'save')
    const saveBtn = wrapper.find('.btn-primary')
    expect(saveBtn.attributes('disabled')).toBeUndefined()
    await saveBtn.trigger('click')
    expect(searchSaveSpy).toHaveBeenCalled()
    expect(resumeSaveSpy).toHaveBeenCalled()
  })

  it('the "Full preferences" link points to /settings/search', async () => {
    mockFetch.mockResolvedValue({ data: null, error: null })
    const wrapper = mount(ProfileSummaryCard, { global: { plugins: [makeRouter()] } })
    await wrapper.vm.$nextTick()
    const link = wrapper.find('a[href="/settings/search"]')
    expect(link.exists()).toBe(true)
    expect(link.text()).toContain('Full preferences')
  })
})
