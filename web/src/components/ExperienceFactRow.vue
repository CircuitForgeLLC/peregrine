<template>
  <li class="fact" :class="{ 'fact--busy': busy }">
    <h3 class="fact__req">{{ fact.requirement }}</h3>
    <p v-if="fact.kind !== 'none' && !editing" class="fact__text">{{ fact.text }}</p>

    <p class="fact__badges">
      <span class="fact__badge">{{ kindLabel }}</span>
      <span class="fact__badge">{{ fact.visibility === 'private' ? 'Private' : 'Used in documents' }}</span>
    </p>

    <p v-if="error && !editing" class="fact__error" role="alert">{{ error }}</p>

    <div v-if="editing" class="fact__editor">
      <label :for="`fact-text-${fact.id}`" class="sr-only">Your words for {{ fact.requirement }}</label>
      <textarea
        :id="`fact-text-${fact.id}`"
        ref="textareaEl"
        v-model="draft"
        class="fact__textarea"
        maxlength="2000"
        rows="4"
      />
      <p v-if="error" class="fact__error" role="alert">{{ error }}</p>
      <div class="fact__actions">
        <button type="button" class="fact__btn fact__btn--primary" :aria-label="`Save: ${fact.requirement}`" :disabled="busy" @click="doSave">Save</button>
        <button type="button" class="fact__btn" :aria-label="`Cancel: ${fact.requirement}`" @click="closeEditor">Cancel</button>
      </div>
    </div>

    <div v-else class="fact__actions">
      <button v-if="fact.kind !== 'none'" ref="editBtn" type="button" class="fact__btn" :aria-label="`Edit: ${fact.requirement}`" :disabled="busy" @click="openEditor">Edit</button>
      <label v-if="fact.kind !== 'none'" class="fact__switch">
        <input
          type="checkbox"
          :aria-label="`Keep private: ${fact.requirement}`"
          :checked="fact.visibility === 'private'"
          :disabled="busy"
          @change="onToggle"
        />
        <span>Keep private</span>
      </label>
      <button v-if="!confirming" ref="deleteBtn" type="button" class="fact__btn" :aria-label="`Delete: ${fact.requirement}`" :disabled="busy" @click="confirming = true">Delete</button>
    </div>

    <div v-if="confirming && !editing" class="fact__confirm" @keydown.esc="cancelConfirm">
      <p>Delete removes it for good. You cannot undo this.</p>
      <div class="fact__actions">
        <button type="button" class="fact__btn fact__btn--danger" :aria-label="`Yes, delete it: ${fact.requirement}`" :disabled="busy" @click="onRemove">Yes, delete it</button>
        <button type="button" class="fact__btn" :aria-label="`Keep it: ${fact.requirement}`" @click="cancelConfirm">Keep it</button>
      </div>
    </div>
  </li>
</template>

<script setup lang="ts">
import { computed, nextTick, ref } from 'vue'

export interface ExperienceFact {
  id: number
  kind: 'experience' | 'adjacent' | 'none'
  requirement: string
  text: string
  visibility: 'document' | 'private'
  status: string
  created_at: string
}

const props = defineProps<{
  fact: ExperienceFact
  busy: boolean
  /** Resolves to an error sentence, or '' when the save worked. */
  save: (fact: ExperienceFact, text: string) => Promise<string>
  toggle: (fact: ExperienceFact, makePrivate: boolean) => Promise<string>
  remove: (fact: ExperienceFact) => Promise<string>
}>()

const KIND_LABELS = { experience: 'Done it', adjacent: 'Something similar', none: 'Have not done' } as const
const kindLabel = computed(() => KIND_LABELS[props.fact.kind])

const editing = ref(false)
const confirming = ref(false)
const draft = ref('')
const error = ref('')
const deleteBtn = ref<HTMLButtonElement | null>(null)
const textareaEl = ref<HTMLTextAreaElement | null>(null)
const editBtn = ref<HTMLButtonElement | null>(null)

async function openEditor() {
  draft.value = props.fact.text
  error.value = ''
  confirming.value = false
  editing.value = true
  await nextTick()
  textareaEl.value?.focus()
}

async function closeEditor() {
  editing.value = false
  error.value = ''
  await nextTick()
  editBtn.value?.focus()
}

async function doSave() {
  error.value = ''
  const err = await props.save(props.fact, draft.value)
  if (err) { error.value = err; return }
  await closeEditor()
}

async function onToggle(e: Event) {
  const el = e.target as HTMLInputElement
  error.value = ''
  const err = await props.toggle(props.fact, el.checked)
  if (err) { el.checked = !el.checked; error.value = err }
}

async function cancelConfirm() {
  confirming.value = false
  await nextTick()
  deleteBtn.value?.focus()
}

async function onRemove() {
  error.value = ''
  const err = await props.remove(props.fact)
  if (err) error.value = err
}
</script>

<style scoped>
.fact { list-style: none; display: flex; flex-direction: column; gap: var(--space-2); padding: var(--space-3) var(--space-4); border: 1px solid var(--color-border); border-radius: var(--radius-md); background: var(--color-surface-raised); }
.fact__req { margin: 0; min-width: 0; font-size: 1rem; color: var(--color-text); overflow-wrap: anywhere; }
.fact__text { margin: 0; color: var(--color-text); white-space: pre-wrap; overflow-wrap: anywhere; }
.fact__badges { display: flex; flex-wrap: wrap; gap: var(--space-2); margin: 0; }
.fact__badge { padding: 0 var(--space-2); border: 1px solid var(--color-border); border-radius: var(--radius-full); font-size: 0.85rem; color: var(--color-text-muted); }
.fact__editor, .fact__confirm { display: flex; flex-direction: column; gap: var(--space-2); }
.fact__confirm p { margin: 0; color: var(--color-text); }
.fact__textarea { width: 100%; box-sizing: border-box; padding: var(--space-2); border: 1px solid var(--color-border); border-radius: var(--radius-sm); background: var(--color-surface); color: var(--color-text); font: inherit; }
.fact__textarea:focus-visible { outline: 2px solid var(--color-primary); outline-offset: 2px; }
.fact__error { margin: 0; padding: var(--space-2) var(--space-3); border: 1px solid var(--color-error); border-left-width: 4px; border-radius: var(--radius-sm); color: var(--color-text); overflow-wrap: anywhere; }
.fact__actions { display: flex; flex-wrap: wrap; align-items: center; gap: var(--space-2); }
.fact__btn { min-height: 2.5rem; padding: var(--space-2) var(--space-4); border: 1px solid var(--color-border); border-radius: var(--radius-md); background: var(--color-surface); color: var(--color-text); font: inherit; cursor: pointer; }
.fact__btn--primary { background: var(--color-primary); color: var(--color-text-inverse); border-color: var(--color-primary); font-weight: 600; }
.fact__btn--danger { border-color: var(--color-error); font-weight: 600; }
.fact__btn:disabled { opacity: 0.6; cursor: not-allowed; }
.fact__btn:focus-visible, .fact__switch input:focus-visible { outline: 2px solid var(--color-primary); outline-offset: 2px; }
.fact__switch { display: inline-flex; align-items: center; gap: var(--space-2); min-height: 2.5rem; color: var(--color-text); cursor: pointer; }
.fact__switch input { width: 1.25rem; height: 1.25rem; }
</style>
