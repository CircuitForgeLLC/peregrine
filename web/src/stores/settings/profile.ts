import { ref } from 'vue'
import { defineStore } from 'pinia'
import { useApiFetch } from '../../composables/useApi'

export interface MissionPref { industry: string; note: string }

export const useProfileStore = defineStore('settings/profile', () => {
  const name = ref('')
  const email = ref('')
  const phone = ref('')
  const linkedin_url = ref('')
  const career_summary = ref('')
  const candidate_voice = ref('')
  const inference_profile = ref('cpu')
  const mission_preferences = ref<MissionPref[]>([])
  const nda_companies = ref<string[]>([])
  const accessibility_focus = ref(false)
  const lgbtq_focus = ref(false)

  const loading = ref(false)
  const saving = ref(false)
  const saveError = ref<string | null>(null)

  async function load() {
    loading.value = true
    const { data } = await useApiFetch<Record<string, unknown>>('/api/settings/profile')
    loading.value = false
    if (!data) return
    name.value = String(data.name ?? '')
    email.value = String(data.email ?? '')
    phone.value = String(data.phone ?? '')
    linkedin_url.value = String(data.linkedin_url ?? '')
    career_summary.value = String(data.career_summary ?? '')
    candidate_voice.value = String(data.candidate_voice ?? '')
    inference_profile.value = String(data.inference_profile ?? 'cpu')
    mission_preferences.value = (data.mission_preferences as MissionPref[]) ?? []
    nda_companies.value = (data.nda_companies as string[]) ?? []
    accessibility_focus.value = Boolean(data.accessibility_focus)
    lgbtq_focus.value = Boolean(data.lgbtq_focus)
  }

  async function save() {
    saving.value = true
    saveError.value = null
    const body = {
      name: name.value,
      email: email.value,
      phone: phone.value,
      linkedin_url: linkedin_url.value,
      career_summary: career_summary.value,
      candidate_voice: candidate_voice.value,
      inference_profile: inference_profile.value,
      mission_preferences: mission_preferences.value,
      nda_companies: nda_companies.value,
      accessibility_focus: accessibility_focus.value,
      lgbtq_focus: lgbtq_focus.value,
    }
    const { error } = await useApiFetch('/api/settings/profile', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
    saving.value = false
    if (error) {
      saveError.value = 'Save failed — please try again.'
      return
    }
    // Push identity fields to resume YAML — graceful; endpoint may not exist yet (Task 3)
    await useApiFetch('/api/settings/resume/sync-identity', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name: name.value,
        email: email.value,
        phone: phone.value,
        linkedin_url: linkedin_url.value,
      }),
    })
  }

  return {
    name, email, phone, linkedin_url, career_summary, candidate_voice, inference_profile,
    mission_preferences, nda_companies, accessibility_focus, lgbtq_focus,
    loading, saving, saveError,
    load, save,
  }
})
