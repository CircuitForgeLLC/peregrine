import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createRouter, createWebHistory } from 'vue-router'
import ApplyWorkspace from '../ApplyWorkspace.vue'

function makeRouter() {
  return createRouter({ history: createWebHistory(), routes: [{ path: '/:p*', component: { template: '<div/>' } }] })
}

vi.mock('../../composables/useApi', () => ({
  useApiFetch: vi.fn(),
}))

import { useApiFetch } from '../../composables/useApi'
const mockFetch = vi.mocked(useApiFetch)

const SAMPLE_JOB = {
  id: 1,
  title: 'Backend Engineer',
  company: 'Acme Corp',
  location: 'Remote',
  is_remote: true,
  salary: '$150k',
  match_score: 82,
  keyword_gaps: null,
  description: 'Short description.',
  url: 'https://example.com/job/1',
  cover_letter: null,
}

function factory() {
  return mount(ApplyWorkspace, {
    props: { jobId: 1 },
    global: { plugins: [makeRouter()], stubs: { Teleport: true } },
  })
}

describe('ApplyWorkspace — job details collapse', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
    mockFetch.mockResolvedValue({ data: SAMPLE_JOB, error: null })
  })

  it('starts expanded when nothing is stored', async () => {
    const w = factory()
    await flushPromises()
    expect(w.find('.workspace__job-panel--collapsed').exists()).toBe(false)
    expect(w.text()).toContain('Backend Engineer')
  })

  it('collapses when the toggle is clicked and hides description/company', async () => {
    const w = factory()
    await flushPromises()
    await w.find('.job-panel-toggle').trigger('click')
    expect(w.find('.workspace__job-panel--collapsed').exists()).toBe(true)
    expect(w.find('.job-details__company').exists()).toBe(false)
  })

  it('persists the collapsed state to localStorage', async () => {
    const w = factory()
    await flushPromises()
    await w.find('.job-panel-toggle').trigger('click')
    expect(localStorage.getItem('peregrine_apply_jobpanel_collapsed')).toBe('true')
  })

  it('restores a previously collapsed state on mount', async () => {
    localStorage.setItem('peregrine_apply_jobpanel_collapsed', 'true')
    const w = factory()
    await flushPromises()
    expect(w.find('.workspace__job-panel--collapsed').exists()).toBe(true)
  })

  it('toggling back to expanded clears the collapsed grid class', async () => {
    localStorage.setItem('peregrine_apply_jobpanel_collapsed', 'true')
    const w = factory()
    await flushPromises()
    await w.find('.job-panel-toggle').trigger('click')
    expect(w.find('.workspace__job-panel--collapsed').exists()).toBe(false)
    expect(localStorage.getItem('peregrine_apply_jobpanel_collapsed')).toBe('false')
  })
})

describe('ApplyWorkspace — Resume Optimizer modal', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
    mockFetch.mockResolvedValue({ data: SAMPLE_JOB, error: null })
  })

  it('does not render the optimizer modal until the trigger is clicked', async () => {
    const w = factory()
    await flushPromises()
    expect(w.find('[role="dialog"]').exists()).toBe(false)
  })

  function findResumeSectionToggle(w: ReturnType<typeof factory>) {
    // Resume section defaults to collapsed -- find it among all
    // CollapsibleSection toggles by its label, since the Cover Letter
    // section's toggle (expanded by default) shares the same class.
    const toggle = w.findAll('.collapsible-section__toggle')
      .find(t => t.text().includes('Resume'))
    if (!toggle) throw new Error('Resume section toggle not found')
    return toggle
  }

  it('opens the optimizer modal when the trigger button is clicked', async () => {
    const w = factory()
    await flushPromises()
    await findResumeSectionToggle(w).trigger('click')
    await w.find('.optimizer-trigger').trigger('click')
    expect(w.find('[role="dialog"]').exists()).toBe(true)
  })

  it('closes the optimizer modal when its close button is clicked', async () => {
    const w = factory()
    await flushPromises()
    await findResumeSectionToggle(w).trigger('click')
    await w.find('.optimizer-trigger').trigger('click')
    await w.find('[role="dialog"] .btn-close').trigger('click')
    expect(w.find('[role="dialog"]').exists()).toBe(false)
  })
})
