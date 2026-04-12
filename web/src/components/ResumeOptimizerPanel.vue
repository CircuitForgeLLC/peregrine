<template>
  <section class="rop" aria-labelledby="rop-heading">
    <h2 id="rop-heading" class="rop__heading">ATS Resume Optimizer</h2>

    <!-- ── Tier gate notice (free) ────────────────────────────────────── -->
    <p v-if="isFree" class="rop__tier-note">
      <span aria-hidden="true">🔒</span>
      Keyword gap report is free. Full AI rewrite requires a
      <strong>Paid</strong> license.
    </p>

    <!-- ── Gap report section (all tiers) ────────────────────────────── -->
    <div class="rop__gaps">
      <div class="rop__gaps-header">
        <h3 class="rop__subheading">Keyword Gap Report</h3>
        <button
          class="btn-generate"
          :disabled="gapState === 'queued' || gapState === 'running'"
          @click="runGapReport"
        >
          <span aria-hidden="true">🔍</span>
          {{ gapState === 'queued' || gapState === 'running' ? 'Analyzing…' : 'Analyze Keywords' }}
        </button>
      </div>

      <template v-if="gapState === 'queued' || gapState === 'running'">
        <div class="rop__spinner-row" role="status" aria-live="polite">
          <span class="spinner" aria-hidden="true" />
          <span>{{ gapStage ?? 'Extracting keyword gaps…' }}</span>
        </div>
      </template>

      <template v-else-if="gapState === 'failed'">
        <p class="rop__error" role="alert">Gap analysis failed. Try again.</p>
      </template>

      <template v-else-if="gaps.length > 0">
        <p class="rop__hint rop__hint--gap-select">
          Check the gaps you want the rewrite to target. Uncheck any that don't apply to you.
        </p>
        <div class="rop__gap-list" role="list" aria-label="Keyword gaps by section">
          <label
            v-for="item in gaps"
            :key="item.term"
            class="rop__gap-item"
            :class="[`rop__gap-item--p${item.priority}`, { 'rop__gap-item--excluded': !selectedGaps.has(item.term) }]"
            role="listitem"
          >
            <input
              type="checkbox"
              class="rop__gap-checkbox"
              :checked="selectedGaps.has(item.term)"
              @change="toggleGap(item.term)"
            />
            <span class="rop__gap-section" :title="`Route to ${item.section}`">{{ item.section }}</span>
            <span class="rop__gap-term">{{ item.term }}</span>
            <span class="rop__gap-rationale">{{ item.rationale }}</span>
          </label>
        </div>
      </template>

      <template v-else-if="gapState === 'completed'">
        <p class="rop__empty">No significant keyword gaps found — your resume already covers this JD well.</p>
      </template>

      <template v-else>
        <p class="rop__hint">Click <em>Analyze Keywords</em> to see which ATS terms your resume is missing.</p>
      </template>
    </div>

    <!-- ── Full rewrite section (paid+) ──────────────────────────────── -->
    <div v-if="!isFree" class="rop__rewrite">
      <div class="rop__gaps-header">
        <h3 class="rop__subheading">Optimized Resume</h3>
        <button
          class="btn-generate"
          :disabled="rewriteState === 'queued' || rewriteState === 'running' || gaps.length === 0"
          :title="gaps.length === 0 ? 'Run gap analysis first' : ''"
          @click="runFullRewrite"
        >
          <span aria-hidden="true">✨</span>
          {{ rewriteState === 'queued' || rewriteState === 'running' ? 'Rewriting…' : 'Optimize Resume' }}
        </button>
      </div>

      <template v-if="rewriteState === 'queued' || rewriteState === 'running'">
        <div class="rop__spinner-row" role="status" aria-live="polite">
          <span class="spinner" aria-hidden="true" />
          <span>{{ rewriteStage ?? 'Rewriting resume sections…' }}</span>
        </div>
      </template>

      <template v-else-if="rewriteState === 'failed'">
        <p class="rop__error" role="alert">Resume rewrite failed. Check that a resume file is configured in Settings.</p>
      </template>

      <!-- ── awaiting_review: modal trigger ──────────────────────────── -->
      <template v-else-if="rewriteState === 'awaiting_review' && reviewDraft">
        <div class="rop__review-trigger">
          <p class="rop__hint">Your resume has been rewritten. Review the proposed changes section by section.</p>
          <button class="btn-generate" @click="showReviewModal = true">
            <span aria-hidden="true">📋</span> Review Changes
          </button>
        </div>
      </template>

      <!-- ── Preview panel (after /review, before /approve) ─────────── -->
      <template v-else-if="rewriteState === 'previewing'">
        <div class="rop__preview" role="region" aria-label="Resume preview">
          <div class="rop__rewrite-toolbar">
            <span class="rop__wordcount" aria-live="polite">{{ previewWordCount }} words</span>
            <span class="rop__preview-badge">Preview — not yet saved</span>
          </div>
          <textarea
            :value="previewText"
            class="rop__textarea rop__textarea--preview"
            aria-label="Resume preview text"
            spellcheck="false"
            readonly
          />
          <p class="rop__preview-hint">
            Review the assembled resume above. If it looks right, click
            <strong>Approve &amp; Save</strong> to lock it in. You can also go back and adjust
            your review decisions.
          </p>
          <div class="rop__save-to-library">
            <label class="rop__save-toggle">
              <input type="checkbox" v-model="saveToLibrary" />
              Save to Resume Library
            </label>
            <input
              v-if="saveToLibrary"
              type="text"
              class="rop__resume-name-input"
              placeholder="Resume name (e.g. Q1 2026 — Acme)"
              v-model="savedResumeName"
              maxlength="80"
            />
          </div>
          <div class="rop__preview-actions">
            <button
              class="btn-generate btn-approve"
              :disabled="approvingResume"
              @click="approveResume"
            >
              <span aria-hidden="true">✅</span>
              {{ approvingResume ? 'Saving…' : 'Approve & Save' }}
            </button>
            <button class="btn-download" @click="downloadTxt">
              <span aria-hidden="true">📄</span> Download .txt
            </button>
            <button class="btn-secondary" @click="rewriteState = 'awaiting_review'">
              ← Back to review
            </button>
          </div>
          <p v-if="reviewError" class="rop__error" role="alert">{{ reviewError }}</p>
        </div>
      </template>

      <!-- ── Finalized resume output ───────────────────────────────────── -->
      <template v-else-if="optimizedResume">
        <div class="rop__rewrite-toolbar">
          <span class="rop__wordcount" aria-live="polite">{{ rewriteWordCount }} words</span>
          <span class="rop__verified-badge" aria-label="Reviewed and approved">✓ Approved</span>
        </div>
        <textarea
          v-model="optimizedResume"
          class="rop__textarea"
          aria-label="Optimized resume text"
          spellcheck="false"
        />
        <div class="rop__download-row">
          <button class="btn-download" @click="downloadTxt">
            <span aria-hidden="true">📄</span> Download .txt
          </button>
          <button class="btn-download" @click="downloadPdf">
            <span aria-hidden="true">📑</span> Download PDF
          </button>
          <button class="btn-download" @click="downloadYaml">
            <span aria-hidden="true">📋</span> Download YAML
          </button>
          <button class="btn-secondary" @click="runFullRewrite">
            <span aria-hidden="true">🔄</span> Rewrite again
          </button>
        </div>

        <!-- Version history -->
        <div v-if="history.length" class="rop__history">
          <button class="rop__history-toggle" @click="showHistory = !showHistory">
            <span aria-hidden="true">🕑</span>
            {{ showHistory ? 'Hide' : 'Show' }} previous versions ({{ history.length }})
          </button>
          <div v-if="showHistory" class="rop__history-list" role="list">
            <div
              v-for="entry in history"
              :key="entry.archived_at"
              class="rop__history-item"
              role="listitem"
            >
              <span class="rop__history-date">{{ entry.archived_at }}</span>
              <button
                class="rop__history-restore"
                @click="optimizedResume = entry.text"
                title="Restore this version to the editor"
              >Restore</button>
            </div>
          </div>
        </div>
      </template>

      <template v-else>
        <p class="rop__hint">
          Run <em>Analyze Keywords</em> first, then click <em>Optimize Resume</em> to rewrite your resume
          sections to naturally incorporate missing ATS keywords.
        </p>
      </template>
    </div>

    <!-- Review modal (Teleport'd to body by the component itself) -->
    <ResumeReviewModal
      v-if="showReviewModal && reviewDraft"
      :job-id="props.jobId"
      :draft="reviewDraft"
      @close="showReviewModal = false"
      @submit="handleReviewSubmit"
      @rewrite-again="handleRewriteAgain"
    />
  </section>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useApiFetch } from '../composables/useApi'
