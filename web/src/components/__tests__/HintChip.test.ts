import { describe, it, expect, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import HintChip from '../HintChip.vue'

beforeEach(() => { localStorage.clear() })

const factory = (viewKey = 'home', message = 'Test hint') =>
  mount(HintChip, { props: { viewKey, message } })

describe('HintChip', () => {
  it('renders the message', () => {
    const w = factory()
    expect(w.text()).toContain('Test hint')
  })

  it('is hidden when localStorage key is already set', () => {
    localStorage.setItem('peregrine_hint_home', '1')
    const w = factory()
    expect(w.find('.hint-chip').exists()).toBe(false)
  })

  it('hides and sets localStorage when dismiss button is clicked', async () => {
    const w = factory()
    await w.find('.hint-chip__dismiss').trigger('click')
    expect(w.find('.hint-chip').exists()).toBe(false)
    expect(localStorage.getItem('peregrine_hint_home')).toBe('1')
  })
})
