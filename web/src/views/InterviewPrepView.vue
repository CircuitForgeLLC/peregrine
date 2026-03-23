<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useStorage } from '@vueuse/core'
import { usePrepStore } from '../stores/prep'
import { useInterviewsStore } from '../stores/interviews'
import type { PipelineJob } from '../stores/interviews'

const route  = useRoute()
const router = useRouter()

const prepStore       = usePrepStore()
const interviewsStore = useInterviewsStore()

// ── Job ID ────────────────────────────────────────────────────────────────────
const jobId = computed<number | null>(() => {
  const raw = route.params.id
  if (!raw) return null
  const n = Number(Array.isArray(raw) ? raw[0] : raw)
  return isNaN(n) ? null : n
})

// ── Current job (from interviews store) ───────────────────────────────────────
const PREP_VALID_STATUSES = ['phone_screen', 'interviewing', 'offer'] as const

const job = ref<PipelineJob | null>(null)

// ── Tabs ──────────────────────────────────────────────────────────────────────
type TabId = 'jd' | 'email' | 'letter'
const activeTab = ref<TabId>('jd')

// ── Call notes (localStorage via @vueuse/core) ────────────────────────────────
const notesKey     = computed(() => `cf-prep-notes-${jobId.value ?? 'none'}`)
const callNotes    = useStorage(notesKey, '')

// ── Page-level error (e.g. network failure during guard) ──────────────────────
const pageError = ref<string | null>(null)

// ── Routing / guard ───────────────────────────────────────────────────────────
async function guardAndLoad() {
  if (jobId.value === null) {
    router.replace('/interviews')
    return
  }

  // Ensure the interviews store is populated
  if (interviewsStore.jobs.length === 0) {
    await interviewsStore.fetchAll()
    if (interviewsStore.error) {
      // Store fetch failed — don't redirect, show error
      pageError.value = 'Failed to load job data. Please try again.'
      return
    }
  }

  const found = interviewsStore.jobs.find(j => j.id === jobId.value)
  if (!found || !PREP_VALID_STATUSES.includes(found.status as typeof PREP_VALID_STATUSES[number])) {
    router.replace('/interviews')
    return
  }

  job.value = found
  await prepStore.fetchFor(jobId.value)
}

onMounted(() => {
  guardAndLoad()
})

onUnmounted(() => {
  prepStore.clear()
})

// ── Stage badge label ─────────────────────────────────────────────────────────
function stageBadgeLabel(status: string): string {
  if (status === 'phone_screen')  return 'Phone Screen'
  if (status === 'interviewing')  return 'Interviewing'
  if (status === 'offer')         return 'Offer'
  return status
}

// ── Interview date countdown ──────────────────────────────────────────────────
interface DateCountdown {
  icon:  string
  label: string
  cls:   string
}

const interviewCountdown = computed<DateCountdown | null>(() => {
  const dateStr = job.value?.interview_date
  if (!dateStr) return null

  const today    = new Date()
  today.setHours(0, 0, 0, 0)
  const target   = new Date(dateStr)
  target.setHours(0, 0, 0, 0)
  const diffDays = Math.round((target.getTime() - today.getTime()) / 86400000)

  if (diffDays === 0)  return { icon: '🔴', label: 'TODAY',              cls: 'countdown--today'    }
  if (diffDays === 1)  return { icon: '🟡', label: 'TOMORROW',           cls: 'countdown--tomorrow' }
  if (diffDays > 1)    return { icon: '🟢', label: `in ${diffDays} days`, cls: 'countdown--future'   }
  // Past
  const ago = Math.abs(diffDays)
  return { icon: '', label: `was ${ago} day${ago !== 1 ? 's' : ''} ago`, cls: 'countdown--past' }
})

// ── Research state helpers ────────────────────────────────────────────────────
const taskStatus  = computed(() => prepStore.taskStatus)
const isRunning   = computed(() => taskStatus.value.status === 'queued' || taskStatus.value.status === 'running')
const hasFailed   = computed(() => taskStatus.value.status === 'failed')
const hasResearch = computed(() => !!prepStore.research)

