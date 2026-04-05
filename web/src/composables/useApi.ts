export type ApiError =
  | { kind: 'network'; message: string }
  | { kind: 'http'; status: number; detail: string }

// Strip trailing slash so '/peregrine/' + '/api/...' → '/peregrine/api/...'
const _apiBase = import.meta.env.BASE_URL.replace(/\/$/, '')

export async function useApiFetch<T>(
  url: string,
  opts?: RequestInit,
): Promise<{ data: T | null; error: ApiError | null }> {
  try {
    const res = await fetch(_apiBase + url, opts)
    if (!res.ok) {
      const detail = await res.text().catch(() => '')
      return { data: null, error: { kind: 'http', status: res.status, detail } }
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
