import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { setActivePinia, createPinia } from 'pinia'

vi.mock('../composables/useApi', () => ({
  useApiFetch: vi.fn(),
  apiUrl: (p: string) => p,
}))

import { useApiFetch } from '../composables/useApi'
import { useAppConfigStore } from '../stores/appConfig'
import ResumeOptimizerPanel from './ResumeOptimizerPanel.vue'

const fetchMock = vi.mocked(useApiFetch)
let approved: string[] = []

const gapData = {
  optimized_resume: '',
  ats_gap_report: [
    { term: 'Kubernetes', section: 'skills', priority: 1, rationale: 'r1' },
    { term: 'Terraform', section: 'skills', priority: 2, rationale: 'r2' },
  ],
}

async function mountPanel() {
  setActivePinia(createPinia())
  useAppConfigStore().tier = 'paid'
  fetchMock.mockImplementation(async (url: string) => {
    if (url.endsWith('/gap_cards')) {
      return { data: { cards: [{ term: 'Kubernetes', snippet: 's', suggestion: null }] }, error: null } as any
    }
    if (url.endsWith('/gap_cards/answers')) return { data: { approved_terms: approved, saved: approved.length }, error: null } as any
    if (url.endsWith('/resume_optimizer')) return { data: gapData, error: null } as any
    if (url.endsWith('/resume_optimizer/task')) return { data: { status: 'none', stage: null }, error: null } as any
    return { data: {}, error: null } as any
  })
  const w = mount(ResumeOptimizerPanel, { props: { jobId: 7 } })
  await flushPromises()
  return w
}

const optimizeBtn = (w: Awaited<ReturnType<typeof mountPanel>>) =>
  w.findAll('button').find((b) => b.text().includes('Optimize Resume'))!
const generateCalls = () =>
  fetchMock.mock.calls.filter((c) => String(c[0]).endsWith('/resume_optimizer/generate'))

describe('ResumeOptimizerPanel full rewrite flow', () => {
  beforeEach(() => { vi.clearAllMocks(); approved = [] })

  it('disables Optimize Resume with a visible hint when no gap is selected', async () => {
    const w = await mountPanel()
    expect(optimizeBtn(w).attributes('disabled')).toBeUndefined()
    for (const box of w.findAll('.rop__gap-checkbox')) await box.setValue(false)
    expect(optimizeBtn(w).attributes('disabled')).toBeDefined()
    expect(w.find('#rop-select-hint').text()).toContain('Select at least one keyword')
  })

  it('shows the cards first and only starts the rewrite after done with approved terms', async () => {
    approved = ['Kubernetes']
    const w = await mountPanel()
    await optimizeBtn(w).trigger('click')
    await flushPromises()
    expect(w.find('fieldset').exists()).toBe(true)
    expect(generateCalls()).toHaveLength(0)

    await w.find('input[value="no"]').setValue(true)
    await w.find('button.gcs__btn--primary').trigger('click')
    await flushPromises()
    const calls = generateCalls()
    expect(calls).toHaveLength(1)
    expect(JSON.parse(String(calls[0][1]?.body))).toEqual({ full_rewrite: true, selected_gaps: ['Kubernetes', 'Terraform'] })
    expect(w.find('fieldset').exists()).toBe(false)
  })

  it('does not start the rewrite when nothing was approved and says so calmly', async () => {
    approved = []
    const w = await mountPanel()
    await optimizeBtn(w).trigger('click')
    await flushPromises()
    await w.find('button.gcs__btn--primary').trigger('click')
    await flushPromises()
    expect(generateCalls()).toHaveLength(0)
    expect(w.text()).toContain('Nothing to rewrite yet, because none of these keywords have an answer from you.')
    expect(w.find('fieldset').exists()).toBe(false)
  })
})