import { useAppConfigStore } from '../stores/appConfig'
import ResumeReviewModal from './ResumeReviewModal.vue'

const props = defineProps<{ jobId: number }>()

const config = useAppConfigStore()
const isFree = computed(() => config.tier === 'free')

// ── Types ─────────────────────────────────────────────────────────────────────

type TaskState = 'none' | 'queued' | 'running' | 'awaiting_review' | 'previewing' | 'completed' | 'failed'
type GapFramingMode = 'skip' | 'adjacent' | 'learning'

interface GapFraming {
  mode: GapFramingMode
  context: string
}

interface SkillsDiff {
  section: 'skills'; type: 'skills_diff'
  added: string[]; removed: string[]; kept: string[]
}
interface TextDiff {
  section: 'summary'; type: 'text_diff'
  original: string; proposed: string
}
interface BulletsDiff {
  section: 'experience'; type: 'bullets_diff'
  entries: Array<{ title: string; company: string; original_bullets: string[]; proposed_bullets: string[] }>
}
type SectionDiff = SkillsDiff | TextDiff | BulletsDiff

interface ReviewDraft {
  sections: SectionDiff[]
  rewritten_struct: Record<string, unknown>
}

// ── Gap report state ─────────────────────────────────────────────────────────

const gapState    = ref<TaskState>('none')
const gapStage    = ref<string | null>(null)
const gaps        = ref<Array<{ term: string; section: string; priority: number; rationale: string }>>([])
const selectedGaps = ref<Set<string>>(new Set())

