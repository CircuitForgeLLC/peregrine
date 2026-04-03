<template>
  <div class="step">
    <h2 class="step__heading">Step 1 — Hardware Detection</h2>
    <p class="step__caption">
      Peregrine uses your hardware profile to choose the right inference setup.
    </p>

    <div v-if="wizard.loading" class="step__info">Detecting hardware…</div>

    <template v-else>
      <div v-if="wizard.hardware.gpus.length" class="step__success">
        ✅ Detected {{ wizard.hardware.gpus.length }} GPU(s):
        {{ wizard.hardware.gpus.join(', ') }}
      </div>
      <div v-else class="step__info">
        No NVIDIA GPUs detected. "Remote" or "CPU" mode recommended.
      </div>

      <div class="step__field">
        <label class="step__label" for="hw-profile">Inference profile</label>
        <select id="hw-profile" v-model="selectedProfile" class="step__select">
          <option value="remote">Remote — use cloud API keys</option>
          <option value="cpu">CPU — local Ollama, no GPU</option>
          <option value="single-gpu">Single GPU — local Ollama + one GPU</option>
          <option value="dual-gpu">Dual GPU — local Ollama + two GPUs</option>
        </select>
      </div>

      <div
        v-if="selectedProfile !== 'remote' && !wizard.hardware.gpus.length"
        class="step__warning"
      >
        ⚠️ No GPUs detected — a GPU profile may not work. Choose CPU or Remote
        if you don't have a local NVIDIA GPU.
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
import './wizard.css'

const wizard = useWizardStore()
const router = useRouter()
const selectedProfile = ref(wizard.hardware.selectedProfile)

onMounted(() => wizard.detectHardware())

async function next() {
  wizard.hardware.selectedProfile = selectedProfile.value
  const ok = await wizard.saveStep(1, { inference_profile: selectedProfile.value })
  if (ok) router.push('/setup/tier')
}
</script>
