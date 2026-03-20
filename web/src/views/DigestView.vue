<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useDigestStore, type DigestEntry, type DigestLink } from '../stores/digest'
import { useApiFetch } from '../composables/useApi'

const store = useDigestStore()

// Per-entry state keyed by DigestEntry.id
const expandedIds  = ref<Record<number, boolean>>({})
const linkResults  = ref<Record<number, DigestLink[]>>({})
const selectedUrls = ref<Record<number, Set<string>>>({})
const queueResult  = ref<Record<number, { queued: number; skipped: number } | null>>({})
const extracting   = ref<Record<number, boolean>>({})
const queuing      = ref<Record<number, boolean>>({})

onMounted(() => store.fetchAll())

function toggleExpand(id: number) {
  expandedIds.value = { ...expandedIds.value, [id]: !expandedIds.value[id] }
}

// Spread-copy pattern — same as expandedSignalIds in InterviewCard, safe for Vue 3 reactivity
function toggleUrl(entryId: number, url: string) {
  const prev = selectedUrls.value[entryId] ?? new Set<string>()
  const next = new Set(prev)
  next.has(url) ? next.delete(url) : next.add(url)
  selectedUrls.value = { ...selectedUrls.value, [entryId]: next }
}

function selectedCount(id: number) {
  return selectedUrls.value[id]?.size ?? 0
}

function jobLinks(id: number): DigestLink[] {
  return (linkResults.value[id] ?? []).filter(l => l.score >= 2)
}

function otherLinks(id: number): DigestLink[] {
  return (linkResults.value[id] ?? []).filter(l => l.score < 2)
}

async function extractLinks(entry: DigestEntry) {
  extracting.value = { ...extracting.value, [entry.id]: true }
  const { data } = await useApiFetch<{ links: DigestLink[] }>(
    `/api/digest-queue/${entry.id}/extract-links`,
    { method: 'POST' },
  )
  extracting.value = { ...extracting.value, [entry.id]: false }
  if (!data) return
  linkResults.value = { ...linkResults.value, [entry.id]: data.links }
  expandedIds.value = { ...expandedIds.value, [entry.id]: true }
  // Pre-check job-likely links (score >= 2)
  const preChecked = new Set(data.links.filter(l => l.score >= 2).map(l => l.url))
  selectedUrls.value = { ...selectedUrls.value, [entry.id]: preChecked }
  queueResult.value = { ...queueResult.value, [entry.id]: null }
}

async function queueJobs(entry: DigestEntry) {
  const urls = [...(selectedUrls.value[entry.id] ?? [])]
  if (!urls.length) return
  queuing.value = { ...queuing.value, [entry.id]: true }
  const { data } = await useApiFetch<{ queued: number; skipped: number }>(
    `/api/digest-queue/${entry.id}/queue-jobs`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ urls }),
    },
  )
  queuing.value = { ...queuing.value, [entry.id]: false }
  if (!data) return
  queueResult.value = { ...queueResult.value, [entry.id]: data }
  linkResults.value  = { ...linkResults.value,  [entry.id]: [] }
  expandedIds.value  = { ...expandedIds.value,  [entry.id]: false }
}

function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}
</script>

