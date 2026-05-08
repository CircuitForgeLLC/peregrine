<!-- web/src/views/MessagingView.vue -->
<template>
  <div class="messaging-layout">
    <!-- Left panel: job list -->
    <aside class="job-panel" role="complementary" aria-label="Jobs with messages">
      <div class="job-panel__header">
        <h1 class="job-panel__title">Messages</h1>
      </div>
      <ul class="job-list" role="list" aria-label="Jobs">
        <li
          v-for="job in jobsWithMessages"
          :key="job.id"
          class="job-list__item"
          :class="{ 'job-list__item--active': selectedJobId === job.id }"
          role="listitem"
          :aria-label="`${job.company}, ${job.title}`"
        >
          <button class="job-list__btn" @click="selectJob(job.id)">
            <span class="job-list__company">{{ job.company }}</span>
            <span class="job-list__role">{{ job.title }}</span>
            <span v-if="job.preview" class="job-list__preview">{{ job.preview }}</span>
          </button>
        </li>
        <li v-if="jobsWithMessages.length === 0" class="job-list__empty">
          No messages yet. Select a job to log a call or use a template.
        </li>
      </ul>
    </aside>

    <!-- Right panel: thread view -->
    <main class="thread-panel" aria-label="Message thread">
      <div v-if="!selectedJobId" class="thread-panel__empty">
        <p>Select a job to view its communication timeline.</p>
      </div>

      <template v-else>
        <!-- Draft pending announcement (screen reader) -->
        <div aria-live="polite" aria-atomic="true" class="sr-only">{{ draftAnnouncement }}</div>

        <!-- Error banner -->
        <p v-if="store.error" class="thread-error" role="alert">{{ store.error }}</p>

        <!-- Timeline -->
        <div v-if="store.loading && timeline.length === 0" class="thread-loading">
          Loading messages…
        </div>
        <ul v-else class="timeline" role="list" aria-label="Message timeline">
          <li
            v-for="item in timeline"
            :key="item._key"
            class="timeline__item"
            :class="[
              `timeline__item--${item.type}`,
              item.approved_at === null && item.type === 'draft' ? 'timeline__item--draft-pending' : '',
              item.type !== 'draft' ? 'timeline__item--expandable' : '',
              expandedKeys.has(item._key) ? 'timeline__item--open' : '',
            ]"
            role="listitem"
            :aria-label="`${typeLabel(item.type)}, ${item.direction || ''}, ${item.logged_at}`"
            @click="item.type !== 'draft' && toggleExpand(item)"
          >
            <span class="timeline__icon" aria-hidden="true">{{ typeIcon(item.type) }}</span>
            <div class="timeline__content">
              <div class="timeline__meta">
                <span class="timeline__type-label">{{ typeLabel(item.type) }}</span>
                <span v-if="item.direction" class="timeline__direction">{{ item.direction }}</span>
                <time class="timeline__time">{{ formatTime(item.logged_at) }}</time>
                <span
                  v-if="item.type === 'draft' && item.approved_at === null"
                  class="timeline__badge timeline__badge--pending"
                >Pending approval</span>
                <span
                  v-if="item.type === 'draft' && item.approved_at !== null"
                  class="timeline__badge timeline__badge--approved"
                >Approved</span>
                <span v-if="item.type !== 'draft'" class="timeline__expand-hint" aria-hidden="true">
                  {{ expandedKeys.has(item._key) ? '▲' : '▼' }}
                </span>
              </div>
              <p v-if="item.subject" class="timeline__subject">{{ item.subject }}</p>

              <!-- Expandable body for non-draft items -->
              <template v-if="item.type !== 'draft' && expandedKeys.has(item._key)">
                <div class="timeline__body-wrap" @click.stop>
                  <div v-if="bodyCache[item.id] === null" class="timeline__body-loading">
                    Loading…
                  </div>
                  <pre v-else-if="bodyCache[item.id]" class="timeline__body">{{ bodyCache[item.id] }}</pre>
                  <p v-else class="timeline__body-empty">No body content.</p>
                </div>
              </template>

              <!-- Draft: editable textarea + actions -->
              <template v-if="item.type === 'draft' && item.approved_at === null">
                <textarea
                  :ref="el => setDraftRef(item.id, el)"
                  class="timeline__draft-body"
                  :value="item.body ?? ''"
                  @input="updateDraftBody(item.id, ($event.target as HTMLTextAreaElement).value)"
                  rows="6"
                  aria-label="Edit draft reply before approving"
                />
                <div class="timeline__draft-actions">
                  <button class="btn btn--primary btn--sm" @click="approveDraft(item.id)">
                    Approve + copy
                  </button>
                  <a
                    v-if="item.to_addr"
                    :href="`mailto:${item.to_addr}?subject=${encodeURIComponent(item.subject ?? '')}&body=${encodeURIComponent(item.body ?? '')}`"
                    class="btn btn--ghost btn--sm"
                    target="_blank" rel="noopener"
                  >Open in email client</a>
                  <button class="btn btn--ghost btn--sm btn--danger" @click="confirmDelete(item.id)">
                    Discard
                  </button>
                </div>
              </template>
            </div>
          </li>
          <li v-if="timeline.length === 0" class="timeline__empty">
            No messages logged yet for this job.
          </li>
        </ul>

        <!-- Compose bar (sticky footer) -->
        <div class="compose-bar" role="toolbar" aria-label="Compose actions">
          <div v-if="composing" class="compose-bar__actions">
            <button class="btn btn--ghost btn--sm" @click="triggerAction(() => openLogModal('call_note'))">Log call</button>
            <button class="btn btn--ghost btn--sm" @click="triggerAction(() => openLogModal('in_person'))">Log note</button>
            <button class="btn btn--ghost btn--sm" @click="triggerAction(() => openTemplateModal('apply'))">Use template</button>
            <button
              class="btn btn--primary btn--sm"
              :disabled="store.loading"
              @click="triggerAction(requestDraft)"
            >
              <span v-if="store.loading" class="btn__spinner" aria-hidden="true"></span>
              {{ store.loading ? 'Drafting…' : 'Draft reply with LLM' }}
            </button>
            <button
              class="btn btn--osprey btn--sm"
              aria-disabled="true"
              :title="ospreyTitle"
              @mouseenter="handleOspreyHover"
              @focus="handleOspreyHover"
            >📞 Call via Osprey</button>
          </div>
          <button
            class="btn compose-bar__toggle"
            :class="composing ? 'btn--ghost' : 'btn--primary'"
            @click="composing = !composing"
            :aria-expanded="composing"
            aria-controls="compose-actions"
          >{{ composing ? '✕ Close' : '＋ New' }}</button>
        </div>
      </template>
    </main>

    <!-- Modals -->
    <MessageLogModal
      :show="logModal.show"
      :job-id="selectedJobId ?? 0"
      :type="logModal.type"
      @close="logModal.show = false"
      @saved="onLogSaved"
    />

    <MessageTemplateModal
      :show="tplModal.show"
      :mode="tplModal.mode"
      :job-tokens="jobTokens"
      :edit-template="tplModal.editTemplate"
      @close="tplModal.show = false"
      @saved="onTemplateSaved"
    />

    <!-- Delete confirmation -->
    <div v-if="deleteConfirm !== null" class="modal-backdrop" @click.self="deleteConfirm = null">
      <div class="modal-dialog modal-dialog--sm" role="dialog" aria-modal="true" aria-label="Confirm delete">
        <div class="modal-body">
          <p>Are you sure you want to delete this message? This cannot be undone.</p>
          <div class="modal-footer">
            <button class="btn btn--ghost" @click="deleteConfirm = null">Cancel</button>
            <button class="btn btn--danger" @click="doDelete">Delete</button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { useMessagingStore, type MessageTemplate } from '../stores/messaging'
