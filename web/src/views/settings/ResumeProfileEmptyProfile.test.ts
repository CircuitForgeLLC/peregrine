import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createRouter, createWebHistory } from 'vue-router'
import ResumeProfileView from './ResumeProfileView.vue'
import { useProfileStore } from '../../stores/settings/profile'

vi.mock('../../composables/useApi', () => ({ useApiFetch: vi.fn() }))
import { useApiFetch } from '../../composables/useApi'
const mockFetch = vi.mocked(useApiFetch)

function mountView() {
  const router = createRouter({ history: createWebHistory(), routes: [{ path: '/:p*', component: { template: '<div/>' } }] })
  return mount(ResumeProfileView, { global: { plugins: [router] } })
}

// Issue 285: a person who starts by parsing a resume has an empty My Profile.
// The page used to show blank locked boxes and a save wiped the parsed values.
describe('ResumeProfileView, empty My Profile with a parsed resume', () => {
  const parsed = {
    exists: true, name: 'Pat', email: 'pat@example.com', phone: '555-9999',
    linkedin_url: 'linkedin.com/in/pat', surname: 'Lee', address: '', city: '',
    zip_code: '', date_of_birth: '', experience: [], salary_min: 0, salary_max: 0,
    notice_period: '', remote: false, relocation: false, assessment: false,
    background_check: false, gender: '', pronouns: '', ethnicity: '',
    veteran_status: '', disability: '', skills: [], domains: [], keywords: [],
  }
  const emptyProfile = { name: '', email: '', phone: '', linkedin_url: '' }

  function setup(profile: Record<string, string>, resume: Record<string, unknown>) {
    setActivePinia(createPinia())
    vi.clearAllMocks()
    mockFetch.mockImplementation((url: string) => {
      if (url === '/api/settings/profile') return Promise.resolve({ data: profile, error: null }) as never
      if (url === '/api/settings/resume') return Promise.resolve({ data: resume, error: null }) as never
      return Promise.resolve({ data: {}, error: null }) as never
    })
  }
  const val = (w: ReturnType<typeof mountView>, id: string) =>
    (w.find(`[data-testid="${id}"]`).element as HTMLInputElement).value
  const putTo = (url: string) => mockFetch.mock.calls.find(
    call => call[0] === url && (call[1] as { method?: string })?.method === 'PUT',
  ) as [string, { body: string }] | undefined

  it('shows the parsed values and offers the button', async () => {
    setup(emptyProfile, parsed)
    const wrapper = mountView()
    await flushPromises()
    expect(val(wrapper, 'resume-name-input')).toBe('Pat')
    expect(val(wrapper, 'resume-email-input')).toBe('pat@example.com')
    expect(val(wrapper, 'resume-phone-input')).toBe('555-9999')
    expect(val(wrapper, 'resume-linkedin-input')).toBe('linkedin.com/in/pat')
    const btn = wrapper.find('[data-testid="use-resume-in-profile"]')
    expect(btn.exists()).toBe(true)
    expect(btn.text()).toBe('Use these details in My Profile')
  })

  it('keeps the parsed values when saving with an empty My Profile', async () => {
    setup(emptyProfile, parsed)
    const wrapper = mountView()
    await flushPromises()
    await wrapper.find('.btn-primary').trigger('click')
    await flushPromises()
    const body = JSON.parse(putTo('/api/settings/resume')![1].body)
    expect(body.name).toBe('Pat')
    expect(body.email).toBe('pat@example.com')
    expect(body.phone).toBe('555-9999')
    expect(body.linkedin_url).toBe('linkedin.com/in/pat')
  })

  it('writes nothing to My Profile until the button is pressed', async () => {
    setup(emptyProfile, parsed)
    mountView()
    await flushPromises()
    expect(putTo('/api/settings/profile')).toBeUndefined()
  })

  it('fills only the empty My Profile fields and saves them when the button is pressed', async () => {
    setup({ ...emptyProfile, email: 'keep@example.com' }, parsed)
    const wrapper = mountView()
    await flushPromises()
    await wrapper.find('[data-testid="use-resume-in-profile"]').trigger('click')
    await flushPromises()
    const body = JSON.parse(putTo('/api/settings/profile')![1].body)
    expect(body.name).toBe('Pat Lee')
    expect(body.email).toBe('keep@example.com')
    expect(body.phone).toBe('555-9999')
    expect(body.linkedin_url).toBe('linkedin.com/in/pat')
    expect(wrapper.find('[data-testid="use-resume-in-profile"]').exists()).toBe(false)
  })

  it('first-run: empty profile, parsed resume, press the button, profile saved and store filled', async () => {
    setup(emptyProfile, parsed)
    const wrapper = mountView()
    await flushPromises()
    expect(wrapper.text()).toContain('We found these details in your resume. Use them in My Profile?')
    await wrapper.find('[data-testid="use-resume-in-profile"]').trigger('click')
    await flushPromises()
    const body = JSON.parse(putTo('/api/settings/profile')![1].body)
    expect(body).toMatchObject({
      name: 'Pat Lee', email: 'pat@example.com', phone: '555-9999', linkedin_url: 'linkedin.com/in/pat',
    })
    const profile = useProfileStore()
    expect(profile.name).toBe('Pat Lee')
    expect(profile.email).toBe('pat@example.com')
  })

  it('still lets a later My Profile edit flow to the resume after the button', async () => {
    setup(emptyProfile, parsed)
    const wrapper = mountView()
    await flushPromises()
    await wrapper.find('[data-testid="use-resume-in-profile"]').trigger('click')
    await flushPromises()
    useProfileStore().phone = '555-0000'
    await wrapper.find('.btn-primary').trigger('click')
    await flushPromises()
    expect(JSON.parse(putTo('/api/settings/resume')![1].body).phone).toBe('555-0000')
  })

  it('shows one plain message with a single link when both are empty', async () => {
    setup(emptyProfile, { ...parsed, name: '', email: '', phone: '', linkedin_url: '' })
    const wrapper = mountView()
    await flushPromises()
    const empty = wrapper.find('[data-testid="contact-empty"]')
    expect(empty.exists()).toBe(true)
    expect(empty.text()).toContain('Nothing here yet. Add your name and contact details in My Profile.')
    expect(empty.findAll('a[href="/settings/my-profile"]')).toHaveLength(1)
    expect(wrapper.findAll('a.sync-link')).toHaveLength(0)
    expect(wrapper.find('[data-testid="use-resume-in-profile"]').exists()).toBe(false)
  })

  it('gives the read-only group an accessible description saying where to edit', async () => {
    setup(emptyProfile, parsed)
    const wrapper = mountView()
    await flushPromises()
    const group = wrapper.find('[data-testid="contact-group"]')
    expect(group.attributes('role')).toBe('group')
    const descId = group.attributes('aria-describedby')
    expect(descId).toBeTruthy()
    expect(wrapper.find(`#${descId}`).text()).toContain('My Profile')
  })
})
