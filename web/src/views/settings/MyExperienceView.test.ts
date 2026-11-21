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
    expect(w.find('button[aria-label="Delete: Rust"]').exists()).toBe(true)
  })

  it('test_there_is_no_stop_using_this_button', async () => {
    const w = await mountView()
    expect(w.text()).not.toContain('Stop using this')
    expect(w.text()).not.toMatch(/kept but no longer used/i)
    expect(w.find('button[aria-label^="Stop using this"]').exists()).toBe(false)
    await w.find('button[aria-label="Delete: scheduling"]').trigger('click')
    expect(w.text()).toContain('Delete removes it for good')
    expect(w.text()).not.toContain('Stop using this')
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

  it('Delete needs a confirm step, explains it is permanent, then calls DELETE', async () => {
    const w = await mountView(FACTS, true)
    await w.find('button[aria-label="Delete: scheduling"]').trigger('click')
    expect(mockFetch).toHaveBeenCalledTimes(1)
    expect(w.text()).toContain('removes it for good')
    mockFetch.mockResolvedValueOnce({ data: { ok: true }, error: null } as never)
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
    await w.find('button[aria-label="Delete: scheduling"]').trigger('click')
    await w.find('button[aria-label="Yes, delete it: scheduling"]').trigger('click')
    await flushPromises()
    expect(w.text()).toContain('This is a demo, so changes are not saved.')
    expect(w.text()).toContain('I ran the rota for 12 nurses.')
  })

  it('every button and checkbox has an accessible name', async () => {
    const w = await mountView()
    for (const li of w.findAll('li')) {
      const req = li.find('h3').text()
      for (const el of li.findAll('button, input')) {
        const name = el.attributes('aria-label') ?? ''
        expect(name, el.html()).toContain(req)
      }
    }
  })

  const err422 = (m: string) => ({ data: null, error: { kind: 'http', status: 422, detail: JSON.stringify({ detail: m }) } }) as never
  const rowOf = (w: ReturnType<typeof mount>, req: string) => w.findAll('li').find((l) => l.find('h3').text() === req)!

  it('test_a_failed_delete_leaves_the_fact_in_place_and_shows_the_error_in_its_row', async () => {
    const w = await mountView()
    await w.find('button[aria-label="Delete: scheduling"]').trigger('click')
    mockFetch.mockResolvedValueOnce({ data: null, error: { kind: 'http', status: 404, detail: '{"detail":"Not found"}' } } as never)
    await w.find('button[aria-label="Yes, delete it: scheduling"]').trigger('click')
    await flushPromises()
    const row = rowOf(w, 'scheduling')
    expect(row.text()).toContain('Not found')
    expect(row.text()).toContain('I ran the rota for 12 nurses.')
    expect(w.findAll('li')).toHaveLength(3)
  })

  it('test_a_failed_visibility_toggle_reverts_the_checkbox_and_shows_the_error_in_its_row', async () => {
    const w = await mountView()
    const box = w.find('input[aria-label="Keep private: scheduling"]')
    mockFetch.mockResolvedValueOnce(err422('Could not change'))
    await box.setValue(true)
    await flushPromises()
    expect((box.element as HTMLInputElement).checked).toBe(false)
    expect(rowOf(w, 'scheduling').text()).toContain('Could not change')
    expect(rowOf(w, 'scheduling').text()).toContain('Used in documents')
  })

  it('test_a_blank_edit_is_refused_and_the_old_text_stays', async () => {
    const w = await mountView()
    await w.find('button[aria-label="Edit: scheduling"]').trigger('click')
    await w.find('textarea').setValue('   ')
    mockFetch.mockResolvedValueOnce(err422('Please write something'))
    await w.find('button[aria-label="Save: scheduling"]').trigger('click')
    await flushPromises()
    expect(w.find('textarea').exists()).toBe(true)
    expect(rowOf(w, 'scheduling').text()).toContain('Please write something')
    await w.find('button[aria-label="Cancel: scheduling"]').trigger('click')
    expect(rowOf(w, 'scheduling').text()).toContain('I ran the rota for 12 nurses.')
  })

  it('test_a_non_demo_403_takes_the_failed_path_not_the_demo_path', async () => {
    const w = await mountView()
    mockFetch.mockResolvedValueOnce({ data: null, error: { kind: 'http', status: 403, detail: '{"detail":"Forbidden"}' } } as never)
    await w.find('button[aria-label="Delete: scheduling"]').trigger('click')
    await w.find('button[aria-label="Yes, delete it: scheduling"]').trigger('click')
    await flushPromises()
    const t = rowOf(w, 'scheduling').text()
    expect(t).toContain('That did not work')
    expect(t).toContain('Forbidden')
    expect(t).not.toContain('This is a demo')
  })

  it('test_keep_it_focuses_the_delete_button', async () => {
    const w = await mountView(FACTS, true)
    await w.find('button[aria-label="Delete: scheduling"]').trigger('click')
    await w.find('button[aria-label="Keep it: scheduling"]').trigger('click')
    await flushPromises()
    expect(document.activeElement).toBe(w.find('button[aria-label="Delete: scheduling"]').element)
    w.unmount()
  })

  it('test_escape_in_the_delete_confirm_cancels_and_focuses_the_delete_button', async () => {
    const w = await mountView(FACTS, true)
    await w.find('button[aria-label="Delete: scheduling"]').trigger('click')
    await w.find('button[aria-label="Keep it: scheduling"]').trigger('keydown', { key: 'Escape' })
    await flushPromises()
    expect(w.find('button[aria-label="Yes, delete it: scheduling"]').exists()).toBe(false)
    expect(mockFetch).toHaveBeenCalledTimes(1)
    expect(document.activeElement).toBe(w.find('button[aria-label="Delete: scheduling"]').element)
    w.unmount()
  })

  it('test_confirm_state_does_not_leak_between_two_facts', async () => {
    const w = await mountView()
    await w.find('button[aria-label="Delete: scheduling"]').trigger('click')
    expect(w.find('button[aria-label="Yes, delete it: scheduling"]').exists()).toBe(true)
    expect(w.find('button[aria-label="Yes, delete it: Kubernetes"]').exists()).toBe(false)
    expect(w.find('button[aria-label="Delete: Kubernetes"]').exists()).toBe(true)
  })

  it('test_focus_moves_to_the_page_heading_when_the_last_fact_in_a_group_is_removed', async () => {
    const w = await mountView(FACTS, true)
    mockFetch.mockResolvedValueOnce({ data: { ok: true }, error: null } as never)
    await w.find('button[aria-label="Delete: Rust"]').trigger('click')
    await w.find('button[aria-label="Yes, delete it: Rust"]').trigger('click')
    await flushPromises()
    expect(lastCall().url).toBe('/api/experience-facts/3')
    expect(lastCall().init.method).toBe('DELETE')
    expect(w.findAll('li').some((l) => l.text().includes('Rust'))).toBe(false)
    expect(document.activeElement).toBe(w.find('h1').element)
    w.unmount()
  })

  it('test_loading_state_is_shown_before_facts_arrive', async () => {
    let resolve!: (v: never) => void
    mockFetch.mockReturnValueOnce(new Promise((r) => { resolve = r as never }) as never)
    const w = mount(MyExperienceView)
    expect(w.text()).toContain('Loading your experience')
    resolve({ data: FACTS, error: null } as never)
    await flushPromises()
    expect(w.text()).not.toContain('Loading your experience')
  })

  it('copy has no em dashes or semicolons', async () => {
    const w = await mountView()
    await w.find('button[aria-label="Delete: scheduling"]').trigger('click')
    expect(w.text()).not.toMatch(/[—;]/)
  })
})