<template>
  <div class="digest-view">
    <h1 class="digest-heading">📰 Digest Queue</h1>

    <div v-if="store.entries.length === 0" class="digest-empty">
      <span class="empty-bird">🦅</span>
      <p>No digest emails queued.</p>
      <p class="empty-hint">When you mark an email as 📰 Digest, it appears here.</p>
    </div>

    <div v-else class="digest-list">
      <div v-for="entry in store.entries" :key="entry.id" class="digest-entry">

        <!-- Entry header row -->
        <div class="entry-header" @click="toggleExpand(entry.id)">
          <span class="entry-toggle" aria-hidden="true">{{ expandedIds[entry.id] ? '▾' : '▸' }}</span>
          <div class="entry-meta">
            <span class="entry-subject">{{ entry.subject }}</span>
            <span class="entry-from">
              <template v-if="entry.from_addr">From: {{ entry.from_addr }} · </template>
              {{ formatDate(entry.received_at) }}
            </span>
          </div>
          <div class="entry-actions" @click.stop>
            <button
              class="btn-extract"
              :disabled="extracting[entry.id]"
              :aria-label="linkResults[entry.id]?.length ? 'Re-extract links' : 'Extract job links'"
              @click="extractLinks(entry)"
            >
              {{ linkResults[entry.id]?.length ? 'Re-extract' : 'Extract' }}
            </button>
            <button
              class="btn-dismiss"
              aria-label="Remove from digest queue"
              @click="store.remove(entry.id)"
            >✕</button>
          </div>
        </div>

        <!-- Post-queue confirmation -->
        <div v-if="queueResult[entry.id]" class="queue-result">
          ✅ {{ queueResult[entry.id]!.queued }}
          job{{ queueResult[entry.id]!.queued !== 1 ? 's' : '' }} queued for review<template
            v-if="queueResult[entry.id]!.skipped > 0"
          >, {{ queueResult[entry.id]!.skipped }} skipped (already in pipeline)</template>
        </div>

        <!-- Expanded: link list -->
        <template v-if="expandedIds[entry.id]">
          <div v-if="extracting[entry.id]" class="entry-status">Extracting links…</div>

          <div v-else-if="linkResults[entry.id] !== undefined && !linkResults[entry.id]!.length" class="entry-status">
            No job links found in this email.
          </div>

          <div v-else-if="linkResults[entry.id]?.length" class="entry-links">
            <!-- Job-likely links (score ≥ 2), pre-checked -->
            <div class="link-group">
              <label
                v-for="link in jobLinks(entry.id)"
                :key="link.url"
                class="link-row"
              >
                <input
                  type="checkbox"
                  class="link-check"
                  :checked="selectedUrls[entry.id]?.has(link.url)"
                  @change="toggleUrl(entry.id, link.url)"
                />
                <div class="link-text">
                  <span v-if="link.hint" class="link-hint">{{ link.hint }}</span>
                  <span class="link-url">{{ link.url }}</span>
                </div>
              </label>
            </div>

            <!-- Other links (score = 1), unchecked -->
            <template v-if="otherLinks(entry.id).length">
              <div class="link-divider">Other links</div>
              <div class="link-group">
                <label
                  v-for="link in otherLinks(entry.id)"
                  :key="link.url"
                  class="link-row link-row--other"
                >
                  <input
                    type="checkbox"
                    class="link-check"
                    :checked="selectedUrls[entry.id]?.has(link.url)"
                    @change="toggleUrl(entry.id, link.url)"
                  />
                  <div class="link-text">
                    <span v-if="link.hint" class="link-hint">{{ link.hint }}</span>
                    <span class="link-url">{{ link.url }}</span>
                  </div>
                </label>
              </div>
            </template>

            <button
              class="btn-queue"
              :disabled="selectedCount(entry.id) === 0 || queuing[entry.id]"
              @click="queueJobs(entry)"
            >
              Queue {{ selectedCount(entry.id) > 0 ? selectedCount(entry.id) + ' ' : '' }}selected →
            </button>
          </div>
        </template>

      </div>
    </div>
  </div>
</template>

<style scoped>
.digest-view {
  padding: var(--space-6);
  max-width: 720px;
  margin: 0 auto;
}

.digest-heading {
  font-size: 1.25rem;
  font-weight: 700;
  color: var(--color-text);
  margin-bottom: var(--space-6);
}

/* Empty state */
.digest-empty {
  text-align: center;
  padding: var(--space-16) var(--space-8);
  color: var(--color-text-muted);
}
.empty-bird  { font-size: 2.5rem; display: block; margin-bottom: var(--space-4); }
.empty-hint  { font-size: 0.875rem; margin-top: var(--space-2); }

