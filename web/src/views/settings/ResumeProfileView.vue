<template>
  <div class="resume-profile">
    <div class="page-header">
      <h2>Resume Profile</h2>
      <a href="https://docs.circuitforge.tech/peregrine/user-guide/settings/#resume-profile" target="_blank" rel="noopener" class="help-link" aria-label="Resume Profile documentation">? Help</a>
    </div>

    <!-- Load error banner -->
    <div v-if="loadError" class="error-banner">
      Failed to load resume: {{ loadError }}
    </div>

    <!-- Empty state -->
    <div v-if="!store.hasResume && !store.loading" class="empty-state">
      <p>No resume found. Choose how to get started:</p>
      <div class="empty-actions">
        <!-- Upload -->
        <div class="empty-card">
          <h3>Upload & Parse</h3>
          <p>Upload a PDF, DOCX, or ODT and we'll extract your info automatically.</p>
          <input type="file" accept=".pdf,.docx,.odt" @change="handleFileSelect" ref="fileInput" />
          <button
            v-if="pendingFile"
            @click="handleUpload"
            :disabled="uploading"
            style="margin-top:10px"
          >{{ uploading ? 'Parsing…' : `Parse "${pendingFile.name}"` }}</button>
          <p v-if="uploadError" class="error">{{ uploadError }}</p>
        </div>
        <!-- Blank -->
        <div class="empty-card">
          <h3>Fill in Manually</h3>
          <p>Start with a blank form and fill in your details.</p>
          <button @click="store.createBlank()" :disabled="store.loading">Start from Scratch</button>
        </div>
        <!-- Wizard — self-hosted only -->
        <div v-if="!config.isCloud" class="empty-card">
          <h3>Run Setup Wizard</h3>
          <p>Walk through the onboarding wizard to set up your profile step by step.</p>
          <RouterLink to="/setup">Open Setup Wizard →</RouterLink>
        </div>
      </div>
    </div>

    <!-- Full form (when resume exists) -->
    <template v-else-if="store.hasResume">
      <!-- Replace resume via upload -->
      <section class="form-section replace-section">
        <h3>Replace Resume</h3>
        <p class="section-note">Upload a new PDF, DOCX, or ODT to re-parse and overwrite the current data.</p>
        <input type="file" accept=".pdf,.docx,.odt" @change="handleFileSelect" ref="replaceFileInput" />
        <button
          v-if="pendingFile"
          @click="handleUpload"
          :disabled="uploading"
          class="btn-primary"
          style="margin-top:10px"
        >{{ uploading ? 'Parsing…' : `Parse "${pendingFile.name}"` }}</button>
        <p v-if="uploadError" class="error">{{ uploadError }}</p>
      </section>

      <!-- Sync status label -->
      <div v-if="store.lastSynced" class="sync-status-label">
        Content synced from Resume Library — {{ fmtDate(store.lastSynced) }}.
        Changes here update the default library entry when you save.
      </div>

      <!-- Career Summary -->
      <section class="form-section">
        <h3>Career Summary</h3>
        <p class="section-note">Used in cover letter generation and as your professional introduction.</p>
        <div class="field-row">
          <label for="career-summary">Career summary</label>
          <textarea id="career-summary" v-model="store.career_summary"
                    rows="4" placeholder="2-3 sentences summarising your background and what you bring."></textarea>
        </div>
      </section>

      <!-- Personal Information -->
      <section class="form-section">
        <h3>Personal Information</h3>
        <div class="field-row">
          <label>First Name <span class="sync-label">← from My Profile</span></label>
          <input v-model="store.name" />
        </div>
        <div class="field-row">
          <label>Last Name</label>
          <input v-model="store.surname" />
        </div>
        <div class="field-row">
          <label>Email <span class="sync-label">← from My Profile</span></label>
          <input v-model="store.email" type="email" />
        </div>
        <div class="field-row">
          <label>Phone <span class="sync-label">← from My Profile</span></label>
          <input v-model="store.phone" type="tel" />
        </div>
        <div class="field-row">
          <label>LinkedIn URL <span class="sync-label">← from My Profile</span></label>
          <input v-model="store.linkedin_url" type="url" />
        </div>
        <div class="field-row">
          <label>Address</label>
          <input v-model="store.address" />
        </div>
        <div class="field-row">
          <label>City</label>
          <input v-model="store.city" />
        </div>
        <div class="field-row">
          <label>ZIP Code</label>
          <input v-model="store.zip_code" />
        </div>
        <div class="field-row">
          <label>Date of Birth</label>
          <input v-model="store.date_of_birth" type="date" />
        </div>
      </section>

      <!-- Work Experience -->
      <section class="form-section">
        <h3>Work Experience</h3>
        <div v-for="(entry, idx) in store.experience" :key="entry.id" class="experience-card">
          <div class="field-row">
            <label>Job Title</label>
            <input v-model="entry.title" />
          </div>
          <div class="field-row">
            <label>Company</label>
            <input v-model="entry.company" />
          </div>
          <div class="field-row">
            <label>Period</label>
            <input v-model="entry.period" placeholder="e.g. Jan 2022 – Present" />
          </div>
          <div class="field-row">
            <label>Location</label>
            <input v-model="entry.location" />
          </div>
          <div class="field-row">
            <label>Industry</label>
            <input v-model="entry.industry" />
          </div>
          <div class="field-row">
            <label>Responsibilities</label>
            <textarea v-model="entry.responsibilities" rows="4" />
          </div>
          <button class="remove-btn" @click="store.removeExperience(idx)">Remove</button>
        </div>
        <button @click="store.addExperience()">+ Add Position</button>
      </section>

      <!-- Education -->
      <section class="form-section">
        <h3>Education</h3>
        <div v-for="(edu, idx) in store.education" :key="edu.id" class="experience-card">
          <div class="experience-card__header">
            <span class="experience-card__label">Education {{ idx + 1 }}</span>
            <button class="btn-remove" @click="store.removeEducation(idx)"
                    :aria-label="`Remove education entry ${idx + 1}`">Remove</button>
          </div>
          <div class="field-row">
            <label>Institution</label>
            <input v-model="edu.institution" placeholder="University or school name" />
          </div>
          <div class="field-row-grid">
            <div class="field-row">
              <label>Degree</label>
              <input v-model="edu.degree" placeholder="e.g. B.S., M.A., Ph.D." />
            </div>
            <div class="field-row">
              <label>Field of study</label>
              <input v-model="edu.field" placeholder="e.g. Computer Science" />
            </div>
          </div>
          <div class="field-row-grid">
            <div class="field-row">
              <label>Start year</label>
              <input v-model="edu.start_date" placeholder="2015" />
            </div>
            <div class="field-row">
              <label>End year</label>
              <input v-model="edu.end_date" placeholder="2019" />
            </div>
          </div>
        </div>
        <button class="btn-secondary" @click="store.addEducation">+ Add education</button>
      </section>

      <!-- Achievements -->
      <section class="form-section">
        <h3>Achievements</h3>
        <p class="section-note">Awards, certifications, open-source projects, publications.</p>
        <div v-for="(ach, idx) in store.achievements" :key="idx" class="achievement-row">
          <input :value="ach"
                 @input="store.achievements[idx] = ($event.target as HTMLInputElement).value"
                 placeholder="Describe the achievement" />
          <button class="btn-remove" @click="store.achievements.splice(idx, 1)"
                  :aria-label="`Remove achievement ${idx + 1}`">&#x2715;</button>
        </div>
        <button class="btn-secondary" @click="store.achievements.push('')">+ Add achievement</button>
      </section>

      <!-- Preferences -->
      <section class="form-section">
        <h3>Preferences & Availability</h3>
        <div class="field-row">
          <label>Salary Min</label>
          <input v-model.number="store.salary_min" type="number" />
        </div>
        <div class="field-row">
          <label>Salary Max</label>
          <input v-model.number="store.salary_max" type="number" />
        </div>
        <div class="field-row">
          <label>Notice Period</label>
          <input v-model="store.notice_period" />
        </div>
        <label class="checkbox-row">
          <input type="checkbox" v-model="store.remote" /> Open to remote
        </label>
        <label class="checkbox-row">
          <input type="checkbox" v-model="store.relocation" /> Open to relocation
        </label>
        <label class="checkbox-row">
          <input type="checkbox" v-model="store.assessment" /> Willing to complete assessments
        </label>
        <label class="checkbox-row">
          <input type="checkbox" v-model="store.background_check" /> Willing to undergo background check
        </label>
      </section>

      <!-- Self-ID (collapsible) -->
      <section class="form-section">
        <h3>
          Self-Identification
          <button class="toggle-btn" @click="showSelfId = !showSelfId">
            {{ showSelfId ? '▲ Hide' : '▼ Show' }}
          </button>
        </h3>
        <p class="section-note">Optional. Used only for your personal tracking.</p>
        <template v-if="showSelfId">
          <div class="field-row">
            <label>Gender</label>
            <input v-model="store.gender" />
          </div>
          <div class="field-row">
            <label>Pronouns</label>
            <input v-model="store.pronouns" />
          </div>
          <div class="field-row">
            <label>Ethnicity</label>
            <input v-model="store.ethnicity" />
          </div>
          <div class="field-row">
            <label>Veteran Status</label>
            <input v-model="store.veteran_status" />
          </div>
          <div class="field-row">
            <label>Disability</label>
            <input v-model="store.disability" />
          </div>
        </template>
      </section>

      <!-- Skills & Keywords -->
      <section class="form-section">
        <h3>Skills & Keywords</h3>
        <div class="tag-section">
          <div class="tag-section-header">
            <label>Skills</label>
            <button @click="store.suggestTags('skills')" :disabled="store.suggestingField === 'skills'" class="btn-suggest">
              {{ store.suggestingField === 'skills' ? 'Thinking…' : '✦ Suggest' }}
            </button>
          </div>
          <div class="tags">
            <span v-for="skill in store.skills" :key="skill" class="tag">
              {{ skill }} <button @click="store.removeTag('skills', skill)">×</button>
            </span>
          </div>
          <div v-if="store.skillSuggestions.length > 0" class="suggestions">
            <span v-for="s in store.skillSuggestions" :key="s" class="suggestion-chip" @click="store.acceptTagSuggestion('skills', s)" title="Click to add">+ {{ s }}</span>
          </div>
          <input v-model="skillInput" @keydown.enter.prevent="store.addTag('skills', skillInput); skillInput = ''" placeholder="Add skill, press Enter" />
        </div>
        <div class="tag-section">
          <div class="tag-section-header">
            <label>Domains</label>
            <button @click="store.suggestTags('domains')" :disabled="store.suggestingField === 'domains'" class="btn-suggest">
              {{ store.suggestingField === 'domains' ? 'Thinking…' : '✦ Suggest' }}
            </button>
          </div>
          <div class="tags">
            <span v-for="domain in store.domains" :key="domain" class="tag">
              {{ domain }} <button @click="store.removeTag('domains', domain)">×</button>
            </span>
          </div>
          <div v-if="store.domainSuggestions.length > 0" class="suggestions">
            <span v-for="s in store.domainSuggestions" :key="s" class="suggestion-chip" @click="store.acceptTagSuggestion('domains', s)" title="Click to add">+ {{ s }}</span>
          </div>
          <input v-model="domainInput" @keydown.enter.prevent="store.addTag('domains', domainInput); domainInput = ''" placeholder="Add domain, press Enter" />
        </div>
        <div class="tag-section">
          <div class="tag-section-header">
            <label>Keywords</label>
            <button @click="store.suggestTags('keywords')" :disabled="store.suggestingField === 'keywords'" class="btn-suggest">
              {{ store.suggestingField === 'keywords' ? 'Thinking…' : '✦ Suggest' }}
            </button>
          </div>
          <div class="tags">
            <span v-for="kw in store.keywords" :key="kw" class="tag">
              {{ kw }} <button @click="store.removeTag('keywords', kw)">×</button>
            </span>
          </div>
          <div v-if="store.keywordSuggestions.length > 0" class="suggestions">
            <span v-for="s in store.keywordSuggestions" :key="s" class="suggestion-chip" @click="store.acceptTagSuggestion('keywords', s)" title="Click to add">+ {{ s }}</span>
          </div>
          <input v-model="kwInput" @keydown.enter.prevent="store.addTag('keywords', kwInput); kwInput = ''" placeholder="Add keyword, press Enter" />
        </div>
      </section>

      <!-- Save -->
      <div class="form-actions">
        <button @click="store.save()" :disabled="store.saving" class="btn-primary">
          {{ store.saving ? 'Saving…' : 'Save Resume' }}
        </button>
        <p v-if="store.saveError" class="error">{{ store.saveError }}</p>
      </div>
    </template>

    <div v-else class="loading">Loading…</div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { storeToRefs } from 'pinia'
