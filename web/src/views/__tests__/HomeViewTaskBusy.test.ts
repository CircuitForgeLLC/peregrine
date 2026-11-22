import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { setActivePinia, createPinia } from 'pinia'

vi.mock('../../composables/useApi', () => ({
  useApiFetch: vi.fn(),
}))

import { useApiFetch } from '../../composables/useApi'
import HomeView from '../HomeView.vue'

type Row = { id: number; task_type: string; status: string; job_id: number }

// Server state the mocked API reads from, changed by each test.
let active: Row[] = []
let detail: Record<number, { id: number; status: string; error: string | null }> = {}
let posts: string[] = []

function installApi() {
  vi.mocked(useApiFetch).mockImplementation((async (url: string, opts?: RequestInit) => {
    const method = opts?.method ?? 'GET'
    if (method === 'POST' && url.startsWith('/api/tasks/')) {
      posts.push(url)
      return { data: { task_id: 7, is_new: true }, error: null }
    }
    if (url === '/api/tasks') return { data: active, error: null }
    const m = url.match(/^\/api\/tasks\/(\d+)$/)
    if (m) return { data: detail[Number(m[1])] ?? null, error: null }
    return { data: null, error: null }
  }) as any)
}

function btn(wrapper: ReturnType<typeof mount>, label: string) {
  return wrapper.findAll('button').find(b => b.text().includes(label))!
}

async function mountHome() {
  setActivePinia(createPinia())
  const wrapper = mount(HomeView, {
    global: { stubs: { RouterLink: true, PipelineStepper: true, ProfileSummaryCard: true, MarketSnapshotCard: true } },
  })
  await flushPromises()
  return wrapper
}

async function tick() {
  await vi.advanceTimersByTimeAsync(5000)
  await flushPromises()
}

async function startDiscovery(wrapper: ReturnType<typeof mount>) {
  active = [{ id: 7, task_type: 'discovery', status: 'running', job_id: 0 }]
  await btn(wrapper, 'Run Discovery').trigger('click')
  await flushPromises()
}

describe('HomeView Run Discovery busy state (#264)', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.clearAllMocks()
    active = []
    detail = {}
    posts = []
    installApi()
  })
  afterEach(() => vi.useRealTimers())

  it('stays busy after the POST returns while the task is still running', async () => {
    const wrapper = await mountHome()
    await startDiscovery(wrapper)
    expect(btn(wrapper, 'Run Discovery').attributes('aria-busy')).toBe('true')
    expect(btn(wrapper, 'Run Discovery').attributes('disabled')).toBeDefined()
    await tick()
    expect(btn(wrapper, 'Run Discovery').attributes('aria-busy')).toBe('true')
  })

  it('returns to idle and shows the result when the task completes', async () => {
    const wrapper = await mountHome()
    await startDiscovery(wrapper)
    active = []
    detail[7] = { id: 7, status: 'completed', error: null }
    await tick()
    expect(btn(wrapper, 'Run Discovery').attributes('aria-busy')).toBe('false')
    expect(wrapper.find('[data-testid="task-status"]').text()).toContain('Discovery finished')
  })

  it('returns to idle and shows a calm message when the task fails', async () => {
    const wrapper = await mountHome()
    await startDiscovery(wrapper)
    active = []
    detail[7] = { id: 7, status: 'failed', error: 'boom' }
    await tick()
    expect(btn(wrapper, 'Run Discovery').attributes('aria-busy')).toBe('false')
    const text = wrapper.find('[data-testid="task-status"]').text()
    expect(text).toContain('Discovery did not finish')
    expect(text).toContain('boom')
  })

  it('resumes busy on mount when a discovery task is already running', async () => {
    active = [{ id: 7, task_type: 'discovery', status: 'running', job_id: 0 }]
    const wrapper = await mountHome()
    expect(btn(wrapper, 'Run Discovery').attributes('aria-busy')).toBe('true')
    active = []
    detail[7] = { id: 7, status: 'completed', error: null }
    await tick()
    expect(btn(wrapper, 'Run Discovery').attributes('aria-busy')).toBe('false')
    expect(wrapper.find('[data-testid="task-status"]').text()).toContain('Discovery finished')
  })

  it('ignores a second click while busy', async () => {
    const wrapper = await mountHome()
    await startDiscovery(wrapper)
    await btn(wrapper, 'Run Discovery').trigger('click')
    await flushPromises()
    expect(posts.filter(p => p === '/api/tasks/discovery')).toHaveLength(1)
  })

  it('announces the busy state in a polite status region', async () => {
    const wrapper = await mountHome()
    await startDiscovery(wrapper)
    const region = wrapper.find('[data-testid="task-status"]')
    expect(region.attributes('role')).toBe('status')
    expect(region.attributes('aria-live')).toBe('polite')
    expect(region.text()).toContain('Discovery is running')
  })

  it('follows the email and enrich tasks the same way', async () => {
    active = [
      { id: 8, task_type: 'email_sync', status: 'running', job_id: 0 },
      { id: 9, task_type: 'enrich_descriptions', status: 'queued', job_id: 0 },
    ]
    const wrapper = await mountHome()
    expect(btn(wrapper, 'Sync Emails').attributes('aria-busy')).toBe('true')
    expect(btn(wrapper, 'Fill Missing Descriptions').attributes('aria-busy')).toBe('true')
    expect(btn(wrapper, 'Run Discovery').attributes('aria-busy')).toBe('false')
  })
})
