import { showToast } from './useToast'

export type ApiError =
  | { kind: 'network'; message: string }
  | { kind: 'http'; status: number; detail: string }
  | { kind: 'demo-blocked' }

// Strip trailing slash so '/peregrine/' + '/api/...' → '/peregrine/api/...'
const _apiBase = import.meta.env.BASE_URL.replace(/\/$/, '')

export async function useApiFetch<T>(
  url: string,
  opts?: RequestInit,
): Promise<{ data: T | null; error: ApiError | null }> {
  try {
    const res = await fetch(_apiBase + url, opts)
    if (!res.ok) {
      const rawText = await res.text().catch(() => '')
      // Demo mode: show toast and swallow the error so callers don't need to handle it
      if (res.status === 403) {
        try {
          const body = JSON.parse(rawText) as { detail?: string }
          if (body.detail === 'demo-write-blocked') {
            showToast('Demo mode — sign in to save changes')
            // Return a truthy error so callers bail early (no optimistic UI update),
            // but the toast is already shown so no additional error handling needed.
            return { data: null, error: { kind: 'demo-blocked' as const } }
          }
        } catch { /* not JSON — fall through to normal error */ }
      }
      return { data: null, error: { kind: 'http', status: res.status, detail: rawText } }
    }
    const data = await res.json() as T
    return { data, error: null }
  } catch (e) {
    return { data: null, error: { kind: 'network', message: String(e) } }
  }
}

/**
 * Open an SSE connection. Returns a cleanup function.
 * onEvent receives each parsed JSON payload.
 * onComplete is called when the server sends a {"type":"complete"} event.
 * onError is called on connection error.
 */
export function useApiSSE(
  url: string,
  onEvent: (data: Record<string, unknown>) => void,
  onComplete?: () => void,
  onError?: (e: Event) => void,
): () => void {
  const es = new EventSource(_apiBase + url)
  es.onmessage = (e) => {
    try {
      const data = JSON.parse(e.data) as Record<string, unknown>
      onEvent(data)
      if (data.type === 'complete') {
        es.close()
        onComplete?.()
      }
    } catch { /* ignore malformed events */ }
  }
  es.onerror = (e) => {
    onError?.(e)
    es.close()
  }
  return () => es.close()
}