/* Entry list */
.digest-list { display: flex; flex-direction: column; gap: var(--space-3); }

.digest-entry {
  background: var(--color-surface-raised);
  border: 1px solid var(--color-border-light);
  border-radius: 10px;
  overflow: hidden;
}

/* Entry header */
.entry-header {
  display: flex;
  align-items: flex-start;
  gap: var(--space-3);
  padding: var(--space-4);
  cursor: pointer;
  user-select: none;
}
.entry-toggle { color: var(--color-text-muted); font-size: 0.9rem; flex-shrink: 0; padding-top: 2px; }

.entry-meta  { flex: 1; min-width: 0; }
.entry-subject {
  display: block;
  font-weight: 600;
  font-size: 0.9rem;
  color: var(--color-text);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.entry-from { display: block; font-size: 0.75rem; color: var(--color-text-muted); margin-top: 2px; }

.entry-actions { display: flex; gap: var(--space-2); flex-shrink: 0; }

.btn-extract {
  font-size: 0.75rem;
  padding: 3px 10px;
  border-radius: 5px;
  border: 1px solid var(--color-border);
  background: var(--color-surface-alt);
  color: var(--color-text);
  cursor: pointer;
  transition: border-color 0.1s, color 0.1s;
}
.btn-extract:hover:not(:disabled) { border-color: var(--color-primary); color: var(--color-primary); }
.btn-extract:disabled { opacity: 0.5; cursor: default; }

.btn-dismiss {
  font-size: 0.75rem;
  padding: 3px 8px;
  border-radius: 5px;
  border: 1px solid var(--color-border-light);
  background: transparent;
  color: var(--color-text-muted);
  cursor: pointer;
  transition: border-color 0.1s, color 0.1s;
}
.btn-dismiss:hover { border-color: var(--color-error); color: var(--color-error); }

/* Queue result */
.queue-result {
  margin: 0 var(--space-4) var(--space-3);
  font-size: 0.8rem;
  color: var(--color-success);
  background: color-mix(in srgb, var(--color-success) 10%, var(--color-surface-raised));
  border-radius: 6px;
  padding: var(--space-2) var(--space-3);
}

/* Status messages */
.entry-status {
  padding: var(--space-3) var(--space-4) var(--space-4);
  font-size: 0.8rem;
  color: var(--color-text-muted);
  font-style: italic;
}

/* Link list */
.entry-links { padding: 0 var(--space-4) var(--space-4); }
.link-group  { display: flex; flex-direction: column; gap: 2px; }

.link-row {
  display: flex;
  align-items: flex-start;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-3);
  border-radius: 6px;
  cursor: pointer;
  background: var(--color-surface);
  transition: background 0.1s;
}
.link-row:hover   { background: var(--color-surface-alt); }
.link-row--other  { opacity: 0.8; }

.link-check { flex-shrink: 0; margin-top: 3px; accent-color: var(--color-primary); cursor: pointer; }

.link-text  { min-width: 0; flex: 1; }
.link-hint  {
  display: block;
  font-size: 0.8rem;
  font-weight: 500;
  color: var(--color-text);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.link-url {
  display: block;
  font-size: 0.7rem;
  color: var(--color-text-muted);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.link-divider {
  font-size: 0.7rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--color-text-muted);
  padding: var(--space-3) 0 var(--space-2);
  border-top: 1px solid var(--color-border-light);
  margin-top: var(--space-2);
}

.btn-queue {
  margin-top: var(--space-3);
  width: 100%;
  padding: var(--space-2) var(--space-4);
  border-radius: 6px;
  border: none;
  background: var(--color-primary);
  color: var(--color-text-inverse);
  font-size: 0.875rem;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.1s;
}
.btn-queue:hover:not(:disabled) { background: var(--color-primary-hover); }
.btn-queue:disabled { opacity: 0.4; cursor: default; }

@media (max-width: 600px) {
  .digest-view { padding: var(--space-4); }
  .entry-subject { font-size: 0.85rem; }
}
</style>