import { useApiFetch } from '../composables/useApi'
import MessageLogModal from '../components/MessageLogModal.vue'
import MessageTemplateModal from '../components/MessageTemplateModal.vue'

const store = useMessagingStore()

// ── Jobs list ──────────────────────────────────────────────────────────────

interface JobSummary { id: number; company: string; title: string; preview?: string }
const allJobs = ref<JobSummary[]>([])
const selectedJobId = ref<number | null>(null)

async function loadJobs() {
  const { data } = await useApiFetch<Array<{ id: number; company: string; title: string }>>('/api/jobs?status=applied&limit=200')
  allJobs.value = data ?? []
}

const jobsWithMessages = computed(() => allJobs.value)

async function selectJob(id: number) {
  selectedJobId.value = id
  draftBodyEdits.value = {}
  await store.fetchMessages(id)
}

// ── Timeline: UNION of job_contacts + messages ─────────────────────────────

interface TimelineItem {
  _key: string
  id: number
  type: 'call_note' | 'in_person' | 'email' | 'draft'
  direction: string | null
  subject: string | null
  body: string | null
  to_addr: string | null
  logged_at: string
  approved_at: string | null
}

interface JobContact {
  id: number
  direction: string | null
  subject: string | null
  from_addr: string | null
  to_addr: string | null
  body: string | null
  received_at: string | null
}

