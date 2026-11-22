import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises, type VueWrapper } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import DataView from './DataView.vue'
import { useAppConfigStore } from '../../stores/appConfig'

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

// Regression for peregrine#247: the hosted API refuses restore with a 403, so the hosted
// page must not offer a picker, an overwrite warning or a Restore button that cannot work.
describe('DataView, restore on the hosted version', () => {
  function mountWith(isCloud: boolean) {
    setActivePinia(createPinia())
    vi.clearAllMocks()
    mockFetch.mockResolvedValue({ data: [], error: null } as never)
    useAppConfigStore().isCloud = isCloud
    return mount(DataView, { attachTo: document.body })
  }

  it('hides the picker, warning and Restore button and explains why on hosted', () => {
    const wrapper = mountWith(true)
    expect(wrapper.find('input[type="file"]').exists()).toBe(false)
    expect(wrapper.find('button.btn-warning').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('Existing files will be overwritten')
    expect(wrapper.text()).toContain("Restoring a backup isn't available on the hosted version.")
    expect(wrapper.text()).toContain('Create Backup')
    wrapper.unmount()
  })

  it('still shows the picker and Restore button when self-hosted', () => {
    const wrapper = mountWith(false)
    expect(wrapper.find('input[type="file"]').exists()).toBe(true)
    expect(wrapper.find('button.btn-warning').exists()).toBe(true)
    expect(wrapper.text()).not.toContain("isn't available on the hosted version")
    wrapper.unmount()
  })
})
