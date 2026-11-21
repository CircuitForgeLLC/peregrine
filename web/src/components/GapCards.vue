<template>
  <section class="gcs" aria-labelledby="gcs-heading">
    <h4 id="gcs-heading" class="gcs__heading">A few questions before the rewrite</h4>
    <p class="gcs__intro">
      For each keyword, tell us in your own words if you have done it. We only write about what you back up.
      "No" and "Skip for now" are fine answers.
    </p>

    <p v-if="loading" class="gcs__status" role="status">Loading your questions…</p>

    <div v-else-if="loadError" class="gcs__error" role="alert">
      <p>We could not load the questions. Nothing was lost.</p>
      <p v-if="saveDetail">{{ saveDetail }}</p>
      <button type="button" class="gcs__btn" @click="load">Retry</button>
    </div>

    <template v-else>
      <div class="gcs__list">
        <GapCard
          v-for="(card, i) in cards"
          :key="card.term"
          ref="cardRefs"
          :card="card"
          :index="i"
          :state="states[i]"
          @update="(s: CardState) => update(i, s)"
        />
      </div>

      <p class="gcs__progress" role="status" aria-live="polite">{{ answeredCount }} of {{ cards.length }} answered</p>

      <div v-if="saveError" class="gcs__error" role="alert">
        <p>We could not save your answers. What you typed is still here.</p>
        <p v-if="saveDetail">{{ saveDetail }}</p>
      </div>

      <div class="gcs__actions">
        <button type="button" class="gcs__btn gcs__btn--primary" :disabled="!canSave || saving" @click="save">
          {{ saveError ? 'Retry saving' : saving ? 'Saving…' : 'Save answers and continue' }}
        </button>
        <button type="button" class="gcs__btn" @click="emit('cancel')">Back</button>
      </div>
      <p v-if="!canSave" class="gcs__hint">Add a few words to each Yes or Similar answer, or choose another option.</p>
    </template>
  </section>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, ref } from 'vue'
import { useApiFetch } from '../composables/useApi'
import GapCard from './GapCard.vue'
import type { CardData, CardState, Choice } from './GapCard.vue'

const props = defineProps<{ jobId: number; terms: string[]; drafts?: Record<string, CardState> }>()
const emit = defineEmits<{
  (e: 'done', approved: string[]): void
  (e: 'cancel'): void
  (e: 'drafts-change', drafts: Record<string, CardState>): void
}>()

const saveDetail = ref('')

// A 422 carries a plain-language message from the server. Other failures use our fixed sentence.
function detailFrom(error: { kind: string; status?: number; detail?: string }): string {
  if (error.kind !== 'http' || error.status !== 422 || !error.detail) return ''
  try {
    const parsed = JSON.parse(error.detail)
    return typeof parsed?.detail === 'string' ? parsed.detail : ''
  } catch {
    return error.detail.trim().slice(0, 300)
  }
}

const cards = ref<CardData[]>([])
const states = ref<CardState[]>([])
const cardRefs = ref<Array<{ focusLegend: () => void }>>([])
const loading = ref(true)
const loadError = ref(false)
const saving = ref(false)
const saveError = ref(false)

function initialState(card: CardData): CardState {
  const s = card.suggestion
  if (!s) return { choice: 'skip', text: '', private: false }
  if (s.kind === 'none') return { choice: 'no', text: '', private: false }
  const isPrivate = s.visibility === 'private'
  const kindChoice: Choice = s.kind === 'adjacent' ? 'similar' : 'yes'
  return { choice: isPrivate ? kindChoice : 'reuse', text: s.text, private: isPrivate }
}

async function load() {
  loading.value = true; loadError.value = false
  const { data, error } = await useApiFetch<{ cards: CardData[] }>(`/api/jobs/${props.jobId}/gap_cards`, {
    method: 'POST',
    body: JSON.stringify({ terms: props.terms }),
    headers: { 'Content-Type': 'application/json' },
  })
  if (error || !data) { loadError.value = true; saveDetail.value = error ? detailFrom(error) : ''; loading.value = false; return }
  cards.value = data.cards
  states.value = data.cards.map((c) => props.drafts?.[c.term] ?? initialState(c))
  loading.value = false
  await nextTick()
  cardRefs.value[0]?.focusLegend()
}

function update(i: number, s: CardState) {
  states.value = states.value.map((old, idx) => (idx === i ? s : old))
  emit('drafts-change', Object.fromEntries(cards.value.map((c, idx) => [c.term, states.value[idx]])))
}

const answeredCount = computed(() => states.value.filter((s) => s.choice !== 'skip').length)
const canSave = computed(() =>
  states.value.every((s) => !['reuse', 'yes', 'similar'].includes(s.choice) || s.text.trim().length > 0),
)

function toAnswer(card: CardData, s: CardState) {
  const base = { term: card.term, text: '', private: false, use_saved_fact_id: null as number | null }
  if (s.choice === 'skip' || s.choice === 'no') return { ...base, choice: s.choice }
  const sug = card.suggestion
  if (s.choice === 'reuse' && sug) {
    const choice = sug.kind === 'adjacent' ? 'similar' : 'yes'
    const unedited = s.text === sug.text && !s.private
    return unedited
      ? { ...base, choice, use_saved_fact_id: sug.id }
      : { ...base, choice, text: s.text.trim(), private: s.private }
  }
  const choice = s.choice === 'reuse' ? 'yes' : s.choice
  return { ...base, choice, text: s.text.trim(), private: s.private }
}

async function save() {
  saving.value = true; saveError.value = false; saveDetail.value = ''
  const answers = cards.value.map((c, i) => toAnswer(c, states.value[i]))
  const { data, error } = await useApiFetch<{ approved_terms: string[]; saved: number }>(
    `/api/jobs/${props.jobId}/gap_cards/answers`,
    { method: 'POST', body: JSON.stringify({ answers }), headers: { 'Content-Type': 'application/json' } },
  )
  saving.value = false
  if (error || !data) { saveError.value = true; saveDetail.value = error ? detailFrom(error) : ''; return }
  emit('done', data.approved_terms)
}

onMounted(load)
</script>

<style scoped>
.gcs { display: flex; flex-direction: column; gap: var(--space-3); padding: var(--space-4); border: 1px solid var(--color-border); border-radius: var(--radius-md); background: var(--color-surface); }
.gcs__heading { margin: 0; color: var(--color-text); }
.gcs__intro, .gcs__hint, .gcs__status { margin: 0; color: var(--color-text-muted); }
.gcs__list { display: flex; flex-direction: column; gap: var(--space-3); }
.gcs__progress { margin: 0; font-weight: 600; color: var(--color-text); }
.gcs__error { border: 1px solid var(--color-error); border-left-width: 4px; border-radius: var(--radius-sm); padding: var(--space-2) var(--space-3); color: var(--color-text); }
.gcs__error p { margin: 0 0 var(--space-2); }
.gcs__actions { display: flex; flex-wrap: wrap; gap: var(--space-2); }
.gcs__btn { min-height: 2.5rem; padding: var(--space-2) var(--space-4); border: 1px solid var(--color-border); border-radius: var(--radius-md); background: var(--color-surface-raised); color: var(--color-text); font: inherit; cursor: pointer; }
.gcs__btn--primary { background: var(--color-primary); color: var(--color-text-inverse); border-color: var(--color-primary); font-weight: 600; }
.gcs__btn:disabled { opacity: 0.6; cursor: not-allowed; }
.gcs__btn:focus-visible { outline: 2px solid var(--color-primary); outline-offset: 2px; }
</style>
