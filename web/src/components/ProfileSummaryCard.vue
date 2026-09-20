<template>
  <section class="profile-summary" aria-labelledby="profile-summary-heading">
    <div class="profile-summary__header">
      <h2 id="profile-summary-heading" class="profile-summary__title">Your Search Profile</h2>
      <RouterLink to="/settings/search" class="profile-summary__link">Full preferences →</RouterLink>
    </div>

    <p v-if="loadErrorMessage" class="error-banner" role="alert">
      Couldn't load your saved preferences, so Save is disabled to avoid overwriting them — {{ loadErrorMessage }}
    </p>

    <!-- Locations -->
    <div class="profile-summary__field">
      <label class="profile-summary__label">Locations</label>
      <div class="tags">
        <span v-for="loc in search.locations" :key="loc" class="tag">
          {{ loc }} <button @click="search.removeTag('locations', loc)" :aria-label="`Remove ${loc}`">×</button>
        </span>
      </div>
      <input
        v-model="locationInput"
        @keydown.enter.prevent="addLocation"
        placeholder="Add location, press Enter"
        aria-label="Add location"
      />
    </div>

    <!-- Min Salary -->
    <div class="profile-summary__field">
      <label class="profile-summary__label" for="profile-summary-min-salary">Min Salary</label>
      <input
        id="profile-summary-min-salary"
        v-model.number="resume.salary_min"
        type="number"
      />
    </div>

    <!-- Remote preference -->
    <div class="profile-summary__field">
      <label class="profile-summary__label">Remote preference</label>
      <div class="remote-options" role="group" aria-label="Remote preference (select any that apply)">
        <button
          v-for="opt in remoteOptions"
          :key="opt.value"
          type="button"
          :class="['remote-btn', { active: search.remote_preference.includes(opt.value) }]"
          :aria-pressed="search.remote_preference.includes(opt.value)"
          @click="search.toggleRemotePreference(opt.value)"
        >{{ opt.label }}</button>
      </div>
    </div>

    <!-- Resume status -->
    <div class="profile-summary__field">
      <label class="profile-summary__label">Resume</label>
      <p v-if="resume.hasResume" class="resume-status">
        <span aria-hidden="true">✓</span> Resume uploaded
      </p>
      <RouterLink v-else to="/settings/resume" class="resume-status resume-status--link">
        Upload resume →
      </RouterLink>
    </div>

    <!-- Save -->
    <div class="profile-summary__actions" role="status" aria-live="polite">
      <button
        class="btn-primary"
        :disabled="isLoading || isSaving || !!loadErrorMessage"
        @click="handleSave"
      >
        {{ isSaving ? 'Saving…' : (justSaved ? '✓ Saved' : 'Save') }}
      </button>
      <p v-if="saveErrorMessage" class="error" role="alert">{{ saveErrorMessage }}</p>
    </div>
  </section>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { RouterLink } from 'vue-router'
import { useSearchStore } from '../stores/settings/search'
import { useResumeStore } from '../stores/settings/resume'

const search = useSearchStore()
const resume = useResumeStore()

const remoteOptions = [
  { value: 'onsite' as const, label: 'On-site' },
  { value: 'remote' as const, label: 'Remote' },
  { value: 'hybrid' as const, label: 'Hybrid' },
]

const locationInput = ref('')
const justSaved = ref(false)

const isLoading = computed(() => search.loading || resume.loading)
const isSaving = computed(() => search.saving || resume.saving)

// A failed initial load leaves store fields at their constructor defaults
// (e.g. resume.salary_min === 0, resume.experience === []) rather than the
// user's real data — Save must stay disabled in that case, not just while
// loading is in flight, or one click PUTs a blank object over their profile.
const loadErrorMessage = computed(() => {
  const searchMsg = search.loadError
  const resumeMsg = resume.loadError
  if (searchMsg && resumeMsg) return `Search preferences: ${searchMsg} — Resume: ${resumeMsg}`
  if (searchMsg) return `Search preferences: ${searchMsg}`
  if (resumeMsg) return `Resume: ${resumeMsg}`
  return null
})

// Name which half failed when only one of the two saves errors, so the user
// isn't left guessing whether their locations or their salary didn't save.
const saveErrorMessage = computed(() => {
  const searchMsg = search.saveError
  const resumeMsg = resume.saveError
  if (searchMsg && resumeMsg) return `Search preferences: ${searchMsg} — Salary: ${resumeMsg}`
  if (searchMsg) return `Search preferences: ${searchMsg}`
  if (resumeMsg) return `Salary: ${resumeMsg}`
  return null
})

