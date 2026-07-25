<template>
  <div class="step">
    <h2 class="step__heading">Step 6 — Inference & API Keys</h2>
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

    <!-- Orchard mode -->
    <template v-else-if="isCfOrch">
      <div class="step__info">
        Orchard mode: Peregrine routes AI generation through the CircuitForge GPU cluster.
      </div>

      <div class="step__field">
        <label class="step__label" for="inf-orch-url">Orchard coordinator URL</label>
        <input id="inf-orch-url" v-model="form.orchUrl" type="url"
               class="step__input" placeholder="https://orch.circuitforge.tech" />
      </div>

      <div v-if="isPaid" class="step__check-row">
        <label class="step__checkbox-label">
          <input
            type="checkbox"
            class="step__checkbox"
            :checked="form.orchUrl === MANAGED_ORCH_URL"
            @change="onUseManagedOrchard"
          />
          <span>Use CircuitForge managed Orchard</span>
        </label>
        <span class="step__check-hint">
          Auto-fills your Paid+ cluster endpoint ({{ MANAGED_ORCH_URL }})
        </span>
      </div>
    </template>

    <!-- Local mode (CPU / single-gpu / dual-gpu) -->
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
import { useAppConfigStore } from '../../stores/appConfig'
import './wizard.css'

const wizard = useWizardStore()
const config = useAppConfigStore()
const router = useRouter()

const MANAGED_ORCH_URL = 'https://orch.circuitforge.tech'

const isRemote = computed(() => wizard.hardware.selectedProfile === 'remote')
const isCfOrch = computed(() => wizard.hardware.selectedProfile === 'cf-orch')
const isPaid = computed(() => config.tier !== 'free')

const showAdvanced = ref(false)
const testing = ref(false)
const testResult = ref<{ ok: boolean; message: string } | null>(null)

const form = reactive({
  anthropicKey: wizard.inference.anthropicKey,
  openaiUrl: wizard.inference.openaiUrl,
  openaiKey: wizard.inference.openaiKey,
  orchUrl: wizard.inference.orchUrl,
})

const savedSvcs = wizard.inference.services as Record<string, string | number>
const services = reactive([
  {
    key: 'ollama',
    label: 'Ollama',
    host: (savedSvcs['ollama_host'] as string) || wizard.inference.ollamaHost || 'localhost',
    port: (savedSvcs['ollama_port'] as number) || wizard.inference.ollamaPort || 11434,
  },
  {
    key: 'searxng',
    label: 'SearXNG',
    host: (savedSvcs['searxng_host'] as string) || 'searxng',
    port: (savedSvcs['searxng_port'] as number) || 8080,
  },
])

function onUseManagedOrchard(e: Event) {
  const checked = (e.target as HTMLInputElement).checked
  form.orchUrl = checked ? MANAGED_ORCH_URL : ''
}

async function runTest() {
  testing.value = true
  testResult.value = null
  wizard.inference.anthropicKey = form.anthropicKey
  wizard.inference.openaiUrl = form.openaiUrl
  wizard.inference.openaiKey = form.openaiKey
  wizard.inference.orchUrl = form.orchUrl
  const ollamaSvc = services.find(s => s.key === 'ollama')
  if (ollamaSvc) {
    wizard.inference.ollamaHost = ollamaSvc.host
    wizard.inference.ollamaPort = ollamaSvc.port
  }
  testResult.value = await wizard.testInference()
  testing.value = false
}

function back() { router.push('/setup/identity') }

async function next() {
  wizard.inference.anthropicKey = form.anthropicKey
  wizard.inference.openaiUrl = form.openaiUrl
  wizard.inference.openaiKey = form.openaiKey
  wizard.inference.orchUrl = form.orchUrl

  const svcMap: Record<string, string | number> = {}
  services.forEach(s => {
    svcMap[`${s.key}_host`] = s.host
    svcMap[`${s.key}_port`] = s.port
  })
  wizard.inference.services = svcMap

  const ok = await wizard.saveStep(6, {
    anthropic_key: form.anthropicKey,
    openai_url: form.openaiUrl,
    openai_key: form.openaiKey,
    orch_url: form.orchUrl,
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

.step__check-row {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  margin-bottom: var(--space-4);
}

.step__checkbox-label {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  cursor: pointer;
  font-size: 0.9rem;
  color: var(--color-text);
}

.step__checkbox {
  width: 1rem;
  height: 1rem;
  accent-color: var(--color-primary);
  flex-shrink: 0;
}

.step__check-hint {
  font-size: 0.8rem;
  color: var(--color-text-muted);
  padding-left: calc(1rem + var(--space-2));
}
</style>
