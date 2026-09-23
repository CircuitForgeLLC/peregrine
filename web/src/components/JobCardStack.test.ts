import { describe, it, expect, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import JobCardStack from './JobCardStack.vue'
import JobCard from './JobCard.vue'
import type { Job } from '../stores/review'

const SAMPLE_JOB: Job = {
  id: 1,
  title: 'Software Engineer',
  company: 'Acme Corp',
  url: 'https://example.com/job/1',
  source: 'linkedin',
  location: 'Remote',
  is_remote: true,
  salary: null,
  description: 'A'.repeat(500),
  match_score: null,
  keyword_gaps: null,
  date_found: '2026-09-01',
  date_posted: null,
  shadow_score: null,
  status: 'pending',
}

function firePointerDown(el: Element) {
  el.dispatchEvent(new Event('pointerdown', { bubbles: true }) as PointerEvent)
}

// Regression test: on mobile, expanding a card ("Show more") used to leave
// swipe-drag capture active, so any touch inside the expanded body (reading
// the full description) was hijacked as a swipe gesture instead of a page
// scroll -- touch-action: none plus setPointerCapture() on every pointerdown
// meant there was no way to scroll the now-taller card at all.
describe('JobCardStack — swipe vs. scroll while expanded', () => {
  beforeEach(() => {
    // jsdom does not implement pointer capture; stub it so pointerdown
    // handlers that call it don't throw during the test.
    if (!HTMLElement.prototype.setPointerCapture) {
      HTMLElement.prototype.setPointerCapture = () => {}
      HTMLElement.prototype.releasePointerCapture = () => {}
    }
  })

  it('does not engage swipe-drag (is-held) on pointerdown while the card is expanded', async () => {
    const wrapper = mount(JobCardStack, { props: { job: SAMPLE_JOB, remaining: 3 } })

    await wrapper.findComponent(JobCard).vm.$emit('expand')
    await wrapper.vm.$nextTick()

    const cardWrapper = wrapper.find('.card-wrapper')
    expect(cardWrapper.classes()).toContain('is-expanded')

    firePointerDown(cardWrapper.element)
    await wrapper.vm.$nextTick()

    expect(cardWrapper.classes()).not.toContain('is-held')
  })

  it('still engages swipe-drag (is-held) on pointerdown while collapsed', async () => {
    const wrapper = mount(JobCardStack, { props: { job: SAMPLE_JOB, remaining: 3 } })

    const cardWrapper = wrapper.find('.card-wrapper')
    expect(cardWrapper.classes()).not.toContain('is-expanded')

    firePointerDown(cardWrapper.element)
    await wrapper.vm.$nextTick()

    expect(cardWrapper.classes()).toContain('is-held')
  })

  it('resets is-expanded when a new job is slotted in', async () => {
    const wrapper = mount(JobCardStack, { props: { job: SAMPLE_JOB, remaining: 3 } })
    await wrapper.findComponent(JobCard).vm.$emit('expand')
    await wrapper.vm.$nextTick()
    expect(wrapper.find('.card-wrapper').classes()).toContain('is-expanded')

    await wrapper.setProps({ job: { ...SAMPLE_JOB, id: 2 } })
    await wrapper.vm.$nextTick()

    expect(wrapper.find('.card-wrapper').classes()).not.toContain('is-expanded')
  })
})
