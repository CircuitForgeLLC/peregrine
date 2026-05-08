<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useApiFetch } from '../composables/useApi'
import HintChip from '../components/HintChip.vue'
import { useAppConfigStore } from '../stores/appConfig'

const config = useAppConfigStore()

interface Contact {
  id:           number
  job_id:       number
  direction:    'inbound' | 'outbound'
  subject:      string | null
  from_addr:    string | null
  to_addr:      string | null
  received_at:  string | null
  stage_signal: string | null
  job_title:    string | null
  job_company:  string | null
}

const contacts    = ref<Contact[]>([])
const total       = ref(0)
const loading     = ref(false)
const error       = ref<string | null>(null)
const search      = ref('')
const direction   = ref<'all' | 'inbound' | 'outbound'>('all')
const searchInput = ref('')
const syncing     = ref(false)
const syncStatus  = ref<{ status: string; last_completed_at: string | null } | null>(null)
let debounceTimer: ReturnType<typeof setTimeout> | null = null

async function fetchContacts() {
  loading.value = true
  error.value = null
  const params = new URLSearchParams({ limit: '100' })
  if (direction.value !== 'all') params.set('direction', direction.value)
  if (search.value) params.set('search', search.value)

  const { data, error: fetchErr } = await useApiFetch<{ total: number; contacts: Contact[] }>(
    `/api/contacts?${params}`
  )
  loading.value = false
  if (fetchErr || !data) {
    error.value = 'Failed to load contacts.'
    return
  }
  contacts.value = data.contacts
  total.value = data.total
}

function onSearchInput() {
  if (debounceTimer) clearTimeout(debounceTimer)
  debounceTimer = setTimeout(() => {
    search.value = searchInput.value
    fetchContacts()
  }, 300)
}

function onDirectionChange() {
  fetchContacts()
}

function formatDate(iso: string | null): string {
  if (!iso) return '—'
  return new Date(iso).toLocaleDateString([], { month: 'short', day: 'numeric', year: 'numeric' })
}

function displayAddr(contact: Contact): string {
  return contact.direction === 'inbound'
    ? contact.from_addr ?? '—'
    : contact.to_addr   ?? '—'
}

const signalLabel: Record<string, string> = {
  interview_scheduled: '📅 Interview',
  offer_received:      '🟢 Offer',
  rejected:            '✖ Rejected',
  positive_response:   '✅ Positive',
  survey_received:     '📋 Survey',
  event_rescheduled:   '🔄 Rescheduled',
  neutral:             '— Neutral',
}

async function fetchSyncStatus() {
  const { data } = await useApiFetch<{ status: string; last_completed_at: string | null }>(
    '/api/email/sync/status'
  )
  if (data) syncStatus.value = data
}

async function triggerSync() {
  syncing.value = true
  await useApiFetch('/api/tasks/email-sync', { method: 'POST' })
  // Poll until the task finishes or we give up after 60 s
  const deadline = Date.now() + 60_000
  const poll = setInterval(async () => {
    await fetchSyncStatus()
    if (syncStatus.value?.status === 'completed' || Date.now() > deadline) {
      clearInterval(poll)
      syncing.value = false
      fetchContacts()
    }
  }, 2000)
}

function formatSyncTime(iso: string | null): string {
  if (!iso) return 'never'
  const d = new Date(iso)
  const diff = Date.now() - d.getTime()
  if (diff < 60_000)  return 'just now'
  if (diff < 3_600_000) return `${Math.floor(diff / 60_000)}m ago`
  if (diff < 86_400_000) return `${Math.floor(diff / 3_600_000)}h ago`
  return d.toLocaleDateString([], { month: 'short', day: 'numeric' })
}

onMounted(async () => {
  await Promise.all([fetchContacts(), fetchSyncStatus()])
})
</script>

