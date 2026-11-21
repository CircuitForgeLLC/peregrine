import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import MyExperienceView from './MyExperienceView.vue'

vi.mock('../../composables/useApi', () => ({ useApiFetch: vi.fn() }))
import { useApiFetch } from '../../composables/useApi'
const mockFetch = vi.mocked(useApiFetch)

function fact(over: Record<string, unknown> = {}) {
  return {
    id: 1, kind: 'experience', requirement: 'scheduling', text: 'I ran the rota for 12 nurses.',
    visibility: 'document', status: 'active', source: 'gap_card', origin_job_id: null,
    created_at: '2026-11-01T10:00:00', updated_at: '2026-11-01T10:00:00', ...over,
  }
}

const FACTS = [
  fact({ id: 1, requirement: 'scheduling', created_at: '2026-11-01T10:00:00' }),
  fact({ id: 2, kind: 'adjacent', requirement: 'Kubernetes', text: 'Used Docker Swarm.', visibility: 'private', created_at: '2026-11-03T10:00:00' }),
  fact({ id: 3, kind: 'none', requirement: 'Rust', text: '', created_at: '2026-11-02T10:00:00' }),
]

async function mountView(list: unknown = FACTS, attach = false) {
  mockFetch.mockResolvedValueOnce({ data: list, error: null } as never)
  const w = mount(MyExperienceView, attach ? { attachTo: document.body } : undefined)
  await flushPromises()
  return w
}

function lastCall() {
  const c = mockFetch.mock.calls[mockFetch.mock.calls.length - 1]
  const init = c[1] as RequestInit
  return { url: c[0] as string, init, body: init?.body ? JSON.parse(init.body as string) : null }
}

