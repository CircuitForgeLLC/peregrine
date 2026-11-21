<template>
  <fieldset class="gc">
    <legend ref="legendEl" class="gc__legend" tabindex="-1">{{ card.term }}</legend>
    <p v-if="card.snippet" class="gc__snippet">
      <span class="gc__snippet-label">In the job description:</span> {{ card.snippet }}
    </p>
    <p v-if="note" class="gc__note">{{ note }}</p>

    <div class="gc__choices">
      <label v-if="canReuse" class="gc__choice">
        <input type="radio" :name="name" value="reuse" :checked="state.choice === 'reuse'" @change="setChoice('reuse')" />
        <span>Use this again</span>
      </label>
      <label class="gc__choice">
        <input type="radio" :name="name" value="yes" :checked="state.choice === 'yes'" @change="setChoice('yes')" />
        <span>Yes, I have done this</span>
      </label>
      <label class="gc__choice">
        <input type="radio" :name="name" value="similar" :checked="state.choice === 'similar'" @change="setChoice('similar')" />
        <span>Something similar</span>
      </label>
      <label class="gc__choice">
        <input type="radio" :name="name" value="no" :checked="state.choice === 'no'" @change="setChoice('no')" />
        <span>No, not something I have done</span>
      </label>
      <label class="gc__choice">
        <input type="radio" :name="name" value="skip" :checked="state.choice === 'skip'" @change="setChoice('skip')" />
        <span>Skip for now</span>
      </label>
    </div>

    <div v-if="hasText" class="gc__text">
      <label :for="`${name}-text`" class="gc__label">{{ textLabel }}</label>
      <textarea
        :id="`${name}-text`"
        class="gc__textarea"
        rows="3"
        maxlength="2000"
        :value="state.text"
        @input="onText(($event.target as HTMLTextAreaElement).value)"
      />
      <label class="gc__choice">
        <input
          type="checkbox"
          :checked="state.private"
          :aria-describedby="`${name}-private-help`"
          @change="onPrivate(($event.target as HTMLInputElement).checked)"
        />
        <span>Keep this private</span>
      </label>
      <p :id="`${name}-private-help`" class="gc__help">Private means this is saved for you but never used in your documents.</p>
    </div>
  </fieldset>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'

export interface CardSuggestion { id: number; kind: string; text: string; visibility: string }
export interface CardData { term: string; snippet: string; suggestion: CardSuggestion | null }
export type Choice = 'reuse' | 'yes' | 'similar' | 'no' | 'skip'
export interface CardState { choice: Choice; text: string; private: boolean }

const props = defineProps<{ card: CardData; state: CardState; index: number }>()
const emit = defineEmits<{ (e: 'update', state: CardState): void }>()

const legendEl = ref<HTMLElement | null>(null)
const name = computed(() => `gap-card-${props.index}`)
const sug = computed(() => props.card.suggestion)
const canReuse = computed(() => !!sug.value && sug.value.kind !== 'none' && sug.value.visibility !== 'private')
const hasText = computed(() => ['reuse', 'yes', 'similar'].includes(props.state.choice))
const textLabel = computed(() =>
  props.state.choice === 'similar' ? 'What is the similar experience?' : 'What did you do? Your own words are best.',
)
const note = computed(() => {
  if (!sug.value) return ''
  if (sug.value.kind === 'none') return 'You told us before that you have not done this. Change it if that is no longer true.'
  if (sug.value.visibility === 'private') return 'Saved as private'
  return ''
})

function setChoice(choice: Choice) { emit('update', { ...props.state, choice }) }
function onText(text: string) { emit('update', { ...props.state, text }) }
function onPrivate(value: boolean) { emit('update', { ...props.state, private: value }) }
function focusLegend() { legendEl.value?.focus() }
defineExpose({ focusLegend })
</script>

<style scoped>
.gc {
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  background: var(--color-surface-raised);
  padding: var(--space-3) var(--space-4);
  margin: 0;
  min-width: 0;
}
.gc__legend { font-weight: 700; color: var(--color-text); padding: 0 var(--space-2); overflow-wrap: anywhere; }
.gc__legend:focus-visible { outline: 2px solid var(--color-primary); outline-offset: 2px; }
.gc__snippet, .gc__note, .gc__help { margin: var(--space-2) 0; color: var(--color-text-muted); font-size: 0.9rem; }
.gc__note { border-left: 3px solid var(--color-info); padding-left: var(--space-2); color: var(--color-text); }
.gc__choices { display: flex; flex-direction: column; gap: var(--space-1); }
.gc__choice { display: flex; align-items: center; gap: var(--space-2); min-height: 2.25rem; cursor: pointer; color: var(--color-text); }
.gc__text { display: flex; flex-direction: column; gap: var(--space-2); margin-top: var(--space-3); }
.gc__label { font-weight: 600; color: var(--color-text); }
.gc__textarea {
  width: 100%;
  box-sizing: border-box;
  font: inherit;
  padding: var(--space-2);
  color: var(--color-text);
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
}
.gc__textarea:focus-visible, .gc input:focus-visible { outline: 2px solid var(--color-primary); outline-offset: 2px; }
</style>
