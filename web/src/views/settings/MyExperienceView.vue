<template>
  <div class="mex">
    <h1 ref="titleEl" tabindex="-1" class="mex__title">My Experience</h1>
    <div class="mex__intro">
      <p>This page lists what you have told us about your experience, in your own words. It is saved only in your own account.</p>
      <p>"Private" means it is saved for you but never used in documents. Nothing here is used in a document unless it is marked "Used in documents".</p>
      <p>"Keep private" stops an answer being used in documents. "Delete" removes it for good.</p>
    </div>

    <p class="sr-only" role="status" aria-live="polite">{{ announcement }}</p>

    <p v-if="loading" class="mex__muted" role="status">Loading your experience...</p>
    <div v-else-if="loadError" class="mex__error" role="alert">
      <p>We could not load your saved experience.</p>
      <button type="button" class="mex__retry" @click="load">Retry</button>
    </div>
    <p v-else-if="facts.length === 0" class="mex__muted">
      You have not saved any experience yet. Answers you give when the resume optimizer asks about a keyword appear here.
    </p>

    <template v-else>
      <section v-for="g in groups" :key="g.key" class="mex__group" :aria-labelledby="`mex-h-${g.key}`">
        <h2 :id="`mex-h-${g.key}`" :ref="(el) => setHeading(g.key, el)" tabindex="-1" class="mex__heading">{{ g.title }}</h2>
        <ul class="mex__list">
          <ExperienceFactRow
            v-for="f in g.items"
            :key="f.id"
            :fact="f"
            :busy="busyId === f.id"
            :save="saveText"
            :toggle="toggleVisibility"
            :remove="removeFact"
          />
        </ul>
      </section>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, ref } from 'vue'
import ExperienceFactRow from '../../components/ExperienceFactRow.vue'
import type { ExperienceFact } from '../../components/ExperienceFactRow.vue'
import { useApiFetch } from '../../composables/useApi'
import type { ApiError } from '../../composables/useApi'

const FAILED = 'That did not work, so nothing was changed.'
const DEMO = 'This is a demo, so changes are not saved.'

const facts = ref<ExperienceFact[]>([])
const loading = ref(true)
const loadError = ref(false)
const busyId = ref<number | null>(null)
const announcement = ref('')
const titleEl = ref<HTMLElement | null>(null)
const headings: Record<string, HTMLElement | null> = {}

function setHeading(key: string, el: unknown) { headings[key] = (el as HTMLElement | null) ?? null }

const newestFirst = (a: ExperienceFact, b: ExperienceFact) =>
  b.created_at.localeCompare(a.created_at) || b.id - a.id

const groups = computed(() => {
  const shared = facts.value.filter((f) => f.kind !== 'none').sort(newestFirst)
  const none = facts.value.filter((f) => f.kind === 'none').sort(newestFirst)
  return [
    { key: 'shared', title: 'Experience you have shared', items: shared },
    { key: 'none', title: 'Things you told us you have not done', items: none },
  ].filter((g) => g.items.length > 0)
})

function detailFrom(error: ApiError): string {
  if (error.kind !== 'http' || !error.detail) return ''
  try {
    const parsed = JSON.parse(error.detail)
    return typeof parsed?.detail === 'string' ? parsed.detail : ''
  } catch {
    return error.detail.trim().slice(0, 300)
  }
}

function replaceFact(updated: ExperienceFact) {
  facts.value = facts.value.map((f) => (f.id === updated.id ? updated : f))
}

async function load() {
  loading.value = true
  loadError.value = false
  const { data, error } = await useApiFetch<ExperienceFact[]>('/api/experience-facts')
  if (error || !Array.isArray(data)) loadError.value = true
  else facts.value = data
  loading.value = false
}

/** Runs one write. Returns the parsed result, or null after setting the error message. */
async function write<T>(fact: ExperienceFact, url: string, init: RequestInit): Promise<{ data: T | null; message: string }> {
  busyId.value = fact.id
  const { data, error } = await useApiFetch<T>(url, init)
  busyId.value = null
  if (!error) return { data, message: '' }
  if (error.kind === 'demo-blocked') return { data: null, message: DEMO }
  const detail = detailFrom(error)
  return { data: null, message: detail ? `${FAILED} ${detail}` : FAILED }
}

function patch(fact: ExperienceFact, body: Record<string, string>) {
  return write<ExperienceFact>(fact, `/api/experience-facts/${fact.id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}

async function saveText(fact: ExperienceFact, text: string): Promise<string> {
  const { data, message } = await patch(fact, { text })
  if (message || !data) return message || FAILED
  replaceFact(data)
  announcement.value = `Saved your words for ${fact.requirement}.`
  return ''
}

async function toggleVisibility(fact: ExperienceFact, makePrivate: boolean): Promise<string> {
  const { data, message } = await patch(fact, { visibility: makePrivate ? 'private' : 'document' })
  if (message || !data) return message || FAILED
  replaceFact(data)
  announcement.value = makePrivate
    ? `${fact.requirement} is now private.`
    : `${fact.requirement} will be used in documents.`
  return ''
}

/** Moves focus to the heading of the group the fact was in, or the page heading if that group is gone. */
async function focusGroupHeading(fact: ExperienceFact) {
  const key = fact.kind === 'none' ? 'none' : 'shared'
  await nextTick()
  const stillThere = groups.value.some((g) => g.key === key)
  ;((stillThere ? headings[key] : null) ?? titleEl.value)?.focus()
}

async function removeFact(fact: ExperienceFact): Promise<string> {
  const { data, message } = await write<unknown>(fact, `/api/experience-facts/${fact.id}`, { method: 'DELETE' })
  if (message || data === null) return message || FAILED
  facts.value = facts.value.filter((f) => f.id !== fact.id)
  announcement.value = `Deleted ${fact.requirement}.`
  await focusGroupHeading(fact)
  return ''
}

onMounted(load)
</script>

<style scoped>
.mex { display: flex; flex-direction: column; gap: var(--space-4); max-width: 48rem; }
.mex__title, .mex__heading { margin: 0; color: var(--color-text); }
.mex__heading { font-size: 1.15rem; }
.mex__intro { display: flex; flex-direction: column; gap: var(--space-2); color: var(--color-text-muted); }
.mex__intro p, .mex__muted { margin: 0; }
.mex__muted { color: var(--color-text-muted); }
.mex__group { display: flex; flex-direction: column; gap: var(--space-3); }
.mex__list { display: flex; flex-direction: column; gap: var(--space-3); margin: 0; padding: 0; }
.mex__error { margin: 0; padding: var(--space-2) var(--space-3); border: 1px solid var(--color-error); border-left-width: 4px; border-radius: var(--radius-sm); color: var(--color-text); overflow-wrap: anywhere; }
.mex__error p { margin: 0 0 var(--space-2); }
.mex__retry { min-height: 2.5rem; padding: var(--space-2) var(--space-4); border: 1px solid var(--color-border); border-radius: var(--radius-md); background: var(--color-surface); color: var(--color-text); font: inherit; cursor: pointer; }
.mex__retry:focus-visible, .mex__heading:focus-visible, .mex__title:focus-visible { outline: 2px solid var(--color-primary); outline-offset: 2px; }
</style>
