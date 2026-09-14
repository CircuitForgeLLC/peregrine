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
})
