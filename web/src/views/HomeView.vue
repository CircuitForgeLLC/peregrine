<template>
  <div class="home">
    <!-- Header -->
    <header class="home__header">
      <div>
        <h1 class="home__greeting">
          {{ greeting }}
          <span v-if="isMidnight" aria-label="Late night session">🌙</span>
        </h1>
        <p class="home__subtitle">Discover → Review → Apply</p>
      </div>
    </header>

    <!-- Metric cards -->
    <section class="home__metrics" aria-label="Pipeline overview">
      <RouterLink
        v-for="metric in metrics"
        :key="metric.status"
        :to="metric.link"
        class="metric-card"
        :class="`metric-card--${metric.status}`"
        :aria-label="`${metric.count ?? 0} ${metric.label} jobs`"
      >
        <span class="metric-card__count" aria-hidden="true">
          {{ store.loading ? '—' : (metric.count ?? 0) }}
        </span>
        <span class="metric-card__label">{{ metric.label }}</span>
      </RouterLink>
    </section>

    <!-- Primary workflow -->
    <section class="home__section" aria-labelledby="workflow-heading">
      <h2 id="workflow-heading" class="home__section-title">Primary Workflow</h2>
      <div class="home__actions">
        <WorkflowButton
          emoji="🚀"
          label="Run Discovery"
          description="Scan job boards for new listings"
          :loading="taskRunning === 'discovery'"
          @click="runDiscovery"
        />
        <WorkflowButton
          emoji="📧"
          label="Sync Emails"
          description="Fetch and classify inbox"
          :loading="taskRunning === 'email'"
          @click="syncEmails"
        />
        <WorkflowButton
          emoji="📊"
          label="Score Unscored"
          description="Run match scoring on new jobs"
          :loading="taskRunning === 'score'"
          @click="scoreUnscored"
        />
      </div>

      <button
        v-if="unsyncedCount > 0"
        class="sync-banner"
        :disabled="taskRunning === 'sync'"
        :aria-busy="taskRunning === 'sync'"
        @click="syncIntegration"
      >
        <span aria-hidden="true">📤</span>
        <span>
          Sync {{ unsyncedCount }} approved {{ unsyncedCount === 1 ? 'job' : 'jobs' }}
          → {{ integrationName }}
        </span>
        <span v-if="taskRunning === 'sync'" class="spinner" aria-hidden="true" />
      </button>
    </section>

    <!-- Auto-enrichment status -->
    <section v-if="store.status?.enrichment_enabled" class="home__section">
      <div class="enrichment-row" role="status" aria-live="polite">
        <span class="enrichment-row__dot" :class="enrichmentDotClass" aria-hidden="true" />
        <span class="enrichment-row__text">
          {{ store.status?.enrichment_last_run
            ? `Last enriched ${formatRelative(store.status.enrichment_last_run)}`
            : 'Auto-enrichment active' }}
        </span>
        <button class="btn-ghost btn-ghost--sm" @click="runEnrich">Run Now</button>
      </div>
    </section>

    <!-- Backlog management -->
    <section v-if="showBacklog" class="home__section" aria-labelledby="backlog-heading">
      <h2 id="backlog-heading" class="home__section-title">Backlog Management</h2>
      <p class="home__section-desc">
        You have
        <strong>{{ store.counts?.pending ?? 0 }} pending</strong>
        and
        <strong>{{ store.counts?.approved ?? 0 }} approved</strong>
        listings.
      </p>
      <div class="home__actions home__actions--secondary">
        <button
          v-if="(store.counts?.pending ?? 0) > 0"
          class="action-btn action-btn--secondary"
          @click="archiveByStatus(['pending'])"
        >
          📦 Archive Pending
        </button>
        <button
          v-if="(store.counts?.rejected ?? 0) > 0"
          class="action-btn action-btn--secondary"
          @click="archiveByStatus(['rejected'])"
        >
          📦 Archive Rejected
        </button>
        <button
          v-if="(store.counts?.approved ?? 0) > 0"
          class="action-btn action-btn--secondary"
          @click="archiveByStatus(['approved'])"
        >
          📦 Archive Approved (unapplied)
        </button>
      </div>
    </section>

    <!-- Add jobs by URL -->
    <section class="home__section" aria-labelledby="add-heading">
      <h2 id="add-heading" class="home__section-title">Add Jobs by URL</h2>
      <div class="add-jobs">
        <div class="add-jobs__tabs" role="tablist">
          <button
            role="tab"
            :aria-selected="addTab === 'url'"
            class="add-jobs__tab"
            :class="{ 'add-jobs__tab--active': addTab === 'url' }"
            @click="addTab = 'url'"
          >Paste URLs</button>
          <button
            role="tab"
            :aria-selected="addTab === 'csv'"
            class="add-jobs__tab"
            :class="{ 'add-jobs__tab--active': addTab === 'csv' }"
            @click="addTab = 'csv'"
          >Upload CSV</button>
        </div>
        <div class="add-jobs__panel" role="tabpanel">
          <template v-if="addTab === 'url'">
            <textarea
              v-model="urlInput"
              class="add-jobs__textarea"
              placeholder="Paste one job URL per line…"
              rows="4"
              aria-label="Job URLs to add"
            />
            <button
              class="action-btn action-btn--primary"
              :disabled="!urlInput.trim()"
              @click="addByUrl"
            >Add Jobs</button>
          </template>
          <template v-else>
            <p class="home__section-desc">Upload a CSV with a <code>url</code> column.</p>
            <input type="file" accept=".csv" aria-label="CSV file" @change="handleCsvUpload" />
          </template>
        </div>
      </div>
    </section>

    <!-- Advanced -->
    <section class="home__section">
      <details class="advanced">
        <summary class="advanced__summary">Advanced</summary>
        <div class="advanced__body">
          <p class="advanced__warning">⚠️ These actions are destructive and cannot be undone.</p>
          <div class="home__actions home__actions--danger">
            <button class="action-btn action-btn--danger" @click="confirmPurge">
              🗑️ Purge Pending + Rejected
            </button>
            <button class="action-btn action-btn--danger" @click="killTasks">
              🛑 Kill Stuck Tasks
            </button>
          </div>
        </div>
      </details>
    </section>

    <!-- Stoop speed toast — easter egg 9.2 -->
    <Transition name="toast">
      <div v-if="stoopToast" class="stoop-toast" role="status" aria-live="polite">
        🦅 Stoop speed.
      </div>
    </Transition>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { RouterLink } from 'vue-router'
