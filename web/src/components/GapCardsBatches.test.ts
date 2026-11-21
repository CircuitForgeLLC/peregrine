import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

vi.mock('../composables/useApi', () => ({
  useApiFetch: vi.fn(),
}))

import { useApiFetch } from '../composables/useApi'
import GapCards from './GapCards.vue'
import { CARD_BATCH_SIZE } from './gapCardsConfig'

const fetchMock = vi.mocked(useApiFetch)

interface Sug { id: number; kind: string; text: string; visibility: string; requirement?: string; exact?: boolean }
function card(term: string, suggestion: Sug | null = null) {
  return { term, snippet: `We need ${term} skills`, suggestion: suggestion && { requirement: term, exact: true, ...suggestion } }
}
const saved = (term: string, id: number, kind = 'experience', text = `Did ${term}`) =>
  card(term, { id, kind, text, visibility: 'document' })
const noAnswer = (term: string, id = 1) => card(term, { id, kind: 'none', text: '', visibility: 'document' })
const unanswered = (n: number, from = 1) => Array.from({ length: n }, (_, i) => card(`T${from + i}`))

type W = Awaited<ReturnType<typeof mountCards>>
const emptyOk = { data: { approved_terms: [], saved: 0 }, error: null }

async function mountCards(cards: ReturnType<typeof card>[], answersResponse: unknown = emptyOk, drafts?: Record<string, any>) {
  fetchMock.mockImplementation(async (url: string) => {
    if (url.endsWith('/gap_cards')) return { data: { cards }, error: null } as any
    return answersResponse as any
  })
  const wrapper = mount(GapCards, {
    props: { jobId: 7, terms: cards.map((c) => c.term), drafts },
    attachTo: document.body,
  })
  await flushPromises()
  return wrapper
}

const changeButton = (w: W, term: string) =>
  w.findAll('button').find((b) => b.text().startsWith('Change') && b.text().includes(term))!
const moreButton = (w: W) => w.findAll('button').find((b) => b.text().startsWith('Save and ask about'))
const legends = (w: W) => w.findAll('fieldset legend').map((l) => l.text())
const mainButton = (w: W) => w.find('button.gcs__btn--primary')
function answersCalls() {
  return fetchMock.mock.calls
    .filter((c) => String(c[0]).endsWith('/gap_cards/answers'))
    .map((c) => JSON.parse(String(c[1]?.body)).answers as Array<Record<string, any>>)
}

