<template>
  <section class="gcs" aria-labelledby="gcs-heading">
    <h4 id="gcs-heading" ref="headingEl" tabindex="-1" class="gcs__heading">A few questions before the rewrite</h4>
    <p v-if="loading || loadError || batch.length > 0" class="gcs__intro">
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
      <div v-if="savedGroup.length > 0" class="gcs__saved">
        <div class="gcs__toggle">
          <input id="gcs-use-saved" v-model="useSaved" type="checkbox" :disabled="savedSent || saving" />
          <label for="gcs-use-saved">{{ savedLabel }}</label>
        </div>
        <p v-if="savedSent" class="gcs__note">{{ useSaved ? 'These are already saved for this job.' : 'Not used for this job.' }}</p>
        <details class="gcs__details">
          <summary>See my saved answers</summary>
          <ul class="gcs__rows">
            <li v-for="c in savedGroup" :key="c.term" class="gcs__row">
              <span class="gcs__term">{{ c.term }}</span>
              <span class="gcs__wording">{{ c.suggestion?.text }}</span>
            </li>
          </ul>
        </details>
      </div>

      <details v-if="notUsable.length > 0" class="gcs__details gcs__skipped">
        <summary>Answered, not used ({{ notUsable.length }})</summary>
        <ul class="gcs__rows">
          <li v-for="c in notUsable" :key="c.term" class="gcs__row">
            <span class="gcs__term">{{ c.term }}</span>
            <span class="gcs__wording">{{ plainAnswer(c) }}</span>
            <button type="button" class="gcs__btn gcs__btn--small" :disabled="saving" @click="promote(c)">
              Change<span class="sr-only"> {{ c.term }}</span>
            </button>
          </li>
        </ul>
      </details>

      <div class="gcs__list" :inert="saving || undefined">
        <GapCard
          v-for="(card, i) in batch"
          :key="card.term"
          :ref="(el) => setCardRef(card.term, el)"
          :card="card"
          :index="i"
          :state="states[card.term]"
          @update="(s: CardState) => update(card.term, s)"
        />
      </div>

      <p v-if="batch.length > 0" class="gcs__progress" role="status" aria-live="polite">
        {{ answeredCount }} of {{ batch.length }} answered.
        <span v-if="remaining > 0" class="gcs__more-note">{{ moreSentence }}</span>
      </p>

      <div v-if="saveError" class="gcs__error" role="alert">
        <p>We could not save your answers. What you typed is still here.</p>
        <p v-if="saveDetail">{{ saveDetail }}</p>
      </div>

      <div class="gcs__actions">
        <button type="button" class="gcs__btn gcs__btn--primary" :disabled="!canSave || saving" @click="save(false)">
          {{ mainLabel }}
        </button>
        <button v-if="remaining > 0" type="button" class="gcs__btn" :disabled="!canSave || saving" @click="save(true)">
          {{ moreButtonLabel }}
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
import { CARD_BATCH_SIZE } from './gapCardsConfig'

const props = defineProps<{ jobId: number; terms: string[]; drafts?: Record<string, CardState> }>()
const emit = defineEmits<{
  (e: 'done', approved: string[]): void
  (e: 'cancel'): void
  (e: 'drafts-change', drafts: Record<string, CardState>): void
}>()

const saveDetail = ref('')
const headingEl = ref<HTMLElement | null>(null)
/** Which button the person last pressed, so Retry and Saving show on that one only. */
const lastAdvance = ref(false)

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

/** Keywords with an exact saved answer that documents may use. They get one toggle, not a card each. */
const savedGroup = ref<CardData[]>([])
/** Keywords with an exact "have not done" or private answer. Listed, never approved unless changed. */
const notUsable = ref<CardData[]>([])
/** The not-used keywords in the order they were first shown, so a returned one goes back to its place. */
const notUsableOrder = ref<string[]>([])
/** Every keyword that still needs an answer, in priority order. Cards are shown a batch at a time. */
const queue = ref<CardData[]>([])
const shownCount = ref(0)
/** The cards on screen now: the current batch, plus any keyword the person chose to change. */
const batch = ref<CardData[]>([])
/** Typed answers by keyword, for every keyword that can get a card. */
const states = ref<Record<string, CardState>>({})
const promoted = ref<Set<string>>(new Set())
const useSaved = ref(true)
const savedSent = ref(false)
const approved = ref<string[]>([])
const cardEls = new Map<string, { focusLegend: () => void }>()
const loading = ref(true)
const loadError = ref(false)
const saving = ref(false)
const saveError = ref(false)

function setCardRef(term: string, el: unknown) {
  if (el) cardEls.set(term, el as { focusLegend: () => void })
  else cardEls.delete(term)
}

function initialState(card: CardData): CardState {
  const s = card.suggestion
  // A fact saved for a related keyword is only a hint. It is never preselected or prefilled.
  if (!s || !s.exact) return { choice: 'skip', text: '', private: false }
  if (s.kind === 'none') return { choice: 'no', text: '', private: false }
  // Only a keyword the person chose to change reaches here with an exact answer, and that answer is
  // "no" or private. An exact usable answer is never a card, so the 'reuse' choice below stays unused.
  const isPrivate = s.visibility === 'private'
  const kindChoice: Choice = s.kind === 'adjacent' ? 'similar' : 'yes'
  return { choice: isPrivate ? kindChoice : 'reuse', text: s.text, private: isPrivate }
}

