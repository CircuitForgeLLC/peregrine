import { afterEach, describe, expect, it, vi } from 'vitest'

// apiUrl reads import.meta.env.BASE_URL when the module loads, so each case stubs the
// base path first and then imports a fresh copy of the module.
async function loadApiUrl(base: string) {
  vi.stubEnv('BASE_URL', base)
  vi.resetModules()
  return (await import('./useApi')).apiUrl
}

describe('apiUrl', () => {
  afterEach(() => {
    vi.unstubAllEnvs()
    vi.resetModules()
  })

  it('prefixes the cloud base path so links open through the /peregrine/ route', async () => {
    const apiUrl = await loadApiUrl('/peregrine/')
    expect(apiUrl('/api/jobs/7/resume_optimizer/export-pdf')).toBe('/peregrine/api/jobs/7/resume_optimizer/export-pdf')
  })

  it('leaves the path alone on a self-hosted install served from the root', async () => {
    const apiUrl = await loadApiUrl('/')
    expect(apiUrl('/api/resumes/3/export-yaml')).toBe('/api/resumes/3/export-yaml')
  })
})