// ── Rewrite / review state ────────────────────────────────────────────────────

const rewriteState  = ref<TaskState>('none')
const rewriteStage  = ref<string | null>(null)
const optimizedResume = ref('')

// Review draft and user decisions
const reviewDraft       = ref<ReviewDraft | null>(null)
const approvedSkills    = ref<Set<string>>(new Set())
// For each unapproved skill: how to frame the gap honestly
const skillFramings     = ref<Map<string, GapFraming>>(new Map())
const summaryAccepted   = ref(true)
const expAccepted       = ref<Record<string, boolean>>({})  // key: "title|company"
const submittingReview  = ref(false)
const reviewError       = ref('')

// Preview state (after /review, before /approve)
const previewText       = ref('')
const previewStruct     = ref<Record<string, unknown> | null>(null)
const approvingResume   = ref(false)

// Archive
const history           = ref<Array<{ archived_at: string; text: string }>>([])
const showHistory       = ref(false)

// Modal + save-to-library state
const showReviewModal   = ref(false)
const saveToLibrary     = ref(false)
const savedResumeName   = ref('')

const rewriteWordCount = computed(() =>
  optimizedResume.value.trim().split(/\s+/).filter(Boolean).length
)
const previewWordCount = computed(() =>
  previewText.value.trim().split(/\s+/).filter(Boolean).length
)

// ── Task polling ─────────────────────────────────────────────────────────────

let pollTimer: ReturnType<typeof setInterval> | null = null

function startPolling() {
  stopPolling()
  pollTimer = setInterval(pollTaskStatus, 3000)
}
function stopPolling() {
  if (pollTimer !== null) { clearInterval(pollTimer); pollTimer = null }
}

async function pollTaskStatus() {
  const { data } = await useApiFetch<{ status: string; stage: string | null }>(
    `/api/jobs/${props.jobId}/resume_optimizer/task`
  )
  if (!data) return
  const status = data.status as TaskState

  if (gapState.value === 'queued' || gapState.value === 'running') {
    gapState.value = status
    gapStage.value = data.stage ?? null
    if (status === 'completed' || status === 'failed') {
      stopPolling()
      if (status === 'completed') await loadResults()
    }
  } else if (rewriteState.value === 'queued' || rewriteState.value === 'running') {
    rewriteState.value = status
    rewriteStage.value = data.stage ?? null
    if (status === 'awaiting_review') {
      stopPolling()
      await loadReviewDraft()
    } else if (status === 'completed' || status === 'failed') {
      stopPolling()
      if (status === 'completed') await loadResults()
    }
  }
}

// ── Data loaders ─────────────────────────────────────────────────────────────

async function loadResults() {
  const { data } = await useApiFetch<{
    optimized_resume: string
    ats_gap_report: Array<{ term: string; section: string; priority: number; rationale: string }>
  }>(`/api/jobs/${props.jobId}/resume_optimizer`)
  if (!data) return
  if (data.ats_gap_report?.length) {
    gaps.value = data.ats_gap_report
    selectedGaps.value = new Set(data.ats_gap_report.map((g: { term: string }) => g.term))
    gapState.value = 'completed'
  }
  if (data.optimized_resume) { optimizedResume.value = data.optimized_resume; rewriteState.value = 'completed' }
}

async function loadReviewDraft() {
  const { data } = await useApiFetch<{ draft: ReviewDraft | null }>(
    `/api/jobs/${props.jobId}/resume_optimizer/review`
  )
  if (!data?.draft) return
  reviewDraft.value = data.draft
  rewriteState.value = 'awaiting_review'

  // All added skills approved by default — user un-checks skills they don't have
  const skillsSec = data.draft.sections.find(s => s.section === 'skills') as SkillsDiff | undefined
  approvedSkills.value = new Set(skillsSec?.added ?? [])
  // Clear any leftover framing decisions from a previous review attempt
  skillFramings.value = new Map()
  summaryAccepted.value = true
  expAccepted.value = {}
  const expSec = data.draft.sections.find(s => s.section === 'experience') as BulletsDiff | undefined
  for (const e of (expSec?.entries ?? [])) {
    expAccepted.value[`${e.title}|${e.company}`] = true
  }

  await loadHistory()
}

