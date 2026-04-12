import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import ResumeReviewModal from '../ResumeReviewModal.vue'

const minimalDraft = {
  sections: [
    { section: 'skills', type: 'skills_diff', added: ['Python', 'FastAPI'], removed: [], kept: ['Git'] },
    { section: 'summary', type: 'text_diff', original: 'Old summary.', proposed: 'New summary.' },
    {
      section: 'experience', type: 'bullets_diff',
      entries: [
        { title: 'Staff Eng', company: 'Acme', original_bullets: ['Did A'], proposed_bullets: ['Led A'] },
        { title: 'SWE', company: 'Beta', original_bullets: ['Did B'], proposed_bullets: ['Led B'] },
      ],
    },
  ],
  rewritten_struct: {},
}

const factory = (draft = minimalDraft) =>
  mount(ResumeReviewModal, {
    props: { jobId: 1, draft },
    global: { stubs: { Teleport: true } },
  })

describe('page generation', () => {
  it('generates skills + summary + 2 experience + confirm = 5 pages', () => {
    const w = factory()
    expect(w.findAll('[role="tab"]').length).toBe(5)
  })

  it('confirm tab has no status dot', () => {
    const w = factory()
    const tabs = w.findAll('[role="tab"]')
    const confirmTab = tabs[tabs.length - 1]
    expect(confirmTab.text()).toContain('Confirm')
    expect(confirmTab.find('.tab__dot').exists()).toBe(false)
  })
})

describe('tab status', () => {
  it('all non-confirm tabs start as unvisited', () => {
    const w = factory()
    const dots = w.findAll('.tab__dot')
    dots.forEach(d => expect(d.classes()).toContain('tab__dot--unvisited'))
  })

  it('visiting a page marks it in-progress', async () => {
    const w = factory()
    await w.find('[role="tab"]').trigger('click')
    const firstDot = w.findAll('.tab__dot')[0]
    expect(firstDot.classes()).toContain('tab__dot--in-progress')
  })
})

describe('navigation', () => {
  it('next button advances to page 2', async () => {
    const w = factory()
    expect(w.find('.rrm__page-counter').text()).toContain('1')
    await w.find('.rrm__next').trigger('click')
    expect(w.find('.rrm__page-counter').text()).toContain('2')
  })

  it('back button on page 1 is disabled', () => {
    const w = factory()
    expect(w.find('.rrm__back').attributes('disabled')).toBeDefined()
  })

  it('emits close when X button clicked', async () => {
    const w = factory()
    await w.find('.rrm__close').trigger('click')
    expect(w.emitted('close')).toBeTruthy()
  })
})

describe('decisions emit', () => {
  it('emits submit with correct shape when Preview clicked on confirm page', async () => {
    const w = factory()
    // Navigate to confirm page (page 5 = index 4)
    for (let i = 0; i < 4; i++) {
      await w.find('.rrm__next').trigger('click')
    }
    await w.find('.rrm__preview').trigger('click')
    const emitted = w.emitted('submit')
    expect(emitted).toBeTruthy()
    const decisions = emitted![0][0] as Record<string, unknown>
    expect(decisions).toHaveProperty('skills')
    expect(decisions).toHaveProperty('summary')
    expect(decisions).toHaveProperty('experience')
  })
})