const jobContacts = ref<JobContact[]>([])

watch(selectedJobId, async (id) => {
  if (id === null) { jobContacts.value = []; return }
  const { data } = await useApiFetch<{ total: number; contacts: JobContact[] }>(`/api/contacts?job_id=${id}`)
  jobContacts.value = data?.contacts ?? []
})

const timeline = computed<TimelineItem[]>(() => {
  const contactItems: TimelineItem[] = jobContacts.value.map(c => ({
    _key: `jc-${c.id}`,
    id: c.id,
    type: 'email',
    direction: c.direction,
    subject: c.subject,
    body: c.body,
    to_addr: c.to_addr,
    logged_at: c.received_at ?? '',
    approved_at: 'n/a',   // contacts are always "approved"
  }))
  const messageItems: TimelineItem[] = store.messages.map(m => ({
    _key: `msg-${m.id}`,
    id: m.id,
    type: m.type,
    direction: m.direction,
    subject: m.subject,
    body: draftBodyEdits.value[m.id] ?? m.body,
    to_addr: m.to_addr,
    logged_at: m.logged_at,
    approved_at: m.approved_at,
  }))
  return [...contactItems, ...messageItems].sort(
    (a, b) => new Date(b.logged_at).getTime() - new Date(a.logged_at).getTime()
  )
})

// ── Body expansion ────────────────────────────────────────────────────────
const expandedKeys = ref(new Set<string>())
const bodyCache = ref<Record<number, string | null>>({})  // null = still loading

async function toggleExpand(item: TimelineItem) {
  const key = item._key
  const next = new Set(expandedKeys.value)
  if (next.has(key)) { next.delete(key); expandedKeys.value = next; return }
  next.add(key)
  expandedKeys.value = next
  if (key.startsWith('jc-') && !(item.id in bodyCache.value)) {
    bodyCache.value = { ...bodyCache.value, [item.id]: null }
    const { data } = await useApiFetch<{ body: string | null }>(`/api/contacts/${item.id}`)
    const raw = data?.body ?? ''
    const text = raw.trimStart().startsWith('<')
      ? (new DOMParser().parseFromString(raw, 'text/html').body.textContent ?? '').trim()
      : raw.trim()
    bodyCache.value = { ...bodyCache.value, [item.id]: text }
  }
}

// ── Compose bar ────────────────────────────────────────────────────────────
const composing = ref(false)
function triggerAction(fn: () => void) { composing.value = false; fn() }

// ── Draft body edits (local, before approve) ──────────────────────────────

const draftBodyEdits = ref<Record<number, string>>({})
const draftRefs = ref<Record<number, HTMLTextAreaElement | null>>({})

function setDraftRef(id: number, el: unknown) {
  draftRefs.value[id] = el as HTMLTextAreaElement | null
}

function updateDraftBody(id: number, value: string) {
  draftBodyEdits.value = { ...draftBodyEdits.value, [id]: value }
}

// ── LLM draft + approval ──────────────────────────────────────────────────

const draftAnnouncement = ref('')

async function requestDraft() {
  // Find the most recent inbound job_contact for this job
  const inbound = jobContacts.value.find(c => c.direction === 'inbound')
  if (!inbound) {
    store.error = 'No inbound emails found for this job to draft a reply to.'
    return
  }
  const msgId = await store.requestDraft(inbound.id)
  if (msgId) {
    draftAnnouncement.value = 'Draft reply generated and ready for review.'
    await store.fetchMessages(selectedJobId.value!)
    setTimeout(() => { draftAnnouncement.value = '' }, 3000)
  }
}