import { useJobsStore } from '../stores/jobs'
import { useApiFetch } from '../composables/useApi'
import WorkflowButton from '../components/WorkflowButton.vue'

const store = useJobsStore()

// Greeting — easter egg 9.7: midnight mode
const userName = ref('')
const hour = new Date().getHours()
const isMidnight = computed(() => hour >= 0 && hour < 5)
const greeting = computed(() => {
  const name = userName.value ? `${userName.value}'s` : 'Your'
  return isMidnight.value ? `${name} Late-Night Job Search` : `${name} Job Search`
})

const metrics = computed(() => [
  { status: 'pending', label: 'Pending',  count: store.counts?.pending,  link: '/review?status=pending'  },
  { status: 'approve', label: 'Approved', count: store.counts?.approved, link: '/review?status=approved' },
  { status: 'applied', label: 'Applied',  count: store.counts?.applied,  link: '/review?status=applied'  },
  { status: 'synced',  label: 'Synced',   count: store.counts?.synced,   link: '/review?status=synced'   },
  { status: 'reject',  label: 'Rejected', count: store.counts?.rejected, link: '/review?status=rejected' },
])

const integrationName = computed(() => store.status?.integration_name ?? 'Export')
const unsyncedCount   = computed(() => store.status?.integration_unsynced ?? 0)
const showBacklog     = computed(() => (store.counts?.pending ?? 0) > 0 || (store.counts?.approved ?? 0) > 0)

const enrichmentDotClass = computed(() =>
  store.status?.enrichment_last_run ? 'enrichment-row__dot--ok' : 'enrichment-row__dot--idle',
)

function formatRelative(isoStr: string) {
  const mins = Math.round((Date.now() - new Date(isoStr).getTime()) / 60000)
  if (mins < 2)  return 'just now'
  if (mins < 60) return `${mins} min ago`
  const hrs = Math.round(mins / 60)
  return hrs === 1 ? '1 hour ago' : `${hrs} hours ago`
}

const taskRunning = ref<string | null>(null)
const stoopToast  = ref(false)

async function runTask(key: string, endpoint: string) {
  taskRunning.value = key
  await useApiFetch(endpoint, { method: 'POST' })
  taskRunning.value = null
  store.refresh()
}

const runDiscovery    = () => runTask('discovery', '/api/tasks/discovery')
const syncEmails      = () => runTask('email', '/api/tasks/email-sync')
const scoreUnscored   = () => runTask('score', '/api/tasks/score')
const syncIntegration = () => runTask('sync', '/api/tasks/sync')
const runEnrich       = () => useApiFetch('/api/tasks/enrich', { method: 'POST' })