async function loadHistory() {
  const { data } = await useApiFetch<{ history: Array<{ archived_at: string; text: string }> }>(
    `/api/jobs/${props.jobId}/resume_optimizer/history`
  )
  if (data?.history) history.value = data.history
}

// ── Actions ──────────────────────────────────────────────────────────────────

async function runGapReport() {
  gapState.value = 'queued'; gapStage.value = null; gaps.value = []; selectedGaps.value = new Set()
  const { error } = await useApiFetch(`/api/jobs/${props.jobId}/resume_optimizer/generate`, {
    method: 'POST',
    body: JSON.stringify({ full_rewrite: false }),
    headers: { 'Content-Type': 'application/json' },
  })
  if (error) { gapState.value = 'failed'; return }
  startPolling()
}

async function runFullRewrite() {
  rewriteState.value = 'queued'; rewriteStage.value = null
  optimizedResume.value = ''; reviewDraft.value = null; reviewError.value = ''
  const body: Record<string, unknown> = { full_rewrite: true }
  if (selectedGaps.value.size > 0) body.selected_gaps = [...selectedGaps.value]
  const { error } = await useApiFetch(`/api/jobs/${props.jobId}/resume_optimizer/generate`, {
    method: 'POST',
    body: JSON.stringify(body),
    headers: { 'Content-Type': 'application/json' },
  })
  if (error) { rewriteState.value = 'failed'; return }
  startPolling()
}

function toggleGap(term: string) {
  if (selectedGaps.value.has(term)) selectedGaps.value.delete(term)
  else selectedGaps.value.add(term)
}

function toggleSkill(skill: string) {
  if (approvedSkills.value.has(skill)) {
    // Unchecking: move to framing state, defaulting to 'skip'
    approvedSkills.value.delete(skill)
    if (!skillFramings.value.has(skill)) {
      skillFramings.value.set(skill, { mode: 'skip', context: '' })
    }
  } else {
    // Re-checking: back to approved, remove framing
    approvedSkills.value.add(skill)
    skillFramings.value.delete(skill)
  }
}

function setFramingMode(skill: string, mode: GapFramingMode) {
  const existing = skillFramings.value.get(skill) ?? { mode: 'skip', context: '' }
  skillFramings.value.set(skill, { ...existing, mode })
}

function setFramingContext(skill: string, context: string) {
  const existing = skillFramings.value.get(skill) ?? { mode: 'skip', context: '' }
  skillFramings.value.set(skill, { ...existing, context })
}

async function handleReviewSubmit(decisions: Record<string, unknown>) {
  showReviewModal.value = false
  submittingReview.value = true
  reviewError.value = ''

  const { data, error } = await useApiFetch<{ preview_text: string; preview_struct: Record<string, unknown> }>(
    `/api/jobs/${props.jobId}/resume_optimizer/review`,
    {
      method: 'POST',
      body: JSON.stringify({ decisions, gap_framings: decisions.gap_framings ?? [] }),
      headers: { 'Content-Type': 'application/json' },
    }
  )
  submittingReview.value = false
  if (error || !data) {
    reviewError.value = 'Failed to generate preview.'
    showReviewModal.value = true
    return
  }
  previewText.value = data.preview_text
  previewStruct.value = data.preview_struct
  rewriteState.value = 'previewing'
}

function handleRewriteAgain() {
  showReviewModal.value = false
  runFullRewrite()
}

async function approveResume() {
  if (!previewStruct.value) return
  approvingResume.value = true

  const body: Record<string, unknown> = { preview_struct: previewStruct.value }
  if (saveToLibrary.value) {
    body.save_to_library = true
    body.resume_name = savedResumeName.value.trim() || `Optimized for job ${props.jobId}`
  }

  const { data, error } = await useApiFetch<{ optimized_resume: string; saved_resume_id?: number }>(
    `/api/jobs/${props.jobId}/resume_optimizer/approve`,
    { method: 'POST', body: JSON.stringify(body), headers: { 'Content-Type': 'application/json' } }
  )
  approvingResume.value = false
  if (error || !data) { reviewError.value = 'Failed to save resume. Please try again.'; return }

  optimizedResume.value = data.optimized_resume
  rewriteState.value = 'completed'
  reviewDraft.value = null
  previewText.value = ''
  previewStruct.value = null
  saveToLibrary.value = false
  savedResumeName.value = ''
  await loadHistory()
}

