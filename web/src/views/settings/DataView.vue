<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { storeToRefs } from 'pinia'
import { useDataStore } from '../../stores/settings/data'
import { useSyncStore, SYNC_DATA_CLASSES } from '../../stores/settings/sync'
import { useAppConfigStore } from '../../stores/appConfig'

const store = useDataStore()
const { backupPath, backupFileCount, backupSizeBytes, creatingBackup, backupError } = storeToRefs(store)
const includeDb = ref(false)
const showRestoreConfirm = ref(false)
const restoreFile = ref<File | null>(null)

const sync  = useSyncStore()
const config = useAppConfigStore()

const canSync = config.isCloud && ['paid', 'premium'].includes(config.tier)

onMounted(() => { if (config.isCloud) sync.loadPrefs() })

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

    <!-- Cross-device sync — cloud accounts only -->
    <section v-if="config.isCloud" class="form-section">
      <h3>Cross-device Sync <span class="tier-badge">Paid</span></h3>
      <p class="section-note">
        Sync selected data to your cloud account so it follows you across devices.
        Each category is opt-in — nothing is uploaded until you enable it.
      </p>

      <div v-if="sync.loading" class="sync-loading">Loading sync preferences…</div>

      <template v-else-if="canSync">
        <div v-for="dc in SYNC_DATA_CLASSES" :key="dc.key" class="sync-row">
          <label class="sync-toggle-label">
            <input
              type="checkbox"
              :checked="sync.prefs[dc.key] ?? false"
              :disabled="sync.saving === dc.key"
              @change="sync.setPref(dc.key, ($event.target as HTMLInputElement).checked)"
            />
            <span class="sync-label-text">
              <strong>{{ dc.label }}</strong>
              <span class="sync-label-desc">{{ dc.description }}</span>
            </span>
          </label>
        </div>
        <p v-if="sync.error" class="error-msg">{{ sync.error }}</p>
      </template>

      <p v-else class="tier-gate-note">
        Cross-device sync is available on the Paid and Premium plans.
      </p>

      <!-- Delete all — tier-free, always shown to cloud users -->
      <div class="form-actions sync-delete-row">
        <button
          class="btn-danger"
          :disabled="sync.wiping"
          @click="sync.wipeAll()"
        >
          {{ sync.wiping ? 'Deleting…' : 'Delete all sync data' }}
        </button>
        <span class="section-note">Removes all uploaded sync data immediately. Preferences are also reset.</span>
      </div>
    </section>
  </div>
</template>

<style scoped>
.tier-badge {
  font-size: 0.7rem;
  font-weight: 600;
  padding: 0.15em 0.5em;
  border-radius: 4px;
  background: var(--color-accent, #6c63ff);
  color: #fff;
  vertical-align: middle;
  margin-left: 0.4em;
}
.sync-loading { color: var(--color-text-muted); font-size: 0.9rem; margin: 0.5rem 0; }
.sync-row { margin: 0.75rem 0; }
.sync-toggle-label { display: flex; align-items: flex-start; gap: 0.6rem; cursor: pointer; }
.sync-label-text { display: flex; flex-direction: column; gap: 0.1rem; }
.sync-label-desc { font-size: 0.8rem; color: var(--color-text-muted); }
.sync-delete-row { display: flex; align-items: center; gap: 1rem; flex-wrap: wrap; margin-top: 1rem; }
.sync-delete-row .section-note { margin: 0; }
.tier-gate-note { font-size: 0.85rem; color: var(--color-text-muted); margin: 0.5rem 0; }
</style>
