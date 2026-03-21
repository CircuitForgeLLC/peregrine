import { ref } from 'vue'
import { defineStore } from 'pinia'
import { useApiFetch } from '../../composables/useApi'

export interface MissionPref { id: string; industry: string; note: string }

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
  const loadError = ref<string | null>(null)

  async function load() {
    loading.value = true
    loadError.value = null
    const { data, error } = await useApiFetch<Record<string, unknown>>('/api/settings/profile')
    loading.value = false
    if (error) {
      loadError.value = error.kind === 'network' ? error.message : error.detail || 'Failed to load profile'
      return
    }
    if (!data) return
    name.value = String(data.name ?? '')
    email.value = String(data.email ?? '')
    phone.value = String(data.phone ?? '')
    linkedin_url.value = String(data.linkedin_url ?? '')
    career_summary.value = String(data.career_summary ?? '')
    candidate_voice.value = String(data.candidate_voice ?? '')
    inference_profile.value = String(data.inference_profile ?? 'cpu')
    mission_preferences.value = ((data.mission_preferences as Array<{ industry: string; note: string }>) ?? [])
      .map((m) => ({ id: crypto.randomUUID(), industry: m.industry ?? '', note: m.note ?? '' }))
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
    // fire-and-forget — identity sync failures don't block save
    useApiFetch('/api/settings/resume/sync-identity', {
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
    loading, saving, saveError, loadError,
    load, save,
  }
})
