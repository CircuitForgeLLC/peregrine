/**
 * Convenience wrapper around useApiFetch from useApi.ts that returns data directly
 * (null on error), simplifying store code that doesn't need detailed error handling.
 */
import { useApiFetch as _useApiFetch } from './useApi'

export async function useApiFetch<T>(url: string, opts?: RequestInit): Promise<T | null> {
  const { data } = await _useApiFetch<T>(url, opts)
  return data
}