async function approveDraft(messageId: number) {
  const editedBody = draftBodyEdits.value[messageId]
  // Persist edits to DB before approving so history shows final version
  if (editedBody !== undefined) {
    const updated = await store.updateMessageBody(messageId, editedBody)
    if (!updated) return   // error already set in store
  }
  const body = await store.approveDraft(messageId)
  if (body) {
    const finalBody = editedBody ?? body
    await navigator.clipboard.writeText(finalBody)
    draftAnnouncement.value = 'Approved and copied to clipboard.'
    setTimeout(() => { draftAnnouncement.value = '' }, 3000)
  }
}

// ── Delete confirmation ───────────────────────────────────────────────────

const deleteConfirm = ref<number | null>(null)

function confirmDelete(id: number) {
  deleteConfirm.value = id
}

async function doDelete() {
  if (deleteConfirm.value === null) return
  await store.deleteMessage(deleteConfirm.value)
  deleteConfirm.value = null
}

// ── Osprey easter egg ─────────────────────────────────────────────────────

const OSPREY_HOVER_KEY = 'peregrine-osprey-hover-count'
const ospreyTitle = ref('Osprey IVR calling — coming in Phase 2')

function handleOspreyHover() {
  const count = parseInt(localStorage.getItem(OSPREY_HOVER_KEY) ?? '0', 10) + 1
  localStorage.setItem(OSPREY_HOVER_KEY, String(count))
  if (count >= 10) {
    ospreyTitle.value = "Osprey is still learning to fly... 🦅"
  }
}

// ── Modals ────────────────────────────────────────────────────────────────

const logModal = ref<{ show: boolean; type: 'call_note' | 'in_person' }>({
  show: false, type: 'call_note',
})

function openLogModal(type: 'call_note' | 'in_person') {
  logModal.value = { show: true, type }
}

function onLogSaved() {
  logModal.value.show = false
  if (selectedJobId.value) store.fetchMessages(selectedJobId.value)
}

const tplModal = ref<{
  show: boolean
  mode: 'apply' | 'create' | 'edit'
  editTemplate?: MessageTemplate
}>({ show: false, mode: 'apply' })

function openTemplateModal(mode: 'apply' | 'create' | 'edit', tpl?: MessageTemplate) {
  tplModal.value = { show: true, mode, editTemplate: tpl }
}

function onTemplateSaved() {
  tplModal.value.show = false
  store.fetchTemplates()
}

// ── Job tokens for template substitution ─────────────────────────────────

const jobTokens = computed<Record<string, string>>(() => {
  const job = allJobs.value.find(j => j.id === selectedJobId.value)
  return {
    company: job?.company ?? '',
    role: job?.title ?? '',
    name: '',            // loaded from user profile; left empty — user fills in
    recruiter_name: '',
    date: new Date().toLocaleDateString(),
    accommodation_details: '',
  }
})

// ── Helpers ───────────────────────────────────────────────────────────────

function typeIcon(type: string): string {
  return { call_note: '📞', in_person: '🤝', email: '✉️', draft: '📝' }[type] ?? '💬'
}

function typeLabel(type: string): string {
  return {
    call_note: 'Call note', in_person: 'In-person note',
    email: 'Email', draft: 'Draft reply',
  }[type] ?? type
}

function formatTime(iso: string): string {
  if (!iso) return ''
  return new Date(iso).toLocaleString(undefined, {
    month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit'
  })
}

// ── Lifecycle ─────────────────────────────────────────────────────────────

onMounted(async () => {
  await Promise.all([loadJobs(), store.fetchTemplates()])
})

onUnmounted(() => {
  store.clear()
})
</script>

<style scoped>
.messaging-layout {
  display: flex;
  height: 100dvh;
  min-height: 0;
  overflow: hidden;
}

@media (max-width: 1023px) {
  .messaging-layout {
    height: calc(100dvh - 56px - env(safe-area-inset-bottom, 0px));
  }
}

