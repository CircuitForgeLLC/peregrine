<script setup lang="ts">
// Shared AI profile-builder chat UI — used at /wizard/ai-profile, reached
// either as a standalone settings entry point or via the "Set up with AI"
// option on the onboarding choice step (SetupPathChoiceView.vue).
//
// The caller owns the tier gate and any outer container/heading; this
// component owns only the conversation itself and emits `saved` once the
// profile has been finalized — the caller decides what happens next.
import { ref, nextTick, onMounted, watch } from 'vue'
import { useAiInterviewStore } from '../stores/wizard/aiInterview'

const emit = defineEmits<{ saved: [] }>()

const store = useAiInterviewStore()

const inputText   = ref('')
const messageList = ref<HTMLElement | null>(null)

const TOTAL_FIELDS = 8

const progressPct = () => Math.min(100, (Object.keys(store.fields).length / TOTAL_FIELDS) * 100)

const TONE_CHIPS = [
  'Professional and direct',
  'Warm and conversational',
  'Concise and clear',
  'Enthusiastic and personable',
]

function showToneChips(): boolean {
  return store.askingAbout === 'candidate_voice'
}

// Human review before save. "LLMs are drafts, never decisions" — the chat's
// completion panel used to just say "ready to save" with no visibility into
// what was actually extracted, so the user (especially the LLM-authored
// career_summary prose) never got a real look before it was written. Every
// field is editable right here; what's shown is exactly what gets saved.
interface ReviewFieldDef {
  fieldName: string
  label: string
  type: 'text' | 'textarea' | 'list' | 'boolean'
}

const REVIEW_FIELDS: ReviewFieldDef[] = [
  { fieldName: 'name', label: 'Full name', type: 'text' },
  { fieldName: 'email', label: 'Email', type: 'text' },
  { fieldName: 'career_summary', label: 'Career summary', type: 'textarea' },
  { fieldName: 'candidate_voice', label: 'Preferred writing tone', type: 'text' },
  { fieldName: 'mission_preferences', label: 'Industries / causes you care about', type: 'list' },
  { fieldName: 'candidate_accessibility_focus', label: 'Research accessibility culture', type: 'boolean' },
  { fieldName: 'candidate_lgbtq_focus', label: 'Research LGBTQIA+ inclusion', type: 'boolean' },
  { fieldName: 'linkedin', label: 'LinkedIn URL', type: 'text' },
]

function reviewFieldsPresent(): ReviewFieldDef[] {
  return REVIEW_FIELDS.filter(f => {
    const v = store.fields[f.fieldName]
    return v !== undefined && v !== null && v !== '' &&
      !(Array.isArray(v) && v.length === 0)
  })
}

function listFieldText(fieldName: string): string {
  const v = store.fields[fieldName]
  return Array.isArray(v) ? v.join(', ') : ''
}

function setListField(fieldName: string, text: string) {
  store.fields[fieldName] = text.split(',').map(s => s.trim()).filter(Boolean)
}

async function scrollToBottom() {
  await nextTick()
  if (messageList.value) {
    messageList.value.scrollTop = messageList.value.scrollHeight
  }
}

watch(() => store.messages.length, () => scrollToBottom())

async function handleSend() {
  const text = inputText.value.trim()
  if (!text || store.loading) return
  inputText.value = ''
  await store.send(text)
}

function handleKeydown(e: KeyboardEvent) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    handleSend()
  }
}

function applyToneChip(chip: string) {
  inputText.value = chip
}

const justSaved = ref(false)

async function handleSave() {
  const ok = await store.finalize()
  if (ok) {
    justSaved.value = true
    emit('saved')
  }
}

onMounted(async () => {
  store.restore()
  if (store.messages.length === 0) {
    await store.send('')
  }
  scrollToBottom()
})
</script>

