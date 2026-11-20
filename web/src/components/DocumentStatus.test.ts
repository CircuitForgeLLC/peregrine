import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import DocumentStatus from './DocumentStatus.vue'

// peregrine#256: a generated letter and an approved tailored resume are separate statuses. A job
// with only a letter must not look finished, and the two states must differ by symbol and words,
// not by colour alone.

function render(props: { hasLetter: boolean; hasResume: boolean; compact?: boolean }) {
  return mount(DocumentStatus, { props })
}

describe('DocumentStatus', () => {
  it('shows neither as done for a new job', () => {
    const text = render({ hasLetter: false, hasResume: false }).text()
    expect(text).toContain('No letter')
    expect(text).toContain('Resume not tailored')
    expect(text).not.toContain('Letter drafted')
    expect(text).not.toContain('Resume tailored')
  })

  it('a generated letter does not mark the resume as done', () => {
    const wrapper = render({ hasLetter: true, hasResume: false })
    expect(wrapper.text()).toContain('Letter drafted')
    expect(wrapper.text()).toContain('Resume not tailored')
    expect(wrapper.findAll('.doc-status__item--done')).toHaveLength(1)
  })

  it('an approved resume does not mark the letter as done', () => {
    const wrapper = render({ hasLetter: false, hasResume: true })
    expect(wrapper.text()).toContain('No letter')
    expect(wrapper.text()).toContain('Resume tailored')
    expect(wrapper.findAll('.doc-status__item--done')).toHaveLength(1)
  })

  it('shows both as done when both exist', () => {
    const wrapper = render({ hasLetter: true, hasResume: true })
    expect(wrapper.findAll('.doc-status__item--done')).toHaveLength(2)
    expect(wrapper.text()).toContain('Letter drafted')
    expect(wrapper.text()).toContain('Resume tailored')
  })

  it('does not rely on colour alone: done and pending use different symbols', () => {
    const done = render({ hasLetter: true, hasResume: true }).text()
    const pending = render({ hasLetter: false, hasResume: false }).text()
    expect(done).toContain('✓')
    expect(done).not.toContain('○')
    expect(pending).toContain('○')
    expect(pending).not.toContain('✓')
  })

  it('the compact layout is short on screen but still labelled in full for screen readers', () => {
    const wrapper = render({ hasLetter: true, hasResume: false, compact: true })
    const visible = wrapper.findAll('[aria-hidden="true"]').map((el) => el.text()).join(' ')
    expect(visible).toContain('Letter ✓')
    expect(visible).toContain('Resume ○')
    const spoken = wrapper.findAll('.sr-only').map((el) => el.text()).join(' ')
    expect(spoken).toContain('Letter drafted')
    expect(spoken).toContain('Resume not tailored')
  })

  it('the full layout exposes the words to everyone and does not hide them', () => {
    const wrapper = render({ hasLetter: false, hasResume: true })
    expect(wrapper.findAll('[aria-hidden="true"]').map((el) => el.text()).join(' ')).not.toContain('Letter drafted')
    expect(wrapper.text()).toContain('No letter')
  })

  it('is exposed as a list with one item per document', () => {
    const wrapper = render({ hasLetter: true, hasResume: false })
    expect(wrapper.attributes('role')).toBe('list')
    expect(wrapper.findAll('[role="listitem"]')).toHaveLength(2)
  })
})
