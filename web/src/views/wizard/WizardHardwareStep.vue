<template>
  <div class="step">
    <h2 class="step__heading">Step 1 — Hardware Detection</h2>
    <p class="step__caption">
      Peregrine uses your hardware profile to choose the right inference setup.
    </p>

    <div v-if="detecting" class="step__info">Detecting hardware…</div>

    <template v-else>
      <div v-if="wizard.hardware.gpus.length" class="step__success">
        ✅ Detected {{ wizard.hardware.gpus.length }} local GPU(s):
        {{ wizard.hardware.gpus.join(', ') }}
      </div>
      <div v-else class="step__info">
        No local NVIDIA GPUs detected. CPU or Orchard mode recommended.
      </div>

      <!-- Service status -->
      <div class="hw-services">
        <div class="hw-svc" :class="ollamaRunning ? 'hw-svc--up' : 'hw-svc--down'">
          <span class="hw-svc__dot" aria-hidden="true" />
          <span class="hw-svc__name">Ollama</span>
          <span class="hw-svc__status">{{ ollamaRunning ? 'running' : 'not detected' }}</span>
        </div>
        <div class="hw-svc" :class="searxngRunning ? 'hw-svc--up' : 'hw-svc--down'">
          <span class="hw-svc__dot" aria-hidden="true" />
          <span class="hw-svc__name">SearXNG</span>
          <span class="hw-svc__status">{{ searxngRunning ? 'running' : 'not detected' }}</span>
        </div>
      </div>

      <p v-if="!ollamaRunning" class="step__field-hint">
        Ollama not running — start it on the host before continuing, or choose Remote or Orchard mode.
        See <strong>Settings → Services</strong> after setup to manage services.
      </p>

      <div class="step__field">
        <label class="step__label" for="hw-profile">Inference profile</label>
        <select id="hw-profile" v-model="selectedProfile" class="step__select">
          <option value="cpu">CPU — local Ollama, no GPU</option>
          <option value="single-gpu">Single GPU — local Ollama + one GPU</option>
          <option value="dual-gpu">Dual GPU — local Ollama + two GPUs</option>
          <option value="cf-orch">
            Orchard — CircuitForge GPU cluster
            {{ orchAvailable ? `(${orchGpus.length} GPU(s) available)` : '(configure endpoint below)' }}
          </option>
          <option value="remote">Remote — use cloud API keys</option>
        </select>
      </div>

      <!-- cf-orch cluster summary -->
      <template v-if="selectedProfile === 'cf-orch'">
        <div v-if="orchAvailable" class="step__orch-nodes">
          <p class="step__orch-label">Available nodes:</p>
          <div
            v-for="gpu in orchGpus"
            :key="`${gpu.node}-${gpu.name}`"
            class="step__orch-row"
          >
            <span class="step__orch-node">{{ gpu.node }}</span>
            <span class="step__orch-name">{{ gpu.name }}</span>
            <span class="step__orch-vram">
              {{ Math.round(gpu.vram_free_mb / 1024 * 10) / 10 }} /
              {{ Math.round(gpu.vram_total_mb / 1024 * 10) / 10 }} GB free
            </span>
          </div>
        </div>

        <div class="step__field">
          <label class="step__label" for="orch-url">Orchard coordinator URL</label>
          <input
            id="orch-url"
            v-model="orchUrl"
            type="url"
            class="step__input"
            placeholder="http://10.1.10.71:7700"
          />
          <p class="step__field-hint">
            The Orchard coordinator serves public inference endpoints for Paid+ users.
            Leave blank to use the default cluster URL from Settings.
          </p>
        </div>

        <div class="step__tier-note">
          <span aria-hidden="true">🔒</span>
          Orchard inference requires a <strong>Paid</strong> license or higher.
          You can select this profile now; it will activate once your license is verified.
        </div>
      </template>

      <div
        v-else-if="selectedProfile !== 'remote' && !wizard.hardware.gpus.length"
        class="step__warning"
      >
        ⚠️ No local GPUs detected — a GPU profile may not work. Choose CPU
        or Orchard if you have access to the cluster.
      </div>
    </template>

    <div class="step__nav step__nav--end">
      <button class="btn-primary" :disabled="wizard.saving" @click="next">
        {{ wizard.saving ? 'Saving…' : 'Next →' }}
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useWizardStore } from '../../stores/wizard'
import { useApiFetch } from '../../composables/useApi'
import './wizard.css'

const wizard = useWizardStore()
const router = useRouter()
const selectedProfile = ref(wizard.hardware.selectedProfile)

// Local loading flag — does NOT touch wizard.loading, avoiding the
// WizardLayout unmount loop that was causing the infinite spinner.
const detecting = ref(false)

// cf-orch cluster state
const orchAvailable = ref(false)
const orchGpus = ref<Array<{ node: string; name: string; vram_total_mb: number; vram_free_mb: number }>>([])
const orchUrl = ref('')

// local service probe results
const ollamaRunning = ref(false)
const searxngRunning = ref(false)

onMounted(async () => {
  detecting.value = true
  const { data } = await useApiFetch<{
    gpus: string[]
    suggested_profile: string
    profiles: string[]
    cf_orch_available: boolean
    cf_orch_gpus: Array<{ node: string; name: string; vram_total_mb: number; vram_free_mb: number }>
    ollama_running: boolean
    searxng_running: boolean
  }>('/api/wizard/hardware')
  detecting.value = false
  if (!data) return

  wizard.hardware.gpus = data.gpus
  wizard.hardware.suggestedProfile = data.suggested_profile as typeof wizard.hardware.suggestedProfile
  if (!wizard.hardware.selectedProfile || wizard.hardware.selectedProfile === 'remote') {
    wizard.hardware.selectedProfile = data.suggested_profile as typeof wizard.hardware.selectedProfile
    selectedProfile.value = wizard.hardware.selectedProfile
  }

  orchAvailable.value = data.cf_orch_available ?? false
  orchGpus.value = data.cf_orch_gpus ?? []
  ollamaRunning.value = data.ollama_running ?? false
  searxngRunning.value = data.searxng_running ?? false
})

async function next() {
  wizard.hardware.selectedProfile = selectedProfile.value as typeof wizard.hardware.selectedProfile
  const stepData: Record<string, unknown> = { inference_profile: selectedProfile.value }
  if (selectedProfile.value === 'cf-orch' && orchUrl.value) {
    stepData.cf_orch_url = orchUrl.value
  }
  const ok = await wizard.saveStep(1, stepData)
  if (ok) router.push('/setup/tier')
}
</script>

<style scoped>
.hw-services {
  display: flex;
  gap: var(--space-4);
  margin: var(--space-3) 0 var(--space-2);
  flex-wrap: wrap;
}

.hw-svc {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-3);
  border-radius: var(--radius-full);
  font-size: 0.8rem;
  font-weight: 500;
  border: 1px solid var(--color-border-light);
  background: var(--color-surface-alt);
}

.hw-svc--up  { border-color: color-mix(in srgb, var(--color-success) 40%, transparent); }
.hw-svc--down { opacity: 0.65; }

.hw-svc__dot {
  width: 8px;
  height: 8px;
  border-radius: var(--radius-full);
  flex-shrink: 0;
}

.hw-svc--up   .hw-svc__dot { background: var(--color-success); }
.hw-svc--down .hw-svc__dot { background: var(--color-text-muted); }

.hw-svc__name  { color: var(--color-text); }
.hw-svc__status { color: var(--color-text-muted); }
</style>
