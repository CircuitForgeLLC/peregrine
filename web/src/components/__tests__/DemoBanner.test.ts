import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import DemoBanner from '../DemoBanner.vue'

describe('DemoBanner', () => {
  it('renders the demo label', () => {
    const w = mount(DemoBanner)
    expect(w.text()).toContain('Demo mode')
  })

  it('renders a free key link', () => {
    const w = mount(DemoBanner)
    expect(w.find('a.demo-banner__cta--primary').exists()).toBe(true)
    expect(w.find('a.demo-banner__cta--primary').text()).toContain('free key')
  })

  it('renders a self-host link', () => {
    const w = mount(DemoBanner)
    expect(w.find('a.demo-banner__cta--secondary').exists()).toBe(true)
    expect(w.find('a.demo-banner__cta--secondary').text()).toContain('Self-host')
  })
})