<template>
  <div class="contacts-view">
    <HintChip
      v-if="config.isDemo"
      view-key="contacts"
      message="Peregrine logs every recruiter email automatically — no manual entry needed"
    />
    <header class="contacts-header">
      <h1 class="contacts-title">Contacts</h1>
      <span class="contacts-count" v-if="total > 0">{{ total }} total</span>
      <div class="contacts-sync">
        <span v-if="syncStatus" class="sync-last">
          Last sync: {{ formatSyncTime(syncStatus.last_completed_at) }}
        </span>
        <button
          class="btn-sync"
          :disabled="syncing"
          @click="triggerSync"
          :aria-label="syncing ? 'Email sync running' : 'Sync email now'"
        >
          <span :class="['sync-icon', { 'sync-icon--spinning': syncing }]">↻</span>
          {{ syncing ? 'Syncing…' : 'Sync email' }}
        </button>
      </div>
    </header>

    <div class="contacts-toolbar">
      <input
        v-model="searchInput"
        class="contacts-search"
        type="search"
        placeholder="Search name, email, or subject…"
        aria-label="Search contacts"
        @input="onSearchInput"
      />
      <div class="contacts-filter" role="group" aria-label="Filter by direction">
        <button
          v-for="opt in (['all', 'inbound', 'outbound'] as const)"
          :key="opt"
          class="filter-btn"
          :class="{ 'filter-btn--active': direction === opt }"
          @click="direction = opt; onDirectionChange()"
        >{{ opt === 'all' ? 'All' : opt === 'inbound' ? 'Inbound' : 'Outbound' }}</button>
      </div>
    </div>

    <div v-if="loading" class="contacts-empty">Loading…</div>
    <div v-else-if="error" class="contacts-empty contacts-empty--error">{{ error }}</div>
    <div v-else-if="contacts.length === 0 && !search" class="contacts-empty contacts-empty--setup">
      <p>No contacts yet.</p>
      <p class="contacts-empty-hint">
        Connect your inbox in
        <a href="/settings?tab=connections" class="setup-link">Settings → Connections</a>
        then hit <strong>Sync email</strong> to import recruiter emails automatically.
      </p>
    </div>
    <div v-else-if="contacts.length === 0" class="contacts-empty">
      No contacts found for that search.
    </div>

    <div v-else class="contacts-table-wrap">
      <table class="contacts-table" aria-label="Contacts">
        <thead>
          <tr>
            <th>Contact</th>
            <th>Subject</th>
            <th>Job</th>
            <th>Signal</th>
            <th>Date</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="c in contacts"
            :key="c.id"
            class="contacts-row"
            :class="{ 'contacts-row--inbound': c.direction === 'inbound' }"
          >
            <td class="contacts-cell contacts-cell--addr">
              <span class="dir-chip" :class="`dir-chip--${c.direction}`">
                {{ c.direction === 'inbound' ? '↓' : '↑' }}
              </span>
              {{ displayAddr(c) }}
            </td>
            <td class="contacts-cell contacts-cell--subject">
              {{ c.subject ? c.subject.slice(0, 60) + (c.subject.length > 60 ? '…' : '') : '—' }}
            </td>
            <td class="contacts-cell contacts-cell--job">
              <span v-if="c.job_title">
                {{ c.job_title }}<span v-if="c.job_company" class="job-company"> · {{ c.job_company }}</span>
              </span>
              <span v-else class="text-muted">—</span>
            </td>
            <td class="contacts-cell contacts-cell--signal">
              <span v-if="c.stage_signal && signalLabel[c.stage_signal]" class="signal-chip">
                {{ signalLabel[c.stage_signal] }}
              </span>
            </td>
            <td class="contacts-cell contacts-cell--date">{{ formatDate(c.received_at) }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<style scoped>
.contacts-view {
  padding: var(--space-6);
  max-width: 1000px;
}

.contacts-header {
  display: flex;
  align-items: baseline;
  gap: var(--space-3);
  margin-bottom: var(--space-5);
}

.contacts-title {
  font-size: var(--text-2xl);
  font-weight: 700;
  color: var(--color-text);
  margin: 0;
}

.contacts-count {
  font-size: var(--text-sm);
  color: var(--color-text-muted);
}

.contacts-toolbar {
  display: flex;
  gap: var(--space-3);
  align-items: center;
  margin-bottom: var(--space-4);
  flex-wrap: wrap;
}

.contacts-search {
  flex: 1;
  min-width: 200px;
  padding: var(--space-2) var(--space-3);
  border: 1px solid var(--color-border);
  border-radius: 8px;
  background: var(--color-surface);
  color: var(--color-text);
  font-size: var(--text-sm);
}

.contacts-search:focus-visible {
  outline: 2px solid var(--app-primary);
  outline-offset: 2px;
}

.contacts-filter {
  display: flex;
  gap: 4px;
}

.filter-btn {
  padding: var(--space-1) var(--space-3);
  border: 1px solid var(--color-border);
  border-radius: 6px;
  background: var(--color-surface);
  color: var(--color-text-muted);
  font-size: var(--text-sm);
  cursor: pointer;
}

.filter-btn--active {
  background: var(--app-primary-light);
  color: var(--app-primary);
  border-color: var(--app-primary);
  font-weight: 600;
}

.contacts-empty {
  color: var(--color-text-muted);
  font-size: var(--text-sm);
  padding: var(--space-8) 0;
  text-align: center;
}

.contacts-empty--error {
  color: var(--color-error, #c0392b);
}

.contacts-table-wrap {
  overflow-x: auto;
}

.contacts-table {
  width: 100%;
  border-collapse: collapse;
  font-size: var(--text-sm);
}

.contacts-table th {
  text-align: left;
  padding: var(--space-2) var(--space-3);
  font-size: var(--text-xs);
  font-weight: 600;
  color: var(--color-text-muted);
  text-transform: uppercase;
  letter-spacing: 0.04em;
  border-bottom: 1px solid var(--color-border);
}

.contacts-row {
  border-bottom: 1px solid var(--color-border);
}

.contacts-row:hover {
  background: var(--color-hover);
}

.contacts-cell {
  padding: var(--space-3);
  vertical-align: top;
  color: var(--color-text);
}

.contacts-cell--addr {
  white-space: nowrap;
  font-size: var(--text-xs);
  font-family: var(--font-mono);
  display: flex;
  align-items: center;
  gap: var(--space-2);
}

.contacts-cell--subject {
  color: var(--color-text-muted);
}

.contacts-cell--job {
  font-size: var(--text-xs);
}

.job-company {
  color: var(--color-text-muted);
}

.contacts-cell--date {
  white-space: nowrap;
  color: var(--color-text-muted);
  font-size: var(--text-xs);
}

.dir-chip {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 18px;
  height: 18px;
  border-radius: 4px;
  font-size: 10px;
  font-weight: 700;
  flex-shrink: 0;
}

.dir-chip--inbound {
  background: rgba(39, 174, 96, 0.15);
  color: var(--color-success);
}

.dir-chip--outbound {
  background: var(--app-primary-light);
  color: var(--app-primary);
}

.signal-chip {
  font-size: var(--text-xs);
  white-space: nowrap;
}

.text-muted {
  color: var(--color-text-muted);
}

.contacts-sync {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  margin-left: auto;
}

.sync-last {
  font-size: var(--text-xs);
  color: var(--color-text-muted);
}

.btn-sync {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 14px;
  background: transparent;
  border: 1px solid var(--color-border);
  border-radius: 7px;
  color: var(--color-text-muted);
  font-size: var(--text-sm);
  cursor: pointer;
  white-space: nowrap;
}

.btn-sync:hover:not(:disabled) {
  border-color: var(--app-primary);
  color: var(--app-primary);
}

.btn-sync:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.sync-icon {
  font-size: 1rem;
  line-height: 1;
  display: inline-block;
}

.sync-icon--spinning {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.contacts-empty--setup {
  padding: var(--space-10) var(--space-4);
}

.contacts-empty-hint {
  margin-top: var(--space-2);
  font-size: var(--text-sm);
  color: var(--color-text-muted);
}

.setup-link {
  color: var(--app-primary);
  text-decoration: underline;
}
</style>