// Stage label during generation
const stageLabel = computed(() => {
  const s = taskStatus.value.stage
  if (s) return s
  return taskStatus.value.status === 'queued' ? 'Queued…' : 'Analyzing…'
})

// Generated-at caption
const generatedAtLabel = computed(() => {
  const ts = prepStore.research?.generated_at
  if (!ts) return null
  const d = new Date(ts)
  return d.toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })
})

// ── Research sections ─────────────────────────────────────────────────────────
interface ResearchSection {
  icon:    string
  title:   string
  content: string
  cls?:    string
  caption?: string
}

const researchSections = computed<ResearchSection[]>(() => {
  const r = prepStore.research
  if (!r) return []

  const sections: ResearchSection[] = []

  if (r.talking_points?.trim()) {
    sections.push({ icon: '🎯', title: 'Talking Points', content: r.talking_points })
  }
  if (r.company_brief?.trim()) {
    sections.push({ icon: '🏢', title: 'Company Overview', content: r.company_brief })
  }
  if (r.ceo_brief?.trim()) {
    sections.push({ icon: '👤', title: 'Leadership & Culture', content: r.ceo_brief })
  }
  if (r.tech_brief?.trim()) {
    sections.push({ icon: '⚙️', title: 'Tech Stack & Product', content: r.tech_brief })
  }
  if (r.funding_brief?.trim()) {
    sections.push({ icon: '💰', title: 'Funding & Market Position', content: r.funding_brief })
  }
  if (r.red_flags?.trim() && !/no significant red flags/i.test(r.red_flags)) {
    sections.push({ icon: '⚠️', title: 'Red Flags & Watch-outs', content: r.red_flags, cls: 'section--warning' })
  }
  if (r.accessibility_brief?.trim()) {
    sections.push({
      icon:    '♿',
      title:   'Inclusion & Accessibility',
      content: r.accessibility_brief,
      caption: 'For your personal evaluation — not disclosed in any application.',
    })
  }

  return sections
})

// ── Match score badge ─────────────────────────────────────────────────────────
const matchScore = computed(() => prepStore.fullJob?.match_score ?? null)

function matchScoreBadge(score: number | null): { icon: string; cls: string } {
  if (score === null) return { icon: '—', cls: 'score--none' }
  if (score >= 70)   return { icon: `🟢 ${score}%`, cls: 'score--high' }
  if (score >= 40)   return { icon: `🟡 ${score}%`, cls: 'score--mid'  }
  return                    { icon: `🔴 ${score}%`, cls: 'score--low'  }
}

// ── Keyword gaps ──────────────────────────────────────────────────────────────
const keywordGaps = computed<string[]>(() => {
  const raw = prepStore.fullJob?.keyword_gaps
  if (!raw) return []
  try {
    const parsed = JSON.parse(raw)
    if (Array.isArray(parsed)) return parsed.map(String)
  } catch {
    // Fall through: return raw as single item
  }
  return [raw]
})

// ── Generate / refresh ────────────────────────────────────────────────────────
async function onGenerate() {
  if (jobId.value === null) return
  await prepStore.generateResearch(jobId.value)
}
</script>

