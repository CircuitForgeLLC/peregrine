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
/** The more button by position, since its label changes to Saving or Retry saving. */
const moreButtonAlways = (w: W) => w.findAll('.gcs__actions button')[1]
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
    expect(w.find('.gcs__progress').text()).toBe(`0 of ${CARD_BATCH_SIZE} answered. There are ${extra} more keywords you can answer after this.`)
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

  it('test_retry_after_a_failed_more_save_retries_the_more_save_and_does_not_start_the_rewrite', async () => {
    const all = unanswered(CARD_BATCH_SIZE + 2)
    let fail = true
    fetchMock.mockImplementation(async (url: string) => {
      if (url.endsWith('/gap_cards')) return { data: { cards: all }, error: null } as any
      return (fail ? { data: null, error: { kind: 'network', message: 'x' } } : { data: { approved_terms: ['T1'], saved: 1 }, error: null }) as any
    })
    const w = mount(GapCards, { props: { jobId: 7, terms: all.map((c) => c.term) }, attachTo: document.body })
    await flushPromises()
    await w.find('input[value="yes"]').setValue(true)
    await w.find('textarea').setValue('Ran clusters')
    await moreButton(w)!.trigger('click')
    await flushPromises()
    const retry = w.findAll('button').find((b) => b.text() === 'Retry saving')!
    expect(retry.classes()).not.toContain('gcs__btn--primary')
    expect((w.find('textarea').element as HTMLTextAreaElement).value).toBe('Ran clusters')
    fail = false
    await retry.trigger('click')
    await flushPromises()
    expect(w.emitted('done')).toBeUndefined()
    expect(answersCalls()).toHaveLength(2)
    expect(legends(w)).toEqual([`T${CARD_BATCH_SIZE + 1}`, `T${CARD_BATCH_SIZE + 2}`])
  })

  it('test_the_main_button_keeps_its_normal_label_after_a_failed_more_save', async () => {
    const w = await mountCards(unanswered(CARD_BATCH_SIZE + 1), { data: null, error: { kind: 'network', message: 'x' } })
    await moreButton(w)!.trigger('click')
    await flushPromises()
    expect(mainButton(w).text()).toBe('Save answers and continue')
  })

  it('test_promoting_without_changing_sends_nothing_for_that_keyword', async () => {
    const w = await mountCards([card('Go'), noAnswer('Rust')])
    await changeButton(w, 'Rust').trigger('click')
    await mainButton(w).trigger('click')
    await flushPromises()
    expect(answersCalls()[0].map((a) => a.term)).toEqual(['Go'])
  })

  it('test_promoting_without_changing_sends_no_request_when_nothing_else_is_there', async () => {
    const w = await mountCards([noAnswer('Rust')])
    await changeButton(w, 'Rust').trigger('click')
    await mainButton(w).trigger('click')
    await flushPromises()
    expect(answersCalls()).toHaveLength(0)
    expect(w.emitted('done')![0]).toEqual([[]])
  })

  it('test_a_promoted_keyword_that_was_changed_is_sent', async () => {
    const w = await mountCards([card('Go'), noAnswer('Rust')])
    await changeButton(w, 'Rust').trigger('click')
    await w.findAll('fieldset')[1].find('input[value="skip"]').setValue(true)
    await mainButton(w).trigger('click')
    await flushPromises()
    expect(answersCalls()[0].find((a) => a.term === 'Rust')).toMatchObject({ choice: 'skip' })
  })

  it('test_focus_goes_to_the_heading_when_there_are_no_cards', async () => {
    const w = await mountCards([saved('Alpha', 4)])
    expect(w.find('fieldset').exists()).toBe(false)
    expect(document.activeElement).toBe(w.find('#gcs-heading').element)
  })

  it('test_the_saved_group_note_says_not_used_when_the_toggle_was_off', async () => {
    const all = [saved('Alpha', 4), ...unanswered(CARD_BATCH_SIZE + 1)]
    const w = await mountCards(all)
    await w.find('.gcs__saved input[type="checkbox"]').setValue(false)
    await moreButton(w)!.trigger('click')
    await flushPromises()
    expect(w.find('.gcs__saved').text()).toContain('Not used for this job.')
    expect(w.find('.gcs__saved').text()).not.toContain('already saved')
    const w2 = await mountCards(all)
    await moreButton(w2)!.trigger('click')
    await flushPromises()
    expect(w2.find('.gcs__saved').text()).toContain('These are already saved for this job.')
  })

  it('test_change_is_disabled_while_saving_and_no_keyword_is_lost', async () => {
    const all = [...unanswered(CARD_BATCH_SIZE + 1), noAnswer('Rust')]
    let release: (v: unknown) => void = () => {}
    fetchMock.mockImplementation(async (url: string) => {
      if (url.endsWith('/gap_cards')) return { data: { cards: all }, error: null } as any
      return new Promise((r) => { release = r }) as any
    })
    const w = mount(GapCards, { props: { jobId: 7, terms: all.map((c) => c.term) }, attachTo: document.body })
    await flushPromises()
    expect(w.find('.gcs__list').attributes('inert')).toBeUndefined()
    await moreButton(w)!.trigger('click')
    await flushPromises()
    expect(changeButton(w, 'Rust').attributes('disabled')).toBeDefined()
    expect(w.find('.gcs__list').attributes('inert')).toBeDefined()
    // A click that still reaches the disabled button changes nothing.
    const legendsBefore = legends(w)
    const notUsedBefore = w.find('.gcs__skipped').text()
    changeButton(w, 'Rust').element.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    await flushPromises()
    expect(legends(w)).toEqual(legendsBefore)
    expect(legends(w)).not.toContain('Rust')
    expect(w.find('.gcs__skipped').text()).toBe(notUsedBefore)
    expect(w.find('.gcs__skipped summary').text()).toBe('Answered, not used (1)')
    release({ data: { approved_terms: [], saved: 0 }, error: null })
    await flushPromises()
    expect(w.find('.gcs__list').attributes('inert')).toBeUndefined()
    expect(changeButton(w, 'Rust').attributes('disabled')).toBeUndefined()
    await changeButton(w, 'Rust').trigger('click')
    expect(legends(w)).toContain('Rust')
  })

  it('test_the_card_list_is_inert_only_while_saving', async () => {
    const all = unanswered(CARD_BATCH_SIZE + 1)
    let release: (v: unknown) => void = () => {}
    fetchMock.mockImplementation(async (url: string) => {
      if (url.endsWith('/gap_cards')) return { data: { cards: all }, error: null } as any
      return new Promise((r) => { release = r }) as any
    })
    const w = mount(GapCards, { props: { jobId: 7, terms: all.map((c) => c.term) }, attachTo: document.body })
    await flushPromises()
    const list = () => w.find('.gcs__list')
    expect(list().attributes('inert')).toBeUndefined()
    expect(list().html()).not.toContain('inert')
    await moreButtonAlways(w).trigger('click')
    await flushPromises()
    expect(list().attributes('inert')).toBeDefined()
    release({ data: null, error: { kind: 'network', message: 'x' } })
    await flushPromises()
    expect(list().attributes('inert')).toBeUndefined()
    expect(list().html()).not.toContain('inert')
    await moreButtonAlways(w).trigger('click')
    await flushPromises()
    expect(list().attributes('inert')).toBeDefined()
    release({ data: { approved_terms: [], saved: 0 }, error: null })
    await flushPromises()
    expect(list().attributes('inert')).toBeUndefined()
    expect(list().html()).not.toContain('inert')
  })

  it('test_exactly_the_batch_size_remaining_says_last_and_builds_the_number_from_the_constant', async () => {
    const w = await mountCards(unanswered(CARD_BATCH_SIZE * 2))
    expect(moreButton(w)!.text()).toBe(`Save and ask about the last ${CARD_BATCH_SIZE}`)
    const w2 = await mountCards(unanswered(CARD_BATCH_SIZE * 2 + 1))
    expect(moreButton(w2)!.text()).toBe(`Save and ask about the next ${CARD_BATCH_SIZE} (${CARD_BATCH_SIZE + 1} more)`)
  })

  it('test_no_progress_line_when_there_are_no_cards', async () => {
    const w = await mountCards([saved('Alpha', 4)])
    expect(w.find('.gcs__progress').exists()).toBe(false)
    expect(w.text()).not.toContain('0 of 0')
    expect(w.text()).not.toContain('For each keyword')
  })

  it('test_drafts_survive_going_back_and_reopening_across_batches', async () => {
    const cards = unanswered(CARD_BATCH_SIZE + 1)
    const last = `T${CARD_BATCH_SIZE + 1}`
    const w = await mountCards(cards)
    await w.find('input[value="yes"]').setValue(true)
    await w.find('textarea').setValue('First draft')
    await moreButtonAlways(w).trigger('click')
    await flushPromises()
    await w.find('input[value="yes"]').setValue(true)
    await w.find('textarea').setValue('Second draft')
    const drafts = w.emitted('drafts-change')!.at(-1)![0] as Record<string, any>
    const w2 = await mountCards(cards, emptyOk, drafts)
    expect((w2.find('textarea').element as HTMLTextAreaElement).value).toBe('First draft')
    await moreButton(w2)!.trigger('click')
    await flushPromises()
    expect(legends(w2)).toEqual([last])
    expect((w2.find('textarea').element as HTMLTextAreaElement).value).toBe('Second draft')
  })

  it('test_an_untouched_changed_keyword_returns_to_answered_not_used_after_a_more_save', async () => {
    const all = [...unanswered(CARD_BATCH_SIZE + 1), noAnswer('Rust', 2), noAnswer('Zulu', 3)]
    const w = await mountCards(all)
    await changeButton(w, 'Rust').trigger('click')
    expect(w.find('.gcs__skipped summary').text()).toBe('Answered, not used (1)')
    await moreButton(w)!.trigger('click')
    await flushPromises()
    const body = answersCalls()[0]
    expect(body.map((a) => a.term)).not.toContain('Rust')
    expect(legends(w)).toEqual([`T${CARD_BATCH_SIZE + 1}`])
    expect(legends(w)).not.toContain('Rust')
    const group = w.find('.gcs__skipped')
    expect(group.exists()).toBe(true)
    expect(group.find('summary').text()).toBe('Answered, not used (2)')
    const terms = group.findAll('.gcs__term').map((t) => t.text())
    expect(terms).toEqual(['Rust', 'Zulu'])
    expect(group.text()).toContain('You said you have not done this')
    expect(changeButton(w, 'Rust')).toBeDefined()
    // It can be changed again from there.
    await changeButton(w, 'Rust').trigger('click')
    expect(legends(w)).toContain('Rust')
  })

  it('test_a_changed_keyword_stays_saved_and_is_not_returned_to_answered_not_used', async () => {
    const all = [...unanswered(CARD_BATCH_SIZE + 1), noAnswer('Rust', 2)]
    const w = await mountCards(all, { data: { approved_terms: ['Rust'], saved: 1 }, error: null })
    await changeButton(w, 'Rust').trigger('click')
    const rustSet = w.findAll('fieldset')[CARD_BATCH_SIZE]
    await rustSet.find('input[value="yes"]').setValue(true)
    await rustSet.find('textarea').setValue('Wrote services')
    await moreButton(w)!.trigger('click')
    await flushPromises()
    expect(answersCalls()[0].find((a) => a.term === 'Rust')).toMatchObject({ choice: 'yes', text: 'Wrote services' })
    expect(w.find('.gcs__skipped').exists()).toBe(false)
    expect(legends(w)).toEqual([`T${CARD_BATCH_SIZE + 1}`])
  })

  it('test_retry_after_a_failed_main_save_emits_done_after_success', async () => {
    const all = unanswered(CARD_BATCH_SIZE + 1)
    let fail = true
    fetchMock.mockImplementation(async (url: string) => {
      if (url.endsWith('/gap_cards')) return { data: { cards: all }, error: null } as any
      return (fail ? { data: null, error: { kind: 'network', message: 'x' } } : { data: { approved_terms: ['T1'], saved: 1 }, error: null }) as any
    })
    const w = mount(GapCards, { props: { jobId: 7, terms: all.map((c) => c.term) }, attachTo: document.body })
    await flushPromises()
    await w.find('input[value="yes"]').setValue(true)
    await w.find('textarea').setValue('Ran clusters')
    await mainButton(w).trigger('click')
    await flushPromises()
    expect(mainButton(w).text()).toBe('Retry saving')
    expect(moreButton(w)!.text()).not.toBe('Retry saving')
    expect(w.emitted('done')).toBeUndefined()
    expect((w.find('textarea').element as HTMLTextAreaElement).value).toBe('Ran clusters')
    fail = false
    await mainButton(w).trigger('click')
    await flushPromises()
    const calls = answersCalls()
    expect(calls).toHaveLength(2)
    expect(calls[1]).toEqual(calls[0])
    expect(calls[0]).toHaveLength(CARD_BATCH_SIZE)
    expect(calls[0][0]).toMatchObject({ term: 'T1', choice: 'yes', text: 'Ran clusters' })
    expect((w.find('textarea').element as HTMLTextAreaElement).value).toBe('Ran clusters')
    expect(w.emitted('done')).toHaveLength(1)
    expect(w.emitted('done')![0]).toEqual([['T1']])
    // The more button took no part: the batch did not advance.
    expect(legends(w)).toEqual(Array.from({ length: CARD_BATCH_SIZE }, (_, i) => `T${i + 1}`))
  })

  it('test_saving_is_shown_only_on_the_pressed_button', async () => {
    const all = unanswered(CARD_BATCH_SIZE + 2)
    const normalMore = `Save and ask about the last 2`
    async function mountDeferred() {
      let release: (v: unknown) => void = () => {}
      fetchMock.mockImplementation(async (url: string) => {
        if (url.endsWith('/gap_cards')) return { data: { cards: all }, error: null } as any
        return new Promise((r) => { release = r }) as any
      })
      const w = mount(GapCards, { props: { jobId: 7, terms: all.map((c) => c.term) }, attachTo: document.body })
      await flushPromises()
      return { w, release: (v: unknown) => release(v) }
    }
    const a = await mountDeferred()
    await mainButton(a.w).trigger('click')
    await flushPromises()
    expect(mainButton(a.w).text()).toBe('Saving…')
    expect(moreButtonAlways(a.w).text()).toBe(normalMore)
    expect(mainButton(a.w).attributes('disabled')).toBeDefined()
    expect(moreButtonAlways(a.w).attributes('disabled')).toBeDefined()
    a.release({ data: { approved_terms: [], saved: 0 }, error: null })
    await flushPromises()

    const b = await mountDeferred()
    await moreButtonAlways(b.w).trigger('click')
    await flushPromises()
    expect(moreButtonAlways(b.w).text()).toBe('Saving…')
    expect(mainButton(b.w).text()).toBe('Save answers and continue')
    expect(mainButton(b.w).attributes('disabled')).toBeDefined()
    expect(moreButtonAlways(b.w).attributes('disabled')).toBeDefined()
    b.release({ data: { approved_terms: [], saved: 0 }, error: null })
    await flushPromises()
  })

  it('has no em dashes or semicolons in the new copy', async () => {
    const w = await mountCards([saved('Alpha', 4), noAnswer('Rust'), ...unanswered(CARD_BATCH_SIZE + 2)])
    expect(w.text()).not.toContain('—')
    expect(w.text()).not.toContain(';')
  })
})
