import { defineConfig, presetWind, presetAttributify } from 'unocss'

export default defineConfig({
  presets: [
    presetWind(),
    // prefixedOnly: avoids false-positive CSS for bare attribute names like "h2", "grid",
    // "shadow" in source files. Use <div un-flex> not <div flex>. Gotcha #4.
    presetAttributify({ prefix: 'un-', prefixedOnly: true }),
  ],
})
