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
  const excludeSuggestions = ref<string[]>([])

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
    arr.value = [...arr.value, trimmed]
  }

  function removeTag(field: 'job_titles' | 'locations' | 'exclude_keywords' | 'custom_board_urls' | 'blocklist_companies' | 'blocklist_industries' | 'blocklist_locations', value: string) {
    const arr = { job_titles, locations, exclude_keywords, custom_board_urls, blocklist_companies, blocklist_industries, blocklist_locations }[field]
    arr.value = arr.value.filter(v => v !== value)
  }

  async function suggestExcludeKeywords() {
    const { data } = await useApiFetch<{ suggestions: string[] }>('/api/settings/search/suggest', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ type: 'exclude_keywords', current: exclude_keywords.value }),
    })
    if (data?.suggestions) {
      excludeSuggestions.value = data.suggestions.filter(s => !exclude_keywords.value.includes(s))
    }
  }

  function acceptSuggestion(type: 'title' | 'location' | 'exclude', value: string) {
    if (type === 'title') {
      if (!job_titles.value.includes(value)) job_titles.value = [...job_titles.value, value]
      titleSuggestions.value = titleSuggestions.value.filter(s => s !== value)
    } else if (type === 'exclude') {
      if (!exclude_keywords.value.includes(value)) exclude_keywords.value = [...exclude_keywords.value, value]
      excludeSuggestions.value = excludeSuggestions.value.filter(s => s !== value)
    } else {
      if (!locations.value.includes(value)) locations.value = [...locations.value, value]
      locationSuggestions.value = locationSuggestions.value.filter(s => s !== value)
    }
  }

  function toggleBoard(name: string) {
    job_boards.value = job_boards.value.map(b =>
      b.name === name ? { ...b, enabled: !b.enabled } : b
    )
  }

  return {
    remote_preference, job_titles, locations, exclude_keywords, job_boards,
    custom_board_urls, blocklist_companies, blocklist_industries, blocklist_locations,
    titleSuggestions, locationSuggestions, excludeSuggestions,
    loading, saving, saveError, loadError,
    load, save, suggestTitles, suggestLocations, suggestExcludeKeywords,
    addTag, removeTag, acceptSuggestion, toggleBoard,
  }
})