<template>
  <div class="prep-view">
    <!-- Loading skeleton while interviews store loads -->
    <div v-if="interviewsStore.loading && !job" class="prep-loading" aria-live="polite">
      Loading…
    </div>

    <template v-else-if="job">
      <div class="prep-layout">
        <!-- ══════════════ LEFT COLUMN ══════════════ -->
        <aside class="prep-left" aria-label="Job overview and research">

          <!-- Back link -->
          <RouterLink to="/interviews" class="back-link">← Back to Interviews</RouterLink>

          <!-- Job header -->
          <header class="job-header">
            <h1 class="job-title">{{ job.title }}</h1>
            <p class="job-company">{{ job.company }}</p>

            <div class="job-meta">
              <span class="stage-badge" :class="`stage-badge--${job.status}`">
                {{ stageBadgeLabel(job.status) }}
              </span>

              <span
                v-if="interviewCountdown"
                class="countdown-chip"
                :class="interviewCountdown.cls"
              >
                <span v-if="interviewCountdown.icon" aria-hidden="true">{{ interviewCountdown.icon }}</span>
                {{ interviewCountdown.label }}
              </span>
            </div>

            <a
              v-if="job.url"
              :href="job.url"
              target="_blank"
              rel="noopener noreferrer"
              class="btn-link-out"
            >
              Open job listing ↗
            </a>
          </header>

          <!-- Research controls -->
          <section class="research-controls" aria-label="Research controls">
            <!-- No research and no active task → show generate button -->
            <template v-if="!hasResearch && !isRunning && !hasFailed">
              <button class="btn-primary" @click="onGenerate" :disabled="prepStore.loading">
                Generate research brief
              </button>
            </template>

            <!-- Task running/queued → spinner + stage -->
            <template v-else-if="isRunning">
              <div class="research-running" aria-live="polite" aria-atomic="true">
                <span class="spinner" aria-hidden="true"></span>
                <span>{{ stageLabel }}</span>
              </div>
            </template>

            <!-- Task failed → error + retry -->
            <template v-else-if="hasFailed">
              <div class="research-error" role="alert">
                <span>⚠️ {{ taskStatus.message ?? 'Research generation failed.' }}</span>
                <button class="btn-secondary" @click="onGenerate">Retry</button>
              </div>
            </template>

            <!-- Research exists (completed or no task but research present) → show refresh -->
            <template v-else-if="hasResearch">
              <div class="research-generated">
                <span v-if="generatedAtLabel" class="research-ts">Generated: {{ generatedAtLabel }}</span>
                <button
                  class="btn-secondary"
                  @click="onGenerate"
                  :disabled="isRunning"
                >
                  Refresh
                </button>
              </div>
            </template>
          </section>

          <!-- Error banner (store-level) -->
          <div v-if="prepStore.error" class="error-banner" role="alert">
            {{ prepStore.error }}
          </div>

          <!-- Research sections -->
          <div v-if="hasResearch" class="research-sections">
            <section
              v-for="sec in researchSections"
              :key="sec.title"
              class="research-section"
              :class="sec.cls"
            >
              <h2 class="section-title">
                <span aria-hidden="true">{{ sec.icon }}</span> {{ sec.title }}
              </h2>
              <p v-if="sec.caption" class="section-caption">{{ sec.caption }}</p>
              <div class="section-body">{{ sec.content }}</div>
            </section>
          </div>

          <!-- Empty state: no research yet and not loading -->
          <div v-else-if="!isRunning && !prepStore.loading" class="research-empty">
            <span class="empty-bird">🦅</span>
            <p>Generate a research brief to see company info, talking points, and more.</p>
          </div>

        </aside>

        <!-- ══════════════ RIGHT COLUMN ══════════════ -->
        <main class="prep-right" aria-label="Job details">

          <!-- Tab bar -->
          <div class="tab-bar" role="tablist" aria-label="Job details tabs">
            <button
              id="tab-jd"
              class="tab-btn"
              :class="{ 'tab-btn--active': activeTab === 'jd' }"
              role="tab"
              :aria-selected="activeTab === 'jd'"
              aria-controls="tabpanel-jd"
              @click="activeTab = 'jd'"
            >
              Job Description
            </button>
            <button
              id="tab-email"
              class="tab-btn"
              :class="{ 'tab-btn--active': activeTab === 'email' }"
              role="tab"
              :aria-selected="activeTab === 'email'"
              aria-controls="tabpanel-email"
              @click="activeTab = 'email'"
            >
              Email History
              <span v-if="prepStore.contacts.length" class="tab-count">{{ prepStore.contacts.length }}</span>
            </button>
            <button
              id="tab-letter"
              class="tab-btn"
              :class="{ 'tab-btn--active': activeTab === 'letter' }"
              role="tab"
              :aria-selected="activeTab === 'letter'"
              aria-controls="tabpanel-letter"
              @click="activeTab = 'letter'"
            >
              Cover Letter
            </button>
          </div>

          <!-- ── JD tab ── -->
          <div
            v-show="activeTab === 'jd'"
            id="tabpanel-jd"
            class="tab-panel"
            role="tabpanel"
            aria-labelledby="tab-jd"
          >
            <div class="jd-meta">
              <span
                class="score-badge"
                :class="matchScoreBadge(matchScore).cls"
                :aria-label="`Match score: ${matchScore ?? 'unknown'}%`"
              >
                {{ matchScoreBadge(matchScore).icon }}
              </span>
              <div v-if="keywordGaps.length" class="keyword-gaps">
                <span class="keyword-gaps-label">Keyword gaps:</span>
                <span class="keyword-gaps-list">{{ keywordGaps.join(', ') }}</span>
              </div>
            </div>

            <div v-if="prepStore.fullJob?.description" class="jd-body">
              {{ prepStore.fullJob.description }}
            </div>
            <div v-else class="tab-empty">
              <span class="empty-bird">🦅</span>
              <p>No job description available.</p>
            </div>
          </div>

          <!-- ── Email tab ── -->
          <div
            v-show="activeTab === 'email'"
            id="tabpanel-email"
            class="tab-panel"
            role="tabpanel"
            aria-labelledby="tab-email"
          >
            <div v-if="prepStore.contactsError" class="error-state" role="alert">
              {{ prepStore.contactsError }}
            </div>
            <template v-else-if="prepStore.contacts.length">
              <div
                v-for="contact in prepStore.contacts"
                :key="contact.id"
                class="email-card"
              >
                <div class="email-header">
                  <span class="email-dir" :title="contact.direction === 'inbound' ? 'Inbound' : 'Outbound'">
                    {{ contact.direction === 'inbound' ? '📥' : '📤' }}
                  </span>
                  <span class="email-subject">{{ contact.subject ?? '(no subject)' }}</span>
                  <span class="email-date" v-if="contact.received_at">
                    {{ new Date(contact.received_at).toLocaleDateString() }}
                  </span>
                </div>
                <div class="email-from" v-if="contact.from_addr">{{ contact.from_addr }}</div>
                <div class="email-body" v-if="contact.body">{{ contact.body.slice(0, 500) }}{{ contact.body.length > 500 ? '…' : '' }}</div>
              </div>
            </template>
            <div v-else class="tab-empty">
              <span class="empty-bird">🦅</span>
              <p>No email history for this job.</p>
            </div>
          </div>

          <!-- ── Cover letter tab ── -->
          <div
            v-show="activeTab === 'letter'"
            id="tabpanel-letter"
            class="tab-panel"
            role="tabpanel"
            aria-labelledby="tab-letter"
          >
            <div v-if="prepStore.fullJob?.cover_letter" class="letter-body">
              {{ prepStore.fullJob.cover_letter }}
            </div>
            <div v-else class="tab-empty">
              <span class="empty-bird">🦅</span>
              <p>No cover letter generated yet.</p>
            </div>
          </div>

          <!-- ── Call notes ── -->
          <section class="call-notes" aria-label="Call notes">
            <h2 class="call-notes-title">Call Notes</h2>
            <textarea
              v-model="callNotes"
              class="call-notes-textarea"
              placeholder="Jot down notes during your call…"
              aria-label="Call notes — saved locally"
            ></textarea>
            <p class="call-notes-caption">Notes are saved locally — they won't sync between devices.</p>
          </section>

        </main>
      </div>
    </template>

    <!-- Network/load error — don't redirect, show message -->
    <div v-else-if="pageError" class="error-banner" role="alert">
      {{ pageError }}
    </div>

    <!-- Fallback while redirecting -->
    <div v-else class="prep-loading" aria-live="polite">
      Redirecting…
    </div>
  </div>