/* ── Left panel ─────────────────────── */
.job-panel {
  width: 260px;
  min-width: 200px;
  flex-shrink: 0;
  border-right: 1px solid var(--color-border);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.job-panel__header {
  padding: var(--space-4);
  border-bottom: 1px solid var(--color-border-light);
}
.job-panel__title { font-size: var(--text-lg); font-weight: 600; margin: 0; }
.job-list {
  flex: 1; overflow-y: auto;
  list-style: none; margin: 0; padding: var(--space-2) 0;
}
.job-list__item { margin: 0; }
.job-list__item--active .job-list__btn {
  background: var(--app-primary-light);
  color: var(--app-primary);
}
.job-list__btn {
  width: 100%; padding: var(--space-3) var(--space-4);
  text-align: left; background: none; border: none; cursor: pointer;
  display: flex; flex-direction: column; gap: 2px;
  transition: background 150ms;
}
.job-list__btn:hover { background: var(--color-surface-alt); }
.job-list__company { font-size: var(--text-sm); font-weight: 600; }
.job-list__role { font-size: var(--text-xs); color: var(--color-text-muted); }
.job-list__preview { font-size: var(--text-xs); color: var(--color-text-muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 220px; }
.job-list__empty { padding: var(--space-4); font-size: var(--text-sm); color: var(--color-text-muted); }

/* ── Right panel ────────────────────── */
.thread-panel {
  flex: 1; min-width: 0;
  display: flex; flex-direction: column;
  overflow: hidden;
}
.thread-panel__empty {
  flex: 1; display: flex; align-items: center; justify-content: center;
  color: var(--color-text-muted);
}
.btn--osprey {
  opacity: 0.5; cursor: not-allowed;
  background: none; border: 1px dashed var(--color-border);
  border-radius: var(--radius-md);
  color: var(--color-text-muted); font-size: var(--text-sm);
  padding: var(--space-2) var(--space-3); min-height: 36px;
}

/* Compose bar */
.compose-bar {
  flex-shrink: 0;
  display: flex; flex-direction: column; align-items: flex-end;
  gap: var(--space-2);
  padding: var(--space-3) var(--space-4);
  border-top: 1px solid var(--color-border-light);
  background: var(--color-surface);
}
.compose-bar__actions {
  display: flex; flex-wrap: wrap; gap: var(--space-2); align-items: center;
  width: 100%; justify-content: flex-start;
}
.compose-bar__toggle { align-self: flex-end; min-width: 90px; justify-content: center; }
.thread-error {
  margin: var(--space-2) var(--space-4);
  color: var(--app-accent); font-size: var(--text-sm);
}
.thread-loading { padding: var(--space-4); color: var(--color-text-muted); font-size: var(--text-sm); }
.timeline {
  flex: 1; overflow-y: auto;
  list-style: none; margin: 0; padding: var(--space-4);
  display: flex; flex-direction: column; gap: var(--space-3);
}
.timeline__item {
  display: flex; gap: var(--space-3);
  padding: var(--space-3); border-radius: var(--radius-md);
  background: var(--color-surface-alt);
  border: 1px solid var(--color-border);
}
.timeline__item--draft-pending {
  border-color: var(--app-accent);
  background: color-mix(in srgb, var(--app-accent) 8%, var(--color-surface));
}
.timeline__icon { font-size: 1.2rem; flex-shrink: 0; }
.timeline__content { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: var(--space-1); }
.timeline__meta { display: flex; align-items: center; gap: var(--space-2); flex-wrap: wrap; }
.timeline__type-label { font-size: var(--text-sm); font-weight: 600; }
.timeline__direction { font-size: var(--text-xs); color: var(--color-text-muted); text-transform: capitalize; }
.timeline__time { font-size: var(--text-xs); color: var(--color-text-muted); margin-left: auto; }
.timeline__badge {
  font-size: var(--text-xs); font-weight: 700;
  padding: 1px 6px; border-radius: var(--radius-full);
}
.timeline__badge--pending { background: var(--color-accent-light); color: var(--color-accent); }
.timeline__badge--approved { background: var(--color-primary-light); color: var(--color-primary); }
.timeline__subject { font-size: var(--text-sm); font-weight: 500; margin: 0; }
.timeline__expand-hint {
  font-size: var(--text-xs); color: var(--color-text-muted); margin-left: auto;
  transition: transform 150ms ease;
}
.timeline__item--expandable { cursor: pointer; }
.timeline__item--expandable:hover { border-color: var(--app-primary); }
.timeline__body-wrap {
  margin-top: var(--space-2);
  border-top: 1px solid var(--color-border-light);
  padding-top: var(--space-2);
}
.timeline__body {
  font-size: var(--text-sm); white-space: pre-wrap; margin: 0;
  color: var(--color-text); max-height: 280px; overflow-y: auto;
  font-family: var(--font-body);
}
.timeline__body-loading { font-size: var(--text-xs); color: var(--color-text-muted); }
.timeline__body-empty { font-size: var(--text-xs); color: var(--color-text-muted); margin: 0; }
.timeline__draft-body {
  width: 100%; font-size: var(--text-sm); font-family: var(--font-body);
  padding: var(--space-2); border: 1px solid var(--color-border);
  border-radius: var(--radius-md); background: var(--color-surface);
  color: var(--color-text); resize: vertical;
}
.timeline__draft-body:focus-visible { outline: 2px solid var(--app-primary); outline-offset: 2px; }
.timeline__draft-actions { display: flex; gap: var(--space-2); flex-wrap: wrap; }
.timeline__empty { color: var(--color-text-muted); font-size: var(--text-sm); padding: var(--space-2); }

/* Buttons */
.btn {
  padding: var(--space-2) var(--space-3);
  border-radius: var(--radius-md);
  font-size: var(--text-sm);
  font-weight: 500;
  cursor: pointer;
  min-height: 36px;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  transition: background 120ms ease, border-color 120ms ease, opacity 120ms ease, transform 80ms ease;
}
.btn:active:not(:disabled) { transform: translateY(1px); }
.btn:focus-visible { outline: 2px solid var(--app-primary); outline-offset: 2px; }
.btn--sm { padding: var(--space-1) var(--space-3); min-height: 30px; font-size: var(--text-xs); }
.btn--primary { background: var(--app-primary); color: var(--color-surface); border: none; }
.btn--primary:hover:not(:disabled) { opacity: 0.88; }
.btn--primary:disabled { opacity: 0.5; cursor: not-allowed; }
.btn--ghost { background: none; border: 1px solid var(--color-border); color: var(--color-text); }
.btn--ghost:hover:not(:disabled) { background: var(--color-surface-alt); border-color: var(--app-primary); color: var(--app-primary); }
.btn--danger { background: var(--app-accent); color: var(--app-accent-text); border: none; }
.btn--danger:hover:not(:disabled) { opacity: 0.88; }

/* Spinner inside buttons */
.btn__spinner {
  width: 13px;
  height: 13px;
  border: 2px solid rgba(255,255,255,0.35);
  border-top-color: white;
  border-radius: 50%;
  animation: btn-spin 0.65s linear infinite;
  flex-shrink: 0;
}
@keyframes btn-spin { to { transform: rotate(360deg); } }

/* Modals (delete confirm) */
.modal-backdrop {
  position: fixed; inset: 0;
  background: var(--color-overlay);
  display: flex; align-items: center; justify-content: center;
  z-index: 200;
}
.modal-dialog {
  background: var(--color-surface-raised); border: 1px solid var(--color-border);
  border-radius: var(--radius-lg); width: min(400px, 95vw); outline: none;
}
.modal-dialog--sm { width: min(360px, 95vw); }
.modal-body { padding: var(--space-5); display: flex; flex-direction: column; gap: var(--space-4); }
.modal-footer { display: flex; justify-content: flex-end; gap: var(--space-3); }

/* Screen-reader only utility */
.sr-only {
  position: absolute; width: 1px; height: 1px;
  padding: 0; margin: -1px; overflow: hidden;
  clip: rect(0,0,0,0); white-space: nowrap; border: 0;
}

/* Responsive: stack panels on narrow screens */
@media (max-width: 700px) {
  .messaging-layout { flex-direction: column; }
  .job-panel { width: 100%; border-right: none; border-bottom: 1px solid var(--color-border); max-height: 180px; }
}
</style>
