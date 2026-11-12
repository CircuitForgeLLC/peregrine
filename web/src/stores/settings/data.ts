import { ref } from 'vue'
import { defineStore } from 'pinia'
import { useApiFetch } from '../../composables/useApi'

export const useDataStore = defineStore('settings/data', () => {
  const backupPath = ref<string | null>(null)
  const backupFileCount = ref(0)
  const backupSizeBytes = ref(0)
  const creatingBackup = ref(false)
  const restoring = ref(false)
  const restoreResult = ref<{restored: string[]; skipped: string[]} | null>(null)
  const backupError = ref<string | null>(null)
  const restoreError = ref<string | null>(null)

  async function createBackup(includeDb: boolean) {
    creatingBackup.value = true
    backupError.value = null
    const { data, error } = await useApiFetch<{path: string; file_count: number; size_bytes: number}>(
      '/api/settings/data/backup/create',
      { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ include_db: includeDb }) }
    )
    creatingBackup.value = false
    if (error || !data) { backupError.value = 'Backup failed'; return }
    backupPath.value = data.path
    backupFileCount.value = data.file_count
    backupSizeBytes.value = data.size_bytes
  }

  async function restore(file: File) {
    restoring.value = true
    restoreError.value = null
    restoreResult.value = null
    const body = new FormData()
    body.append('file', file)
    const { data, error } = await useApiFetch<{restored: string[]; skipped: string[]}>(
      '/api/settings/data/backup/restore',
      // The custom header is what stops another website from posting a forged backup
      // here: browsers will not add one to a cross-site form. Content-Type stays unset
      // so the browser can add the multipart boundary.
      { method: 'POST', body, headers: { 'X-Requested-With': 'peregrine' } }
    )
    restoring.value = false
    if (data) { restoreResult.value = data; return }
    if (error?.kind === 'demo-blocked') return  // useApiFetch already showed a toast
    restoreError.value = error?.kind === 'http'
      ? (restoreMessage(error.detail) ?? 'Restore failed. Please try again.')
      : 'Restore failed. Please check your connection and try again.'
  }

  // The API answers {"detail": "..."} with a message written for people.
  function restoreMessage(raw: string): string | null {
    try {
      const detail = (JSON.parse(raw) as { detail?: unknown }).detail
      return typeof detail === 'string' && detail ? detail : null
    } catch {
      return null
    }
  }

  return { backupPath, backupFileCount, backupSizeBytes, creatingBackup, restoring, restoreResult, backupError, restoreError, createBackup, restore }
})