const addTab   = ref<'url' | 'csv'>('url')
const urlInput = ref('')

async function addByUrl() {
  const urls = urlInput.value.split('\n').map(u => u.trim()).filter(Boolean)
  await useApiFetch('/api/jobs/add', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ urls }),
  })
  urlInput.value = ''
  store.refresh()
}

function handleCsvUpload(e: Event) {
  const file = (e.target as HTMLInputElement).files?.[0]
  if (!file) return
  const form = new FormData()
  form.append('file', file)
  useApiFetch('/api/jobs/upload-csv', { method: 'POST', body: form })
}

async function archiveByStatus(statuses: string[]) {
  await useApiFetch('/api/jobs/archive', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ statuses }),
  })
  store.refresh()
}

function confirmPurge() {
  // TODO: replace with ConfirmModal component
  if (confirm('Permanently delete all pending and rejected jobs? This cannot be undone.')) {
    useApiFetch('/api/jobs/purge', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ target: 'pending_rejected' }),
    })
    store.refresh()
  }
}

async function killTasks() {
  await useApiFetch('/api/tasks/kill', { method: 'POST' })
}

onMounted(async () => {
  store.refresh()
  const { data } = await useApiFetch<{ name: string }>('/api/config/user')
  if (data?.name) userName.value = data.name
})
</script>

<style scoped>
.home {
  max-width: 900px;
  margin: 0 auto;
  padding: var(--space-8) var(--space-6);
  display: flex;
  flex-direction: column;
  gap: var(--space-8);
}

.home__header {
  padding-bottom: var(--space-4);
  border-bottom: 1px solid var(--color-border-light);
}

.home__greeting {
  font-family: var(--font-display);
  font-size: var(--text-3xl);
  color: var(--app-primary);
  line-height: 1.1;
}

.home__subtitle {
  margin-top: var(--space-2);
  color: var(--color-text-muted);
  font-size: var(--text-sm);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.home__metrics {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: var(--space-3);
}

.metric-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-1);
  padding: var(--space-4) var(--space-3);
  background: var(--color-surface-raised);
  border: 2px solid transparent;
  border-radius: var(--radius-lg);
  text-decoration: none;
  min-height: 44px;
  transition:
    border-color 150ms ease,
    box-shadow   150ms ease,
    transform    150ms ease;
}

.metric-card:hover {
  border-color: var(--app-primary-light);
  box-shadow: var(--shadow-md);
  transform: translateY(-1px);
}

.metric-card__count {
  font-family: var(--font-display);
  font-size: var(--text-2xl);
  font-weight: 700;
  line-height: 1;
}

.metric-card__label {
  font-size: var(--text-xs);
  color: var(--color-text-muted);
  text-transform: uppercase;
  letter-spacing: 0.06em;
}

.metric-card--pending .metric-card__count { color: var(--status-pending); }
.metric-card--approve .metric-card__count { color: var(--status-approve); }
.metric-card--applied .metric-card__count { color: var(--status-applied); }
.metric-card--synced  .metric-card__count { color: var(--status-synced); }
.metric-card--reject  .metric-card__count { color: var(--status-reject); }

.home__section { display: flex; flex-direction: column; gap: var(--space-4); }

.home__section-title {
  font-family: var(--font-display);
  font-size: var(--text-xl);
  color: var(--color-text);
}

.home__section-desc { font-size: var(--text-sm); color: var(--color-text-muted); }

.home__actions {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: var(--space-3);
}

.home__actions--secondary { grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); }
.home__actions--danger    { grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); }

.sync-banner {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-4) var(--space-5);
  background: var(--app-primary-light);
  border: 1px solid var(--app-primary);
  border-radius: var(--radius-md);
  color: var(--app-primary);
  font-size: var(--text-sm);
  font-weight: 600;
  cursor: pointer;
  width: 100%;
  text-align: left;
  transition: background 150ms ease, box-shadow 150ms ease;
}

.sync-banner:hover    { background: var(--color-surface-alt); box-shadow: var(--shadow-sm); }
.sync-banner:disabled { opacity: 0.6; cursor: not-allowed; }

.spinner {
  width: 1rem;
  height: 1rem;
  border: 2px solid currentColor;
  border-top-color: transparent;
  border-radius: 50%;
  animation: spin 0.7s linear infinite;
  margin-left: auto;
}

@keyframes spin { to { transform: rotate(360deg); } }

.action-btn {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-3) var(--space-5);
  border-radius: var(--radius-md);
  font-size: var(--text-sm);
  font-weight: 600;
  cursor: pointer;
  border: none;
  min-height: 44px;
  transition: background 150ms ease, box-shadow 150ms ease;
}

