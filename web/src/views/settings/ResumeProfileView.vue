<template>
  <div class="resume-profile">
    <h2>Resume Profile</h2>

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
          <label>Skills</label>
          <div class="tags">
            <span v-for="skill in store.skills" :key="skill" class="tag">
              {{ skill }} <button @click="store.removeTag('skills', skill)">×</button>
            </span>
          </div>
          <input v-model="skillInput" @keydown.enter.prevent="store.addTag('skills', skillInput); skillInput = ''" placeholder="Add skill, press Enter" />
        </div>
        <div class="tag-section">
          <label>Domains</label>
          <div class="tags">
            <span v-for="domain in store.domains" :key="domain" class="tag">
              {{ domain }} <button @click="store.removeTag('domains', domain)">×</button>
            </span>
          </div>
          <input v-model="domainInput" @keydown.enter.prevent="store.addTag('domains', domainInput); domainInput = ''" placeholder="Add domain, press Enter" />
        </div>
        <div class="tag-section">
          <label>Keywords</label>
          <div class="tags">
            <span v-for="kw in store.keywords" :key="kw" class="tag">
              {{ kw }} <button @click="store.removeTag('keywords', kw)">×</button>
            </span>
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
.resume-profile { max-width: 720px; margin: 0 auto; padding: var(--space-4, 24px); }
h2 { font-size: 1.4rem; font-weight: 600; margin-bottom: var(--space-6, 32px); color: var(--color-text-primary, #e2e8f0); }
h3 { font-size: 1rem; font-weight: 600; margin-bottom: var(--space-3, 16px); color: var(--color-text-primary, #e2e8f0); }
.form-section { margin-bottom: var(--space-8, 48px); padding-bottom: var(--space-6, 32px); border-bottom: 1px solid var(--color-border, rgba(255,255,255,0.08)); }
.field-row { display: flex; flex-direction: column; gap: 4px; margin-bottom: var(--space-3, 16px); }
.field-row label { font-size: 0.82rem; color: var(--color-text-secondary, #94a3b8); }
.field-row input, .field-row textarea, .field-row select {
  background: var(--color-surface-2, rgba(255,255,255,0.05));
  border: 1px solid var(--color-border, rgba(255,255,255,0.12));
  border-radius: 6px;
  color: var(--color-text-primary, #e2e8f0);
  padding: 7px 10px;
  font-size: 0.88rem;
  width: 100%;
  box-sizing: border-box;
}
.sync-label { font-size: 0.72rem; color: var(--color-accent, #7c3aed); margin-left: 6px; }
.checkbox-row { display: flex; align-items: center; gap: 8px; margin-bottom: 10px; font-size: 0.88rem; color: var(--color-text-primary, #e2e8f0); cursor: pointer; }
.experience-card { border: 1px solid var(--color-border, rgba(255,255,255,0.08)); border-radius: 8px; padding: var(--space-4, 24px); margin-bottom: var(--space-4, 24px); }
.remove-btn { margin-top: 8px; padding: 4px 12px; border-radius: 4px; background: rgba(239,68,68,0.15); color: #ef4444; border: 1px solid rgba(239,68,68,0.3); cursor: pointer; font-size: 0.82rem; }
.empty-state { text-align: center; padding: var(--space-8, 48px) 0; }
.empty-actions { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: var(--space-4, 24px); margin-top: var(--space-6, 32px); }
.empty-card { background: var(--color-surface-2, rgba(255,255,255,0.04)); border: 1px solid var(--color-border, rgba(255,255,255,0.08)); border-radius: 10px; padding: var(--space-4, 24px); text-align: left; }
.empty-card h3 { margin-bottom: 8px; }
.empty-card p { font-size: 0.85rem; color: var(--color-text-secondary, #94a3b8); margin-bottom: 16px; }
.empty-card button, .empty-card a { padding: 8px 16px; border-radius: 6px; font-size: 0.85rem; cursor: pointer; text-decoration: none; display: inline-block; background: var(--color-accent, #7c3aed); color: #fff; border: none; }
.tag-section { margin-bottom: var(--space-4, 24px); }
.tag-section label { font-size: 0.82rem; color: var(--color-text-secondary, #94a3b8); display: block; margin-bottom: 6px; }
.tags { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 8px; }
.tag { padding: 3px 10px; background: rgba(124,58,237,0.15); border: 1px solid rgba(124,58,237,0.3); border-radius: 12px; font-size: 0.78rem; color: var(--color-accent, #a78bfa); display: flex; align-items: center; gap: 5px; }
.tag button { background: none; border: none; color: inherit; cursor: pointer; padding: 0; line-height: 1; }
.tag-section input { background: var(--color-surface-2, rgba(255,255,255,0.05)); border: 1px solid var(--color-border, rgba(255,255,255,0.12)); border-radius: 6px; color: var(--color-text-primary, #e2e8f0); padding: 6px 10px; font-size: 0.85rem; width: 100%; box-sizing: border-box; }
.form-actions { margin-top: var(--space-6, 32px); display: flex; align-items: center; gap: var(--space-4, 24px); }
.btn-primary { padding: 9px 24px; background: var(--color-accent, #7c3aed); color: #fff; border: none; border-radius: 7px; font-size: 0.9rem; cursor: pointer; font-weight: 600; }
.btn-primary:disabled { opacity: 0.5; cursor: not-allowed; }
.error { color: #ef4444; font-size: 0.82rem; }
.error-banner { background: rgba(239,68,68,0.1); border: 1px solid rgba(239,68,68,0.3); border-radius: 6px; color: #ef4444; font-size: 0.85rem; padding: 10px 14px; margin-bottom: var(--space-4, 24px); }
.section-note { font-size: 0.8rem; color: var(--color-text-secondary, #94a3b8); margin-bottom: 16px; }
.toggle-btn { margin-left: 10px; padding: 2px 10px; background: transparent; border: 1px solid var(--color-border, rgba(255,255,255,0.15)); border-radius: 4px; color: var(--color-text-secondary, #94a3b8); cursor: pointer; font-size: 0.78rem; }
.loading { text-align: center; padding: var(--space-8, 48px); color: var(--color-text-secondary, #94a3b8); }
.replace-section { background: var(--color-surface-2, rgba(255,255,255,0.03)); border-radius: 8px; padding: var(--space-4, 24px); }
</style>