</template>

<style scoped>
/* ── Layout ─────────────────────────────────────────────────────────────── */
.prep-view {
  padding: var(--space-4) var(--space-4) var(--space-12);
  max-width: 1200px;
  margin: 0 auto;
}

.prep-layout {
  display: grid;
  grid-template-columns: 40% 1fr;
  gap: var(--space-6);
  align-items: start;
}

/* Mobile: single column */
@media (max-width: 1023px) {
  .prep-layout {
    grid-template-columns: 1fr;
  }
  .prep-right {
    order: 2;
  }
  .prep-left {
    order: 1;
  }
}

.prep-left {
  position: sticky;
  top: calc(var(--nav-height, 4rem) + var(--space-4));
  max-height: calc(100vh - var(--nav-height, 4rem) - var(--space-8));
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
  /* On mobile, don't stick */
}

@media (max-width: 1023px) {
  .prep-left {
    position: static;
    max-height: none;
    overflow-y: visible;
  }
}

.prep-right {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
  min-width: 0;
}

/* ── Loading ─────────────────────────────────────────────────────────────── */
.prep-loading {
  text-align: center;
  padding: var(--space-16);
  color: var(--color-text-muted);
  font-size: var(--text-sm);
}

/* ── Back link ──────────────────────────────────────────────────────────── */
.back-link {
  font-size: var(--text-sm);
  color: var(--app-primary);
  text-decoration: none;
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
}
.back-link:hover { text-decoration: underline; }