describe('MyExperienceView', () => {
  beforeEach(() => { vi.clearAllMocks() })

  it('lists experience facts newest first and none facts in a separate group', async () => {
    const w = await mountView()
    expect(mockFetch.mock.calls[0][0]).toBe('/api/experience-facts')
    const groups = w.findAll('section')
    expect(groups).toHaveLength(2)
    expect(groups[0].find('h2').text()).toBe('Experience you have shared')
    expect(groups[1].find('h2').text()).toBe('Things you told us you have not done')
    const first = groups[0].findAll('li')
    expect(first[0].text()).toContain('Kubernetes')
    expect(first[1].text()).toContain('scheduling')
    expect(first[1].text()).toContain('I ran the rota for 12 nurses.')
    expect(groups[1].text()).toContain('Rust')
    expect(groups[1].text()).not.toContain('Kubernetes')
  })

  it('shows visibility and kind as words', async () => {
    const w = await mountView()
    const items = w.findAll('li')
    expect(items[0].text()).toContain('Private')
    expect(items[0].text()).toContain('Something similar')
    expect(items[1].text()).toContain('Used in documents')
    expect(items[1].text()).toContain('Done it')
    expect(items[2].text()).toContain('Have not done')
  })

  it('explains the page and shows an empty state', async () => {
    const w = await mountView([])
    expect(w.text()).toContain('Answers you give when the resume optimizer asks about a keyword appear here.')
    expect(w.text()).toContain('Nothing here is used in a document unless it is marked "Used in documents"')
    expect(w.findAll('section')).toHaveLength(0)
  })

  it('shows an error with Retry when loading fails', async () => {
    mockFetch.mockResolvedValueOnce({ data: null, error: { kind: 'network', message: 'x' } } as never)
    const w = mount(MyExperienceView)
    await flushPromises()
    expect(w.find('[role="alert"]').exists()).toBe(true)
    mockFetch.mockResolvedValueOnce({ data: FACTS, error: null } as never)
    await w.find('button.mex__retry').trigger('click')
    await flushPromises()
    expect(w.findAll('li').length).toBe(3)
  })

  it('edits text inline with PATCH, focusing the textarea then the Edit button', async () => {
    const w = await mountView(FACTS, true)
    await w.find('button[aria-label="Edit: scheduling"]').trigger('click')
    await flushPromises()
    const ta = w.find('textarea')
    expect(ta.attributes('maxlength')).toBe('2000')
    expect(document.activeElement).toBe(ta.element)
    await ta.setValue('I built the rota for 30 staff.')
    mockFetch.mockResolvedValueOnce({ data: fact({ text: 'I built the rota for 30 staff.' }), error: null } as never)
    await w.find('button[aria-label="Save: scheduling"]').trigger('click')
    await flushPromises()
    const c = lastCall()
    expect(c.url).toBe('/api/experience-facts/1')
    expect(c.init.method).toBe('PATCH')
    expect(c.body).toEqual({ text: 'I built the rota for 30 staff.' })
    expect(w.text()).toContain('I built the rota for 30 staff.')
    expect(w.find('textarea').exists()).toBe(false)
    expect(document.activeElement).toBe(w.find('button[aria-label="Edit: scheduling"]').element)
    w.unmount()
  })

  it('cancel leaves text unchanged and makes no request', async () => {
    const w = await mountView()
    await w.find('button[aria-label="Edit: scheduling"]').trigger('click')
    await w.find('textarea').setValue('changed')
    await w.find('button[aria-label="Cancel: scheduling"]').trigger('click')
    expect(mockFetch).toHaveBeenCalledTimes(1)
    expect(w.text()).toContain('I ran the rota for 12 nurses.')
  })

  it('keeps the editor open and shows the server detail as plain text when a save fails', async () => {
    const w = await mountView()
    await w.find('button[aria-label="Edit: scheduling"]').trigger('click')
    await w.find('textarea').setValue('   ')
    mockFetch.mockResolvedValueOnce({ data: null, error: { kind: 'http', status: 422, detail: '{"detail":"<b>Answer is empty</b>"}' } } as never)
    await w.find('button[aria-label="Save: scheduling"]').trigger('click')
    await flushPromises()
    expect(w.find('textarea').exists()).toBe(true)
    expect(w.text()).toContain('<b>Answer is empty</b>')
    expect(w.find('b').exists()).toBe(false)
  })

  it('kind none facts have no Edit or Keep private control', async () => {
    const w = await mountView()
    expect(w.find('button[aria-label="Edit: Rust"]').exists()).toBe(false)
    expect(w.find('[aria-label="Keep private: Rust"]').exists()).toBe(false)
    expect(w.find('button[aria-label="Stop using this: Rust"]').exists()).toBe(true)
    expect(w.find('button[aria-label="Delete: Rust"]').exists()).toBe(true)
  })

  it('toggling Keep private sends PATCH with the new visibility', async () => {
    const w = await mountView()
    const box = w.find('input[aria-label="Keep private: scheduling"]')
    expect((box.element as HTMLInputElement).checked).toBe(false)
    mockFetch.mockResolvedValueOnce({ data: fact({ visibility: 'private' }), error: null } as never)
    await box.setValue(true)
    await flushPromises()
    const c = lastCall()
    expect(c.url).toBe('/api/experience-facts/1')
    expect(c.init.method).toBe('PATCH')
    expect(c.body).toEqual({ visibility: 'private' })
    const li = w.findAll('li').find((l) => l.text().includes('scheduling'))!
    expect(li.text()).toContain('Private')
    const other = w.find('input[aria-label="Keep private: Kubernetes"]')
    expect((other.element as HTMLInputElement).checked).toBe(true)
  })

  it('Stop using this sends status retired and removes the fact with a note', async () => {
    const w = await mountView()
    mockFetch.mockResolvedValueOnce({ data: fact({ status: 'retired' }), error: null } as never)
    await w.find('button[aria-label="Stop using this: scheduling"]').trigger('click')
    await flushPromises()
    expect(lastCall().body).toEqual({ status: 'retired' })
    expect(lastCall().init.method).toBe('PATCH')
    expect(w.text()).not.toContain('I ran the rota for 12 nurses.')
    expect(w.text()).toContain('Stopped facts are kept but no longer used.')
    expect(w.find('[aria-live="polite"]').text()).toContain('scheduling')
  })

  it('Delete needs a confirm step, explains it is permanent, then calls DELETE', async () => {
    const w = await mountView(FACTS, true)
    await w.find('button[aria-label="Delete: scheduling"]').trigger('click')
    expect(mockFetch).toHaveBeenCalledTimes(1)
    expect(w.text()).toContain('removes it for good')
    mockFetch.mockResolvedValueOnce({ data: { deleted: true }, error: null } as never)
    await w.find('button[aria-label="Yes, delete it: scheduling"]').trigger('click')
    await flushPromises()
    const c = lastCall()
    expect(c.url).toBe('/api/experience-facts/1')
    expect(c.init.method).toBe('DELETE')
    expect(w.text()).not.toContain('I ran the rota for 12 nurses.')
    expect(document.activeElement?.tagName).toBe('H2')
    w.unmount()
  })

  it('Keep it cancels the delete without a request', async () => {
    const w = await mountView()
    await w.find('button[aria-label="Delete: scheduling"]').trigger('click')
    await w.find('button[aria-label="Keep it: scheduling"]').trigger('click')
    expect(mockFetch).toHaveBeenCalledTimes(1)
    expect(w.text()).toContain('I ran the rota for 12 nurses.')
    expect(w.find('button[aria-label="Delete: scheduling"]').exists()).toBe(true)
  })

  it('shows a calm demo sentence when writes are blocked and keeps the fact', async () => {
    const w = await mountView()
    mockFetch.mockResolvedValueOnce({ data: null, error: { kind: 'demo-blocked' } } as never)
    await w.find('button[aria-label="Stop using this: scheduling"]').trigger('click')
    await flushPromises()
    expect(w.text()).toContain('This is a demo, so changes are not saved.')
    expect(w.text()).toContain('I ran the rota for 12 nurses.')
  })

  it('every button and checkbox has an accessible name', async () => {
    const w = await mountView()
    for (const el of w.findAll('button, input, textarea')) {
      const name = el.attributes('aria-label') ?? el.text()
      expect(name.trim().length).toBeGreaterThan(0)
    }
  })

  it('copy has no em dashes or semicolons', async () => {
    const w = await mountView()
    await w.find('button[aria-label="Delete: scheduling"]').trigger('click')
    expect(w.text()).not.toMatch(/[—;]/)
  })
})
