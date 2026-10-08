import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createRouter, createWebHistory } from 'vue-router'
import ResumeProfileView from './ResumeProfileView.vue'
import { useResumeStore } from '../../stores/settings/resume'

vi.mock('../../composables/useApi', () => ({ useApiFetch: vi.fn() }))
import { useApiFetch } from '../../composables/useApi'
const mockFetch = vi.mocked(useApiFetch)

function makeRouter() {
  return createRouter({ history: createWebHistory(), routes: [{ path: '/:p*', component: { template: '<div/>' } }] })
}

function mountView() {
  return mount(ResumeProfileView, { global: { plugins: [makeRouter()] } })
}

// Contact fields (name/email/phone/linkedin_url) used to be independently
// editable copies that only matched My Profile at the moment a resume was
// first created -- editing one side silently left the other stale. They're
// now read-only here, sourced live from My Profile, and re-synced immediately
// before every save so the persisted value always matches what's currently
// live in My Profile.
describe('ResumeProfileView, contact info stays in sync with My Profile', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
    mockFetch.mockImplementation((url: string) => {
      if (url === '/api/settings/profile') {
        return Promise.resolve({
          data: { name: 'Alex Rivera', email: 'alex@example.com', phone: '555-1234', linkedin_url: 'linkedin.com/in/alex' },
          error: null,
        }) as never
      }
      if (url === '/api/settings/resume') {
        return Promise.resolve({
          data: {
            exists: true, name: 'Stale Name', email: 'stale@example.com', phone: '000-0000',
            linkedin_url: 'linkedin.com/in/stale', surname: 'Rivera', address: '', city: '',
            zip_code: '', date_of_birth: '', experience: [], salary_min: 0, salary_max: 0,
            notice_period: '', remote: false, relocation: false, assessment: false,
            background_check: false, gender: '', pronouns: '', ethnicity: '',
            veteran_status: '', disability: '', skills: [], domains: [], keywords: [],
          },
          error: null,
        }) as never
      }
      return Promise.resolve({ data: {}, error: null }) as never
    })
  })

  it('displays My Profile\'s live contact info, not the resume\'s own stale copy', async () => {
    const wrapper = mountView()
    await flushPromises()

    // My Profile holds the full name; this is the First Name box, so only the first word.
    expect((wrapper.find('[data-testid="resume-name-input"]').element as HTMLInputElement).value).toBe('Alex')
    expect((wrapper.find('[data-testid="resume-email-input"]').element as HTMLInputElement).value).toBe('alex@example.com')
    expect((wrapper.find('[data-testid="resume-phone-input"]').element as HTMLInputElement).value).toBe('555-1234')
    expect((wrapper.find('[data-testid="resume-linkedin-input"]').element as HTMLInputElement).value).toBe('linkedin.com/in/alex')
  })

  it('makes the contact fields read-only', async () => {
    const wrapper = mountView()
    await flushPromises()

    for (const testid of ['resume-name-input', 'resume-email-input', 'resume-phone-input', 'resume-linkedin-input']) {
      const input = wrapper.find(`[data-testid="${testid}"]`)
      expect(input.attributes('readonly')).toBeDefined()
    }
  })

  it('saves the live My Profile values, not the stale ones the resume loaded with', async () => {
    const wrapper = mountView()
    await flushPromises()
    const store = useResumeStore()
    expect(store.name).toBe('Stale Name') // confirms the resume's own stale copy really was loaded

    await wrapper.find('.btn-primary').trigger('click')
    await flushPromises()

    const putCall = mockFetch.mock.calls.find(
      call => call[0] === '/api/settings/resume' && (call[1] as { method?: string })?.method === 'PUT',
    )
    expect(putCall).toBeDefined()
    const body = JSON.parse((putCall as [string, { body: string }])[1].body)
    expect(body.name).toBe('Alex')
    expect(body.email).toBe('alex@example.com')
    expect(body.phone).toBe('555-1234')
    expect(body.linkedin_url).toBe('linkedin.com/in/alex')
  })

  // A locked field that looks editable is the failure a beta tester hit: she could
  // only type in the boxes without the orange "from My Profile" text and never found
  // out where to change the others. Each one now says so and links there.
  it('gives every read-only field a visible link to where it can be edited', async () => {
    const wrapper = mountView()
    await flushPromises()

    for (const testid of ['resume-name-input', 'resume-email-input', 'resume-phone-input', 'resume-linkedin-input']) {
      const row = wrapper.find(`[data-testid="${testid}"]`).element.closest('.field-row') as HTMLElement
      const link = row.querySelector('a.sync-link')
      expect(link, testid).not.toBeNull()
      expect(link?.getAttribute('href')).toBe('/settings/my-profile')
      expect(link?.textContent).toContain('Edit in My Profile')
    }
  })

  it('marks the read-only inputs so they can be styled as locked', async () => {
    const wrapper = mountView()
    await flushPromises()

    for (const testid of ['resume-name-input', 'resume-email-input', 'resume-phone-input', 'resume-linkedin-input']) {
      expect(wrapper.find(`[data-testid="${testid}"]`).classes()).toContain('synced-input')
    }
  })

  // The library convention is the full name in `name`, but this page keeps first name
  // and surname apart. Saving the full name next to a surname joined them into
  // "Nikki Wilson Wilson" when the page was synced back to the library.
  it('saves only the first name in name, and keeps the surname already entered', async () => {
    const wrapper = mountView()
    await flushPromises()

    await wrapper.find('.btn-primary').trigger('click')
    await flushPromises()

    const putCall = mockFetch.mock.calls.find(
      call => call[0] === '/api/settings/resume' && (call[1] as { method?: string })?.method === 'PUT',
    )
    const body = JSON.parse((putCall as [string, { body: string }])[1].body)
    expect(body.name).toBe('Alex')
    expect(body.surname).toBe('Rivera')
  })

  it('fills an empty surname from the rest of the profile name, without overwriting one', () => {
    setActivePinia(createPinia())
    const store = useResumeStore()

    store.surname = ''
    store.syncFromProfile({ name: 'Nikki Wilson', email: 'n@example.com', phone: '1', linkedin_url: '' })
    expect(store.name).toBe('Nikki')
    expect(store.surname).toBe('Wilson')

    store.surname = 'Smith-Jones'
    store.syncFromProfile({ name: 'Nikki Wilson', email: 'n@example.com', phone: '1', linkedin_url: '' })
    expect(store.surname).toBe('Smith-Jones')

    store.syncFromProfile({ name: 'Cher', email: 'c@example.com', phone: '1', linkedin_url: '' })
    expect(store.name).toBe('Cher')
  })
})
