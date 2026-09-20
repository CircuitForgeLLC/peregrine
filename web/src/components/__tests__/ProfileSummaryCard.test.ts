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

  it('clicking a remote-preference button toggles it out of the multi-select', async () => {
    mockFetch.mockResolvedValue({ data: null, error: null })
    const search = useSearchStore()
    search.remote_preference = ['onsite', 'remote', 'hybrid']
    const wrapper = mount(ProfileSummaryCard, { global: { plugins: [makeRouter()] } })
    await wrapper.vm.$nextTick()
    const buttons = wrapper.findAll('.remote-btn')
    const remoteBtn = buttons.find(b => b.text() === 'Remote')
    expect(remoteBtn!.classes()).toContain('active')

    await remoteBtn!.trigger('click')
    expect(search.remote_preference).toEqual(['onsite', 'hybrid'])
    expect(remoteBtn!.classes()).not.toContain('active')
  })

  it('clicking an unselected remote-preference button adds it to the multi-select', async () => {
    mockFetch.mockResolvedValue({ data: null, error: null })
    const search = useSearchStore()
    search.remote_preference = ['onsite']
    const wrapper = mount(ProfileSummaryCard, { global: { plugins: [makeRouter()] } })
    await wrapper.vm.$nextTick()
    const buttons = wrapper.findAll('.remote-btn')
    const hybridBtn = buttons.find(b => b.text() === 'Hybrid')
    expect(hybridBtn!.classes()).not.toContain('active')

    await hybridBtn!.trigger('click')
    expect(search.remote_preference).toEqual(['onsite', 'hybrid'])
    expect(hybridBtn!.classes()).toContain('active')
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

  it('does not show "✓ Saved" and surfaces the error when a save fails', async () => {
    mockFetch.mockResolvedValue({ data: null, error: null })
    const search = useSearchStore()
    const resume = useResumeStore()
    const wrapper = mount(ProfileSummaryCard, { global: { plugins: [makeRouter()] } })
    await wrapper.vm.$nextTick()
    await wrapper.vm.$nextTick()

    // Simulate resume.save() failing (matching how resume.test.ts exercises the failure path:
    // saveError is set internally when the mocked useApiFetch call errors).
    vi.spyOn(search, 'save').mockResolvedValue(undefined)
    vi.spyOn(resume, 'save').mockImplementation(async () => {
      resume.saveError = 'Save failed — please try again.'
    })

    const saveBtn = wrapper.find('.btn-primary')
    await saveBtn.trigger('click')
    await wrapper.vm.$nextTick()
    await wrapper.vm.$nextTick()

    expect(saveBtn.text()).not.toContain('✓ Saved')
    expect(wrapper.find('.error').exists()).toBe(true)
    expect(wrapper.find('.error').text()).toContain('Save failed')
  })

  it('disables Save and never calls save when the initial load fails (not just while in flight)', async () => {
    // Both search.load() and resume.load() resolve with an error — this leaves
    // store fields at their constructor defaults (e.g. resume.salary_min === 0),
    // not the user's real data, so Save must stay disabled after loading settles,
    // not just while it's in flight.
    mockFetch.mockResolvedValue({ data: null, error: { kind: 'http', status: 500, detail: 'Server error' } })
    const search = useSearchStore()
    const resume = useResumeStore()
    const wrapper = mount(ProfileSummaryCard, { global: { plugins: [makeRouter()] } })
    await wrapper.vm.$nextTick()
    await wrapper.vm.$nextTick()

    expect(search.loading).toBe(false)
    expect(resume.loading).toBe(false)
    expect(search.loadError).toBeTruthy()
    expect(resume.loadError).toBeTruthy()

    const searchSaveSpy = vi.spyOn(search, 'save')
    const resumeSaveSpy = vi.spyOn(resume, 'save')

    const saveBtn = wrapper.find('.btn-primary')
    expect(saveBtn.attributes('disabled')).toBeDefined()
    expect(wrapper.find('.error-banner').exists()).toBe(true)

    // Prove a click structurally cannot fire a save — not just that the
    // `disabled` attribute is present — by asserting the spies were never called.
    await saveBtn.trigger('click')
    expect(searchSaveSpy).not.toHaveBeenCalled()
    expect(resumeSaveSpy).not.toHaveBeenCalled()
  })

  it('does not re-fire load on a second mount once a store already loaded successfully', async () => {
    mockFetch.mockResolvedValue({ data: null, error: null })
    const search = useSearchStore()
    const resume = useResumeStore()

    const first = mount(ProfileSummaryCard, { global: { plugins: [makeRouter()] } })
    await first.vm.$nextTick()
    await first.vm.$nextTick()
    expect(search.loaded).toBe(true)
    expect(resume.loaded).toBe(true)
    first.unmount()
    vi.clearAllMocks()

    // Same (still-active) Pinia stores, simulating navigating back to the dashboard.
    mount(ProfileSummaryCard, { global: { plugins: [makeRouter()] } })
    await Promise.resolve()
    expect(mockFetch).not.toHaveBeenCalled()
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
