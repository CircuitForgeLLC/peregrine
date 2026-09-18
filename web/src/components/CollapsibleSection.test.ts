import { describe, it, expect, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import CollapsibleSection from './CollapsibleSection.vue'

describe('CollapsibleSection', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('renders the title and slot content', () => {
    const wrapper = mount(CollapsibleSection, {
      props: { title: 'Cover Letter', modelValue: true },
      slots: { default: '<p>body content</p>' },
    })
    expect(wrapper.text()).toContain('Cover Letter')
    expect(wrapper.text()).toContain('body content')
  })

  it('defaults to collapsed and hides slot content when no modelValue/persistId given', () => {
    const wrapper = mount(CollapsibleSection, {
      props: { title: 'Resume' },
      slots: { default: '<p>body content</p>' },
    })
    expect(wrapper.text()).not.toContain('body content')
    expect(wrapper.find('button').attributes('aria-expanded')).toBe('false')
  })

  it('respects defaultExpanded when true', () => {
    const wrapper = mount(CollapsibleSection, {
      props: { title: 'Resume', defaultExpanded: true },
      slots: { default: '<p>body content</p>' },
    })
    expect(wrapper.text()).toContain('body content')
  })

  it('toggles on click and emits update:modelValue (controlled mode)', async () => {
    const wrapper = mount(CollapsibleSection, {
      props: { title: 'Cover Letter', modelValue: false },
      slots: { default: '<p>body content</p>' },
    })
    expect(wrapper.text()).not.toContain('body content')
    await wrapper.find('button').trigger('click')
    expect(wrapper.emitted('update:modelValue')).toEqual([[true]])
  })

  it('renders a badge when provided', () => {
    const wrapper = mount(CollapsibleSection, {
      props: { title: 'Q&A', badge: 3 },
    })
    expect(wrapper.text()).toContain('3')
  })

  it('does not render a badge element when badge is omitted', () => {
    const wrapper = mount(CollapsibleSection, {
      props: { title: 'Q&A' },
    })
    expect(wrapper.find('.collapsible-section__badge').exists()).toBe(false)
  })

  it('with a persistId, persists expanded state to localStorage across mounts', async () => {
    const wrapper1 = mount(CollapsibleSection, {
      props: { title: 'Resume', persistId: 'peregrine_test_section' },
      slots: { default: '<p>body content</p>' },
    })
    await wrapper1.find('button').trigger('click')
    expect(localStorage.getItem('peregrine_test_section')).toBe('true')

    const wrapper2 = mount(CollapsibleSection, {
      props: { title: 'Resume', persistId: 'peregrine_test_section' },
      slots: { default: '<p>body content</p>' },
    })
    expect(wrapper2.text()).toContain('body content')
  })

  it('a persistId takes priority over a controlled modelValue', () => {
    localStorage.setItem('peregrine_test_priority', 'true')
    const wrapper = mount(CollapsibleSection, {
      props: { title: 'Resume', persistId: 'peregrine_test_priority', modelValue: false },
      slots: { default: '<p>body content</p>' },
    })
    // persistId wins -- this is what lets a parent use a plain ref (like
    // Q&A's dynamic auto-expand-on-data logic) for sections that opt out
    // of persistence, while other sections opt in via persistId alone.
    expect(wrapper.text()).toContain('body content')
  })
})
