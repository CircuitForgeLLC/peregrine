import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { setActivePinia, createPinia } from 'pinia'

vi.mock('../composables/useApi', () => ({
  useApiFetch: vi.fn(),
}))

import { useApiFetch } from '../composables/useApi'
import SalaryCalculatorView from './SalaryCalculatorView.vue'

interface SalaryStats {
  count: number
  count_with_salary: number
  median: number | null
  p25: number | null
  p75: number | null
}

const EMPTY_STATS: SalaryStats = { count: 5, count_with_salary: 0, median: null, p25: null, p75: null }
const FULL_STATS: SalaryStats = { count: 42, count_with_salary: 10, median: 90000, p25: 80000, p75: 100000 }

function mockApi(searchPrefs: Record<string, unknown>, stats: SalaryStats) {
  vi.mocked(useApiFetch).mockImplementation((url: string) => {
    if (url.startsWith('/api/settings/search')) {
      return Promise.resolve({ data: searchPrefs, error: null }) as never
    }
    if (url.startsWith('/api/salary-stats')) {
      return Promise.resolve({ data: stats, error: null }) as never
    }
    return Promise.resolve({ data: null, error: null }) as never
  })
}

async function mountView() {
  const w = mount(SalaryCalculatorView)
  await flushPromises()
  return w
}

describe('SalaryCalculatorView', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  it('auto-fills titles/location from the search store and fires the initial fetch', async () => {
    mockApi({ job_titles: ['Backend Developer', 'SRE'], locations: ['Remote'] }, FULL_STATS)
    const w = await mountView()

    const titlesInput = w.find('#salary-titles').element as HTMLInputElement
    const locationInput = w.find('#salary-location').element as HTMLInputElement
    expect(titlesInput.value).toBe('Backend Developer, SRE')
    expect(locationInput.value).toBe('Remote')

    const calls = vi.mocked(useApiFetch).mock.calls.map(c => c[0])
    expect(calls.some(u => (u as string).startsWith('/api/salary-stats'))).toBe(true)
  })

  it('re-fetches with overridden titles/location when Recalculate is clicked', async () => {
    mockApi({ job_titles: ['Backend Developer'], locations: ['Remote'] }, FULL_STATS)
    const w = await mountView()
    vi.mocked(useApiFetch).mockClear()

    await w.find('#salary-titles').setValue('Data Scientist')
    await w.find('#salary-location').setValue('Boston MA')
    await w.find('form').trigger('submit')
    await flushPromises()

    const call = vi.mocked(useApiFetch).mock.calls.find(c => (c[0] as string).startsWith('/api/salary-stats'))
    expect(call).toBeDefined()
    const url = call![0] as string
    expect(url).toContain('titles=Data+Scientist')
    expect(url).toContain('location=Boston+MA')
  })

  it('renders the p25/median/p75 range bar when data is present', async () => {
    mockApi({ job_titles: [], locations: [] }, FULL_STATS)
    const w = await mountView()

    expect(w.text()).toContain('$80,000')
    expect(w.text()).toContain('$100,000')
    expect(w.text()).toContain('Median $90,000')
    expect(w.text()).toContain('based on 10 of 42 roles with a listed salary')
  })

  it('renders the zero-data empty state when count_with_salary is 0', async () => {
    mockApi({ job_titles: [], locations: [] }, EMPTY_STATS)
    const w = await mountView()

    expect(w.text()).toContain('No salary data in your current search results yet')
    expect(w.text()).not.toContain('Median')
  })

  it('renders the honest framing text near the top', async () => {
    mockApi({ job_titles: [], locations: [] }, FULL_STATS)
    const w = await mountView()

    expect(w.text()).toContain(
      "Based on job postings matching your search — not a broader market benchmark.",
    )
  })

  it('never uses market-percentile or peer-comparison language', async () => {
    mockApi({ job_titles: [], locations: [] }, FULL_STATS)
    const w = await mountView()

    const text = w.text().toLowerCase()
    for (const forbidden of ['percentile', 'market ceiling', 'peers', 'ranking']) {
      expect(text).not.toContain(forbidden)
    }
  })
})
