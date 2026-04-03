import { useAppConfigStore } from '../stores/appConfig'
import { useWizardStore } from '../stores/wizard'

/**
 * Gate the entire app behind /setup until wizard_complete is true.
 *
 * Rules:
 * - Any non-/setup route while wizard is incomplete → redirect to /setup
 * - /setup/* while wizard is complete → redirect to /
 * - /setup with no step suffix → redirect to the current step route
 *
 * Must run AFTER appConfig.load() has resolved (called from router.beforeEach).
 */
export async function wizardGuard(
  to: { path: string },
  _from: unknown,
  next: (to?: string | { path: string }) => void,
): Promise<void> {
  const config = useAppConfigStore()

  // Ensure config is loaded before inspecting wizardComplete
  if (!config.loaded) await config.load()

  const onSetup = to.path.startsWith('/setup')
  const complete = config.wizardComplete

  // Wizard done — keep user out of /setup
  if (complete && onSetup) return next('/')

  // Wizard not done — redirect to setup
  if (!complete && !onSetup) return next('/setup')

  // On /setup exactly (no step) — delegate to WizardLayout which loads status
  next()
}
