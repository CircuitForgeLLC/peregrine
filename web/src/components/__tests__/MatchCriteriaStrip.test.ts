import { describe, it, expect, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createRouter, createWebHistory } from 'vue-router'
import MatchCriteriaStrip from '../MatchCriteriaStrip.vue'
import { useSearchStore } from '../../stores/settings/search'
import { useResumeStore } from '../../stores/settings/resume'

function makeRouter() {
  return createRouter({ history: createWebHistory(), routes: [{ path: '/:p*', component: { template: '<div/>' } }] })
}

function factory() {
  return mount(MatchCriteriaStrip, { global: { plugins: [makeRouter()] } })
}

describe('MatchCriteriaStrip', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('shows the first location plus a count of the rest', () => {
    useSearchStore().locations = ['San Francisco', 'Remote', 'New York']
    const w = factory()
    expect(w.text()).toContain('San Francisco +2')
  })

  it('shows a single location with no +N suffix', () => {
    useSearchStore().locations = ['Remote']
    const w = factory()
    expect(w.text()).toContain('Remote')
    expect(w.text()).not.toMatch(/Remote\s*\+/)
  })

  it('renders an unset pill for locations when none are configured', () => {
    useSearchStore().locations = []
    const w = factory()
    expect(w.text()).toContain('Locations?')
    expect(w.find('.criteria-pill--unset').exists()).toBe(true)
  })

  it('formats salary as $Xk+ when min salary is set', () => {
    useResumeStore().salary_min = 140000
    const w = factory()
    expect(w.text()).toContain('$140k+')
  })

  it('shows an unset pill when min salary is not configured', () => {
    useResumeStore().salary_min = 0
    const w = factory()
    expect(w.text()).toContain('Min salary?')
  })

  it('maps remote_preference to a readable label', () => {
    useSearchStore().remote_preference = 'remote'
    const w = factory()
    expect(w.text()).toContain('Remote')
  })

  it('shows a checkmark on the resume pill when a resume is uploaded', () => {
    useResumeStore().hasResume = true
    const w = factory()
    const pills = w.findAll('.criteria-pill')
    const resumePill = pills.find(p => p.text().includes('Resume'))
    expect(resumePill?.text()).toContain('✓')
    expect(resumePill?.classes()).not.toContain('criteria-pill--unset')
  })

  it('marks the resume pill unset when no resume is uploaded', () => {
    useResumeStore().hasResume = false
    const w = factory()
    const pills = w.findAll('.criteria-pill')
    const resumePill = pills.find(p => p.text().includes('Resume'))
    expect(resumePill?.classes()).toContain('criteria-pill--unset')
  })

  it('renders an edit-preferences link to /settings/search', () => {
    const w = factory()
    const link = w.find('a[href="/settings/search"]')
    expect(link.exists()).toBe(true)
    expect(link.text()).toContain('Edit preferences')
  })

  it('shows the first job title plus a count of the rest', () => {
    useSearchStore().job_titles = ['Backend Engineer', 'Platform Engineer']
    const w = factory()
    expect(w.text()).toContain('Backend Engineer +1')
  })
})