<template>
  <div class="ai-chat">
    <header class="ai-chat__header">
      <h1 class="ai-chat__title">Set up your profile with AI</h1>
      <p class="ai-chat__subtitle">I'll ask you a few questions. You can skip anything.</p>

      <!-- Progress bar -->
      <div class="ai-progress" role="progressbar"
        :aria-valuenow="Object.keys(store.fields).length"
        :aria-valuemax="TOTAL_FIELDS"
        aria-label="Profile fields completed">
        <div class="ai-progress__bar" :style="{ width: progressPct() + '%' }"></div>
      </div>
      <p class="ai-progress__label">
        {{ Object.keys(store.fields).length }} of {{ TOTAL_FIELDS }} fields captured
      </p>
    </header>

    <!-- Message list -->
    <div class="ai-messages" ref="messageList">
      <div
        v-for="(msg, idx) in store.messages"
        :key="idx"
        class="ai-bubble"
        :class="msg.role === 'user' ? 'ai-bubble--user' : 'ai-bubble--assistant'"
      >
        <span class="ai-bubble__text">{{ msg.content }}</span>
      </div>
      <div v-if="store.loading" class="ai-bubble ai-bubble--assistant ai-bubble--typing">
        <span class="ai-typing-dots" aria-label="Thinking">
          <span></span><span></span><span></span>
        </span>
      </div>
    </div>

    <!-- Completion panel -->
    <div v-if="justSaved" class="ai-complete ai-complete--saved">
      <p class="ai-complete__msg">✓ Profile saved.</p>
    </div>
    <div v-else-if="store.complete" class="ai-complete">
      <p class="ai-complete__msg">Review what I've gathered before saving — edit anything that's off.</p>

      <div class="ai-review" role="group" aria-label="Review profile before saving">
        <div v-for="field in reviewFieldsPresent()" :key="field.fieldName" class="ai-review__field">
          <label class="ai-review__label" :for="`ai-review-${field.fieldName}`">{{ field.label }}</label>

          <textarea
            v-if="field.type === 'textarea'"
            :id="`ai-review-${field.fieldName}`"
            v-model="(store.fields[field.fieldName] as string)"
            class="ai-review__textarea"
            rows="3"
          />
          <input
            v-else-if="field.type === 'text'"
            :id="`ai-review-${field.fieldName}`"
            v-model="(store.fields[field.fieldName] as string)"
            type="text"
            class="ai-review__input"
          />
          <input
            v-else-if="field.type === 'list'"
            :id="`ai-review-${field.fieldName}`"
            :value="listFieldText(field.fieldName)"
            @input="setListField(field.fieldName, ($event.target as HTMLInputElement).value)"
            type="text"
            class="ai-review__input"
            placeholder="Comma-separated"
          />
          <label v-else-if="field.type === 'boolean'" class="ai-review__checkbox-label">
            <input
              :id="`ai-review-${field.fieldName}`"
              v-model="(store.fields[field.fieldName] as boolean)"
              type="checkbox"
              class="ai-review__checkbox"
            />
            <span>{{ store.fields[field.fieldName] ? 'Yes' : 'No' }}</span>
          </label>
        </div>
      </div>

      <div class="ai-complete__actions">
        <button
          class="btn-primary"
          :disabled="store.saving"
          @click="handleSave"
        >
          {{ store.saving ? 'Saving…' : 'Save Profile' }}
        </button>
        <button
          class="btn-ghost"
          :disabled="store.loading || store.saving"
          @click="store.keepChatting()"
        >
          Keep chatting
        </button>
      </div>
    </div>

    <!-- Input area -->
    <div class="ai-input-area">
      <!-- Tone chips -->
      <div v-if="showToneChips()" class="ai-tone-chips" role="group" aria-label="Writing tone suggestions">
        <button
          v-for="chip in TONE_CHIPS"
          :key="chip"
          class="ai-tone-chip"
          @click="applyToneChip(chip)"
        >{{ chip }}</button>
      </div>

      <div class="ai-input-row">
        <textarea
          v-model="inputText"
          class="ai-input"
          placeholder="Type your answer…"
          rows="2"
          :disabled="store.loading || store.saving"
          @keydown="handleKeydown"
          aria-label="Chat input"
        ></textarea>
        <div class="ai-input-btns">
          <button
            class="btn-primary ai-send-btn"
            :disabled="store.loading || store.saving || !inputText.trim()"
            @click="handleSend"
          >
            Send
          </button>
          <button
            class="btn-ghost ai-skip-btn"
            :disabled="store.loading || store.saving || store.complete"
            @click="store.skip()"
          >
            Skip
          </button>
        </div>
      </div>

      <p v-if="store.error" class="ai-error" role="alert">{{ store.error }}</p>

      <div v-if="store.messages.length > 0" class="ai-startover-row">
        <button class="btn-startover" @click="store.startOver()">Start over</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* ── Chat container ────────────────────────────────── */
