import { ref } from 'vue'
import { defineStore } from 'pinia'
import { useApiFetch } from '../../composables/useApi'

export type RemotePreference = 'remote' | 'onsite' | 'hybrid'
const ALL_REMOTE_PREFERENCES: RemotePreference[] = ['onsite', 'remote', 'hybrid']
export interface JobBoard { name: string; enabled: boolean }

export const useSearchStore = defineStore('settings/search', () => {
  const remote_preference = ref<RemotePreference[]>([...ALL_REMOTE_PREFERENCES])
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
  const suggestingField = ref<'titles' | 'locations' | 'exclude' | null>(null)
  const suggestErrors = ref<{ titles: string | null; locations: string | null; exclude: string | null }>({
    titles: null, locations: null, exclude: null,
  })

  const loading = ref(false)
  const saving = ref(false)
  const saveError = ref<string | null>(null)
  const loadError = ref<string | null>(null)
  // Set true only after a successful load — lets callers (e.g. dashboard
  // cards) avoid re-fetching on every mount, without masking a failed load
  // as "already loaded" (a failure leaves this false so a retry can happen).
  const loaded = ref(false)

  async function load() {
    loading.value = true
    loadError.value = null
    const { data, error } = await useApiFetch<Record<string, unknown>>('/api/settings/search')
    loading.value = false
    if (error) { loadError.value = 'Failed to load search preferences'; return }
    loaded.value = true
    if (!data) return
    // Backward compat: an install may still have an old single-string value
    // on disk (including the retired 'both'), not yet re-saved as a list.
    const _rp = data.remote_preference
    if (Array.isArray(_rp) && _rp.length > 0) {
      remote_preference.value = _rp as RemotePreference[]
    } else if (typeof _rp === 'string') {
      remote_preference.value = _rp === 'both' ? [...ALL_REMOTE_PREFERENCES] : [_rp as RemotePreference]
    } else {
      remote_preference.value = [...ALL_REMOTE_PREFERENCES]
    }
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
    suggestingField.value = 'titles'
    suggestErrors.value.titles = null
    const { data, error } = await useApiFetch<{ suggestions: string[] }>('/api/settings/search/suggest', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ type: 'titles', current: job_titles.value }),
    })
    suggestingField.value = null
    if (error || !data?.suggestions) {
      suggestErrors.value.titles = 'Could not generate suggestions — please try again.'
      return
    }
    titleSuggestions.value = data.suggestions.filter(s => !job_titles.value.includes(s))
    if (titleSuggestions.value.length === 0) {
      suggestErrors.value.titles = 'No new suggestions right now — try again in a moment.'
    }
  }

  async function suggestLocations() {
    suggestingField.value = 'locations'
    suggestErrors.value.locations = null
    const { data, error } = await useApiFetch<{ suggestions: string[] }>('/api/settings/search/suggest', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ type: 'locations', current: locations.value }),
    })
    suggestingField.value = null
    if (error || !data?.suggestions) {
      suggestErrors.value.locations = 'Could not generate suggestions — please try again.'
      return
    }
    locationSuggestions.value = data.suggestions.filter(s => !locations.value.includes(s))
    if (locationSuggestions.value.length === 0) {
      suggestErrors.value.locations = 'No new suggestions right now — try again in a moment.'
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
    suggestingField.value = 'exclude'
    suggestErrors.value.exclude = null
    const { data, error } = await useApiFetch<{ suggestions: string[] }>('/api/settings/search/suggest', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ type: 'exclude_keywords', current: exclude_keywords.value }),
    })
    suggestingField.value = null
    if (error || !data?.suggestions) {
      suggestErrors.value.exclude = 'Could not generate suggestions — please try again.'
      return
    }
    excludeSuggestions.value = data.suggestions.filter(s => !exclude_keywords.value.includes(s))
    if (excludeSuggestions.value.length === 0) {
      suggestErrors.value.exclude = 'No new suggestions right now — try again in a moment.'
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

  function toggleRemotePreference(value: RemotePreference) {
    remote_preference.value = remote_preference.value.includes(value)
      ? remote_preference.value.filter(v => v !== value)
      : [...remote_preference.value, value]
  }

  function toggleBoard(name: string) {
    job_boards.value = job_boards.value.map(b =>
      b.name === name ? { ...b, enabled: !b.enabled } : b
    )
  }

  return {
    remote_preference, job_titles, locations, exclude_keywords, job_boards,
    custom_board_urls, blocklist_companies, blocklist_industries, blocklist_locations,
    titleSuggestions, locationSuggestions, excludeSuggestions, suggestingField, suggestErrors,
    loading, saving, saveError, loadError, loaded,
    load, save, suggestTitles, suggestLocations, suggestExcludeKeywords,
    addTag, removeTag, acceptSuggestion, toggleBoard, toggleRemotePreference,
  }
})
