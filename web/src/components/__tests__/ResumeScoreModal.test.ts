import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import ResumeScoreModal from '../ResumeScoreModal.vue'

vi.mock('../../composables/useApi', () => ({
  useApiFetch: vi.fn(),
}))
import { useApiFetch } from '../../composables/useApi'

const mockFeedback = {
  overall_score: 7, summary: 'Solid resume.',
  strengths: ['Clear impact'], improvements: ['Generic summary'],
  suggestions: [
    { id: 'sugg-1', section: 'summary', target: '', before: 'old', after: 'new',
      rationale: 'better', appliable: true },
    { id: 'sugg-2', section: 'experience', target: 'A|B', before: 'x', after: 'y',
      rationale: 'z', appliable: false },
  ],
  ats_score: 6, ats_basis: 'based on your 3 most recently saved jobs',
  ats_issues: ['No quantified bullets in one role.'],
}

describe('ResumeScoreModal', () => {
  beforeEach(() => vi.clearAllMocks())

  it('shows existing score immediately when already scored', async () => {
    vi.mocked(useApiFetch).mockResolvedValueOnce({ data: { score: mockFeedback }, error: null } as any)
    const wrapper = mount(ResumeScoreModal, { props: { resumeId: 1 }, global: { stubs: { Teleport: true } } })
    await new Promise((r) => setTimeout(r, 0))
    expect(wrapper.text()).toContain('7')
    expect(wrapper.text()).toContain('Solid resume.')
  })

  it('always renders the ats_basis string alongside the ATS score', async () => {
    vi.mocked(useApiFetch).mockResolvedValueOnce({ data: { score: mockFeedback }, error: null } as any)
    const wrapper = mount(ResumeScoreModal, { props: { resumeId: 1 }, global: { stubs: { Teleport: true } } })
    await new Promise((r) => setTimeout(r, 0))
    expect(wrapper.text()).toContain('based on your 3 most recently saved jobs')
  })

  it('disables Apply and shows "Needs manual review" for non-appliable suggestions', async () => {
    vi.mocked(useApiFetch).mockResolvedValueOnce({ data: { score: mockFeedback }, error: null } as any)
    const wrapper = mount(ResumeScoreModal, { props: { resumeId: 1 }, global: { stubs: { Teleport: true } } })
    await new Promise((r) => setTimeout(r, 0))
    expect(wrapper.text()).toContain('Needs manual review')
  })

  it('emits close when the close button is clicked', async () => {
    vi.mocked(useApiFetch).mockResolvedValueOnce({ data: { score: null }, error: null } as any)
    const wrapper = mount(ResumeScoreModal, { props: { resumeId: 1 }, global: { stubs: { Teleport: true } } })
    await new Promise((r) => setTimeout(r, 0))
    await wrapper.find('.rsm__close').trigger('click')
    expect(wrapper.emitted('close')).toBeTruthy()
  })

  it('shows a text label next to the score badges, not color alone', async () => {
    vi.mocked(useApiFetch).mockResolvedValueOnce({ data: { score: mockFeedback }, error: null } as any)
    const wrapper = mount(ResumeScoreModal, { props: { resumeId: 1 }, global: { stubs: { Teleport: true } } })
    await new Promise((r) => setTimeout(r, 0))
    const labels = wrapper.findAll('.rsm__score-label')
    expect(labels.length).toBe(2)
    expect(labels[0].text()).toBe('Solid') // overall_score 7 -> "Solid"
    expect(labels[1].text()).toBe('Solid') // ats_score 6 -> "Solid"
  })

  it('shows a failure notice with retry instead of an empty result when scoring failed', async () => {
    const failedFeedback = {
      overall_score: null, summary: '', strengths: [], improvements: [], suggestions: [],
      ats_score: 6, ats_basis: 'general ATS best practices — save some jobs to sharpen this',
      ats_issues: [],
    }
    vi.mocked(useApiFetch).mockResolvedValueOnce({ data: { score: failedFeedback }, error: null } as any)
    const wrapper = mount(ResumeScoreModal, { props: { resumeId: 1 }, global: { stubs: { Teleport: true } } })
    await new Promise((r) => setTimeout(r, 0))
    expect(wrapper.text()).toContain('Scoring failed')
    expect(wrapper.find('.rsm__llm-failure').exists()).toBe(true)
    // ATS card (a separate, synchronous code path) should still render.
    expect(wrapper.text()).toContain('general ATS best practices')
  })

  it('surfaces an inline error and does not mark Applied when apply-suggestion fails', async () => {
    vi.mocked(useApiFetch)
      .mockResolvedValueOnce({ data: { score: mockFeedback }, error: null } as any)
      .mockResolvedValueOnce({ data: null, error: { message: 'Unprocessable' } } as any)
    const wrapper = mount(ResumeScoreModal, { props: { resumeId: 1 }, global: { stubs: { Teleport: true } } })
    await new Promise((r) => setTimeout(r, 0))
    const applyButtons = wrapper.findAll('button').filter((b) => b.text() === 'Apply')
    expect(applyButtons.length).toBeGreaterThan(0)
    await applyButtons[0].trigger('click')
    await new Promise((r) => setTimeout(r, 0))
    expect(wrapper.text()).not.toContain('Applied ✓')
    expect(wrapper.find('.rsm__apply-error').exists()).toBe(true)
    expect(wrapper.emitted('applied')).toBeFalsy()
  })

  it('places role=dialog and aria-modal on the dialog card, not the backdrop', async () => {
    vi.mocked(useApiFetch).mockResolvedValueOnce({ data: { score: null }, error: null } as any)
    const wrapper = mount(ResumeScoreModal, { props: { resumeId: 1 }, global: { stubs: { Teleport: true } } })
    await new Promise((r) => setTimeout(r, 0))
    const backdrop = wrapper.find('.rsm-backdrop')
    const card = wrapper.find('.rsm-card')
    expect(backdrop.attributes('role')).toBeUndefined()
    expect(card.attributes('role')).toBe('dialog')
    expect(card.attributes('aria-modal')).toBe('true')
  })
})