.ai-chat {
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

/* ── Header ────────────────────────────────────────── */
.ai-chat__header {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.ai-chat__title {
  font-family: var(--font-display);
  font-size: 1.375rem;
  font-weight: 700;
  color: var(--color-primary);
  margin: 0;
}

.ai-chat__subtitle {
  font-size: 0.9rem;
  color: var(--color-text-muted);
  margin: 0;
}

/* ── Progress bar ──────────────────────────────────── */
.ai-progress {
  height: 6px;
  background: var(--color-border-light);
  border-radius: var(--radius-full);
  overflow: hidden;
}

.ai-progress__bar {
  height: 100%;
  background: var(--color-primary);
  border-radius: var(--radius-full);
  transition: width 0.4s ease;
}

.ai-progress__label {
  font-size: 0.78rem;
  color: var(--color-text-muted);
  margin: 0;
}

/* ── Message list ──────────────────────────────────── */
.ai-messages {
  flex: 1;
  min-height: 320px;
  max-height: 480px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  padding: var(--space-4);
  background: var(--color-surface-raised);
  border: 1px solid var(--color-border-light);
  border-radius: var(--radius-lg);
  scroll-behavior: smooth;
}

/* ── Chat bubbles ──────────────────────────────────── */
.ai-bubble {
  display: flex;
  max-width: 80%;
}

.ai-bubble--user {
  align-self: flex-end;
}

.ai-bubble--assistant {
  align-self: flex-start;
}

.ai-bubble__text {
  display: block;
  padding: var(--space-3) var(--space-4);
  border-radius: var(--radius-md);
  font-size: 0.9rem;
  line-height: 1.55;
  white-space: pre-wrap;
}

.ai-bubble--user .ai-bubble__text {
  background: var(--color-primary);
  color: var(--color-text-inverse);
  border-bottom-right-radius: var(--radius-sm);
}

.ai-bubble--assistant .ai-bubble__text {
  background: var(--color-surface-alt);
  color: var(--color-text);
  border: 1px solid var(--color-border-light);
  border-bottom-left-radius: var(--radius-sm);
}

/* ── Typing indicator ──────────────────────────────── */
.ai-bubble--typing .ai-bubble__text {
  padding: var(--space-3) var(--space-4);
}

.ai-typing-dots {
  display: inline-flex;
  gap: 4px;
  align-items: center;
}

.ai-typing-dots span {
  display: inline-block;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--color-text-muted);
  animation: typing-bounce 1.2s infinite ease-in-out;
}

.ai-typing-dots span:nth-child(2) { animation-delay: 0.2s; }
.ai-typing-dots span:nth-child(3) { animation-delay: 0.4s; }

@keyframes typing-bounce {
  0%, 80%, 100% { transform: translateY(0); opacity: 0.4; }
  40%            { transform: translateY(-4px); opacity: 1; }
}

@media (prefers-reduced-motion: reduce) {
  .ai-typing-dots span { animation: none; opacity: 0.7; }
}

/* ── Completion panel ──────────────────────────────── */
.ai-complete {
  background: color-mix(in srgb, var(--color-success) 10%, transparent);
  border: 1px solid color-mix(in srgb, var(--color-success) 35%, transparent);
  border-radius: var(--radius-md);
  padding: var(--space-4);
  display: flex;
  flex-direction: column;
  align-items: stretch;
  gap: var(--space-4);
}

.ai-complete--saved {
  flex-direction: row;
  align-items: center;
}

.ai-complete__msg {
  margin: 0;
  font-size: 0.95rem;
  font-weight: 600;
  color: var(--color-success);
}

.ai-complete__actions {
  display: flex;
  gap: var(--space-3);
  flex-wrap: wrap;
}

/* ── Review-before-save panel ─────────────────────────── */
.ai-review {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  background: var(--color-surface-raised);
  border: 1px solid var(--color-border-light);
  border-radius: var(--radius-md);
  padding: var(--space-4);
}

.ai-review__field {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}

.ai-review__label {
  font-size: 0.8rem;
  font-weight: 600;
  color: var(--color-text-muted);
}

.ai-review__input,
.ai-review__textarea {
  padding: var(--space-2) var(--space-3);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  background: var(--color-surface);
  color: var(--color-text);
  font-family: var(--font-body);
  font-size: 0.9rem;
}

.ai-review__textarea {
  resize: vertical;
}

.ai-review__input:focus,
.ai-review__textarea:focus {
  outline: none;
  border-color: var(--color-primary);
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--color-primary) 15%, transparent);
}

