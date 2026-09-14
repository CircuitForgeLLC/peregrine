import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createRouter, createWebHistory } from 'vue-router'
import { setActivePinia, createPinia } from 'pinia'

vi.mock('../../composables/useApi', () => ({
  useApiFetch: vi.fn(),
}))

import { useApiFetch } from '../../composables/useApi'
import MarketSnapshotCard from '../MarketSnapshotCard.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', component: { template: '<div />' } },
    { path: '/salary-calculator', component: { template: '<div />' } },
  ],
})

async function mountCard() {
  const w = mount(MarketSnapshotCard, {
    global: { plugins: [router] },
  })
  await router.isReady()
  return w
}

describe('MarketSnapshotCard', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  it('renders a loading state before the fetch resolves', () => {
    vi.mocked(useApiFetch).mockReturnValue(new Promise(() => {}) as never)
    const w = mount(MarketSnapshotCard, { global: { plugins: [router] } })
    expect(w.text()).toContain('Loading')
  })

  it('renders the role count from the API response', async () => {
    vi.mocked(useApiFetch).mockResolvedValueOnce({
      data: { count: 42, count_with_salary: 10, median: 90000, p25: 80000, p75: 100000 },
      error: null,
    })
    const w = await mountCard()
    await w.vm.$nextTick()
    await w.vm.$nextTick()
    expect(w.text()).toContain('42 open roles in your search results')
  })

  it('renders the p25-p75 range and the "M of N" sub-line when count_with_salary > 0', async () => {
    vi.mocked(useApiFetch).mockResolvedValueOnce({
      data: { count: 42, count_with_salary: 10, median: 90000, p25: 80000, p75: 100000 },
      error: null,
    })
    const w = await mountCard()
    await w.vm.$nextTick()
    await w.vm.$nextTick()
    expect(w.text()).toContain('Median $80,000–$100,000')
    expect(w.text()).toContain('based on 10 of 42 roles with a listed salary')
  })

  it('renders the "no salary data yet" message when count_with_salary is 0, with no range', async () => {
    vi.mocked(useApiFetch).mockResolvedValueOnce({
      data: { count: 5, count_with_salary: 0, median: null, p25: null, p75: null },
      error: null,
    })
    const w = await mountCard()
    await w.vm.$nextTick()
    await w.vm.$nextTick()
    expect(w.text()).toContain('No salary data in your current search results yet')
    expect(w.text()).not.toContain('Median')
  })

  it('renders a "Full calculator" link pointing to /salary-calculator', async () => {
    vi.mocked(useApiFetch).mockResolvedValueOnce({
      data: { count: 5, count_with_salary: 0, median: null, p25: null, p75: null },
      error: null,
    })
    const w = await mountCard()
    await w.vm.$nextTick()
    const link = w.find('a.market-snapshot__link')
    expect(link.exists()).toBe(true)
    expect(link.text()).toContain('Full calculator')
    expect(link.attributes('href')).toBe('/salary-calculator')
  })

  it('handles a fetch error gracefully without throwing and shows fallback UI', async () => {
    vi.mocked(useApiFetch).mockResolvedValueOnce({
      data: null,
      error: { kind: 'network', message: 'boom' },
    })
    const w = await mountCard()
    await w.vm.$nextTick()
    await w.vm.$nextTick()
    expect(w.text()).not.toContain('undefined')
    expect(w.text()).not.toContain('NaN')
    expect(w.text().length).toBeGreaterThan(0)
  })

  it('never uses market-percentile or peer-comparison language', async () => {
    vi.mocked(useApiFetch).mockResolvedValueOnce({
      data: { count: 42, count_with_salary: 10, median: 90000, p25: 80000, p75: 100000 },
      error: null,
    })
    const w = await mountCard()
    await w.vm.$nextTick()
    await w.vm.$nextTick()
    const text = w.text().toLowerCase()
    for (const forbidden of ['percentile', 'market ceiling', 'peers', 'ranking']) {
      expect(text).not.toContain(forbidden)
    }
  })
})