.action-btn--primary          { background: var(--app-accent); color: var(--app-accent-text); }
.action-btn--primary:hover    { background: var(--app-accent-hover); }
.action-btn--primary:disabled { opacity: 0.4; cursor: not-allowed; }

.action-btn--secondary       { background: var(--color-surface-alt); color: var(--color-text); border: 1px solid var(--color-border); }
.action-btn--secondary:hover { background: var(--color-border-light); }

.action-btn--danger       { background: transparent; color: var(--color-error); border: 1px solid var(--color-error); }
.action-btn--danger:hover { background: rgba(192, 57, 43, 0.08); }

.enrichment-row {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-3) var(--space-4);
  background: var(--color-surface-raised);
  border-radius: var(--radius-md);
  font-size: var(--text-sm);
  color: var(--color-text-muted);
}

.enrichment-row__dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.enrichment-row__dot--ok   { background: var(--color-success); }
.enrichment-row__dot--idle { background: var(--color-text-muted); }
.enrichment-row__text { flex: 1; }

.btn-ghost {
  background: transparent;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  color: var(--color-text-muted);
  cursor: pointer;
  transition: background 150ms ease, color 150ms ease;
}

.btn-ghost--sm   { padding: var(--space-1) var(--space-3); font-size: var(--text-xs); }
.btn-ghost:hover { background: var(--color-surface-alt); color: var(--color-text); }

.add-jobs {
  background: var(--color-surface-raised);
  border-radius: var(--radius-lg);
  border: 1px solid var(--color-border-light);
  overflow: hidden;
}

.add-jobs__tabs { display: flex; border-bottom: 1px solid var(--color-border-light); }

.add-jobs__tab {
  flex: 1;
  padding: var(--space-3) var(--space-4);
  border: none;
  border-bottom: 2px solid transparent;
  margin-bottom: -1px;
  background: transparent;
  font-size: var(--text-sm);
  color: var(--color-text-muted);
  cursor: pointer;
  transition: color 150ms ease, border-color 150ms ease;
}

.add-jobs__tab--active { color: var(--app-primary); border-bottom-color: var(--app-primary); font-weight: 600; }

.add-jobs__panel {
  padding: var(--space-4);
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.add-jobs__textarea {
  width: 100%;
  padding: var(--space-3);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  background: var(--color-surface);
  color: var(--color-text);
  font-family: var(--font-mono);
  font-size: var(--text-sm);
  resize: vertical;
}

.add-jobs__textarea:focus { outline: 2px solid var(--app-primary); outline-offset: 1px; }

.advanced {
  background: var(--color-surface-raised);
  border: 1px solid var(--color-border-light);
  border-radius: var(--radius-md);
}

.advanced__summary {
  padding: var(--space-3) var(--space-4);
  cursor: pointer;
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--color-text-muted);
  list-style: none;
  user-select: none;
}

.advanced__summary::-webkit-details-marker { display: none; }
.advanced__summary::before { content: '▶  '; font-size: 0.7em; }
details[open] > .advanced__summary::before { content: '▼  '; }

.advanced__body { padding: 0 var(--space-4) var(--space-4); display: flex; flex-direction: column; gap: var(--space-4); }

.advanced__warning {
  font-size: var(--text-sm);
  color: var(--color-warning);
  background: rgba(212, 137, 26, 0.08);
  padding: var(--space-3) var(--space-4);
  border-radius: var(--radius-md);
  border-left: 3px solid var(--color-warning);
}

.stoop-toast {
  position: fixed;
  bottom: var(--space-6);
  right: var(--space-6);
  background: var(--color-surface-raised);
  border: 1px solid var(--color-border);
  padding: var(--space-3) var(--space-5);
  border-radius: var(--radius-md);
  font-size: var(--text-sm);
  color: var(--color-text-muted);
  box-shadow: var(--shadow-lg);
  z-index: 200;
}

.toast-enter-active,
.toast-leave-active {
  transition: opacity 300ms ease, transform 300ms ease;
}

.toast-enter-from,
.toast-leave-to {
  opacity: 0;
  transform: translateY(8px);
}

@media (max-width: 768px) {
  .home { padding: var(--space-4); gap: var(--space-6); }
  .home__greeting { font-size: var(--text-2xl); }
  .home__metrics { grid-template-columns: repeat(3, 1fr); }
}

@media (max-width: 480px) {
  .home__metrics { grid-template-columns: repeat(2, 1fr); }
  .home__metrics .metric-card:last-child { grid-column: 1 / -1; }
}
</style>
