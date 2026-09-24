import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { setActivePinia, createPinia } from 'pinia'

vi.mock('../../composables/useApi', () => ({
  useApiFetch: vi.fn(),
}))

import { useApiFetch } from '../../composables/useApi'
import ContactsView from '../ContactsView.vue'

const mockContacts = {
  total: 2,
  contacts: [
    { id: 1, job_id: 5, direction: 'inbound', subject: 'Interview invite', from_addr: 'a@co.com',
      to_addr: null, received_at: '2026-09-20T00:00:00Z', stage_signal: 'interview_scheduled',
      job_title: 'Engineer', job_company: 'Acme' },
    { id: 2, job_id: null, direction: 'inbound', subject: 'Newsletter', from_addr: 'b@co.com',
      to_addr: null, received_at: '2026-09-21T00:00:00Z', stage_signal: null,
      job_title: null, job_company: null },
  ],
}
const mockSyncStatus = { status: 'idle', last_completed_at: null }

async function mountView() {
  setActivePinia(createPinia())
  vi.mocked(useApiFetch)
    .mockResolvedValueOnce({ data: mockContacts, error: null } as any)
    .mockResolvedValueOnce({ data: mockSyncStatus, error: null } as any)
  const wrapper = mount(ContactsView)
  await new Promise((r) => setTimeout(r, 0))
  return wrapper
}

describe('ContactsView', () => {
  beforeEach(() => vi.clearAllMocks())

  it('renders a signal chip for a classified contact', async () => {
    const wrapper = await mountView()
    expect(wrapper.text()).toContain('📅 Interview')
  })

  it('shows a Re-classify placeholder for an unclassified contact', async () => {
    const wrapper = await mountView()
    expect(wrapper.text()).toContain('Re-classify')
  })

  it('clicking the signal chip turns it into a re-classify select', async () => {
    const wrapper = await mountView()
    const chips = wrapper.findAll('.signal-chip--clickable')
    await chips[0].trigger('click')
    expect(wrapper.find('.signal-reclassify-select').exists()).toBe(true)
  })

  it('reclassifying to Digest reclassifies, dismisses, and queues for digest review (peregrine gap fix)', async () => {
    const wrapper = await mountView()
    vi.mocked(useApiFetch).mockResolvedValue({ data: { ok: true }, error: null } as any)

    const chips = wrapper.findAll('.signal-chip--clickable')
    await chips[0].trigger('click')
    const select = wrapper.find('.signal-reclassify-select')
    await select.setValue('digest')

    // reclassify + dismiss + digest-queue POST, beyond the 2 initial mount calls
    const calls = vi.mocked(useApiFetch).mock.calls
    const urls = calls.map((c) => c[0])
    expect(urls).toContain('/api/stage-signals/1/reclassify')
    expect(urls).toContain('/api/stage-signals/1/dismiss')
    expect(urls).toContain('/api/digest-queue')
  })

  it('reclassifying to a non-dismiss label (e.g. Offer) does not call dismiss or digest-queue', async () => {
    const wrapper = await mountView()
    vi.mocked(useApiFetch).mockResolvedValue({ data: { ok: true }, error: null } as any)

    const chips = wrapper.findAll('.signal-chip--clickable')
    await chips[0].trigger('click')
    const select = wrapper.find('.signal-reclassify-select')
    await select.setValue('offer_received')

    const calls = vi.mocked(useApiFetch).mock.calls
    const urls = calls.map((c) => c[0])
    expect(urls).toContain('/api/stage-signals/1/reclassify')
    expect(urls).not.toContain('/api/stage-signals/1/dismiss')
    expect(urls).not.toContain('/api/digest-queue')
  })

  it('changing the signal filter re-fetches with the stage_signal query param', async () => {
    const wrapper = await mountView()
    vi.mocked(useApiFetch).mockResolvedValue({ data: { total: 0, contacts: [] }, error: null } as any)

    const select = wrapper.find('.contacts-signal-filter')
    await select.setValue('needs_review')

    const calls = vi.mocked(useApiFetch).mock.calls
    const lastUrl = calls[calls.length - 1][0] as string
    expect(lastUrl).toContain('stage_signal=needs_review')
  })
})
