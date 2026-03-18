// jsdom does not implement window.matchMedia — stub it so useMotion and other
// composables that check prefers-reduced-motion can import without throwing.
// Gotcha #12.
if (typeof window !== 'undefined' && !window.matchMedia) {
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    value: (query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: () => {},
      removeListener: () => {},
      addEventListener: () => {},
      removeEventListener: () => {},
      dispatchEvent: () => false,
    }),
  })
}

// navigator.vibrate not in jsdom — stub so useHaptics doesn't throw. Gotcha #9.
if (typeof window !== 'undefined' && !('vibrate' in window.navigator)) {
  Object.defineProperty(window.navigator, 'vibrate', {
    writable: true,
    value: () => false,
  })
}

// ResizeObserver not in jsdom — stub if any component uses it.
if (typeof window !== 'undefined' && !window.ResizeObserver) {
  window.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  }
}
