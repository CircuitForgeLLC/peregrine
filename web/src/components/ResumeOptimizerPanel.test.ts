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

async function mountPanel(report = gapData) {
  setActivePinia(createPinia())
  useAppConfigStore().tier = 'paid'
  fetchMock.mockImplementation(async (url: string) => {
    if (url.endsWith('/gap_cards')) {
      return { data: { cards: [{ term: 'Kubernetes', snippet: 's', suggestion: null }] }, error: null } as any
    }
    if (url.endsWith('/gap_cards/answers')) return { data: { approved_terms: approved, saved: approved.length }, error: null } as any
    if (url.endsWith('/resume_optimizer')) return { data: report, error: null } as any
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
    expect(JSON.parse(String(calls[0][1]?.body))).toEqual({
      full_rewrite: true, selected_gaps: ['Kubernetes', 'Terraform'], approved_terms: ['Kubernetes'],
    })
    expect(w.find('fieldset').exists()).toBe(false)
  })

  it('the panel passes terms in priority order', async () => {
    const w = await mountPanel({
      optimized_resume: '',
      ats_gap_report: [
        { term: 'Alpha', section: 'skills', priority: 3, rationale: 'r' },
        { term: 'Bravo', section: 'skills', priority: 1, rationale: 'r' },
        { term: 'Charlie', section: 'skills', priority: 2, rationale: 'r' },
        { term: 'Delta', section: 'skills', priority: 1, rationale: 'r' },
        { term: 'Echo', section: 'skills', priority: 3, rationale: 'r' },
      ],
    })
    await w.findAll('.rop__gap-checkbox')[2].setValue(false)
    await optimizeBtn(w).trigger('click')
    await flushPromises()
    const call = fetchMock.mock.calls.find((c) => String(c[0]).endsWith('/gap_cards'))!
    expect(JSON.parse(String(call[1]?.body)).terms).toEqual(['Bravo', 'Delta', 'Alpha', 'Echo'])
  })

  it('test_all_answered_not_usable_reaches_nothing_to_rewrite', async () => {
    fetchMock.mockImplementation(async (url: string) => {
      if (url.endsWith('/gap_cards')) {
        return { data: { cards: [
          { term: 'Kubernetes', snippet: 's', suggestion: { id: 1, kind: 'none', text: '', visibility: 'document', requirement: 'Kubernetes', exact: true } },
          { term: 'Terraform', snippet: 's', suggestion: { id: 2, kind: 'experience', text: 'x', visibility: 'private', requirement: 'Terraform', exact: true } },
        ] }, error: null } as any
      }
      if (url.endsWith('/resume_optimizer')) return { data: gapData, error: null } as any
      if (url.endsWith('/resume_optimizer/task')) return { data: { status: 'none', stage: null }, error: null } as any
      return { data: {}, error: null } as any
    })
    setActivePinia(createPinia())
    useAppConfigStore().tier = 'paid'
    const w = mount(ResumeOptimizerPanel, { props: { jobId: 7 } })
    await flushPromises()
    await optimizeBtn(w).trigger('click')
    await flushPromises()
    expect(w.find('fieldset').exists()).toBe(false)
    await w.find('button.gcs__btn--primary').trigger('click')
    await flushPromises()
    expect(generateCalls()).toHaveLength(0)
    expect(w.text()).toContain('Nothing to rewrite. None of your answers can be used in a resume yet.')
  })

  it('test_the_rewrite_request_carries_approved_terms_and_selected_gaps', async () => {
    approved = ['Terraform']
    const w = await mountPanel()
    await optimizeBtn(w).trigger('click')
    await flushPromises()
    await w.find('button.gcs__btn--primary').trigger('click')
    await flushPromises()
    const body = JSON.parse(String(generateCalls()[0][1]?.body))
    expect(body.selected_gaps).toEqual(['Kubernetes', 'Terraform'])
    expect(body.approved_terms).toEqual(['Terraform'])
  })

  it('does not start the rewrite when nothing was approved and says so calmly', async () => {
    approved = []
    const w = await mountPanel()
    await optimizeBtn(w).trigger('click')
    await flushPromises()
    await w.find('button.gcs__btn--primary').trigger('click')
    await flushPromises()
    expect(generateCalls()).toHaveLength(0)
    expect(w.text()).toContain('Nothing to rewrite. None of your answers can be used in a resume yet. Choose Optimize Resume to change them.')
    expect(w.text()).not.toContain('have an answer from you')
    expect(w.find('fieldset').exists()).toBe(false)
  })

  async function openAndType(w: Awaited<ReturnType<typeof mountPanel>>) {
    await optimizeBtn(w).trigger('click')
    await flushPromises()
    await w.find('input[value="yes"]').setValue(true)
    await w.find('textarea').setValue('Ran clusters')
  }
  const typedValue = (w: Awaited<ReturnType<typeof mountPanel>>) =>
    (w.find('textarea').element as HTMLTextAreaElement).value
  const backBtn = (w: Awaited<ReturnType<typeof mountPanel>>) =>
    w.findAll('button').find((b) => b.text() === 'Back')!

  it('test_typed_answers_survive_back_and_reopen', async () => {
    const w = await mountPanel()
    await openAndType(w)
    await backBtn(w).trigger('click')
    await optimizeBtn(w).trigger('click')
    await flushPromises()
    expect(typedValue(w)).toBe('Ran clusters')
  })

  it('test_typed_answers_survive_toggling_a_gap_checkbox', async () => {
    const w = await mountPanel()
    await openAndType(w)
    await w.findAll('.rop__gap-checkbox')[1].setValue(false)
    await w.findAll('.rop__gap-checkbox')[1].setValue(true)
    await optimizeBtn(w).trigger('click')
    await flushPromises()
    expect(typedValue(w)).toBe('Ran clusters')
  })

  it('test_drafts_are_cleared_after_a_successful_save', async () => {
    approved = []
    const w = await mountPanel()
    await openAndType(w)
    await w.find('button.gcs__btn--primary').trigger('click')
    await flushPromises()
    await optimizeBtn(w).trigger('click')
    await flushPromises()
    expect(w.find('textarea').exists()).toBe(false)
    expect((w.find('input[value="skip"]').element as HTMLInputElement).checked).toBe(true)
  })

  it('test_a_draft_for_a_term_that_is_no_longer_selected_is_dropped', async () => {
    const w = await mountPanel()
    await openAndType(w)
    await w.findAll('.rop__gap-checkbox')[0].setValue(false)
    await optimizeBtn(w).trigger('click')
    await flushPromises()
    await backBtn(w).trigger('click')
    await w.findAll('.rop__gap-checkbox')[0].setValue(true)
    await optimizeBtn(w).trigger('click')
    await flushPromises()
    expect(w.find('textarea').exists()).toBe(false)
  })

  async function deselectAll(w: Awaited<ReturnType<typeof mountPanel>>) {
    for (const box of w.findAll('.rop__gap-checkbox')) await box.setValue(false)
  }

  it('test_rewrite_again_with_nothing_selected_shows_a_message_and_does_not_start_a_rewrite', async () => {
    const w = await mountPanel()
    await deselectAll(w)
    ;(w.vm as any).openCards()
    await flushPromises()
    const notice = w.find('.rop__select-notice')
    expect(notice.attributes('aria-live')).toBe('polite')
    expect(notice.text()).toBe('Select at least one keyword to rewrite for.')
    expect(w.find('fieldset').exists()).toBe(false)
    expect(generateCalls()).toHaveLength(0)
    await w.findAll('.rop__gap-checkbox')[0].setValue(true)
    expect(w.find('.rop__select-notice').text()).toBe('')
  })

  it('shows the same message from the review modal rewrite-again path', async () => {
    const w = await mountPanel()
    await deselectAll(w)
    ;(w.vm as any).handleRewriteAgain()
    await flushPromises()
    expect(w.find('.rop__select-notice').text()).toBe('Select at least one keyword to rewrite for.')
    expect(generateCalls()).toHaveLength(0)
  })

  it('returns focus to the rewrite button when the cards close', async () => {
    const w = await mountPanel()
    w.unmount()
    setActivePinia(createPinia())
    useAppConfigStore().tier = 'paid'
    const w2 = mount(ResumeOptimizerPanel, { props: { jobId: 7 }, attachTo: document.body })
    await flushPromises()
    await optimizeBtn(w2).trigger('click')
    await flushPromises()
    await backBtn(w2).trigger('click')
    await flushPromises()
    expect(document.activeElement).toBe(optimizeBtn(w2).element)
    w2.unmount()
  })

  it('test_focus_moves_to_the_rewrite_progress_status_after_a_save_that_starts_a_rewrite', async () => {
    approved = ['Kubernetes']
    const w = await mountPanel()
    w.unmount()
    setActivePinia(createPinia())
    useAppConfigStore().tier = 'paid'
    const w2 = mount(ResumeOptimizerPanel, { props: { jobId: 7 }, attachTo: document.body })
    await flushPromises()
    await optimizeBtn(w2).trigger('click')
    await flushPromises()
    await w2.find('button.gcs__btn--primary').trigger('click')
    await flushPromises()
    const status = w2.find('.rop__rewrite .rop__spinner-row')
    expect(status.exists()).toBe(true)
    expect(document.activeElement).toBe(status.element)
    w2.unmount()
  })

  describe('claims notice on the review step', () => {
    const baseDraft = {
      sections: [
        { section: 'skills', type: 'skills', original: ['Python'], proposed: ['Python', 'Docker'], added: ['Docker'], removed: [], gap_terms: [] },
      ],
      rewritten_struct: {},
    }

    async function mountReview(draft: Record<string, unknown>) {
      setActivePinia(createPinia())
      useAppConfigStore().tier = 'paid'
      fetchMock.mockImplementation(async (url: string) => {
        if (url.endsWith('/resume_optimizer/review')) return { data: { draft }, error: null } as any
        if (url.endsWith('/resume_optimizer/task')) return { data: { status: 'awaiting_review', stage: null }, error: null } as any
        if (url.endsWith('/resume_optimizer')) return { data: { optimized_resume: '', ats_gap_report: [] }, error: null } as any
        return { data: {}, error: null } as any
      })
      const w = mount(ResumeOptimizerPanel, { props: { jobId: 7 }, attachTo: document.body })
      await flushPromises()
      return w
    }
    const openReview = async (w: Awaited<ReturnType<typeof mountReview>>) => {
      await w.find('.rop__review-trigger button').trigger('click')
      await flushPromises()
    }

    it('test_the_review_modal_shows_the_claims_notice_for_a_draft_with_a_claims_report', async () => {
      const w = await mountReview({ ...baseDraft, claims_report: { novel_words: ['kubernetes'], unused_terms: ['Terraform'] } })
      await openReview(w)
      const dialog = document.body.querySelector('[role="dialog"]')!
      expect(dialog).not.toBeNull()
      const notice = dialog.querySelector('section[aria-labelledby="cn-heading"]')!
      expect(notice).not.toBeNull()
      expect(notice.textContent).toContain('kubernetes')
      expect(notice.textContent).toContain('Terraform')
      w.unmount()
    })

    it('test_the_review_modal_shows_no_notice_for_a_draft_without_a_claims_report', async () => {
      const w = await mountReview({ ...baseDraft })
      await openReview(w)
      expect(document.body.querySelector('[role="dialog"]')).not.toBeNull()
      expect(document.body.querySelector('#cn-heading')).toBeNull()
      w.unmount()
    })

    it('test_the_trigger_card_no_longer_shows_the_claims_notice', async () => {
      const w = await mountReview({ ...baseDraft, claims_report: { novel_words: ['kubernetes'], unused_terms: ['Terraform'] } })
      expect(w.find('.rop__review-trigger').exists()).toBe(true)
      expect(w.find('.rop__review-trigger').text()).not.toContain('kubernetes')
      expect(document.body.querySelector('#cn-heading')).toBeNull()
      w.unmount()
    })
  })
})