type Group = 'saved' | 'notUsable' | 'unanswered'
function groupOf(card: CardData): Group {
  const s = card.suggestion
  if (!s || !s.exact) return 'unanswered'
  if (s.kind === 'none' || s.visibility === 'private') return 'notUsable'
  if ((s.kind === 'experience' || s.kind === 'adjacent') && s.visibility === 'document') return 'saved'
  return 'unanswered'
}

function focusCard(term: string) {
  nextTick(() => cardEls.get(term)?.focusLegend())
}

async function load() {
  loading.value = true; loadError.value = false; saveDetail.value = ''
  const { data, error } = await useApiFetch<{ cards: CardData[] }>(`/api/jobs/${props.jobId}/gap_cards`, {
    method: 'POST',
    body: JSON.stringify({ terms: props.terms }),
    headers: { 'Content-Type': 'application/json' },
  })
  if (error || !data) { loadError.value = true; saveDetail.value = error ? detailFrom(error) : ''; loading.value = false; return }
  savedGroup.value = data.cards.filter((c) => groupOf(c) === 'saved')
  notUsable.value = data.cards.filter((c) => groupOf(c) === 'notUsable')
  notUsableOrder.value = notUsable.value.map((c) => c.term)
  queue.value = data.cards.filter((c) => groupOf(c) === 'unanswered')
  states.value = Object.fromEntries(queue.value.map((c) => [c.term, props.drafts?.[c.term] ?? initialState(c)]))
  useSaved.value = true; savedSent.value = false; approved.value = []; promoted.value = new Set()
  batch.value = queue.value.slice(0, CARD_BATCH_SIZE)
  shownCount.value = batch.value.length
  loading.value = false
  await nextTick()
  if (batch.value.length > 0) cardEls.get(batch.value[0].term)?.focusLegend()
  else headingEl.value?.focus()
}

function update(term: string, s: CardState) {
  states.value = { ...states.value, [term]: s }
  emit('drafts-change', { ...states.value })
}

function promote(card: CardData) {
  // A save in flight owns the batch. A click that gets past the disabled button must not change it.
  if (saving.value) return
  notUsable.value = notUsable.value.filter((c) => c.term !== card.term)
  states.value = { ...states.value, [card.term]: props.drafts?.[card.term] ?? initialState(card) }
  promoted.value = new Set([...promoted.value, card.term])
  batch.value = [...batch.value, card]
  focusCard(card.term)
}

const remaining = computed(() => queue.value.length - shownCount.value)
/** A changed keyword whose answer is still the old one is left out of the save and the count. */
function isUntouched(card: CardData): boolean {
  if (!promoted.value.has(card.term)) return false
  const a = states.value[card.term]
  const b = initialState(card)
  return !!a && a.choice === b.choice && a.text === b.text && a.private === b.private
}
const answeredCount = computed(() =>
  batch.value.filter((c) => states.value[c.term]?.choice !== 'skip' && !isUntouched(c)).length,
)
const canSave = computed(() =>
  batch.value.every((c) => {
    const s = states.value[c.term]
    return !s || !['reuse', 'yes', 'similar'].includes(s.choice) || s.text.trim().length > 0
  }),
)

const savedLabel = computed(() => {
  const n = savedGroup.value.length
  return `Use my ${n} saved ${n === 1 ? 'answer' : 'answers'}`
})
const moreLabel = computed(() =>
  remaining.value <= CARD_BATCH_SIZE
    ? `Save and ask about the last ${remaining.value}`
    : `Save and ask about the next ${CARD_BATCH_SIZE} (${remaining.value} more)`,
)
const mainLabel = computed(() => {
  if (!lastAdvance.value && saveError.value) return 'Retry saving'
  if (!lastAdvance.value && saving.value) return 'Saving…'
  return 'Save answers and continue'
})
const moreButtonLabel = computed(() => {
  if (lastAdvance.value && saveError.value) return 'Retry saving'
  if (lastAdvance.value && saving.value) return 'Saving…'
  return moreLabel.value
})
const moreSentence = computed(() =>
  remaining.value === 1
    ? 'There is 1 more keyword you can answer after this.'
    : `There are ${remaining.value} more keywords you can answer after this.`,
)

function plainAnswer(card: CardData): string {
  return card.suggestion?.kind === 'none' ? 'You said you have not done this' : 'Saved as private'
}

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

/** The saved group is an unedited reused card when the toggle is on, and a skip when it is off. */
function savedAnswer(card: CardData) {
  const state: CardState = useSaved.value
    ? { choice: 'reuse', text: card.suggestion?.text ?? '', private: false }
    : { choice: 'skip', text: '', private: false }
  return toAnswer(card, state)
}