/* ── Job header ─────────────────────────────────────────────────────────── */
.job-header {
  background: var(--color-surface-raised);
  border-radius: var(--radius-lg);
  padding: var(--space-4);
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  border: 1px solid var(--color-border-light);
}

.job-title {
  font-family: var(--font-display);
  font-size: var(--text-xl);
  color: var(--color-text);
  line-height: 1.3;
}

.job-company {
  font-size: var(--text-base);
  color: var(--color-text-muted);
  margin: 0;
  font-weight: 600;
}

.job-meta {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  flex-wrap: wrap;
}

/* Stage badges */
.stage-badge {
  display: inline-block;
  padding: 2px 10px;
  border-radius: var(--radius-full);
  font-size: var(--text-xs);
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: .04em;
}
.stage-badge--phone_screen {
  background: color-mix(in srgb, var(--status-phone) 12%, var(--color-surface-raised));
  color: var(--status-phone);
}
.stage-badge--interviewing {
  background: color-mix(in srgb, var(--status-interview) 12%, var(--color-surface-raised));
  color: var(--status-interview);
}
.stage-badge--offer {
  background: color-mix(in srgb, var(--status-offer) 12%, var(--color-surface-raised));
  color: var(--status-offer);
}

/* Countdown chip */
.countdown-chip {
  font-size: var(--text-xs);
  font-weight: 700;
  padding: 2px 8px;
  border-radius: var(--radius-full);
  display: inline-flex;
  align-items: center;
  gap: 4px;
}
.countdown--today    { background: color-mix(in srgb, var(--color-error) 12%, var(--color-surface-raised)); color: var(--color-error); }
.countdown--tomorrow { background: color-mix(in srgb, var(--color-warning) 12%, var(--color-surface-raised)); color: var(--color-warning); }
.countdown--future   { background: color-mix(in srgb, var(--color-success) 12%, var(--color-surface-raised)); color: var(--color-success); }
.countdown--past     { background: var(--color-surface-alt); color: var(--color-text-muted); }

.btn-link-out {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: var(--text-sm);
  color: var(--app-primary);
  text-decoration: none;
  width: fit-content;
}
.btn-link-out:hover { text-decoration: underline; }

/* ── Research controls ──────────────────────────────────────────────────── */
.research-controls {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.btn-primary {
  background: var(--app-primary);
  color: var(--color-text-inverse);
  border: none;
  border-radius: var(--radius-md);
  padding: var(--space-2) var(--space-4);
  font-size: var(--text-sm);
  font-weight: 600;
  cursor: pointer;
  transition: background var(--transition);
}
.btn-primary:hover:not(:disabled) { background: var(--app-primary-hover); }
.btn-primary:disabled { opacity: 0.6; cursor: default; }

.btn-secondary {
  background: none;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  padding: var(--space-1) var(--space-3);
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--app-primary);
  cursor: pointer;
  transition: background var(--transition);
}
.btn-secondary:hover:not(:disabled) { background: var(--color-surface-alt); }
.btn-secondary:disabled { opacity: 0.6; cursor: default; }

