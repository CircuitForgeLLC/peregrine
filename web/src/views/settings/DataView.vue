<script setup lang="ts">
import { ref } from 'vue'
import { storeToRefs } from 'pinia'
import { useDataStore } from '../../stores/settings/data'

const store = useDataStore()
const { backupPath, backupFileCount, backupSizeBytes, creatingBackup, backupError } = storeToRefs(store)
const includeDb = ref(false)
const showRestoreConfirm = ref(false)
const restoreFile = ref<File | null>(null)

function formatBytes(b: number) {
  if (b < 1024) return `${b} B`
  if (b < 1024 * 1024) return `${(b / 1024).toFixed(1)} KB`
  return `${(b / 1024 / 1024).toFixed(1)} MB`
}
</script>

<template>
  <div class="data-view">
    <h2>Data &amp; Backup</h2>

    <!-- Backup -->
    <section class="form-section">
      <h3>Create Backup</h3>
      <p class="section-note">Exports your config files (and optionally the job database) as a zip archive.</p>
      <label class="checkbox-row">
        <input type="checkbox" v-model="includeDb" /> Include job database (staging.db)
      </label>
      <div class="form-actions">
        <button @click="store.createBackup(includeDb)" :disabled="creatingBackup" class="btn-primary">
          {{ creatingBackup ? 'Creating…' : 'Create Backup' }}
        </button>
      </div>
      <p v-if="backupError" class="error-msg">{{ backupError }}</p>
      <div v-if="backupPath" class="backup-result">
        <span>{{ backupFileCount }} files · {{ formatBytes(backupSizeBytes) }}</span>
        <span class="backup-path">{{ backupPath }}</span>
      </div>
    </section>

    <!-- Restore -->
    <section class="form-section">
      <h3>Restore from Backup</h3>
      <p class="section-note">Upload a backup zip to restore your configuration. Existing files will be overwritten.</p>
      <input
        type="file"
        accept=".zip"
        @change="restoreFile = ($event.target as HTMLInputElement).files?.[0] ?? null"
        class="file-input"
      />
      <div class="form-actions">
        <button
          @click="showRestoreConfirm = true"
          :disabled="!restoreFile || store.restoring"
          class="btn-warning"
        >
          {{ store.restoring ? 'Restoring…' : 'Restore' }}
        </button>
      </div>
      <div v-if="store.restoreResult" class="restore-result">
        <p>Restored {{ store.restoreResult.restored.length }} files.</p>
        <p v-if="store.restoreResult.skipped.length">Skipped: {{ store.restoreResult.skipped.join(', ') }}</p>
      </div>
      <p v-if="store.restoreError" class="error-msg">{{ store.restoreError }}</p>

      <Teleport to="body">
        <div v-if="showRestoreConfirm" class="modal-overlay" @click.self="showRestoreConfirm = false">
          <div class="modal-card" role="dialog">
            <h3>Restore Backup?</h3>
            <p>This will overwrite your current configuration. This cannot be undone.</p>
            <div class="modal-actions">
              <button @click="showRestoreConfirm = false" class="btn-danger">Restore</button>
              <button @click="showRestoreConfirm = false" class="btn-secondary">Cancel</button>
            </div>
          </div>
        </div>
      </Teleport>
    </section>
  </div>
</template>