function addLocation() {
  search.addTag('locations', locationInput.value)
  locationInput.value = ''
}

async function handleSave() {
  await Promise.all([search.save(), resume.save()])
  if (search.saveError || resume.saveError) return
  justSaved.value = true
  setTimeout(() => { justSaved.value = false }, 2000)
}

onMounted(() => {
  // Stores are shared Pinia singletons — re-loading on every mount would
  // silently discard unsaved edits made on the Settings pages before the
  // user navigated back to the dashboard, plus cost two needless round-trips
  // per visit. Only load once per session (per store), unless a previous
  // load failed (loaded stays false on failure so a retry can still happen).
  if (!search.loaded) search.load()
  if (!resume.loaded) resume.load()
})
</script>

<style scoped>
.profile-summary {
  background: var(--color-surface-raised);
  border: 1px solid var(--color-border-light);
  border-radius: var(--radius-lg);
  padding: var(--space-6);
  display: flex;
  flex-direction: column;
  gap: var(--space-5);
}

.profile-summary__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
  flex-wrap: wrap;
}

.profile-summary__title {
  font-family: var(--font-display);
  font-size: var(--text-xl);
  color: var(--color-text);
}

.profile-summary__link {
  font-size: var(--text-sm);
  color: var(--app-primary, var(--color-primary));
  text-decoration: none;
  white-space: nowrap;
  font-weight: 500;
}
.profile-summary__link:hover { text-decoration: underline; }

.profile-summary__field {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.profile-summary__label {
  font-size: 0.82rem;
  color: var(--color-text-muted);
}

.tags { display: flex; flex-wrap: wrap; gap: 6px; }
.tag {
  padding: 3px 10px;
  background: color-mix(in srgb, var(--color-accent) 15%, transparent);
  border: 1px solid color-mix(in srgb, var(--color-accent) 30%, transparent);
  border-radius: var(--radius-full);
  font-size: 0.78rem;
  color: var(--color-accent);
  display: flex;
  align-items: center;
  gap: 5px;
}
.tag button { background: none; border: none; color: inherit; cursor: pointer; padding: 0; line-height: 1; }

.profile-summary__field input[type="text"],
.profile-summary__field input:not([type]),
.profile-summary__field input[type="number"] {
  background: var(--color-surface-alt);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  color: var(--color-text);
  padding: 7px 10px;
  font-size: 0.85rem;
  box-sizing: border-box;
  width: 100%;
}

.remote-options { display: flex; gap: var(--space-2); flex-wrap: wrap; }
.remote-btn {
  padding: 8px 18px;
  border-radius: var(--radius-md);
  border: 1px solid var(--color-border);
  background: transparent;
  color: var(--color-text-muted);
  cursor: pointer;
  font-size: 0.88rem;
  transition: all var(--transition);
}
.remote-btn.active {
  background: var(--color-accent);
  border-color: var(--color-accent);
  color: var(--color-text-inverse);
}

.resume-status {
  font-size: 0.88rem;
  color: var(--color-success);
  display: flex;
  align-items: center;
  gap: var(--space-2);
  margin: 0;
}
.resume-status--link {
  color: var(--app-primary, var(--color-primary));
  text-decoration: none;
  width: fit-content;
}
.resume-status--link:hover { text-decoration: underline; }

.profile-summary__actions {
  display: flex;
  align-items: center;
  gap: var(--space-4);
}

.btn-primary {
  padding: 9px 24px;
  background: var(--color-accent);
  color: var(--color-text-inverse);
  border: none;
  border-radius: var(--radius-md);
  font-size: 0.9rem;
  cursor: pointer;
  font-weight: 600;
}
.btn-primary:disabled { opacity: 0.5; cursor: not-allowed; }
.error { color: var(--color-error); font-size: 0.82rem; margin: 0; }
.error-banner {
  background: color-mix(in srgb, var(--color-error) 10%, transparent);
  border: 1px solid color-mix(in srgb, var(--color-error) 30%, transparent);
  border-radius: var(--radius-sm);
  color: var(--color-error);
  padding: 10px 14px;
  font-size: 0.85rem;
  margin: 0;
}

@media (max-width: 480px) {
  .profile-summary { padding: var(--space-4); }
  .profile-summary__header { flex-direction: column; align-items: flex-start; gap: var(--space-2); }
}
</style>
