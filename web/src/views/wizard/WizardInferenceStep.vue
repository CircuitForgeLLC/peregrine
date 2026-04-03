<template>
  <div class="step">
    <h2 class="step__heading">Step 5 — Inference & API Keys</h2>
    <p class="step__caption">
      Configure how Peregrine generates AI content. You can adjust this any time
      in Settings → System.
    </p>

    <!-- Remote mode -->
    <template v-if="isRemote">
      <div class="step__info">
        Remote mode: at least one external API key is required for AI generation.
      </div>

      <div class="step__field">
        <label class="step__label" for="inf-anthropic">Anthropic API key</label>
        <input id="inf-anthropic" v-model="form.anthropicKey" type="password"
               class="step__input" placeholder="sk-ant-…" autocomplete="off" />
      </div>

      <div class="step__field">
        <label class="step__label step__label--optional" for="inf-oai-url">
          OpenAI-compatible endpoint
        </label>
        <input id="inf-oai-url" v-model="form.openaiUrl" type="url"
               class="step__input" placeholder="https://api.together.xyz/v1" />
      </div>

      <div v-if="form.openaiUrl" class="step__field">
        <label class="step__label step__label--optional" for="inf-oai-key">
          Endpoint API key
        </label>
        <input id="inf-oai-key" v-model="form.openaiKey" type="password"
               class="step__input" placeholder="API key for the endpoint above"
               autocomplete="off" />
      </div>
    </template>

    <!-- Local mode -->
    <template v-else>
      <div class="step__info">
        Local mode ({{ wizard.hardware.selectedProfile }}): Peregrine uses
        Ollama for AI generation. No API keys needed.
      </div>
    </template>

    <!-- Advanced: service ports -->
    <div class="step__expandable">
      <button class="step__expandable__toggle" @click="showAdvanced = !showAdvanced">
        {{ showAdvanced ? '▼' : '▶' }} Advanced — service hosts &amp; ports
      </button>
      <div v-if="showAdvanced" class="step__expandable__body">
        <div class="svc-row" v-for="svc in services" :key="svc.key">
          <span class="svc-label">{{ svc.label }}</span>
          <input v-model="svc.host" type="text" class="step__input svc-input" />
          <input v-model.number="svc.port" type="number" class="step__input svc-port" />
        </div>
      </div>
    </div>

    <!-- Connection test -->
    <div class="test-row">
      <button class="btn-secondary" :disabled="testing" @click="runTest">
        {{ testing ? 'Testing…' : '🔌 Test connection' }}
      </button>
      <span v-if="testResult" :class="testResult.ok ? 'test-ok' : 'test-warn'">
        {{ testResult.message }}
      </span>
    </div>

    <div class="step__nav">
      <button class="btn-ghost" @click="back">← Back</button>
      <button class="btn-primary" :disabled="wizard.saving" @click="next">
        {{ wizard.saving ? 'Saving…' : 'Next →' }}
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import { useWizardStore } from '../../stores/wizard'
import './wizard.css'

const wizard = useWizardStore()
const router = useRouter()

const isRemote = computed(() => wizard.hardware.selectedProfile === 'remote')
const showAdvanced = ref(false)
const testing = ref(false)
const testResult = ref<{ ok: boolean; message: string } | null>(null)

const form = reactive({
  anthropicKey: wizard.inference.anthropicKey,
  openaiUrl: wizard.inference.openaiUrl,
  openaiKey: wizard.inference.openaiKey,
})

const services = reactive([
  { key: 'ollama', label: 'Ollama', host: 'ollama', port: 11434 },
  { key: 'searxng', label: 'SearXNG', host: 'searxng', port: 8080 },
])

async function runTest() {
  testing.value = true
  testResult.value = null
  wizard.inference.anthropicKey = form.anthropicKey
  wizard.inference.openaiUrl = form.openaiUrl
  wizard.inference.openaiKey = form.openaiKey
  testResult.value = await wizard.testInference()
  testing.value = false
}

function back() { router.push('/setup/identity') }

async function next() {
  // Sync form back to store
  wizard.inference.anthropicKey = form.anthropicKey
  wizard.inference.openaiUrl = form.openaiUrl
  wizard.inference.openaiKey = form.openaiKey

  const svcMap: Record<string, string | number> = {}
  services.forEach(s => {
    svcMap[`${s.key}_host`] = s.host
    svcMap[`${s.key}_port`] = s.port
  })
  wizard.inference.services = svcMap

  const ok = await wizard.saveStep(5, {
    anthropic_key: form.anthropicKey,
    openai_url: form.openaiUrl,
    openai_key: form.openaiKey,
    services: svcMap,
  })
  if (ok) router.push('/setup/search')
}
</script>

<style scoped>
.test-row {
  display: flex;
  align-items: center;
  gap: var(--space-4);
  margin-bottom: var(--space-4);
  flex-wrap: wrap;
}

.test-ok  { font-size: 0.875rem; color: var(--color-success); }
.test-warn { font-size: 0.875rem; color: var(--color-warning); }

.svc-row {
  display: grid;
  grid-template-columns: 6rem 1fr 5rem;
  gap: var(--space-2);
  align-items: center;
  margin-bottom: var(--space-2);
}

.svc-label {
  font-size: 0.875rem;
  font-weight: 500;
  color: var(--color-text-muted);
}

.svc-port {
  text-align: right;
}
</style>