function downloadTxt() {
  const text = rewriteState.value === 'previewing' ? previewText.value : optimizedResume.value
  const blob = new Blob([text], { type: 'text/plain' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url; a.download = `resume-optimized-job-${props.jobId}.txt`; a.click()
  URL.revokeObjectURL(url)
}

function downloadPdf() {
  window.open(`/api/jobs/${props.jobId}/resume_optimizer/export-pdf`, '_blank')
}

function downloadYaml() {
  window.open(`/api/jobs/${props.jobId}/resume_optimizer/export-yaml`, '_blank')
}

// ── Lifecycle ────────────────────────────────────────────────────────────────

onMounted(async () => {
  await loadResults()
  const { data } = await useApiFetch<{ status: string }>(
    `/api/jobs/${props.jobId}/resume_optimizer/task`
  )
  const s = data?.status
  if (s === 'queued' || s === 'running') {
    if (!optimizedResume.value && !gaps.value.length) gapState.value = s as TaskState
    else if (gaps.value.length) rewriteState.value = s as TaskState
    startPolling()
  } else if (s === 'awaiting_review') {
    await loadReviewDraft()
  }
})

onUnmounted(stopPolling)
</script>

<style scoped>
.rop {
  display: flex;
  flex-direction: column;
  gap: var(--space-5, 1.25rem);
  padding: var(--space-4, 1rem);
  border-top: 1px solid var(--app-border, #e2e8f0);
}

.rop__heading {
  font-size: var(--font-lg, 1.125rem);
  font-weight: 600;
  color: var(--app-text, #1e293b);
  margin: 0;
}

.rop__subheading {
  font-size: var(--font-base, 1rem);
  font-weight: 600;
  color: var(--app-text, #1e293b);
  margin: 0;
}

.rop__tier-note {
  font-size: var(--font-sm, 0.875rem);
  color: var(--app-text-muted, #64748b);
  background: var(--app-surface-alt, #f8fafc);
  border: 1px solid var(--app-border, #e2e8f0);
  border-radius: var(--radius-md, 0.5rem);
  padding: var(--space-3, 0.75rem) var(--space-4, 1rem);
  margin: 0;
}

.rop__gaps,
.rop__rewrite {
  display: flex;
  flex-direction: column;
  gap: var(--space-3, 0.75rem);
}

.rop__gaps-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3, 0.75rem);
}

.rop__hint,
.rop__empty {
  font-size: var(--font-sm, 0.875rem);
  color: var(--app-text-muted, #64748b);
  margin: 0;
}

.rop__error {
  font-size: var(--font-sm, 0.875rem);
  color: var(--app-danger, #dc2626);
  margin: 0;
}

.rop__spinner-row {
  display: flex;
  align-items: center;
  gap: var(--space-2, 0.5rem);
  font-size: var(--font-sm, 0.875rem);
  color: var(--app-text-muted, #64748b);
}

/* ── Gap list ─────────────────────────────────────────────────────── */

.rop__gap-list {
  display: flex;
  flex-direction: column;
  gap: var(--space-1, 0.25rem);
}

.rop__hint--gap-select {
  font-style: italic;
}

.rop__gap-item {
  display: grid;
  grid-template-columns: 1.5rem 6rem 1fr;
  grid-template-rows: auto auto;
  gap: 0 var(--space-2, 0.5rem);
  padding: var(--space-2, 0.5rem) var(--space-3, 0.75rem);
  border-radius: var(--radius-sm, 0.25rem);
  border-left: 3px solid transparent;
  background: var(--app-surface-alt, #f8fafc);
  font-size: var(--font-sm, 0.875rem);
  cursor: pointer;
  user-select: none;
}

.rop__gap-item--excluded {
  opacity: 0.45;
}

.rop__gap-checkbox {
  grid-row: 1 / 3;
  grid-column: 1;
  align-self: center;
  cursor: pointer;
  accent-color: var(--app-accent, #6366f1);
}

.rop__gap-item--p1 { border-left-color: var(--app-accent, #6366f1); }
.rop__gap-item--p2 { border-left-color: var(--app-warning, #f59e0b); }
.rop__gap-item--p3 { border-left-color: var(--app-border, #e2e8f0); }

.rop__gap-section {
  grid-row: 1;
  grid-column: 2;
  font-size: var(--font-xs, 0.75rem);
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--app-text-muted, #64748b);
  align-self: center;
}

.rop__gap-term {
  grid-row: 1;
  grid-column: 3;
  font-weight: 500;
  color: var(--app-text, #1e293b);
}

.rop__gap-rationale {
  grid-row: 2;
  grid-column: 3;
  font-size: var(--font-xs, 0.75rem);
  color: var(--app-text-muted, #64748b);
}

.rop__review-actions {
  display: flex;
  gap: var(--space-3, 0.75rem);
  align-items: center;
  flex-wrap: wrap;
}

/* ── Rewrite output ───────────────────────────────────────────────── */

.rop__rewrite-toolbar {
  display: flex;
  align-items: center;
  gap: var(--space-3, 0.75rem);
  justify-content: space-between;
}

.rop__wordcount {
  font-size: var(--font-sm, 0.875rem);
  color: var(--app-text-muted, #64748b);
}

.rop__verified-badge {
  font-size: var(--font-xs, 0.75rem);
  font-weight: 600;
  color: var(--app-success, #16a34a);
  background: color-mix(in srgb, var(--app-success, #16a34a) 10%, transparent);
  padding: 0.2em 0.6em;
  border-radius: var(--radius-full, 9999px);
}

.rop__hallucination-badge {
  display: flex;
  align-items: flex-start;
  gap: var(--space-2, 0.5rem);
  padding: var(--space-3, 0.75rem) var(--space-4, 1rem);
  background: color-mix(in srgb, var(--app-danger, #dc2626) 8%, transparent);
  border: 1px solid color-mix(in srgb, var(--app-danger, #dc2626) 30%, transparent);
  border-radius: var(--radius-md, 0.5rem);
  font-size: var(--font-sm, 0.875rem);
  color: var(--app-danger, #dc2626);
}

.rop__textarea {
  width: 100%;
  min-height: 20rem;
  padding: var(--space-3, 0.75rem);
  font-family: var(--font-mono, monospace);
  font-size: var(--font-sm, 0.875rem);
  line-height: 1.6;
  border: 1px solid var(--app-border, #e2e8f0);
  border-radius: var(--radius-md, 0.5rem);
  background: var(--app-surface, #fff);
  color: var(--app-text, #1e293b);
  resize: vertical;
  box-sizing: border-box;
}

.rop__textarea:focus {
  outline: 2px solid var(--app-accent, #6366f1);
  outline-offset: 2px;
}

/* ── Buttons (inherit app-wide classes) ──────────────────────────── */

.btn-generate {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2, 0.5rem);
  padding: var(--space-2, 0.5rem) var(--space-4, 1rem);
  background: var(--app-accent, #6366f1);
  color: #fff;
  border: none;
  border-radius: var(--radius-md, 0.5rem);
  font-size: var(--font-sm, 0.875rem);
  font-weight: 500;
  cursor: pointer;
  transition: background 0.15s;
  white-space: nowrap;
}

.btn-generate:hover:not(:disabled) { background: var(--app-accent-hover, #4f46e5); }
.btn-generate:disabled { opacity: 0.6; cursor: not-allowed; }

.btn-download {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2, 0.5rem);
  padding: var(--space-2, 0.5rem) var(--space-4, 1rem);
  background: var(--app-surface-alt, #f8fafc);
  color: var(--app-text, #1e293b);
  border: 1px solid var(--app-border, #e2e8f0);
  border-radius: var(--radius-md, 0.5rem);
  font-size: var(--font-sm, 0.875rem);
  font-weight: 500;
  cursor: pointer;
  transition: background 0.15s;
  align-self: flex-start;
}

.btn-download:hover { background: var(--app-border, #e2e8f0); }

/* ── Review gate ──────────────────────────────────────────────────── */

.rop__review {
  display: flex;
  flex-direction: column;
  gap: var(--space-4, 1rem);
}

.rop__review-intro {
  font-size: var(--font-sm, 0.875rem);
  color: var(--app-text-muted, #64748b);
  margin: 0;
  padding: var(--space-3, 0.75rem) var(--space-4, 1rem);
  background: color-mix(in srgb, var(--app-accent, #6366f1) 6%, transparent);
  border: 1px solid color-mix(in srgb, var(--app-accent, #6366f1) 20%, transparent);
  border-radius: var(--radius-md, 0.5rem);
}

.rop__review-section {
  display: flex;
  flex-direction: column;
  gap: var(--space-3, 0.75rem);
  padding: var(--space-3, 0.75rem) var(--space-4, 1rem);
  background: var(--app-surface-alt, #f8fafc);
  border: 1px solid var(--app-border, #e2e8f0);
  border-radius: var(--radius-md, 0.5rem);
}

.rop__review-section-title {
  font-size: var(--font-sm, 0.875rem);
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--app-text-muted, #64748b);
  margin: 0;
}

.rop__review-hint {
  font-size: var(--font-xs, 0.75rem);
  color: var(--app-text-muted, #64748b);
  margin: 0;
}

.rop__review-removed {
  font-size: var(--font-xs, 0.75rem);
  color: var(--app-danger, #dc2626);
  margin: 0;
}

/* Skills chips */
.rop__skill-chips {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2, 0.5rem);
}

.rop__skill-chip {
  display: inline-flex;
  align-items: center;
  gap: var(--space-1, 0.25rem);
  padding: 0.3em 0.75em;
  border-radius: var(--radius-full, 9999px);
  font-size: var(--font-sm, 0.875rem);
  border: 1.5px solid var(--app-border, #e2e8f0);
  background: var(--app-surface, #fff);
  cursor: pointer;
  user-select: none;
  transition: background 0.1s, border-color 0.1s;
  color: var(--app-text-muted, #64748b);
}

.rop__skill-chip--approved {
  border-color: var(--app-success, #16a34a);
  background: color-mix(in srgb, var(--app-success, #16a34a) 10%, transparent);
  color: var(--app-success, #16a34a);
  font-weight: 500;
}

.rop__skill-checkbox {
  accent-color: var(--app-success, #16a34a);
  width: 14px;
  height: 14px;
}

/* Diff pair layout */
.rop__diff-pair {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--space-3, 0.75rem);
}

.rop__diff-col {
  display: flex;
  flex-direction: column;
  gap: var(--space-1, 0.25rem);
  padding: var(--space-2, 0.5rem) var(--space-3, 0.75rem);
  border-radius: var(--radius-sm, 0.25rem);
  font-size: var(--font-sm, 0.875rem);
}

.rop__diff-col--original {
  background: color-mix(in srgb, var(--app-danger, #dc2626) 5%, transparent);
  border: 1px solid color-mix(in srgb, var(--app-danger, #dc2626) 20%, transparent);
}

.rop__diff-col--proposed {
  background: color-mix(in srgb, var(--app-success, #16a34a) 5%, transparent);
  border: 1px solid color-mix(in srgb, var(--app-success, #16a34a) 20%, transparent);
}

.rop__diff-label {
  font-size: var(--font-xs, 0.75rem);
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--app-text-muted, #64748b);
}

.rop__diff-text {
  margin: 0;
  line-height: 1.5;
  color: var(--app-text, #1e293b);
}

.rop__bullet-list {
  margin: 0;
  padding-left: 1.25rem;
  line-height: 1.5;
  color: var(--app-text, #1e293b);
}

/* Experience entry */
.rop__exp-entry {
  display: flex;
  flex-direction: column;
  gap: var(--space-2, 0.5rem);
}

.rop__exp-header {
  display: flex;
  align-items: center;
  gap: var(--space-2, 0.5rem);
  flex-wrap: wrap;
}

.rop__exp-company {
  font-size: var(--font-sm, 0.875rem);
  color: var(--app-text-muted, #64748b);
}

/* Accept toggle */
.rop__accept-toggle {
  display: inline-flex;
  align-items: center;
  gap: var(--space-1, 0.25rem);
  font-size: var(--font-sm, 0.875rem);
  cursor: pointer;
  color: var(--app-text, #1e293b);
}

.rop__accept-toggle--inline {
  margin-left: auto;
}

/* Download row */
.rop__download-row {
  display: flex;
  gap: var(--space-2, 0.5rem);
  flex-wrap: wrap;
}

/* History */
.rop__history {
  display: flex;
  flex-direction: column;
  gap: var(--space-2, 0.5rem);
}

.rop__history-toggle {
  display: inline-flex;
  align-items: center;
  gap: var(--space-1, 0.25rem);
  background: none;
  border: none;
  color: var(--app-accent, #6366f1);
  font-size: var(--font-sm, 0.875rem);
  cursor: pointer;
  padding: 0;
}

.rop__history-list {
  display: flex;
  flex-direction: column;
  gap: var(--space-1, 0.25rem);
}

.rop__history-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--space-2, 0.5rem) var(--space-3, 0.75rem);
  background: var(--app-surface-alt, #f8fafc);
  border: 1px solid var(--app-border, #e2e8f0);
  border-radius: var(--radius-sm, 0.25rem);
  font-size: var(--font-sm, 0.875rem);
}

.rop__history-date {
  color: var(--app-text-muted, #64748b);
  font-variant-numeric: tabular-nums;
}

.rop__history-restore {
  background: none;
  border: 1px solid var(--app-border, #e2e8f0);
  border-radius: var(--radius-sm, 0.25rem);
  padding: 0.2em 0.6em;
  font-size: var(--font-xs, 0.75rem);
  cursor: pointer;
  color: var(--app-text, #1e293b);
  transition: background 0.1s;
}

.rop__history-restore:hover { background: var(--app-border, #e2e8f0); }

/* ── Skill chip group (chip + optional gap framing below) ─────── */

.rop__skill-chip-group {
  display: flex;
  flex-direction: column;
  gap: var(--space-2, 0.5rem);
  /* Don't wrap the chip and its framing panel onto separate lines */
  flex-basis: 100%;
}

/* Keep the chip itself inline; only expand when framing is shown */
.rop__skill-chip-group:has(.rop__gap-framing) {
  background: var(--app-surface-alt, #f8fafc);
  border: 1px solid var(--app-border, #e2e8f0);
  border-radius: var(--radius-md, 0.5rem);
  padding: var(--space-2, 0.5rem) var(--space-3, 0.75rem);
}

/* Gap framing panel */
.rop__gap-framing {
  display: flex;
  flex-direction: column;
  gap: var(--space-2, 0.5rem);
  padding-top: var(--space-2, 0.5rem);
  border-top: 1px dashed var(--app-border, #e2e8f0);
}

.rop__gap-framing-label {
  font-size: var(--font-xs, 0.75rem);
  font-weight: 600;
  color: var(--app-text-muted, #64748b);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.rop__gap-framing-modes {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-3, 0.75rem);
}

.rop__framing-option {
  display: inline-flex;
  align-items: center;
  gap: var(--space-1, 0.25rem);
  font-size: var(--font-sm, 0.875rem);
  cursor: pointer;
  color: var(--app-text, #1e293b);
}

.rop__framing-context {
  width: 100%;
  padding: var(--space-2, 0.5rem) var(--space-3, 0.75rem);
  font-size: var(--font-sm, 0.875rem);
  font-family: inherit;
  line-height: 1.5;
  border: 1px solid var(--app-border, #e2e8f0);
  border-radius: var(--radius-sm, 0.25rem);
  background: var(--app-surface, #fff);
  color: var(--app-text, #1e293b);
  resize: vertical;
  box-sizing: border-box;
}

.rop__framing-context:focus {
  outline: 2px solid var(--app-accent, #6366f1);
  outline-offset: 2px;
}

/* ── Preview panel ────────────────────────────────────────────── */

.rop__preview {
  display: flex;
  flex-direction: column;
  gap: var(--space-3, 0.75rem);
}

.rop__preview-badge {
  font-size: var(--font-xs, 0.75rem);
  font-weight: 600;
  color: var(--app-warning, #f59e0b);
  background: color-mix(in srgb, var(--app-warning, #f59e0b) 12%, transparent);
  padding: 0.2em 0.6em;
  border-radius: var(--radius-full, 9999px);
}

.rop__textarea--preview {
  background: color-mix(in srgb, var(--app-accent, #6366f1) 3%, var(--app-surface, #fff));
  cursor: default;
}

.rop__preview-hint {
  font-size: var(--font-sm, 0.875rem);
  color: var(--app-text-muted, #64748b);
  margin: 0;
}

.rop__preview-actions {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2, 0.5rem);
  align-items: center;
}

.btn-approve {
  background: var(--app-success, #16a34a);
}

.btn-approve:hover:not(:disabled) {
  background: color-mix(in srgb, var(--app-success, #16a34a) 85%, black);
}

.btn-secondary {
  display: inline-flex;
  align-items: center;
  gap: var(--space-1, 0.25rem);
  padding: var(--space-2, 0.5rem) var(--space-3, 0.75rem);
  background: none;
  color: var(--app-text-muted, #64748b);
  border: 1px solid var(--app-border, #e2e8f0);
  border-radius: var(--radius-md, 0.5rem);
  font-size: var(--font-sm, 0.875rem);
  cursor: pointer;
  transition: background 0.15s;
}

.btn-secondary:hover { background: var(--app-surface-alt, #f8fafc); }

/* ── Review trigger (modal CTA) ───────────────────────────────── */

.rop__review-trigger {
  display: flex;
  flex-direction: column;
  gap: var(--space-3, 0.75rem);
  padding: var(--space-4, 1rem);
  background: color-mix(in srgb, var(--app-accent, #6366f1) 6%, transparent);
  border: 1px solid color-mix(in srgb, var(--app-accent, #6366f1) 20%, transparent);
  border-radius: var(--radius-md, 0.5rem);
}

/* ── Save to library ──────────────────────────────────────────── */

.rop__save-to-library {
  display: flex;
  flex-direction: column;
  gap: var(--space-2, 0.5rem);
}

.rop__save-toggle {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2, 0.5rem);
  font-size: var(--font-sm, 0.875rem);
  color: var(--app-text, #1e293b);
  cursor: pointer;
  user-select: none;
}

.rop__resume-name-input {
  padding: var(--space-2, 0.5rem) var(--space-3, 0.75rem);
  font-size: var(--font-sm, 0.875rem);
  font-family: inherit;
  border: 1px solid var(--app-border, #e2e8f0);
  border-radius: var(--radius-sm, 0.25rem);
  background: var(--app-surface, #fff);
  color: var(--app-text, #1e293b);
  box-sizing: border-box;
  width: 100%;
  max-width: 28rem;
}

.rop__resume-name-input:focus {
  outline: 2px solid var(--app-accent, #6366f1);
  outline-offset: 2px;
}

@media (max-width: 640px) {
  .rop__gaps-header { flex-direction: column; align-items: flex-start; }
  .btn-generate { width: 100%; justify-content: center; }
  .rop__diff-pair { grid-template-columns: 1fr; }
  .rop__download-row { flex-direction: column; }
  .rop__preview-actions { flex-direction: column; }
  .btn-approve, .btn-secondary { width: 100%; justify-content: center; }
  .rop__gap-framing-modes { flex-direction: column; gap: var(--space-2, 0.5rem); }
  .rop__resume-name-input { max-width: 100%; }
}
</style>
