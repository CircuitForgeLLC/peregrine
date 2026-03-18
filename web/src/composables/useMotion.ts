import { computed, ref } from 'vue'

// Peregrine-namespaced localStorage entry (avocet uses cf-avocet-rich-motion)
const LS_MOTION = 'cf-peregrine-rich-motion'

// OS-level prefers-reduced-motion — checked once at module load
const OS_REDUCED = typeof window !== 'undefined'
  ? window.matchMedia('(prefers-reduced-motion: reduce)').matches
  : false

// Reactive ref so toggling localStorage triggers re-reads in the same session
const _richOverride = ref(
  typeof window !== 'undefined'
    ? localStorage.getItem(LS_MOTION)
    : null,
)

export function useMotion() {
  // null/missing = default ON; 'false' = explicitly disabled by user
  const rich = computed(() =>
    !OS_REDUCED && _richOverride.value !== 'false',
  )

  function setRich(enabled: boolean) {
    localStorage.setItem(LS_MOTION, enabled ? 'true' : 'false')
    _richOverride.value = enabled ? 'true' : 'false'
  }

  return { rich, setRich }
}
