import { ref } from 'vue'
import { defineStore } from 'pinia'
import { useApiFetch } from '../../composables/useApi'

export type RemotePreference = 'remote' | 'onsite' | 'both'
export interface JobBoard { name: string; enabled: boolean }

export const useSearchStore = defineStore('settings/search', () => {
  const remote_preference = ref<RemotePreference>('both')
  const job_titles = ref<string[]>([])
  const locations = ref<string[]>([])
  const exclude_keywords = ref<string[]>([])
  const job_boards = ref<JobBoard[]>([])
  const custom_board_urls = ref<string[]>([])
  const blocklist_companies = ref<string[]>([])
  const blocklist_industries = ref<string[]>([])
  const blocklist_locations = ref<string[]>([])

  const titleSuggestions = ref<string[]>([])
  const locationSuggestions = ref<string[]>([])

  const loading = ref(false)
  const saving = ref(false)
  const saveError = ref<string | null>(null)
  const loadError = ref<string | null>(null)

  async function load() {
    loading.value = true
    loadError.value = null
    const { data, error } = await useApiFetch<Record<string, unknown>>('/api/settings/search')
    loading.value = false
    if (error) { loadError.value = 'Failed to load search preferences'; return }
    if (!data) return
    remote_preference.value = (data.remote_preference as RemotePreference) ?? 'both'
    job_titles.value = (data.job_titles as string[]) ?? []
    locations.value = (data.locations as string[]) ?? []
    exclude_keywords.value = (data.exclude_keywords as string[]) ?? []
    job_boards.value = (data.job_boards as JobBoard[]) ?? []
    custom_board_urls.value = (data.custom_board_urls as string[]) ?? []
    blocklist_companies.value = (data.blocklist_companies as string[]) ?? []
    blocklist_industries.value = (data.blocklist_industries as string[]) ?? []
    blocklist_locations.value = (data.blocklist_locations as string[]) ?? []
  }

  async function save() {
    saving.value = true
    saveError.value = null
    const body = {
      remote_preference: remote_preference.value,
      job_titles: job_titles.value,
      locations: locations.value,
      exclude_keywords: exclude_keywords.value,
      job_boards: job_boards.value,
      custom_board_urls: custom_board_urls.value,
      blocklist_companies: blocklist_companies.value,
      blocklist_industries: blocklist_industries.value,
      blocklist_locations: blocklist_locations.value,
    }
    const { error } = await useApiFetch('/api/settings/search', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
    saving.value = false
    if (error) saveError.value = 'Save failed — please try again.'
  }

  async function suggestTitles() {
    const { data } = await useApiFetch<{ suggestions: string[] }>('/api/settings/search/suggest', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ type: 'titles', current: job_titles.value }),
    })
    if (data?.suggestions) {
      titleSuggestions.value = data.suggestions.filter(s => !job_titles.value.includes(s))
    }
  }

  async function suggestLocations() {
    const { data } = await useApiFetch<{ suggestions: string[] }>('/api/settings/search/suggest', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ type: 'locations', current: locations.value }),
    })
    if (data?.suggestions) {
      locationSuggestions.value = data.suggestions.filter(s => !locations.value.includes(s))
    }
  }

  function addTag(field: 'job_titles' | 'locations' | 'exclude_keywords' | 'custom_board_urls' | 'blocklist_companies' | 'blocklist_industries' | 'blocklist_locations', value: string) {
    const arr = { job_titles, locations, exclude_keywords, custom_board_urls, blocklist_companies, blocklist_industries, blocklist_locations }[field]
    const trimmed = value.trim()
    if (!trimmed || arr.value.includes(trimmed)) return
    arr.value.push(trimmed)
  }

  function removeTag(field: 'job_titles' | 'locations' | 'exclude_keywords' | 'custom_board_urls' | 'blocklist_companies' | 'blocklist_industries' | 'blocklist_locations', value: string) {
    const arr = { job_titles, locations, exclude_keywords, custom_board_urls, blocklist_companies, blocklist_industries, blocklist_locations }[field]
    const idx = arr.value.indexOf(value)
    if (idx !== -1) arr.value.splice(idx, 1)
  }

  function acceptSuggestion(type: 'title' | 'location', value: string) {
    if (type === 'title') {
      if (!job_titles.value.includes(value)) job_titles.value.push(value)
      titleSuggestions.value = titleSuggestions.value.filter(s => s !== value)
    } else {
      if (!locations.value.includes(value)) locations.value.push(value)
      locationSuggestions.value = locationSuggestions.value.filter(s => s !== value)
    }
  }

  return {
    remote_preference, job_titles, locations, exclude_keywords, job_boards,
    custom_board_urls, blocklist_companies, blocklist_industries, blocklist_locations,
    titleSuggestions, locationSuggestions,
    loading, saving, saveError, loadError,
    load, save, suggestTitles, suggestLocations, addTag, removeTag, acceptSuggestion,
  }
})
