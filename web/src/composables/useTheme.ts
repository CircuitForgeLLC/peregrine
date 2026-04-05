/**
 * useTheme — manual theme picker for Peregrine.
 *
 * Themes: 'auto' | 'light' | 'dark' | 'solarized-dark' | 'solarized-light' | 'colorblind'
 * Persisted in localStorage under 'cf-theme'.
 * Applied via document.documentElement.dataset.theme.
 * 'auto' removes the attribute so the @media prefers-color-scheme rule takes effect.
 *
 * Hacker mode sits on top of this system — toggling it off calls restoreTheme()
 * so the user's chosen theme is reinstated rather than dropping back to auto.
 */

import { ref, readonly } from 'vue'
import { useApiFetch } from './useApi'

export type Theme = 'auto' | 'light' | 'dark' | 'solarized-dark' | 'solarized-light' | 'colorblind'

const STORAGE_KEY = 'cf-theme'
const HACKER_KEY  = 'cf-hacker-mode'

export const THEME_OPTIONS: { value: Theme; label: string; icon: string }[] = [
  { value: 'auto',            label: 'Auto',             icon: '⬡' },
  { value: 'light',           label: 'Light',            icon: '☀' },
  { value: 'dark',            label: 'Dark',             icon: '🌙' },
  { value: 'solarized-light', label: 'Solarized Light',  icon: '🌤' },
  { value: 'solarized-dark',  label: 'Solarized Dark',   icon: '🌃' },
  { value: 'colorblind',      label: 'Colorblind Safe',  icon: '♿' },
]

// Module-level singleton so all consumers share the same reactive state.
const _current = ref<Theme>(_load())

function _load(): Theme {
  return (localStorage.getItem(STORAGE_KEY) as Theme | null) ?? 'auto'
}

function _apply(theme: Theme) {
  const root = document.documentElement
  if (theme === 'auto') {
    delete root.dataset.theme
  } else {
    root.dataset.theme = theme
  }
}

export function useTheme() {
  function setTheme(theme: Theme) {
    _current.value = theme
    localStorage.setItem(STORAGE_KEY, theme)
    _apply(theme)
    // Best-effort persist to server; ignore failures (works offline / local LLM)
    useApiFetch('/api/settings/theme', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ theme }),
    }).catch(() => {})
  }

  /** Restore user's chosen theme — called when hacker mode or other overlays exit. */
  function restoreTheme() {
    // Hacker mode clears itself; we only restore if it's actually off.
    if (localStorage.getItem(HACKER_KEY) === 'true') return
    _apply(_current.value)
  }

  /** Call once at app boot to apply persisted theme before first render. */
  function initTheme() {
    // Hacker mode takes priority on restore.
    if (localStorage.getItem(HACKER_KEY) === 'true') {
      document.documentElement.dataset.theme = 'hacker'
    } else {
      _apply(_current.value)
    }
  }

  return {
    currentTheme: readonly(_current),
    setTheme,
    restoreTheme,
    initTheme,
  }
}
