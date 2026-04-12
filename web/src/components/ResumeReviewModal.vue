<template>
  <Teleport to="body">
    <div
      class="rrm-backdrop"
      role="dialog"
      aria-modal="true"
      :aria-labelledby="`rrm-title-${jobId}`"
      @keydown.esc="handleEscape"
      @click.self="handleEscape"
    >
      <div class="rrm-card" ref="cardRef" tabindex="-1">

        <!-- Header -->
        <div class="rrm__header">
          <h2 :id="`rrm-title-${jobId}`" class="rrm__title">Resume Review</h2>
          <button class="rrm__close" aria-label="Close review" @click="handleEscape">✕</button>
        </div>

        <!-- Tab bar -->
        <div class="rrm__tabs" role="tablist" aria-label="Resume sections">
          <button
            v-for="(page, idx) in pages"
            :key="page.id"
            role="tab"
            :id="`rrm-tab-${page.id}`"
            :aria-selected="idx === currentIdx"
            :aria-controls="`rrm-panel-${page.id}`"
            class="rrm__tab"
            :class="{ 'rrm__tab--active': idx === currentIdx }"
            @click="goTo(idx)"
          >
            <span
              v-if="page.type !== 'confirm'"
              class="tab__dot"
              :class="`tab__dot--${tabStatus(page)}`"
              :aria-label="`${page.label}: ${tabStatus(page)}`"
            />
            <span class="tab__label">{{ page.label }}</span>
          </button>
        </div>

        <!-- Page content -->
        <div
          :id="`rrm-panel-${currentPage.id}`"
          class="rrm__content"
          role="tabpanel"
          :aria-labelledby="`rrm-tab-${currentPage.id}`"
        >
          <!-- Skills page -->
          <template v-if="currentPage.type === 'skills'">
            <SkillsPage
              :section="skillsSection!"
              :approved-skills="approvedSkills"
              :skill-framings="skillFramings"
              @toggle-skill="toggleSkill"
              @set-framing-mode="setFramingMode"
              @set-framing-context="setFramingContext"
            />
          </template>

          <!-- Summary page -->
          <template v-else-if="currentPage.type === 'summary'">
            <SummaryPage
              :section="summarySection!"
              :accepted="summaryAccepted"
              @update:accepted="summaryAccepted = $event"
            />
          </template>

          <!-- Experience page -->
          <template v-else-if="currentPage.type === 'experience'">
            <ExperiencePage
              :entry="currentEntry!"
              :accepted="expAccepted[currentPage.entryKey!] ?? true"
              @update:accepted="expAccepted[currentPage.entryKey!] = $event"
            />
          </template>

          <!-- Confirm page -->
          <template v-else-if="currentPage.type === 'confirm'">
            <ConfirmPage
              :pages="pages.filter(p => p.type !== 'confirm')"
              :tab-status="tabStatus"
              :submitting="submitting"
              :error="submitError"
              @preview="emitSubmit"
              @rewrite="emit('rewriteAgain')"
            />
          </template>
        </div>

        <!-- Footer navigation -->
        <div class="rrm__footer">
          <button
            class="rrm__back btn-secondary"
            :disabled="currentIdx === 0"
            @click="goTo(currentIdx - 1)"
          >
            ← Back
          </button>
          <span class="rrm__page-counter">
            {{ currentIdx + 1 }} / {{ pages.length }}
          </span>
          <button
            v-if="currentPage.type !== 'confirm'"
            class="rrm__next btn-generate"
            @click="goTo(currentIdx + 1)"
          >
            Next →
          </button>
          <button
            v-else
            class="rrm__preview btn-generate"
            :disabled="submitting"
            @click="emitSubmit"
          >
            <span aria-hidden="true">👁️</span>
            {{ submitting ? 'Generating…' : 'Preview Full Resume' }}
          </button>
        </div>

      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import SkillsPage from './resume-review/SkillsPage.vue'
import SummaryPage from './resume-review/SummaryPage.vue'
import ExperiencePage from './resume-review/ExperiencePage.vue'
import ConfirmPage from './resume-review/ConfirmPage.vue'

// ── Types ─────────────────────────────────────────────────────────────────────

