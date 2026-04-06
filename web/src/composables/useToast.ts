/**
 * useToast — global reactive toast singleton.
 *
 * Module-level ref shared across all importers; no Pinia needed for a single
 * ephemeral string. Call showToast() from anywhere; App.vue renders it.
 */
import { ref } from 'vue'

const _message = ref<string | null>(null)
let _timer = 0

export function showToast(msg: string, duration = 3500): void {
  clearTimeout(_timer)
  _message.value = msg
  _timer = window.setTimeout(() => { _message.value = null }, duration)
}

export function useToast() {
  return { message: _message }
}
