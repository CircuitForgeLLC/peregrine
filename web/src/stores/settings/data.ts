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

  return { backupPath, backupFileCount, backupSizeBytes, creatingBackup, restoring, restoreResult, backupError, restoreError, createBackup }
})