type TabStatus = 'unvisited' | 'in-progress' | 'accepted' | 'partial' | 'skipped'
type PageType = 'skills' | 'summary' | 'experience' | 'confirm'
type GapFramingMode = 'skip' | 'adjacent' | 'learning'

interface GapFraming { mode: GapFramingMode; context: string }

export interface SkillsDiff {
  section: 'skills'
  type: 'skills_diff'
  added: string[]
  removed: string[]
  kept: string[]
}

export interface TextDiff {
  section: 'summary'
  type: 'text_diff'
  original: string
  proposed: string
}

export interface BulletsDiff {
  section: 'experience'
  type: 'bullets_diff'
  entries: Array<{
    title: string
    company: string
    original_bullets: string[]
    proposed_bullets: string[]
  }>
}

export type SectionDiff = SkillsDiff | TextDiff | BulletsDiff

export interface ReviewDraft {
  sections: SectionDiff[]
  rewritten_struct: Record<string, unknown>
  gap_report?: unknown[]
}

interface Page {
  id: string
  type: PageType
  label: string
  entryKey?: string
}

// ── Props / emits ─────────────────────────────────────────────────────────────

const props = defineProps<{
  jobId: number
  draft: ReviewDraft
}>()

const emit = defineEmits<{
  close: []
  submit: [decisions: Record<string, unknown>]
  rewriteAgain: []
}>()

// ── Section accessors ─────────────────────────────────────────────────────────

const skillsSection = computed(() =>
  props.draft.sections.find(s => s.section === 'skills') as SkillsDiff | undefined
)
const summarySection = computed(() =>
  props.draft.sections.find(s => s.section === 'summary') as TextDiff | undefined
)
const expSection = computed(() =>
  props.draft.sections.find(s => s.section === 'experience') as BulletsDiff | undefined
)

// ── Page list ─────────────────────────────────────────────────────────────────

const pages = computed<Page[]>(() => {
  const result: Page[] = []
  const skills = skillsSection.value
  const summary = summarySection.value
  const exp = expSection.value
  if (skills && skills.added.length > 0) {
    result.push({ id: 'skills', type: 'skills', label: 'Skills' })
  }
  if (summary) {
    result.push({ id: 'summary', type: 'summary', label: 'Summary' })
  }
  for (const e of (exp?.entries ?? [])) {
    const key = `${e.title}|${e.company}`
    result.push({ id: key, type: 'experience', label: e.title, entryKey: key })
  }
  result.push({ id: 'confirm', type: 'confirm', label: 'Confirm' })
  return result
})

// ── Navigation state ──────────────────────────────────────────────────────────

const currentIdx = ref(0)
const visitedPages = ref<Set<string>>(new Set())
// Pages where the user has explicitly made a decision (toggled/changed something)
const interactedPages = ref<Set<string>>(new Set())

const currentPage = computed(() => pages.value[currentIdx.value])

const currentEntry = computed(() => {
  const key = currentPage.value.entryKey
  if (!key) return undefined
  return expSection.value?.entries.find(e => `${e.title}|${e.company}` === key)
})

function goTo(idx: number) {
  if (idx < 0 || idx >= pages.value.length) return
  // Mark current page as visited before leaving
  visitedPages.value = new Set([...visitedPages.value, currentPage.value.id])
  currentIdx.value = idx
  // Mark destination as visited on arrival
  visitedPages.value = new Set([...visitedPages.value, pages.value[idx].id])
}

// ── Decision state ────────────────────────────────────────────────────────────

const approvedSkills = ref<Set<string>>(new Set(skillsSection.value?.added ?? []))
const skillFramings = ref<Map<string, GapFraming>>(new Map())
const summaryAccepted = ref(true)
const expAccepted = ref<Record<string, boolean>>(
  Object.fromEntries(
    (expSection.value?.entries ?? []).map(e => [`${e.title}|${e.company}`, true])
  )
)

function toggleSkill(skill: string) {
  interactedPages.value = new Set([...interactedPages.value, 'skills'])
  const next = new Set(approvedSkills.value)
  if (next.has(skill)) {
    next.delete(skill)
    if (!skillFramings.value.has(skill)) {
      skillFramings.value = new Map([...skillFramings.value, [skill, { mode: 'skip', context: '' }]])
    }
  } else {
    next.add(skill)
    const next2 = new Map(skillFramings.value)
    next2.delete(skill)
    skillFramings.value = next2
  }
  approvedSkills.value = next
}