/** A changed keyword left as it was is not saved, so it goes back to the not-used list as it was shown. */
function returnUntouchedPromoted() {
  const untouched = batch.value.filter(isUntouched)
  if (untouched.length === 0) return
  const back = new Set(untouched.map((c) => c.term))
  const order = notUsableOrder.value
  notUsable.value = [...notUsable.value, ...untouched].sort((a, b) => order.indexOf(a.term) - order.indexOf(b.term))
  promoted.value = new Set([...promoted.value].filter((t) => !back.has(t)))
}

async function showNextBatch() {
  returnUntouchedPromoted()
  batch.value = queue.value.slice(shownCount.value, shownCount.value + CARD_BATCH_SIZE)
  shownCount.value += batch.value.length
  await nextTick()
  if (batch.value.length > 0) cardEls.get(batch.value[0].term)?.focusLegend()
}

/** advance true saves the batch and shows the next one. false saves and hands every approved term on. */
async function save(advance: boolean) {
  lastAdvance.value = advance
  saving.value = true; saveError.value = false; saveDetail.value = ''
  const sendSaved = !savedSent.value && savedGroup.value.length > 0
  const answers = [
    ...(sendSaved ? savedGroup.value.map(savedAnswer) : []),
    ...batch.value.filter((c) => !isUntouched(c)).map((c) => toAnswer(c, states.value[c.term])),
  ]
  let returned: string[] = []
  if (answers.length > 0) {
    const { data, error } = await useApiFetch<{ approved_terms: string[]; saved: number }>(
      `/api/jobs/${props.jobId}/gap_cards/answers`,
      { method: 'POST', body: JSON.stringify({ answers }), headers: { 'Content-Type': 'application/json' } },
    )
    if (error || !data) {
      saving.value = false; saveError.value = true; saveDetail.value = error ? detailFrom(error) : ''
      return
    }
    returned = data.approved_terms
  }
  saving.value = false
  if (sendSaved) savedSent.value = true
  approved.value = [...new Set([...approved.value, ...returned])]
  if (advance) await showNextBatch()
  else emit('done', approved.value)
}

onMounted(load)
</script>

<style scoped>
.gcs { display: flex; flex-direction: column; gap: var(--space-3); padding: var(--space-4); border: 1px solid var(--color-border); border-radius: var(--radius-md); background: var(--color-surface); }
.gcs__heading { margin: 0; color: var(--color-text); }
.gcs__intro, .gcs__hint, .gcs__status { margin: 0; color: var(--color-text-muted); }
.gcs__list { display: flex; flex-direction: column; gap: var(--space-3); }
.gcs__progress { margin: 0; font-weight: 600; color: var(--color-text); }
.gcs__more-note { font-weight: 400; color: var(--color-text-muted); }
.gcs__error { border: 1px solid var(--color-error); border-left-width: 4px; border-radius: var(--radius-sm); padding: var(--space-2) var(--space-3); color: var(--color-text); }
.gcs__error p { margin: 0 0 var(--space-2); }
.gcs__saved { display: flex; flex-direction: column; gap: var(--space-2); padding: var(--space-3) var(--space-4); border: 1px solid var(--color-border); border-left: 4px solid var(--color-info); border-radius: var(--radius-md); background: var(--color-surface-raised); }
.gcs__toggle { display: flex; align-items: center; gap: var(--space-2); min-height: 2.25rem; font-weight: 600; color: var(--color-text); }
.gcs__toggle label { cursor: pointer; }
.gcs__note { margin: 0; color: var(--color-text-muted); font-size: 0.9rem; }
.gcs__details { color: var(--color-text); }
.gcs__details summary { cursor: pointer; min-height: 2.25rem; display: flex; align-items: center; }
.gcs__skipped { padding: var(--space-2) var(--space-4); border: 1px solid var(--color-border); border-radius: var(--radius-md); background: var(--color-surface-raised); }
.gcs__rows { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: var(--space-2); }
.gcs__row { display: flex; flex-wrap: wrap; align-items: center; gap: var(--space-2); min-width: 0; }
.gcs__term { font-weight: 700; overflow-wrap: anywhere; }
.gcs__wording { color: var(--color-text-muted); white-space: pre-wrap; overflow-wrap: anywhere; flex: 1 1 12rem; min-width: 0; }
.gcs__actions { display: flex; flex-wrap: wrap; gap: var(--space-2); }
.gcs__btn { min-height: 2.5rem; padding: var(--space-2) var(--space-4); border: 1px solid var(--color-border); border-radius: var(--radius-md); background: var(--color-surface-raised); color: var(--color-text); font: inherit; cursor: pointer; }
.gcs__btn--small { min-height: 2.25rem; padding: var(--space-1) var(--space-3); }
.gcs__btn--primary { background: var(--color-primary); color: var(--color-text-inverse); border-color: var(--color-primary); font-weight: 600; }
.gcs__btn:disabled { opacity: 0.6; cursor: not-allowed; }
.gcs__btn:focus-visible, .gcs__details summary:focus-visible, .gcs__toggle input:focus-visible { outline: 2px solid var(--color-primary); outline-offset: 2px; }
</style>
