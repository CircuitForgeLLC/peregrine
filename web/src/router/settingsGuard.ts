import { useAppConfigStore } from '../stores/appConfig'

const GPU_PROFILES = ['single-gpu', 'dual-gpu']

/**
 * Synchronous tab-gating logic for /settings/* routes.
 * Called by the async router.beforeEach after config.load() has resolved.
 * Reading devTierOverride from localStorage here (not only the store ref) ensures
 * the guard reflects overrides set externally before the store hydrates.
 */
export function settingsGuard(
  to: { path: string },
  _from: unknown,
  next: (to?: string) => void,
): void {
  const config = useAppConfigStore()
  const tab = to.path.replace('/settings/', '')
  const devOverride = config.devTierOverride || localStorage.getItem('dev_tier_override')

  if (tab === 'system' && config.isCloud) return next('/settings/my-profile')

  if (tab === 'fine-tune') {
    const cloudBlocked = config.isCloud && config.tier !== 'premium'
    const selfHostedBlocked = !config.isCloud && !GPU_PROFILES.includes(config.inferenceProfile)
    if (cloudBlocked || selfHostedBlocked) return next('/settings/my-profile')
  }

  if (tab === 'developer' && !config.isDevMode && !devOverride) return next('/settings/my-profile')

  next()
}