function setFramingMode(skill: string, mode: GapFramingMode) {
  const existing = skillFramings.value.get(skill) ?? { mode: 'skip' as GapFramingMode, context: '' }
  skillFramings.value = new Map([...skillFramings.value, [skill, { ...existing, mode }]])
}

function setFramingContext(skill: string, context: string) {
  const existing = skillFramings.value.get(skill) ?? { mode: 'skip' as GapFramingMode, context: '' }
  skillFramings.value = new Map([...skillFramings.value, [skill, { ...existing, context }]])
}

// ── Tab status ────────────────────────────────────────────────────────────────

function tabStatus(page: Page): TabStatus {
  if (!visitedPages.value.has(page.id)) return 'unvisited'
  // Only report a resolved status if the user has explicitly interacted
  if (!interactedPages.value.has(page.id)) return 'in-progress'
  if (page.type === 'skills') {
    const total = skillsSection.value?.added.length ?? 0
    const approved = approvedSkills.value.size
    if (approved === total) return 'accepted'
    if (approved === 0) return 'skipped'
    return 'partial'
  }
  if (page.type === 'summary') {
    return summaryAccepted.value ? 'accepted' : 'skipped'
  }
  if (page.type === 'experience' && page.entryKey) {
    return (expAccepted.value[page.entryKey] ?? true) ? 'accepted' : 'skipped'
  }
  return 'in-progress'
}

// ── Submit ────────────────────────────────────────────────────────────────────

const submitting = ref(false)
const submitError = ref('')

function emitSubmit() {
  const decisions: Record<string, unknown> = {}

  if (skillsSection.value) {
    decisions.skills = { approved_additions: [...approvedSkills.value] }
  }
  if (summarySection.value) {
    decisions.summary = { accepted: summaryAccepted.value }
  }
  if (expSection.value) {
    decisions.experience = {
      accepted_entries: expSection.value.entries.map(e => ({
        title: e.title,
        company: e.company,
        accepted: expAccepted.value[`${e.title}|${e.company}`] ?? true,
      })),
    }
  }

  const gap_framings = [...skillFramings.value.entries()]
    .filter(([, f]) => f.mode !== 'skip')
    .map(([skill, f]) => ({ skill, mode: f.mode, context: f.context }))
  if (gap_framings.length) decisions.gap_framings = gap_framings

  emit('submit', decisions)
}

// ── Escape / focus ────────────────────────────────────────────────────────────

function handleEscape() {
  emit('close')
}

const cardRef = ref<HTMLElement | null>(null)

onMounted(() => {
  cardRef.value?.focus()
})

function trapFocus(e: KeyboardEvent) {
  if (e.key !== 'Tab' || !cardRef.value) return
  const focusable = cardRef.value.querySelectorAll<HTMLElement>(
    'button:not([disabled]), input, textarea, select, [tabindex]:not([tabindex="-1"])'
  )
  if (focusable.length === 0) return
  const first = focusable[0]
  const last = focusable[focusable.length - 1]
  if (e.shiftKey && document.activeElement === first) {
    e.preventDefault()
    last.focus()
  } else if (!e.shiftKey && document.activeElement === last) {
    e.preventDefault()
    first.focus()
  }
}

onMounted(() => document.addEventListener('keydown', trapFocus))
onUnmounted(() => document.removeEventListener('keydown', trapFocus))
</script>

<style scoped>
.rrm-backdrop {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.55);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 200;
  padding: var(--space-4, 1rem);
}

.rrm-card {
  background: var(--color-surface-raised, #f5f7fc);
  border-radius: var(--radius-lg, 1rem);
  box-shadow: var(--shadow-lg, 0 10px 30px rgba(26, 35, 56, 0.12));
  width: 100%;
  max-width: 860px;
  max-height: 90vh;
  display: flex;
  flex-direction: column;
  outline: none;
}

/* Header */
.rrm__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--space-4, 1rem) var(--space-6, 1.5rem);
  border-bottom: 1px solid var(--color-border, #a8b8d0);
  flex-shrink: 0;
}

