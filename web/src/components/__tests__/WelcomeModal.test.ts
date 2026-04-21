import { describe, it, expect, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import WelcomeModal from '../WelcomeModal.vue'

const LS_KEY = 'peregrine_demo_visited'

beforeEach(() => {
  localStorage.clear()
})

describe('WelcomeModal', () => {
  it('is visible when localStorage key is absent', () => {
    const w = mount(WelcomeModal, { global: { stubs: { Teleport: true } } })
    expect(w.find('.welcome-modal').exists()).toBe(true)
  })

  it('is hidden when localStorage key is set', () => {
    localStorage.setItem(LS_KEY, '1')
    const w = mount(WelcomeModal, { global: { stubs: { Teleport: true } } })
    expect(w.find('.welcome-modal').exists()).toBe(false)
  })

  it('dismisses and sets localStorage on primary CTA click', async () => {
    const w = mount(WelcomeModal, { global: { stubs: { Teleport: true } } })
    await w.find('.welcome-modal__explore').trigger('click')
    expect(w.find('.welcome-modal').exists()).toBe(false)
    expect(localStorage.getItem(LS_KEY)).toBe('1')
  })

  it('emits dismissed event on close', async () => {
    const w = mount(WelcomeModal, { global: { stubs: { Teleport: true } } })
    await w.find('.welcome-modal__explore').trigger('click')
    expect(w.emitted('dismissed')).toBeTruthy()
  })
})