.research-running {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  font-size: var(--text-sm);
  color: var(--color-info);
}

/* Spinner */
.spinner {
  width: 16px;
  height: 16px;
  border: 2px solid color-mix(in srgb, var(--color-info) 25%, transparent);
  border-top-color: var(--color-info);
  border-radius: 50%;
  animation: spin 700ms linear infinite;
  flex-shrink: 0;
}
@keyframes spin { to { transform: rotate(360deg); } }
@media (prefers-reduced-motion: reduce) {
  .spinner { animation: none; border-top-color: var(--color-info); }
}

.research-generated {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  flex-wrap: wrap;
}
.research-ts {
  font-size: var(--text-xs);
  color: var(--color-text-muted);
}

.research-error {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  flex-wrap: wrap;
  background: color-mix(in srgb, var(--color-error) 8%, var(--color-surface));
  border: 1px solid color-mix(in srgb, var(--color-error) 25%, transparent);
  border-radius: var(--radius-md);
  padding: var(--space-2) var(--space-3);
  font-size: var(--text-sm);
  color: var(--color-error);
}

/* ── Error banner ────────────────────────────────────────────────────────── */
.error-banner {
  background: color-mix(in srgb, var(--color-error) 10%, var(--color-surface));
  color: var(--color-error);
  padding: var(--space-2) var(--space-3);
  border-radius: var(--radius-md);
  font-size: var(--text-sm);
}

/* Inline error state for tab panels (e.g. contacts fetch failure) */
.error-state {
  background: color-mix(in srgb, var(--color-error) 8%, var(--color-surface));
  color: var(--color-error);
  border: 1px solid color-mix(in srgb, var(--color-error) 25%, transparent);
  border-radius: var(--radius-md);
  padding: var(--space-3) var(--space-4);
  font-size: var(--text-sm);
}

/* ── Research sections ───────────────────────────────────────────────────── */
.research-sections {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.research-section {
  background: var(--color-surface-raised);
  border: 1px solid var(--color-border-light);
  border-radius: var(--radius-md);
  padding: var(--space-3) var(--space-4);
}

.research-section.section--warning {
  background: color-mix(in srgb, var(--color-warning) 8%, var(--color-surface));
  border-color: color-mix(in srgb, var(--color-warning) 30%, transparent);
}

.section-title {
  font-family: var(--font-display);
  font-size: var(--text-sm);
  font-weight: 700;
  color: var(--color-text);
  margin-bottom: var(--space-2);
  display: flex;
  align-items: center;
  gap: var(--space-1);
}

.section-caption {
  font-size: var(--text-xs);
  color: var(--color-text-muted);
  font-style: italic;
  margin: 0 0 var(--space-2);
}

.section-body {
  font-size: var(--text-sm);
  color: var(--color-text);
  line-height: 1.6;
  white-space: pre-wrap;
}

/* ── Empty state ─────────────────────────────────────────────────────────── */
.research-empty,
.tab-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-8) var(--space-4);
  color: var(--color-text-muted);
  text-align: center;
}
.empty-bird {
  font-size: 2rem;
}
.tab-empty p {
  font-size: var(--text-sm);
  margin: 0;
}

/* ── Tab bar ─────────────────────────────────────────────────────────────── */
.tab-bar {
  display: flex;
  gap: 2px;
  border-bottom: 2px solid var(--color-border-light);
  overflow-x: auto;
}

.tab-btn {
  background: none;
  border: none;
  border-bottom: 3px solid transparent;
  padding: var(--space-2) var(--space-3);
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--color-text-muted);
  cursor: pointer;
  white-space: nowrap;
  transition: color var(--transition), border-color var(--transition);
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
  margin-bottom: -2px;
}
.tab-btn:hover { color: var(--app-primary); }
.tab-btn--active {
  color: var(--app-primary);
  border-bottom-color: var(--app-primary);
}