.rrm__title {
  font-size: var(--font-lg, 1.125rem);
  font-weight: 600;
  margin: 0;
  color: var(--color-text, #1a2338);
  font-family: var(--font-display, Georgia, serif);
}

.rrm__close {
  background: none;
  border: none;
  cursor: pointer;
  font-size: 1.1rem;
  color: var(--color-text-muted, #4a5c7a);
  padding: var(--space-1, 0.25rem) var(--space-2, 0.5rem);
  border-radius: var(--radius-sm, 0.25rem);
  line-height: 1;
  transition: color var(--transition, 200ms ease);
}
.rrm__close:hover { color: var(--color-text, #1a2338); }

/* Tab bar */
.rrm__tabs {
  display: flex;
  flex-shrink: 0;
  overflow-x: auto;
  scrollbar-width: none;
  border-bottom: 1px solid var(--color-border, #a8b8d0);
  padding: 0 var(--space-4, 1rem);
  background: var(--color-surface, #eaeff8);
}
.rrm__tabs::-webkit-scrollbar { display: none; }

.rrm__tab {
  display: flex;
  align-items: center;
  gap: var(--space-2, 0.5rem);
  padding: var(--space-3, 0.75rem) var(--space-3, 0.75rem);
  background: none;
  border: none;
  border-bottom: 2px solid transparent;
  cursor: pointer;
  white-space: nowrap;
  color: var(--color-text-muted, #4a5c7a);
  transition: color var(--transition, 200ms ease), border-color var(--transition, 200ms ease);
}

.rrm__tab--active {
  color: var(--color-text, #1a2338);
  border-bottom-color: var(--color-accent, #c4732a);
}

.rrm__tab:hover { color: var(--color-text, #1a2338); }

.tab__label { font-size: 0.875rem; }

.tab__dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
  background: var(--tab-color, #94a3b8);
  display: inline-block;
}

.tab__dot--unvisited   { --tab-color: var(--color-text-muted, #4a5c7a); opacity: 0.4; }
.tab__dot--in-progress { --tab-color: var(--color-accent, #c4732a); }
.tab__dot--accepted    { --tab-color: var(--color-success, #3a7a32); }
.tab__dot--partial     { --tab-color: var(--color-warning, #d4891a); }
.tab__dot--skipped     { --tab-color: var(--color-border, #a8b8d0); }

/* Content */
.rrm__content {
  flex: 1;
  overflow-y: auto;
  padding: var(--space-6, 1.5rem);
}

/* Footer */
.rrm__footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--space-4, 1rem) var(--space-6, 1.5rem);
  border-top: 1px solid var(--color-border, #a8b8d0);
  flex-shrink: 0;
  background: var(--color-surface, #eaeff8);
  border-radius: 0 0 var(--radius-lg, 1rem) var(--radius-lg, 1rem);
}

.rrm__page-counter {
  font-size: 0.875rem;
  color: var(--color-text-muted, #4a5c7a);
}

/* Shared button styles (scoped — footer only) */
.btn-generate {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2, 0.5rem);
  padding: var(--space-2, 0.5rem) var(--space-4, 1rem);
  background: var(--color-accent, #c4732a);
  color: #fff;
  border: none;
  border-radius: var(--radius-md, 0.5rem);
  font-size: 0.875rem;
  font-weight: 600;
  cursor: pointer;
  transition: background var(--transition, 200ms ease);
}
.btn-generate:hover:not(:disabled) { background: var(--color-accent-hover, #a85c1f); }
.btn-generate:disabled { opacity: 0.6; cursor: not-allowed; }

.btn-secondary {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2, 0.5rem);
  padding: var(--space-2, 0.5rem) var(--space-4, 1rem);
  background: var(--color-surface-alt, #dde4f0);
  color: var(--color-text, #1a2338);
  border: 1px solid var(--color-border, #a8b8d0);
  border-radius: var(--radius-md, 0.5rem);
  font-size: 0.875rem;
  font-weight: 600;
  cursor: pointer;
  transition: background var(--transition, 200ms ease);
}
.btn-secondary:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}
.btn-secondary:hover:not(:disabled) { background: var(--color-surface, #eaeff8); }

/* Mobile */
@media (max-width: 600px) {
  .rrm-card { max-height: 100vh; border-radius: 0; }
  .rrm-backdrop { padding: 0; align-items: flex-end; }
  .rrm__content { padding: var(--space-4, 1rem); }
}
</style>