.ai-review__checkbox-label {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  cursor: pointer;
  font-size: 0.9rem;
  color: var(--color-text);
}

.ai-review__checkbox {
  width: 1rem;
  height: 1rem;
  accent-color: var(--color-primary);
  cursor: pointer;
}

/* ── Input area ────────────────────────────────────── */
.ai-input-area {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.ai-input-row {
  display: flex;
  gap: var(--space-3);
  align-items: flex-end;
}

.ai-input {
  flex: 1;
  padding: var(--space-3);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  background: var(--color-surface-raised);
  color: var(--color-text);
  font-family: var(--font-body);
  font-size: 0.9rem;
  line-height: 1.5;
  resize: none;
  transition: border-color var(--transition);
}

.ai-input:focus {
  outline: none;
  border-color: var(--color-primary);
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--color-primary) 15%, transparent);
}

.ai-input:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.ai-input-btns {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.ai-send-btn,
.ai-skip-btn {
  white-space: nowrap;
  min-width: 72px;
}

/* ── Tone chips ────────────────────────────────────── */
.ai-tone-chips {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
}

.ai-tone-chip {
  padding: var(--space-1) var(--space-3);
  border: 1px solid color-mix(in srgb, var(--color-accent) 40%, transparent);
  border-radius: var(--radius-full);
  background: var(--color-accent-light);
  color: var(--color-accent);
  font-family: var(--font-body);
  font-size: 0.82rem;
  font-weight: 500;
  cursor: pointer;
  transition: background var(--transition), border-color var(--transition);
}

.ai-tone-chip:hover {
  background: color-mix(in srgb, var(--color-accent) 15%, transparent);
  border-color: var(--color-accent);
}

/* ── Error ─────────────────────────────────────────── */
.ai-error {
  font-size: 0.875rem;
  color: var(--color-error);
  margin: 0;
  padding: var(--space-2) var(--space-3);
  background: color-mix(in srgb, var(--color-error) 8%, transparent);
  border: 1px solid color-mix(in srgb, var(--color-error) 25%, transparent);
  border-radius: var(--radius-md);
}

/* ── Start over ────────────────────────────────────── */
.ai-startover-row {
  display: flex;
  justify-content: flex-end;
}

.btn-startover {
  background: none;
  border: none;
  font-family: var(--font-body);
  font-size: 0.8rem;
  color: var(--color-text-muted);
  cursor: pointer;
  padding: var(--space-1) var(--space-2);
  border-radius: var(--radius-sm);
  transition: color var(--transition);
  text-decoration: underline;
  text-underline-offset: 2px;
}

.btn-startover:hover {
  color: var(--color-error);
}

/* ── Button styles (local defs matching wizard.css) ── */
.btn-primary {
  padding: var(--space-2) var(--space-6);
  background: var(--color-primary);
  color: var(--color-text-inverse);
  border: none;
  border-radius: var(--radius-md);
  font-family: var(--font-body);
  font-size: 0.9rem;
  font-weight: 600;
  cursor: pointer;
  transition: background var(--transition), opacity var(--transition);
  min-height: 44px;
}

.btn-primary:hover:not(:disabled) { background: var(--color-primary-hover); }

.btn-primary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn-ghost {
  padding: var(--space-2) var(--space-4);
  background: none;
  color: var(--color-text-muted);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  font-family: var(--font-body);
  font-size: 0.9rem;
  cursor: pointer;
  transition: color var(--transition), border-color var(--transition);
  min-height: 44px;
}

.btn-ghost:hover:not(:disabled) {
  color: var(--color-text);
  border-color: var(--color-border);
}

.btn-ghost:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

/* ── Mobile ────────────────────────────────────────── */
@media (max-width: 600px) {
  .ai-messages {
    min-height: 240px;
    max-height: 360px;
  }

  .ai-input-row {
    flex-direction: column;
    align-items: stretch;
  }

  .ai-input-btns {
    flex-direction: row;
  }

  .ai-bubble {
    max-width: 92%;
  }

  .ai-complete {
    flex-direction: column;
    align-items: flex-start;
  }
}
</style>