describe('GapCards batches and saved answers', () => {
  beforeEach(() => vi.clearAllMocks())

  it('partitions cards into saved usable, answered not usable and unanswered', async () => {
    const w = await mountCards([
      saved('Alpha', 1),
      noAnswer('Bravo', 2),
      card('Charlie', { id: 3, kind: 'experience', text: 'Private words', visibility: 'private' }),
      card('Delta'),
      card('Echo', { id: 5, kind: 'adjacent', text: 'Related', visibility: 'document', requirement: 'Other', exact: false }),
    ])
    expect(legends(w)).toEqual(['Delta', 'Echo'])
    expect(w.find('.gcs__saved').text()).toContain('Use my 1 saved answer')
    expect(w.find('.gcs__saved').text()).toContain('Alpha')
    expect(w.find('.gcs__skipped summary').text()).toBe('Answered, not used (2)')
    expect(w.find('.gcs__skipped').text()).toContain('You said you have not done this')
    expect(w.find('.gcs__skipped').text()).toContain('Saved as private')
    // The overlap-only card keeps today's behaviour.
    expect((w.findAll('fieldset')[1].find('input[value="skip"]').element as HTMLInputElement).checked).toBe(true)
  })

  it('shows at most the batch size of cards and builds the number from the constant', async () => {
    const extra = CARD_BATCH_SIZE + 3
    const w = await mountCards(unanswered(CARD_BATCH_SIZE + extra))
    expect(w.findAll('fieldset')).toHaveLength(CARD_BATCH_SIZE)
    expect(legends(w)[0]).toBe('T1')
    expect(moreButton(w)!.text()).toBe(`Save and ask about the next ${CARD_BATCH_SIZE} (${extra} more)`)
    expect(w.find('.gcs__progress').text()).toBe(`0 of ${CARD_BATCH_SIZE} answered There are ${extra} more keywords you can answer after this.`)
  })

  it('no more button when the unanswered fit in one batch', async () => {
    const w = await mountCards(unanswered(CARD_BATCH_SIZE))
    expect(w.findAll('fieldset')).toHaveLength(CARD_BATCH_SIZE)
    expect(moreButton(w)).toBeUndefined()
    expect(w.find('.gcs__progress').text()).not.toContain('more keyword')
  })

  it('the more button label shows the remaining count and the last batch wording', async () => {
    const w = await mountCards(unanswered(CARD_BATCH_SIZE + 2))
    expect(moreButton(w)!.text()).toBe('Save and ask about the last 2')
    const w2 = await mountCards(unanswered(CARD_BATCH_SIZE * 2 + 2))
    expect(moreButton(w2)!.text()).toBe(`Save and ask about the next ${CARD_BATCH_SIZE} (${CARD_BATCH_SIZE + 2} more)`)
    const w3 = await mountCards(unanswered(CARD_BATCH_SIZE + 1))
    expect(w3.find('.gcs__progress').text()).toContain('There is 1 more keyword you can answer after this.')
  })

  it('the more button saves the current batch keeps the cards open and shows the next batch without emitting done', async () => {
    const w = await mountCards(unanswered(CARD_BATCH_SIZE + 2), { data: { approved_terms: ['T1'], saved: 1 }, error: null })
    await w.find('input[value="yes"]').setValue(true)
    await w.find('textarea').setValue('Ran clusters')
    await moreButton(w)!.trigger('click')
    await flushPromises()
    const calls = answersCalls()
    expect(calls).toHaveLength(1)
    expect(calls[0].map((a) => a.term)).toEqual(Array.from({ length: CARD_BATCH_SIZE }, (_, i) => `T${i + 1}`))
    expect(calls[0][0]).toMatchObject({ term: 'T1', choice: 'yes', text: 'Ran clusters' })
    expect(w.emitted('done')).toBeUndefined()
    expect(legends(w)).toEqual([`T${CARD_BATCH_SIZE + 1}`, `T${CARD_BATCH_SIZE + 2}`])
    expect(moreButton(w)).toBeUndefined()
    expect(fetchMock.mock.calls.filter((c) => String(c[0]).endsWith('/gap_cards'))).toHaveLength(1)
  })

  it('approved terms accumulate across batches and done emits the union', async () => {
    const all = unanswered(CARD_BATCH_SIZE + 1)
    let n = 0
    fetchMock.mockImplementation(async (url: string) => {
      if (url.endsWith('/gap_cards')) return { data: { cards: all }, error: null } as any
      n += 1
      return { data: { approved_terms: n === 1 ? ['T1'] : [`T${CARD_BATCH_SIZE + 1}`], saved: 1 }, error: null } as any
    })
    const w = mount(GapCards, { props: { jobId: 7, terms: all.map((c) => c.term) }, attachTo: document.body })
    await flushPromises()
    await moreButton(w)!.trigger('click')
    await flushPromises()
    await mainButton(w).trigger('click')
    await flushPromises()
    expect(answersCalls()).toHaveLength(2)
    expect(answersCalls()[1].map((a) => a.term)).toEqual([`T${CARD_BATCH_SIZE + 1}`])
    expect(w.emitted('done')).toHaveLength(1)
    expect(w.emitted('done')![0]).toEqual([['T1', `T${CARD_BATCH_SIZE + 1}`]])
  })

  it('the saved answers toggle is on by default and sends use_saved_fact_id for exactly those keywords', async () => {
    const w = await mountCards(
      [saved('Alpha', 4), saved('Bravo', 5, 'adjacent'), card('Charlie')],
      { data: { approved_terms: ['Alpha', 'Bravo'], saved: 2 }, error: null },
    )
    const toggle = w.find('.gcs__saved input[type="checkbox"]')
    expect((toggle.element as HTMLInputElement).checked).toBe(true)
    expect(w.find(`label[for="${toggle.attributes('id')}"]`).text()).toBe('Use my 2 saved answers')
    await mainButton(w).trigger('click')
    await flushPromises()
    const body = answersCalls()[0]
    expect(body.find((a) => a.term === 'Alpha')).toEqual({ term: 'Alpha', choice: 'yes', text: '', private: false, use_saved_fact_id: 4 })
    expect(body.find((a) => a.term === 'Bravo')).toEqual({ term: 'Bravo', choice: 'similar', text: '', private: false, use_saved_fact_id: 5 })
    expect(body.filter((a) => a.use_saved_fact_id !== null).map((a) => a.term)).toEqual(['Alpha', 'Bravo'])
    expect(body.find((a) => a.term === 'Charlie')).toMatchObject({ choice: 'skip' })
    expect(w.emitted('done')![0]).toEqual([['Alpha', 'Bravo']])
  })

  it('the saved answers list is a disclosure with each keyword and its wording as plain text', async () => {
    const w = await mountCards([card('Alpha', { id: 4, kind: 'experience', text: '<b>Ran</b> clusters', visibility: 'document' })])
    const details = w.find('.gcs__saved details')
    expect(details.exists()).toBe(true)
    expect(details.find('summary').exists()).toBe(true)
    expect(details.text()).toContain('Alpha')
    expect(details.text()).toContain('<b>Ran</b> clusters')
    expect(details.find('b').exists()).toBe(false)
  })

  it('unchecking the saved answers toggle treats them as skip', async () => {
    const w = await mountCards([saved('Alpha', 4), saved('Bravo', 5, 'adjacent')])
    await w.find('.gcs__saved input[type="checkbox"]').setValue(false)
    await mainButton(w).trigger('click')
    await flushPromises()
    const body = answersCalls()[0]
    expect(body).toHaveLength(2)
    for (const a of body) expect(a).toMatchObject({ choice: 'skip', text: '', use_saved_fact_id: null })
    expect(w.emitted('done')![0]).toEqual([[]])
  })

  it('the saved group is sent once per session', async () => {
    const all = [saved('Alpha', 4), ...unanswered(CARD_BATCH_SIZE + 1)]
    let n = 0
    fetchMock.mockImplementation(async (url: string) => {
      if (url.endsWith('/gap_cards')) return { data: { cards: all }, error: null } as any
      n += 1
      return { data: { approved_terms: n === 1 ? ['Alpha'] : [], saved: 1 }, error: null } as any
    })
    const w = mount(GapCards, { props: { jobId: 7, terms: all.map((c) => c.term) }, attachTo: document.body })
    await flushPromises()
    await moreButton(w)!.trigger('click')
    await flushPromises()
    await mainButton(w).trigger('click')
    await flushPromises()
    const calls = answersCalls()
    expect(calls[0].map((a) => a.term)).toContain('Alpha')
    expect(calls[1].map((a) => a.term)).not.toContain('Alpha')
    expect(w.emitted('done')![0]).toEqual([['Alpha']])
  })

  it('an answered not usable keyword can be changed into a card and is never sent unless changed', async () => {
    const w = await mountCards([card('Go'), noAnswer('Rust')])
    expect(changeButton(w, 'Rust').attributes('type')).toBe('button')
    await mainButton(w).trigger('click')
    await flushPromises()
    expect(answersCalls()[0].map((a) => a.term)).toEqual(['Go'])

    fetchMock.mockClear()
    const w2 = await mountCards([card('Go'), noAnswer('Rust')])
    await changeButton(w2, 'Rust').trigger('click')
    await flushPromises()
    expect(legends(w2)).toEqual(['Go', 'Rust'])
    expect(document.activeElement).toBe(w2.findAll('fieldset legend')[1].element)
    expect(w2.find('.gcs__skipped').exists()).toBe(false)
    await w2.findAll('fieldset')[1].find('input[value="yes"]').setValue(true)
    await w2.findAll('fieldset')[1].find('textarea').setValue('Wrote services')
    await mainButton(w2).trigger('click')
    await flushPromises()
    expect(answersCalls()[0].find((a) => a.term === 'Rust')).toMatchObject({ choice: 'yes', text: 'Wrote services' })
  })

  it('a changed keyword can go past the batch size', async () => {
    const w = await mountCards([...unanswered(CARD_BATCH_SIZE), noAnswer('Rust')])
    await changeButton(w, 'Rust').trigger('click')
    expect(w.findAll('fieldset')).toHaveLength(CARD_BATCH_SIZE + 1)
  })

  it('everything already answered shows no cards and still saves', async () => {
    const w = await mountCards([saved('Alpha', 4), noAnswer('Rust')], { data: { approved_terms: ['Alpha'], saved: 1 }, error: null })
    expect(w.find('fieldset').exists()).toBe(false)
    expect(moreButton(w)).toBeUndefined()
    await mainButton(w).trigger('click')
    await flushPromises()
    expect(answersCalls()[0]).toEqual([{ term: 'Alpha', choice: 'yes', text: '', private: false, use_saved_fact_id: 4 }])
    expect(w.emitted('done')![0]).toEqual([['Alpha']])
  })

  it('with nothing unanswered and nothing saved the main button emits an empty approved list', async () => {
    const w = await mountCards([noAnswer('Rust')])
    expect(w.find('.gcs__saved').exists()).toBe(false)
    await mainButton(w).trigger('click')
    await flushPromises()
    expect(answersCalls()).toHaveLength(0)
    expect(w.emitted('done')![0]).toEqual([[]])
  })

  it('focus moves to the first new card after the more button', async () => {
    const w = await mountCards(unanswered(CARD_BATCH_SIZE + 2))
    await moreButton(w)!.trigger('click')
    await flushPromises()
    expect(document.activeElement).toBe(w.find('fieldset legend').element)
    expect(document.activeElement?.textContent).toBe(`T${CARD_BATCH_SIZE + 1}`)
  })

  it('drafts survive across batches', async () => {
    const last = `T${CARD_BATCH_SIZE + 1}`
    const w = await mountCards(unanswered(CARD_BATCH_SIZE + 1), emptyOk, { [last]: { choice: 'yes', text: 'Later draft', private: false } })
    await w.find('input[value="yes"]').setValue(true)
    await w.find('textarea').setValue('First draft')
    const emitted = w.emitted('drafts-change')!.at(-1)![0] as Record<string, any>
    expect(emitted.T1).toEqual({ choice: 'yes', text: 'First draft', private: false })
    expect(emitted[last]).toEqual({ choice: 'yes', text: 'Later draft', private: false })
    await moreButton(w)!.trigger('click')
    await flushPromises()
    expect((w.find('textarea').element as HTMLTextAreaElement).value).toBe('Later draft')
  })

  it('a save failure on the more button keeps the cards and shows the server detail', async () => {
    const w = await mountCards(unanswered(CARD_BATCH_SIZE + 1), { data: null, error: { kind: 'http', status: 422, detail: '{"detail":"Too long"}' } })
    await moreButton(w)!.trigger('click')
    await flushPromises()
    expect(w.find('[role="alert"]').text()).toContain('Too long')
    expect(w.findAll('fieldset')).toHaveLength(CARD_BATCH_SIZE)
    expect(w.emitted('done')).toBeUndefined()
  })

  it('has no em dashes or semicolons in the new copy', async () => {
    const w = await mountCards([saved('Alpha', 4), noAnswer('Rust'), ...unanswered(CARD_BATCH_SIZE + 2)])
    expect(w.text()).not.toContain('—')
    expect(w.text()).not.toContain(';')
  })
})
