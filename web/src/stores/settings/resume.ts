import { ref } from 'vue'
import { defineStore } from 'pinia'
import { useApiFetch } from '../../composables/useApi'

export interface WorkEntry {
  title: string; company: string; period: string; location: string
  industry: string; responsibilities: string; skills: string[]
}

export const useResumeStore = defineStore('settings/resume', () => {
  const hasResume = ref(false)
  const loading = ref(false)
  const saving = ref(false)
  const saveError = ref<string | null>(null)

  // Identity (synced from profile store)
  const name = ref(''); const email = ref(''); const phone = ref(''); const linkedin_url = ref('')
  // Resume-only contact
  const surname = ref(''); const address = ref(''); const city = ref('')
  const zip_code = ref(''); const date_of_birth = ref('')
  // Experience
  const experience = ref<WorkEntry[]>([])
  // Prefs
  const salary_min = ref(0); const salary_max = ref(0); const notice_period = ref('')
  const remote = ref(false); const relocation = ref(false)
  const assessment = ref(false); const background_check = ref(false)
  // Self-ID
  const gender = ref(''); const pronouns = ref(''); const ethnicity = ref('')
  const veteran_status = ref(''); const disability = ref('')
  // Keywords
  const skills = ref<string[]>([]); const domains = ref<string[]>([]); const keywords = ref<string[]>([])

  function syncFromProfile(p: { name: string; email: string; phone: string; linkedin_url: string }) {
    name.value = p.name; email.value = p.email
    phone.value = p.phone; linkedin_url.value = p.linkedin_url
  }

  async function load() {
    loading.value = true
    const { data, error } = await useApiFetch<Record<string, unknown>>('/api/settings/resume')
    loading.value = false
    if (error || !data || !data.exists) { hasResume.value = false; return }
    hasResume.value = true
    name.value = String(data.name ?? ''); email.value = String(data.email ?? '')
    phone.value = String(data.phone ?? ''); linkedin_url.value = String(data.linkedin_url ?? '')
    surname.value = String(data.surname ?? ''); address.value = String(data.address ?? '')
    city.value = String(data.city ?? ''); zip_code.value = String(data.zip_code ?? '')
    date_of_birth.value = String(data.date_of_birth ?? '')
    experience.value = (data.experience as WorkEntry[]) ?? []
    salary_min.value = Number(data.salary_min ?? 0); salary_max.value = Number(data.salary_max ?? 0)
    notice_period.value = String(data.notice_period ?? '')
    remote.value = Boolean(data.remote); relocation.value = Boolean(data.relocation)
    assessment.value = Boolean(data.assessment); background_check.value = Boolean(data.background_check)
    gender.value = String(data.gender ?? ''); pronouns.value = String(data.pronouns ?? '')
    ethnicity.value = String(data.ethnicity ?? ''); veteran_status.value = String(data.veteran_status ?? '')
    disability.value = String(data.disability ?? '')
    skills.value = (data.skills as string[]) ?? []
    domains.value = (data.domains as string[]) ?? []
    keywords.value = (data.keywords as string[]) ?? []
  }

  async function save() {
    saving.value = true; saveError.value = null
    const body = {
      name: name.value, email: email.value, phone: phone.value, linkedin_url: linkedin_url.value,
      surname: surname.value, address: address.value, city: city.value, zip_code: zip_code.value,
      date_of_birth: date_of_birth.value, experience: experience.value,
      salary_min: salary_min.value, salary_max: salary_max.value, notice_period: notice_period.value,
      remote: remote.value, relocation: relocation.value,
      assessment: assessment.value, background_check: background_check.value,
      gender: gender.value, pronouns: pronouns.value, ethnicity: ethnicity.value,
      veteran_status: veteran_status.value, disability: disability.value,
      skills: skills.value, domains: domains.value, keywords: keywords.value,
    }
    const { error } = await useApiFetch('/api/settings/resume', {
      method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
    })
    saving.value = false
    if (error) saveError.value = 'Save failed — please try again.'
  }

  async function createBlank() {
    const { error } = await useApiFetch('/api/settings/resume/blank', { method: 'POST' })
    if (!error) { hasResume.value = true; await load() }
  }

  return {
    hasResume, loading, saving, saveError,
    name, email, phone, linkedin_url, surname, address, city, zip_code, date_of_birth,
    experience, salary_min, salary_max, notice_period, remote, relocation, assessment, background_check,
    gender, pronouns, ethnicity, veteran_status, disability,
    skills, domains, keywords,
    syncFromProfile, load, save, createBlank,
  }
})
