import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createRouter, createWebHistory } from 'vue-router'
import ApplyWorkspace from '../ApplyWorkspace.vue'

vi.mock('../../composables/useApi', () => ({
  useApiFetch: vi.fn(),
}))

import { useApiFetch } from '../../composables/useApi'
const mockFetch = vi.mocked(useApiFetch)

const BASE_JOB = {
  id: 1,
  title: 'Importing...',
  company: '',
  location: '',
  is_remote: false,
  salary: null,
  match_score: null,
  keyword_gaps: null,
  description: '',
  url: 'https://example.com/job/1',
  cover_letter: null,
  import_state: null as string | null,
}

function respondWith(job: Record<string, unknown>) {
  mockFetch.mockImplementation(async (url: string, opts?: RequestInit) => {
    if (url === '/api/jobs/1/details' && opts?.method === 'PATCH') {
      return { data: { ...job, title: 'Engineer', company: 'Acme', description: 'Pasted', import_state: null }, error: null }
    }
    if (url === '/api/jobs/1') return { data: job, error: null }
    return { data: null, error: null }
  })
}

function factory() {
  const router = createRouter({ history: createWebHistory(), routes: [{ path: '/:p*', component: { template: '<div/>' } }] })
  return mount(ApplyWorkspace, {
    props: { jobId: 1 },
    global: { plugins: [router], stubs: { Teleport: true } },
  })
}

describe('ApplyWorkspace import state', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
    mockFetch.mockReset()
  })

  it('explains an unreadable page calmly and offers the paste-and-fill form', async () => {
    respondWith({ ...BASE_JOB, import_state: 'needs_manual_entry' })
    const w = factory()
    await flushPromises()
    const panel = w.find('[data-test="manual-entry"]')
    expect(panel.exists()).toBe(true)
    expect(panel.text()).toContain("We couldn't read this page automatically")
    expect(panel.find('input[name="title"]').exists()).toBe(true)
    expect(panel.find('input[name="company"]').exists()).toBe(true)
    expect(panel.find('textarea[name="description"]').exists()).toBe(true)
    expect(w.find('[data-test="importing"]').exists()).toBe(false)
  })

  it('labels every field for screen readers', async () => {
    respondWith({ ...BASE_JOB, import_state: 'needs_manual_entry' })
    const w = factory()
    await flushPromises()
    for (const name of ['title', 'company', 'description']) {
      const field = w.find(`[name="${name}"]`)
      const id = field.attributes('id')
      expect(id).toBeTruthy()
      expect(w.find(`label[for="${id}"]`).exists()).toBe(true)
    }
  })

  it('saves what was typed and then leaves the manual entry state', async () => {
    respondWith({ ...BASE_JOB, import_state: 'needs_manual_entry' })
    const w = factory()
    await flushPromises()
    await w.find('input[name="title"]').setValue('Engineer')
    await w.find('input[name="company"]').setValue('Acme')
    await w.find('textarea[name="description"]').setValue('Pasted')
    await w.find('[data-test="manual-entry"] form').trigger('submit')
    await flushPromises()
    const call = mockFetch.mock.calls.find(c => c[0] === '/api/jobs/1/details')
    expect(call).toBeTruthy()
    expect(JSON.parse(call![1]!.body as string)).toEqual({ title: 'Engineer', company: 'Acme', description: 'Pasted' })
    expect(w.find('[data-test="manual-entry"]').exists()).toBe(false)
  })

  it('does not submit without a title and a description', async () => {
    respondWith({ ...BASE_JOB, import_state: 'needs_manual_entry' })
    const w = factory()
    await flushPromises()
    await w.find('[data-test="manual-entry"] form').trigger('submit')
    await flushPromises()
    expect(mockFetch.mock.calls.some(c => c[0] === '/api/jobs/1/details')).toBe(false)
  })

  it('still shows the normal importing note while a scrape is running', async () => {
    respondWith({ ...BASE_JOB, import_state: 'importing' })
    const w = factory()
    await flushPromises()
    expect(w.find('[data-test="importing"]').exists()).toBe(true)
    expect(w.find('[data-test="manual-entry"]').exists()).toBe(false)
    w.unmount()
  })

  it('shows neither note for an ordinary job', async () => {
    respondWith({ ...BASE_JOB, title: 'Engineer', description: 'Text', import_state: null })
    const w = factory()
    await flushPromises()
    expect(w.find('[data-test="importing"]').exists()).toBe(false)
    expect(w.find('[data-test="manual-entry"]').exists()).toBe(false)
  })
})
