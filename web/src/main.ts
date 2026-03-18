import { createApp } from 'vue'
import { createPinia } from 'pinia'
import { router } from './router'

// Self-hosted fonts — no Google Fonts CDN (privacy requirement)
import '@fontsource/fraunces/400.css'
import '@fontsource/fraunces/700.css'
import '@fontsource/atkinson-hyperlegible/400.css'
import '@fontsource/atkinson-hyperlegible/700.css'
import '@fontsource/jetbrains-mono/400.css'

import 'virtual:uno.css'
import './assets/theme.css'
import './assets/peregrine.css'

import App from './App.vue'

// Manual scroll restoration — prevents browser from jumping to last position on SPA nav
if ('scrollRestoration' in history) history.scrollRestoration = 'manual'

const app = createApp(App)
app.use(createPinia())
app.use(router)
app.mount('#app')