import { useResumeStore } from '../../stores/settings/resume'
import { useProfileStore } from '../../stores/settings/profile'
import { useAppConfigStore } from '../../stores/appConfig'
import { useApiFetch } from '../../composables/useApi'

const store = useResumeStore()
const profileStore = useProfileStore()
const config = useAppConfigStore()
const { loadError } = storeToRefs(store)
const showSelfId = ref(false)
const skillInput = ref('')
const domainInput = ref('')
const kwInput = ref('')
const uploadError = ref<string | null>(null)
const uploading = ref(false)
const pendingFile = ref<File | null>(null)
const fileInput = ref<HTMLInputElement | null>(null)
const replaceFileInput = ref<HTMLInputElement | null>(null)

onMounted(async () => {
  await store.load()
  // Only prime identity from profile on a fresh/empty resume
  if (!store.hasResume) {
    store.syncFromProfile({
      name: profileStore.name,
      email: profileStore.email,
      phone: profileStore.phone,
      linkedin_url: profileStore.linkedin_url,
    })
  }
})

function handleFileSelect(event: Event) {
  const file = (event.target as HTMLInputElement).files?.[0]
  pendingFile.value = file ?? null
  uploadError.value = null
}

function fmtDate(iso: string) {
  return new Date(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}

async function handleUpload() {
  const file = pendingFile.value
  if (!file) return
  uploading.value = true
  uploadError.value = null
  const formData = new FormData()
  formData.append('file', file)
  const { data, error } = await useApiFetch<{ ok: boolean; data?: Record<string, unknown>; error?: string }>(
    '/api/settings/resume/upload',
    { method: 'POST', body: formData }
  )
  uploading.value = false
  if (error || !data?.ok) {
    uploadError.value = data?.error ?? (typeof error === 'string' ? error : (error?.kind === 'network' ? error.message : error?.detail ?? 'Upload failed'))
    return
  }
  pendingFile.value = null
  if (fileInput.value) fileInput.value.value = ''
  if (replaceFileInput.value) replaceFileInput.value.value = ''
  if (data.data) {
    await store.load()
  }
}
</script>

<style scoped>
.resume-profile { max-width: 720px; margin: 0 auto; padding: var(--space-4); }
.page-header { display: flex; align-items: center; gap: var(--space-3); margin-bottom: var(--space-6); }
.page-header h2 { margin-bottom: 0; }
.help-link { font-size: 0.75rem; color: var(--color-text-muted); border: 1px solid var(--color-border); border-radius: var(--radius-full); padding: 2px 8px; text-decoration: none; white-space: nowrap; flex-shrink: 0; }
.help-link:hover { color: var(--color-primary); border-color: var(--color-primary); }
h2 { font-size: 1.4rem; font-weight: 600; margin-bottom: var(--space-6); }
h3 { font-size: 1rem; font-weight: 600; margin-bottom: var(--space-3); }
.form-section { margin-bottom: var(--space-8); padding-bottom: var(--space-6); border-bottom: 1px solid var(--color-border); }
.field-row { display: flex; flex-direction: column; gap: 4px; margin-bottom: var(--space-3); }
.field-row label { font-size: 0.82rem; color: var(--color-text-muted); }
.field-row input, .field-row textarea, .field-row select {
  background: var(--color-surface-alt);
  border: 1px solid var(--color-border);
  border-radius: 6px;
  color: var(--color-text);
  padding: 7px 10px;
  font-size: 0.88rem;
  width: 100%;
  box-sizing: border-box;
}
.sync-label { font-size: 0.72rem; color: var(--color-accent); margin-left: 6px; }
.checkbox-row { display: flex; align-items: center; gap: 8px; margin-bottom: 10px; font-size: 0.88rem; color: var(--color-text); cursor: pointer; }
.experience-card { border: 1px solid var(--color-border); border-radius: 8px; padding: var(--space-4); margin-bottom: var(--space-4); }
.remove-btn {
  margin-top: 8px; padding: 4px 12px; border-radius: 4px;
  background: color-mix(in srgb, var(--color-error) 15%, transparent);
  color: var(--color-error);
  border: 1px solid color-mix(in srgb, var(--color-error) 30%, transparent);
  cursor: pointer; font-size: 0.82rem;
}
.empty-state { text-align: center; padding: var(--space-8) 0; }
.empty-actions { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: var(--space-4); margin-top: var(--space-6); }
.empty-card { background: var(--color-surface-alt); border: 1px solid var(--color-border); border-radius: 10px; padding: var(--space-4); text-align: left; }
.empty-card h3 { margin-bottom: 8px; }
.empty-card p { font-size: 0.85rem; color: var(--color-text-muted); margin-bottom: 16px; }
.empty-card button, .empty-card a { padding: 8px 16px; border-radius: 6px; font-size: 0.85rem; cursor: pointer; text-decoration: none; display: inline-block; background: var(--color-accent); color: var(--color-text-inverse); border: none; }
.tag-section { margin-bottom: var(--space-4); }
.tag-section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 6px; }
.tag-section-header label { font-size: 0.82rem; color: var(--color-text-muted); margin: 0; }
.tag-section label { font-size: 0.82rem; color: var(--color-text-muted); display: block; margin-bottom: 6px; }
.btn-suggest {
  padding: 4px 12px; border-radius: 6px;
  background: color-mix(in srgb, var(--color-accent) 15%, transparent);
  border: 1px solid color-mix(in srgb, var(--color-accent) 25%, transparent);
  color: var(--color-accent); cursor: pointer; font-size: 0.78rem; white-space: nowrap; transition: background 0.15s;
}
.btn-suggest:hover:not(:disabled) { background: color-mix(in srgb, var(--color-accent) 28%, transparent); }
.btn-suggest:disabled { opacity: 0.55; cursor: default; }
.suggestions { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 8px; }
.suggestion-chip {
  padding: 3px 10px; border-radius: 12px; font-size: 0.78rem;
  background: var(--color-surface-alt);
  border: 1px dashed var(--color-border);
  color: var(--color-text-muted); cursor: pointer; transition: all 0.15s;
}
.suggestion-chip:hover {
  background: color-mix(in srgb, var(--color-accent) 15%, transparent);
  border-color: color-mix(in srgb, var(--color-accent) 30%, transparent);
  color: var(--color-accent);
}
.tags { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 8px; }
.tag {
  padding: 3px 10px;
  background: color-mix(in srgb, var(--color-accent) 15%, transparent);
  border: 1px solid color-mix(in srgb, var(--color-accent) 30%, transparent);
  border-radius: 12px; font-size: 0.78rem; color: var(--color-accent);
  display: flex; align-items: center; gap: 5px;
}
.tag button { background: none; border: none; color: inherit; cursor: pointer; padding: 0; line-height: 1; }
.tag-section input { background: var(--color-surface-alt); border: 1px solid var(--color-border); border-radius: 6px; color: var(--color-text); padding: 6px 10px; font-size: 0.85rem; width: 100%; box-sizing: border-box; }
.form-actions { margin-top: var(--space-6); display: flex; align-items: center; gap: var(--space-4); }
.btn-primary { padding: 9px 24px; background: var(--color-accent); color: var(--color-text-inverse); border: none; border-radius: 7px; font-size: 0.9rem; cursor: pointer; font-weight: 600; }
.btn-primary:disabled { opacity: 0.5; cursor: not-allowed; }
.error { color: var(--color-error); font-size: 0.82rem; }
.error-banner {
  background: color-mix(in srgb, var(--color-error) 10%, transparent);
  border: 1px solid color-mix(in srgb, var(--color-error) 30%, transparent);
  border-radius: 6px; color: var(--color-error); font-size: 0.85rem; padding: 10px 14px; margin-bottom: var(--space-4);
}
.section-note { font-size: 0.8rem; color: var(--color-text-muted); margin-bottom: 16px; }
.toggle-btn { margin-left: 10px; padding: 2px 10px; background: transparent; border: 1px solid var(--color-border); border-radius: 4px; color: var(--color-text-muted); cursor: pointer; font-size: 0.78rem; }
.loading { text-align: center; padding: var(--space-8); color: var(--color-text-muted); }
.replace-section { background: var(--color-surface-alt); border-radius: 8px; padding: var(--space-4); }
.sync-status-label {
  font-size: 0.82rem; color: var(--color-text-muted);
  border-left: 3px solid var(--color-primary);
  padding: var(--space-2) var(--space-3);
  margin-bottom: var(--space-6);
  background: color-mix(in srgb, var(--color-primary) 6%, var(--color-surface-alt));
  border-radius: 0 var(--radius-sm) var(--radius-sm) 0;
}
.achievement-row {
  display: flex; gap: var(--space-2); align-items: center; margin-bottom: var(--space-2);
}
.achievement-row input { flex: 1; }
.btn-remove {
  background: none; border: 1px solid var(--color-border);
  border-radius: var(--radius-sm); padding: 2px var(--space-2);
  cursor: pointer; color: var(--color-text-muted); font-size: 0.8rem;
  white-space: nowrap;
}
.btn-remove:hover { color: var(--color-error, #dc2626); border-color: var(--color-error, #dc2626); }
.field-row-grid { display: grid; grid-template-columns: 1fr 1fr; gap: var(--space-3); }
.btn-secondary {
  padding: 7px 16px; background: transparent;
  border: 1px solid var(--color-border); border-radius: 6px;
  color: var(--color-text-muted); cursor: pointer; font-size: 0.85rem;
}
.btn-secondary:hover { border-color: var(--color-accent); color: var(--color-accent); }
.experience-card__header {
  display: flex; justify-content: space-between; align-items: center; margin-bottom: var(--space-3);
}
.experience-card__label { font-size: 0.82rem; color: var(--color-text-muted); font-weight: 500; }
</style>
