import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises, type VueWrapper } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import DataView from './DataView.vue'

vi.mock('../../composables/useApi', () => ({ useApiFetch: vi.fn() }))
import { useApiFetch } from '../../composables/useApi'
const mockFetch = vi.mocked(useApiFetch)

const RESTORE_URL = '/api/settings/data/backup/restore'

// Regression for peregrine#222: the dialog's Restore button had the same handler as
// Cancel (it only closed the dialog), so choosing a backup and confirming did nothing.
describe('DataView, restore from backup', () => {
  let wrapper: VueWrapper

  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
    mockFetch.mockResolvedValue({ data: { restored: ['config/user.yaml'], skipped: [] }, error: null } as never)
    wrapper = mount(DataView, { attachTo: document.body })
  })

  afterEach(() => wrapper.unmount())

  async function chooseBackup() {
    const input = wrapper.find('input[type="file"]')
    const file = new File(['PK'], 'backup.zip', { type: 'application/zip' })
    Object.defineProperty(input.element, 'files', { value: [file], configurable: true })
    await input.trigger('change')
    return file
  }

  const openDialog = async () => {
    await wrapper.find('button.btn-warning').trigger('click')
    await flushPromises()
  }

  const restoreCalls = () => mockFetch.mock.calls.filter(([url]) => url === RESTORE_URL)

  it('does not restore until the dialog is confirmed', async () => {
    await chooseBackup()
    await openDialog()

    expect(document.body.textContent).toContain('Restore Backup?')
    expect(restoreCalls()).toHaveLength(0)
  })

  it('uploads the chosen file when the dialog is confirmed, then closes it', async () => {
    const file = await chooseBackup()
    await openDialog()

    ;(document.body.querySelector('.modal-actions .btn-danger') as HTMLButtonElement).click()
    await flushPromises()

    expect(restoreCalls()).toHaveLength(1)
    expect(((restoreCalls()[0][1]?.body) as FormData).get('file')).toBe(file)
    expect(document.body.textContent).not.toContain('Restore Backup?')
    expect(wrapper.text()).toContain('Restored 1 files.')
  })

  it('does nothing when the dialog is cancelled', async () => {
    await chooseBackup()
    await openDialog()

    ;(document.body.querySelector('.modal-actions .btn-secondary') as HTMLButtonElement).click()
    await flushPromises()

    expect(restoreCalls()).toHaveLength(0)
    expect(document.body.textContent).not.toContain('Restore Backup?')
  })

  it('shows why a restore failed', async () => {
    mockFetch.mockResolvedValue({
      data: null,
      error: { kind: 'http', status: 400, detail: JSON.stringify({ detail: 'No settings files found in that backup.' }) },
    } as never)
    await chooseBackup()
    await openDialog()

    ;(document.body.querySelector('.modal-actions .btn-danger') as HTMLButtonElement).click()
    await flushPromises()

    expect(wrapper.text()).toContain('No settings files found in that backup.')
  })
})
