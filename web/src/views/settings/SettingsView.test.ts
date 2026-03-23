import { describe, it, expect, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createRouter, createWebHistory } from 'vue-router'
import SettingsView from './SettingsView.vue'
import { useAppConfigStore } from '../../stores/appConfig'

function makeRouter() {
  return createRouter({ history: createWebHistory(), routes: [{ path: '/:p*', component: { template: '<div/>' } }] })
}

describe('SettingsView sidebar', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('hides System group items in cloud mode', async () => {
    const store = useAppConfigStore()
    store.isCloud = true
    const wrapper = mount(SettingsView, { global: { plugins: [makeRouter()] } })
    expect(wrapper.find('[data-testid="nav-system"]').exists()).toBe(false)
  })

  it('shows System when not cloud', async () => {
    const store = useAppConfigStore()
    store.isCloud = false
    const wrapper = mount(SettingsView, { global: { plugins: [makeRouter()] } })
    expect(wrapper.find('[data-testid="nav-system"]').exists()).toBe(true)
  })

  it('hides Developer when neither devMode nor devTierOverride', () => {
    const store = useAppConfigStore()
    store.isDevMode = false
    localStorage.removeItem('dev_tier_override')
    const wrapper = mount(SettingsView, { global: { plugins: [makeRouter()] } })
    expect(wrapper.find('[data-testid="nav-developer"]').exists()).toBe(false)
  })

  it('shows Developer when devTierOverride is set in store', () => {
    const store = useAppConfigStore()
    store.isDevMode = false
    store.setDevTierOverride('premium')
    const wrapper = mount(SettingsView, { global: { plugins: [makeRouter()] } })
    expect(wrapper.find('[data-testid="nav-developer"]').exists()).toBe(true)
    store.setDevTierOverride(null)  // cleanup
  })
})
