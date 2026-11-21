import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

vi.mock('../composables/useApi', () => ({
  useApiFetch: vi.fn(),
}))

import { useApiFetch } from '../composables/useApi'
import GapCards from './GapCards.vue'

const fetchMock = vi.mocked(useApiFetch)

interface Sug { id: number; kind: string; text: string; visibility: string; requirement?: string; exact?: boolean }
// A suggestion is for the card's own term unless a test says otherwise.
function card(term: string, suggestion: Sug | null = null) {
  return { term, snippet: `We need ${term} skills`, suggestion: suggestion && { requirement: term, exact: true, ...suggestion } }
}

async function mountCards(cards: ReturnType<typeof card>[], answersResponse: unknown = { data: { approved_terms: [], saved: 0 }, error: null }) {
  fetchMock.mockImplementation(async (url: string) => {
    if (url.endsWith('/gap_cards')) return { data: { cards }, error: null } as any
    return answersResponse as any
  })
  const wrapper = mount(GapCards, {
    props: { jobId: 7, terms: cards.map((c) => c.term) },
    attachTo: document.body,
  })
  await flushPromises()
  return wrapper
}

function answersCall() {
  const call = fetchMock.mock.calls.find((c) => String(c[0]).endsWith('/gap_cards/answers'))
  return call ? JSON.parse(String(call[1]?.body)).answers : null
}