.tab-count {
  background: var(--color-surface-alt);
  border-radius: var(--radius-full);
  padding: 1px 6px;
  font-size: var(--text-xs);
  font-weight: 700;
  color: var(--color-text-muted);
}

/* ── Tab panels ──────────────────────────────────────────────────────────── */
.tab-panel {
  background: var(--color-surface-raised);
  border: 1px solid var(--color-border-light);
  border-radius: var(--radius-md);
  padding: var(--space-4);
  min-height: 200px;
}

/* JD tab */
.jd-meta {
  display: flex;
  align-items: flex-start;
  flex-wrap: wrap;
  gap: var(--space-3);
  margin-bottom: var(--space-3);
}

.score-badge {
  font-size: var(--text-sm);
  font-weight: 700;
  padding: 2px 10px;
  border-radius: var(--radius-full);
}
.score--high { background: color-mix(in srgb, var(--color-success) 12%, var(--color-surface-raised)); color: var(--color-success); }
.score--mid  { background: color-mix(in srgb, var(--color-warning) 12%, var(--color-surface-raised)); color: var(--color-warning); }
.score--low  { background: color-mix(in srgb, var(--color-error)   12%, var(--color-surface-raised)); color: var(--color-error);   }
.score--none { background: var(--color-surface-alt); color: var(--color-text-muted); }

.keyword-gaps {
  font-size: var(--text-xs);
  color: var(--color-text-muted);
  display: flex;
  gap: var(--space-1);
  flex-wrap: wrap;
  align-items: baseline;
}
.keyword-gaps-label { font-weight: 700; }

.jd-body {
  font-size: var(--text-sm);
  color: var(--color-text);
  line-height: 1.7;
  white-space: pre-wrap;
  max-height: 60vh;
  overflow-y: auto;
}

/* Email tab */
.email-card {
  border: 1px solid var(--color-border-light);
  border-radius: var(--radius-md);
  padding: var(--space-3);
  background: var(--color-surface);
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  margin-bottom: var(--space-3);
}
.email-card:last-child { margin-bottom: 0; }

.email-header {
  display: flex;
  align-items: baseline;
  gap: var(--space-2);
  flex-wrap: wrap;
}
.email-dir { font-size: 1rem; }
.email-subject {
  font-weight: 600;
  font-size: var(--text-sm);
  flex: 1;
  min-width: 0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.email-date {
  font-size: var(--text-xs);
  color: var(--color-text-muted);
  flex-shrink: 0;
}
.email-from {
  font-size: var(--text-xs);
  color: var(--color-text-muted);
}
.email-body {
  font-size: var(--text-xs);
  color: var(--color-text);
  line-height: 1.5;
  white-space: pre-wrap;
}

/* Cover letter tab */
.letter-body {
  font-size: var(--text-sm);
  color: var(--color-text);
  line-height: 1.8;
  white-space: pre-wrap;
}

/* ── Call notes ──────────────────────────────────────────────────────────── */
.call-notes {
  background: var(--color-surface-raised);
  border: 1px solid var(--color-border-light);
  border-radius: var(--radius-md);
  padding: var(--space-4);
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.call-notes-title {
  font-family: var(--font-display);
  font-size: var(--text-sm);
  font-weight: 700;
  color: var(--color-text);
}

.call-notes-textarea {
  width: 100%;
  min-height: 120px;
  resize: vertical;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  padding: var(--space-2) var(--space-3);
  font-family: var(--font-body);
  font-size: var(--text-sm);
  color: var(--color-text);
  line-height: 1.6;
  box-sizing: border-box;
}
.call-notes-textarea::placeholder { color: var(--color-text-muted); }
.call-notes-textarea:focus-visible {
  outline: 2px solid var(--app-primary);
  outline-offset: 2px;
  border-color: var(--app-primary);
}

.call-notes-caption {
  font-size: var(--text-xs);
  color: var(--color-text-muted);
  margin: 0;
  font-style: italic;
}
</style>
