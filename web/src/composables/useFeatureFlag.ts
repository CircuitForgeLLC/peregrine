/**
 * useFeatureFlag — demo toolbar tier display helper.
 *
 * Reads the `prgn_demo_tier` cookie set by the Streamlit demo toolbar so the
 * Vue SPA can visually reflect the simulated tier (e.g. in ClassicUIButton
 * or feature-locked UI hints).
 *
 * ⚠️  NOT an authoritative feature gate. This is demo-only visual consistency.
 *     Production feature gating will use a future /api/features endpoint (issue #8).
 *     All real access control lives in the Python tier system (app/wizard/tiers.py).
 */
import { computed } from 'vue'

const VALID_TIERS = ['free', 'paid', 'premium'] as const
type Tier = (typeof VALID_TIERS)[number]

function _readDemoTierCookie(): Tier | null {
  const match = document.cookie
    .split('; ')
    .find((row) => row.startsWith('prgn_demo_tier='))
  if (!match) return null
  const value = match.split('=')[1] as Tier
  return VALID_TIERS.includes(value) ? value : null
}

/**
 * Returns the simulated demo tier from the `prgn_demo_tier` cookie,
 * or `null` when not in demo mode (cookie absent).
 *
 * Use for visual indicators only — never for access control.
 */
export function useFeatureFlag() {
  const demoTier = computed<Tier | null>(() => _readDemoTierCookie())

  const isDemoMode = computed(() => demoTier.value !== null)

  /**
   * Returns true if the simulated demo tier meets `required`.
   * Always returns false outside demo mode.
   */
  function demoCanUse(required: Tier): boolean {
    const order: Tier[] = ['free', 'paid', 'premium']
    if (!demoTier.value) return false
    return order.indexOf(demoTier.value) >= order.indexOf(required)
  }

  return { demoTier, isDemoMode, demoCanUse }
}
