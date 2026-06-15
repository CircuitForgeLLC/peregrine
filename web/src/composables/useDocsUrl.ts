const DOCS_BASE = 'https://docs.circuitforge.tech/peregrine'

export function useDocsUrl(path: string): string {
  return `${DOCS_BASE}/${path}`
}