describe('GapCards', () => {
  beforeEach(() => vi.clearAllMocks())

  it('renders one card per term with the term and snippet', async () => {
    const w = await mountCards([card('Kubernetes'), card('Terraform')])
    const sets = w.findAll('fieldset')
    expect(sets).toHaveLength(2)
    expect(sets[0].find('legend').text()).toBe('Kubernetes')
    expect(sets[0].text()).toContain('We need Kubernetes skills')
    expect(fetchMock.mock.calls[0][0]).toBe('/api/jobs/7/gap_cards')
  })

  it('yes and similar reveal a labelled textarea, no does not', async () => {
    const w = await mountCards([card('Kubernetes')])
    expect(w.find('textarea').exists()).toBe(false)
    await w.find('input[value="yes"]').setValue(true)
    const ta = w.find('textarea')
    expect(ta.exists()).toBe(true)
    expect(w.find(`label[for="${ta.attributes('id')}"]`).text()).toBe('What did you do? Your own words are best.')
    expect(ta.attributes('maxlength')).toBe('2000')
    await w.find('input[value="similar"]').setValue(true)
    expect(w.find(`label[for="${w.find('textarea').attributes('id')}"]`).text()).toBe('What is the similar experience?')
    await w.find('input[value="no"]').setValue(true)
    expect(w.find('textarea').exists()).toBe(false)
  })

  it('keeps save disabled while a yes or similar card has blank text', async () => {
    const w = await mountCards([card('Kubernetes')])
    const save = () => w.find('button.gcs__btn--primary')
    expect(save().attributes('disabled')).toBeUndefined()
    await w.find('input[value="yes"]').setValue(true)
    expect(save().attributes('disabled')).toBeDefined()
    await w.find('textarea').setValue('   ')
    expect(save().attributes('disabled')).toBeDefined()
    await w.find('textarea').setValue('Ran clusters')
    expect(save().attributes('disabled')).toBeUndefined()
  })

  it('offers Use this again on a related answer and fills the saved text for editing', async () => {
    const w = await mountCards([card('Kubernetes', { id: 4, kind: 'experience', text: 'Ran clusters', visibility: 'document', exact: false })])
    expect((w.find('input[value="skip"]').element as HTMLInputElement).checked).toBe(true)
    expect(w.text()).toContain('Use this again')
    await w.find('input[value="reuse"]').setValue(true)
    const ta = w.find('textarea')
    expect((ta.element as HTMLTextAreaElement).value).toBe('Ran clusters')
    await ta.setValue('Ran clusters at scale')
    expect((w.find('textarea').element as HTMLTextAreaElement).value).toBe('Ran clusters at scale')
  })

  it('sends use_saved_fact_id when the saved text is untouched, a new answer when edited', async () => {
    const sug = { id: 4, kind: 'adjacent', text: 'Used Nomad', visibility: 'document', exact: false }
    const w = await mountCards([card('Kubernetes', sug)])
    await w.find('input[value="reuse"]').setValue(true)
    await w.find('button.gcs__btn--primary').trigger('click')
    await flushPromises()
    expect(answersCall()[0]).toMatchObject({ term: 'Kubernetes', choice: 'similar', use_saved_fact_id: 4 })

    fetchMock.mockClear()
    const w2 = await mountCards([card('Kubernetes', sug)])
    await w2.find('input[value="reuse"]').setValue(true)
    await w2.find('textarea').setValue('Used Nomad daily')
    await w2.find('button.gcs__btn--primary').trigger('click')
    await flushPromises()
    const a = answersCall()[0]
    expect(a).toMatchObject({ choice: 'similar', text: 'Used Nomad daily' })
    expect(a.use_saved_fact_id).toBeNull()
  })

  it('preselects No with a calm note for an earlier no, and flags private suggestions', async () => {
    const w = await mountCards([
      card('Rust', { id: 1, kind: 'none', text: '', visibility: 'document' }),
      card('Go', { id: 2, kind: 'experience', text: 'Wrote services', visibility: 'private' }),
    ])
    // Answered keywords are listed, not carded, until the person chooses Change.
    const change = (term: string) => w.findAll('button').find((b) => b.text().startsWith('Change') && b.text().includes(term))!
    await change('Rust').trigger('click')
    await change('Go').trigger('click')
    expect((w.findAll('input[value="no"]')[0].element as HTMLInputElement).checked).toBe(true)
    expect(w.text()).toContain('You told us before that you have not done this. Change it if that is no longer true.')
    expect(w.text()).toContain('Saved as private')
    const box = w.findAll('input[type="checkbox"]')[0]
    expect((box.element as HTMLInputElement).checked).toBe(true)
  })

  it('sends the private flag from the Keep this private checkbox', async () => {
    const w = await mountCards([card('Kubernetes')])
    await w.find('input[value="yes"]').setValue(true)
    await w.find('textarea').setValue('Ran clusters')
    expect(w.text()).toContain('Keep this private')
    expect(w.text()).toContain('Private means this is saved for you but never used in your documents.')
    await w.find('input[type="checkbox"]').setValue(true)
    await w.find('button.gcs__btn--primary').trigger('click')
    await flushPromises()
    expect(answersCall()[0]).toMatchObject({ choice: 'yes', text: 'Ran clusters', private: true })
  })

  it('Skip for now sends choice skip', async () => {
    const w = await mountCards([card('Kubernetes')])
    await w.find('input[value="yes"]').setValue(true)
    await w.find('input[value="skip"]').setValue(true)
    await w.find('button.gcs__btn--primary').trigger('click')
    await flushPromises()
    expect(answersCall()[0]).toMatchObject({ term: 'Kubernetes', choice: 'skip' })
  })

  it('posts all answers once and emits done with the approved terms', async () => {
    const w = await mountCards(
      [card('Kubernetes'), card('Terraform')],
      { data: { approved_terms: ['Kubernetes'], saved: 1 }, error: null },
    )
    await w.findAll('input[value="yes"]')[0].setValue(true)
    await w.find('textarea').setValue('Ran clusters')
    await w.find('button.gcs__btn--primary').trigger('click')
    await flushPromises()
    const calls = fetchMock.mock.calls.filter((c) => String(c[0]).endsWith('/gap_cards/answers'))
    expect(calls).toHaveLength(1)
    expect(String(calls[0][0])).toBe('/api/jobs/7/gap_cards/answers')
    expect(answersCall()).toHaveLength(2)
    expect(w.emitted('done')![0]).toEqual([['Kubernetes']])
  })

  it('shows progress as plain text and moves focus to the first card heading', async () => {
    const w = await mountCards([card('Kubernetes'), card('Terraform')])
    const progress = w.find('.gcs__progress')
    expect(progress.text()).toBe('0 of 2 answered')
    expect(progress.attributes('aria-live')).toBe('polite')
    expect(document.activeElement).toBe(w.find('legend').element)
    await w.findAll('input[value="no"]')[1].setValue(true)
    expect(w.find('.gcs__progress').text()).toBe('1 of 2 answered')
  })

  it('keeps typed text and offers a retry when saving fails', async () => {
    const w = await mountCards([card('Kubernetes')], { data: null, error: { kind: 'http', status: 422, detail: 'bad' } })
    await w.find('input[value="yes"]').setValue(true)
    await w.find('textarea').setValue('Ran clusters')
    await w.find('button.gcs__btn--primary').trigger('click')
    await flushPromises()
    expect(w.find('[role="alert"]').exists()).toBe(true)
    expect(w.emitted('done')).toBeUndefined()
    expect((w.find('textarea').element as HTMLTextAreaElement).value).toBe('Ran clusters')
    expect(w.find('button.gcs__btn--primary').text()).toContain('Retry')
  })

  it('shows an error with Retry when the cards fail to load', async () => {
    fetchMock.mockResolvedValueOnce({ data: null, error: { kind: 'network', message: 'x' } } as any)
    const w = mount(GapCards, { props: { jobId: 7, terms: ['Kubernetes'] } })
    await flushPromises()
    expect(w.find('[role="alert"]').text()).toContain('Retry')
    fetchMock.mockResolvedValueOnce({ data: { cards: [card('Kubernetes')] }, error: null } as any)
    await w.findAll('button').find((b) => b.text() === 'Retry')!.trigger('click')
    await flushPromises()
    expect(w.findAll('fieldset')).toHaveLength(1)
  })

  it('uses real labels on native radios and never leans on colour alone', async () => {
    const w = await mountCards([card('Kubernetes')])
    const radios = w.findAll('input[type="radio"]')
    expect(radios.length).toBeGreaterThanOrEqual(4)
    for (const r of radios) {
      expect(r.element.closest('label')?.textContent?.trim().length).toBeGreaterThan(0)
    }
    expect(new Set(radios.map((r) => r.attributes('name'))).size).toBe(1)
    expect(w.find('fieldset legend').text()).toBe('Kubernetes')
    expect(w.text()).toMatch(/\d+ of \d+ answered/)
  })

  it('has no em dashes or semicolons and words No neutrally', async () => {
    const w = await mountCards([
      card('Kubernetes'),
      card('Rust', { id: 1, kind: 'none', text: '', visibility: 'document' }),
      card('Go', { id: 2, kind: 'experience', text: 'Wrote services', visibility: 'private' }),
    ])
    const text = w.text()
    expect(text).not.toContain('—')
    expect(text).not.toContain(';')
    expect(text).toContain('No, not something I have done')
    expect(text.toLowerCase()).not.toMatch(/urgent|hurry|deadline|expires|only \d+ left/)
  })

  it('test_a_failed_save_shows_the_servers_detail_message_as_plain_text', async () => {
    const w = await mountCards([card('Kubernetes')], { data: null, error: { kind: 'http', status: 422, detail: '<b>too long</b>' } })
    await w.find('button.gcs__btn--primary').trigger('click')
    await flushPromises()
    const alert = w.find('[role="alert"]')
    expect(alert.text()).toContain('<b>too long</b>')
    expect(alert.find('b').exists()).toBe(false)
  })

  it('shows a JSON detail string from the server', async () => {
    const w = await mountCards([card('Kubernetes')], { data: null, error: { kind: 'http', status: 422, detail: '{"detail":"Text is too long"}' } })
    await w.find('button.gcs__btn--primary').trigger('click')
    await flushPromises()
    expect(w.find('[role="alert"]').text()).toContain('Text is too long')
  })

  it('test_a_restored_draft_on_a_card_with_a_saved_suggestion_sends_the_right_request_body', async () => {
    const sug = { id: 4, kind: 'experience', text: 'Saved', visibility: 'document', exact: false }
    fetchMock.mockImplementation(async (url: string) => {
      if (url.endsWith('/gap_cards')) return { data: { cards: [card('Kubernetes', sug)] }, error: null } as any
      return { data: { approved_terms: [], saved: 0 }, error: null } as any
    })
    const send = async (draft: { choice: string; text: string; private: boolean }) => {
      fetchMock.mockClear()
      const w = mount(GapCards, { props: { jobId: 7, terms: ['Kubernetes'], drafts: { Kubernetes: draft as any } } })
      await flushPromises()
      await w.find('button.gcs__btn--primary').trigger('click')
      await flushPromises()
      return answersCall()[0]
    }
    const edited = await send({ choice: 'reuse', text: 'Saved plus more', private: false })
    expect(edited).toMatchObject({ choice: 'yes', text: 'Saved plus more' })
    expect(edited.use_saved_fact_id).toBeNull()
    const same = await send({ choice: 'reuse', text: 'Saved', private: false })
    expect(same.use_saved_fact_id).toBe(4)
  })

  it('does not show a stale server detail after a later failure or a retry', async () => {
    let calls = 0
    fetchMock.mockImplementation(async (url: string) => {
      if (url.endsWith('/gap_cards')) return { data: { cards: [card('Kubernetes')] }, error: null } as any
      calls += 1
      return { data: null, error: calls === 1 ? { kind: 'http', status: 422, detail: 'Old problem' } : { kind: 'network', message: 'x' } } as any
    })
    const w = mount(GapCards, { props: { jobId: 7, terms: ['Kubernetes'] } })
    await flushPromises()
    await w.find('button.gcs__btn--primary').trigger('click')
    await flushPromises()
    expect(w.find('[role="alert"]').text()).toContain('Old problem')
    await w.find('button.gcs__btn--primary').trigger('click')
    await flushPromises()
    expect(w.find('[role="alert"]').text()).not.toContain('Old problem')
  })

  it('starts from supplied drafts, and a draft wins over a saved suggestion', async () => {
    fetchMock.mockImplementation(async () => ({
      data: { cards: [card('Kubernetes', { id: 4, kind: 'experience', text: 'Saved', visibility: 'document', exact: false })] }, error: null,
    }) as any)
    const w = mount(GapCards, {
      props: { jobId: 7, terms: ['Kubernetes'], drafts: { Kubernetes: { choice: 'similar', text: 'Typed', private: true } } },
    })
    await flushPromises()
    expect((w.find('input[value="similar"]').element as HTMLInputElement).checked).toBe(true)
    expect((w.find('textarea').element as HTMLTextAreaElement).value).toBe('Typed')
  })

  it('test_an_overlap_only_suggestion_is_a_hint_and_defaults_to_skip', async () => {
    const sug = { id: 9, kind: 'adjacent', text: 'Built two mobile apps', visibility: 'document', requirement: 'React Native', exact: false }
    const w = await mountCards([card('React', sug)])
    expect((w.find('input[value="skip"]').element as HTMLInputElement).checked).toBe(true)
    expect((w.find('input[value="reuse"]').element as HTMLInputElement).checked).toBe(false)
    expect(w.text()).toContain('Built two mobile apps')
    await w.find('input[value="yes"]').setValue(true)
    expect((w.find('textarea').element as HTMLTextAreaElement).value).toBe('')
    await w.find('input[value="similar"]').setValue(true)
    expect((w.find('textarea').element as HTMLTextAreaElement).value).toBe('')

    fetchMock.mockClear()
    const w2 = await mountCards([card('React', sug)])
    await w2.find('button.gcs__btn--primary').trigger('click')
    await flushPromises()
    expect(answersCall()[0]).toMatchObject({ term: 'React', choice: 'skip', use_saved_fact_id: null })
  })

  it('test_an_exact_suggestion_is_reused_without_a_card', async () => {
    const sug = { id: 4, kind: 'experience', text: 'Ran clusters', visibility: 'document', requirement: 'kubernetes', exact: true }
    const w = await mountCards([card('Kubernetes', sug)])
    expect(w.find('fieldset').exists()).toBe(false)
    expect(w.text()).toContain('Ran clusters')
    expect(w.text()).not.toContain('You saved this for')
    await w.find('button.gcs__btn--primary').trigger('click')
    await flushPromises()
    expect(answersCall()[0]).toMatchObject({ term: 'Kubernetes', choice: 'yes', use_saved_fact_id: 4 })
  })

  it('test_a_non_exact_suggestion_shows_which_keyword_it_was_saved_for', async () => {
    const w = await mountCards([
      card('React', { id: 9, kind: 'adjacent', text: 'Built two mobile apps', visibility: 'document', requirement: 'React Native', exact: false }),
      card('Kubernetes'),
    ])
    const sets = w.findAll('fieldset')
    expect(sets[0].text()).toContain('You saved this for React Native')
    expect(sets[1].text()).not.toContain('You saved this for')
    await sets[0].find('input[value="reuse"]').setValue(true)
    expect((sets[0].find('textarea').element as HTMLTextAreaElement).value).toBe('Built two mobile apps')
  })

  it('emits the whole drafts object on every change', async () => {
    const w = await mountCards([card('Kubernetes'), card('Terraform')])
    await w.findAll('input[value="yes"]')[1].setValue(true)
    await w.find('textarea').setValue('Wrote modules')
    const last = w.emitted('drafts-change')!.at(-1)![0]
    expect(last).toEqual({
      Kubernetes: { choice: 'skip', text: '', private: false },
      Terraform: { choice: 'yes', text: 'Wrote modules', private: false },
    })
  })
})
